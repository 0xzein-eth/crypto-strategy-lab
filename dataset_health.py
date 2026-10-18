"""Read-only, replayable cohort/data health for prospective PAPER strategy research.

This is a coverage and provenance diagnostic, NOT an allocator, strategy
promotion test, exchange-fills model or replacement for the canonical report.
"""
from collections import defaultdict
import datetime as dt
import math
from statistics import mean
import learner

UTC = dt.timezone.utc
HORIZONS = (1, 2, 4, 8, 12, 24)
VERSION = "prospective-cohort-health-v1"
MIN_DAYS = 20
MIN_WEEKS = 4


def parse_utc(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("INTEGRITY_FAILURE: missing observation timezone")
    return parsed.astimezone(UTC)


def _empty():
    return {
        "opened": 0, "open_now": 0, "open_due_pending": 0,
        "closed": 0, "eligible_timely_perpetual_closed": 0,
        "late_closed": 0, "spot_proxy_closed": 0,
        "closed_not_eligible": 0, "entry_spread_observed": 0,
        "entry_spread_not_observed": 0,
    }


def evaluate(records, report, matched_comparison=None):
    """Inspect original OPEN attributes plus actual closed eligibility only."""
    if not isinstance(report, dict) or not isinstance(report.get("timestamp"), str):
        raise ValueError("INTEGRITY_FAILURE: missing source report timestamp")
    now = parse_utc(report["timestamp"])
    rows = records.values() if isinstance(records, dict) else records
    per_arm = {}
    groups = defaultdict(list)
    seen = set()
    provider_closes = defaultdict(int)
    for row in rows:
        rid = row.get("id")
        if not isinstance(rid, str) or rid in seen:
            raise ValueError("INTEGRITY_FAILURE: duplicate or missing unique paper id")
        seen.add(rid)
        arm = row["strategy"]
        if arm not in learner.BASELINES+learner.ADVANCED:
            raise ValueError("INTEGRITY_FAILURE: unregistered research strategy")
        if row["horizon_hours"] not in HORIZONS:
            raise ValueError("INTEGRITY_FAILURE: unsupported fixed horizon")
        when = parse_utc(row["created_at"])
        if when > now + dt.timedelta(seconds=60):
            raise ValueError("INTEGRITY_FAILURE: future paper experiment")
        groups[(arm, row["horizon_hours"])].append(row)
        if row["status"] == "CLOSED":
            provider_closes[str(row["provider"])] += 1
    matched_arms = ((matched_comparison or {}).get("arms") or {})
    for arm in learner.BASELINES+learner.ADVANCED:
        horizons = {}
        arm_days = set()
        for horizon in HORIZONS:
            items = groups[(arm, horizon)]
            counts = _empty()
            eligibles = []
            for row in items:
                counts["opened"] += 1
                created = parse_utc(row["created_at"])
                original_spread = (row.get("friction_stress") or {}).get("source_spread_pct")
                if (isinstance(original_spread, (int,float))
                        and not isinstance(original_spread, bool)
                        and math.isfinite(original_spread)
                        and original_spread >= 0):
                    counts["entry_spread_observed"] += 1
                else:
                    counts["entry_spread_not_observed"] += 1
                if row["status"] == "OPEN":
                    counts["open_now"] += 1
                    if parse_utc(row["evaluate_at"]) <= now:
                        counts["open_due_pending"] += 1
                elif row["status"] == "CLOSED":
                    counts["closed"] += 1
                    if row.get("late_excluded"):
                        counts["late_closed"] += 1
                    if row.get("market_type") == "spot_proxy":
                        counts["spot_proxy_closed"] += 1
                    if learner.eligible(row):
                        counts["eligible_timely_perpetual_closed"] += 1
                        arm_days.add(created.date())
                        eligibles.append(row)
                    else:
                        counts["closed_not_eligible"] += 1
                else:
                    raise ValueError("INTEGRITY_FAILURE: unsupported paper state")
            counts["timely_eligible_fraction_of_closed"] = (
                round(counts["eligible_timely_perpetual_closed"]/counts["closed"], 6)
                if counts["closed"] else None)
            counts["actual_eligible_utc_entry_days"] = len(
                {learner.day_of(r) for r in eligibles})
            counts["after_fee_mean_R_of_eligible"] = (
                round(mean(float(r["normalized_R"]) for r in eligibles), 6)
                if eligibles else None)
            counts["stress_scenario_mean_R_of_eligible"] = (
                round(mean(learner.research_R(r) for r in eligibles), 6)
                if eligibles else None)
            horizons[str(horizon)] = counts
        totals = {k: sum(horizons[str(h)][k] for h in HORIZONS) for k in _empty()}
        weeks = {d.isocalendar()[:2] for d in arm_days}
        matched = matched_arms.get(arm, {})
        per_arm[arm] = {
            **totals,
            "distinct_eligible_entry_utc_days": len(arm_days),
            "distinct_eligible_entry_iso_weeks": len(weeks),
            "additional_entry_utc_days_to_20": max(0, MIN_DAYS-len(arm_days)),
            "additional_entry_iso_weeks_to_4": max(0, MIN_WEEKS-len(weeks)),
            "matched_control_pairs": matched.get("matched_pairs"),
            "matched_control_fraction": matched.get("matched_fraction"),
            "matched_control_entry_days": matched.get("matched_entry_utc_days"),
            "horizons": horizons,
            "edge_proven": False,
        }
    totals = {k: sum(per_arm[a][k] for a in per_arm) for k in _empty()}
    if totals["opened"] != len(seen):
        raise ValueError("INTEGRITY_FAILURE: cohort counts disagree with ledger")
    return {
        "version": VERSION,
        "paper_only": True,
        "read_only": True,
        "no_strategy_promotion": True,
        "source_report_timestamp_utc": report["timestamp"],
        "source_report_ledger_tip_sha256": report.get("ledger_tip_sha256"),
        "source_report_verified_events": report.get("verified_events"),
        "published_simulation_pnl_unchanged_usd": report.get("net_pnl_usd"),
        "source_venue_closed_counts": dict(sorted(provider_closes.items())),
        "recent_observation_coverage_ratio": (report.get("scheduling_diagnostics") or {}).get(
            "estimated_10m_slot_coverage"),
        "latest_tick_entry_opportunities": report.get("entry_opportunity_audit"),
        "latest_tick_quote_errors": report.get("source_errors") or {},
        "totals": totals,
        "arms": per_arm,
        "notes": [
            "Only the actual source ledger and entry-frozen timestamps were counted; missing 15m observations are NOT reconstructed.",
            "CLOSED late and spot proxy rows remain part of the ledger but NOT timely perpetual edge evidence.",
            "Real entry spread availability means an observed quote-field existed; stress impact is hypothetical and not an actual fill.",
            "Matched controls are retrospective observational estimates and can be missing; they do not prove alpha.",
            "Per-arm counts/means are descriptive; dependence, repeated peeks and multiplicity prevent alpha certification.",
            "No new paper OPEN, CLOSE or exit policy is generated by this report."
        ],
    }
