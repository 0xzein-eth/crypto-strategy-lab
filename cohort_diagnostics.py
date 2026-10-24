"""Read-only, cost-reconciled provenance diagnostics for v8 PAPER research.

No allocation or champion is based on these reports: observations correlate by
UTC day, instrument, horizon and market. Never treat 10,000 USD notional
per hypothesis as a capital-funded wallet or samples as independent trials.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math


UTC = timezone.utc
CONFIRMED_BAR_SPAN = "15m confirmed OKX USDT-SWAP"
BASELINES = {"BR-proxy-v1", "MR-proxy-v1", "CTRL-v1"}


def _day(iso):
    date = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("missing UTC offset on recorded prospective entry")
    return date.astimezone(UTC).date().isoformat()


def _provenance(record):
    evidence = record.get("evidence") or {}
    if record.get("strategy") in BASELINES:
        return "direction_proxy_or_neutral_control"
    if (evidence.get("bar_span") == CONFIRMED_BAR_SPAN and
            isinstance(evidence.get("bar_time"), str) and
            evidence.get("bar_time")):
        return "confirmed_15m_candle"
    return "unverified_advanced_signal_metadata"


def summarize(records):
    """Partition CLOSED outcomes before any strategy ranking or hypothesis testing.

    This purely descriptive analysis never reads or modifies allocation choices,
    and computes monetary totals from the same canonical close records.
    """
    values = records.values() if isinstance(records, dict) else records
    counters = defaultdict(int)
    by_provenance = {}
    cells = {}
    total = {"n": 0, "gross_before_fee_usd": 0., "fees_usd": 0.,
             "net_fee_only_usd": 0., "stress_net_usd": 0.,
             "stress_count": 0}
    for record in values:
        if record.get("status") != "CLOSED":
            continue
        counters["all_closed"] += 1
        market = record.get("market_type")
        if market != "perpetual":
            counters["non_perpetual_closed"] += 1
            continue
        if record.get("late_excluded", True):
            counters["late_perpetual_closed"] += 1
            continue
        counters["eligible_timely_perpetual_closed"] += 1
        provenance = _provenance(record)
        counters["eligible_" + provenance] += 1
        name = (str(record.get("strategy")), int(record["horizon_hours"]), provenance)
        for pool, key in ((by_provenance, provenance), (cells, name)):
            if key not in pool:
                pool[key] = {"n": 0, "gross_before_fee_usd": 0.,
                             "fees_usd": 0., "net_fee_only_usd": 0.,
                             "stress_net_usd": 0., "stress_count": 0,
                             "utc_days": set()}
        net = float(record["net_pnl_usd"])
        fee = float(record["fee_round_trip_usd"])
        if not (math.isfinite(net) and math.isfinite(fee) and fee >= 0):
            raise ValueError("invalid canonical net PnL or roundtrip fee")
        day = _day(record["created_at"])
        for pool in (total, by_provenance[provenance], cells[name]):
            pool["n"] += 1
            pool["gross_before_fee_usd"] += net + fee
            pool["fees_usd"] += fee
            pool["net_fee_only_usd"] += net
            if "stress_net_pnl_usd" in record:
                stress = float(record["stress_net_pnl_usd"])
                if not math.isfinite(stress):
                    raise ValueError("invalid canonical modeled stress outcome")
                pool["stress_count"] += 1
                pool["stress_net_usd"] += stress
        by_provenance[provenance]["utc_days"].add(day)
        cells[name]["utc_days"].add(day)
    def publish(row, with_days=True):
        data = {k: round(row[k], 2) for k in (
            "gross_before_fee_usd", "fees_usd", "net_fee_only_usd")}
        data["n"] = row["n"]
        data["mean_net_usd_per_hypothesis"] = (
            round(row["net_fee_only_usd"] / row["n"], 4) if row["n"] else None)
        data["stress_model_covered"] = row["stress_count"]
        data["stress_model_net_usd"] = (
            round(row["stress_net_usd"], 2) if row["stress_count"] else None)
        if with_days:
            data["observed_distinct_utc_entry_days"] = len(row["utc_days"])
        return data
    strata = [
        {"strategy": strategy, "horizon_hours": horizon,
         "signal_provenance": provenance, **publish(values)}
        for (strategy, horizon, provenance), values in cells.items()
    ]
    strata.sort(key=lambda row: (
        row["strategy"], row["horizon_hours"], row["signal_provenance"]))
    return {
        "version": "immutable-v8-cohort-provenance-and-cost-v1",
        "population": "CLOSED timely perpetual only; all other cohorts excluded",
        "closed_partition": dict(sorted(counters.items())),
        "eligible_cost_reconciliation": publish(total, with_days=False),
        "by_source_provenance": {
            k: publish(v) for k, v in sorted(by_provenance.items())},
        "by_strategy_horizon_provenance": strata,
        "strictly_descriptive_no_allocation_feedback": True,
        "not_independent_trials": True,
        "not_a_funded_wallet": True,
        "unknown_unverified_advanced_not_promoted": True,
        "stress_is_modeled_not_real_fills": True,
        "note": ("Reports original immutable outcomes with source provenance; "
                 "multiple hypotheses share instruments, UTC regimes and data. "
                 "Positive retrospective net cells are NOT investable champions."),
    }
