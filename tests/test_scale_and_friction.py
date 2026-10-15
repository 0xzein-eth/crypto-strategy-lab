"""Capacity, sampling and hypothetical-friction regression checks (offline)."""
import datetime as dt
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import engine
import friction
import learner
import universe

UTC=dt.timezone.utc

class ScaleAndCostTests(unittest.TestCase):
    def setUp(self):
        self.t=dt.datetime(2026,10,8,6,0,tzinfo=UTC)
        self.quotes={}
        for i,symbol in enumerate(engine.SYMBOLS):
            self.quotes[symbol]={
                "symbol":symbol,"price":100+i,"pct24h":1.0+i*.025 if i%2 else -1.0-i*.025,
                "quote_volume_24h":50_000_000,"observed_at":engine.stamp(self.t),
                "provider":"okx-swap","market_type":"perpetual",
                "instrument":symbol+"-USDT-SWAP",
                "spread_pct_observed":.015 if i%3==0 else .035,
            }

    def read(self,symbol,provider=None):
        return self.quotes[symbol]

    def test_quality_first_budget_scales_only_with_real_schedule_coverage(self):
        def coverage(p):
            return {"recent_observed_intervals":72,
                    "estimated_10m_slot_coverage":p}
        self.assertEqual(engine.prospective_entry_budget(30,coverage(.31)),(5,"severe_scheduler_coverage"))
        self.assertEqual(engine.prospective_entry_budget(30,coverage(.66)),(12,"degraded_scheduler_coverage"))
        self.assertEqual(engine.prospective_entry_budget(30,coverage(.83)),(20,"recovering_scheduler_coverage"))
        self.assertEqual(engine.prospective_entry_budget(36,coverage(.96)),(36,"healthy_scheduler_coverage"))
        self.assertEqual(engine.prospective_entry_budget(30,coverage(.96),recovery=True)[0],3)
        self.assertEqual(engine.prospective_entry_budget(30,
                         {"recent_observed_intervals":3}), (30,"collect_scheduler_baseline"))

    def test_many_markets_and_stratified_capacity(self):
        self.assertGreaterEqual(len(engine.SYMBOLS),35)
        self.assertEqual(set(engine.SYMBOLS),set(universe.ASSET_SECTORS))
        out=engine.new_candidates({},self.read,self.t,116,24,clock=lambda:self.t)
        self.assertEqual(len(out),24)
        self.assertEqual(len({r["symbol"] for r in out}),24)
        increased=engine.new_candidates({},self.read,self.t,116,36,
                                        clock=lambda:self.t)
        self.assertEqual(len(increased),36)
        self.assertEqual(len({r["symbol"] for r in increased}),36)
        self.assertTrue(all(r["evidence"]["performance_neutral_allocation"] for r in increased))
        self.assertGreaterEqual(len({r["evidence"]["sampling_stratum"][0] for r in out}),4)
        self.assertGreaterEqual(len({r["horizon_hours"] for r in out}),5)
        self.assertTrue(all(r["friction_stress"]["version"]==friction.VERSION for r in out))
        self.assertTrue(all(r["evidence"]["sampling_rule"].endswith("roundrobin-15m") for r in out))

    def test_sparse_strata_preferred_only_by_frozen_entry_counts(self):
        data=[dict(self.quotes[s]) for s in ("BTC","ETH","DOGE","LINK")]
        slot=int(self.t.timestamp()//900)
        major=universe.bucket("BTC",data[0]["pct24h"],
                              data[0]["quote_volume_24h"])
        meme=universe.bucket("DOGE",data[2]["pct24h"],
                             data[2]["quote_volume_24h"])
        self.assertNotEqual(major,meme)
        prior={major:20,meme:0}
        first=engine.diversified_quotes(data,slot,prior)
        second=engine.diversified_quotes(data,slot,prior)
        self.assertEqual(first,second)
        self.assertNotEqual(
            universe.bucket(first[0]["symbol"],first[0]["pct24h"],
                            first[0]["quote_volume_24h"]),major)
        self.assertEqual({q["symbol"] for q in first},
                         {q["symbol"] for q in data})

    def test_horizon_quality_band_changes_only_future_experiments(self):
        all_h=engine.new_candidates({},self.read,self.t,116,24,clock=lambda:self.t)
        degraded_h=engine.new_candidates({},self.read,self.t,116,24,
                                          clock=lambda:self.t,horizons=(4,8,12,24))
        self.assertEqual(len(degraded_h),24)
        self.assertTrue({r["horizon_hours"] for r in degraded_h}.issubset({4,8,12,24}))
        self.assertTrue(all(r["evidence"]["eligible_horizons_at_selection"]==[4,8,12,24]
                            for r in degraded_h))
        self.assertTrue(any(r["horizon_hours"] in (1,2) for r in all_h))
        self.assertEqual({r["symbol"] for r in all_h},
                         {r["symbol"] for r in degraded_h})
        for rec in degraded_h:
            engine.validate_open(rec)
        with self.assertRaisesRegex(ValueError,"invalid allowed"):
            engine.new_candidates({},self.read,self.t,116,2,horizons=(8,8))

    def test_frozen_15m_symbol_slots_prevent_correlated_repeat_entries(self):
        # Scheduler observations occur every ten minutes, but the research
        # candle/signal is 15 minutes. Do not multiply nearly identical
        # independent trade hypotheses in the same decision slot.
        first=engine.new_candidates({},self.read,self.t,116,24,
                                    clock=lambda:self.t)
        existing={r["id"]:r for r in first}
        now10=self.t+dt.timedelta(minutes=10)
        def fresh10(symbol,provider=None):
            return dict(self.quotes[symbol],observed_at=engine.stamp(now10))
        again=engine.new_candidates(existing,fresh10,now10,140,24,
                                    clock=lambda:now10)
        first_symbols={r["symbol"] for r in first}
        self.assertTrue(all(r["symbol"] not in first_symbols for r in again))
        self.assertTrue(all(r["evidence"]["signal_slot_utc"] ==
                            engine.stamp(self.t) for r in first+again))
        self.assertTrue(all("one_open_per_symbol_per_15m" in
                            r["evidence"]["independent_symbol_slot_policy"]
                            for r in first+again))
        # Once the predeclared 15-minute slot rolls over, new prospective
        # observations can sample the same assets again.
        future=self.t+dt.timedelta(minutes=20)
        def fresh20(symbol,provider=None):
            return dict(self.quotes[symbol],observed_at=engine.stamp(future))
        reopened=engine.new_candidates(existing,fresh20,future,140,24,
                                       clock=lambda:future)
        self.assertGreater(len(reopened),0)
        self.assertTrue(any(r["symbol"] in first_symbols for r in reopened))
        for r in first+again+reopened:
            engine.validate_open(r)

    def test_closed_positions_cannot_bypass_same_slot_guard(self):
        first=engine.new_candidates({},self.read,self.t,116,24,
                                    clock=lambda:self.t)
        historical={r["id"]:dict(r,status="CLOSED") for r in first}
        later=self.t+dt.timedelta(minutes=10)
        def fresh(symbol,provider=None):
            return dict(self.quotes[symbol],observed_at=engine.stamp(later))
        second=engine.new_candidates(historical,fresh,later,140,24,
                                     clock=lambda:later)
        self.assertFalse({r["symbol"] for r in first} &
                         {r["symbol"] for r in second})

    def test_daily_budget_blocks_after_prior_trades_even_if_closed(self):
        records={}
        for i in range(engine.MAX_NEW_PER_UTC_DAY):
            records["HIST-"+str(i)]={"symbol":"BTC","created_at":engine.stamp(self.t),
                                    "status":"CLOSED"}
        self.assertEqual(engine.new_candidates(records,self.read,self.t,3000,24),[])

    def test_new_friction_is_frozen_and_audited(self):
        original=engine.new_candidates({},self.read,self.t,116,1,clock=lambda:self.t)[0]
        self.assertIsNotNone(original["friction_stress"]["source_spread_pct"])
        self.assertGreater(original["friction_stress"]["assumed_round_trip_extra_pct"],0)
        due=engine.parse(original["evaluate_at"])
        exit_quote=dict(self.quotes[original["symbol"]],price=original["entry_price"]*.99,
                        observed_at=engine.stamp(due+dt.timedelta(minutes=1)))
        outputs,_,missing=engine.close_due(
            {original["id"]:original},lambda s,p:exit_quote,
            due+dt.timedelta(minutes=1))
        self.assertEqual(missing,0)
        closed=outputs[0]
        self.assertLess(closed["stress_net_pnl_usd"],closed["net_pnl_usd"])
        engine.validate_close(original,closed)
        broken=dict(closed,stress_normalized_R=closed["stress_normalized_R"]+1)
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            engine.validate_close(original,broken)

    def test_existing_monthly_event_can_close_in_new_daily_shard(self):
        original=engine.new_candidates({},self.read,self.t,116,1,clock=lambda:self.t)[0]
        due=engine.parse(original["evaluate_at"])
        later=dict(self.quotes[original["symbol"]],price=original["entry_price"]*1.01,
                   observed_at=engine.stamp(due+dt.timedelta(minutes=2)))
        closed=engine.close_due({original["id"]:original},lambda s,p:later,
                                due+dt.timedelta(minutes=2))[0][0]
        with tempfile.TemporaryDirectory() as name:
            base=Path(name)
            folder=base/"data"/"events"
            folder.mkdir(parents=True)
            historical=engine.seal(1,engine.PREV_ZERO,"OPEN",original)
            (folder/"2026-10.jsonl").write_text(engine.canonical(historical)+"\n")
            with patch.object(engine,"EVENTS",folder):
                seq,tip=engine.append_events([("CLOSE",closed)],1,historical["hash"],due)
            self.assertEqual(seq,2)
            self.assertEqual(tip,engine.replay(base)[2])
            self.assertEqual(engine.replay(base)[0][original["id"]]["status"],"CLOSED")
            self.assertTrue((folder/"2026-10.jsonl").exists())
            self.assertTrue(list(folder.glob("2026-10_daily_*.jsonl")))

    def test_spread_validation_and_scenario(self):
        self.assertIsNone(friction.observed_spread_pct(101,100))
        self.assertIsNone(friction.observed_spread_pct(None,100))
        self.assertAlmostEqual(friction.observed_spread_pct(99,101),2.0)
        m=friction.estimate_extra_round_trip_pct("BTC",-2,200_000_000,.02)
        self.assertEqual(m["spread_basis"],"observed_entry")
        x=friction.scenario(1,10000,1.5,m["assumed_round_trip_extra_pct"])
        self.assertLess(x["stress_net_pnl_usd"],90)
        self.assertAlmostEqual(x["stress_extra_cost_usd"],
            100*m["assumed_round_trip_extra_pct"],places=4)

    def test_learner_stress_metric_preferred_to_optimistic_base(self):
        r={"strategy":"BR-v3","created_at":"2026-10-08T03:00:00Z",
           "status":"CLOSED","market_type":"perpetual",
           "late_excluded":False,"normalized_R":1.0,"stress_normalized_R":-0.1,
           "horizon_hours":2,"research_risk_pct":1.5}
        self.assertEqual(learner.research_R(r),-.1)
        older=dict(r)
        del older["stress_normalized_R"]
        self.assertLess(learner.research_R(older),older["normalized_R"])

if __name__=="__main__":
    unittest.main()
