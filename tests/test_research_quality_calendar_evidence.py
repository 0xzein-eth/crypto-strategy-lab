import unittest
from research_quality.calendar_evidence import interval_by_entry_day

class CalendarEvidenceTests(unittest.TestCase):
    def test_overlapping_trades_same_day_not_independent(self):
        rows=[("2026-10-20",0.1)]*200
        x=interval_by_entry_day(rows,families=5)
        self.assertEqual(x["distinct_entry_days"],1)
        self.assertIsNone(x["lcb_pct"])
    def test_sufficient_independent_days(self):
        rows=[(f"2026-09-{i:02d}",0.1) for i in range(1,26)]*4
        x=interval_by_entry_day(rows,families=5)
        self.assertTrue(x["enough_for_descriptive_interval"])
        self.assertEqual(x["lcb_pct"],0.1)
    def test_invalid_observations(self):
        with self.assertRaises(ValueError):
            interval_by_entry_day([("2026-10-20",float("nan"))],families=5)
    def test_empty(self):
        self.assertIsNone(interval_by_entry_day([],families=5)["ucb_pct"])
