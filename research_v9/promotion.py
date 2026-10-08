"""Conservative promotion QUEUE for independent future paper-trial code review.

No strategy is implemented by this module, and no v8 OPEN event is created.
Historical walk-forward validation is inspected repeatedly; this queue is a
screening tool, NEVER a claim of statistical proof or expected live profits.
"""
import datetime as dt
import re

PROMOTION_POLICY = "research-v9.1-review-gate-1"


def build_queue(report):
    if report.get("historical_only") is not True or report.get("proven_edge") is not False:
        raise ValueError("INTEGRITY_FAILURE: promotional input must be historical and unproven")
    measured = set(report.get("measured_funding_symbols", []))
    analyzed = set(report.get("symbols_analyzed", []))
    if not analyzed:
        raise ValueError("DATA_UNAVAILABLE: missing symbols")
    full_funding = measured == analyzed and not report.get("funding_fetch_failures")
    folds = report.get("folds", [])
    recommendations, diagnostics = [], []
    for candidate in report.get("walk_forward_selected", []):
        ident = candidate["variant_id"]
        metric = candidate["walk_forward"]
        selected = int(candidate["folds_selected"])
        match = re.search(r"-H([0-9]+)$", ident)
        if not match:
            raise ValueError("INTEGRITY_FAILURE: unrecognized versioned variant identifier")
        horizon = int(match.group(1))
        passing_folds = 0
        for fold in folds:
            chosen = next((c for c in fold["selected_for_validation"]
                           if c["variant_id"] == ident), None)
            if chosen is None:
                continue
            m = chosen["validation"]
            controls = fold["controls"]
            names = (f"control-L0-T0p0-S0-H{horizon}",
                     f"long_control-L0-T0p0-S0-H{horizon}")
            comparator = [controls[k]["avg_R"] for k in names
                          if k in controls and controls[k]["avg_R"] is not None
                          and controls[k]["n"] >= 10]
            if (len(comparator) == 2 and m["n"] >= 20
                    and m["days"] >= 4
                    and m["avg_R"] is not None
                    and m["avg_R"] > max(comparator) + 0.05
                    and m["funding_adjusted_avg_R"] is not None
                    and m["funding_adjusted_avg_R"] > 0
                    and m["barrier_touches"] == 0):
                passing_folds += 1
        ready = (full_funding and selected >= 2 and passing_folds >= 2
                 and metric["n"] >= 80 and metric["days"] >= 12
                 and metric["day_lcb_R"] is not None
                 and metric["day_lcb_R"] > 0.05
                 and metric["funding_adjusted_avg_R"] is not None
                 and metric["funding_adjusted_avg_R"] > 0.05
                 and metric["barrier_touches"] == 0)
        diagnostics.append({
            "variant_id": ident, "passes_gate": bool(ready),
            "selected_folds": selected, "folds_beating_controls_after_cost": passing_folds,
            "validation_n": metric["n"], "distinct_utc_days": metric["days"],
            "day_lcb_R": metric["day_lcb_R"],
            "funding_adjusted_avg_R": metric["funding_adjusted_avg_R"],
            "margin_proxy_barrier_touches": metric["barrier_touches"],
            "full_settled_funding_coverage": full_funding
        })
        if ready:
            recommendations.append({
                "variant_id": ident, "review_status": "CODE_REVIEW_REQUIRED",
                "next_step": "Implement as NEW VERSIONED prospective paper-only hypothesis",
                "automatic_activation": False,
                "can_trade_real_money": False,
            })
    return {
        "schema_version": 1, "policy": PROMOTION_POLICY,
        "generated_at_utc": report.get("generated_at_utc"),
        "historical_eligibility_only": True,
        "settled_funding_fully_covered": full_funding,
        "eligible_for_forward_code_review": recommendations,
        "candidate_diagnostics": diagnostics,
        "paper_v8_auto_activation": False,
        "live_trading_enabled": False,
        "reason": ("Requires independent FROZEN future-only prospective evidence. "
                   "Repeatedly inspected validation is not a clean final holdout."),
    }
