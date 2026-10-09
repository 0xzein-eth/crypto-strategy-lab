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
from research_v9 import funding
from research_v9.promotion import build_queue

ROOT = Path(__file__).resolve().parent
RESULT_PATH = ROOT / "research_results" / "latest.json"
QUEUE_PATH = ROOT / "research_results" / "forward_candidates.json"
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL", "LINK", "XRP", "ADA", "AVAX", "DOGE")


def dataset_digest(bars):
    serialized = json.dumps(bars, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def produce(symbols=DEFAULT_SYMBOLS, offline=False, cold_pages=16,
            update_pages=10, max_variants=260, now=None,
            backfill_pages=10, funding_pages=5):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    if len(set(symbols)) != len(symbols) or not 2 <= len(symbols) <= 10:
        raise ValueError("select 2..10 distinct research symbols")
    if any(s not in universe.SYMBOLS for s in symbols):
        raise ValueError("symbol not in predeclared v8 universe")
    datasets, problems = {}, {}
    funding_by_symbol, funding_errors, funding_coverage = {}, {}, {}
    for symbol in symbols:
        try:
            candles = (load_cache(symbol) if offline else
                       refresh_symbol(symbol, cold_pages=cold_pages,
                                      update_pages=update_pages, now=now,
                                      backfill_pages=backfill_pages))
            if len(candles) < 800:
                raise ValueError("DATA_INSUFFICIENT: less than 800 consecutive 15m candles")
            datasets[symbol] = candles
        except Exception as exc:
            # Record failures, but never fabricate history to fill the gaps.
            problems[symbol] = type(exc).__name__ + ": " + str(exc)[:180]
    if len(datasets) < 2:
        raise RuntimeError("DATA_UNAVAILABLE: need two verified perpetual instruments; errors=" +
                           json.dumps(problems, sort_keys=True))
    for symbol, candles in sorted(datasets.items()):
        try:
            rates = (funding.load_cache(symbol) if offline else
                     funding.refresh_symbol(symbol, pages=funding_pages, now=now,
                                            first_bar_ms=candles[0][0],
                                            backfill_pages=funding_pages))
            is_complete = funding.coverage(
                rates, candles[0][0], candles[-1][0] + 15*60_000)
            funding_coverage[symbol] = {
                "historical_settlements": len(rates),
                "complete_for_candle_window": bool(is_complete),
                "first_settlement_utc": (dt.datetime.fromtimestamp(rates[0][0]/1000,
                                         dt.timezone.utc).isoformat() if rates else None),
                "last_settlement_utc": (dt.datetime.fromtimestamp(rates[-1][0]/1000,
                                        dt.timezone.utc).isoformat() if rates else None),
                "sha256": dataset_digest(rates) if rates else None
            }
            if is_complete:
                funding_by_symbol[symbol] = rates
            else:
                funding_errors[symbol] = "INCOMPLETE: cannot treat missing settlements as 0%"
        except Exception as exc:
            funding_errors[symbol] = type(exc).__name__ + ": " + str(exc)[:180]
            funding_coverage[symbol] = {"complete_for_candle_window": False}
    metrics = walk_forward(datasets, max_variants=max_variants,
                           funding_by_symbol=funding_by_symbol)
    report = {
        **metrics,
        "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "research_status": "EXPLORATORY_HISTORICAL_ONLY",
        "historical_overlap_days": round(metrics["common_bars"] / 96, 2),
        "historical_cache_cap_bars_per_instrument": 12_000,
        "ninety_day_overlap_reached": bool(metrics["common_bars"] >= 90 * 96),
        "history_quality_note": ("Overlapping observations across requested symbols; "
                                 "number of days does not establish distinct market regimes"),
        "data_source": "OKX public history-candles; confirmed 15m USDT perpetual",
        "backtest_entry_exit": "next 15m bar OPEN, fixed horizon; approximate, no actual fill",
        "symbols_requested": list(symbols),
        "symbols_analyzed": sorted(datasets),
        "fetch_failures": problems,
        "funding_fetch_failures": funding_errors,
        "funding_coverage": funding_coverage,
        "funding_method": "settled realizedRate, constant-notional scenario; "
                          "excluded entirely for symbols without full coverage",
        "barrier_method": "intrabar high-low adverse threshold only at "
                          "3x hypothetical leverage and 0.5% assumed maintenance margin",
        "config": {"offline": offline, "cold_pages": cold_pages,
                   "update_pages": update_pages, "backfill_pages": backfill_pages,
                   "funding_pages": funding_pages, "max_variants": max_variants},
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
    # Derivative outputs only. Never append into v8 prospective event source.
    queue = build_queue(report)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path, obj in ((RESULT_PATH, report), (QUEUE_PATH, queue)):
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(obj, indent=2, sort_keys=True,
                                   allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temp, path)
    return report


def main():
    parser = argparse.ArgumentParser(description="V9 paper-only historical research")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--offline", action="store_true",
                        help="Read local cache only; never access exchanges")
    parser.add_argument("--cold-pages", type=int, default=16)
    parser.add_argument("--update-pages", type=int, default=10)
    parser.add_argument("--backfill-pages", type=int, default=10)
    parser.add_argument("--funding-pages", type=int, default=5)
    parser.add_argument("--max-variants", type=int, default=260)
    args = parser.parse_args()
    report = produce(args.symbols, args.offline, args.cold_pages,
                     args.update_pages, args.max_variants,
                     backfill_pages=args.backfill_pages,
                     funding_pages=args.funding_pages)
    print(json.dumps({
        "research_status": report["research_status"],
        "symbols": report["symbols_analyzed"],
        "candidate_variants": report["candidates_evaluated"],
        "common_bars": report["common_bars"],
        "measured_funding_symbols": report["measured_funding_symbols"],
        "funding_coverage_failures": report["funding_fetch_failures"],
        "walkforward_selected": len(report["walk_forward_selected"]),
        "proven_edge": report["proven_edge"],
        "fetch_failures": report["fetch_failures"],
    }, indent=2))


if __name__ == "__main__":
    main()
