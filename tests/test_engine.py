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
        self.assertAlmostEqual(abs(outputs[0]["net_pnl_usd"]),110,places=2)
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
                path=event_dir/"2026-10.jsonl"
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

    def test_no_data_does_not_create_events(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/"data").mkdir()
            with patch.object(engine,"BASE",base),patch.object(engine,"EVENTS",base/"data"/"events"),\
                 patch.object(engine,"REPORT",base/"data"/"report.json"),\
                 patch.object(engine,"STATE",base/"data"/"state.json"),\
                 patch.object(engine,"LEGACY",base/"data"/"ledger.json"),\
                 patch.object(engine,"quote",side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError,"DATA_UNAVAILABLE"):
                    engine.run(5,clock=lambda:self.t)
                self.assertFalse((base/"data"/"events").exists())
                self.assertFalse((base/"data"/"report.json").exists())

if __name__=="__main__":
    unittest.main()
