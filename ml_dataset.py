#!/usr/bin/env python3
"""Read-only, leakage-resistant supervised-learning dataset builder.

Only timely, CLOSED, same-venue perpetual observations become labelled rows.
Every model feature is copied from OPEN-time metadata; post-evaluation fields
are labels/metadata only. No orders, strategy selection, or ledger writes.
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import engine

VERSION = "ml-dataset-v1"
HORIZONS = (1, 2, 4, 8, 12, 24)
NUMERIC_FEATURES = (
    "price_change_24h_pct", "quote_volume_24h",
    "last_close", "last_open", "last_high", "last_low", "last_volume",
    "c_prev", "sma20", "sma50", "sma20prev", "sma50prev",
    "rsi14", "rsi14prev", "vwap20", "vwap20prev", "z20", "atr14",
    "prev_high20", "prev_low20", "vol_ratio", "prior20_range_width",
    "older20_range_width", "prior20_mean_range",
    "upper_wick_ratio", "lower_wick_ratio",
)
CATEGORICAL_FEATURES = (
    "strategy", "side", "symbol", "regime", "cluster",
    "provider", "market_type", "horizon_hours",
)


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp missing timezone")
    return parsed.astimezone(dt.timezone.utc)


def _candidate(record):
    """Return whether a reconstructed canonical CLOSE is a valid ML label."""
    try:
        if record.get("status") != "CLOSED" or record.get("market_type") != "perpetual":
            return False
        if record.get("late_excluded") is not False or record.get("horizon_hours") not in HORIZONS:
            return False
        if record.get("exit_provider") != record.get("provider"):
            return False
        if record.get("exit_instrument") != record.get("instrument"):
            return False
        if _timestamp(record["exit_observed_at"]) < _timestamp(record["evaluate_at"]):
            return False
        if _timestamp(record["entry_observed_at"]) > _timestamp(record["created_at"]):
            return False
        for key in ("entry_price", "exit_price", "net_pnl_usd", "normalized_R", "signed_return_pct"):
            if _finite_number(record.get(key)) is None:
                return False
        return record["entry_price"] > 0 and record["exit_price"] > 0
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def make_row(record):
    """Create one row; all predictors are frozen OPEN-time inputs."""
    evidence = record.get("evidence") or {}
    features = {key: _finite_number(evidence.get(key)) for key in NUMERIC_FEATURES}
    features.update({key: record.get(key) for key in CATEGORICAL_FEATURES})
    pnl = float(record["net_pnl_usd"])
    return {
        "dataset_version": VERSION,
        "sample_id": record["id"],
        "entry_at": record["created_at"],
        "entry_observed_at": record["entry_observed_at"],
        "evaluate_at": record["evaluate_at"],
        "features_asof": record["created_at"],
        "features": features,
        "labels": {
            "net_profit": int(pnl > 1e-7),
            "net_pnl_usd": round(pnl, 6),
            "signed_return_pct": float(record["signed_return_pct"]),
            "normalized_R": float(record["normalized_R"]),
            "outcome": record.get("outcome"),
            "exit_observed_at": record["exit_observed_at"],
            "delay_seconds": int(record["delay_seconds"]),
            "fee_round_trip_usd": float(record["fee_round_trip_usd"]),
            "stress_normalized_R": _finite_number(record.get("stress_normalized_R")),
            "stress_net_pnl_usd": _finite_number(record.get("stress_net_pnl_usd")),
        },
    }


def build_dataset(records):
    """Build stable rows and an exclusion audit from engine.replay() records."""
    rows = []
    excluded = {"not_closed": 0, "not_perpetual": 0,
                "late_or_missing_late_flag": 0, "invalid_or_mismatched_observation": 0}
    source = records.values() if isinstance(records, dict) else records
    for record in source:
        if record.get("status") != "CLOSED":
            excluded["not_closed"] += 1
        elif record.get("market_type") != "perpetual":
            excluded["not_perpetual"] += 1
        elif record.get("late_excluded") is not False:
            excluded["late_or_missing_late_flag"] += 1
        elif not _candidate(record):
            excluded["invalid_or_mismatched_observation"] += 1
        else:
            rows.append(make_row(record))
    rows.sort(key=lambda item: (item["entry_at"], item["sample_id"]))
    summary = {
        "dataset_version": VERSION, "rows": len(rows), "excluded": excluded,
        "horizons": {str(h): sum(row["features"]["horizon_hours"] == h for row in rows)
                     for h in HORIZONS},
        "features_are_open_time_only": True,
        "labels_require_timely_same_venue_perpetual_close": True,
        "ledger_mutated": False, "training_performed": False,
    }
    return rows, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/ml_dataset_v1.jsonl")
    parser.add_argument("--report", default="artifacts/ml_dataset_v1_report.json")
    args = parser.parse_args(argv)
    records, sequence, head, _ = engine.replay()
    rows, summary = build_dataset(records)
    summary.update({"ledger_events_verified": sequence, "ledger_tip_sha256": head})
    output, report = Path(args.output), Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                               for row in rows), encoding="utf-8")
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
