#!/usr/bin/env python3
"""Run independent v9 historical research; NEVER submit orders or edit v8 ledger."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import universe
from research_v9.factory import walk_forward
from research_v9.history import load_cache, refresh_symbol

ROOT = Path(__file__).resolve().parent
RESULT_PATH = ROOT / "research_results" / "latest.json"
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL", "LINK")


def dataset_digest(bars):
    serialized = json.dumps(bars, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def produce(symbols=DEFAULT_SYMBOLS, offline=False, cold_pages=16,
            update_pages=10, max_variants=260, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    if len(set(symbols)) != len(symbols) or not 2 <= len(symbols) <= 10:
        raise ValueError("select 2..10 distinct research symbols")
    if any(s not in universe.SYMBOLS for s in symbols):
        raise ValueError("symbol not in predeclared v8 universe")
    datasets, problems = {}, {}
    for symbol in symbols:
        try:
            candles = (load_cache(symbol) if offline else
                       refresh_symbol(symbol, cold_pages=cold_pages,
                                      update_pages=update_pages, now=now))
            if len(candles) < 800:
                raise ValueError("DATA_INSUFFICIENT: less than 800 consecutive 15m candles")
            datasets[symbol] = candles
        except Exception as exc:
            # Record failures, but never fabricate history to fill the gaps.
            problems[symbol] = type(exc).__name__ + ": " + str(exc)[:180]
    if len(datasets) < 2:
        raise RuntimeError("DATA_UNAVAILABLE: need two verified perpetual instruments; errors=" +
                           json.dumps(problems, sort_keys=True))
    metrics = walk_forward(datasets, max_variants=max_variants)
    report = {
        **metrics,
        "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "research_status": "EXPLORATORY_HISTORICAL_ONLY",
        "data_source": "OKX public history-candles; confirmed 15m USDT perpetual",
        "backtest_entry_exit": "next 15m bar OPEN, fixed horizon; approximate, no actual fill",
        "symbols_requested": list(symbols),
        "symbols_analyzed": sorted(datasets),
        "fetch_failures": problems,
        "config": {"offline": offline, "cold_pages": cold_pages,
                   "update_pages": update_pages, "max_variants": max_variants},
        "data_provenance": {
            symbol: {
                "bars": len(rows), "sha256": dataset_digest(rows),
                "first_candle_utc": dt.datetime.fromtimestamp(
                    rows[0][0]/1000, dt.timezone.utc).isoformat(),
                "last_candle_utc": dt.datetime.fromtimestamp(
                    rows[-1][0]/1000, dt.timezone.utc).isoformat(),
            } for symbol, rows in sorted(datasets.items())
        },
        "v8_event_ledger_modified": False,
        "forward_paper_trades_created": 0,
        "research_recommendation": "Continue prospective v8 paper trades separately; "
                                   "historical candidates require versioned, independent "
                                   "forward validation before any promotion."
    }
    # Derivative output only. No historical records are copied into v8 event history.
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = RESULT_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True,
                               allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, RESULT_PATH)
    return report


def main():
    parser = argparse.ArgumentParser(description="V9 paper-only historical research")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--offline", action="store_true",
                        help="Read local cache only; never access exchanges")
    parser.add_argument("--cold-pages", type=int, default=16)
    parser.add_argument("--update-pages", type=int, default=10)
    parser.add_argument("--max-variants", type=int, default=260)
    args = parser.parse_args()
    report = produce(args.symbols, args.offline, args.cold_pages,
                     args.update_pages, args.max_variants)
    print(json.dumps({
        "research_status": report["research_status"],
        "symbols": report["symbols_analyzed"],
        "candidate_variants": report["candidates_evaluated"],
        "common_bars": report["common_bars"],
        "walkforward_selected": len(report["walk_forward_selected"]),
        "proven_edge": report["proven_edge"],
        "fetch_failures": report["fetch_failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
