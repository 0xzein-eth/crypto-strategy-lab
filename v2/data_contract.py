"""Immutable-source, as-of-aware 15m historical data quality manifest.

Only audits existing cache; NEVER fills missing bars or assumes a zero
funding rate. No orders, ledger writes or historical data revisions.
"""
import argparse
import datetime as dt
import hashlib
import json

from research_v9.history import BAR_MS, validate_series, load_cache
from research_v9.funding import validate_rates, load_cache as load_funding

UTC = dt.timezone.utc
SCHEMA = "v2-source-manifest-1"
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL", "LINK", "XRP", "ADA",
                   "AVAX", "DOGE", "DOT", "NEAR", "LTC", "SUI")


def stamp(ms):
    return dt.datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def digest(rows):
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest(symbol, candles, funding=None):
    """Auditable contiguous price series with explicitly UNKNOWN funding.

    Passing historical OHLCV does NOT imply historical bids/asks, funding or
    viable execution prices; each source is independently qualified.
    """
    if not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum() or symbol.upper()!=symbol:
        raise ValueError("invalid instrument symbol")
    if not candles:
        raise ValueError("DATA_UNAVAILABLE: no verified 15m candles")
    validate_series(candles, min_bars=2)  # rejects gaps/duplicates/forming/corrupt columns
    first, last = candles[0][0], candles[-1][0] + BAR_MS
    days = (last - first) / 86_400_000
    observed_utc_days = len({stamp(row[0])[:10] for row in candles})
    out = {
        "schema_version": SCHEMA, "provider": "okx-swap",
        "market_type": "perpetual", "instrument": symbol + "-USDT-SWAP",
        "bar": "15m confirmed", "source": "exchange public historical candles cache",
        "price_dataset_hash_sha256": digest(candles),
        "price_bar_count": len(candles),
        "price_start_utc": stamp(first), "price_end_exclusive_utc": stamp(last),
        "continuous_price_window_days": round(days, 6),
        "real_observed_entry_utc_days": observed_utc_days,
        "contiguous_verified_15m": True, "one_calendar_year_verified": days >= 365,
        "two_calendar_years_verified": days >= 730,
        "price_coverage_does_not_prove_liquidity": True,
        "historical_observed_bid_ask": False,
        "historical_depth_available": False,
        "funding_status": "UNKNOWN_NOT_PROVIDED",
        "funding_completeness_proved": False,
        "settled_funding_events": 0, "funding_hash_sha256": None,
        "settled_funding_start_utc": None, "settled_funding_end_utc": None,
    }
    if funding is not None:
        validate_rates(funding)
        if funding:
            out.update(
                funding_status="SETTLED_EVENTS_PARTIAL_OR_UNVERIFIED_COVERAGE",
                settled_funding_events=len(funding),
                funding_hash_sha256=digest(funding),
                settled_funding_start_utc=stamp(funding[0][0]),
                settled_funding_end_utc=stamp(funding[-1][0]),
            )
        else:
            out["funding_status"] = "NO_SETTLED_FUNDING_EVENTS"
    return out


def inventory(symbols=DEFAULT_SYMBOLS, *, price_loader=load_cache,
              funding_loader=load_funding):
    """Expose unavailable markets explicitly; never pretend missing means 0."""
    if len(set(symbols)) != len(symbols):
        raise ValueError("duplicate symbols in research inventory")
    rows, missing = {}, {}
    for symbol in symbols:
        try:
            data = price_loader(symbol)
            rates = funding_loader(symbol)
            rows[symbol] = manifest(symbol, data, funding=rates)
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            # SOURCE status not hidden. Message includes no API credentials.
            missing[symbol] = type(exc).__name__ + ": " + str(exc)[:180]
    return {
        "policy": SCHEMA, "research_only": True, "orders_sent": False,
        "markets_requested": len(symbols), "verified_markets": len(rows),
        "markets_unavailable_or_invalid": missing,
        "verified_market_manifests": rows,
        "common_prices_1y_ready": len(rows) >= 2 and all(
            item["one_calendar_year_verified"] for item in rows.values()),
        "funding_is_never_inferred_from_candles": True,
        "no_historical_gapfill": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only authentic cache inventory")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    args = parser.parse_args()
    print(json.dumps(inventory(args.symbols), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
