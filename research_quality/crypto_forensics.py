"""Crypto v8 read-only financial forensics from the hash-verified event replay.

Never interpret repeated $10k hypothesis notionals as account equity.
Completeness, cost decomposition, and correlated-day counts precede rankings.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean

VERSION = "crypto-v8-forensic-economics-v1"

def finite(value, label):
    if isinstance(value, bool):
        raise ValueError(label + ": boolean instead of quantity")
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(label + ": nonfinite quantity")
    return v

def day(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("entry timestamp must have timezone")
    return t.astimezone(timezone.utc).date().isoformat()

def score(rows):
    n = len(rows)
    pnl = [finite(r["net_pnl_usd"], "net") for r in rows]
    fee = [finite(r["fee_round_trip_usd"], "fee") for r in rows]
    gross = [p + f for p, f in zip(pnl, fee)]
    notionals = [finite(r["notional_usd"], "notional") for r in rows]
    if any(f < 0 for f in fee) or any(v <= 0 for v in notionals):
        raise ValueError("invalid notional/fee")
    gains = sum(max(p, 0) for p in pnl)
    losses = -sum(min(p, 0) for p in pnl)
    days = defaultdict(list)
    for row, p in zip(rows, pnl):
        days[day(row["created_at"])].append(p / finite(row["notional_usd"], "notional") * 100)
    daily = [mean(v) for _, v in sorted(days.items())]
    return {
        "closed": n,
        "distinct_utc_entry_days": len(days),
        "net_usd": round(sum(pnl), 2),
        "gross_price_pnl_usd": round(sum(gross), 2),
        "roundtrip_fees_usd": round(sum(fee), 2),
        "mean_net_pct_of_individual_notional": round(
            mean(p / v * 100 for p, v in zip(pnl, notionals)), 6) if n else None,
        "mean_day_equal_weight_net_pct": round(mean(daily), 6) if daily else None,
        "win_rate": round(sum(p > 0 for p in pnl) / n, 6) if n else None,
        "net_profit_factor": round(gains / losses, 6) if losses else None,
        "extra_price_edge_usd_per_trade_to_break_even": round(
            max(0, -sum(pnl)) / n, 5) if n else None,
        "sample_not_independent": True,
    }

def analyze(records, report):
    if not isinstance(report, dict) or report.get("schema_version") != 8:
        raise ValueError("expected canonical v8 report")
    rows = list(records.values()) if isinstance(records, dict) else list(records)
    closed = [r for r in rows if r["status"] == "CLOSED"]
    if len(closed) != report["closed"] or len(rows) != report["created"]:
        raise ValueError("canonical record count mismatch")
    total = score(closed)
    if (abs(total["net_usd"] - finite(report["net_pnl_usd"], "report_net")) > 0.02 or
        abs(total["roundtrip_fees_usd"] - finite(
            report["total_round_trip_fees_usd"], "report_fees")) > 0.02):
        raise ValueError("ledger PnL/fee does not reconcile with canonical report")
    groups = defaultdict(list)
    for r in closed:
        groups[(r["strategy"], r["horizon_hours"])].append(r)
    cohort = {f"{arm}/{h}h": score(arr)
              for (arm, h), arr in sorted(groups.items())}
    eligible = [r for r in closed if r["market_type"] == "perpetual"
                and not r.get("late_excluded", True)]
    return {
        "version": VERSION,
        "canonical_report_timestamp": report["timestamp"],
        "canonical_verified_events": report["verified_events"],
        "ledger_tip_sha256": report["ledger_tip_sha256"],
        "all_closed": total,
        "timely_perpetual_only": score(eligible),
        "by_arm_and_horizon": cohort,
        "arm_horizon_cells": len(cohort),
        "transaction_fee_only_not_full_execution_cost": True,
        "funding_spread_impact_unverified": True,
        "historical_repeat_notional_not_wallet_equity": True,
        "inspected_no_clean_holdout": True,
        "real_orders": 0,
        "champion": None,
        "promoted": [],
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", default="data/report.json")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    import engine
    records, _, _, _ = engine.replay()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = analyze(records, report)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True,
                              allow_nan=False) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
