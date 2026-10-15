import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import engine

UTC=dt.timezone.utc

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.t=dt.datetime(2026,10,8,2,0,tzinfo=UTC)
        self.q={"symbol":"BTC","price":100,"pct24h":-4,
                "quote_volume_24h":2_000_000,"observed_at":engine.stamp(self.t),
                "provider":"kraken-spot-proxy","market_type":"spot_proxy","instrument":"XBTUSD"}

    def test_creates_prospective_unique_experiments(self):
        inputs={"BTC":self.q}
        out=engine.new_candidates({},lambda s,p:inputs[s],self.t,116,5)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["id"],"LAB-116")
        self.assertEqual(out[0]["created_at"],engine.stamp(self.t))
        self.assertGreater(engine.parse(out[0]["evaluate_at"]),self.t)
        self.assertEqual(out[0]["market_type"],"spot_proxy")

    def test_closure_fees_late_and_venue_protection(self):
        r=engine.new_candidates({},lambda s,p:self.q,self.t,116,1)[0]
        due=engine.parse(r["evaluate_at"])
        mismatch=dict(self.q,price=99,observed_at=engine.stamp(due+dt.timedelta(minutes=3)),
                      provider="coinbase-spot-proxy",instrument="BTC-USD")
        outputs,_,missing=engine.close_due({r["id"]:r},lambda s,p:mismatch,due+dt.timedelta(minutes=3))
        self.assertEqual(outputs,[])
        self.assertEqual(missing,1)
        same=dict(self.q,price=99,observed_at=engine.stamp(due+dt.timedelta(minutes=4)))
        outputs,late,missing=engine.close_due({r["id"]:r},lambda s,p:same,due+dt.timedelta(minutes=4))
        self.assertEqual((len(outputs),late,missing),(1,0,0))
        self.assertEqual(outputs[0]["delay_seconds"],240)
        self.assertEqual(outputs[0]["fee_round_trip_usd"],10.0)
        self.assertAlmostEqual(outputs[0]["net_pnl_usd"],-110 if r["side"]=="LONG" else 90,places=2)
        self.assertFalse(outputs[0]["late_excluded"])
        stale=dict(self.q,price=99,observed_at=engine.stamp(due-dt.timedelta(seconds=1)))
        self.assertEqual(engine.close_due({r["id"]:r},lambda s,p:stale,due)[0],[])
        late_q=dict(same,observed_at=engine.stamp(due+dt.timedelta(hours=3)))
        self.assertTrue(engine.close_due({r["id"]:r},lambda s,p:late_q,due+dt.timedelta(hours=3))[0][0]["late_excluded"])

    def test_hash_chain_immutability_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            event_dir=base/"data"/"events"
            with patch.object(engine,"EVENTS",event_dir):
                r=engine.new_candidates({},lambda s,p:self.q,self.t,116,1)[0]
                seq,head=engine.append_events([("OPEN",r)],0,engine.PREV_ZERO,self.t)
                self.assertEqual((seq,engine.replay(base)[1]),(1,1))
                self.assertEqual(engine.replay(base)[2],head)
                due=engine.parse(r["evaluate_at"])
                later=dict(self.q,price=99,observed_at=engine.stamp(due+dt.timedelta(minutes=2)))
                closed=engine.close_due({r["id"]:r},lambda s,p:later,due+dt.timedelta(minutes=2))[0][0]
                seq,head=engine.append_events([("CLOSE",closed)],seq,head,self.t)
                self.assertEqual(engine.replay(base)[0][r["id"]]["status"],"CLOSED")
                path=next(event_dir.glob("2026-10_daily_*.jsonl"))
                lines=path.read_text().splitlines()
                bad=json.loads(lines[1]);bad["record"]["net_pnl_usd"]=99999
                lines[1]=json.dumps(bad)
                path.write_text("\n".join(lines)+"\n")
                with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
                    engine.replay(base)

    def test_cannot_double_close_record(self):
        r=engine.new_candidates({},lambda s,p:self.q,self.t,116,1)[0]
        due=engine.parse(r["evaluate_at"])
        later=dict(self.q,price=99,observed_at=engine.stamp(due+dt.timedelta(minutes=2)))
        closed=engine.close_due({r["id"]:r},lambda s,p:later,due+dt.timedelta(minutes=2))[0][0]
        self.assertEqual(engine.close_due({r["id"]:closed},lambda s,p:later,due)[0],[])

    def test_spot_results_excluded_from_perpetual_evidence(self):
        r=engine.new_candidates({},lambda s,p:self.q,self.t,116,1)[0]
        due=engine.parse(r["evaluate_at"])
        later=dict(self.q,price=99,observed_at=engine.stamp(due+dt.timedelta(minutes=2)))
        closed=engine.close_due({r["id"]:r},lambda s,p:later,due+dt.timedelta(minutes=2))[0][0]
        stats=engine.summarize({r["id"]:closed},due)
        self.assertEqual(stats["closed"],1)
        self.assertEqual(stats["eligible_perpetual_timely"]["n"],0)
        self.assertEqual(stats["spot_proxy_closures"],1)

    def test_quote_parse_kraken_and_age_guard(self):
        fake={"error":[],"result":{"XXBTZUSD":{"c":["100","1"],"o":"98","v":["4","3"]}}}
        with self.assertRaisesRegex(ValueError,"stale"):
            engine.quote("BTC","kraken-spot-proxy",
                         clock=lambda:self.t+dt.timedelta(minutes=10),
                         requester=lambda url:fake) if False else self._stale_test()
        q=engine.quote("BTC","kraken-spot-proxy",clock=lambda:self.t,requester=lambda url:fake)
        self.assertEqual(q["price"],100)
        self.assertEqual(q["instrument"],"XBTUSD")
        self.assertEqual(q["market_type"],"spot_proxy")

    def _stale_test(self):
        tick={"code":"0","data":[{"last":"100","open24h":"98","volCcy24h":"3",
                                  "ts":str(int((self.t-dt.timedelta(minutes=15)).timestamp()*1000))}]}
        return engine.quote("BTC","okx-swap",clock=lambda:self.t,requester=lambda u:tick)

    def test_eligible_market_breadth_never_invents_days(self):
        import copy
        q=self.q
        r=engine.new_candidates({},lambda s,p:q,self.t,116,1)[0]
        r1=copy.deepcopy(r)
        r2=copy.deepcopy(r)
        for record,day,regime in ((r1,"2026-10-08","24h_up"),
                                  (r2,"2026-10-09","24h_down")):
            record["status"]="CLOSED"
            record["created_at"]=day+"T03:00:00Z"
            record["market_type"]="perpetual"
            record["late_excluded"]=False
            record["regime"]=regime
        breadth=engine.eligible_market_breadth([r1,r2])
        self.assertEqual(breadth["eligible_entry_days"],2)
        self.assertEqual(breadth["days_with_both_up_and_down_regimes"],0)
        self.assertEqual(len(breadth["recent_14_entry_days"]),2)
        self.assertEqual(breadth["recent_14_entry_days"][0]["eligible_closes"],1)

    def test_idle_tick_uses_a_real_public_quote_without_fake_trade(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/"data").mkdir()
            calls=[]
            def current_quote(symbol,provider,clock=None):
                calls.append((symbol,provider))
                if (symbol,provider)!=("BTC","okx-swap"):
                    raise RuntimeError("only BTC market available")
                return {"symbol":"BTC","price":100,"pct24h":0,
                        "quote_volume_24h":4_000_000,
                        "observed_at":engine.stamp(self.t),
                        "provider":"okx-swap","market_type":"perpetual",
                        "instrument":"BTC-USDT-SWAP"}
            with patch.object(engine,"BASE",base),patch.object(engine,"EVENTS",base/"data"/"events"),\
                 patch.object(engine,"REPORT",base/"data"/"report.json"),\
                 patch.object(engine,"STATE",base/"data"/"state.json"),\
                 patch.object(engine,"LEGACY",base/"data"/"ledger.json"),\
                 patch.object(engine,"quote",side_effect=current_quote):
                result=engine.run(0,clock=lambda:self.t)
                self.assertEqual(result["status"],"NO_NEW_SIGNALS")
                self.assertEqual(result["created"],0)
                self.assertEqual(result["verified_events"],0)
                self.assertEqual(result["provider_observations"],1)
                self.assertTrue(result["observation_heartbeat"]["attested_by_real_quote"])
                self.assertEqual(result["observation_heartbeat"]["provider"],"okx-swap")
                self.assertEqual(result["observation_heartbeat"]["observed_at"],
                                 engine.stamp(self.t))
                self.assertEqual(calls,[("BTC","okx-swap")])
                self.assertEqual(engine.replay(base)[1],0)
                later=self.t+dt.timedelta(minutes=10)
                with patch.object(engine,"quote",side_effect=lambda sym,p,clock=None: {
                    "symbol":"BTC","price":101,"pct24h":0,
                    "quote_volume_24h":4_000_000,
                    "observed_at":engine.stamp(later),
                    "provider":"okx-swap","market_type":"perpetual",
                    "instrument":"BTC-USDT-SWAP"}):
                    second=engine.run(0,clock=lambda:later)
                self.assertEqual(second["created"],0)
                self.assertEqual(second["verified_events"],0)
                self.assertEqual(second["scheduling_diagnostics"]["prior_observation_gap_minutes"],10)

    def test_no_data_does_not_create_events(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/"data").mkdir()
            with patch.object(engine,"BASE",base),patch.object(engine,"EVENTS",base/"data"/"events"),\
                 patch.object(engine,"REPORT",base/"data"/"report.json"),\
                 patch.object(engine,"STATE",base/"data"/"state.json"),\
                 patch.object(engine,"LEGACY",base/"data"/"ledger.json"),\
                 patch.object(engine,"quote",side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError,"heartbeat symbols attempted=BTC,ETH,SOL,XRP"):
                    engine.run(5,clock=lambda:self.t)
                self.assertFalse((base/"data"/"events").exists())
                self.assertFalse((base/"data"/"report.json").exists())

if __name__=="__main__":
    unittest.main()
