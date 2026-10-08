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



class ExtendedHistoryTests(unittest.TestCase):
    def test_reverse_older_paging_must_touch_cache(self):
        data = market(400)
        older, existing = data[:100], data[100:300]
        out = history.extend_older(existing, older)
        self.assertEqual(out, data[:300])
        with self.assertRaisesRegex(ValueError, "gap"):
            history.extend_older(existing, data[:98])
        changed = [r.copy() for r in older + existing[:1]]
        changed[-1][4] += 1
        with self.assertRaisesRegex(ValueError, "conflicting"):
            history.extend_older(existing, changed)

    def test_refresh_expands_oldest_history_and_preserves_newest(self):
        from urllib.parse import parse_qs, urlsplit
        data = market(340)
        def payload(url):
            query = parse_qs(urlsplit(url).query)
            if "after" in query:
                cursor = int(query["after"][0])
                selected = [r for r in data if r[0] < cursor][-100:]
            else:
                selected = data[-100:]
            return {"code": "0", "data": [
                [str(row[0]), *(str(x) for x in row[1:]), "0", "0", "1"]
                for row in reversed(selected)]}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(history, "CACHE_DIR", Path(folder)):
                history.save_cache("BTC", data[100:300])
                now = dt.datetime.fromtimestamp(data[-1][0]/1000+900,
                                                 dt.timezone.utc)
                updated = history.refresh_symbol("BTC", update_pages=1,
                               backfill_pages=1, max_bars=500,
                               now=now, getter=payload, sleeper=lambda _: None)
                self.assertEqual(updated, data)
                self.assertEqual(history.load_cache("BTC"), data)


class FundingAndRiskTests(unittest.TestCase):
    @staticmethod
    def events(n=1500):
        return [[BASE_TS+i*32*history.BAR_MS, 0.0001*((-1)**i)]
                for i in range(n//32+2)]

    def test_funding_only_realized_settled(self):
        from research_v9 import funding
        payload = {"code": "0", "data": [
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP",
             "fundingTime": str(BASE_TS+32*history.BAR_MS),
             "fundingRate": "0.05", "realizedRate": "0.0002"},
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP",
             "fundingTime": str(BASE_TS+64*history.BAR_MS),
             "fundingRate": "0.0002", "realizedRate": ""}
        ]}
        now = dt.datetime.fromtimestamp((BASE_TS+120*history.BAR_MS)/1000,
                                         dt.timezone.utc)
        parsed = funding.parse_settled(payload, "BTC", now)
        self.assertEqual(parsed, [[BASE_TS+32*history.BAR_MS, 0.0002]])
        payment = funding.payment_pct(parsed, 1, BASE_TS,
                                      BASE_TS+32*history.BAR_MS)
        self.assertAlmostEqual(payment, 0.02)
        self.assertAlmostEqual(funding.payment_pct(parsed, -1, BASE_TS,
                                  BASE_TS+32*history.BAR_MS), -0.02)
        bad = {"code":"0", "data":[dict(payload["data"][0], instId="ETH-USDT-SWAP")]}
        with self.assertRaisesRegex(ValueError, "different contract"):
            funding.parse_settled(bad, "BTC", now)

    def test_funding_coverage_rejects_missing_periods(self):
        from research_v9 import funding
        bars = market(800)
        events = self.events(800)
        self.assertTrue(funding.coverage(events, bars[0][0], bars[-1][0]))
        missing = events[:4] + events[5:]
        self.assertFalse(funding.coverage(missing, bars[0][0], bars[-1][0]))
        self.assertFalse(funding.coverage([], bars[0][0], bars[-1][0]))

    def test_funded_results_separate_from_base_pnl(self):
        funded = self.events(800)
        v = factory.Variant("long_control", 0, 0.0, 0, 32)
        a = factory.backtest(market(800), v, funding_events=None)
        b = factory.backtest(market(800), v, funding_events=funded)
        self.assertEqual([x["net_pct"] for x in a],
                         [x["net_pct"] for x in b])
        self.assertTrue(all(x["funding_adjusted_net_pct"] is not None for x in b))
        self.assertIsNone(factory.statistics_for(a)["funding_adjusted_avg_R"])
        self.assertIsNotNone(factory.statistics_for(b)["funding_adjusted_avg_R"])

    def test_intrabar_proxy_not_real_liquidation(self):
        rows = market(400)
        v = factory.Variant("long_control", 0, 0.0, 0, 8)
        baseline = factory.backtest(rows, v)
        self.assertFalse(baseline[0]["barrier_touch_proxy"])
        rows[67][3] = rows[67][1] * 0.60
        flagged = factory.backtest(rows, v)
        self.assertTrue(flagged[0]["barrier_touch_proxy"])
        self.assertEqual(flagged[0]["barrier_adverse_move_pct"], 32.833333)
        self.assertEqual(flagged[0]["net_pct"], baseline[0]["net_pct"])

    def test_funding_cache_offline_research_provenance(self):
        from research_v9 import funding
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            with patch.object(history, "CACHE_DIR", folder/"candles"), patch.object(
                    funding, "CACHE_DIR", folder/"rates"), patch.object(
                    cli, "RESULT_PATH", folder/"report.json"), patch.object(
                    cli, "QUEUE_PATH", folder/"candidates.json"):
                for sym, base in (("BTC", 100), ("ETH", 210)):
                    history.save_cache(sym, market(1000, base=base))
                    funding.save_cache(sym, self.events(1000))
                report = cli.produce(["BTC", "ETH"], offline=True, max_variants=15)
                self.assertEqual(set(report["measured_funding_symbols"]),
                                 {"BTC", "ETH"})
                self.assertTrue((folder/"candidates.json").exists())
                self.assertFalse(report["v8_event_ledger_modified"])
                self.assertFalse(json.loads((folder/"candidates.json").read_text())
                                 ["paper_v8_auto_activation"])


class ReviewGateTests(unittest.TestCase):
    def test_missing_funding_never_promotes(self):
        from research_v9.promotion import build_queue
        report = {
            "historical_only": True, "proven_edge": False, "symbols_analyzed": ["BTC"],
            "measured_funding_symbols": [], "funding_fetch_failures": {},
            "walk_forward_selected": [{
                "variant_id": "momentum-L4-T0p008-S0-H96",
                "folds_selected": 3,
                "walk_forward": {
                    "n": 100, "days": 20, "day_lcb_R": 0.3,
                    "funding_adjusted_avg_R": None, "barrier_touches": 0}}],
            "folds": []}
        r = build_queue(report)
        self.assertFalse(r["settled_funding_fully_covered"])
        self.assertEqual(r["eligible_for_forward_code_review"], [])
        self.assertFalse(r["live_trading_enabled"])

if __name__ == "__main__":
    unittest.main()
