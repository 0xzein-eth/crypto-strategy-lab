import copy
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import lab

class LabTests(unittest.TestCase):
    def setUp(self):
        self.t=dt.datetime(2026,10,8,2,0,tzinfo=dt.timezone.utc)
        self.snap={"price":100.0,"change24h_pct":-3.0,"quote_volume_24h":100000000,
                   "provider":"fixture-perpetual","observed_at":lab.stamp(self.t),"instrument":"BTCUSDT perpetual"}
    def test_open_and_close_after_due(self):
        d={"schema_version":7,"next_id":116,"records":[]}
        self.assertEqual(lab.create_new(d,{"BTC":self.snap},self.t,5),1)
        r=d["records"][0]
        self.assertEqual(r["status"],"OPEN")
        self.assertEqual(lab.close_due(d,{"BTC":self.snap},self.t)[0],0)
        due=lab.parse(r["evaluate_at"])
        q=dict(self.snap,price=99.0,observed_at=lab.stamp(due+dt.timedelta(minutes=3)))
        self.assertEqual(lab.close_due(d,{"BTC":q},due+dt.timedelta(minutes=3))[0],1)
        self.assertEqual(r["delay_seconds"],180)
        self.assertAlmostEqual(r["net_pnl_usd"],90,places=5)
        before=copy.deepcopy(r)
        lab.close_due(d,{"BTC":dict(q,price=88)},due+dt.timedelta(hours=2))
        self.assertEqual(r,before)
    def test_missing_price_pending_then_recovery(self):
        d={"schema_version":7,"next_id":116,"records":[]}
        lab.create_new(d,{"BTC":self.snap},self.t,1)
        due=lab.parse(d["records"][0]["evaluate_at"])
        lab.close_due(d,{},due)
        self.assertEqual(d["records"][0]["status"],"DATA_MISSING_PENDING")
        lab.close_due(d,{"BTC":dict(self.snap,observed_at=lab.stamp(due+dt.timedelta(minutes=2)))},due+dt.timedelta(minutes=2))
        self.assertEqual(d["records"][0]["status"],"CLOSED")
    def test_capacity(self):
        d={"schema_version":7,"next_id":116,"records":[]}
        for i in range(80):
            d["records"].append({"id":f"LAB-{i+116}","status":"CLOSED"})
        self.assertEqual(lab.create_new(d,{"BTC":self.snap},self.t,5),0)
    def test_invalid_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as p:
            with patch.object(lab,"LEDGER",Path(p)/"missing.json"):
                with self.assertRaisesRegex(RuntimeError,"INTEGRITY_FAILURE"):lab.load()

if __name__=="__main__":unittest.main()
