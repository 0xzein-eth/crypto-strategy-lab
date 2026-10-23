import unittest
from research_quality.crypto_composite_audit import analyze
from v2.shadow_research import VERSION

def row(arm,side="LONG",value=0.2):
    return {"symbol":"BTC","entry_at":"2026-10-20T09:00:00+00:00",
            "arm":arm,"signal_side":side,"timely":True,
            "executable_topbook_quantity_both_sides":True,
            "assumed_stressed_net_pct":value}

class CryptoCompositeTests(unittest.TestCase):
    def test_agreeing_arms(self):
        x=analyze({"version":VERSION,"closed_outcomes":[
             row("TREND-v1"),row("BR-v3")]})
        self.assertEqual(x["results"]["consensus_trend_breakout_v1"]["matched_closed"],1)
        self.assertEqual(x["real_orders"],0)
    def test_conflicting_direction_abstains(self):
        x=analyze({"version":VERSION,"closed_outcomes":[
            row("TREND-v1"),row("BR-v3","SHORT")]})
        self.assertEqual(x["results"]["consensus_trend_breakout_v1"]["matched_closed"],0)
    def test_different_identical_path_return_rejected(self):
        with self.assertRaises(ValueError):
            analyze({"version":VERSION,"closed_outcomes":[
                row("TREND-v1"),row("BR-v3",value=.6)]})
    def test_missing_source_fails_closed(self):
        with self.assertRaises(ValueError):
            analyze({"closed_outcomes":[]})
    def test_nonfinite_matched_outcomes_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"nonfinite"):
            analyze({"version":VERSION,"closed_outcomes":[
                row("TREND-v1",value=float("nan")),row("BR-v3",value=float("nan"))]})
    def test_calendar_clusters_use_utc_entry_date(self):
        records=[]
        for at in ("2026-10-20T00:30:00+07:00","2026-10-19T23:00:00Z"):
            for arm in ("TREND-v1","BR-v3"):
                records.append({**row(arm),"entry_at":at})
        result=analyze({"version":VERSION,"closed_outcomes":records})
        self.assertEqual(result["results"]["consensus_trend_breakout_v1"]["entry_days"],1)
