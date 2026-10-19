"""Coverage-first PAPER sampling: data quality, unbiased allocation, observability."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

import engine
import entry_sampling
import learner

UTC=dt.timezone.utc
WHEN=dt.datetime(2026,10,18,16,0,tzinfo=UTC)


def old(arm, when, status="CLOSED", market="perpetual", result=-2.0):
    return {"strategy":arm, "created_at":engine.stamp(when),
            "market_type":market, "status":status, "normalized_R":result,
            "late_excluded":status=="CLOSED" and result < 0}


def quote(time=WHEN, symbol="BTC"):
    return {"symbol":symbol, "price":100.0, "pct24h":2.5,
            "quote_volume_24h":5_000_000.0,
            "observed_at":engine.stamp(time),
            "provider":"okx-swap","market_type":"perpetual",
            "instrument":symbol+"-USDT-SWAP"}


def candidates():
    return [{"strategy":"BR-v3","side":"LONG","evidence":{"bar_span":"15m confirmed OKX USDT-SWAP"}},
            {"strategy":"BRREG-v1","side":"LONG","evidence":{"bar_span":"15m confirmed OKX USDT-SWAP",
                                                              "hypothesis_version":"entry-regime-confirmation-v1"}}]


class EntryExposureTests(unittest.TestCase):
    def test_entry_time_count_excludes_no_outcomes_but_includes_late_closed(self):
        p=[old("BRREG-v1", WHEN-dt.timedelta(days=1), result=-99),
           old("BRREG-v1", WHEN-dt.timedelta(days=2), status="OPEN"),
           old("BRREG-v1", WHEN-dt.timedelta(days=8), result=900),
           old("BR-v3", WHEN-dt.timedelta(days=2), market="spot_proxy"),
           old("BR-v3", WHEN+dt.timedelta(days=1)),
           old("BR-v3", WHEN-dt.timedelta(days=6))]
        counts=entry_sampling.recent_confirmed_open_counts(p,WHEN)
        self.assertEqual(counts["BRREG-v1"],2)
        self.assertEqual(counts["BR-v3"],1)
        self.assertEqual(counts["TPREG-v1"],0)
        changed=copy.deepcopy(p)
        for r in changed:
            r["normalized_R"]=-r["normalized_R"]
            r["status"]="CLOSED" if r["status"]=="OPEN" else "OPEN"
            r["late_excluded"]=not r["late_excluded"]
        self.assertEqual(entry_sampling.recent_confirmed_open_counts(changed,WHEN),counts)
        with self.assertRaisesRegex(ValueError,"naive"):
            entry_sampling.recent_confirmed_open_counts(p,WHEN.replace(tzinfo=None))

    def test_no_luck_or_monitoring_outcome_can_change_coverage_selection(self):
        choices=[{"strategy":"CTRL-v1","side":"LONG"},
                 {"strategy":"BR-v3","side":"LONG"},
                 {"strategy":"BRREG-v1","side":"LONG"}]
        counts={"BR-v3":150,"BRREG-v1":2}
        profile={"entry_exposure_counts_v1":counts}
        winners=[]
        for slot in range(1500):
            winner,mode=learner.choose(choices,[], "BTC",4,slot,0,profile)
            winners.append((winner["strategy"],mode))
        self.assertGreater(sum(a=="CTRL-v1" for a,_ in winners),220)
        self.assertGreater(sum(a=="BRREG-v1" for a,_ in winners),250)
        self.assertGreater(sum(mode=="confirmed_entry_coverage_neutral_exploration"
                               for _,mode in winners),260)
        self.assertTrue(all(a in {x["strategy"] for x in choices} for a,_ in winners))
        reversed_rewards={"entry_exposure_counts_v1":dict(counts),
                          "allocation_leaders":["BR-v3"],
                          "training_only_underperformers":["BRREG-v1"]}
        self.assertEqual(winners,[
            (y["strategy"],m) for slot in range(1500)
            for y,m in [learner.choose(choices,[], "BTC",4,slot,0,reversed_rewards)]])
        # No confirmed candidate may be synthesised from counts.
        options=choices[:1]
        self.assertEqual(learner.choose(options,[],"BTC",4,999,0,profile)[0]["strategy"],
                         "CTRL-v1")

    def test_opportunities_are_distinct_from_executed_paper_opens(self):
        audit={}
        with patch.object(engine,"SYMBOLS",("BTC",)):
            prior={"LAB-123":old("BR-v3", WHEN-dt.timedelta(days=1))}
            original=copy.deepcopy(prior)
            opens=engine.new_candidates(prior, lambda s,p:quote(),
                                        WHEN,5000,1,
                                        advanced=lambda s,q:candidates(),
                                        reobserve=lambda s,p:quote(),
                                        clock=lambda:WHEN,
                                        opportunity_audit=audit)
        self.assertEqual(prior,original)
        self.assertEqual(audit["eligible_quote_symbols"],1)
        self.assertEqual(audit["screened_symbol_slots"],1)
        self.assertEqual(audit["advanced_source_checks"],1)
        self.assertEqual(audit["slots_with_any_confirmed_signal"],1)
        self.assertEqual(audit["confirmed_arm_opportunities"]["BR-v3"],1)
        self.assertEqual(audit["confirmed_arm_opportunities"]["BRREG-v1"],1)
        self.assertEqual(sum(audit["new_paper_opens_by_arm"].values()),len(opens))
        self.assertLessEqual(len(opens),1)
        self.assertEqual(audit["recent_7d_confirmed_open_counts"]["BR-v3"],1)
        self.assertEqual(audit["recent_7d_confirmed_open_counts"]["BRREG-v1"],0)
        self.assertTrue(all(r["evidence"]["performance_neutral_allocation"] for r in opens))
        self.assertTrue(all(r["evidence"]["allocation_policy"].startswith("learner-v7-") for r in opens))
        for position in opens:
            engine.validate_open(position)

    def test_missing_confirmed_ohlcv_does_not_fabricate_strategy(self):
        audit={}
        with patch.object(engine,"SYMBOLS",("BTC",)):
            result=engine.new_candidates({},lambda s,p:quote(),WHEN,700,1,
                                         advanced=lambda s,q:[],
                                         reobserve=lambda s,p:quote(),
                                         clock=lambda:WHEN, opportunity_audit=audit)
        self.assertEqual(audit["slots_with_no_confirmed_signal"],1)
        self.assertEqual(audit["confirmed_arm_opportunities"],{})
        self.assertTrue(all(r["strategy"] in learner.BASELINES for r in result))

    def test_quote_rejection_does_not_create_an_open_from_signal(self):
        audit={}
        with patch.object(engine,"SYMBOLS",("BTC",)):
            result=engine.new_candidates({},lambda s,p:quote(),WHEN,800,1,
                                         advanced=lambda s,q:candidates(),
                                         reobserve=lambda s,p:quote(symbol="ETH"),
                                         clock=lambda:WHEN, opportunity_audit=audit)
        self.assertEqual(result,[])
        self.assertEqual(audit["confirmed_arm_opportunities"]["BRREG-v1"],1)
        self.assertEqual(audit["fresh_entry_quote_rejections"],1)
        self.assertEqual(audit["new_paper_opens_by_arm"],{})

    def test_daily_quota_and_concurrent_limit_reasons_are_explicit(self):
        # Including already CLOSED entries: quota is about real OPENs made
        # today, not about how many remained open or won.
        history={"LAB-1":old("BR-v3", WHEN-dt.timedelta(minutes=5))}
        preserved=copy.deepcopy(history)
        audit={}
        with patch.object(engine,"MAX_NEW_PER_UTC_DAY",1):
            new=engine.new_candidates(history,lambda s,p:quote(),WHEN,600,10,
                                      opportunity_audit=audit)
        self.assertEqual(new,[])
        self.assertEqual(history,preserved)
        self.assertEqual(audit["utc_day_quota_remaining_before_tick"],0)
        self.assertEqual(audit["no_new_entry_reason"],"DAILY_OPEN_QUOTA_REACHED")

        audit={}
        with patch.object(engine,"MAX_OPEN",0):
            new=engine.new_candidates({},lambda s,p:quote(),WHEN,600,10,
                                      opportunity_audit=audit)
        self.assertEqual(new,[])
        self.assertEqual(audit["no_new_entry_reason"],"MAX_CONCURRENT_OPEN_REACHED")

    def test_no_public_quotes_is_not_claimed_to_be_no_market_signals(self):
        audit={}
        with patch.object(engine,"SYMBOLS",("BTC",)):
            result=engine.new_candidates(
                {},lambda s,p:quote() if False else (_ for _ in ()).throw(
                    RuntimeError("PUBLIC_PRICE_MISSING")),
                WHEN,700,1,opportunity_audit=audit)
        self.assertEqual(result,[])
        self.assertEqual(audit["eligible_quote_symbols"],0)
        self.assertEqual(audit["no_new_entry_reason"],"NO_ELIGIBLE_REAL_PUBLIC_QUOTES")

    def test_symbol_slot_capacity_rejection_is_recorded_without_new_trades(self):
        audit={}
        with patch.object(engine,"SYMBOLS",("BTC",)), patch.object(engine,"MAX_PER_SYMBOL",0):
            result=engine.new_candidates({},lambda s,p:quote(),WHEN,700,1,
                                         opportunity_audit=audit)
        self.assertEqual(result,[])
        self.assertEqual(audit["eligible_quote_symbols"],1)
        self.assertEqual(audit["screened_symbol_slots"],0)
        self.assertEqual(audit["no_new_entry_reason"],
                         "ALL_AVAILABLE_SYMBOL_SLOTS_OCCUPIED_OR_CAPPED")

    def test_no_remaining_capacity_does_not_invent_observations(self):
        audit={}
        with patch.object(engine,"MAX_NEW_PER_RUN",0):
            result=engine.new_candidates({},lambda s,p:quote(),WHEN,900,10,
                                         opportunity_audit=audit)
        self.assertEqual(result,[])
        self.assertEqual(audit["screened_symbol_slots"],0)
        self.assertEqual(audit["confirmed_arm_opportunities"],{})
        self.assertEqual(audit["requested_new_slots"],10)
        self.assertEqual(audit["no_new_entry_reason"],"REQUEST_OR_PER_RUN_BUDGET_ZERO")


if __name__=="__main__":
    unittest.main()
