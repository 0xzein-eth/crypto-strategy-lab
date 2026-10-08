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

    def test_many_markets_and_stratified_capacity(self):
        self.assertGreaterEqual(len(engine.SYMBOLS),35)
        self.assertEqual(set(engine.SYMBOLS),set(universe.ASSET_SECTORS))
        out=engine.new_candidates({},self.read,self.t,116,24,clock=lambda:self.t)
        self.assertEqual(len(out),24)
        self.assertEqual(len({r["symbol"] for r in out}),24)
        self.assertGreaterEqual(len({r["evidence"]["sampling_stratum"][0] for r in out}),4)
        self.assertGreaterEqual(len({r["horizon_hours"] for r in out}),5)
        self.assertTrue(all(r["friction_stress"]["version"]==friction.VERSION for r in out))
        self.assertTrue(all(r["evidence"]["sampling_rule"].endswith("roundrobin-15m") for r in out))

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
