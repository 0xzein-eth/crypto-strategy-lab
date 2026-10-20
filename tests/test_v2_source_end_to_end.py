"""Whole-source no-network smoke test: contract metadata + real wire schemas.

This catches source-path integration failures CI unit mocks of one_book
alone cannot catch. No market data are invented for production; every
number here is an explicitly synthetic test fixture.
"""
import datetime as dt
from urllib.parse import urlparse,parse_qs
import unittest

from v2 import forward_paper as f
from v2 import okx_observer_source as okx
from v2 import shadow_research as shadow

UTC=dt.timezone.utc
NOW=dt.datetime(2026,10,20,3,7,18,tzinfo=UTC)


def fixture(url):
    parsed=urlparse(url)
    if parsed.scheme!="https" or parsed.netloc!="www.okx.com":
        raise AssertionError("no private or cross-origin source allowed")
    params=parse_qs(parsed.query)
    instrument=params.get("instId",[""])[0]
    symbol=instrument.removesuffix("-USDT-SWAP")
    if symbol not in f.SYMBOLS or instrument != symbol+"-USDT-SWAP":
        raise AssertionError("unexpected requested instrument "+instrument)
    if parsed.path.endswith("/public/instruments"):
        return {"code":"0","data":[{
            "instId":instrument,"instType":"SWAP","state":"live",
            "ctType":"linear","ctValCcy":symbol,"settleCcy":"USDT",
            "ctVal":"0.01"}]}
    if parsed.path.endswith("/market/books"):
        t=int((NOW-dt.timedelta(seconds=5)).timestamp()*1000)
        return {"code":"0","data":[{
            "ts":str(t),"bids":[["100","5000","0","0"]],
            "asks":[["100.05","5000","0","0"]]}]}
    if parsed.path.endswith("/market/ticker"):
        t=int((NOW-dt.timedelta(seconds=3)).timestamp()*1000)
        return {"code":"0","data":[{
            "instId":instrument,"ts":str(t),
            "last":"100.02","open24h":"99.8"}]}
    if parsed.path.endswith("/market/candles"):
        start=NOW.replace(minute=0,second=0,microsecond=0)-dt.timedelta(minutes=15)
        candles=[]
        for ix in range(120):
            when=start-dt.timedelta(minutes=15*ix)
            close=100+0.005*(120-ix)
            price=close-.01
            candles.append([
                str(int(when.timestamp()*1000)),str(price),
                str(close+.09),str(price-.08),str(close),
                str(120+ix%8),"0","0","1"])
        # The newest candle is forming and MUST NOT be a source signal.
        forming=NOW.replace(minute=0,second=0,microsecond=0)
        candles.insert(0,[str(int(forming.timestamp()*1000)),
                          "100","100.1","99.9","100.0","999","0","0","0"])
        return {"code":"0","data":candles}
    raise AssertionError("unrecognized source route "+url)


class CompletePaperSourceIntegration(unittest.TestCase):
    def test_three_instruments_real_schema_asof_confirmed_and_replay(self):
        observed=okx.current_tick(clock=lambda:NOW,getter=fixture)
        self.assertEqual(observed["version"],f.VERSION)
        self.assertEqual(set(observed["books"]),set(f.SYMBOLS))
        self.assertEqual(set(observed["signals"]),set(f.SYMBOLS))
        self.assertEqual(observed["observed_at"],f.iso(NOW))
        self.assertFalse(observed["funding_settlement_history_verified"])
        for sym in f.SYMBOLS:
            book=observed["books"][sym]
            self.assertEqual(book["provider"],"okx-swap")
            self.assertTrue(book["instrument_metadata_verified"])
            self.assertEqual(book["bid_size_base"],"50.00")
            self.assertLessEqual(len(observed["signals"][sym]),64)
            for candidate in observed["signals"][sym]:
                self.assertIn(candidate["strategy"],shadow.ARMS)
                self.assertLessEqual(f.ts(candidate["evidence"]["bar_time"])+
                                     dt.timedelta(minutes=15), NOW)
        report,curve=f.replay([f.seal(observed,1,f.HASH_ZERO)])
        research=shadow.assess([f.seal(observed,1,f.HASH_ZERO)])
        self.assertEqual(report["observations"],1)
        self.assertEqual(len(curve),1)
        self.assertEqual(research["source_observation_events"],1)
        self.assertEqual(report["real_order_submissions"],0)
        self.assertFalse(report["after_all_costs_performance_proven"])

    def test_source_unavailable_never_creates_replay_observation(self):
        def broken(url):
            if "/market/books?" in url and "ETH-USDT-SWAP" in url:
                return {"code":"0","data":[]}
            return fixture(url)
        with self.assertRaisesRegex(ValueError,"SOURCE_UNAVAILABLE"):
            okx.current_tick(clock=lambda:NOW,getter=broken)

    def test_exchange_timestamp_not_wall_clock_bar_open(self):
        future=NOW+dt.timedelta(minutes=16)
        def bad_tick(url):
            if "/market/ticker?" in url and "SOL-USDT-SWAP" in url:
                invalid=fixture(url)
                invalid["data"][0]["ts"]=str(int(future.timestamp()*1000))
                return invalid
            return fixture(url)
        with self.assertRaisesRegex(ValueError,"SOURCE_STALE"):
            okx.current_tick(clock=lambda:NOW,getter=bad_tick)


if __name__=="__main__":
    unittest.main()
