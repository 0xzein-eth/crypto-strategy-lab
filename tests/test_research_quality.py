"""Fail-closed evidence quality checks."""
import unittest
import research_quality as rq

def row(ident, strategy, day="2026-10-08"):
    return {"id": ident, "strategy": strategy, "created_at": day+"T12:00:00Z",
            "status": "CLOSED", "market_type": "perpetual", "late_excluded": False,
            "normalized_R": 0.2, "horizon_hours": 4}

def comparison(n=100, days=25, fraction=0.8, lcb=0.1):
    return {"arms": {"BR-v3": {"matched_pairs": n,
            "matched_entry_utc_days": days, "matched_fraction": fraction,
            "day_cluster_95pct_descriptive_lcb_after_friction_R": lcb}}}

class QualityTests(unittest.TestCase):
    def test_sparse_data_fails_closed(self):
        result = rq.evaluate([row("1", "BR-v3")], comparison(), 1)
        self.assertFalse(result["arms"]["BR-v3"]["quality_gate_pass"])
        self.assertFalse(result["arms"]["BR-v3"]["edge_proven"])

    def test_bad_coverage_fails(self):
        rows = [row(str(i), "BR-v3", "2026-10-%02d" % (1+i%25))
                for i in range(200)]
        result = rq.evaluate(rows, comparison(), 0.72)
        self.assertIn("LOW_OR_UNKNOWN_SCHEDULER_COVERAGE",
                      result["arms"]["BR-v3"]["blocking_reasons"])

    def test_never_claims_edge_even_when_ready(self):
        import datetime as dt
        rows = [row(str(i), "BR-v3",
                    (dt.date(2026, 9, 1)+dt.timedelta(days=i%50)).isoformat())
                for i in range(300)]
        result = rq.evaluate(rows, comparison(days=50), 0.99)
        self.assertTrue(result["arms"]["BR-v3"]["quality_gate_pass"])
        self.assertFalse(result["arms"]["BR-v3"]["edge_proven"])

    def test_invalid_coverage_fails(self):
        for coverage in (None, float("nan"), True, 1.5, -1):
            with self.subTest(coverage=coverage):
                self.assertFalse(rq.evaluate([], comparison(), coverage)["schedule_coverage_gate"])

if __name__ == "__main__":
    unittest.main()
