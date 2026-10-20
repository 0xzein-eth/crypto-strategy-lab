"""Offline tests: authentic-only, backward-bounded warehouse and funding gaps."""
import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from v2 import history_warehouse as hw
from research_v9.history import BAR_MS

UTC=dt.timezone.utc
NOW=dt.datetime(2026,10,20,3,7,tzinfo=UTC)
LAST=int((NOW.replace(minute=0,second=0,microsecond=0)-
          dt.timedelta(minutes=15)).timestamp()*1000)
ALL=[]
for i in range(550):
    candle_at=LAST-(549-i)*BAR_MS
    p=100+i*.02
    ALL.append([candle_at,p,p+.2,p-.2,p+.05,1000.0])


def price_page(symbol,after):
    if symbol not in hw.SYMBOLS:
        raise AssertionError("wrong symbol")
    dataset=ALL if after is None else [r for r in ALL if r[0]<after]
    return {"code":"0","data":[[str(x) for x in row]+["0","0","1"]
                               for row in reversed(dataset[-100:])]}


FUNDING=[]
for i in range(8):
    when=LAST-(7-i)*8*3600_000
    FUNDING.append([when, 0.0001])


def funding_page(symbol,after):
    rows=FUNDING if after is None else [r for r in FUNDING if r[0]<after]
    return {"code":"0","data":[{
        "instId":symbol+"-USDT-SWAP","instType":"SWAP",
        "fundingTime":str(event[0]),"realizedRate":str(event[1])}
        for event in reversed(rows[-100:])]}


class AuthenticWarehouseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(hw,"WAREHOUSE",Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_backfill_real_pages_from_existing_verified_history(self):
        report=hw.build(
            ("BTC",),now=NOW,target_days=30,
            price_page=price_page,funding_page=funding_page,
            price_seed=lambda sym:ALL[-200:],
            funding_seed=lambda sym:[],
            price_backfill_pages=6,funding_backfill_pages=6,
            sleeper=lambda sec:None)
        item=report["symbols"]["BTC"]
        self.assertEqual(item["confirmed_bars"],550)
        self.assertTrue(item["price_ingestion"]["legacy_verified_seed_used"])
        self.assertEqual(item["price_ingestion"]["older_confirmed_bars_added"],350)
        self.assertFalse(item["one_year_price_verified"])
        self.assertFalse(item["two_year_price_verified"])
        self.assertTrue(item["funding_missing_cannot_be_assumed_zero"])
        self.assertEqual(len(hw.load("BTC","candles")),550)
        self.assertEqual(hw.load("BTC","candles"),ALL)
        self.assertTrue(hw.path_for("BTC","settled_funding").exists())
        self.assertTrue((Path(self.temp.name)/"manifest.json").exists())
        rerun=hw.build(
            ("BTC",),now=NOW,target_days=30,
            price_page=price_page,funding_page=funding_page,
            price_seed=lambda sym:[],
            funding_seed=lambda sym:[],
            price_backfill_pages=6,funding_backfill_pages=6,
            sleeper=lambda sec:None)
        self.assertEqual(rerun["symbols"]["BTC"]["price_hash_sha256"],
                         item["price_hash_sha256"])
        self.assertEqual(rerun["symbols"]["BTC"]["confirmed_bars"],550)

    def test_immutable_hash_detects_historical_price_revision(self):
        hw.save("BTC","candles",ALL[-200:])
        path=hw.path_for("BTC","candles")
        item=json.loads(gzip.decompress(path.read_bytes()).decode())
        item["rows"][0][4]+=100
        path.write_bytes(gzip.compress(json.dumps(item).encode(),mtime=0))
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            hw.load("BTC","candles")

    def test_fake_hole_cannot_be_hidden_with_a_merged_cache(self):
        broken=ALL[-200:]
        broken=[*broken[:100],*broken[101:]]
        with self.assertRaisesRegex(ValueError,"DATA_INVALID"):
            hw.extend_prices("BTC",now=NOW,page=price_page,
                              seed=lambda sym:broken,sleeper=lambda x:None)
        with self.assertRaisesRegex(ValueError,"invalid exact market universe"):
            hw.build(("BTC","BTC"),now=NOW)

    def test_cold_start_from_only_actual_upstream_history(self):
        result=hw.build(("SOL",),now=NOW,target_days=30,
                        price_seed=lambda sym:[],
                        funding_seed=lambda sym:[],
                        price_page=price_page,funding_page=funding_page,
                        price_backfill_pages=6,funding_backfill_pages=2,
                        sleeper=lambda _:None)
        info=result["symbols"]["SOL"]
        self.assertEqual(info["confirmed_bars"],550)
        self.assertFalse(info["price_ingestion"]["legacy_verified_seed_used"])
        self.assertFalse(info["two_year_price_verified"])
        self.assertEqual(hw.load("SOL","candles"),ALL)

    def test_older_exchange_does_not_have_more_is_valid_data_limit(self):
        few=ALL[-150:]
        def limited(symbol,after):
            rows=few if after is None else [r for r in few if r[0]<after]
            return {"code":"0","data":[[str(x) for x in r]+["0","0","1"]
                                        for r in reversed(rows[-100:])]}
        candles,_=hw.extend_prices("BTC",now=NOW,target_days=365,
                                   page=limited,seed=lambda s:[],
                                   backfill_pages=10,sleeper=lambda _:None)
        self.assertEqual(len(candles),150)
        self.assertLess(len(candles),365*96)
        # Upstream limitations are disclosed, not turned into fake 1y data.

    def test_funding_failure_is_not_a_zero_cost(self):
        def refused(symbol,after):
            raise ValueError("DATA_UNAVAILABLE: funding provider unavailable")
        report=hw.build(("ETH",),now=NOW,target_days=30,
                        price_page=price_page,funding_page=refused,
                        price_seed=lambda sym:ALL[-200:],
                        funding_seed=lambda sym:[],
                        price_backfill_pages=6,sleeper=lambda _:None)
        item=report["symbols"]["ETH"]
        self.assertTrue(item["funding_fetch_failed"])
        self.assertTrue(item["funding_missing_cannot_be_assumed_zero"])
        self.assertEqual(item["funding_events"],0)
        self.assertFalse(item["settled_funding_full_price_window"])

    def test_incorrect_timestamp_and_tamper_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"DATA_INVALID"):
            hw.extend_prices("BTC",now=NOW.replace(tzinfo=None),
                             page=price_page,seed=lambda sym:[])
        with self.assertRaisesRegex(ValueError,"DATA_INVALID"):
            hw.extend_prices("BTC",now=NOW,target_days=10,
                             page=price_page,seed=lambda sym:[])
        with self.assertRaises(ValueError):
            hw.path_for("OTHER","candles")


if __name__=="__main__":
    unittest.main()
