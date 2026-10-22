"""Offline, immutable-data-only regression for 30m v2 availability reporting."""
import datetime as dt
import unittest
from v2.observation_health import summarize
from v2.paper_portfolio import iso

UTC = dt.timezone.utc
START = dt.datetime(2026,10,20,10,7,tzinfo=UTC)


def record(minute):
    return {"tick":{"observed_at":iso(START + dt.timedelta(minutes=minute))}}


class ObservationHealthTests(unittest.TestCase):
    def test_missing_slots_are_not_counted_as_success(self):
        result=summarize([record(0),record(30),record(120)],
                         now=START+dt.timedelta(minutes=125))
        self.assertEqual(result["verified_observations"],3)
        self.assertEqual(result["completed_slots_since_first"],5)
        self.assertEqual(result["overall_coverage_pct"],60)
        self.assertEqual(result["status"],"BELOW_90_PERCENT_TARGET")
        self.assertEqual(result["max_recorded_gap_minutes"],90)
        self.assertTrue(result["market_observations_were_not_synthesized"])

    def test_no_data_never_claims_100pct(self):
        result=summarize([],now=START)
        self.assertIsNone(result["recent_6h_coverage_pct"])
        self.assertEqual(result["status"],"NO_VERIFIED_OBSERVATIONS")

    def test_late_and_duplicate_rows_refused(self):
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            summarize([record(0),record(2)],now=START+dt.timedelta(hours=1))
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            summarize([record(120)],now=START)

    def test_workflow_slot_output_is_real_newline_not_literal_escape(self):
        # Production regression from 2026-10-22: GitHub marked a v2
        # workflow successful but skipped the market observer despite a
        # freshly eligible slot because GITHUB_OUTPUT contained literal
        # backslash-n rather than a real newline.
        from pathlib import Path
        workflow=(Path(__file__).resolve().parent.parent /
                  ".github" / "workflows" / "v2-forward-paper.yml").read_text()
        self.assertIn('print("needs_observation="+str(observe).lower(),file=out)',
                      workflow)
        self.assertIn("Validate GITHUB_OUTPUT contains a real, parseable slot decision",
                      workflow)
        self.assertIn('case "$NEEDS_OBSERVATION" in',workflow)
        self.assertNotIn('out.write("needs_observation="+str(observe).lower()+"\\\\n")',
                         workflow)
        import io
        stream=io.StringIO()
        print("needs_observation="+str(True).lower(),file=stream)
        self.assertEqual(stream.getvalue(),"needs_observation=true\\n")

    def test_staleness_distinct_from_low_coverage(self):
        result=summarize([record(0)],now=START+dt.timedelta(hours=3))
        self.assertEqual(result["status"],"STALE")
        self.assertGreater(result["minutes_since_last_observation"],90)


if __name__=="__main__":
    unittest.main()
