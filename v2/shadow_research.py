"""All-registered-arm, genuinely prospective PAPER shadow cohort research.

Runs on one immutable sequence of observed exchange order books + confirmed
15m signals. Evaluates EVERY pre-registered hypothesis, without opening a
wallet position or retroactive outcome selection. Matched neutral controls
are deterministic *same-symbol/same-entry/same-horizon* hypothetical
directions selected BEFORE future prices; not actual CTRL-v1 trades.

This is descriptive research, not clean OOS selection, alpha proof, or
actual executed fills. Missing funding, order queue, impact and latency
make deployability explicitly false. All 4h exits use the first genuinely
recorded book AFTER the precommitted horizon; never interpolate.
"""
from collections import defaultdict
import datetime as dt
from decimal import Decimal
import hashlib
import json
import math
from statistics import mean, stdev

from v2.paper_portfolio import D, ts, verify_quote
from v2.cost_gate import break_even

VERSION = "v2-shadow-all-confirmed-2026-10-20-v1"
# An explicitly FROZEN hypothesis family, not a dynamically expanding
# winner list or historical v9 variant factory.
ARMS = (
    "TP-v3", "BR-v3", "MR-v3", "LS-v3", "FB-v3",
    "TREND-v1", "VOL-v1", "RANGE-v1", "RSI-v1", "CROSS-v1",
    "VWAP-v1", "DC-v1", "RSITREND-v1", "ATRCHAN-v1",
    "COMPBR-v1", "IMPULSE-v1", "TRECLAIM-v1", "VOLFADE-v1",
    "RSIREC-v1", "BRREG-v1", "TPREG-v1", "IBREAK-v1",
    "BANDREV-v1", "VWAPTR-v1", "EFFTREND-v1", "BANDSWEEP-v1",
)
HORIZON = dt.timedelta(hours=4)
NOTIONAL = Decimal("200")
TAKER_FEE = Decimal("0.0005")
EXTRA_ADVERSE_STRESS_BPS = Decimal("30")  # not observed funding or impacts
MAX_SPREAD_BPS = Decimal("15")
MAX_EXIT_DELAY = dt.timedelta(minutes=30)
MIN_DAYS_FOR_DESCRIPTIVE_INTERVAL = 4
NO_PROVEN_WINNERS = True


def stable_side(key):
    """Frozen deterministic contemporaneous random-direction comparator."""
    value = hashlib.sha256(("v2-shadow-control-v1:" + key).encode()).digest()
    return "LONG" if value[0] % 2 == 0 else "SHORT"


def price_outcome(entry_book, exit_book, side):
    """Pay both sides' observed quote spread and hypothetical taker fees."""
    entry = D(entry_book["ask"] if side == "LONG" else entry_book["bid"])
    exit_px = D(exit_book["bid"] if side == "LONG" else exit_book["ask"])
    qty = NOTIONAL / entry
    gross = (exit_px-entry) * qty * (1 if side == "LONG" else -1)
    fees = NOTIONAL * TAKER_FEE + qty * exit_px * TAKER_FEE
    return (gross-fees) / NOTIONAL * 100, (gross-fees) / NOTIONAL * 100 - EXTRA_ADVERSE_STRESS_BPS / 100


def enough_depth(book, side, *, notional=NOTIONAL):
    px = D(book["ask"] if side=="LONG" else book["bid"])
    available = D(book["ask_size_base"] if side=="LONG" else book["bid_size_base"])
    return available * px >= notional


def daily_interval(pairs):
    """Day clustered CLIPPED descriptive interval; NOT valid alpha p-value."""
    blocks=defaultdict(list)
    for item in pairs:
        blocks[item["entry_day"]].append(
            max(-3.0,min(3.0,item["delta_stress_pct"])))
    days=[mean(blocks[day]) for day in sorted(blocks)]
    if len(days)<MIN_DAYS_FOR_DESCRIPTIVE_INTERVAL:
        return None
    error=1.96*stdev(days)/math.sqrt(len(days))
    return [round(mean(days)-error,6),round(mean(days)+error,6)]


def assess(events):
    """Rebuild all cohorts deterministically from hashed, frozen real ticks."""
    from v2.forward_paper import (SYMBOLS, SLOT_SECONDS, VERSION as TICK_VERSION,
                                  HASH_ZERO, sha, validate_tick)
    slots=-1
    prev=HASH_ZERO
    pending={}
    known=set()
    outcomes=[]
    opportunity_by_arm=defaultdict(int)
    feasible_by_arm=defaultdict(int)
    unfillable_by_arm=defaultdict(int)
    closed_by_arm=defaultdict(int)
    ontime_by_arm=defaultdict(int)
    rejected_exit_depth_by_arm=defaultdict(int)
    for ix,event in enumerate(events,1):
        body={k:v for k,v in event.items() if k!="hash"}
        if (event.get("seq")!=ix or event.get("prev_hash")!=prev or
                event.get("hash")!=sha(body)):
            raise ValueError("INTEGRITY_FAILURE: shadow event chain")
        prev=event["hash"]
        tick=event["tick"]
        if tick.get("version")!=TICK_VERSION:
            raise ValueError("INTEGRITY_FAILURE: incompatible source tick")
        now=validate_tick(tick)
        slot=int(now.timestamp())//SLOT_SECONDS
        if slot<=slots:
            raise ValueError("CLOCK_INTEGRITY: duplicate or out of order shadow slot")
        slots=slot
        books=tick["books"]

        # Resolve only at an ACTUALLY OBSERVED book after elapsed 4h.
        for key in sorted(list(pending)):
            candidate=pending[key]
            if now < candidate["evaluate_at"]:
                continue
            book=books[candidate["symbol"]]
            signal_exit_ok=enough_depth(book,candidate["side"])
            control_exit_ok=enough_depth(book,candidate["control_side"])
            exit_delay=now-candidate["evaluate_at"]
            ontime=exit_delay <= MAX_EXIT_DELAY
            arm=candidate["arm"]
            closed_by_arm[arm]+=1
            matched=ontime and signal_exit_ok and control_exit_ok
            if not signal_exit_ok or not control_exit_ok:
                rejected_exit_depth_by_arm[arm]+=1
            own,own_stress=price_outcome(candidate["entry_book"],book,candidate["side"])
            neutral,neutral_stress=price_outcome(candidate["entry_book"],book,
                                                candidate["control_side"])
            row={
                "entry_id":key,"arm":arm,"symbol":candidate["symbol"],
                "signal_side":candidate["side"],"neutral_control_side":candidate["control_side"],
                "entry_at":candidate["entered_at"].isoformat(),
                "exit_due_at":candidate["evaluate_at"].isoformat(),
                "genuine_exit_book_at":now.isoformat(),
                "actual_observation_delay_seconds":round(exit_delay.total_seconds(),3),
                "entry_day":candidate["entered_at"].date().isoformat(),
                "timely":ontime,"executable_topbook_quantity_both_sides":matched,
                "assumed_net_after_book_and_fees_pct":round(float(own),7),
                "assumed_stressed_net_pct":round(float(own_stress),7),
                "same_time_neutral_net_after_book_fee_pct":round(float(neutral),7),
                "same_time_neutral_stressed_net_pct":round(float(neutral_stress),7),
                "delta_stress_pct":round(float(own_stress-neutral_stress),7),
                "funding_observed_complete":False,
                "real_exchange_fill":False,
            }
            outcomes.append(row)
            if matched:
                ontime_by_arm[arm]+=1
            del pending[key]

        for symbol in SYMBOLS:
            book=books[symbol]
            for signal in tick["signals"][symbol]:
                arm=signal["strategy"]
                if arm not in ARMS:
                    raise ValueError("INTEGRITY_FAILURE: unregistered shadow hypothesis")
                start=signal["evidence"]["bar_time"]
                side=signal["side"]
                key=f"{symbol}:{arm}:{side}:{start}"
                if key in known:
                    continue
                known.add(key)
                opportunity_by_arm[arm]+=1
                control=stable_side(key)
                spread=(D(book["ask"])-D(book["bid"])) / (
                    (D(book["ask"])+D(book["bid"]))/2) * 10000
                enough=both=enough_depth(book,side) and enough_depth(book,control)
                feasible=spread<=MAX_SPREAD_BPS and enough
                if not feasible:
                    unfillable_by_arm[arm]+=1
                    continue
                feasible_by_arm[arm]+=1
                pending[key]={
                    "arm":arm,"symbol":symbol,"side":side,"control_side":control,
                    "entry_book":book,"entered_at":now,
                    "evaluate_at":now+HORIZON,
                }

    per_arm={}
    for arm in ARMS:
        matched=[row for row in outcomes
                 if row["arm"]==arm and row["timely"] and
                    row["executable_topbook_quantity_both_sides"]]
        entry_days={row["entry_day"] for row in matched}
        weeks={dt.date.fromisoformat(day).isocalendar()[:2] for day in entry_days}
        all_opps=opportunity_by_arm[arm]
        matched_n=len(matched)
        signal_stressed=mean(row["assumed_stressed_net_pct"] for row in matched) if matched else None
        neutral_stressed=mean(row["same_time_neutral_stressed_net_pct"] for row in matched) if matched else None
        delta=mean(row["delta_stress_pct"] for row in matched) if matched else None
        lcb=daily_interval(matched)
        per_arm[arm]={
            "opportunities_from_confirmed_bars":all_opps,
            "feasible_book_entry_opportunities":feasible_by_arm[arm],
            "unfillable_or_wide_entry_count":unfillable_by_arm[arm],
            "closed_shadow_hypotheses_all":closed_by_arm[arm],
            "timely_matched_control_closed":matched_n,
            "unresolved_due_to_no_future_observation":sum(
                p["arm"]==arm for p in pending.values()),
            "not_comparable_exit_depth_count":rejected_exit_depth_by_arm[arm],
            "entry_utc_days_in_matched_cohort":len(entry_days),
            "distinct_iso_weeks_in_matched_cohort":len(weeks),
            "stressed_signal_avg_pct":round(signal_stressed,7) if signal_stressed is not None else None,
            "same_time_neutral_stressed_avg_pct":round(neutral_stressed,7) if neutral_stressed is not None else None,
            "same_time_neutral_paired_delta_pct":round(delta,7) if delta is not None else None,
            "clipped_utc_day_descriptive_pair_interval_pct":lcb,
            "descriptive_calendar_maturity_target_met":(
                len(entry_days)>=20 and len(weeks)>=4 and matched_n>=100),
            "independent_out_of_sample_proof":False,
            "eligible_for_live_deployment":False,
        }
    return {
        "version":VERSION,
        "catalog_sha256":hashlib.sha256("|".join(ARMS).encode()).hexdigest(),
        "catalog_arms":list(ARMS),
        "source_observation_events":len(events),
        "last_source_hash":prev,
        "per_arm":per_arm,
        "closed_outcomes":outcomes,
        "actual_paper_wallet_positions_created_by_this_study":0,
        "real_order_submissions":0,
        "funding_accounted_with_verified_real_settlements":False,
        "extra_30bps_stress_assumed_not_measured":True,
        "neutral_comparator_is_frozen_sha256_random_direction":True,
        "neutral_comparator_is_not_funded_live_ctrl":True,
        "historical_validation_repeatedly_inspected":True,
        "multiple_correlated_arms_tested":len(ARMS),
        "shadow_rows_do_not_imply_independent_trials":True,
        "promotion_authorized":False,
        "final_clean_holdout_complete":False,
        "after_all_costs_alpha_proven":False,
        "genuine_book_observations_no_gapfill":True,
        "hypothetical_exit_4h_first_real_observed":True,
        "research_caveat":"All arm data collection, not winner mining: real bid/ask snapshots but hypothetical best-level fills, unknown settled funding/latency/slippage. Day intervals descriptive, not multiple-testing adjusted. Do not select live strategy based on this report.",
    }
