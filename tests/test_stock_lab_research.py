"""Pure IDX historical research uses purge/embargo and never promotes alpha."""
import copy
import datetime as dt
import math
import unittest

from stock_lab import source,research,strategies

WIB=source.WIB


def dates(n=300):
    out=[]
    day=dt.date(2025,1,6)
    while len(out)<n:
        if day.weekday()<5:out.append(day)
        day+=dt.timedelta(days=1)
    return out


DAYS=dates()


def make_market():
    markets={}
    for j,ticker in enumerate(source.SYMBOLS):
        bars=[]
        for i,d in enumerate(DAYS):
            # Deterministic synthetic, never real market data or future fills.
            p=1000+i*(.15+.08*j)+40*math.sin((i+j*4)/11)
            op=p-(i%3)+1
            vol=1000000 if i%24 else 2100000
            bars.append({
                "date":d.isoformat(),"open":round(op,5),
                "high":round(max(op,p)+10,5),
                "low":round(min(op,p)-10,5),
                "close":round(p,5),"volume":vol,
            })
        markets[ticker]={
            "provider":source.PROVIDER,"venue":"IDX","currency":"IDR",
            "instrument":ticker,"history":bars,
            "history_sha256":source.sha(bars),"actions":{},
        }
    return markets


class PurgedTrainingEvidenceTests(unittest.TestCase):
    def test_three_chronological_periods_and_true_embargo(self):
        report=research.evaluate(make_market())
        self.assertEqual(report["schema"],research.SCHEMA)
        self.assertEqual(report["common_authentic_market_days"],300)
        self.assertEqual(set(report["per_arm"]),set(strategies.ARMS))
        split=report["chronological_splits"]
        self.assertEqual(split["training"]["observed_trading_days"],180)
        self.assertEqual(split["validation"]["observed_trading_days"],60)
        self.assertEqual(split["historical_holdout_repeatedly_inspected"]["observed_trading_days"],60)
        self.assertEqual(report["embargo_trading_sessions"],5)
        self.assertTrue(report["outcome_blind_untouched_future_holdout_not_completed"])
        self.assertFalse(report["candidate_auto_promoted_to_wallet"])
        self.assertFalse(report["live_order_permission"])
        self.assertTrue(report["unadjusted_prices_missing_dividend_total_returns"])

    def test_future_changes_do_not_change_training_or_preselected_arm(self):
        src=make_market()
        a=research.evaluate(src)
        other=copy.deepcopy(src)
        for sym in source.SYMBOLS:
            bars=other[sym]["history"]
            for row in bars[-12:]:
                row["open"]*=.9
                row["close"]*=.9
                row["high"]=max(row["high"],row["open"],row["close"])
                row["low"]=min(row["low"],row["open"],row["close"])
            other[sym]["history_sha256"]=source.sha(bars)
        b=research.evaluate(other)
        self.assertEqual(a["experimental_training_only_selected_arm"],
                         b["experimental_training_only_selected_arm"])
        for arm in strategies.ARMS:
            self.assertEqual(a["per_arm"][arm]["training"],
                             b["per_arm"][arm]["training"])
        self.assertEqual(a["training_ranked_by_after_cost_excess_return_only"],
                         b["training_ranked_by_after_cost_excess_return_only"])

    def test_source_tamper_rejected_and_partial_universe_not_backfilled(self):
        src=make_market()
        src["BBCA.JK"]["history"][30]["close"]=500000
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            research.evaluate(src)
        src=make_market()
        del src["TLKM.JK"]
        with self.assertRaisesRegex(ValueError,"entire predeclared"):
            research.evaluate(src)
        src=make_market()
        for sym in source.SYMBOLS:
            src[sym]["history"]=src[sym]["history"][:190]
            src[sym]["history_sha256"]=source.sha(src[sym]["history"])
        with self.assertRaisesRegex(ValueError,"200 real"):
            research.evaluate(src)

    def test_corporate_actions_exclude_windows_without_fake_total_return(self):
        src=make_market()
        before=research.evaluate(src)
        for s in source.SYMBOLS:
            src[s]["actions"]={DAYS[i].isoformat():{"dividend":{"amount_idr_per_share":100}}
                               for i in range(80,295)}
        after=research.evaluate(src)
        for arm in strategies.ARMS:
            total_before=sum(before["per_arm"][arm][k]["closed_historical_hypothetical_trades"]
                             for k in ("training","validation","historical_holdout_repeatedly_inspected"))
            total_after=sum(after["per_arm"][arm][k]["closed_historical_hypothetical_trades"]
                            for k in ("training","validation","historical_holdout_repeatedly_inspected"))
            self.assertLessEqual(total_after,total_before)
            self.assertTrue(after["per_arm"][arm]["excluded_actions_or_dividend_windows"]>=0)
        self.assertEqual(after["experimental_training_only_selected_arm"],None)

    def test_costs_always_charged_even_on_flat_prices(self):
        price=[{"open":1000} for _ in range(8)]
        value=research.cross_window_return(price,1,6)
        self.assertLess(value,0)
        self.assertGreater(value,-1)
        self.assertTrue(all(arm in research.evaluate(make_market())["per_arm"]
                            for arm in strategies.ARMS))


if __name__=="__main__":
    unittest.main()
