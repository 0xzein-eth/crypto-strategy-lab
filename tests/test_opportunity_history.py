"""Integrity tests for the append-only, daily-sharded opportunity audit."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import opportunity_history


class OpportunityHistoryTests(unittest.TestCase):
    def test_appends_rows_to_daily_shard_and_verifies_global_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "opportunity_history.jsonl"
            first = opportunity_history.append(
                path, timestamp="2026-10-28T00:00:00Z",
                entry_mode="legacy-explore",
                audit={"screened_symbol_slots": 18, "slots_with_no_confirmed_signal": 18},
                added=0, status="NO_NEW_SIGNALS", verified_events=10)
            second = opportunity_history.append(
                path, timestamp="2026-10-28T00:10:00Z",
                entry_mode="legacy-explore",
                audit={"screened_symbol_slots": 20, "slots_with_any_confirmed_signal": 2},
                added=2, status="OK", verified_events=12)
            self.assertEqual(first["rows"], 1)
            self.assertEqual(second["rows"], 2)
            self.assertNotEqual(first["head_sha256"], second["head_sha256"])
            self.assertEqual(opportunity_history.verify_history(path),
                             (2, second["head_sha256"]))
            shard = path.parent / "opportunity_history" / "2026-10-28.jsonl"
            rows = [json.loads(line) for line in shard.read_text().splitlines()]
            self.assertEqual([row["seq"] for row in rows], [1, 2])
            self.assertEqual(rows[1]["prev_hash"], rows[0]["hash"])
            self.assertFalse(path.exists())

    def test_tampering_in_daily_shard_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "opportunity_history.jsonl"
            opportunity_history.append(
                path, timestamp="2026-10-28T00:00:00Z",
                entry_mode="legacy-explore", audit={"screened_symbol_slots": 1},
                added=0, status="NO_NEW_SIGNALS", verified_events=0)
            shard = path.parent / "opportunity_history" / "2026-10-28.jsonl"
            row = json.loads(shard.read_text())
            row["audit"]["screened_symbol_slots"] = 99
            shard.write_text(json.dumps(row) + "\n")
            with self.assertRaisesRegex(ValueError, "INTEGRITY_FAILURE"):
                opportunity_history.verify_history(path)

    def test_legacy_file_is_frozen_and_daily_shards_continue_its_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "opportunity_history.jsonl"
            path.parent.mkdir(parents=True)
            row = {
                "seq": 1, "prev_hash": opportunity_history.GENESIS,
                "timestamp": "2026-10-27T23:50:00Z",
                "entry_mode": "legacy-explore", "audit": {"legacy": True},
                "added": 0, "status": "OK", "verified_events": 1,
            }
            digest = hashlib.sha256(
                opportunity_history.canonical(row).encode("utf-8")).hexdigest()
            path.write_text(opportunity_history.canonical(dict(row, hash=digest)) + "\n")
            original_bytes = path.read_bytes()

            result = opportunity_history.append(
                path, timestamp="2026-10-28T00:00:00Z",
                entry_mode="legacy-explore", audit={"new_shard": True},
                added=1, status="OK", verified_events=2)

            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertTrue(result["legacy_file_frozen"])
            self.assertEqual(result["rows"], 2)
            self.assertEqual(opportunity_history.verify_history(path),
                             (2, result["head_sha256"]))
            shard = path.parent / "opportunity_history" / "2026-10-28.jsonl"
            new_row = json.loads(shard.read_text())
            self.assertEqual(new_row["seq"], 2)
            self.assertEqual(new_row["prev_hash"], digest)

    def test_shards_are_separated_by_utc_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "opportunity_history.jsonl"
            opportunity_history.append(
                path, timestamp="2026-10-28T23:59:00+05:00",
                entry_mode="legacy-explore", audit={}, added=0,
                status="OK", verified_events=1)
            result = opportunity_history.append(
                path, timestamp="2026-10-29T05:01:00Z",
                entry_mode="legacy-explore", audit={}, added=0,
                status="OK", verified_events=2)
            directory = path.parent / "opportunity_history"
            self.assertEqual(sorted(p.name for p in directory.glob("*.jsonl")),
                             ["2026-10-28.jsonl", "2026-10-29.jsonl"])
            self.assertEqual(opportunity_history.verify_history(path),
                             (2, result["head_sha256"]))


if __name__ == "__main__":
    unittest.main()
