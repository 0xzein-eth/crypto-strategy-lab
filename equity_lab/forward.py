"""Independent USD and IDR forward CASH PAPER wallets, replayed from EOD.

Every prior-day signal is priced at the *next actually recorded full-day OPEN*;
the assumed fill is retrospective and NEVER a broker order. Fixed 5 observed
session hold; no next-bar lookahead, over-leverage, FX conversion, shorting or
invented dividends. Hash-chained observations cannot be rewritten.
"""
import argparse
import datetime as dt
from decimal import Decimal,ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path

from equity_lab import source,universe
from stock_lab import strategies,experimental

ROOT=Path(__file__).resolve().parent.parent
STATE=ROOT/"equity_state"
ZERO="0"*64
LEGACY_VERSION="dual-equity-two-cash-wallet-eod-paper-v1"
VERSION="dual-equity-two-cash-wallet-eod-paper-v2"
HOLD_SESSIONS=5
MAX_POSITIONS=3
MAX_ENTRY_PCT=Decimal(".25")
MAX_DRAWDOWN_NEW_ENTRIES=Decimal(".10")
MAX_PRIOR_VOLUME_SHARE=Decimal(".01")
MAX_OPEN_SLIPPAGE=Decimal(".0015")
BASIC_ARMS=strategies.ARMS
RESEARCH_ARMS=experimental.ARMS
ALL_ARMS=BASIC_ARMS+RESEARCH_ARMS


def dec(v):
    if isinstance(v,bool):raise ValueError("DATA_INVALID: bool in monetary amount")
    out=Decimal(str(v))
    if not out.is_finite():raise ValueError("DATA_INVALID: nonfinite financial amount")
    return out


def money(v):
    return str(dec(v).quantize(Decimal(".01")))


def state_paths(market):
    universe.market(market,now=dt.datetime(2026,10,21,tzinfo=dt.timezone.utc))
    return (STATE/market/"observations.jsonl",
            STATE/market/"report.json",
            STATE/market/"equity_curve.json")


def snapshot(feed):
    conf=universe.market(feed["market"],
        now=dt.datetime.fromisoformat(feed["observed_at_utc"].replace("Z","+00:00")))
    if feed.get("currency")!=conf["currency"] or feed.get("no_real_orders") is not True:
        raise ValueError("MONEY_INTEGRITY: market or order flag mismatch")
    assets={}
    for symbol, data in sorted(feed["stocks"].items()):
        if data["currency"]!=conf["currency"] or data["market"]!=feed["market"]:
            raise ValueError("SOURCE_INVALID: wrong venue/currency")
        if data["last_complete_session"]!=feed["session"]:
            raise ValueError("CLOCK_INTEGRITY: asynchronous market bar")
        source.validate_history(data["history"],last_session=feed["session"])
        if source.sha(data["history"])!=data["history_sha256"]:
            raise ValueError("INTEGRITY_FAILURE: source history hash mismatch")
        bars=data["history"][-125:]
        assets[symbol]={
            "history":bars,"last_bar":bars[-1],
            "history_sha256":source.sha(bars),
            "full_source_sha256":data["history_sha256"],
            "actions":data.get("corporate_action_dates",{}),
            "signals":{**strategies.signals(bars),**experimental.signals(bars)},
        }
    if len(assets)<8:raise ValueError("DATA_INSUFFICIENT: fewer than 8 authentic ticker snapshots")
    bm=feed.get("benchmark")
    return {"schema":VERSION,"market":feed["market"],"currency":conf["currency"],
            "session":feed["session"],"observed_at_utc":feed["observed_at_utc"],
            "membership_effective":feed["membership_effective"],
            "membership_expiry":feed["membership_expiry"],
            "assets":assets,
            "benchmark_last_bar":bm["history"][-1] if bm is not None else None,
            "benchmark_symbol":conf["benchmark"],
            "benchmark_evidence_sha256":bm["history_sha256"] if bm is not None else None,
            "missing_data":feed["missing_symbols"],"real_broker_orders":0,
            "price_entries_retrospective_only":True}


def check_snapshot(tick):
    config=universe.market(
        tick["market"],now=dt.datetime.fromisoformat(
            tick["observed_at_utc"].replace("Z","+00:00")))
    if tick.get("schema") not in (LEGACY_VERSION,VERSION) or tick.get("currency")!=config["currency"] or (
        tick.get("real_broker_orders")!=0):
        raise ValueError("INTEGRITY_FAILURE: invalid wallet epoch or real broker orders")
    observer=dt.datetime.fromisoformat(tick["observed_at_utc"].replace("Z","+00:00"))
    if observer.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: timezone required")
    from zoneinfo import ZoneInfo
    local=observer.astimezone(ZoneInfo(config["timezone"]))
    day=dt.date.fromisoformat(tick["session"])
    if day.weekday()>=5 or (
            local.date()-day).days>source.MAX_MARKET_STALE_DAYS:
        raise ValueError("CLOCK_INTEGRITY: stale/invalid market session")
    if local.date()<day or (local.date()==day and
                           local.hour<config["min_complete_local_hour"]):
        raise ValueError("CLOCK_INTEGRITY: incomplete local market session")
    if tick.get("membership_effective")!=config["membership_effective"]:
        raise ValueError("MEMBERSHIP_INTEGRITY: inconsistent fixed snapshot")
    if tick.get("membership_expiry")!=config["membership_expiry"]:
        raise ValueError("MEMBERSHIP_INTEGRITY: inconsistent snapshot expiry")
    if set(tick["assets"])-set(config["symbols"]) or len(tick["assets"])<8:
        raise ValueError("INTEGRITY_FAILURE: research universe drift")
    for symbol,entry in tick["assets"].items():
        bars=entry["history"]
        if len(bars)!=125 or bars[-1]!=entry["last_bar"]:
            raise ValueError("DATA_INTEGRITY: invalid bounded OHLCV evidence")
        source.validate_history(bars,last_session=tick["session"])
        if source.sha(bars)!=entry["history_sha256"]:
            raise ValueError("INTEGRITY_FAILURE: modified source bars")
        if entry["signals"]!={**strategies.signals(bars),**experimental.signals(bars)}:
            raise ValueError("SIGNAL_INTEGRITY: rule drift or lookahead")
        if bars[-1]["date"]!=tick["session"]:
            raise ValueError("CLOCK_INTEGRITY: a ticker has stale EOD price")
    if tick["benchmark_last_bar"] is not None and tick["benchmark_last_bar"]["date"]!=tick["session"]:
        raise ValueError("BENCHMARK_INTEGRITY: mixed trading days")
    if tick["benchmark_last_bar"] is not None:
        source.validate_history([tick["benchmark_last_bar"]],last_session=tick["session"])
    return day


def read_events(market,path=None):
    path=Path(path) if path else state_paths(market)[0]
    if not path.exists():return []
    head=ZERO
    out=[]
    last=None
    last_observer=None
    for row in path.read_text(encoding="utf-8").splitlines():
        if not row:raise ValueError("INTEGRITY_FAILURE: blank observation")
        event=json.loads(row)
        body={k:v for k,v in event.items() if k!="hash"}
        if (set(body)!={"seq","prev_hash","snapshot"} or
            body["seq"]!=len(out)+1 or body["prev_hash"]!=head or
            event.get("hash")!=source.sha(body)):
            raise ValueError("INTEGRITY_FAILURE: broken journal chain")
        tick=event["snapshot"]
        if tick["market"]!=market:raise ValueError("MONEY_INTEGRITY: mixed ledger market")
        day=check_snapshot(tick)
        if last and day<=last:raise ValueError("CLOCK_INTEGRITY: repeated/reversed session")
        observer=dt.datetime.fromisoformat(tick["observed_at_utc"].replace("Z","+00:00"))
        if last_observer and observer<=last_observer:
            raise ValueError("CLOCK_INTEGRITY: reversed observation time")
        if out and out[-1]["snapshot"]["schema"]==VERSION and tick["schema"]==LEGACY_VERSION:
            raise ValueError("INTEGRITY_FAILURE: wallet policy downgrade")
        last_observer=observer
        last=day
        head=event["hash"]
        out.append(event)
    return out


def append(events,tick):
    day=check_snapshot(tick)
    if events and day<=check_snapshot(events[-1]["snapshot"]):
        raise ValueError("CLOCK_INTEGRITY: no replaying a filled daily session")
    if events:
        prev=events[-1]["snapshot"]
        if dt.datetime.fromisoformat(tick["observed_at_utc"].replace("Z","+00:00"))<=dt.datetime.fromisoformat(prev["observed_at_utc"].replace("Z","+00:00")):
            raise ValueError("CLOCK_INTEGRITY: reversed observation time")
        if prev["schema"]==VERSION and tick["schema"]==LEGACY_VERSION:
            raise ValueError("INTEGRITY_FAILURE: wallet policy downgrade")
    body={"seq":len(events)+1,
          "prev_hash":events[-1]["hash"] if events else ZERO,
          "snapshot":tick}
    return events+[{**body,"hash":source.sha(body)}]


def replay(events,market):
    """Auditable fixed-5-session one-cash-account simulation, 0 true fills."""
    conf=universe.market(market,now=dt.datetime(2026,10,21,tzinfo=dt.timezone.utc))
    currency=conf["currency"]
    cash=dec(conf["initial_paper_cash"])
    start_cash=cash
    buy_fee=dec(conf["buy_fee_pct"])/100
    sell_fee=dec(conf["sell_fee_pct"])/100
    adverse=dec(conf["adverse_impact_each_side_pct"])/100
    settle_delay=int(conf["settlement_sessions"])
    lot=int(conf["lot"])
    positions={}
    settlements=[]
    closes=[]
    curve=[]
    peak=cash
    max_dd=Decimal("0")
    eligible_opportunities=0
    denied={}
    last_source=None
    for i,event in enumerate(events):
        body={k:v for k,v in event.items() if k!="hash"}
        if (set(body)!={"seq","prev_hash","snapshot"} or event["seq"]!=i+1 or
                event["prev_hash"]!=(last_source or ZERO) or event["hash"]!=source.sha(body)):
            raise ValueError("INTEGRITY_FAILURE: invalid equity replay event")
        tick=event["snapshot"]
        if tick["market"]!=market or tick["currency"]!=currency:
            raise ValueError("MONEY_INTEGRITY: no FX cross-subsidies")
        check_snapshot(tick)
        if i:
            previous_tick=events[i-1]["snapshot"]
            if tick["session"]<=previous_tick["session"] or (
                dt.datetime.fromisoformat(tick["observed_at_utc"].replace("Z","+00:00"))<=
                dt.datetime.fromisoformat(previous_tick["observed_at_utc"].replace("Z","+00:00"))):
                raise ValueError("CLOCK_INTEGRITY: repeated/reversed equity replay")
            if previous_tick["schema"]==VERSION and tick["schema"]==LEGACY_VERSION:
                raise ValueError("INTEGRITY_FAILURE: wallet policy downgrade")
        session=tick["session"]
        legacy=tick["schema"]==LEGACY_VERSION
        # v2 freezes the OPEN budget and risk decision at the prior EOD.
        # Today's CLOSE is not available when that OPEN is assumed filled.
        prior_equity=(dec(curve[-1]["simulated_equity"])
                      if curve and curve[-1]["simulated_equity"] is not None else None)
        prior_drawdown=max_dd
        for row in list(settlements):
            if row["available_after_session_idx"]<=i:
                cash+=dec(row["amount"])
                settlements.remove(row)
        assets=tick["assets"]
        # Exits first. No recorded same-day OPEN => position remains open,
        # marked UNPRICED in equity, with further entries frozen.
        for symbol,pos in list(positions.items()):
            row=assets.get(symbol)
            if row is None:continue
            if any(pos["entry_date"]<=action<=session for action in row["actions"]):
                raise ValueError("CORPORATE_ACTION_UNMODELED: cannot assert cash/share balance")
            if i-int(pos["session_index"])<HOLD_SESSIONS:continue
            price=dec(row["last_bar"]["open"])*(1-adverse)
            gross=dec(pos["units"])*price
            fee=gross*sell_fee
            proceeds=gross-fee
            entry_cost=dec(pos["gross_cost"])
            net=proceeds-entry_cost
            closes.append({
                "id":pos["id"],"symbol":symbol,"strategy":pos["strategy"],
                "opened_at_eod":pos["entry_date"],"closed_at_eod":session,
                "units":pos["units"],"net_pnl":money(net),
                "net_return_pct":float(net/entry_cost*100),
                "modeled_entry_fee":money(pos["entry_fee"]),
                "modeled_exit_fee":money(fee),
                "exit_observed_after_daily_bar":True,
                "not_actual_broker_fill":True,
            })
            settlements.append({"amount":money(proceeds),
                                "available_after_session_idx":i+settle_delay+1})
            del positions[symbol]
        # Conservative mark on completed CLOSE. If any held ticker is
        # absent at EOD, never pretend an unchanged price.
        fully_marked=all(symbol in assets for symbol in positions)
        estimated_assets=sum(
            dec(assets[symbol]["last_bar"]["close"])*dec(pos["units"])*(1-sell_fee)
            for symbol,pos in positions.items() if symbol in assets)
        pending=sum(dec(x["amount"]) for x in settlements)
        equity=cash+pending+estimated_assets if fully_marked else None
        if equity is not None:
            peak=max(peak,equity)
            max_dd=max(max_dd,(peak-equity)/peak if peak else Decimal("0"))
        decision_equity=equity if legacy else prior_equity
        decision_drawdown=max_dd if legacy else prior_drawdown
        if equity is None or (i>0 and decision_equity is None) or decision_drawdown>=MAX_DRAWDOWN_NEW_ENTRIES:
            denied["unpriced_or_drawdown_freeze"]=denied.get("unpriced_or_drawdown_freeze",0)+1
        elif i>0 and len(positions)<MAX_POSITIONS:
            prev=events[i-1]["snapshot"]
            proposals=[]
            for symbol,record in prev["assets"].items():
                if symbol in positions or symbol not in assets:continue
                if record["last_bar"]["date"]!=prev["session"]:continue
                if any(prev["session"]<=action<=session for action in assets[symbol]["actions"]):
                    continue
                volume_bar=assets[symbol]["last_bar"] if legacy else record["last_bar"]
                if volume_bar["volume"]<10000:
                    continue
                if not legacy:
                    # A missed observer session cannot create a retroactive
                    # next-open trade from an older signal.
                    if assets[symbol]["history"][-2]["date"]!=prev["session"]:
                        denied["missed_next_session"]=denied.get("missed_next_session",0)+1
                        continue
                    from zoneinfo import ZoneInfo
                    opening=dt.datetime.combine(dt.date.fromisoformat(session),
                        dt.time(9,30) if market=="NASDAQ" else dt.time(9),
                        tzinfo=ZoneInfo(conf["timezone"]))
                    observed=dt.datetime.fromisoformat(prev["observed_at_utc"].replace("Z","+00:00"))
                    if observed>=opening:
                        denied["signal_unavailable_before_open"]=denied.get("signal_unavailable_before_open",0)+1
                        continue
                for arm,kind in record["signals"].items():
                    if kind=="BUY":
                        proposals.append((symbol,arm))
            # Frozen BEFORE outcomes: deterministic all-arm lottery.
            proposals.sort(key=lambda pair:hashlib.sha256(
                (market+":"+prev["session"]+":"+pair[0]+":"+pair[1]).encode()
                ).hexdigest())
            eligible_opportunities+=len(proposals)
            for symbol,arm in proposals:
                if symbol in positions or len(positions)>=MAX_POSITIONS:continue
                price=dec(assets[symbol]["last_bar"]["open"])*(1+adverse)
                if price<=0:continue
                old_volume=dec(prev["assets"][symbol]["last_bar"]["volume"])
                affordable=min(cash,decision_equity*MAX_ENTRY_PCT)
                budget_units=int((affordable/(price*(1+buy_fee))).to_integral_value(
                                 rounding=ROUND_FLOOR))
                volume_limit=int((old_volume*MAX_PRIOR_VOLUME_SHARE).to_integral_value(
                                 rounding=ROUND_FLOOR))
                units=(min(budget_units,volume_limit)//lot)*lot
                if units<lot:continue
                entry_fee=price*units*buy_fee
                cost=price*units+entry_fee
                if cost>cash:continue
                cash-=cost
                ident=hashlib.sha256(
                    (market+":"+session+":"+symbol+":"+arm).encode()).hexdigest()[:18]
                positions[symbol]={
                    "id":ident,"units":units,"entry_date":session,
                    "strategy":arm,"session_index":i,
                    "entry_fee":money(entry_fee),"gross_cost":money(cost),
                    "modeled_fill_price":money(price),
                }
        # Re-mark *after* hypothetical D+1 OPEN allocations. The risk
        # budget above used the prior fully observed pre-entry equity,
        # but published EOD equity must include the new holdings.
        fully_marked=all(symbol in assets for symbol in positions)
        marked_assets=sum(
            dec(assets[symbol]["last_bar"]["close"])*dec(pos["units"])*(1-sell_fee)
            for symbol,pos in positions.items() if symbol in assets)
        pending=sum(dec(x["amount"]) for x in settlements)
        equity=cash+pending+marked_assets if fully_marked else None
        if equity is not None:
            peak=max(peak,equity)
            max_dd=max(max_dd,(peak-equity)/peak if peak else Decimal("0"))
        curve.append({"session":session,"cash":money(cash),
                      "receivables":money(sum(dec(x["amount"]) for x in settlements)),
                      "simulated_equity":money(equity) if equity is not None else None,
                      "positions":len(positions),"marked_from_complete_eod":fully_marked})
        last_source=event["hash"]
    pnl=sum((dec(row["net_pnl"]) for row in closes),Decimal(0))
    wins=sum(dec(t["net_pnl"])>0 for t in closes)
    losses=sum(dec(t["net_pnl"])<0 for t in closes)
    gross_wins=sum((dec(r["net_pnl"]) for r in closes if dec(r["net_pnl"])>0),Decimal(0))
    gross_losses=-sum((dec(r["net_pnl"]) for r in closes if dec(r["net_pnl"])<0),Decimal(0))
    # Observational attribution only, not parameter tuning or winner rank.
    strategy_results={}
    for arm in ALL_ARMS:
        rows=[r for r in closes if r["strategy"]==arm]
        if not rows:continue
        gain=sum((dec(r["net_pnl"]) for r in rows if dec(r["net_pnl"])>0),Decimal(0))
        loss=-sum((dec(r["net_pnl"]) for r in rows if dec(r["net_pnl"])<0),Decimal(0))
        strategy_results[arm]={
            "closed_positions":len(rows),
            "wins":sum(dec(r["net_pnl"])>0 for r in rows),
            "losses":sum(dec(r["net_pnl"])<0 for r in rows),
            "win_rate_pct":round(100*sum(dec(r["net_pnl"])>0 for r in rows)/len(rows),4),
            "closed_pnl":money(sum((dec(r["net_pnl"]) for r in rows),Decimal(0))),
            "profit_factor":round(float(gain/loss),5) if loss else None,
            "avg_closed_return_pct":round(
                sum(r["net_return_pct"] for r in rows)/len(rows),5),
            "exploratory_not_statistically_independent":True,
        }
    equity=curve[-1]["simulated_equity"] if curve else money(start_cash)
    return {
        "schema":events[-1]["snapshot"]["schema"] if events else VERSION,
        "market":market,"currency":currency,
        "paper_only":True,"real_orders":0,
        "initial_capital":money(start_cash),"simulated_equity":equity,
        "roi_pct":(round(float((dec(equity)/start_cash-1)*100),5)
                   if equity is not None else None),
        "closed_pnl":money(pnl),
        "closed_trades":len(closes),"wins":wins,"losses":losses,
        "win_rate":(round(wins/len(closes)*100,4) if closes else None),
        "profit_factor":(round(float(gross_wins/gross_losses),5)
                         if gross_losses else None),
        "max_observed_drawdown_pct":round(float(max_dd*100),5),
        "open_positions":list(positions.values()),
        "unsettled_receivables":settlements,
        "closed_trades_detail":closes[-100:],
        "per_strategy":strategy_results,
        "observed_last_session_symbol_count":(len(events[-1]["snapshot"]["assets"]) if events else 0),
        "frozen_universe_target_count":len(conf["symbols"]),
        "genuine_complete_sessions":len(events),
        "last_market_session":events[-1]["snapshot"]["session"] if events else None,
        "last_source_hash":last_source,
        "eligible_signal_proposals_observed":eligible_opportunities,
        "denials":denied,
        "fixed_hold_trading_sessions":HOLD_SESSIONS,
        "benchmark_index_only_nontradable":conf["benchmark"],
        "currency_conversion_performed":False,
        "corporate_action_cash_dividends_not_accrued":True,
        "no_automatic_champion_or_strategy_promotion":True,
        "future_open_fills_are_retrospective_hypotheticals":True,
        "equity_curve":curve,
    }


def verify_saved(market):
    """Read-only reconciliation of source chain, report AND equity curve."""
    events=read_events(market)
    report=replay(events,market)
    curve=report.pop("equity_curve")
    event_path,report_path,curve_path=state_paths(market)
    for path,expected in ((report_path,report),(curve_path,curve)):
        if not path.is_file():
            if event_path.exists():
                raise ValueError("INTEGRITY_FAILURE: missing derived equity output: "+path.name)
        elif json.loads(path.read_text(encoding="utf-8"))!=expected:
            raise ValueError("INTEGRITY_FAILURE: derived equity output differs from replay: "+path.name)
    return events,report,curve


def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",
                         encoding="utf-8")
    os.replace(temporary,path)


def observe(market):
    # Existing hashes rechecked before any network request or new event.
    events,_,_=verify_saved(market)
    feed=source.collect(market)
    tick=snapshot(feed)
    if events and events[-1]["snapshot"]["session"]==tick["session"]:
        print(source.canonical({"status":"ALREADY_RECORDED_SESSION",
                                "market":market,"session":tick["session"]}))
        return
    # Reuse exactly the SAME authentic capture for historical diagnostics.
    # This study is never appended as prospective equity or P&L.
    output=os.environ.get("EQUITY_HISTORICAL_OUTPUT")
    if output:
        from equity_lab import research
        try:
            study=research.evaluate(market,feed["stocks"],feed["benchmark"])
        except (ValueError,RuntimeError) as exc:
            study={"schema":"dual-equity-historical-source-status-v1",
                   "market":market,"status":"NO_VALID_HISTORICAL_RESULT",
                   "source_error":type(exc).__name__+": "+str(exc)[:240],
                   "fabricated_results":0,"real_orders":0}
        dest=Path(output)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(study,indent=2,sort_keys=True,allow_nan=False)+"\n",
                        encoding="utf-8")
    updated=append(events,tick)
    report=replay(updated,market)
    event_path,report_path,curve_path=state_paths(market)
    event_path.parent.mkdir(parents=True,exist_ok=True)
    with event_path.open("a",encoding="utf-8") as stream:
        stream.write(source.canonical(updated[-1])+"\n")
        stream.flush()
        os.fsync(stream.fileno())
    curve=report.pop("equity_curve")
    atomic_json(report_path,report)
    atomic_json(curve_path,curve)
    print(source.canonical({"status":"AUTHENTIC_EOD_APPENDED",
                           "market":market,"session":tick["session"],
                           "observed_tickers":len(tick["assets"]),
                           "trades_closed":report["closed_trades"],
                           "win_rate":report["win_rate"],
                           "equity":report["simulated_equity"]}))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--market",required=True,choices=("NASDAQ","LQ45"))
    p.add_argument("--observe",action="store_true")
    p.add_argument("--verify-only",action="store_true")
    opts=p.parse_args()
    if opts.observe==opts.verify_only:
        raise ValueError("Select exactly one action")
    if opts.observe:
        observe(opts.market)
    else:
        _,report,_=verify_saved(opts.market)
        print(source.canonical(report))


if __name__=="__main__":
    main()
