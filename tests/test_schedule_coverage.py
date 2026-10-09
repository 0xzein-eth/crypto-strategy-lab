"""No-network tests for rolling GitHub Actions observation coverage diagnostics."""
import unittest
import engine


class ScheduleCoverageTests(unittest.TestCase):
    def test_first_observation_has_insufficient_schedule_coverage(self):
        r = engine.recent_schedule_coverage(None, None)
        self.assertIsNone(r["estimated_10m_slot_coverage"])
        self.assertEqual(r["recent_observed_intervals"], 0)

    def test_regular_observations_receive_full_coverage(self):
        previous = {"scheduling_diagnostics": {
            "recent_observation_gaps_minutes": [9.9, 10.1, 12.0, 13.0]}}
        r = engine.recent_schedule_coverage(previous, 10.0)
        self.assertEqual(r["recent_observed_intervals"], 5)
        self.assertEqual(r["estimated_missed_10m_slots"], 0)
        self.assertEqual(r["estimated_10m_slot_coverage"], 1.0)

    def test_hours_long_gap_remains_visible_through_next_short_runs(self):
        initial = engine.recent_schedule_coverage(None, 149.486)
        self.assertGreater(initial["estimated_missed_10m_slots"], 10)
        last = {"scheduling_diagnostics": initial}
        for _ in range(3):
            updated = engine.recent_schedule_coverage(last, 10)
            last = {"scheduling_diagnostics": updated}
        self.assertLess(updated["estimated_10m_slot_coverage"], 0.35)
        self.assertEqual(updated["max_observed_gap_minutes"], 149.486)

    def test_history_is_bounded_and_old_outage_expires_only_after_new_observations(self):
        old = {"scheduling_diagnostics": {
            "recent_observation_gaps_minutes": [200] + [10] * 71}}
        r = engine.recent_schedule_coverage(old, 10, limit=72)
        self.assertEqual(r["recent_observed_intervals"], 72)
        self.assertEqual(r["max_observed_gap_minutes"], 10)
        self.assertEqual(r["estimated_10m_slot_coverage"], 1.0)

    def test_invalid_history_fails_closed(self):
        for bad in (None, "30", [float("nan")], [-2], [True]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    engine.recent_schedule_coverage(
                        {"scheduling_diagnostics": {
                            "recent_observation_gaps_minutes": bad}}, 10)
        with self.assertRaises(ValueError):
            engine.recent_schedule_coverage(None, -10)
        with self.assertRaises(ValueError):
            engine.recent_schedule_coverage(None, 2, limit=0)


if __name__ == "__main__":
    unittest.main()
