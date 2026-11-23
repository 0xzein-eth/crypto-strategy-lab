"""Append-only, hash-chained run-level opportunity audit.

The immutable legacy JSONL may be gzip-archived byte-for-byte. New rows are
written to UTC-day shards; one global hash chain spans legacy and new files.
"""
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

GENESIS = "0" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _legacy_path(path):
    path = Path(path)
    compressed = Path(str(path) + ".gz")
    if path.exists():
        return path
    if compressed.exists():
        return compressed
    return path


def _verify_rows(path, seq=0, head=GENESIS):
    """Verify a file as the next segment of one global hash chain."""
    path = Path(path)
    if not path.exists():
        return seq, head
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(
                    f"OPPORTUNITY_HISTORY_INTEGRITY_FAILURE {path} line {line_number}"
                ) from exc
            digest = row.pop("hash", None)
            if (row.get("seq") != seq + 1 or row.get("prev_hash") != head or
                    not isinstance(digest, str) or
                    hashlib.sha256(canonical(row).encode("utf-8")).hexdigest() != digest):
                raise ValueError(
                    f"OPPORTUNITY_HISTORY_INTEGRITY_FAILURE {path} line {line_number}"
                )
            seq += 1
            head = digest
    return seq, head


def verify(path):
    """Verify a standalone legacy JSONL, transparently reading .jsonl.gz."""
    return _verify_rows(_legacy_path(path))


def shard_directory(path):
    """Return the daily-shard directory associated with the legacy file path."""
    path = Path(path)
    return path.parent / path.stem


def verify_history(path):
    """Verify immutable legacy rows followed by every ordered daily shard."""
    path = Path(path)
    seq, head = _verify_rows(_legacy_path(path))
    directory = shard_directory(path)
    if directory.exists():
        for shard in sorted(directory.glob("*.jsonl")):
            if not shard.is_file():
                continue
            seq, head = _verify_rows(shard, seq, head)
    return seq, head


def _utc_day(timestamp):
    if not isinstance(timestamp, str):
        raise ValueError("OPPORTUNITY_HISTORY_INVALID_TIMESTAMP")
    try:
        value = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("OPPORTUNITY_HISTORY_INVALID_TIMESTAMP") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("OPPORTUNITY_HISTORY_INVALID_TIMESTAMP: timezone required")
    return value.astimezone(dt.timezone.utc).date().isoformat()


def append(path, *, timestamp, entry_mode, audit, added, status, verified_events):
    """Verify complete history then append to the current UTC-day shard.

    The pre-existing opportunity-history segment is frozen. If gzip archived,
    it is still verified and remains the first segment of the same hash chain.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_path(path)
    seq, head = verify_history(path)
    day = _utc_day(timestamp)
    directory = shard_directory(path)
    directory.mkdir(parents=True, exist_ok=True)
    shard = directory / f"{day}.jsonl"
    row = {
        "seq": seq + 1,
        "prev_hash": head,
        "timestamp": timestamp,
        "entry_mode": entry_mode,
        "audit": audit,
        "added": added,
        "status": status,
        "verified_events": verified_events,
    }
    digest = hashlib.sha256(canonical(row).encode("utf-8")).hexdigest()
    with shard.open("a", encoding="utf-8") as stream:
        stream.write(canonical(dict(row, hash=digest)) + "\n")
        stream.flush()
    return {
        "version": "opportunity-history-hash-chain-v2-daily-shards",
        "path": str(shard.relative_to(path.parent.parent)).replace("\\", "/"),
        "rows": seq + 1,
        "head_sha256": digest,
        "legacy_file_frozen": legacy.exists(),
        "legacy_file_compressed": legacy.suffix == ".gz" and legacy.exists(),
        "daily_shards": len(list(directory.glob("*.jsonl"))),
        "append_only": True,
        "individual_opportunities_not_reconstructed": True,
    }
