"""Read-only, penny-reconciled legacy v8 PAPER cohort attribution.

DOES NOT emit orders, mutate data/events, change v8 policies or pretend
repeated hypothetical $10k notionals constitute a funded account.
Run: python -m v2.legacy_audit --verify-main
"""
import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal(0)
POLICY = "v2-p0-fee-capital-audit-1"


def money(number):
    """Finite decimal dollars, rounded only at report boundary."""
    value = Decimal(str(number))
    if not value.is_finite():
        raise ValueError("INTEGRITY_FAILURE: nonfinite monetary amount")
    return value


def usd(number):
    return str(money(number).quantize(CENT, rounding=ROUND_HALF_UP))


def compute(records, *, leverage=3):
    """Attribute gross/fee/net from actual immutable CLOSED records only.

    LIVE modeled trading P&L is NOT inferred. Every fact is a function of
    the original frozen OPEN / CLOSE fields, regardless of strategy winners.
    """
    if isinstance(leverage, bool) or not isinstance(leverage, (int, float)) or not 1 <= leverage <= 20:
        raise ValueError("invalid hypothetical leverage")
    source = records.values() if isinstance(records, dict) else list(records)
    ids = set()
    n_closed = n_open = n_late = n_proxy = 0
    gross = fees = net = ZERO
    by_strategy = defaultdict(lambda: {"n": 0, "eligible_n": 0,
                                       "gross": ZERO, "fees": ZERO, "net": ZERO,
                                       "valid_dates": set()})
    timeline = []
    open_notional = ZERO
    open_margin = ZERO
    total_notional_created = ZERO
    for r in source:
        ident = r["id"]
        if ident in ids:
            raise ValueError("INTEGRITY_FAILURE: duplicate paper experiment ID")
        ids.add(ident)
        entered = r["created_at"]
        stake = money(r["notional_usd"])
        if stake <= 0:
            raise ValueError("INTEGRITY_FAILURE: nonpositive synthetic notional")
        total_notional_created += stake
        # Treat every recorded experiment as an independent hypothetical
        # position to estimate *required collateral*; never call this equity.
        timeline.append((entered, 1, stake))
        if r["status"] == "OPEN":
            n_open += 1
            open_notional += stake
            open_margin += stake / money(leverage)
            continue
        if r["status"] != "CLOSED":
            raise ValueError("INTEGRITY_FAILURE: unsupported paper status")
        n_closed += 1
        if r.get("late_excluded"):
            n_late += 1
        if r["market_type"] == "spot_proxy":
            n_proxy += 1
        billed = money(r["fee_round_trip_usd"])
        realized = money(r["net_pnl_usd"])
        if billed < 0:
            raise ValueError("INTEGRITY_FAILURE: negative fee")
        # Authoritative fee is recorded on the CLOSE, not recomputed from
        # assumptions about current/legacy fee schedules.
        before_fee = realized + billed
        if "signed_return_pct" in r:
            expected_gross = stake * money(r["signed_return_pct"]) / 100
            if abs(expected_gross - before_fee) > Decimal("0.0002"):
                raise ValueError("INTEGRITY_FAILURE: gross/fee/price identity")
        fee_rate = money(r.get("fee_per_side_pct", "0.05")) * 2 / 100
        if abs(billed - stake * fee_rate) > Decimal("0.0002"):
            raise ValueError("INTEGRITY_FAILURE: roundtrip fee identity")
        gross += before_fee
        fees += billed
        net += realized
        group = by_strategy[r["strategy"]]
        group["n"] += 1
        group["gross"] += before_fee
        group["fees"] += billed
        group["net"] += realized
        eligible = r["market_type"] == "perpetual" and not r.get("late_excluded", True)
        if eligible:
            group["eligible_n"] += 1
            group["valid_dates"].add(entered[:10])
        exit_event = r.get("resolved_at")
        if not exit_event:
            raise ValueError("INTEGRITY_FAILURE: missing resolved_at")
        timeline.append((exit_event, -1, stake))
    if gross - fees != net:
        raise ValueError("INTEGRITY_FAILURE: aggregate gross minus fee mismatch")
    # Equal timestamp departures are ordered before arrivals: conservative,
    # non-duplicated instantaneous notional requirement.
    active = peak = ZERO
    for when, side, stake in sorted(timeline, key=lambda e: (e[0], e[1])):
        active += side * stake
        if active < 0:
            raise ValueError("INTEGRITY_FAILURE: CLOSE precedes OPEN in time")
        peak = max(peak, active)
    if active != open_notional:
        raise ValueError("INTEGRITY_FAILURE: open-notional timeline mismatch")
    count = n_closed + n_open
    groups = {name: {
        "closed": value["n"],
        "eligible_timely_perpetual_closed": value["eligible_n"],
        "eligible_distinct_entry_utc_days": len(value["valid_dates"]),
        "gross_price_pnl_usd": usd(value["gross"]),
        "modeled_roundtrip_fees_usd": usd(value["fees"]),
        "modeled_net_pnl_usd": usd(value["net"]),
    } for name, value in sorted(by_strategy.items())}
    return {
        "policy": POLICY, "source": "v8 canonical verified event replay",
        "research_only": True, "real_account_equity_available": False,
        "do_not_use_as_account_equity": True,
        "created_experiments": count, "closed_experiments": n_closed,
        "open_experiments": n_open, "late_closes": n_late,
        "spot_proxy_closes": n_proxy,
        "gross_price_pnl_usd": usd(gross),
        "modeled_roundtrip_fees_usd": usd(fees),
        "modeled_net_pnl_usd": usd(net),
        "mean_gross_return_pct_per_close_notional": (
            str((gross / sum(money(r["notional_usd"]) for r in source
                              if r["status"] == "CLOSED") * 100).quantize(
                                  Decimal("0.000001"))) if n_closed else None),
        "total_reused_research_notional_usd": usd(total_notional_created),
        "currently_open_nominal_exposure_usd": usd(open_notional),
        "hypothetical_current_initial_margin_usd": usd(open_margin),
        "hypothetical_peak_concurrent_notional_usd": usd(peak),
        "hypothetical_peak_initial_margin_usd": usd(peak / money(leverage)),
        "hypothetical_leverage": leverage,
        "initial_margin_is_not_a_funded_wallet": True,
        "price_fee_attribution_not_a_fill_or_funding_reconciliation": True,
        "by_strategy": groups,
    }


def verify_snapshot(attribution, report):
    """A consistent report/ledger checkout must match; no silent rescaling."""
    for a, b in (("created_experiments", "created"),
                 ("closed_experiments", "closed")):
        if attribution[a] != report[b]:
            raise ValueError("INTEGRITY_FAILURE: canonical report count differs")
    for a, b in (("modeled_roundtrip_fees_usd", "total_round_trip_fees_usd"),
                 ("modeled_net_pnl_usd", "net_pnl_usd")):
        if abs(money(attribution[a]) - money(report[b])) > CENT:
            raise ValueError("INTEGRITY_FAILURE: canonical report PnL/fee mismatch")
    return True


def main():
    parser = argparse.ArgumentParser(description="READ-ONLY v8 trade/notional attribution")
    parser.add_argument("--verify-main", action="store_true",
                        help="Verify counts and P&L against tracked data/report.json")
    args = parser.parse_args()
    import engine
    records, event_count, head_hash, _ = engine.replay()
    result = compute(records, leverage=3)
    result["verified_event_count"] = event_count
    result["verified_event_hash"] = head_hash
    if args.verify_main:
        current = json.loads((Path(engine.BASE) / "data" / "report.json").read_text())
        verify_snapshot(result, current)
        result["canonical_report_reconciled"] = True
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
