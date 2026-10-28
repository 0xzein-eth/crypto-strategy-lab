"""PAPER-only research quality policy, independently reproducible offline."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

import engine
import entry_sampling
import learner


UTC=dt.timezone.utc
BASE=dt.datetime(2026,10,19,6,0,tzinfo=UTC)


def quote(moment, symbol="BTC"):
    return {
        "symbol":symbol,"price":101.0,"pct24h":2.0,
        "quote_volume_24h":10_000_000,
        "observed_at":engine.stamp(moment),
        "provider":"okx-swap","market_type":"perpetual",
        "instrument":symbol+"-USDT-SWAP"}


def record(arm, date, value):
    return {"id":arm+date+str(value), "strategy":arm,
            "created_at":date+"T06:00:00Z",
            "status":"CLOSED","market_type":"perpetual",
            "normalized_R":value,"horizon_hours":4,"late_excluded":False}


class ProxyQualityGateTests(unittest.TestCase):
    def test_no_confirmed_signal_most_slots_are_not_wasted_on_proxies(self):
        seen=[]
        decisions=[]
        for i in range(300):
            now=BASE+dt.timedelta(minutes=15*i)
            slot=int(now.timestamp()//engine.SIGNAL_SLOT_SECONDS)
            expected=entry_sampling.no_confirmed_baseline_probe("BTC",slot)
            audit={}
            def authentic(symbol,provider):
                return quote(now,symbol)
            with patch.object(engine,"SYMBOLS",("BTC",)):
                opened=engine.new_candidates(
                    {},authentic,now,116,1,
                    advanced=lambda symbol,ticker:[],
                    reobserve=authentic,clock=lambda:now,
                    opportunity_audit=audit)
            seen.append(bool(opened))
            decisions.append(expected)
            self.assertEqual(bool(opened),expected)
            self.assertEqual(audit["screened_symbol_slots"],1)
            self.assertEqual(audit["slots_with_any_confirmed_signal"],0)
            self.assertEqual(audit["slots_with_no_confirmed_signal"],1)
            self.assertEqual(audit["confirmed_arm_opportunities"],{})
            self.assertEqual(audit["no_confirmed_signal_baseline_probes_allowed"],
                             int(expected))
            self.assertEqual(len(audit["symbol_decisions"]), 1)
            self.assertEqual(audit["symbol_decisions"][0]["decision"],
                             "PAPER_OPEN_CREATED" if expected else "NO_SIGNAL_NOT_SAMPLED")
            self.assertEqual(audit["no_confirmed_signal_proxy_slots_skipped"],
                             int(not expected))
            if opened:
                self.assertEqual(len(opened),1)
                self.assertIn(opened[0]["strategy"],learner.BASELINES)
                self.assertTrue(opened[0]["evidence"]["performance_neutral_allocation"])
                engine.validate_open(opened[0])
            else:
                self.assertEqual(audit["no_new_entry_reason"],
                                 "NO_CONFIRMED_SIGNAL_AND_SPARSE_PROBES_GATED")
        self.assertEqual(seen,decisions)
        self.assertGreater(sum(seen),40)
        self.assertLess(sum(seen),80)

    def test_real_confirmed_candidates_remain_available_at_every_fresh_slot(self):
        def make_advanced(symbol,market):
            when=engine.parse(market["observed_at"])-dt.timedelta(minutes=15)
            return [{"strategy":"IBREAK-v1","side":"LONG",
                     "evidence":{"bar_time":engine.stamp(when),
                                 "bar_span":"15m confirmed OKX USDT-SWAP"}}]
        for i in range(75):
            moment=BASE+dt.timedelta(minutes=15*i)
            def read(symbol,provider):
                return quote(moment,symbol)
            audit={}
            with patch.object(engine,"SYMBOLS",("BTC",)):
                opened=engine.new_candidates(
                    {},read,moment,500,1,
                    advanced=make_advanced,reobserve=read,clock=lambda:moment,
                    opportunity_audit=audit)
            self.assertEqual(len(opened),1)
            self.assertEqual(audit["no_confirmed_signal_proxy_slots_skipped"],0)
            self.assertEqual(audit["confirmed_arm_opportunities"]["IBREAK-v1"],1)
            self.assertEqual(audit["slots_with_any_confirmed_signal"],1)
            self.assertEqual(opened[0]["evidence"]["sampling_rule"],
                             "sector-direction-volatility-roundrobin-15m")
            engine.validate_open(opened[0])

    def test_probe_fails_closed_on_invalid_policy_and_is_outcome_blind(self):
        with self.assertRaises(ValueError):
            entry_sampling.no_confirmed_baseline_probe("BTC",10,-1)
        with self.assertRaises(ValueError):
            entry_sampling.no_confirmed_baseline_probe("BTC",10,True)
        with self.assertRaises(ValueError):
            entry_sampling.no_confirmed_baseline_probe("",10)
        with self.assertRaises(ValueError):
            entry_sampling.no_confirmed_baseline_probe("BTC",True)
        slot=int(BASE.timestamp()//900)
        a=entry_sampling.no_confirmed_baseline_probe("BTC",slot)
        self.assertEqual(a,entry_sampling.no_confirmed_baseline_probe("BTC",slot))
        self.assertTrue(entry_sampling.no_confirmed_baseline_probe("BTC",slot,100))
        self.assertFalse(entry_sampling.no_confirmed_baseline_probe("BTC",slot,0))

    def test_train_only_persistent_losses_have_bounded_deweight_and_ctrl(self):
        dates=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat()
               for i in range(70)]
        rows=[]
        for day in dates:
            for j in range(3):
                rows.append(record("BR-v3",day,-2.0))
                rows.append(record("CTRL-v1",day,0.0))
        profile=learner.analysis(rows)
        self.assertIn("BR-v3",profile["training_only_underperformers"])
        controlled={
            "entry_exposure_counts_v1":{"BR-v3":10,"IBREAK-v1":10},
            "train_negative_arms_v1":profile["training_only_underperformers"],
            "training_negative_policy_version":"day-cluster-training-only-v1",
        }
        neutral=dict(controlled,train_negative_arms_v1=[])
        options=[{"strategy":"CTRL-v1","side":"LONG"},
                 {"strategy":"BR-v3","side":"LONG"},
                 {"strategy":"IBREAK-v1","side":"LONG"}]
        with_guard=[learner.choose(options,rows,"BTC",4,k,0,controlled)
                    for k in range(3000)]
        without_guard=[learner.choose(options,rows,"BTC",4,k,0,neutral)
                       for k in range(3000)]
        guarded_bad=sum(a["strategy"]=="BR-v3" for a,_ in with_guard)
        neutral_bad=sum(a["strategy"]=="BR-v3" for a,_ in without_guard)
        self.assertLess(guarded_bad,neutral_bad-100)
        self.assertGreater(guarded_bad,0)
        self.assertEqual(sum(a["strategy"]=="CTRL-v1" for a,_ in with_guard),
                         sum(a["strategy"]=="CTRL-v1" for a,_ in without_guard))
        self.assertGreater(sum(m=="confirmed_signal_training_negative_downweighted"
                               for _,m in with_guard),400)
        # Changing ONLY monitoring outcomes must not shift a single future choice.
        fake=copy.deepcopy(rows)
        for row in fake:
            if learner.stable_bucket("holdout:"+learner.day_of(row),5)==0:
                row["normalized_R"]=30.0
        changed=learner.analysis(fake)
        self.assertEqual(profile["training_only_underperformers"],
                         changed["training_only_underperformers"])
        still=dict(controlled,train_negative_arms_v1=changed["training_only_underperformers"])
        self.assertEqual(with_guard,
                         [learner.choose(options,fake,"BTC",4,k,0,still)
                          for k in range(3000)])

    def test_three_days_even_many_losses_never_trigger_policy(self):
        days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat()
              for i in range(3)]
        rows=[]
        for day in days:
            for _ in range(100):
                rows.append(record("BR-v3",day,-5))
                rows.append(record("CTRL-v1",day,0))
        profile=learner.analysis(rows)
        self.assertNotIn("BR-v3",profile["training_only_underperformers"])

    def test_missing_signal_legacy_offline_and_spot_proxies_are_untouched(self):
        # Legacy offline tests and spot-only observations are still available
        # for auditing but never enter eligible perpetual strategy evidence.
        with patch.object(engine,"SYMBOLS",("BTC",)):
            legacy=engine.new_candidates({},lambda s,p:quote(BASE,s),
                                         BASE,116,1,clock=lambda:BASE)
        self.assertEqual(len(legacy),1)


if __name__=="__main__":
    unittest.main()
