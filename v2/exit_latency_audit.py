"""Read-only audit of observed fixed-horizon exit latency in the v2 PAPER wallet.

This reports operational delay only. It never changes exits, wallet cash,
strategy eligibility, frozen-trial rules, or the append-only source journal.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from v2.paper_portfolio import ts

SCHEMA = "v2-observed-exit-latency-audit-v1"
TIMELY_LIMIT_SECONDS = 30 * 60
BUCKETS = (
    ("0-5m", 0, 5 * 60),
    ("5-15m", 5 * 60, 15 * 60),
    ("15-30m", 15 * 60, 30 * 60),
    ("30-60m", 30 * 60, 60 * 60),
    ("60m+", 60 * 60, None),
)


def audit(report):
    if not isinstance(report, dict):
        raise ValueError("INTEGRITY_FAILURE: report must be an object")
    rows = report.get("recorded_closed_outcomes")
    if not isinstance(rows, list):
        raise ValueError("SOURCE_UNAVAILABLE: closed outcome records missing")

    delays = []
    by_strategy = defaultdict(list)
    by_symbol = defaultdict(list)
    buckets = Counter()
    late = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INTEGRITY_FAILURE: malformed closed outcome")
        try:
            delay = (ts(row["actually_closed_at"]) -
                     ts(row["fixed_evaluate_at"])).total_seconds()
            strategy = row["strategy"]
            symbol = row["symbol"]
            ident = row["id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("INTEGRITY_FAILURE: incomplete exit timestamp record") from exc
        if delay < 0:
            raise ValueError("CLOCK_INTEGRITY: exit observed before fixed evaluation")
        delay = int(delay)
        delays.append(delay)
        by_strategy[strategy].append(delay)
        by_symbol[symbol].append(delay)
        if delay > TIMELY_LIMIT_SECONDS:
            late += 1
        for label, lower, upper in BUCKETS:
            if delay >= lower and (upper is None or delay < upper):
                buckets[label] += 1
                break

    def summarize(values):
        if not values:
            return {"count": 0, "mean_delay_seconds": None,
                    "median_delay_seconds": None, "max_delay_seconds": None,
                    "over_30m": 0}
        ordered = sorted(values)
        n = len(ordered)
        median = (ordered[n // 2] if n % 2 else
                  (ordered[n // 2 - 1] + ordered[n // 2]) / 2)
        return {
            "count": n,
            "mean_delay_seconds": round(sum(ordered) / n, 2),
            "median_delay_seconds": median,
            "max_delay_seconds": max(ordered),
            "over_30m": sum(x > TIMELY_LIMIT_SECONDS for x in ordered),
        }

    return {
        "schema": SCHEMA,
        "paper_only": True,
        "read_only": True,
        "source_latest_observation_utc": report.get("latest_real_observation_utc"),
        "source_closed_positions": report.get("closed_positions"),
        "source_open_positions": report.get("open_positions"),
        "fixed_exit_delay_limit_seconds": TIMELY_LIMIT_SECONDS,
        "closed_outcome_count": len(delays),
        "exit_delay": summarize(delays),
        "delay_buckets": {label: buckets[label] for label, _, _ in BUCKETS},
        "by_strategy": {key: summarize(value)
                        for key, value in sorted(by_strategy.items())},
        "by_symbol": {key: summarize(value)
                      for key, value in sorted(by_symbol.items())},
        "frozen_trial_policy_unchanged": True,
        "wallet_or_source_journal_modified": False,
        "strategy_returns_and_rankings_omitted": True,
        "note": ("Delay is the elapsed time from the predeclared fixed evaluation "
                 "timestamp to the first genuinely observed close. This diagnostic "
                 "does not relax the frozen 30-minute eligibility rule or infer "
                 "unobserved prices, fills, funding, or execution costs."),
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only v2 exit-latency audit")
    parser.add_argument("--report", default="v2_state/report.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    path = Path(args.report)
    if not path.exists():
        raise SystemExit("SOURCE_UNAVAILABLE: v2 wallet report not found")
    result = audit(json.loads(path.read_text(encoding="utf-8")))
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
