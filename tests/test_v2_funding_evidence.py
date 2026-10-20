"""Actual settled funding is an observed cash-flow, never a guessed 0%."""
import copy
import datetime as dt
import unittest

from v2 import funding_evidence as e
from v2 import shadow_research as sh
from v2 import forward_paper as f

UTC=dt.timezone.utc
DAY=dt.datetime(2026,10,20,0,tzinfo=UTC)
H="3"*64


def rates():
    return {
        symbol:[[int((DAY+dt.timedelta(hours=h)).timestamp()*1000),.0001]
                for h in (0,8,16,24,32)]
        for symbol in e.SYMBOLS
    }


def record():
    entry=DAY+dt.timedelta(hours=2)
    closed=DAY+dt.timedelta(hours=10)
    return {
        "entry_id":"BTC:FB-v3:synthetic", "symbol":"BTC","arm":"FB-v3",
        "timely":True,"executable_topbook_quantity_both_sides":True,
        "signal_side":"LONG","neutral_control_side":"SHORT",
        "entry_at":entry.isoformat(),"genuine_exit_book_at":closed.isoformat(),
        "entry_day":entry.date().isoformat(),
        "assumed_net_after_book_and_fees_pct":0.5,
        "same_time_neutral_net_after_book_fee_pct":-0.4,
    }


def fixtures():
    opened=DAY+dt.timedelta(hours=2)
    closed=DAY+dt.timedelta(hours=10)
    wallet={
        "version":f.VERSION,"last_tick_hash":H,
        "real_order_submissions":0,
        "recorded_closed_outcomes":[{
            "id":"V2-example", "symbol":"BTC", "side":"LONG",
            "opened_at":opened.isoformat(),"actually_closed_at":closed.isoformat(),
            "net_after_bidask_and_fee_before_unverified_funding_usdt":"1.00"}],
    }
    shadow={
        "version":sh.VERSION,"last_source_hash":H,
        "real_order_submissions":0,
        "catalog_arms":list(sh.ARMS),
        "closed_outcomes":[record()],
    }
    return wallet,shadow


class SettledFundingEvidenceTests(unittest.TestCase):
    def test_cross_settlement_long_short_are_opposite_signed_costs(self):
        items=rates()["BTC"]
        start=DAY+dt.timedelta(hours=2)
        close=DAY+dt.timedelta(hours=10)
        self.assertEqual(float(e.funding_cost_pct(items,"LONG",start,close)),.01)
        self.assertEqual(float(e.funding_cost_pct(items,"SHORT",start,close)),-.01)
        with self.assertRaises(ValueError):
            e.funding_cost_pct(items,"LONG",close,start)

    def test_real_settlement_adjusts_only_closed_shadow_and_wallet_cash_flow(self):
        w,s=fixtures()
        original=(copy.deepcopy(w),copy.deepcopy(s))
        output=e.reconcile(w,s,rates=rates())
        self.assertEqual(output["matched_shadow_closes_with_actual_settlements"],1)
        self.assertEqual(output["per_arm"]["FB-v3"]["funding_known_matched_timely_closes"],1)
        pair=output["settlement_eligible_shadow_rows"][0]
        self.assertAlmostEqual(pair["settled_funding_adjusted_net_pct"],.49)
        self.assertAlmostEqual(pair["settled_funding_adjusted_control_net_pct"],-.39)
        self.assertAlmostEqual(pair["incremental_after_settled_funding_pct"],.88)
        self.assertEqual(output["closed_wallet_results_with_measured_funding"][0][
            "historical_closed_net_after_measured_funding_usdt"],"0.9800")
        self.assertFalse(output["wallet_final_equity_adjusted_for_all_funding"])
        self.assertFalse(output["90_day_untouched_alpha_proven"])
        self.assertFalse(output["live_deployment_authorized"])
        self.assertEqual(original,(w,s))

    def test_unknown_funding_is_never_fake_zero(self):
        w,s=fixtures()
        rs=rates()
        rs["BTC"]=[]
        output=e.reconcile(w,s,rates=rs)
        self.assertEqual(output["matched_shadow_closes_with_actual_settlements"],0)
        self.assertEqual(output["per_arm"]["FB-v3"]["missing_funding_intervals_excluded_not_zero"],1)
        self.assertIsNone(output["per_arm"]["FB-v3"]["mean_after_settled_funding_pct"])
        self.assertEqual(output["closed_wallet_missing_settled_funding_count"],1)

    def test_source_mismatch_private_orders_and_wrong_catalog_fail_closed(self):
        w,s=fixtures()
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            e.reconcile(w,{**s,"last_source_hash":"a"*64},rates=rates())
        with self.assertRaisesRegex(ValueError,"forbidden"):
            e.reconcile({**w,"real_order_submissions":1},s,rates=rates())
        with self.assertRaisesRegex(ValueError,"catalog"):
            e.reconcile(w,{**s,"catalog_arms":["FB-v3"]},rates=rates())
        with self.assertRaisesRegex(ValueError,"incomplete source instrument"):
            e.reconcile(w,s,rates={"BTC":rates()["BTC"]})

    def test_no_trade_can_pay_after_future_settlement(self):
        start=DAY+dt.timedelta(hours=2)
        close=DAY+dt.timedelta(hours=6)
        result=e.funding_cost_pct(rates()["BTC"],"LONG",start,close)
        self.assertEqual(float(result),0.0)
        # This zero is legitimate only because a real, audited
        # settlement timeline was independently supplied and covered.

if __name__=="__main__":
    unittest.main()
