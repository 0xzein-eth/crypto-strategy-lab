"""Strictly prospective, version-frozen 90d research trial; NO trading.

Chosen candidate hypotheses FB-v3 and VWAP-v1 were inspected repeatedly
prior to registration. We pre-register ONE genuinely *future* window
before looking at its outcomes. During it we publish ONLY observation
and source-integrity counts; this module withholds all candidate returns.
Public source data remain available separately, so this is NOT guaranteed
blinded or pristine in the clinical sense. Do not tune the frozen version.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from v2 import shadow_research
from v2 import forward_paper
from v2 import evidence_gate
from v2.paper_portfolio import ts

UTC=dt.timezone.utc
START=dt.datetime(2026,10,21,0,0,tzinfo=UTC)
END=dt.datetime(2027,1,19,0,0,tzinfo=UTC)
HORIZON=dt.timedelta(hours=4)
MAX_EXIT_DELAY=dt.timedelta(minutes=30)
CANDIDATES=("FB-v3","VWAP-v1")
UNIVERSE=("BTC","ETH","SOL")
MIN_TRIAL_DAYS=40
MIN_TRIAL_WEEKS=8
MIN_PAIRED_MATCHES_PER_ARM=100
MAX_DRAWDOWN_USDT=100
MIN_PORTFOLIO_PROFIT_FACTOR=1.20
VERSION="v2-90day-predeclared-future-paper-v1"


def contract():
    policy={
        "schema":VERSION,
        "registered_utc":"2026-10-20",
        "future_entry_start_utc":START.isoformat(),
        "future_entry_end_exclusive_utc":END.isoformat(),
        "minimum_calendar_days":90,
        "source_signal_policy_version":forward_paper.VERSION,
        "source_shadow_catalog_version":shadow_research.VERSION,
        "frozen_catalog_count":len(shadow_research.ARMS),
        "predeclared_candidate_arms":list(CANDIDATES),
        "predeclared_exact_symbols":list(UNIVERSE),
        "fixed_horizon_hours":4,
        "source_hypothetical_wallet_initial_usdt":1000,
        "maximum_hypothetical_wallet_positions":2,
        "maximum_hypothetical_wallet_leverage":2,
        "minimum_utc_day_groups":MIN_TRIAL_DAYS,
        "minimum_iso_weeks":MIN_TRIAL_WEEKS,
        "minimum_depth_matched_book_closes_per_candidate":MIN_PAIRED_MATCHES_PER_ARM,
        "familywise_correction":"26-frozen-arm shared-day maxT; 2048 null sign permutations",
        "max_allowed_observed_portfolio_drawdown_usdt":MAX_DRAWDOWN_USDT,
        "minimum_hypothetical_fee_only_portfolio_profit_factor":MIN_PORTFOLIO_PROFIT_FACTOR,
        "unobserved_funding_or_price_impact_are_never_imputed_zero":True,
        "result_shown_before_end":False,
        "requires_explicit_separate_user_approval_for_any_real_execution":True,
    }
    encoding=json.dumps(policy,sort_keys=True,separators=(",",":"),allow_nan=False)
    return {**policy,"frozen_policy_digest_sha256":hashlib.sha256(encoding.encode()).hexdigest()}


def evaluate(wallet,shadow,*,now=None):
    rules=contract()
    if wallet.get("version")!=forward_paper.VERSION or shadow.get("version")!=shadow_research.VERSION:
        raise ValueError("INTEGRITY_FAILURE: mismatching registered v2 sources")
    if wallet.get("last_tick_hash")!=shadow.get("last_source_hash"):
        raise ValueError("INTEGRITY_FAILURE: wallet and all-arm future signal stream diverged")
    if wallet.get("real_order_submissions")!=0 or shadow.get("real_order_submissions")!=0:
        raise ValueError("INTEGRITY_FAILURE: trial contains actual trading")
    observed=wallet.get("latest_real_observation_utc")
    if not observed:
        return {"schema":VERSION,"phase":"WAITING_FOR_FIRST_VERIFIED_SOURCE",
                "contract":rules,"real_orders_enabled":False,
                "results_withheld":True,"deployment_authorized":False}
    last=ts(observed)
    if now is not None and ts(now)<last:
        raise ValueError("CLOCK_INTEGRITY: cannot claim future observed source")
    if last<START:
        return {"schema":VERSION,"phase":"WAITING_FOR_FUTURE_REGISTRATION_START",
                "contract":rules,"last_verified_source_utc":last.isoformat(),
                "real_orders_enabled":False,"results_withheld":True,
                "deployment_authorized":False}
    trial_days=min(90,max(0,(last-START).total_seconds()/86400))
    entries=shadow.get("closed_outcomes")
    if not isinstance(entries,list):
        raise ValueError("INTEGRITY_FAILURE: source lacks actual recorded future outcomes")
    frozen_rows=[]
    keys=set()
    for row in entries:
        key=row.get("entry_id")
        if key in keys:
            raise ValueError("INTEGRITY_FAILURE: duplicate prospective entry identity")
        keys.add(key)
        entry=ts(row["entry_at"])
        exit_seen=ts(row["genuine_exit_book_at"])
        if entry<START or entry>=END-HORIZON:
            continue
        # A timely final close after the period end can count only when
        # it was genuinely observed before END+30min; no synthetic fill.
        if exit_seen>END+MAX_EXIT_DELAY or exit_seen>last:
            continue
        frozen_rows.append(row)
    progress={
        "schema":VERSION,
        "phase":"COLLECTING_PREDECLARED_FUTURE",
        "contract":rules,
        "last_verified_source_utc":last.isoformat(),
        "actual_calendar_days_since_start":round(trial_days,5),
        "fully_elapsed_90_calendar_days":last>=END+MAX_EXIT_DELAY,
        "registered_candidate_count":len(CANDIDATES),
        "actual_observed_validity_subset_count":len(frozen_rows),
        "results_withheld":True,
        "no_reselection_or_tuning_during_window":True,
        "public_source_data_is_not_blinded_by_this_report":True,
        "pending_until_utc":(END+MAX_EXIT_DELAY).isoformat(),
        "real_orders_enabled":False,
        "deployment_authorized":False,
        "alpha_proven":False,
    }
    # No candidate returns, sharpe, winrate, PF or performance rankings
    # are ever released by this tracker before the actual market deadline.
    if last<END+MAX_EXIT_DELAY:
        return progress
    future_shadow={**shadow,"closed_outcomes":frozen_rows}
    corrected=evidence_gate.evaluate(future_shadow,asof=END+MAX_EXIT_DELAY)
    arm_reviews={name:corrected["arms"][name] for name in CANDIDATES}
    maturity=all(
        r["timely_depth_matched_closed"]>=MIN_PAIRED_MATCHES_PER_ARM
        and r["distinct_utc_entry_days"]>=MIN_TRIAL_DAYS
        and r["distinct_iso_weeks"]>=MIN_TRIAL_WEEKS
        for r in arm_reviews.values())
    all_costs_complete=bool(wallet.get("funding_source_complete")) and not bool(
        wallet.get("future_slippage_and_market_impact_unverified",True))
    equity_stress_complete=bool(
        wallet.get("closed_positions",0)>0 and
        wallet.get("observed_closed_profit_factor_fee_bidask_only") is not None
        and float(wallet["observed_closed_profit_factor_fee_bidask_only"]) >=
            MIN_PORTFOLIO_PROFIT_FACTOR and
        float(wallet.get("observed_max_drawdown_usdt",1e9))<=MAX_DRAWDOWN_USDT)
    candidates_exploratory_pass=all(
        r["positive_absolute_stressed_mean_required"] and
        r["shared_day_maxT_adjusted_p_exploratory"] is not None and
        r["shared_day_maxT_adjusted_p_exploratory"]<=0.05
        for r in arm_reviews.values())
    # Corrected p is descriptive and repeated source inspections are
    # unavoidable. NO live permission is exposed even if all checks pass.
    progress.update(
        phase="FINAL_WINDOW_ENDED_UNVERIFIED_EXECUTION_AND_REVIEW_REQUIRED",
        results_withheld=False,
        maturity_reached=maturity,
        both_candidates_positive_exploratory_maxT=candidates_exploratory_pass,
        complete_funding_spread_slippage_impact=all_costs_complete,
        cash_constrained_hypothetical_wallet_risk_gate=equity_stress_complete,
        after_all_costs_untouched_alpha_proven=False,
        requires_new_independent_confirmatory_trial_if_repeatedly_inspected=True,
        per_candidate_descriptive_review=arm_reviews,
        final_readiness_blockers=[
            label for condition,label in (
                (maturity,"INSUFFICIENT_INDEPENDENT_VALID_FUTURE_DAYS"),
                (candidates_exploratory_pass,"NO_POSITIVE_FAMILYWISE_MATCHED_CONTROL_EVIDENCE"),
                (all_costs_complete,"UNMEASURED_FUNDING_OR_ACTUAL_EXECUTION"),
                (equity_stress_complete,"INSUFFICIENT_FUNDED_PAPER_PORTFOLIO_RISK_CONTROL"))
            if not condition
        ],
    )
    return progress


def main():
    cli=argparse.ArgumentParser(description="Frozen 90d forward research: do not peek before 2027")
    cli.add_argument("--wallet",default="v2_state/report.json")
    cli.add_argument("--shadow",default="v2_state/shadow_report.json")
    cli.add_argument("--output",default=None)
    args=cli.parse_args()
    if not Path(args.wallet).is_file() or not Path(args.shadow).is_file():
        output={
            "schema":VERSION,"phase":"WAITING_FOR_REAL_SOURCE",
            "contract":contract(),"results_withheld":True,
            "real_orders_enabled":False,"deployment_authorized":False,
        }
    else:
        output=evaluate(json.loads(Path(args.wallet).read_text()),
                        json.loads(Path(args.shadow).read_text()))
    document=json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if args.output:
        Path(args.output).write_text(document,encoding="utf-8")
    else:
        print(document)


if __name__=="__main__":
    main()
