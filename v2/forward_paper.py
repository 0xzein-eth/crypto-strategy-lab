"""Durable, deterministic, strictly PAPER-ONLY one-wallet forward experiment.

Journal stores *actual observed exchange book snapshots* and confirmed-candle
signals, not fictitious historical fills. Each run replays ALL journal ticks
to reconstruct a single funded-in-simulation account: no silent cash reset.
The v8 SHA256 ledger is NEVER read for allocations nor modified.

Two exploratory, previously INSPECTED signals are examined (NOT champions).
All modeled fills are hypothetical top-of-book crossings; funding coverage
is UNKNOWN, so equity is explicitly *before unverified funding and impact*.
"""
import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from v2.paper_portfolio import D, PaperWallet, OrderRejected, iso, ts, verify_quote
from v2.cost_gate import break_even

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "v2_state"
OBSERVATIONS = STATE / "observations.jsonl"
REPORT = STATE / "report.json"
CURVE = STATE / "equity_curve.json"
VERSION = "v2-onewallet-observer-2026-10-20-v1"
HASH_ZERO = "0" * 64
SYMBOLS = ("BTC", "ETH", "SOL")
STRATEGIES = ("FB-v3", "VWAP-v1")  # previously inspected, hypothesis only
HORIZON = dt.timedelta(hours=4)
SLOT_SECONDS = 1800
MAX_POSITIONS = 2
NOTIONAL_PER_ENTRY = Decimal("200")
INITIAL_WALLET = Decimal("1000")
MAX_ALLOWED_SPREAD_BPS = Decimal("15")
VOLATILITY_MULTIPLE = Decimal("3")  # ATR feasibility heuristic, NOT forecast
UTC = dt.timezone.utc


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def seal(tick, seq, prev):
    base = {"seq": seq, "prev_hash": prev, "tick": tick}
    return {**base, "hash": sha(base)}


def read_events(path=OBSERVATIONS):
    """Verify entire append-only observation chain before any new input."""
    path = Path(path)
    if not path.exists():
        return []
    events = []
    head = HASH_ZERO
    last_time = None
    last_slot = -1
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                raise ValueError("INTEGRITY_FAILURE: blank observation event")
            event = json.loads(line)
            body = {k: v for k, v in event.items() if k != "hash"}
            if (event.get("seq") != len(events)+1 or
                    event.get("prev_hash") != head or
                    event.get("hash") != sha(body) or
                    set(body) != {"seq", "prev_hash", "tick"}):
                raise ValueError("INTEGRITY_FAILURE: v2 observation hash / sequence")
            tick = event["tick"]
            if not isinstance(tick, dict) or tick.get("version") != VERSION:
                raise ValueError("INTEGRITY_FAILURE: unknown v2 observer policy")
            moment = ts(tick["observed_at"])
            slot = int(moment.timestamp()) // SLOT_SECONDS
            if (last_time is not None and moment <= last_time) or slot <= last_slot:
                raise ValueError("INTEGRITY_FAILURE: duplicate/out-of-order observation slot")
            last_time, last_slot = moment, slot
            events.append(event)
            head = event["hash"]
    return events


def validate_tick(tick):
    if not isinstance(tick, dict) or tick.get("version") != VERSION:
        raise ValueError("INTEGRITY_FAILURE: unknown forward observer tick")
    now = ts(tick["observed_at"])
    if set(tick.get("books", {})) != set(SYMBOLS) or set(tick.get("signals", {})) != set(SYMBOLS):
        raise ValueError("SOURCE_UNAVAILABLE: must observe all 3 markets for a valid equity mark")
    for symbol in SYMBOLS:
        verify_quote(tick["books"][symbol], symbol=symbol, now=now)
        offered = tick["signals"][symbol]
        if not isinstance(offered, list) or len(offered) > 25:
            raise ValueError("SIGNAL_INVALID: unbounded / missing confirmed signal list")
        distinct = set()
        for row in offered:
            if not isinstance(row, dict) or row.get("strategy") not in STRATEGIES or row.get("side") not in ("LONG", "SHORT"):
                raise ValueError("SIGNAL_INVALID: arm not preregistered")
            ev = row.get("evidence", {})
            if not isinstance(ev, dict) or ev.get("bar_span") != "15m confirmed OKX USDT-SWAP":
                raise ValueError("SIGNAL_INVALID: not an authentic completed 15m candle")
            bar_start = ts(ev["bar_time"])
            bar_end = bar_start + dt.timedelta(minutes=15)
            if (bar_start.minute % 15 or bar_start.second or bar_start.microsecond or
                    not 0 <= (now - bar_end).total_seconds() <= 25*60 or
                    bar_end > ts(tick["books"][symbol]["observed_at"])):
                raise ValueError("CLOCK_INTEGRITY: forming, future, stale or misaligned signal")
            atr, close = D(ev.get("atr14")), D(ev.get("last_close"))
            if atr <= 0 or close <= 0:
                raise ValueError("SIGNAL_INVALID: ATR/price")
            ident = (row["strategy"], row["side"], ev["bar_time"])
            if ident in distinct:
                raise ValueError("SIGNAL_INVALID: duplicate same-bar hypothesis")
            distinct.add(ident)
    return now


def replay(events):
    """Derive wallet/equity deterministically from ONLY verified future inputs.

    If inputs are malformed, do not skip/reinterpret them: fail the run.
    v2's funding is deliberately unreconciled; do NOT label this as
    after-all-costs or use it to approve strategy trading.
    """
    wallet = PaperWallet(balance_usdt=INITIAL_WALLET, max_leverage=2,
                         max_gross_equity_multiple="1.25")
    active = {}
    seen = set()
    curve = []
    opened = closed = late = liquidated = attempted = 0
    closed_records = []
    vetoes = {}
    last_slot = -1
    previous = HASH_ZERO

    def veto(reason):
        vetoes[reason] = vetoes.get(reason, 0) + 1

    for index, event in enumerate(events, 1):
        if (event.get("seq") != index or event.get("prev_hash") != previous or
                event.get("hash") != sha({k: v for k, v in event.items() if k != "hash"})):
            raise ValueError("INTEGRITY_FAILURE: invalid replay event")
        previous = event["hash"]
        tick = event["tick"]
        now = validate_tick(tick)
        slot = int(now.timestamp()) // SLOT_SECONDS
        if slot <= last_slot:
            raise ValueError("CLOCK_INTEGRITY: non-increasing observation slots")
        last_slot = slot
        books = tick["books"]
        marked = wallet.mark(books, now)
        forced = marked["liquidation_required"]
        # Liquidate if actually marked maintenance breached; otherwise
        # evaluate predeclared fixed 4h exits at FIRST NEXT REAL observation.
        for ident in sorted(list(active)):
            position = active[ident]
            if forced or now >= ts(position["evaluate_at"]):
                condition = wallet.snapshot(now)
                mandatory = condition["liquidation_required"]
                if not forced and now < ts(position["evaluate_at"]):
                    continue
                outcome = wallet.close(ident, books[position["symbol"]], now,
                                       forced_liquidation=mandatory)
                closed += 1
                if forced:
                    liquidated += 1
                delayed = (now - ts(position["evaluate_at"])).total_seconds() > 1800
                if delayed:
                    late += 1
                closed_records.append({
                    "id":ident, "symbol":position["symbol"],
                    "strategy":position["strategy"],
                    "side":position["side"],
                    "opened_at":position["opened_at"],
                    "fixed_evaluate_at":position["evaluate_at"],
                    "actually_closed_at":iso(now),
                    "late_excluded_from_timely_study":delayed,
                    "forced_liquidation_or_account_emergency":bool(forced),
                    "price_pnl_usdt":outcome["price_pnl_usdt"],
                    "entry_fee_usdt":outcome["entry_fee_usdt"],
                    "exit_fee_usdt":outcome["exit_fee_usdt"],
                    "net_after_bidask_and_fee_before_unverified_funding_usdt":
                        outcome["net_pnl_usdt"],
                })
                del active[ident]
        # No new entries are opened during a tick that encountered a margin
        # breach; otherwise the investor could instantly re-leverage after
        # a forced-losing liquidation.
        if not forced:
            for symbol in SYMBOLS:
                choices = sorted(tick["signals"][symbol],
                                 key=lambda x:(STRATEGIES.index(x["strategy"]),x["side"]))
                if not choices:
                    continue
                # All candidate signals are registered as seen, including
                # rejected ones; repeated observations of same 15m candle
                # must never increase experimentation budget.
                available = []
                for sig in choices:
                    evidence = sig["evidence"]
                    key = (symbol, sig["strategy"], sig["side"], evidence["bar_time"])
                    if key not in seen:
                        seen.add(key)
                        available.append(sig)
                if not available:
                    continue
                attempted += 1
                if any(p["symbol"] == symbol for p in active.values()):
                    veto("one_position_per_symbol")
                    continue
                if len(active) >= MAX_POSITIONS:
                    veto("two_position_wallet_cap")
                    continue
                selected = available[0]
                side = selected["side"]
                quote = books[symbol]
                costs = break_even(quote, now, symbol, side)
                if D(costs["quoted_spread_bps"]) > MAX_ALLOWED_SPREAD_BPS:
                    veto("spread_exceeds_research_cap")
                    continue
                ev = selected["evidence"]
                # ATR is a *scale of prior volatility*, not a prediction.
                # This rule only screens patently cost-infeasible market
                # movement; no model or untested forecast is implied.
                exploratory_volatility_pct = D(ev["atr14"])/D(ev["last_close"])*100*VOLATILITY_MULTIPLE
                if exploratory_volatility_pct < D(costs["minimum_favorable_mid_move_pct"]):
                    veto("atr_movement_scale_below_cost_hurdle")
                    continue
                ident = "V2-%s-%s-%s"%(slot,symbol,selected["strategy"])
                try:
                    wallet.open(ident, symbol, side, NOTIONAL_PER_ENTRY,
                                quote, now, allow_partial=False)
                except OrderRejected as exc:
                    veto(str(exc).split(":")[0])
                    continue
                active[ident] = {
                    "position_id": ident, "symbol": symbol, "side": side,
                    "strategy": selected["strategy"], "opened_at": iso(now),
                    "evaluate_at": iso(now+HORIZON),
                    "frozen_signal_hash": sha(selected),
                    "cost_hurdle_pct": str(costs["minimum_favorable_mid_move_pct"]),
                    "atr_scale_pct_not_forecast": str(exploratory_volatility_pct),
                    "model_has_proven_predictive_edge": False,
                }
                opened += 1
        snapshot = wallet.snapshot(now)
        curve.append({
            "observed_at": iso(now), "slot": slot,
            "cash_usdt": snapshot["cash_usdt"],
            "equity_usdt": snapshot["equity_usdt"],
            "unrealized_exit_side_pnl_usdt": snapshot["unrealized_exit_side_pnl_usdt"],
            "gross_opened_notional_usdt": snapshot["gross_opened_notional_usdt"],
            "observed_max_drawdown_usdt": snapshot["observed_max_drawdown_usdt"],
            "positions_open": snapshot["open_positions"],
            "positions_closed": snapshot["closed_positions"],
        })

    if curve:
        moment = ts(curve[-1]["observed_at"])
        final = wallet.snapshot(moment)
    else:
        # First bootstrap when no feed has been observed: NO fake mark.
        final = {
            "schema": "v2-no-observations", "initial_cash_usdt":str(INITIAL_WALLET),
            "cash_usdt":str(INITIAL_WALLET), "equity_usdt":str(INITIAL_WALLET),
            "open_positions":0, "closed_positions":0,"total_fees_usdt":"0.00",
            "observed_max_drawdown_usdt":"0.00","real_order_submissions":0,
            "journal":wallet.audit_events(),
        }
    wins = sum(D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"]) > 0
               for r in closed_records)
    losses = sum(D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"]) < 0
                 for r in closed_records)
    gross_gain = sum((D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"])
                      for r in closed_records
                      if D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"]) > 0),
                     Decimal(0))
    gross_loss = -sum((D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"])
                       for r in closed_records
                       if D(r["net_after_bidask_and_fee_before_unverified_funding_usdt"]) < 0),
                      Decimal(0))
    report = {
        "version": VERSION, "paper_only": True, "real_order_submissions":0,
        "research_status":"EXPLORATORY_FORWARD_PLUMBING_NOT_VALIDATED_ALPHA",
        "observations":len(events), "last_tick_hash":previous,
        "latest_real_observation_utc":curve[-1]["observed_at"] if curve else None,
        "initial_simulated_capital_usdt":"1000.00",
        "current_simulated_cash_usdt":final["cash_usdt"],
        "current_simulated_equity_usdt":final["equity_usdt"],
        "observed_max_drawdown_usdt":final["observed_max_drawdown_usdt"],
        "simulated_fee_total_usdt":final["total_fees_usdt"],
        "open_positions":len(active), "closed_positions":closed,
        "prospective_paper_opens":opened,
        "closed_paper_win_count":wins, "closed_paper_loss_count":losses,
        "observed_closed_win_rate":round(wins/closed,4) if closed else None,
        "observed_closed_profit_factor_fee_bidask_only":(
            round(float(gross_gain/gross_loss),4) if gross_loss>0 else None),
        "net_equity_change_from_initial_pct_before_unverified_funding":round(
            float((D(final["equity_usdt"])/INITIAL_WALLET-1)*100),5),
        "recorded_closed_outcomes":closed_records,
        "fixed_4h_exits_observed_late_over_30min":late,
        "estimated_margin_liquidations":liquidated,
        "signal_opportunities_inspected":attempted,
        "research_veto_counts":vetoes,
        "active_positions":sorted(active.values(),key=lambda x:x["position_id"]),
        "account_journal":final["journal"],
        "funding_source_complete":False,
        "after_all_costs_performance_proven":False,
        "funding_pnl_not_assumed_zero_to_be_real":True,
        "simulated_wallet_excludes_unverified_funding":True,
        "future_slippage_and_market_impact_unverified":True,
        "candidate_arms":list(STRATEGIES),
        "candidates_already_inspected_not_pristine_holdout":True,
        "simulated_book_crossings_are_not_executed_orders":True,
        "not_a_trading_recommendation":True,
        "legacy_v8_ledger_unchanged":True,
        "equity_curve_observations":len(curve),
    }
    if final["journal"]["verified_events"] != opened + closed:
        raise ValueError("INTEGRITY_FAILURE: wallet event count mismatch")
    if D(report["current_simulated_equity_usdt"]) < Decimal("-10000"):
        raise ValueError("RISK_GUARD: unexpected account mark")
    return report, curve


def evaluate_candidate(existing, tick):
    validate_tick(tick)
    now = ts(tick["observed_at"])
    if existing and int(ts(existing[-1]["tick"]["observed_at"]).timestamp()) // SLOT_SECONDS >= int(now.timestamp()) // SLOT_SECONDS:
        raise ValueError("CLOCK_INTEGRITY: already observed this 30-minute slot")
    new = seal(tick, len(existing)+1,
               existing[-1]["hash"] if existing else HASH_ZERO)
    report, curve = replay([*existing,new])
    return new, report, curve


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+"\n",
                    encoding="utf-8")
    os.replace(temp,path)


def main():
    parser = argparse.ArgumentParser(description="v2 PUBLIC MARKET READS + ONLY PAPER WALLET")
    parser.add_argument("--observe",action="store_true",
                        help="fetch genuine current public OKX books and completed candles")
    parser.add_argument("--verify-only",action="store_true")
    args = parser.parse_args()
    if args.observe and args.verify_only:
        parser.error("choose one mode")
    existing = read_events()
    old_report, old_curve = replay(existing)
    if args.verify_only:
        if REPORT.exists():
            actual = json.loads(REPORT.read_text(encoding="utf-8"))
            if actual != old_report:
                raise ValueError("INTEGRITY_FAILURE: derived v2 report no longer matches source")
        if CURVE.exists():
            actual = json.loads(CURVE.read_text(encoding="utf-8"))
            if actual != old_curve:
                raise ValueError("INTEGRITY_FAILURE: derived equity curve no longer matches source")
        print(canonical({"verified_observations":len(existing),
                         "last_hash":old_report["last_tick_hash"],
                         "equity_usdt":old_report["current_simulated_equity_usdt"],
                         "no_orders":True}))
        return
    if not args.observe:
        parser.error("must explicitly request --observe, otherwise use --verify-only")
    from v2.okx_observer_source import current_tick
    tick = current_tick()
    if existing and int(ts(existing[-1]["tick"]["observed_at"]).timestamp()) // SLOT_SECONDS >= int(ts(tick["observed_at"]).timestamp()) // SLOT_SECONDS:
        print(canonical({"skipped":"already observed this 30m slot",
                         "last_hash":old_report["last_tick_hash"]}))
        return
    new, report, curve = evaluate_candidate(existing,tick)
    STATE.mkdir(parents=True, exist_ok=True)
    with OBSERVATIONS.open("a",encoding="utf-8") as handle:
        handle.write(canonical(new)+"\n")
        handle.flush()
        os.fsync(handle.fileno())
    atomic_json(REPORT,report)
    atomic_json(CURVE,curve)
    print(canonical({"observed_at":tick["observed_at"],
                     "equity_usdt":report["current_simulated_equity_usdt"],
                     "closed_positions":report["closed_positions"],
                     "opened_positions":report["prospective_paper_opens"],
                     "last_hash":new["hash"],"no_orders":True}))


if __name__ == "__main__":
    main()
