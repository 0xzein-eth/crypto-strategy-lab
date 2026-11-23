"""Lossless archive migration tests."""
import gzip
import tempfile
import unittest
from pathlib import Path

import archive_event_data


class ArchiveEventDataTests(unittest.TestCase):
    def test_compress_file_preserves_exact_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "2026-11_daily_22.jsonl"
            payload = (b'{"seq":1,"hash":"abc"}\n' * 1000)
            source.write_bytes(payload)
            result = archive_event_data.compress_file(source)
            target = Path(str(source) + ".gz")
            self.assertFalse(source.exists())
            self.assertTrue(target.exists())
            self.assertEqual(gzip.decompress(target.read_bytes()), payload)
            self.assertEqual(result["status"], "archived_losslessly")
            self.assertEqual(result["original_bytes"], len(payload))
            self.assertLess(result["compressed_bytes"], len(payload))

    def test_incremental_archiver_keeps_only_latest_event_shard_plain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "data" / "events"
            events.mkdir(parents=True)
            payloads = {}
            for day in (21, 22, 23):
                path = events / f"2026-11_daily_{day:02d}.jsonl"
                payloads[path.name] = (f"immutable-event-{day}\\n" * 100).encode()
                path.write_bytes(payloads[path.name])
            opportunity = root / "data" / "opportunity_history.jsonl"
            opportunity.write_bytes(b"immutable-opportunity-history\\n" * 100)

            result = archive_event_data.archive_uncompressed(root, keep_latest=1)

            self.assertEqual(result["event_files_archived"], 2)
            for name in ("2026-11_daily_21.jsonl", "2026-11_daily_22.jsonl"):
                self.assertFalse((events / name).exists())
                self.assertEqual(gzip.decompress((events / (name+".gz")).read_bytes()),
                                 payloads[name])
            self.assertTrue((events / "2026-11_daily_23.jsonl").exists())
            self.assertTrue(Path(str(opportunity)+".gz").exists())
            self.assertFalse(opportunity.exists())

    def test_compression_is_idempotent_when_archive_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "history.jsonl"
            source.write_bytes(b'row\n')
            archive_event_data.compress_file(source)
            target = Path(str(source) + ".gz")
            result = archive_event_data.compress_file(source)
            self.assertEqual(result["status"], "already_archived")
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
