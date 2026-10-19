"""One-source forward/historical candle SIGNAL parity harness (PAPER only).

v8 prospective candle rules in signals.classify() are the ONLY shared rules
tested here. The v9 parameter factory has different hypotheses and NEXT-bar
OPEN fills; historical v9 execution is NOT claimed to be equivalent.
"""
import datetime as dt
import hashlib
import json
import math

import signals
import regime_hypotheses
from research_v9.history import BAR_MS, validate_series

UTC = dt.timezone.utc


def utc(value):
    if value.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: naive as-of timestamp")
    return value.astimezone(UTC)


def bar_view(candles, asof):
    """Return fully observed candles <= as-of, reject gaps among used bars."""
    when = int(utc(asof).timestamp() * 1000)
    selected = [r for r in candles if isinstance(r, (list, tuple))
                and len(r) == 6 and isinstance(r[0], int)
                and r[0]+BAR_MS <= when]
    validate_series(selected, min_bars=signals.MIN_BARS)
    return [{
        "time": dt.datetime.fromtimestamp(row[0]/1000, UTC).isoformat().replace("+00:00","Z"),
        "open": float(row[1]), "high": float(row[2]), "low": float(row[3]),
        "close": float(row[4]), "volume": float(row[5])} for row in selected]


def stable_signals(events):
    """Exact deterministic equality, including frozen feature observations."""
    if not isinstance(events, list):
        raise ValueError("INTEGRITY_FAILURE: invalid event sequence")
    ordered = sorted(events,key=lambda x:(x["strategy"],x["side"]))
    content = json.dumps(ordered,sort_keys=True,separators=(",",":"),
                         allow_nan=False).encode()
    return hashlib.sha256(content).hexdigest()


def from_historical_confirmed(candles, asof, market_snapshot, symbol):
    """As-of research signal using exactly current deployed v8 classifier."""
    bars = bar_view(candles, asof)
    output = signals.classify(bars)
    return output + regime_hypotheses.candidates(output,market_snapshot,symbol)


def from_online_adapter(candles, asof, market_snapshot, symbol):
    """Reconstruct unaltered exchange payload for current v8 online parser."""
    # Present future bars to the adapter intentionally. Only confirmed-as-of
    # candles get confirm=1; forming/future bars get confirm=0 and are ignored.
    when = int(utc(asof).timestamp()*1000)
    encoded = []
    for row in reversed(candles):
        if not isinstance(row,(tuple,list)) or len(row)!=6:
            raise ValueError("DATA_INVALID: malformed source candle")
        ts, op,hi,lo,close,vol = row
        confirmed = "1" if ts + BAR_MS <= when else "0"
        encoded.append([str(ts),str(op),str(hi),str(lo),str(close),
                        str(vol),"0","0",confirmed])
    request = lambda url: {"code":"0","data":encoded}
    return signals.from_okx(symbol, market_snapshot, request,lambda:utc(asof))


def verify_pair(candles, asof, snapshot, symbol):
    research = from_historical_confirmed(candles,asof,snapshot,symbol)
    online = from_online_adapter(candles,asof,snapshot,symbol)
    a, b = stable_signals(research), stable_signals(online)
    if a != b:
        raise ValueError("PARITY_FAILURE: historical asof != prospective OHLCV parser")
    return {
        "source": "same canonical v8 candle strategy rules",
        "hypotheses": len(research), "frozen_signal_hash_sha256": a,
        "asof_utc": utc(asof).isoformat(),
        "historical_signal_equals_online_adapter": True,
        "historical_v9_trade_execution_verified": False,
        "signal_parity_is_not_fill_parity": True,
        "real_orders": False,
    }


def proposed_entry_drift(confirmed_last_end, v9_next_open, v8_quote_price,
                         quote_observed_at, side):
    """Diagnostic: historical next-bar OPEN vs later prospective fresh quote.

    Not a fill/slippage measurement. Absolute divergence is an alert, never
    evidence of execution alpha. Entries are *not* retroactively aligned.
    """
    cut = utc(confirmed_last_end)
    observed = utc(quote_observed_at)
    if observed < cut:
        raise ValueError("CLOCK_INTEGRITY: quote before confirmed candle")
    if side not in ("LONG","SHORT"):
        raise ValueError("invalid side")
    values = [float(v9_next_open), float(v8_quote_price)]
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("DATA_INVALID: invalid quote / bar price")
    signed = (values[1]/values[0]-1) * (1 if side=="LONG" else -1)*100
    return {
        "measurement": "hypothetical historical next-open versus observed paper quote",
        "entry_drift_pct_signed": round(signed,8),
        "time_lag_seconds": (observed-cut).total_seconds(),
        "v9_next_bar_open": values[0], "v8_observed_ticker": values[1],
        "a_real_executed_fill": False,
    }
