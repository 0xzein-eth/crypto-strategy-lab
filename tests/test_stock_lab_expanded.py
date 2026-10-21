"""Synthetic ONLY: enlarged IDX cohort is never written as live evidence."""
import copy
import datetime as dt
import math
import unittest

from stock_lab import engine, experimental, expanded_research, source

WIB=source.WIB


def fake_market(n=300, symbols=None):
    symbols=symbols or source.HISTORICAL_RESEARCH_SYMBOLS
    dates=[]
    date=dt.date(2024,1,2)
    while len(dates)<n:
        if date.weekday()<5:dates.append(date.isoformat())
        date+=dt.timedelta(days=1)
    out={}
    for j,symbol in enumerate(symbols):
        rows=[]
        for i,d in enumerate(dates):
            px=900+j*33+i*(0.6+j*0.02)+32*math.sin(i/17+j)
            op=px-1.7
            rows.append({"date":d,"open":round(op,5),
                         "high":round(max(op,px)+6,5),
                         "low":round(min(op,px)-6,5),
                         "close":round(px,5),"volume":int(1_000_000+i*1500+(i%40)*5000)})
        out[symbol]={"provider":source.PROVIDER,"venue":"IDX","currency":"IDR",
                     "history":rows,"history_sha256":source.sha(rows),"actions":{}}
    return out


class ExpandedHistoricalStudy(unittest.TestCase):
    def test_preserves_frozen_four_arm_cash_wallet(self):
        self.assertEqual(len(source.SYMBOLS),6)
        self.assertEqual(len(source.HISTORICAL_RESEARCH_SYMBOLS),18)
        self.assertEqual(len(experimental.ARMS),10)
        self.assertEqual(len(engine.source.SYMBOLS),6)
        self.assertIn("BBNI.JK",source.endpoint("BBNI.JK"))
        with self.assertRaisesRegex(ValueError,"ticker"):
            source.endpoint("TSLA")

    def test_chronological_expanded_study_no_promotion(self):
        out=expanded_research.evaluate(fake_market())
        self.assertEqual(out["common_genuine_sessions"],300)
        self.assertEqual(len(out["expanded_symbols_observed"]),18)
        self.assertEqual(set(out["per_arm"]),set(experimental.ARMS))
        self.assertEqual(out["split_sessions"]["training"]["days"],180)
        self.assertEqual(out["split_sessions"]["validation"]["days"],60)
        self.assertEqual(
            out["split_sessions"]["historical_holdout_repeatedly_inspected"]["days"],60)
        self.assertTrue(out["survivorship_dividend_and_open_auction_bias_remain"])
        self.assertFalse(out["candidate_auto_promoted"])
        self.assertFalse(out["independent_out_of_sample_edge_proven"])
        for arm in experimental.ARMS:
            self.assertFalse(out["per_arm"][arm]["training"]["portfolio_roi_claimed"])

    def test_no_lookahead_on_completed_bars(self):
        m=fake_market()
        rows=m["BBCA.JK"]["history"]
        a=experimental.signals(rows[:200])
        future=copy.deepcopy(rows)
        future[250]["close"]*=2
        self.assertEqual(a,experimental.signals(future[:200]))
        self.assertEqual(set(a),set(experimental.ARMS))
        self.assertEqual(set(a.values())-{"BUY","FLAT"},set())

    def test_source_hash_tamper_rejected(self):
        m=fake_market()
        m["BBCA.JK"]["history"][150]["close"]=500000
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            expanded_research.evaluate(m)

    def test_minimum_common_history_never_fabricated(self):
        m=fake_market()
        for symbol in m:
            m[symbol]["history"]=m[symbol]["history"][:220]
            m[symbol]["history_sha256"]=source.sha(m[symbol]["history"])
        with self.assertRaisesRegex(ValueError,"250 genuine"):
            expanded_research.evaluate(m)

    def test_observer_keeps_frozen_six_symbols_only(self):
        with self.assertRaisesRegex(ValueError,"fixed cash-equity"):
            source.capture(symbols=source.HISTORICAL_RESEARCH_SYMBOLS,
                           now=dt.datetime(2026,10,21,19,tzinfo=WIB))


if __name__=="__main__":
    unittest.main()
