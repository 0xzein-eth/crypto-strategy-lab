"""Regression: unvalidated legacy v8 entry safety is fail-closed in production.

Every quote is synthetic and used ONLY as an offline test fixture.
"""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine


UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 8, 2, 0, tzinfo=UTC)


class V8EntrySafetyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "data").mkdir()
        self.root = root
        self.now = START
        self.mockers = (
            patch.object(engine, "BASE", root),
            patch.object(engine, "EVENTS", root / "data" / "events"),
            patch.object(engine, "REPORT", root / "data" / "report.json"),
            patch.object(engine, "STATE", root / "data" / "state.json"),
            patch.object(engine, "SYMBOLS", ("BTC",)),
            patch.object(engine, "quote", side_effect=self.fake_quote),
        )
        for mocker in self.mockers:
            mocker.start()
            self.addCleanup(mocker.stop)

    def fake_quote(self, symbol, provider, clock=None):
        if provider != "kraken-spot-proxy":
            raise RuntimeError("synthetic mock: other providers unavailable")
        price = 100.0 if self.now == START else 102.0
        return {
            "symbol": symbol, "price": price, "pct24h": 2.0,
            "quote_volume_24h": 5_000_000,
            "observed_at": engine.stamp(self.now),
            "provider": "kraken-spot-proxy",
            "market_type": "spot_proxy", "instrument": "XBTUSD",
        }

    def execute(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return engine.run(1, clock=lambda: self.now, **kwargs)

    def test_default_is_active_high_volume_paper_research_not_auto_paused(self):
        report = self.execute()
        self.assertEqual(report["entry_mode"], "legacy-explore")
        self.assertEqual(report["added"], 1)
        self.assertTrue(report["entry_safety_policy"]["new_entries_permitted"])
        self.assertTrue(report["entry_safety_policy"]["research_only"])
        self.assertTrue(report["entry_safety_policy"]["no_live_trades_or_orders"])
        self.assertFalse(report["entry_safety_policy"]["not_a_funded_portfolio"] is False)

    def test_explicit_observe_only_abstains_and_attests_market(self):
        result = self.execute(entry_mode="observe-only")
        self.assertEqual(result["entry_mode"], "observe-only")
        self.assertEqual(result["status"], "OBSERVE_ONLY_NO_NEW_V8_ENTRIES")
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["closed"], 0)
        self.assertEqual(result["verified_events"], 0)
        self.assertGreater(result["provider_observations"], 0)
        self.assertEqual(result["entry_opportunity_audit"]["no_new_entry_reason"],
                         "UNVALIDATED_V8_EDGE_SAFETY_HOLD")
        self.assertEqual(result["entry_safety_policy"]["new_entries_after_safety_hold"], 0)
        self.assertEqual(result["economic_reconciliation"]["net_fee_only_pnl_usd"], 0)
        self.assertEqual(engine.replay(self.root)[1], 0)

    def test_legacy_opt_in_is_paper_only_and_prior_exits_remain_processed(self):
        first = self.execute(entry_mode="legacy-explore")
        self.assertEqual(first["created"], 1)
        self.assertEqual(first["entry_mode"], "legacy-explore")
        self.assertEqual(first["added"], 1)
        original, old_seq, old_hash, _ = engine.replay(self.root)
        self.assertEqual(len(original), 1)
        self.assertEqual(old_seq, 1)
        self.assertEqual(original[next(iter(original))]["status"], "OPEN")
        self.now += dt.timedelta(hours=25)
        second = self.execute(entry_mode="observe-only")
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["created"], 1)
        self.assertEqual(second["closed_this_run"], 1)
        self.assertEqual(second["closed"], 1)
        self.assertEqual(second["verified_events"], 2)
        self.assertEqual(second["entry_mode"], "observe-only")
        self.assertGreater(second["economic_reconciliation"]["roundtrip_fee_usd"], 0)
        gross = second["economic_reconciliation"]["gross_before_fee_price_pnl_usd"]
        fee = second["economic_reconciliation"]["roundtrip_fee_usd"]
        self.assertAlmostEqual(gross-fee, second["net_pnl_usd"], places=2)
        records, sequence, tip, _ = engine.replay(self.root)
        self.assertEqual((sequence, tip), (2, second["ledger_tip_sha256"]))
        self.assertNotEqual(tip, old_hash)
        self.assertEqual(len(records), 1)
        self.assertEqual(next(iter(records.values()))["status"], "CLOSED")
        self.assertEqual(
            json.loads((self.root/"data"/"report.json").read_text())["verified_events"], 2)

    def test_fail_closed_unknown_mode_or_invalid_requested_count(self):
        with self.assertRaisesRegex(ValueError, "invalid v8 entry_mode"):
            self.execute(entry_mode="unknown")
        with self.assertRaisesRegex(ValueError, "invalid requested"):
            with contextlib.redirect_stdout(io.StringIO()):
                engine.run(-1, clock=lambda: self.now)
        self.assertEqual(engine.replay(self.root)[1], 0)


if __name__ == "__main__":
    unittest.main()
