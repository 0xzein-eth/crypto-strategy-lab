"""Offline tests: no future bar use, authentic data manifests, parity."""
import copy
import datetime as dt
import unittest
import v2.data_contract as dc
import v2.signal_parity as parity
from research_v9.history import BAR_MS

UTC = dt.timezone.utc
START = int(dt.datetime(2026,10,17,tzinfo=UTC).timestamp()*1000)


def candles(n=90):
    data=[]
    for i in range(n):
        px=100 + i*.02
        data.append([START+i*BAR_MS,px,px+.2,px-.2,px+.05,2000+i])
    return data


def clock_at(bars):
    return dt.datetime.fromtimestamp((bars[-1][0]+BAR_MS+30_000)/1000,UTC)


def snap(when):
    return {"provider":"okx-swap","market_type":"perpetual",
            "symbol":"BTC","instrument":"BTC-USDT-SWAP",
            "observed_at":when.isoformat().replace("+00:00","Z"),
            "pct24h":2.0}


class SourceParityTests(unittest.TestCase):
    def test_good_manifest_and_explicit_incomplete_funding(self):
        c=candles()
        m=dc.manifest("BTC",c)
        self.assertEqual(m["price_bar_count"],90)
        self.assertEqual(m["continuous_price_window_days"],.9375)
        self.assertTrue(m["contiguous_verified_15m"])
        self.assertFalse(m["one_calendar_year_verified"])
        self.assertFalse(m["funding_completeness_proved"])
        self.assertEqual(m["funding_status"],"UNKNOWN_NOT_PROVIDED")
        self.assertEqual(m["historical_observed_bid_ask"],False)
        self.assertEqual(m["price_dataset_hash_sha256"],dc.digest(c))
        changed=copy.deepcopy(c); changed[0][4]+=.01
        self.assertNotEqual(dc.manifest("BTC",changed)["price_dataset_hash_sha256"],
                            m["price_dataset_hash_sha256"])
        with self.assertRaisesRegex(ValueError,"DATA_INVALID"):
            dc.manifest("BTC",c[:20]+c[21:])
        with self.assertRaisesRegex(ValueError,"DATA_INVALID"):
            dc.manifest("BTC",c[:10]+[c[9]]+c[10:])
        self.assertEqual(dc.manifest("BTC",c,funding=[])["funding_status"],
                         "NO_SETTLED_FUNDING_EVENTS")

    def test_inventory_advertises_missing_not_fake(self):
        rows=candles()
        report=dc.inventory(
            ("BTC","ETH"),price_loader=lambda symbol: rows if symbol=="BTC" else [],
            funding_loader=lambda symbol: [])
        self.assertEqual(report["verified_markets"],1)
        self.assertIn("ETH", report["markets_unavailable_or_invalid"])
        self.assertFalse(report["common_prices_1y_ready"])
        self.assertTrue(report["no_historical_gapfill"])

    def test_asof_parity_and_exclude_future_confirmed_bar(self):
        c=candles(100)
        moment=clock_at(c[:80])
        look=parity.verify_pair(c[:80],moment,snap(moment),"BTC")
        forward=parity.verify_pair(c,moment,snap(moment),"BTC")
        self.assertEqual(look["frozen_signal_hash_sha256"],
                         forward["frozen_signal_hash_sha256"])
        self.assertTrue(forward["historical_signal_equals_online_adapter"])
        self.assertFalse(forward["historical_v9_trade_execution_verified"])
        # Even a poisonous FUTURE confirmed OHLCV cannot alter as-of rules.
        poisoned=copy.deepcopy(c)
        poisoned[-1][4]=poisoned[-1][2]=9_000_000
        self.assertEqual(
            parity.verify_pair(poisoned,moment,snap(moment),"BTC")[
                "frozen_signal_hash_sha256"],look["frozen_signal_hash_sha256"])
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            parity.bar_view(c,moment.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            parity.bar_view(c[:40],clock_at(c[:40]))

    def test_realism_delta_is_explicitly_not_a_fill(self):
        candles_end=dt.datetime(2026,10,19,8,0,tzinfo=UTC)
        quote_at=candles_end+dt.timedelta(seconds=37)
        q=parity.proposed_entry_drift(candles_end,100,100.25,quote_at,"LONG")
        self.assertEqual(q["entry_drift_pct_signed"],.25)
        self.assertFalse(q["a_real_executed_fill"])
        self.assertEqual(q["time_lag_seconds"],37)
        short=parity.proposed_entry_drift(candles_end,100,100.25,quote_at,"SHORT")
        self.assertEqual(short["entry_drift_pct_signed"],-.25)
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            parity.proposed_entry_drift(candles_end,100,101,
                                        candles_end-dt.timedelta(seconds=2),"LONG")

if __name__=="__main__":
    unittest.main()
