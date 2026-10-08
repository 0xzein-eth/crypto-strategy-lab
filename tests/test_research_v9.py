"""Independent v9 regression suite; all tests deterministic/offline."""
import datetime as dt
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_v9
import research_v9.history as history
import research_v9.factory as factory
import run_research_v9 as cli

BASE_TS = 1_767_225_600_000  # 2026-01-01 00:00 UTC, aligned 15m


def market(n=1100, slope=0.035, base=100.0):
    out = []
    for i in range(n):
        cycle = math.sin(i/14)*0.55+math.cos(i/31)*0.37
        price = base + slope*i + cycle
        previous = base + slope*(i-1) + math.sin((i-1)/14)*0.55 + math.cos((i-1)/31)*0.37
        op = previous
        cl = price
        out.append([BASE_TS+i*history.BAR_MS, op, max(op, cl)+0.14,
                    min(op, cl)-0.14, cl, 1000.0+100*abs(math.sin(i/11))])
    return out


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def test_parse_confirmed_only_and_validate(self):
        now = dt.datetime(2026, 1, 1, 1, 0, tzinfo=dt.timezone.utc)
        payload = {"code": "0", "data": [
            [str(BASE_TS), "100", "101", "99", "100.5", "123", "0", "0", "1"],
            [str(BASE_TS+history.BAR_MS), "100.5", "101", "99", "100.9", "123", "0", "0", "0"],
            [str(BASE_TS+2*history.BAR_MS), "100.9", "102", "100", "101", "123", "0", "0", "1"],
        ]}
        rows = history.parse_confirmed(payload, now)
        self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, "nonsequential"):
            history.validate_series(rows)

    def test_merge_only_with_overlap(self):
        older = market(200)
        incoming = older[-20:] + market(220)[200:]
        self.assertEqual(len(history.merge_series(older, incoming)), 220)
        changed = [r.copy() for r in incoming]
        changed[0][5] += 5
        with self.assertRaisesRegex(ValueError, "revised"):
            history.merge_series(older, changed)
        with self.assertRaisesRegex(ValueError, "no overlap"):
            history.merge_series(older, market(240)[220:])

    def test_gapped_bars_rejected(self):
        rows = market(205)
        del rows[101]
        with self.assertRaisesRegex(ValueError, "nonsequential"):
            history.validate_series(rows)

    def test_cache_roundtrip_and_instrument_binding(self):
        with patch.object(history, "CACHE_DIR", self.cache):
            history.save_cache("BTC", market(250))
            self.assertEqual(history.load_cache("BTC"), market(250))
            with self.assertRaises(ValueError):
                history.load_cache("../ETH")

    def test_okx_pagination_uses_after_oldest(self):
        urls = []
        def stub(url):
            urls.append(url)
            return {"code": "0", "data": []}
        history.okx_page("BTC", after=BASE_TS, getter=stub, sleeper=lambda _: None)
        self.assertIn("after=", urls[0])
        self.assertIn("BTC-USDT-SWAP", urls[0])

    def test_invalid_candle_fails(self):
        now = dt.datetime(2026, 1, 1, 1, 0, tzinfo=dt.timezone.utc)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            history.parse_confirmed({"code": "0", "data": [
                [str(BASE_TS), "100", "99", "101", "100", "100", "0", "0", "1"]
            ]}, now)


class FactoryTests(unittest.TestCase):
    def test_catalog_is_reproducible_unique_and_bounded(self):
        first = factory.variant_catalog(260)
        self.assertEqual([v.id for v in first], [v.id for v in factory.variant_catalog(260)])
        self.assertEqual(len(first), len(set(v.id for v in first)))
        self.assertTrue(set(v.family for v in first) >= {
            "trend", "momentum", "mean_revert", "breakout", "rsi_revert",
            "control", "long_control"})

    def test_no_future_leakage_in_signal(self):
        original = market(400)
        modified = [r.copy() for r in original]
        modified[350][4] *= 1.2
        modified[350][2] = max(modified[350][2], modified[350][4]+1)
        v = factory.Variant("momentum", 8, 0.002, 0, 4)
        self.assertEqual(factory.signal(factory.Features(original), v, 300),
                         factory.signal(factory.Features(modified), v, 300))

    def test_fee_and_friction_never_improve_outcome(self):
        v = factory.Variant("long_control", 0, 0.0, 0, 4)
        base = factory.backtest(market(400), v, extra_cost_pct=0.0)
        costly = factory.backtest(market(400), v, extra_cost_pct=0.25)
        self.assertEqual(len(base), len(costly))
        self.assertTrue(all(a["net_R"] > b["net_R"] for a, b in zip(base, costly)))

    def test_next_bar_entry_and_exact_fixed_horizon(self):
        v = factory.Variant("long_control", 0, 0.0, 0, 8)
        trades = factory.backtest(market(400), v)
        self.assertTrue(trades)
        self.assertTrue(all(t["exit_ts"]-t["entry_ts"] ==
                            8*history.BAR_MS for t in trades))
        self.assertTrue(all(a["exit_ts"] <= b["entry_ts"]
                            for a, b in zip(trades, trades[1:])))

    def test_chronological_purged_validation_report(self):
        datasets = {"BTC": market(1100), "ETH": market(1100, base=220, slope=-0.02)}
        result = factory.walk_forward(datasets, max_variants=15)
        self.assertEqual(result["candidates_evaluated"], 15)
        self.assertEqual(len(result["folds"]), 3)
        self.assertFalse(result["proven_edge"])
        self.assertIsNone(result["champion"])
        self.assertEqual(result["folds"][0]["purge_bars"], 96)
        previous = None
        for fold in result["folds"]:
            val_start = fold["validation_start_utc"]
            if previous:
                self.assertGreaterEqual(val_start, previous)
            previous = fold["validation_end_exclusive_utc"]


class CliTests(unittest.TestCase):
    def test_offline_research_does_not_touch_paper_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root/"latest.json"
            with patch.object(history, "CACHE_DIR", root/"cache"):
                history.save_cache("BTC", market(1000))
                history.save_cache("ETH", market(1000, base=200))
                with patch.object(cli, "RESULT_PATH", destination):
                    report = cli.produce(["BTC", "ETH"], offline=True,
                                         max_variants=15)
            self.assertTrue(destination.exists())
            self.assertEqual(report["forward_paper_trades_created"], 0)
            self.assertFalse(report["proven_edge"])
            self.assertEqual(report["symbols_analyzed"], ["BTC", "ETH"])
            self.assertEqual(json.loads(destination.read_text())["schema_version"], 1)
            self.assertFalse((root/"data"/"ledger.json").exists())

    def test_failure_does_not_publish_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root/"latest.json"
            with patch.object(history, "CACHE_DIR", root/"cache"):
                with patch.object(cli, "RESULT_PATH", destination):
                    with self.assertRaisesRegex(RuntimeError, "DATA_UNAVAILABLE"):
                        cli.produce(["BTC", "ETH"], offline=True)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
