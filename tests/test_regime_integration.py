"""End-to-end PAPER entry integration: immutable old entries, frozen new version."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

import engine
import learner
import regime_hypotheses as rh


class ForwardEntryIntegrationTests(unittest.TestCase):
    def test_new_regime_arm_creates_only_new_fixed_horizon_paper_open(self):
        now = dt.datetime(2026, 10, 18, 0, 32, tzinfo=dt.timezone.utc)
        q = {"symbol": "BTC", "price": 100.0, "pct24h": 2.5,
             "quote_volume_24h": 2_000_000.0,
             "observed_at": engine.stamp(now), "provider": "okx-swap",
             "market_type": "perpetual", "instrument": "BTC-USDT-SWAP"}
        confirmed = [{"strategy": "BR-v3", "side": "LONG",
                      "evidence": {"bar_span": "15m confirmed OKX USDT-SWAP",
                                   "bar_time": "2026-10-18T00:15:00Z",
                                   "sma20": 102.0, "sma50": 100.0,
                                   "atr14": 2.0, "signal_rule": "confirmed breakout"}}]
        new_arm = rh.candidates(confirmed, q, "BTC")
        self.assertEqual(len(new_arm), 1)

        # Preserve an unrelated historical CLOSED position byte-for-byte.
        existing = {"id": "LAB-1", "status": "CLOSED",
                    "created_at": "2026-10-01T00:00:00Z",
                    "symbol": "ETH", "provider": "okx-swap",
                    "strategy": "BR-v3", "horizon_hours": 1}
        records = {existing["id"]: existing}
        before = copy.deepcopy(records)

        def read_quote(symbol, provider):
            if symbol != "BTC":
                raise ValueError("no authentic quote for other symbols")
            return q

        def choose_new(options, records, symbol, horizon, slot, rank, profile=None):
            return next((item for item in options if item["strategy"] == "BRREG-v1"), None), "test_forward_only"

        with patch.object(learner, "choose", side_effect=choose_new):
            opens = engine.new_candidates(
                records, read_quote, now, 5000, 2,
                advanced=lambda symbol, quote: new_arm,
                reobserve=lambda symbol, provider: q,
                clock=lambda: now)

        self.assertEqual(records, before)
        self.assertEqual(len(opens), 1)
        new = opens[0]
        self.assertEqual(new["id"], "LAB-5000")
        self.assertEqual(new["strategy"], "BRREG-v1")
        self.assertEqual(new["status"], "OPEN")
        self.assertEqual(new["provider"], "okx-swap")
        self.assertEqual(new["market_type"], "perpetual")
        self.assertIn(new["horizon_hours"], (1, 2, 4, 8, 12, 24))
        self.assertEqual((engine.parse(new["evaluate_at"]) -
                          engine.parse(new["created_at"])).total_seconds(),
                         new["horizon_hours"]*3600)
        self.assertEqual(new["evidence"]["hypothesis_version"], rh.VERSION)
        self.assertEqual(new["evidence"]["entry_regime_observed_at"],
                         q["observed_at"])
        self.assertTrue(new["evidence"]["research_only"])


if __name__ == "__main__":
    unittest.main()
