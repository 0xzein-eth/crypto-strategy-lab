import unittest
import ml_walkforward


class WalkForwardMaturityTests(unittest.TestCase):
    def test_only_labels_matured_before_prediction_week_are_trainable(self):
        rows = [
            {"sample_id":"old","entry_at":"2026-10-01T00:00:00Z","labels":{"exit_observed_at":"2026-10-01T01:00:00Z"},"features":{"horizon_hours":1}},
            {"sample_id":"late","entry_at":"2026-10-04T00:00:00Z","labels":{"exit_observed_at":"2026-10-05T01:00:00Z"},"features":{"horizon_hours":1}},
            {"sample_id":"future","entry_at":"2026-10-06T00:00:00Z","labels":{"exit_observed_at":"2026-10-06T01:00:00Z"},"features":{"horizon_hours":1}},
            {"sample_id":"other","entry_at":"2026-10-01T00:00:00Z","labels":{"exit_observed_at":"2026-10-01T01:00:00Z"},"features":{"horizon_hours":4}},
        ]
        selected = ml_walkforward.matured_training_rows(rows,1,"2026-10-05T00:00:00Z")
        self.assertEqual([r["sample_id"] for r in selected],["old"])

    def test_prediction_week_starts_monday_utc(self):
        self.assertEqual(ml_walkforward.week_start("2026-11-05T12:00:00Z").isoformat(),"2026-11-02T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
