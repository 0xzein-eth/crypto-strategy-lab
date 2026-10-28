"""Integrity tests for the append-only per-run opportunity audit."""
import json
import tempfile
import unittest
from pathlib import Path

import opportunity_history


class OpportunityHistoryTests(unittest.TestCase):
    def test_appends_rows_and_verifies_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opportunities.jsonl"
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
            self.assertEqual(opportunity_history.verify(path), (2, second["head_sha256"]))
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([row["seq"] for row in rows], [1, 2])
            self.assertEqual(rows[1]["prev_hash"], rows[0]["hash"])

    def test_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opportunities.jsonl"
            opportunity_history.append(
                path, timestamp="2026-10-28T00:00:00Z",
                entry_mode="legacy-explore", audit={"screened_symbol_slots": 1},
                added=0, status="NO_NEW_SIGNALS", verified_events=0)
            row = json.loads(path.read_text())
            row["audit"]["screened_symbol_slots"] = 99
            path.write_text(json.dumps(row) + "\\n")
            with self.assertRaisesRegex(ValueError, "INTEGRITY_FAILURE"):
                opportunity_history.verify(path)


if __name__ == "__main__":
    unittest.main()
