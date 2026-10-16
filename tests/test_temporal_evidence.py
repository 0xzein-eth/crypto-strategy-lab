"""Temporal evidence readiness must count days, not correlated trade volume."""
import datetime as dt
import unittest
import temporal_evidence as te

UTC=dt.timezone.utc


def trade(n, day, strategy="CTRL-v1", regime="24h_up", hour=12,
          late=False, market="perpetual", status="CLOSED"):
    return {
        "id":str(n), "strategy":strategy,"created_at":day+"T%02d:00:00Z"%hour,
        "status":status, "market_type":market, "late_excluded":late,
        "normalized_R":0.1, "horizon_hours":4, "regime":regime,
    }


class TemporalMaturityTests(unittest.TestCase):
    def test_many_correlated_trades_on_one_day_are_not_mature(self):
        day="2026-10-16"
        data=[trade(i,day) for i in range(2500)]
        result=te.summarize(data,dt.datetime(2026,10,16,23,tzinfo=UTC))
        m=result["overall"]
        self.assertEqual(m["eligible_closes"],2500)
        self.assertEqual(m["distinct_entry_utc_days"],1)
        self.assertEqual(m["distinct_iso_weeks"],1)
        self.assertEqual(m["effective_equally_weighted_day_clusters_upper_bound"],1)
        self.assertFalse(m["data_maturity_ready"])
        self.assertEqual(m["additional_distinct_days_needed"],19)
        self.assertEqual(m["recent_7_calendar_days"]["observed_entry_utc_days"],1)
        self.assertFalse(result["edge_proven"])

    def test_genuine_20_days_and_four_weeks_ready_but_never_proves_edge(self):
        start=dt.date(2026,9,10)
        data=[]
        for d in range(30):
            day=(start+dt.timedelta(days=d)).isoformat()
            data.append(trade(d,day,regime="24h_up" if d%2 else "24h_down",
                              hour=(d%4)*6))
        result=te.summarize(
            data,dt.datetime(2026,10,16,12,tzinfo=UTC))
        m=result["overall"]
        self.assertEqual(m["distinct_entry_utc_days"],30)
        self.assertGreaterEqual(m["distinct_iso_weeks"],4)
        self.assertTrue(m["data_maturity_ready"])
        self.assertEqual(m["additional_distinct_days_needed"],0)
        self.assertEqual(m["recent_30_calendar_days"]["observed_entry_utc_days"],23)
        self.assertFalse(result["edge_proven"])

    def test_missing_days_not_interpolated_and_closed_eligibility_enforced(self):
        data=[trade("a","2026-10-08"),trade("b","2026-10-13"),
              trade("c","2026-10-13",late=True),
              trade("d","2026-10-14",market="spot_proxy"),
              trade("e","2026-10-15",status="OPEN")]
        m=te.summarize(data,dt.datetime(2026,10,16,tzinfo=UTC))["overall"]
        self.assertEqual(m["eligible_closes"],2)
        self.assertEqual(m["distinct_entry_utc_days"],2)
        self.assertEqual(m["calendar_span_days"],6)
        self.assertEqual(m["recent_7_calendar_days"]["observed_entry_utc_days"],2)
        self.assertFalse(m["data_maturity_ready"])

    def test_future_eligible_events_and_naive_clock_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"future"):
            te.summarize([trade("f","2026-10-17")],
                         dt.datetime(2026,10,16,tzinfo=UTC))
        with self.assertRaisesRegex(ValueError,"clock"):
            te.summarize([],dt.datetime(2026,10,16))


if __name__=="__main__":
    unittest.main()
