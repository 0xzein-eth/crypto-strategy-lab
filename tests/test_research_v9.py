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

    def test_expanded_preregistered_catalog_reaches_four_hundred(self):
        entries = factory.variant_catalog(400)
        self.assertEqual(len(entries), 400)
        self.assertEqual(len({v.id for v in entries}), 400)
        self.assertIn(48, {v.horizon for v in entries})
        self.assertTrue(any(v.family == "trend" and v.lookback == 6
                            for v in entries))
        self.assertTrue(any(v.family == "momentum" and v.lookback == 24
                            for v in entries))
        self.assertTrue(any(v.family == "rsi_revert" and v.threshold == 40
                            for v in entries))

    def test_extended_catalog_supports_five_hundred_variants(self):
        items = factory.variant_catalog(500)
        self.assertEqual(len(items), 500)
        self.assertEqual(len({x.id for x in items}), 500)
        self.assertTrue(any(x.family == "momentum" and x.lookback == 48 for x in items))
        self.assertTrue(any(x.family == "mean_revert" and x.threshold == 2.8 for x in items))

    def test_seven_hundred_fifty_historical_variants_and_frozen_old_prefix(self):
        baseline = factory.variant_catalog(500)
        expanded = factory.variant_catalog(750)
        self.assertEqual(len(expanded),750)
        self.assertEqual([x.id for x in baseline],
                         [x.id for x in expanded[:500]])
        self.assertEqual(len({x.id for x in expanded}),750)
        for family in ("donchian","ztrend","rsi_trend"):
            self.assertIn(family,{x.family for x in expanded})
        with self.assertRaises(ValueError):
            factory.variant_catalog(2001)

    def test_twelve_hundred_variants_preserve_all_previous_750_ids(self):
        old = factory.variant_catalog(750)
        extended = factory.variant_catalog(1200)
        self.assertEqual(len(extended), 1200)
        self.assertEqual([v.id for v in old], [v.id for v in extended[:750]])
        self.assertEqual(len({v.id for v in extended}), 1200)
        self.assertTrue({"compression_breakout", "volatility_impulse",
                         "trend_reclaim"} <= {v.family for v in extended})
        with self.assertRaises(ValueError):
            factory.variant_catalog(2001)

    def test_one_thousand_six_hundred_preserves_every_old_id(self):
        original=factory.variant_catalog(1200)
        larger=factory.variant_catalog(1600)
        self.assertEqual([x.id for x in original],[x.id for x in larger[:1200]])
        self.assertEqual(len({x.id for x in larger}),1600)
        self.assertTrue({"volume_climax_fade","rsi_recovery"} <=
                        {x.family for x in larger})
        with self.assertRaises(ValueError):
            factory.variant_catalog(2001)

    def test_twenty_four_hundred_hypotheses_keep_two_thousand_prefix(self):
        old=factory.variant_catalog(2000)
        larger=factory.variant_catalog(2400)
        self.assertEqual(len(larger),2400)
        self.assertEqual(len(set(v.id for v in larger)),2400)
        self.assertEqual([v.id for v in old],
                         [v.id for v in larger[:2000]])
        families=[v.family for v in larger[2000:]]
        expected={"range_failure_revert","momentum_acceleration",
                  "volume_followthrough","pullback_channel"}
        self.assertEqual(set(families),expected)
        self.assertEqual({x:families.count(x) for x in expected},
                         {x:100 for x in expected})
        self.assertEqual({v.horizon for v in larger[2000:]},
                         set(factory.HORIZONS))
        with self.assertRaises(ValueError):
            factory.variant_catalog(2401)

    def test_four_new_signals_use_only_confirmed_trailing_bars(self):
        candles=market(400)
        base=factory.Features(candles)
        mutated=[r[:] for r in candles]
        mutated[-1][4]*=1.2
        mutated[-1][2]=max(mutated[-1][2],mutated[-1][4])
        from_future=factory.Features(mutated)
        for v in factory.variant_catalog(2400)[2000::13]:
            first=factory.signal(base,v,250)
            second=factory.signal(from_future,v,250)
            self.assertIn(first,(-1,0,1))
            self.assertEqual(first,second,v.id)

    def test_two_thousand_distinct_diverse_variants_preserve_all_1600_ids(self):
        old=factory.variant_catalog(1600)
        enlarged=factory.variant_catalog(2000)
        self.assertEqual(len(enlarged),2000)
        self.assertEqual(len({v.id for v in enlarged}),2000)
        self.assertEqual([v.id for v in old],[v.id for v in enlarged[:1600]])
        families=[v.family for v in enlarged[1600:]]
        self.assertEqual(set(families),
                         {"inside_bar_release","band_reentry",
                          "vwap_trend_reclaim","efficient_trend"})
        self.assertEqual({name:families.count(name) for name in set(families)},
                         {name:100 for name in set(families)})
        self.assertEqual(set(v.horizon for v in enlarged[1600:]),
                         set(factory.HORIZONS))
        with self.assertRaises(ValueError):
            factory.variant_catalog(2001)

    def test_training_only_selection_covers_families_before_correlated_parameters(self):
        variants={
            "a1":factory.Variant("trend",8,0.01,50,4),
            "a2":factory.Variant("trend",12,0.01,50,4),
            "a3":factory.Variant("trend",20,0.01,50,4),
            "b1":factory.Variant("band_reentry",20,1.8,0,4),
            "c1":factory.Variant("efficient_trend",6,0.82,50,4),
            "d1":factory.Variant("vwap_trend_reclaim",20,1.0,50,4)}
        training_sorted=["a1","a2","a3","b1","c1","d1"]
        selected=factory.family_diverse_top(training_sorted,variants,4)
        self.assertEqual(selected,["a1","b1","c1","d1"])
        self.assertEqual(factory.family_diverse_top(training_sorted[:3],variants,4),
                         ["a1","a2","a3"])
        self.assertEqual(factory.family_diverse_top(training_sorted,variants,2),
                         ["a1","b1"])
        with self.assertRaises(ValueError):
            factory.family_diverse_top(training_sorted,variants,0)
        with self.assertRaises(ValueError):
            factory.family_diverse_top(training_sorted,variants,True)

    def test_new_four_v9_signals_use_only_current_or_earlier_confirmed_bars(self):
        j=350
        variants=[
            factory.Variant("inside_bar_release",20,1.15,50,4),
            factory.Variant("band_reentry",20,1.8,0,8),
            factory.Variant("vwap_trend_reclaim",20,1.0,50,16),
            factory.Variant("efficient_trend",6,0.82,50,32)]
        for variant in variants:
            rows=market(600, slope=.035 if variant.family!="band_reentry" else .005)
            if variant.family=="inside_bar_release":
                m=rows[j-2][4]
                rows[j-2][1:5]=[m,m+2,m-2,m]
                rows[j-1][1:5]=[m,m+1,m-1,m]
                rows[j][1:5]=[m,m+3.5,m-.5,m+3]
                rows[j][5]=2400
            elif variant.family=="band_reentry":
                rows[j-1][4]-=7
                rows[j-1][3]=min(rows[j-1][3],rows[j-1][4]-.25)
                rows[j][5]=1500
            elif variant.family=="vwap_trend_reclaim":
                rows[j-1][4]-=3
                rows[j-1][3]=min(rows[j-1][3],rows[j-1][4]-.2)
                rows[j][4]+=2
                rows[j][2]=max(rows[j][2],rows[j][4]+.2)
                rows[j][5]=2500
            elif variant.family=="efficient_trend":
                base=rows[j-7][4]
                for k in range(j-6,j+1):
                    p=base+(k-(j-7))*0.8
                    rows[k][1:5]=[p-.4,p+.3,p-.7,p]
                    rows[k][5]=1500
            f=factory.Features(rows)
            observed=factory.signal(f,variant,j)
            self.assertEqual(observed,1,variant.family)
            # Bars created/altered in the future must not change the
            # historical signal that would actually have been available.
            future=[r.copy() for r in rows]
            future[j+15][4]+=20
            future[j+15][2]=max(future[j+15][2],future[j+15][4]+1)
            self.assertEqual(factory.signal(factory.Features(future),variant,j),
                             observed,variant.family)
            # Missing / invalid future-source proof cannot become a fill.
            self.assertTrue(all(r["entry_ts"]<r["exit_ts"]
                                for r in factory.backtest(rows,variant)))

    def test_volume_fade_and_rsi_recovery_never_look_ahead(self):
        original=market(400)
        changed=[x.copy() for x in original]
        changed[350][4] *= 1.2
        changed[350][2] = max(changed[350][2],changed[350][4]+1)
        for family,window,gate in (("volume_climax_fade",20,1.5),
                                    ("rsi_recovery",14,30)):
            v=factory.Variant(family,window,gate,0,4)
            self.assertEqual(factory.signal(factory.Features(original),v,300),
                             factory.signal(factory.Features(changed),v,300))
            self.assertTrue(all(t["entry_ts"]<t["exit_ts"]
                                for t in factory.backtest(original,v)))

    def test_bounded_memory_historical_trade_accounting(self):
        result=factory.walk_forward(
            {"BTC":market(1100),"ETH":market(1100,base=220,slope=-.02)},
            max_variants=24)
        self.assertEqual(result["memory_policy"],
                         "aggregate_training_then_recompute_only_selected_validation")
        self.assertGreater(result["hypothetical_historical_trades_tested"],0)
        self.assertEqual(result["hypothetical_historical_trades_tested"],
                         sum(result["hypothetical_trades_by_family"].values()))
        self.assertEqual(result["hypothetical_historical_trades_tested"],
                         sum(result["hypothetical_trades_by_symbol"].values()))
        self.assertFalse(result["proven_edge"])

    def test_added_signal_families_have_no_future_leakage(self):
        original = market(400)
        later = [row.copy() for row in original]
        later[350][4] *= 1.2
        later[350][2] = max(later[350][2], later[350][4]+1)
        for family,lookback,threshold,second in (
            ("compression_breakout",20,0.8,0),
            ("volatility_impulse",12,0.75,0),
            ("trend_reclaim",16,0.2,50),
        ):
            v = factory.Variant(family,lookback,threshold,second,4)
            self.assertEqual(factory.signal(factory.Features(original),v,300),
                             factory.signal(factory.Features(later),v,300))
            self.assertTrue(all(t["exit_ts"]>t["entry_ts"] for t in
                                factory.backtest(original,v)))

    def test_new_families_use_only_confirmed_trailing_bars(self):
        original=market(400)
        future=[bar.copy() for bar in original]
        future[310][4]*=1.5
        future[310][2]=max(future[310][2],future[310][4]+1)
        for family,lookback,gate in (
            ("donchian",20,1.1),("ztrend",20,0.6),
            ("rsi_trend",14,60)):
            with self.subTest(family=family):
                v=factory.Variant(family,lookback,gate,0,4)
                self.assertEqual(
                    factory.signal(factory.Features(original),v,300),
                    factory.signal(factory.Features(future),v,300))
                events=factory.backtest(original,v)
                self.assertTrue(all(e["exit_ts"]>e["entry_ts"]
                                    for e in events))
                self.assertTrue(all(e["settled_funding_paid_pct"] is None
                                    for e in events))

    def test_day_cluster_stress_and_funding_sensitivity(self):
        sample = factory.backtest(market(1100),
                 factory.Variant("long_control", 0, 0.0, 0, 4))
        stats = factory.statistics_for(sample)
        diff = 0.25 / factory.R_DENOMINATOR_PCT
        self.assertGreaterEqual(stats["days"], 4)
        self.assertAlmostEqual(stats["extra_25bps_after_cost_avg_R"],
                               stats["avg_R"]-diff, delta=0.000003)
        self.assertAlmostEqual(stats["extra_25bps_day_cluster_lcb_R"],
                               stats["day_lcb_R"]-diff, delta=0.000003)
        self.assertIsNone(stats["funding_plus_extra_25bps_avg_R"])
        with_funding = [dict(x, funding_adjusted_R=x["net_R"]+0.02)
                        for x in sample]
        funded = factory.statistics_for(with_funding)
        self.assertAlmostEqual(funded["funding_plus_extra_25bps_avg_R"],
                               funded["funding_adjusted_avg_R"]-diff, delta=0.000003)

    def test_no_future_leakage_in_signal(self):
        original = market(400)
        modified = [r.copy() for r in original]
        modified[350][4] *= 1.2
        modified[350][2] = max(modified[350][2], modified[350][4]+1)
        v = factory.Variant("momentum", 8, 0.002, 0, 4)
        self.assertEqual(factory.signal(factory.Features(original), v, 300),
                         factory.signal(factory.Features(modified), v, 300))

    def test_rejected_shadow_diagnostics_never_promote_or_relabel_validation(self):
        from research_v9.promotion import build_queue
        import copy
        datasets={"BTC":market(1200),"ETH":market(1200,base=220,slope=-.02)}
        result=factory.walk_forward(datasets,max_variants=70)
        self.assertEqual(result["candidates_evaluated"],70)
        shadow_ids={x["variant_id"] for fold in result["folds"]
                    for x in fold["shadow_evaluations"]}
        self.assertTrue(shadow_ids)
        selected_ids={x["variant_id"] for x in result["walk_forward_selected"]}
        self.assertFalse(shadow_ids & selected_ids)
        self.assertFalse(result["proven_edge"])
        queue_input=dict(result,
                         symbols_analyzed=["BTC","ETH"],
                         measured_funding_symbols=[],
                         generated_at_utc="2026-10-15T00:00:00Z")
        queue=build_queue(queue_input)
        self.assertFalse(queue["eligible_for_forward_code_review"])
        self.assertFalse(queue["paper_v8_auto_activation"])
        self.assertFalse(queue["live_trading_enabled"])

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
        for fold in result["folds"]:
            self.assertIn("training_screen_rejection_counts",fold)
            self.assertIn("highest_scoring_unqualified_training_only",fold)
            self.assertIn("shadow_evaluations",fold)
            self.assertIn("train_selected_family_diversity",fold)
            self.assertLessEqual(fold["train_selected_family_diversity"],4)
            self.assertLessEqual(len(fold["shadow_evaluations"]),4)
            self.assertEqual(len({p["family"] for p in fold["shadow_evaluations"]}),
                             len(fold["shadow_evaluations"]))
            self.assertTrue(all(
                shadow["status"]=="SHADOW_EXPLORATORY_ONLY"
                and shadow["eligible_for_promotion"] is False
                and shadow["variant_id"] not in {
                    x["variant_id"] for x in fold["selected_for_validation"]}
                and shadow["shadow_validation"]["n"] >= 0
                for shadow in fold["shadow_evaluations"]))
            self.assertTrue(all(
                c["training_day_cluster_lcb_R"] is None or
                c["training_day_cluster_lcb_R"]<=0
                for c in fold["highest_scoring_unqualified_training_only"]))
            self.assertTrue(all(
                not any(c["variant_id"]==s["variant_id"] for s in
                        fold["selected_for_validation"])
                for c in fold["highest_scoring_unqualified_training_only"]))
        previous = None
        for fold in result["folds"]:
            val_start = fold["validation_start_utc"]
            if previous:
                self.assertGreaterEqual(val_start, previous)
            previous = fold["validation_end_exclusive_utc"]


class ResearchWindowTests(unittest.TestCase):
    def test_trailing_window_preserves_raw_cache_and_never_zero_fills(self):
        from research_v9 import funding
        bars = market(11000)
        raw = {"BTC":bars, "ETH":market(11000,base=220)}
        clipped=cli.trim_research_window(raw,window_days=90)
        self.assertEqual(len(clipped["BTC"]),8640)
        self.assertEqual(len(raw["BTC"]),11000)
        self.assertEqual(clipped["ETH"][0][0],clipped["BTC"][0][0])
        funding_events=[[bars[i][0],0.0001] for i in range(15*96,11000,32)]
        self.assertFalse(funding.coverage(funding_events,bars[0][0],
                                          bars[-1][0]+history.BAR_MS))
        self.assertTrue(funding.coverage(funding_events,clipped["BTC"][0][0],
                                         clipped["BTC"][-1][0]+history.BAR_MS))
        with self.assertRaises(ValueError):
            cli.trim_research_window(raw,window_days=5)

    def test_too_short_window_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"DATA_INSUFFICIENT"):
            cli.trim_research_window({"BTC":market(400),"ETH":market(400)},90)


class CliTests(unittest.TestCase):
    def test_offline_research_does_not_touch_paper_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root/"latest.json"
            with patch.object(history, "CACHE_DIR", root/"cache"):
                history.save_cache("BTC", market(1000))
                history.save_cache("ETH", market(1000, base=200))
                with patch.object(cli, "RESULT_PATH", destination), patch.object(
                        cli, "QUEUE_PATH", root/"candidates.json"):
                    report = cli.produce(["BTC", "ETH"], offline=True,
                                         max_variants=15)
            self.assertTrue(destination.exists())
            self.assertEqual(report["forward_paper_trades_created"], 0)
            self.assertFalse(report["proven_edge"])
            self.assertEqual(report["symbols_analyzed"], ["BTC", "ETH"])
            self.assertAlmostEqual(report["historical_overlap_days"], 1000/96, delta=0.01)
            self.assertFalse(report["ninety_day_overlap_reached"])
            self.assertEqual(report["historical_cache_cap_bars_per_instrument"], 18000)
            self.assertEqual(json.loads(destination.read_text())["schema_version"], 1)
            self.assertFalse((root/"data"/"ledger.json").exists())

    def test_failure_does_not_publish_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root/"latest.json"
            with patch.object(history, "CACHE_DIR", root/"cache"):
                with patch.object(cli, "RESULT_PATH", destination), patch.object(
                        cli, "QUEUE_PATH", root/"candidates.json"):
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
        changed[-1][5] += 1
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

    def test_funding_refresh_extends_target_window_without_refetching_all_history(self):
        from research_v9 import funding
        from urllib.parse import parse_qs, urlsplit
        rows = [[BASE_TS+i*3600_000, 0.0001] for i in range(400)]
        calls = []
        def getter(url):
            query = parse_qs(urlsplit(url).query)
            cursor = int(query["after"][0]) if "after" in query else None
            calls.append(cursor)
            batch = [r for r in rows if cursor is None or r[0] < cursor][-100:]
            return {"code": "0", "data": [
                {"instId": "BTC-USDT-SWAP", "fundingTime": str(t),
                 "realizedRate": str(rate)} for t, rate in reversed(batch)]}
        now = dt.datetime.fromtimestamp(rows[-1][0]/1000+1, dt.timezone.utc)
        with tempfile.TemporaryDirectory() as folder, patch.object(
                funding, "CACHE_DIR", Path(folder)):
            funding.save_cache("BTC", rows[200:390])
            updated = funding.refresh_symbol("BTC", pages=5, now=now,
                getter=getter, sleeper=lambda _: None,
                first_bar_ms=rows[50][0], backfill_pages=2)
            self.assertEqual(updated, rows)
            self.assertEqual(calls, [None, rows[200][0], rows[100][0]])
            calls.clear()
            funding.refresh_symbol("BTC", pages=5, now=now,
                getter=getter, sleeper=lambda _: None,
                first_bar_ms=rows[50][0], backfill_pages=2)
            self.assertEqual(calls, [None])

    def test_funding_refresh_rejects_revised_cached_settlement(self):
        from research_v9 import funding
        with tempfile.TemporaryDirectory() as folder, patch.object(
                funding, "CACHE_DIR", Path(folder)):
            funding.save_cache("BTC", [[BASE_TS, 0.0001]])
            payload = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP",
                "fundingTime": str(BASE_TS), "realizedRate": "0.0002"}]}
            with self.assertRaisesRegex(ValueError, "settlement changed"):
                funding.refresh_symbol("BTC", getter=lambda _: payload,
                    sleeper=lambda _: None)
            self.assertEqual(funding.load_cache("BTC"), [[BASE_TS, 0.0001]])

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
