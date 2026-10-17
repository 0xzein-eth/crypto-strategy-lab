"""Tests for entry-frozen regime research without selection leakage."""
import datetime as dt
import unittest
import regime_evidence as re

def row(i, day, regime="24h_up", value=-1, horizon=4, late=False):
    return {"id": str(i), "strategy": "BR-v3",
            "created_at": day+"T12:00:00Z", "status": "CLOSED",
            "market_type": "perpetual", "late_excluded": late,
            "normalized_R": value, "horizon_hours": horizon,
            "side": "LONG", "regime": regime, "research_risk_pct": 1.5}

class RegimeEvidenceTests(unittest.TestCase):
    def test_strata_and_late_exclusion(self):
        rows = [row(1, "2026-10-01"), row(2, "2026-10-01", "24h_down"),
                row(3, "2026-10-01", horizon=8),
                row(4, "2026-10-01", late=True)]
        cells = re.evaluate(rows)["cells"]
        self.assertEqual(len(cells), 3)
        self.assertEqual(sum(c["eligible_closes"] for c in cells), 3)
        self.assertTrue(all(c["edge_proven"] is False for c in cells))

    def test_negative_training_regime_warning(self):
        rows = [row(i, (dt.date(2026, 9, 1)+dt.timedelta(days=i%35)).isoformat())
                for i in range(240)]
        cell = re.evaluate(rows)["cells"][0]
        self.assertTrue(cell["sample_ready_for_diagnostics"])
        self.assertTrue(cell["persistent_negative_warning"])
        self.assertFalse(cell["edge_proven"])

    def test_monitoring_not_used_in_training(self):
        import learner
        rows = []
        for i in range(40):
            day = (dt.date(2026, 8, 1)+dt.timedelta(days=i)).isoformat()
            v = 3 if learner.stable_bucket("holdout:"+day, 5) == 0 else -1
            for j in range(5):
                rows.append(row(i*5+j, day, value=v))
        cell = re.evaluate(rows)["cells"][0]
        self.assertTrue(cell["persistent_negative_warning"])
        self.assertGreater(cell["monitoring_closes_not_used"], 0)

if __name__ == "__main__":
    unittest.main()
