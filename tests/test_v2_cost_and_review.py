"""Evidence-first experiment triage never silently becomes real trading."""
import copy
import datetime as dt
import unittest

import learner
from v2.cost_gate import break_even,shadow_decision
from v2.paper_portfolio import OrderRejected
from v2.research_review import evaluate

UTC=dt.timezone.utc
NOW=dt.datetime(2026,10,19,11,0,tzinfo=UTC)


def book(when=NOW):
    return {"symbol":"BTC","provider":"okx-swap",
            "market_type":"perpetual","instrument":"BTC-USDT-SWAP",
            "observed_at":when.isoformat().replace("+00:00","Z"),
            "bid":100,"ask":100.1,
            "bid_size_base":100,"ask_size_base":100}


def row(ident,arm,day,value):
    return {
        "id":ident,"strategy":arm,
        "created_at":day+"T12:00:00Z",
        "status":"CLOSED","market_type":"perpetual",
        "late_excluded":False,"normalized_R":value,
        "horizon_hours":4,"symbol":"BTC","side":"LONG",
        "regime":"24h_up",
    }


class V2CandidateResearchTests(unittest.TestCase):
    def test_real_bid_ask_and_all_costs_raise_breakeven(self):
        base=break_even(book(),NOW,"BTC","LONG",
                        assumed_funding_adverse_bps=0,
                        impact_latency_bps=0,safety_buffer_bps=0)
        stressed=break_even(book(),NOW,"BTC","LONG",
                        assumed_funding_adverse_bps=15,
                        impact_latency_bps=10,safety_buffer_bps=15)
        self.assertGreater(base["minimum_favorable_mid_move_pct"],0.15)
        self.assertGreater(stressed["minimum_favorable_mid_move_pct"],
                           base["minimum_favorable_mid_move_pct"])
        self.assertFalse(stressed["trading_authorized"])
        short=break_even(book(),NOW,"BTC","SHORT",
                         assumed_funding_adverse_bps=0,
                         impact_latency_bps=0,safety_buffer_bps=0)
        self.assertGreater(short["minimum_favorable_mid_move_pct"],0.15)

    def test_no_prediction_means_no_trade(self):
        no=shadow_decision(book(),NOW,"BTC","LONG")
        self.assertEqual(no["status"],"NO_FROZEN_OUT_OF_SAMPLE_FORECAST")
        self.assertFalse(no["auto_paper_portfolio_entry"])
        b=shadow_decision(book(),NOW,"BTC","LONG",
                          forecast_model_id="frozen-bucket-v1",
                          model_training_end=NOW-dt.timedelta(days=1),
                          forecast_favorable_move_pct=0.02)
        self.assertEqual(b["status"],"FORECAST_BELOW_AFTER_COST_HURDLE")
        research=shadow_decision(book(),NOW,"BTC","LONG",
                          forecast_model_id="frozen-bucket-v1",
                          model_training_end=NOW-dt.timedelta(days=1),
                          forecast_favorable_move_pct=1.0)
        self.assertEqual(research["status"],"EXPLORATORY_SHADOW_CANDIDATE_ONLY")
        self.assertFalse(research["champion_proven"])
        self.assertFalse(research["trading_authorized"])
        leak=shadow_decision(book(),NOW,"BTC","LONG",
                          forecast_model_id="frozen-bucket-v1",
                          model_training_end=NOW+dt.timedelta(days=1),
                          forecast_favorable_move_pct=1.0)
        self.assertEqual(leak["status"],"MODEL_PROVENANCE_INSUFFICIENT")
        with self.assertRaises(OrderRejected):
            shadow_decision(book(),NOW,"BTC","SHORT",
                            forecast_model_id="v1",
                            model_training_end=NOW-dt.timedelta(days=1),
                            forecast_favorable_move_pct=999)

    def test_future_monitoring_cannot_change_train_triage(self):
        rows=[]
        # >=70 UTC days; all train -2R, all control 0R; deliberately
        # change MONITORING+100R and preserve an identical next-run triage.
        for i in range(70):
            day=(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat()
            rows.append(row("A"+str(i),"BR-v3",day,-2))
            rows.append(row("C"+str(i),"CTRL-v1",day,0))
        original=copy.deepcopy(rows)
        before=evaluate(rows,schedule_coverage=.99)
        self.assertEqual(rows,original)
        base=next(x for x in before["arms"] if x["strategy"]=="BR-v3")
        self.assertEqual(base["triage"],"PERSISTENT_TRAINING_NEGATIVE_REVIEW")
        modified=copy.deepcopy(rows)
        for r in modified:
            if learner.stable_bucket("holdout:"+r["created_at"][:10],5)==0:
                r["normalized_R"]=100
        after=evaluate(modified,schedule_coverage=.99)
        changed=next(x for x in after["arms"] if x["strategy"]=="BR-v3")
        for field in ("triage","training_eligible_n",
                      "training_distinct_utc_days",
                      "training_stress_scenario_mean_R",
                      "training_daily_descriptive_lcb_R"):
            self.assertEqual(base[field],changed[field])
        self.assertFalse(after["edge_proven"])
        self.assertIsNone(after["champion"])

    def test_many_correlated_trades_in_one_day_are_never_enough(self):
        rows=[row(str(i),"FB-v3","2026-10-19",1.2) for i in range(200)]
        result=evaluate(rows,schedule_coverage=1)
        stats=next(x for x in result["arms"] if x["strategy"]=="FB-v3")
        self.assertEqual(stats["training_distinct_utc_days"],0 if
                         learner.stable_bucket("holdout:2026-10-19",5)==0 else 1)
        self.assertEqual(stats["triage"],"INSUFFICIENT_INDEPENDENT_TRAINING_DAYS")
        self.assertFalse(stats["after_fee_and_real_fill_edge_proven"])
        self.assertFalse(result["existing_allocation_untouched"])

if __name__=="__main__":
    unittest.main()
