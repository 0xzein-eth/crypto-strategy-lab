"""Independent IDX ordinary-cash-stock PAPER account + all-arm EOD shadows.

Only genuine observed completed daily bars and as-of signals are journalled.
Any modeled fill at NEXT session's OPEN is a RETROSPECTIVE daily-bar
assumption assessed after that next session is complete. There is NO
real-time executable quote, real order, leverage, borrow or short sale.

All account currency is IDR; nominal cash is seeded ONCE and never reset.
Sales are conservatively released on the third observed subsequent
trading session (T+2 + safety delay, NOT an official IDX calendar).
Unknown dividends, splits and provider outages are not silently erased.
"""
import argparse
import datetime as dt
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path

from stock_lab import source, strategies

ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"stock_lab_state"
EVENTS=STATE/"observations.jsonl"
REPORT=STATE/"report.json"
CURVE=STATE/"equity_curve.json"
SHADOW=STATE/"shadow_report.json"
VERSION="stock-idx-cash-EOD-paper-2026-10-20-v1"
ZERO="0"*64
START_CASH=Decimal("10000000")
LOT=100
MAX_STOCKS=3
BUY_FEE=Decimal("0.0015")   # configurable illustrative retail broker cost, not guaranteed
SELL_FEE=Decimal("0.0025")
ADVERSE_OPEN=Decimal("0.0010")  # independent 10bp fill impact assumption
MAX_TARGET_FRACTION=Decimal("0.30")
MAX_DAILY_VOLUME_SHARE=Decimal("0.01")
MAX_HOLD_SESSIONS=15
SHADOW_HORIZON_SESSIONS=5
MIN_COMPLETE_BARS=strategies.MIN_BARS


def dec(v):
    if isinstance(v,bool):raise ValueError("DATA_INVALID: financial bool")
    try:out=Decimal(str(v))
    except Exception as e:raise ValueError("DATA_INVALID: nonnumeric") from e
    if not out.is_finite():raise ValueError("DATA_INVALID: NaN/nonfinite")
    return out


def strid(v):
    return format(dec(v).quantize(Decimal("0.01")),"f")


def seal(snapshot,index,head):
    body={"seq":index,"prev_hash":head,"snapshot":snapshot}
    return {**body,"hash":source.sha(body)}


def freeze_snapshot(feed):
    if set(feed["markets"])!=set(source.SYMBOLS):
        raise ValueError("SOURCE_INVALID: all 6 frozen IDX tickers required")
    ticker_date=feed["date"]
    assets={}
    for symbol in source.SYMBOLS:
        m=feed["markets"][symbol]
        if m["provider"]!=source.PROVIDER or m["venue"]!="IDX" or m["currency"]!="IDR":
            raise ValueError("SOURCE_INVALID: wrong source currency or venue")
        if m["last_complete_session_date"]!=ticker_date:
            raise ValueError("CLOCK_INTEGRITY: non-synchronized IDX sessions")
        bars=m["history"][-90:]
        decisions=strategies.signals(bars)
        assets[symbol]={
            "provider":source.PROVIDER,"currency":"IDR","venue":"IDX",
            "bars":bars,
            "source_full_price_history_hash_sha256":m["history_sha256"],
            "declared_decisions_for_NEXT_session":decisions,
            "corporate_actions_by_ex_date":m["actions"],
            "official_exchange_broker_book_verified":False,
        }
    return {
        "version":VERSION,"source_policy":feed["source_policy"],
        "session":ticker_date,"observed_at_utc":feed["captured_at_utc"],
        "assets":assets,"cash_market_only":True,
        "broker_orders_sent":0,"execution_open_prices_retrospective":True,
    }


def validate_snapshot(tick):
    if tick.get("version")!=VERSION or set(tick.get("assets",{}))!=set(source.SYMBOLS):
        raise ValueError("INTEGRITY_FAILURE: wrong IDX cohort/schema")
    day=dt.date.fromisoformat(tick["session"])
    seen_at=dt.datetime.fromisoformat(tick["observed_at_utc"].replace("Z","+00:00"))
    if seen_at.tzinfo is None:
        raise ValueError("CLOCK_INVALID: source capture time missing timezone")
    local=seen_at.astimezone(source.WIB)
    if (local.date()<day or local.hour<source.PUBLISH_AFTER_HOUR_WIB and local.date()==day):
        raise ValueError("CLOCK_INTEGRITY: session observed before its market close")
    if tick.get("broker_orders_sent")!=0 or not tick.get("cash_market_only"):
        raise ValueError("RISK_GUARD: only cash PAPER simulation permitted")
    for symbol,row in tick["assets"].items():
        if row.get("provider")!=source.PROVIDER or row.get("venue")!="IDX" or row.get("currency")!="IDR":
            raise ValueError("INTEGRITY_FAILURE: wrong venue or denomination")
        bars=row.get("bars")
        if not isinstance(bars,list) or len(bars)<MIN_COMPLETE_BARS or len(bars)>90:
            raise ValueError("INTEGRITY_FAILURE: insufficient bounded bar evidence")
        if bars[-1]["date"]!=tick["session"]:
            raise ValueError("CLOCK_INTEGRITY: last bar differs from observed session")
        for bar in bars:
            try:
                if not isinstance(bar["date"],str) or not bar["date"]:
                    raise ValueError("DATA_INVALID: empty historical session date")
                if not all(dec(bar[k])>0 for k in ("open","high","low","close")):
                    raise ValueError("DATA_INVALID: non-positive equity price")
                if (dec(bar["volume"])<0 or
                        dec(bar["low"])>min(dec(bar["open"]),dec(bar["close"])) or
                        dec(bar["high"])<max(dec(bar["open"]),dec(bar["close"])) or
                        dec(bar["high"])<dec(bar["low"])):
                    raise ValueError("DATA_INVALID: implausible daily OHLC/volume")
            except (KeyError,TypeError) as exc:
                raise ValueError("DATA_INVALID: incomplete historical bar") from exc
        actual=strategies.signals(bars)
        if row.get("declared_decisions_for_NEXT_session")!=actual:
            raise ValueError("SIGNAL_INTEGRITY: frozen strategy output differs from candle evidence")
        if not isinstance(row.get("corporate_actions_by_ex_date"),dict):
            raise ValueError("DATA_INVALID: corporate action dates are missing")
        if not isinstance(row.get("source_full_price_history_hash_sha256"),str):
            raise ValueError("INTEGRITY_FAILURE: no source provenance hash")
    return day


def read_events(path=EVENTS):
    if not Path(path).exists():return []
    head=ZERO
    result=[]
    last_day=None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line:raise ValueError("INTEGRITY_FAILURE: blank journal row")
        event=json.loads(line)
        body={k:v for k,v in event.items() if k!="hash"}
        if (set(body)!={"seq","prev_hash","snapshot"} or
                body["seq"]!=len(result)+1 or body["prev_hash"]!=head or
                event.get("hash")!=source.sha(body)):
            raise ValueError("INTEGRITY_FAILURE: damaged stock observation chain")
        date=validate_snapshot(event["snapshot"])
        if last_day is not None and date<=last_day:
            raise ValueError("CLOCK_INTEGRITY: repeated/backdated stock session")
        last_day=date
        head=event["hash"]
        result.append(event)
    return result


def _units_to_buy(cash,open_px,volume, equity):
    px=dec(open_px)*(1+ADVERSE_OPEN)
    budget=min(cash,MAX_TARGET_FRACTION*equity)
    one_lot=LOT*px*(1+BUY_FEE)
    lots=int((budget/one_lot).to_integral_value(rounding=ROUND_FLOOR)) if one_lot>0 else 0
    volume_max=int((dec(volume)*MAX_DAILY_VOLUME_SHARE/LOT).to_integral_value(rounding=ROUND_FLOOR))
    return max(0,min(lots,volume_max))*LOT


def _price_open(book,side):
    price=dec(book["open"])
    return price*(1+ADVERSE_OPEN if side=="BUY" else 1-ADVERSE_OPEN)


def _day_action(tick,symbol):
    return tick["assets"][symbol]["corporate_actions_by_ex_date"].get(tick["session"],{})


def replay(events):
    cash=START_CASH
    unsettled=[]
    positions={}
    closed=[]
    curve=[]
    shadow_open=[]
    shadow_closed=[]
    fees=Decimal(0)
    previous=None
    prior_date=None
    head=ZERO
    peak=START_CASH
    max_dd=Decimal(0)
    opens=closes=skipped_cash=skipped_volume=0
    dividend_held_uncredited=0
    split_day_skipped=0

    def equity_from_close(tick):
        equity=cash+sum(p["proceeds"] for p in unsettled)
        for symbol,p in positions.items():
            eq=dec(tick["assets"][symbol]["bars"][-1]["close"])
            equity+=dec(p["shares"])*eq*(1-SELL_FEE)
        return equity

    for i,event in enumerate(events):
        body={k:v for k,v in event.items() if k!="hash"}
        if (event.get("seq")!=i+1 or event.get("prev_hash")!=head or
                event.get("hash")!=source.sha(body)):
            raise ValueError("INTEGRITY_FAILURE: replay event hash")
        head=event["hash"]
        tick=event["snapshot"]
        day=validate_snapshot(tick)
        if prior_date is not None and day<=prior_date:
            raise ValueError("CLOCK_INTEGRITY: non-increasing session dates")
        if previous is not None:
            for symbol in source.SYMBOLS:
                old_rows={x["date"]:x for x in previous["assets"][symbol]["bars"]}
                new_rows={x["date"]:x for x in tick["assets"][symbol]["bars"]}
                if not (set(old_rows)&set(new_rows)):
                    raise ValueError("DATA_GAP: no overlapping authentic market days")
                for historic_date in set(old_rows)&set(new_rows):
                    if old_rows[historic_date]!=new_rows[historic_date]:
                        raise ValueError("SOURCE_REVISION: previously observed daily bar changed; suspend rather than rewrite PAPER fills")
        # A capital balance from a prior CLOSE is never silently reset.
        still=[]
        for claim in unsettled:
            if i>=claim["release_session_index"]:
                cash+=claim["proceeds"]
            else:still.append(claim)
        unsettled=still

        if previous is not None:
            for symbol in source.SYMBOLS:
                actions=tick["assets"][symbol]["corporate_actions_by_ex_date"]
                # If a split occurred since last real common session, a
                # stock position cannot be valued with unchanged share count.
                for action_date,action in actions.items():
                    if prior_date.isoformat()<action_date<=day.isoformat():
                        if action.get("split") and symbol in positions:
                            raise ValueError("CORPORATE_ACTION_UNMODELED: split while holding stock")
                        if action.get("dividend") and symbol in positions:
                            dividend_held_uncredited+=1
            # Pending decisions were actually frozen AFTER the prior
            # completed day. Next-session OPEN is labeled only AFTER the
            # entire next daily bar has been received; NEVER a broker fill.
            for symbol in source.SYMBOLS:
                if symbol not in positions:continue
                p=positions[symbol]
                decision=previous["assets"][symbol]["declared_decisions_for_NEXT_session"][p["arm"]]
                old_days=i-p["entry_session_index"]
                if decision!="EXIT" and old_days<MAX_HOLD_SESSIONS:continue
                actual_px=_price_open(tick["assets"][symbol]["bars"][-1],"SELL")
                gross=actual_px*p["shares"]
                fee=gross*SELL_FEE
                proceeds=gross-fee
                fees+=fee
                unsettled.append({"proceeds":proceeds,
                                  "release_session_index":i+3,
                                  "sold_on":day.isoformat(),
                                  "T_plus_2_plus_one_session_safety":True})
                pnl=proceeds-p["total_entry_cost"]
                closed.append({
                    "symbol":symbol,"arm":p["arm"],
                    "entry_date":p["entry_date"],"exit_date":day.isoformat(),
                    "entry_approved_asof":p["entry_approved_asof"],
                    "shares":p["shares"],"lots":p["shares"]//LOT,
                    "net_price_fee_assumed_pnl_idr":strid(pnl),
                    "realised_return_pct":round(float(pnl/p["total_entry_cost"]*100),6),
                    "entry_and_exit_prices_known_only_after_entire_daily_session":True,
                    "actual_execution":False,"dividend_cash_verified":False,
                })
                del positions[symbol]
                closes+=1
            # Evaluate ALL strategy paper shadows, regardless of wallet
            # capacity. Entries and exits use authentic next future
            # session's OPEN, but are hypothetical and known ex post.
            for slot in list(shadow_open):
                if i-slot["entry_session_index"]<SHADOW_HORIZON_SESSIONS:
                    continue
                symbol=slot["symbol"]
                exit_px=_price_open(tick["assets"][symbol]["bars"][-1],"SELL")
                entry_cost=slot["entry_open_px"]*(1+BUY_FEE)
                exit_cash=exit_px*(1-SELL_FEE)
                shadow_closed.append({
                    "symbol":symbol,"arm":slot["arm"],
                    "signal_session":slot["signal_session"],
                    "hypothetical_entry_session":slot["entry_session"],
                    "hypothetical_exit_session":day.isoformat(),
                    "after_fee_and_assumed_impact_return_pct":round(
                        float((exit_cash/entry_cost-1)*100),6),
                    "cash_benchmark_return_pct":0,
                    "holding_observed_sessions":SHADOW_HORIZON_SESSIONS,
                    "real_execution":False,
                    "dividend_and_corporate_action_total_return_unverified":True,
                })
                shadow_open.remove(slot)
            for symbol in source.SYMBOLS:
                actions=_day_action(tick,symbol)
                if actions.get("split"):
                    split_day_skipped+=1
                    continue
                signals=previous["assets"][symbol]["declared_decisions_for_NEXT_session"]
                for arm in strategies.ARMS:
                    if signals[arm]=="BUY":
                        shadow_open.append({
                            "symbol":symbol,"arm":arm,
                            "entry_open_px":_price_open(tick["assets"][symbol]["bars"][-1],"BUY"),
                            "entry_session":day.isoformat(),
                            "signal_session":prior_date.isoformat(),
                            "entry_session_index":i,
                        })
                if symbol in positions or len(positions)>=MAX_STOCKS:
                    continue
                candidates=[arm for arm in strategies.ARMS if signals[arm]=="BUY"]
                if not candidates:continue
                # Choose hashed PRE-OUTCOME exploratory arm without mining
                # the recently viewed winners.
                key=hashlib.sha256(("IDX-paper-v1|"+symbol+"|"+prior_date.isoformat()).encode()).digest()
                arm=candidates[key[0]%len(candidates)]
                current=tick["assets"][symbol]["bars"][-1]
                equity_pre=equity_from_close(tick)
                n=_units_to_buy(cash,current["open"],current["volume"],equity_pre)
                if n<LOT:
                    if cash<dec(current["open"])*LOT*(1+BUY_FEE)*(1+ADVERSE_OPEN):
                        skipped_cash+=1
                    else:skipped_volume+=1
                    continue
                fill=_price_open(current,"BUY")
                gross=fill*n
                fee=gross*BUY_FEE
                total=gross+fee
                if cash<total:raise ValueError("RISK_GUARD: model overspent settled cash")
                cash-=total
                fees+=fee
                positions[symbol]={
                    "symbol":symbol,"arm":arm,"shares":n,
                    "entry_date":day.isoformat(),
                    "entry_approved_asof":prior_date.isoformat(),
                    "entry_session_index":i,
                    "total_entry_cost":total,
                }
                opens+=1

        equity=equity_from_close(tick)
        peak=max(peak,equity)
        max_dd=max(max_dd,peak-equity)
        if cash<0 or equity<0 or len(positions)>MAX_STOCKS:
            raise ValueError("RISK_GUARD: invalid funded-in-simulation account")
        curve.append({
            "session":day.isoformat(),"simulated_equity_idr":strid(equity),
            "settled_cash_idr":strid(cash),
            "unsettled_sale_cash_idr":strid(sum((x["proceeds"] for x in unsettled),Decimal(0))),
            "open_stocks":len(positions),"closed_trades":closes,
            "max_observed_drawdown_idr":strid(max_dd),
            "next_session_open_is_expost_hypothesis":True,
        })
        prior_date=day
        previous=tick
    gain=sum((dec(x["net_price_fee_assumed_pnl_idr"]) for x in closed
              if dec(x["net_price_fee_assumed_pnl_idr"])>0),Decimal(0))
    loss=-sum((dec(x["net_price_fee_assumed_pnl_idr"]) for x in closed
              if dec(x["net_price_fee_assumed_pnl_idr"])<0),Decimal(0))
    winners=sum(dec(x["net_price_fee_assumed_pnl_idr"])>0 for x in closed)
    report={
        "version":VERSION,"venue":"IDX","currency":"IDR",
        "cash_only_no_margin_or_shorts":True,"real_broker_orders":0,
        "starting_cash_idr":"10000000.00",
        "observation_sessions":len(events),"last_source_hash":head,
        "latest_observed_complete_session":curve[-1]["session"] if curve else None,
        "latest_simulated_equity_idr":curve[-1]["simulated_equity_idr"] if curve else "10000000.00",
        "latest_settled_cash_idr":curve[-1]["settled_cash_idr"] if curve else "10000000.00",
        "max_observed_drawdown_idr":strid(max_dd),
        "positions_opened":opens,"positions_closed":closes,
        "positions_active":len(positions),
        "win_rate_closed":round(winners/closes,5) if closes else None,
        "profit_factor_closed":round(float(gain/loss),5) if loss>0 else None,
        "modeled_total_broker_fees_idr":strid(fees),
        "capital_unavailable_until_T2_plus_safety_session":True,
        "unsettled_sale_claims":len(unsettled),
        "denied_missing_cash":skipped_cash,
        "denied_insufficient_real_bar_volume":skipped_volume,
        "uncredited_dividend_events_for_held_stocks":dividend_held_uncredited,
        "split_day_entries_skipped":split_day_skipped,
        "open_positions_detail":[
            {"symbol":s,"arm":p["arm"],"shares":p["shares"],"lots":p["shares"]//LOT,
             "entry_session":p["entry_date"]}
            for s,p in sorted(positions.items())],
        "closed_positions_detail":closed,
        "one_day_later_OPEN_is_observed_only_after_the_daily_bar":True,
        "not_a_tradable_fill_or_real_time_order":True,
        "no_bid_ask_spread_or_verified_broker_fills":True,
        "dividends_splits_and_total_return_not_fully_modeled":True,
        "financial_edge_after_all_costs_unproven":True,
        "eligible_for_live_deployment":False,
    }
    arms={}
    for arm in strategies.ARMS:
        rows=[r for r in shadow_closed if r["arm"]==arm]
        days={r["signal_session"] for r in rows}
        values=[r["after_fee_and_assumed_impact_return_pct"] for r in rows]
        arms[arm]={
            "prospective_fixed_five_session_closed_shadow_cohorts":len(rows),
            "entry_utc_calendar_dates_not_independent_trials":len(days),
            "win_rate":round(sum(v>0 for v in values)/len(values),5) if values else None,
            "mean_price_fee_impact_stress_return_pct":round(sum(values)/len(values),6) if values else None,
            "independent_untouched_validation_completed":False,
            "eligible_for_live":False,
        }
    shadow_report={
        "version":VERSION,"source_hash":head,"observations":len(events),
        "all_arms":list(strategies.ARMS),"per_arm":arms,
        "closed_rows":shadow_closed,
        "unresolved_future_horizon":len(shadow_open),
        "cash_control_is_zero_yield_and_not_market_beta_adjusted":True,
        "missing_dividend_total_returns_and_unmeasured_execution":True,
        "historical_bars_before_first_journal_are_features_not_forward_outcomes":True,
        "no_strategy_auto_promotion":True,"real_orders":0,
    }
    return report,curve,shadow_report


def observe(feed,old):
    snapshot=freeze_snapshot(feed)
    validate_snapshot(snapshot)
    if old and snapshot["session"]<=old[-1]["snapshot"]["session"]:
        if snapshot["session"]==old[-1]["snapshot"]["session"]:
            for sym in source.SYMBOLS:
                previous_bar=old[-1]["snapshot"]["assets"][sym]["bars"][-1]
                newly_received=snapshot["assets"][sym]["bars"][-1]
                if previous_bar!=newly_received:
                    raise ValueError("SOURCE_REVISION: duplicate-session EOD source bar revised; do not silently accept")
        return None
    row=seal(snapshot,len(old)+1,old[-1]["hash"] if old else ZERO)
    return row,*replay([*old,row])


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)


def main():
    p=argparse.ArgumentParser(description="IDX long-only cash PAPER EOD independent research")
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--observe",action="store_true")
    g.add_argument("--verify-only",action="store_true")
    args=p.parse_args()
    old=read_events()
    report,curve,shadow=replay(old)
    if args.verify_only:
        for dest,expected in ((REPORT,report),(CURVE,curve),(SHADOW,shadow)):
            if dest.exists() and json.loads(dest.read_text(encoding="utf-8"))!=expected:
                raise ValueError("INTEGRITY_FAILURE: stock report not reproducible from hash-chain")
        print(source.canonical({"observations":len(old),
                                "latest_complete_session":report["latest_observed_complete_session"],
                                "equity_idr":report["latest_simulated_equity_idr"],
                                "real_orders":0}))
        return
    feed=source.capture()
    result=observe(feed,old)
    if result is None:
        print(source.canonical({"skipped":"already observed latest genuinely completed IDX EOD session",
                                "last_hash":old[-1]["hash"],"real_orders":0}))
        return
    event,report,curve,shadow=result
    STATE.mkdir(parents=True,exist_ok=True)
    with EVENTS.open("a",encoding="utf-8") as out:
        out.write(source.canonical(event)+"\n")
        out.flush()
        os.fsync(out.fileno())
    atomic(REPORT,report)
    atomic(CURVE,curve)
    atomic(SHADOW,shadow)
    print(source.canonical({
        "session":feed["date"],"equity_idr":report["latest_simulated_equity_idr"],
        "positions_opened":report["positions_opened"],
        "closed":report["positions_closed"],"observations":report["observation_sessions"],
        "hash":event["hash"],"real_orders":0,
    }))


if __name__=="__main__":
    main()
