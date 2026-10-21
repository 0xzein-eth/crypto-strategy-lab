"""Ex-post REAL settled funding attribution for v2 PAPER experiments.

Authentic settled perpetual payments are read ONLY from the validated v2
OKX warehouse. Funding is cash-flow cost at settlement instants, not
a direction forecast, proof of fill, or a trading decision. Missing
settlements => explicitly UNKNOWN result, never a zero-funded trade.

This is a supplementary research scorecard; it does not alter source
v2 observations, wallet cash accounting or frozen trial algorithms.
"""
import argparse
from collections import defaultdict
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path
from statistics import mean

from research_v9 import funding
from v2.history_warehouse import load as load_warehouse
from v2.paper_portfolio import D, ts
from v2.shadow_research import ARMS, VERSION as SHADOW_VERSION
from v2.forward_paper import VERSION as WALLET_VERSION

SCHEMA="v2-expost-settled-funding-reconciliation-v1"
SYMBOLS=("BTC","ETH","SOL")
UTC=dt.timezone.utc
EXTRA_UNMEASURED_IMPACT_STRESS_BPS=20


def as_ms(when):
    return int(ts(when).timestamp()*1000)


def funding_cost_pct(events, side, opened, closed):
    """Return signed cash PAID in %-of-constant-reference-notional.

    Returning None means truly UNKNOWN. Zero is returned only after the
    source settlement history explicitly passes continuity/time coverage.
    """
    begin,end=as_ms(opened),as_ms(closed)
    if begin>=end or side not in ("LONG","SHORT"):
        raise ValueError("INTEGRITY_FAILURE: invalid funded PAPER interval")
    funding.validate_rates(events)
    if not funding.coverage(events,begin,end):
        return None
    value=funding.payment_pct(events,1 if side=="LONG" else -1,begin,end)
    return D(value)


def reconcile(wallet, shadow, *, rates=None):
    if wallet.get("version")!=WALLET_VERSION or shadow.get("version")!=SHADOW_VERSION:
        raise ValueError("INTEGRITY_FAILURE: source research policy version mismatch")
    if wallet.get("last_tick_hash")!=shadow.get("last_source_hash"):
        raise ValueError("INTEGRITY_FAILURE: wallet and shadow source hash mismatch")
    if wallet.get("real_order_submissions")!=0 or shadow.get("real_order_submissions")!=0:
        raise ValueError("INTEGRITY_FAILURE: real trading is forbidden")
    catalog=shadow.get("catalog_arms")
    if catalog!=list(ARMS):
        raise ValueError("INTEGRITY_FAILURE: unknown future strategy catalog")
    if rates is None:
        rates={symbol:load_warehouse(symbol,"settled_funding") for symbol in SYMBOLS}
    if set(rates)!=set(SYMBOLS):
        raise ValueError("SOURCE_UNAVAILABLE: incomplete source instrument set")
    for symbol in SYMBOLS:
        funding.validate_rates(rates[symbol])
    shadow_rows=[]
    by_arm=defaultdict(list)
    missing=defaultdict(int)
    eligible=0
    for row in shadow["closed_outcomes"]:
        arm,symbol=row["arm"],row["symbol"]
        if arm not in ARMS or symbol not in SYMBOLS:
            raise ValueError("INTEGRITY_FAILURE: out-of-catalog funded experiment")
        if not row["timely"] or not row["executable_topbook_quantity_both_sides"]:
            continue
        eligible+=1
        own=funding_cost_pct(rates[symbol],row["signal_side"],
                             row["entry_at"],row["genuine_exit_book_at"])
        comparator=funding_cost_pct(rates[symbol],row["neutral_control_side"],
                                    row["entry_at"],row["genuine_exit_book_at"])
        if own is None or comparator is None:
            missing[arm]+=1
            continue
        before=D(row["assumed_net_after_book_and_fees_pct"])
        reference=D(row["same_time_neutral_net_after_book_fee_pct"])
        after=before-own
        counter=reference-comparator
        delta=after-counter
        # *Measured settlements* + another separate unmeasured 20bp
        # impact/latency sensitivity. This is NOT observed execution cost.
        stressed=after-D(EXTRA_UNMEASURED_IMPACT_STRESS_BPS)/100
        meta={
            "entry_id":row["entry_id"],"symbol":symbol,"arm":arm,
            "entry_day":row["entry_day"],
            "real_funding_paid_pct":float(own),
            "neutral_real_funding_paid_pct":float(comparator),
            "settled_funding_adjusted_net_pct":float(after),
            "settled_funding_adjusted_control_net_pct":float(counter),
            "incremental_after_settled_funding_pct":float(delta),
            "additional_hypothetical_impact_stress_bps":EXTRA_UNMEASURED_IMPACT_STRESS_BPS,
            "after_settled_funding_plus_unmeasured_impact_stress_pct":float(stressed),
            "real_exchange_fill":False,
        }
        shadow_rows.append(meta)
        by_arm[arm].append(meta)
    per_arm={}
    for arm in ARMS:
        rows=by_arm[arm]
        distinct_days={x["entry_day"] for x in rows}
        distinct_weeks={dt.date.fromisoformat(d).isocalendar()[:2] for d in distinct_days}
        per_arm[arm]={
            "funding_known_matched_timely_closes":len(rows),
            "missing_funding_intervals_excluded_not_zero":missing[arm],
            "independent_utc_days":len(distinct_days),
            "independent_iso_weeks":len(distinct_weeks),
            "mean_after_settled_funding_pct":round(mean(
                x["settled_funding_adjusted_net_pct"] for x in rows),7) if rows else None,
            "mean_increment_vs_same_time_funded_reference_pct":round(mean(
                x["incremental_after_settled_funding_pct"] for x in rows),7) if rows else None,
            "mean_after_settled_funding_plus_hypothetical_impact_pct":round(mean(
                x["after_settled_funding_plus_unmeasured_impact_stress_pct"]
                for x in rows),7) if rows else None,
            "final_execution_alpha_proven":False,
        }
    # Wallet cash was already simulated on bid/ask+fee; this computes a
    # supplement for CLOSED only. It never revises the wallet equity path:
    # open-position funding, mark/margin/impact remain incompletely modeled.
    wallet_adjusted=[]
    wallet_unfunded=0
    for record in wallet.get("recorded_closed_outcomes",[]):
        if record["symbol"] not in SYMBOLS:
            raise ValueError("INTEGRITY_FAILURE: out-of-universe wallet funding")
        pct=funding_cost_pct(rates[record["symbol"]],record["side"],
                             record["opened_at"],record["actually_closed_at"])
        if pct is None:
            wallet_unfunded+=1
            continue
        net=D(record["net_after_bidask_and_fee_before_unverified_funding_usdt"])
        adjustment=D("200")*pct/100
        wallet_adjusted.append({
            "id":record["id"],"symbol":record["symbol"],
            "settled_cash_paid_usdt":str(adjustment),
            "historical_closed_net_after_measured_funding_usdt":str(net-adjustment),
            "funding_settlements_authentic":True,
            "exchange_fill_known":False,
        })
    return {
        "schema":SCHEMA,"paper_only":True,
        "source_wallet_version":WALLET_VERSION,
        "source_shadow_version":SHADOW_VERSION,
        "verified_source_tick_hash":wallet["last_tick_hash"],
        "real_order_submissions":0,
        "actual_funding_cashflows_only_after_settlement":True,
        "unknown_or_missing_funding_never_assumed_zero":True,
        "matched_shadow_closes_before_funding_eligibility":eligible,
        "matched_shadow_closes_with_actual_settlements":len(shadow_rows),
        "per_arm":per_arm,"settlement_eligible_shadow_rows":shadow_rows,
        "closed_wallet_results_with_measured_funding":wallet_adjusted,
        "closed_wallet_missing_settled_funding_count":wallet_unfunded,
        "wallet_final_equity_adjusted_for_all_funding":False,
        "future_queue_impact_slippage_unverified":True,
        "genuine_fills_are_not_recorded":True,
        "90_day_untouched_alpha_proven":False,
        "live_deployment_authorized":False,
        "limitations":"Historical funding is ex-post settled. Cash flows are only modeled at constant reference notional; it does not reprice liquidations, open margin or executed order slippage. No alpha promotion.",
    }


def main():
    parser=argparse.ArgumentParser(description="Read-only measured settled-funding scorecard")
    parser.add_argument("--wallet",default="v2_state/report.json")
    parser.add_argument("--shadow",default="v2_state/shadow_report.json")
    parser.add_argument("--output",default=None)
    args=parser.parse_args()
    if Path(args.wallet).exists() and Path(args.shadow).exists():
        output=reconcile(json.loads(Path(args.wallet).read_text()),
                         json.loads(Path(args.shadow).read_text()))
    else:
        output={
            "schema":SCHEMA,"status":"NO_AUTHENTIC_FORWARD_SOURCE",
            "live_deployment_authorized":False,
            "unknown_or_missing_funding_never_assumed_zero":True,
        }
    doc=json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if args.output:
        Path(args.output).write_text(doc,encoding="utf-8")
    else:
        print(doc)


if __name__=="__main__":
    main()
