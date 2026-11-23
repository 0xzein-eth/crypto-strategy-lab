"""Lossless gzip archival for immutable paper-ledger JSONL files.

The uncompressed JSONL bytes are verified against the gzip stream before the
original working-tree file is removed. engine.replay() verifies the complete
event hash chain both before and after migration.
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path


def sha256_file(path, opener=open):
    digest = hashlib.sha256()
    with opener(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compress_file(path):
    """Create a deterministic gzip copy; remove source only after byte equality."""
    path = Path(path)
    target = Path(str(path) + ".gz")
    temporary = Path(str(target) + ".tmp")
    if not path.exists():
        if target.exists():
            return {"path": str(target), "status": "already_archived"}
        raise FileNotFoundError(path)
    if target.exists():
        if sha256_file(path) == sha256_file(target, opener=gzip.open):
            original_size = path.stat().st_size
            compressed_size = target.stat().st_size
            path.unlink()
            return {
                "path": str(target),
                "status": "archived_losslessly_recovered",
                "original_bytes": original_size,
                "compressed_bytes": compressed_size,
                "original_sha256": sha256_file(target, opener=gzip.open),
            }
        raise ValueError("ARCHIVE_INTEGRITY_FAILURE: source/archive collision")

    original_hash = sha256_file(path)
    try:
        with path.open("rb") as source, temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed, length=1024*1024)
        compressed_hash = sha256_file(temporary, opener=gzip.open)
        if compressed_hash != original_hash:
            raise ValueError("ARCHIVE_INTEGRITY_FAILURE: decompressed bytes differ")
        os.replace(temporary, target)
        # Verify the final path once more before unlinking the source.
        if sha256_file(target, opener=gzip.open) != original_hash:
            target.unlink(missing_ok=True)
            raise ValueError("ARCHIVE_INTEGRITY_FAILURE: final gzip verification failed")
        original_size = path.stat().st_size
        compressed_size = target.stat().st_size
        path.unlink()
        return {
            "path": str(target),
            "status": "archived_losslessly",
            "original_bytes": original_size,
            "compressed_bytes": compressed_size,
            "original_sha256": original_hash,
        }
    finally:
        temporary.unlink(missing_ok=True)


def archive_uncompressed(root=Path("."), keep_latest=1):
    """Compress older uncompressed daily shards; caller verifies replay afterward."""
    root = Path(root)
    events = root / "data" / "events"
    if keep_latest < 0:
        raise ValueError("keep_latest must be nonnegative")
    event_files = sorted(events.glob("????-??*.jsonl"))
    to_archive = event_files[:-keep_latest] if keep_latest else event_files
    archived = [compress_file(path) for path in to_archive]
    opportunity_path = root / "data" / "opportunity_history.jsonl"
    if opportunity_path.exists():
        archived.append(compress_file(opportunity_path))
    original_bytes = sum(row.get("original_bytes", 0) for row in archived)
    compressed_bytes = sum(row.get("compressed_bytes", 0) for row in archived)
    return {
        "archived_files": archived,
        "event_files_archived": sum(
            row.get("status") in ("archived_losslessly", "archived_losslessly_recovered")
            for row in archived if "events" in row.get("path", "")
        ),
        "original_bytes": original_bytes,
        "compressed_bytes": compressed_bytes,
        "space_saved_bytes": original_bytes-compressed_bytes,
        "source_jsonl_bytes_preserved_inside_gzip": True,
    }


def migrate(root=Path("."), keep_latest=1):
    """Archive old event shards and verify full ledgers before and after."""
    root = Path(root)
    import engine
    import opportunity_history

    before_records, before_sequence, before_head, before_next_id = engine.replay(root)
    opportunity_path = root / "data" / "opportunity_history.jsonl"
    before_opportunity = opportunity_history.verify_history(opportunity_path)
    archived = archive_uncompressed(root, keep_latest)
    after_records, after_sequence, after_head, after_next_id = engine.replay(root)
    after_opportunity = opportunity_history.verify_history(opportunity_path)
    if (before_records != after_records or
            (before_sequence, before_head, before_next_id) !=
            (after_sequence, after_head, after_next_id) or
            before_opportunity != after_opportunity):
        raise ValueError("ARCHIVE_INTEGRITY_FAILURE: replay changed after compression")
    return {
        "schema": "immutable-paper-ledger-gzip-archive-v1",
        **archived,
        "event_count_unchanged": after_sequence,
        "event_chain_head_unchanged": after_head,
        "opportunity_history_rows_unchanged": after_opportunity[0],
        "opportunity_history_head_unchanged": after_opportunity[1],
        "canonical_records_unchanged": True,
        "no_event_rows_rewritten": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--keep-latest", type=int, default=1)
    parser.add_argument("--incremental", action="store_true",
                        help="compress older uncompressed shards; caller must replay-verify afterward")
    args = parser.parse_args()
    result = (archive_uncompressed(Path(args.root), args.keep_latest)
              if args.incremental else migrate(Path(args.root), args.keep_latest))
    if args.incremental:
        result["incremental_mode"] = True
        result["replay_verification_required_afterward"] = True
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
