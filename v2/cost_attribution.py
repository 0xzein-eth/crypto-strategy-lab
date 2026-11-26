"""Read-only reconciliation of wallet price PnL, fees and settled funding.

The report separates the assumed bid/ask-crossing price result from explicit
fees and ex-post authentic settled funding. It never modifies the wallet,
observations, strategy eligibility, or frozen trial.
"""
import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

SCHEMA = "v2-wallet-cost-attribution-v1"


def dec(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"DATA_INVALID: {label}") from exc
    if not result.is_finite():
        raise ValueError(f"DATA_INVALID: {label}")
    return result


def reconcile(wallet, funding):
    if not isinstance(wallet, dict) or not isinstance(funding, dict):
        raise ValueError("INTEGRITY_FAILURE: source documents must be objects")
    wallet_rows = wallet.get("recorded_closed_outcomes")
    funded_rows = funding.get("closed_wallet_results_with_measured_funding")
    if not isinstance(wallet_rows, list) or not isinstance(funded_rows, list):
        raise ValueError("SOURCE_UNAVAILABLE: closed wallet rows missing")
    wallet_by_id = {}
    for row in wallet_rows:
        if not isinstance(row, dict) or not row.get("id"):
            raise ValueError("INTEGRITY_FAILURE: malformed wallet outcome")
        if row["id"] in wallet_by_id:
            raise ValueError("INTEGRITY_FAILURE: duplicate wallet outcome id")
        wallet_by_id[row["id"]] = row
    funded_by_id = {}
    for row in funded_rows:
        if not isinstance(row, dict) or not row.get("id"):
            raise ValueError("INTEGRITY_FAILURE: malformed funding outcome")
        if row["id"] in funded_by_id or row["id"] not in wallet_by_id:
            raise ValueError("INTEGRITY_FAILURE: duplicate or unmatched funding id")
        if row.get("funding_settlements_authentic") is not True:
            raise ValueError("INTEGRITY_FAILURE: funding provenance not authentic")
        if row.get("exchange_fill_known") is not False:
            raise ValueError("INTEGRITY_FAILURE: assumed fill misrepresented")
        funded_by_id[row["id"]] = row

    total_price = sum((dec(x["price_pnl_usdt"], "price pnl")
                       for x in wallet_rows), Decimal(0))
    total_entry_fee = sum((dec(x["entry_fee_usdt"], "entry fee")
                           for x in wallet_rows), Decimal(0))
    total_exit_fee = sum((dec(x["exit_fee_usdt"], "exit fee")
                          for x in wallet_rows), Decimal(0))
    net_before = sum((dec(x["net_after_bidask_and_fee_before_unverified_funding_usdt"],
                          "net before funding") for x in wallet_rows), Decimal(0))
    funding_known = len(funded_by_id)
    missing = len(wallet_rows) - funding_known
    funding_paid = sum((dec(x["settled_cash_paid_usdt"], "settled funding cash")
                        for x in funded_by_id.values()), Decimal(0))
    matched_net = sum((dec(x["historical_closed_net_after_measured_funding_usdt"],
                           "net after funding") for x in funded_by_id.values()), Decimal(0))
    per_strategy = defaultdict(lambda: {"count": 0, "net_before_funding_usdt": Decimal(0),
                                         "late_over_30m": 0})
    wins = losses = late = 0
    for row in wallet_rows:
        net = dec(row["net_after_bidask_and_fee_before_unverified_funding_usdt"],
                  "net before funding")
        wins += net > 0
        losses += net < 0
        is_late = bool(row.get("late_excluded_from_timely_study"))
        late += is_late
        group = per_strategy[row.get("strategy", "UNKNOWN")]
        group["count"] += 1
        group["net_before_funding_usdt"] += net
        group["late_over_30m"] += int(is_late)

    def fmt(value):
        return str(value.quantize(Decimal("0.000001")))

    fee_total = total_entry_fee + total_exit_fee
    # Trade-row net values are rounded independently. Keep the residual visible
    # rather than silently treating it as zero or assuming its cause.
    row_net_reconciliation_residual = net_before - (total_price - fee_total)
    precision_fields = (
        "price_pnl_unrounded_usdt", "entry_fee_unrounded_usdt",
        "exit_fee_unrounded_usdt",
        "net_after_bidask_and_fee_before_unverified_funding_unrounded_usdt",
    )
    precision_available = bool(wallet_rows) and all(
        all(field in row for field in precision_fields) for row in wallet_rows
    )
    if precision_available:
        precise_price = sum((dec(row["price_pnl_unrounded_usdt"], "precise price pnl")
                             for row in wallet_rows), Decimal(0))
        precise_entry_fee = sum((dec(row["entry_fee_unrounded_usdt"], "precise entry fee")
                                 for row in wallet_rows), Decimal(0))
        precise_exit_fee = sum((dec(row["exit_fee_unrounded_usdt"], "precise exit fee")
                                for row in wallet_rows), Decimal(0))
        precise_net_before = sum((dec(
            row["net_after_bidask_and_fee_before_unverified_funding_unrounded_usdt"],
            "precise net before funding") for row in wallet_rows), Decimal(0))
        precise_fee_total = precise_entry_fee + precise_exit_fee
        precise_residual = precise_net_before - (precise_price - precise_fee_total)
    else:
        precise_price = precise_entry_fee = precise_exit_fee = None
        precise_net_before = precise_fee_total = precise_residual = None
    gross_abs = abs(total_price)
    return {
        "schema": SCHEMA,
        "paper_only": True,
        "read_only": True,
        "real_order_submissions": wallet.get("real_order_submissions"),
        "closed_wallet_outcomes": len(wallet_rows),
        "wins_before_funding": wins,
        "losses_before_funding": losses,
        "observed_late_exits_over_30m": late,
        "assumed_top_of_book_crossing_price_pnl_usdt": fmt(total_price),
        "entry_fees_from_rounded_trade_rows_usdt": fmt(total_entry_fee),
        "exit_fees_from_rounded_trade_rows_usdt": fmt(total_exit_fee),
        "fees_from_rounded_trade_rows_usdt": fmt(fee_total),
        "reported_aggregate_simulated_fee_total_usdt": wallet.get("simulated_fee_total_usdt"),
        "rounded_trade_fee_sum_minus_aggregate_fee_usdt": fmt(
            fee_total - dec(wallet.get("simulated_fee_total_usdt", "0"), "aggregate fee")),
        "net_after_bidask_and_fees_before_funding_usdt": fmt(net_before),
        "trade_row_net_reconciliation_residual_usdt": fmt(row_net_reconciliation_residual),
        "trade_row_net_reconciliation_formula": (
            "sum(row net before funding) - (sum(row price pnl) - sum(row entry and exit fees))"
        ),
        "full_precision_source_available_for_all_closed_rows": precision_available,
        "full_precision_price_pnl_usdt": fmt(precise_price) if precision_available else None,
        "full_precision_entry_fees_usdt": fmt(precise_entry_fee) if precision_available else None,
        "full_precision_exit_fees_usdt": fmt(precise_exit_fee) if precision_available else None,
        "full_precision_fees_usdt": fmt(precise_fee_total) if precision_available else None,
        "full_precision_net_before_funding_usdt": fmt(precise_net_before) if precision_available else None,
        "full_precision_net_reconciliation_residual_usdt": (
            fmt(precise_residual) if precision_available else None
        ),
        "fee_to_absolute_crossing_price_pnl_ratio": (
            round(float(fee_total / gross_abs), 6) if gross_abs else None),
        "settled_funding_coverage": {
            "closed_wallet_intervals": len(wallet_rows),
            "authentically_funded_intervals": funding_known,
            "unknown_intervals_not_assumed_zero": missing,
            "complete_for_closed_wallet_rows": missing == 0,
        },
        "signed_settled_funding_cash_paid_usdt": fmt(funding_paid) if funding_known else None,
        "net_after_measured_funding_usdt": fmt(matched_net) if missing == 0 else None,
        "matched_subset_net_after_measured_funding_usdt": fmt(matched_net),
        "per_strategy_before_funding": {
            key: {
                "closed": value["count"],
                "net_usdt": fmt(value["net_before_funding_usdt"]),
                "late_over_30m": value["late_over_30m"],
            } for key, value in sorted(per_strategy.items())
        },
        "funding_is_not_the_only_unmodeled_cost": True,
        "exchange_fills_queue_and_future_market_impact_verified": False,
        "wallet_equity_rewritten": False,
        "strategy_ranking_or_promotion_performed": False,
        "note": (
            "Price PnL uses hypothetical top-of-book crossing prices and is not "
            "pure mid-price alpha or a verified fill. Fee components from trade "
            "rows are rounded to cents. Both the rounded-row fee sum versus aggregate "
            "fee total and the net-versus-price-minus-fees residual are exposed; neither "
            "is silently forced to zero. The current wallet close code independently "
            "rounds gross PnL, entry fee, exit fee and net PnL to cents, explaining the "
            "observed row-sum residual. Exact historical full-precision totals are not "
            "present in the current report. Optional precision fields are used only "
            "when every closed row supplies them. Funding is ex-post authentic settlement "
            "cash for matched closed intervals only. No result establishes executable "
            "alpha or live readiness."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only wallet fee/funding attribution")
    parser.add_argument("--wallet", default="v2_state/report.json")
    parser.add_argument("--funding", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    wallet = json.loads(Path(args.wallet).read_text(encoding="utf-8"))
    funding = json.loads(Path(args.funding).read_text(encoding="utf-8"))
    result = reconcile(wallet, funding)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
