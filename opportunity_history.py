"""Append-only, hash-chained run-level opportunity audit.

This is diagnostic telemetry, separate from the canonical OPEN/CLOSE ledger.
It records inspected opportunity denominators and abstention reasons without
pretending that aggregate tick counters are individual independent samples.
"""
import hashlib
import json
from pathlib import Path


GENESIS = "0" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def verify(path):
    """Verify every persisted row; fail closed on malformed or edited history."""
    path = Path(path)
    if not path.exists():
        return 0, GENESIS
    seq, head = 0, GENESIS
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"OPPORTUNITY_HISTORY_INTEGRITY_FAILURE line {line_number}") from exc
            digest = row.pop("hash", None)
            if (row.get("seq") != seq + 1 or row.get("prev_hash") != head or
                    not isinstance(digest, str) or
                    hashlib.sha256(canonical(row).encode("utf-8")).hexdigest() != digest):
                raise ValueError(f"OPPORTUNITY_HISTORY_INTEGRITY_FAILURE line {line_number}")
            seq += 1
            head = digest
    return seq, head


def append(path, *, timestamp, entry_mode, audit, added, status, verified_events):
    """Verify old rows then append one real observer tick's aggregate audit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seq, head = verify(path)
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
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical(dict(row, hash=digest)) + "\n")
        stream.flush()
    return {"version": "opportunity-history-hash-chain-v1",
            "path": "data/opportunity_history.jsonl",
            "rows": seq + 1, "head_sha256": digest,
            "append_only": True, "individual_opportunities_not_reconstructed": True}
