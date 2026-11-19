import datetime as dt
import unittest
from unittest.mock import patch

from equity_lab import stale_check

UTC = dt.timezone.utc


class EquityStalenessTests(unittest.TestCase):
    def test_recent_session_is_healthy(self):
        with patch.object(stale_check, "journal_last_session", return_value="2026-11-19"):
            stale, detail = stale_check.check(
                "NASDAQ", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertFalse(stale)
        self.assertEqual(detail["status"], "OK")
        self.assertEqual(detail["session_age_calendar_days"], 1)

    def test_market_specific_budget_is_enforced(self):
        with patch.object(stale_check, "journal_last_session", return_value="2026-11-13"):
            stale, detail = stale_check.check(
                "NASDAQ", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertTrue(stale)
        self.assertEqual(detail["status"], "STALE")
        self.assertEqual(detail["staleness_budget_calendar_days"], 5)

        with patch.object(stale_check, "journal_last_session", return_value="2026-11-13"):
            stale, detail = stale_check.check(
                "LQ45", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertFalse(stale)
        self.assertEqual(detail["staleness_budget_calendar_days"], 7)

    def test_missing_journal_fails_closed(self):
        with patch.object(stale_check, "journal_last_session", return_value=None):
            stale, detail = stale_check.check(
                "LQ45", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertTrue(stale)
        self.assertEqual(detail["status"], "STALE_NO_JOURNAL")

    def test_future_session_fails_closed(self):
        with patch.object(stale_check, "journal_last_session", return_value="2026-11-21"):
            stale, detail = stale_check.check(
                "NASDAQ", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertTrue(stale)
        self.assertEqual(detail["status"], "FUTURE_SESSION")

    def test_invalid_clock_and_market_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            stale_check.check("NASDAQ", now=dt.datetime(2026, 11, 20, 12))
        with self.assertRaisesRegex(ValueError, "unknown"):
            stale_check.check("NYSE", now=dt.datetime(2026, 11, 20, 12, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
