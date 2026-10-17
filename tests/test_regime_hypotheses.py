"""Prospective v1 24h-regime/confirmed-15m paper hypothesis regressions."""
import copy
import datetime as dt
import unittest
import learner
import regime_hypotheses as rh
import signals

UTC = dt.timezone.utc


def screening(move=2.0, **overrides):
    quote = {"provider": "okx-swap", "market_type": "perpetual",
             "symbol": "BTC", "instrument": "BTC-USDT-SWAP",
             "observed_at": "2026-10-18T00:32:00Z", "pct24h": move}
    quote.update(overrides)
    return quote


def detected(strategy="BR-v3", side="LONG", sma20=102, sma50=100):
    return {"strategy": strategy, "side": side,
            "evidence": {"bar_span": "15m confirmed OKX USDT-SWAP",
                         "bar_time": "2026-10-18T00:15:00Z",
                         "sma20": sma20, "sma50": sma50, "atr14": 2.0,
                         "signal_rule": "confirmed original hypothesis"}}


def bars(n=70):
    start = dt.datetime(2026, 10, 17, 7, tzinfo=UTC)
    b = []
    for i in range(n):
        at = start+dt.timedelta(minutes=15*i)
        b.append({"time": at.isoformat().replace("+00:00", "Z"),
                  "open": 100.0, "high": 101.0, "low": 99.0,
                  "close": 100.0, "volume": 100.0})
    return b


def payload(b):
    result = []
    for row in reversed(b):
        ms = int(dt.datetime.fromisoformat(row["time"].replace("Z", "+00:00")).timestamp()*1000)
        result.append([str(ms), str(row["open"]), str(row["high"]),
                       str(row["low"]), str(row["close"]), str(row["volume"]),
                       "1", "1", "1"])
    return {"code": "0", "data": result}


class ProspectiveRegimeHypothesisTests(unittest.TestCase):
    def test_new_label_and_frozen_regime_for_real_confirmed_arm(self):
        original = detected()
        untouched = copy.deepcopy(original)
        decision = rh.candidates([original], screening(), "BTC")
        self.assertEqual(len(decision), 1)
        self.assertEqual(decision[0]["strategy"], "BRREG-v1")
        self.assertEqual(decision[0]["side"], "LONG")
        self.assertEqual(decision[0]["evidence"]["source_strategy"], "BR-v3")
        self.assertEqual(decision[0]["evidence"]["entry_direction_24h_pct"], 2.0)
        self.assertEqual(original, untouched)
        self.assertIn("BRREG-v1", learner.ADVANCED)

    def test_short_and_pullback_have_independent_versions(self):
        result = rh.candidates([detected("TP-v3", "SHORT", sma20=97, sma50=100)],
                               screening(-2), "BTC")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["strategy"], "TPREG-v1")
        self.assertIn("TPREG-v1", learner.ADVANCED)

    def test_reject_counter_regime_flat_wrong_trend_or_small_move(self):
        for q in (screening(-2), screening(0.99), screening(0),
                  screening(float("nan")), screening(float("inf")),
                  screening(True), screening("2")):
            self.assertEqual(rh.candidates([detected()], q, "BTC"), [])
        self.assertEqual(rh.candidates([detected(sma20=98, sma50=100)],
                                       screening(), "BTC"), [])

    def test_reject_wrong_instrument_or_missing_confirmed_evidence(self):
        for overrides in ({"provider": "kraken-spot-proxy"},
                          {"market_type": "spot_proxy"},
                          {"symbol": "ETH"},
                          {"instrument": "ETH-USDT-SWAP"},
                          {"observed_at": None}):
            self.assertEqual(rh.candidates([detected()], screening(**overrides), "BTC"), [])
        bad = detected()
        bad["evidence"]["bar_span"] = "forming 15m candle"
        self.assertEqual(rh.candidates([bad], screening(), "BTC"), [])
        self.assertEqual(rh.candidates([detected("CTRL-v1")], screening(), "BTC"), [])

    def test_end_to_end_only_confirmed_15m_candle(self):
        rows = bars()
        rows[-1].update(open=100, high=105, low=99, close=104, volume=220)
        last_start = dt.datetime.fromisoformat(rows[-1]["time"].replace("Z", "+00:00"))
        now = last_start + dt.timedelta(minutes=17)
        quote = screening(observed_at=now.isoformat().replace("+00:00", "Z"))
        data = payload(rows)
        decisions = signals.from_okx("BTC", quote, lambda url: data, lambda: now)
        self.assertTrue(any(r["strategy"] == "BR-v3" for r in decisions))
        versioned = [r for r in decisions if r["strategy"] == "BRREG-v1"]
        self.assertEqual(len(versioned), 1)
        self.assertEqual(versioned[0]["evidence"]["bar_time"], rows[-1]["time"])
        self.assertEqual(versioned[0]["evidence"]["entry_regime_observed_at"],
                         quote["observed_at"])
        # The last bar is unconfirmed: it MUST NOT create the new arm.
        data["data"][0][-1] = "0"
        without = signals.from_okx("BTC", quote, lambda url: data, lambda: now)
        self.assertFalse(any(r["strategy"] == "BRREG-v1" for r in without))

    def test_reject_stale_confirmed_candle_even_if_ticker_recent(self):
        rows = bars()
        rows[-1].update(open=100, high=105, low=99, close=104, volume=220)
        last_start = dt.datetime.fromisoformat(rows[-1]["time"].replace("Z", "+00:00"))
        now = last_start + dt.timedelta(minutes=50)
        quote = screening(observed_at=now.isoformat().replace("+00:00", "Z"))
        with self.assertRaisesRegex(ValueError, "stale"):
            signals.from_okx("BTC", quote, lambda url: payload(rows), lambda: now)


if __name__ == "__main__":
    unittest.main()
