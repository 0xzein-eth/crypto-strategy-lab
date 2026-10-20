"""Bounded, replayable 15m USDT-SWAP history warehouse (historical ONLY).

Separately retains exchange-verified candles and *settled* funding. Seed
prices from the existing authenticated v9 cache if available; NEVER from
v8 fills or imagined bars. Missing settled funding never becomes a zero
rate. GitHub best-effort batch jobs extend backwards in real API pages.

No credentials, orders, signal selection, portfolio changes or ledger edits.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

from research_v9 import history as prices
from research_v9 import funding as funding_src
from v2.data_contract import digest

ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = ROOT / "v2_history"
SCHEMA = "v2-historical-warehouse-2026-10-20-v1"
SYMBOLS = ("BTC", "ETH", "SOL")
UTC = dt.timezone.utc
BARS_PER_DAY = 96
TARGET_DAYS = 730
MAX_TARGET_DAYS = 1095


def path_for(symbol, kind):
    if symbol not in SYMBOLS or kind not in ("candles", "settled_funding"):
        raise ValueError("INTEGRITY_FAILURE: unsupported historical instrument/series")
    return WAREHOUSE / (symbol + "-" + kind + ".json.gz")


def _validate(kind, rows):
    if kind == "candles":
        return prices.validate_series(rows, min_bars=1)
    return funding_src.validate_rates(rows)


def load(symbol, kind):
    path=path_for(symbol,kind)
    if not path.exists():
        return []
    item=json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    if (item.get("schema")!=SCHEMA or item.get("instrument")!=symbol+"-USDT-SWAP"
            or item.get("venue")!="okx-swap" or item.get("kind")!=kind
            or item.get("hash_sha256")!=digest(item.get("rows"))):
        raise ValueError("INTEGRITY_FAILURE: verified warehouse hash/source mismatch")
    rows=item["rows"]
    _validate(kind,rows)
    return rows


def save(symbol, kind, rows):
    _validate(kind,rows)
    path=path_for(symbol,kind)
    path.parent.mkdir(parents=True,exist_ok=True)
    payload={"schema":SCHEMA,"venue":"okx-swap",
             "instrument":symbol+"-USDT-SWAP","kind":kind,
             "rows":rows,"hash_sha256":digest(rows)}
    content=json.dumps(payload,sort_keys=True,separators=(",",":"),
                       allow_nan=False).encode("utf-8")
    temp=path.with_suffix(".tmp")
    temp.write_bytes(gzip.compress(content,compresslevel=9,mtime=0))
    os.replace(temp,path)


def extend_prices(symbol, *, now, target_days=TARGET_DAYS, newest_pages=12,
                  backfill_pages=40, page=None, seed=None,
                  sleeper=time.sleep):
    """Append authentic *newer* data and extend authentic *older* data.

    Existing caches with a missing interval fail; a gap is never zeroed or
    synthetically interpolated. Incremental run resumes at the same real
    oldest candle; a page that does not advance must not be retried forever.
    """
    if (now.tzinfo is None or not 30<=target_days<=MAX_TARGET_DAYS or
            not 1<=newest_pages<=60 or not 0<=backfill_pages<=60):
        raise ValueError("DATA_INVALID: unsafe data backfill budget/time")
    target=target_days*BARS_PER_DAY
    page=page or (lambda symbol, after:prices.okx_page(symbol,after=after))
    existing=load(symbol,"candles")
    seeded=False
    if not existing:
        candidate=(prices.load_cache(symbol) if seed is None else seed(symbol))
        if candidate:
            prices.validate_series(candidate)
            existing=candidate[-target:]
            seeded=True
    fresh={}
    cursor=None
    last_cursor=None
    for i in range(newest_pages):
        batch=prices.parse_confirmed(page(symbol,cursor),now=now)
        if not batch:
            if not fresh:
                raise ValueError("DATA_UNAVAILABLE: no actual recently confirmed OHLCV")
            break
        if last_cursor is not None and batch[-1][0]>=last_cursor:
            raise ValueError("DATA_INVALID: OHLCV cursor did not progress")
        for b in batch:
            prev=fresh.get(b[0])
            if prev is not None and prev!=b:
                raise ValueError("INTEGRITY_FAILURE: contradictory page overlap")
            fresh[b[0]]=b
        cursor=batch[0][0]
        if existing and cursor<=existing[-1][0]:
            break
        last_cursor=cursor
        if i+1<newest_pages:
            sleeper(.11)
    incoming=[fresh[k] for k in sorted(fresh)]
    if existing:
        updated=prices.merge_series(existing,incoming,max_bars=target)
    else:
        updated=prices.validate_series(incoming,min_bars=2)[-target:]
    older_added=0
    for _ in range(backfill_pages):
        if len(updated)>=target:
            break
        before=updated[0][0]
        batch=prices.parse_confirmed(page(symbol,before),now=now)
        if not batch:
            break
        if batch[-1][0]>=before:
            raise ValueError("DATA_INVALID: older OHLCV page failed cursor monotonicity")
        next_rows=prices.extend_older(updated,batch,max_bars=target)
        if next_rows[0][0]>=before:
            raise ValueError("DATA_INVALID: no historic extension")
        older_added+=len(next_rows)-len(updated)
        updated=next_rows
        sleeper(.11)
    end=updated[-1][0]+prices.BAR_MS
    age=(now.timestamp()*1000-end)/1000
    if age>3*3600 or age< -20:
        raise ValueError("DATA_STALE: newest archived candle not truly current")
    prices.validate_series(updated)
    save(symbol,"candles",updated)
    return updated,{"legacy_verified_seed_used":seeded,
                    "newer_confirmed_bars_seen":len(incoming),
                    "older_confirmed_bars_added":older_added,
                    "price_windows_are_genuinely_contiguous":True}


def extend_funding(symbol, *, now, earliest_bar_ms, newer_pages=3,
                   backfill_pages=20, page=None, seed=None,
                   sleeper=time.sleep):
    """Use actual settled funding only; never invent nonexistent settlements."""
    if not 1<=newer_pages<=60 or not 0<=backfill_pages<=60:
        raise ValueError("invalid funding page budget")
    page=page or (lambda symbol,after:funding_src.fetch_page(symbol,after=after))
    existing=load(symbol,"settled_funding")
    seeded=False
    if not existing:
        prior=funding_src.load_cache(symbol) if seed is None else seed(symbol)
        if prior:
            funding_src.validate_rates(prior)
            existing=list(prior)
            seeded=True
    observed={e[0]:e for e in existing}
    cursor=None
    last_cursor=None
    for i in range(newer_pages):
        batch=funding_src.parse_settled(page(symbol,cursor),symbol,now=now)
        if not batch:
            if i==0 and not existing:
                raise ValueError("DATA_UNAVAILABLE: exchange has no settled funding")
            break
        if last_cursor is not None and batch[-1][0]>=last_cursor:
            raise ValueError("DATA_INVALID: funding cursor did not advance")
        for event in batch:
            if event[0] in observed and observed[event[0]]!=event:
                raise ValueError("INTEGRITY_FAILURE: settled funding revision")
            observed[event[0]]=event
        cursor=batch[0][0]
        if existing and cursor<=existing[-1][0]:
            break
        last_cursor=cursor
        if i+1<newer_pages:
            sleeper(.11)
    while_step=min(observed) if observed else cursor
    for _ in range(backfill_pages):
        if while_step is None or while_step<=earliest_bar_ms:
            break
        batch=funding_src.parse_settled(page(symbol,while_step),symbol,now=now)
        if not batch:
            break
        if batch[-1][0]>=while_step:
            raise ValueError("DATA_INVALID: older settled funding did not advance")
        for event in batch:
            if event[0] in observed and observed[event[0]]!=event:
                raise ValueError("INTEGRITY_FAILURE: contradictory funding revision")
            observed[event[0]]=event
        while_step=batch[0][0]
        sleeper(.11)
    result=[observed[k] for k in sorted(observed)]
    funding_src.validate_rates(result)
    save(symbol,"settled_funding",result)
    return result,{"legacy_verified_seed_used":seeded,
                   "historical_rates_observed":len(result),
                   "rates_are_only_real_settled_events":True}


def build(symbols=SYMBOLS, *, now=None, target_days=TARGET_DAYS,
          price_backfill_pages=40,funding_backfill_pages=20,
          price_page=None,funding_page=None,price_seed=None,funding_seed=None,
          sleeper=time.sleep):
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("CLOCK_INVALID: UTC-aware fetch time required")
    if not symbols or len(set(symbols))!=len(symbols) or any(s not in SYMBOLS for s in symbols):
        raise ValueError("invalid exact market universe")
    results={}
    for symbol in symbols:
        rows,pinfo=extend_prices(
            symbol,now=now,target_days=target_days,
            backfill_pages=price_backfill_pages,page=price_page,
            seed=price_seed,sleeper=sleeper)
        start,end=rows[0][0],rows[-1][0]+prices.BAR_MS
        funding_error=None
        try:
            rates,finfo=extend_funding(
                symbol,now=now,earliest_bar_ms=start,
                backfill_pages=funding_backfill_pages,
                page=funding_page,seed=funding_seed,sleeper=sleeper)
        except (ValueError,OSError,TimeoutError) as exc:
            # Do NOT mask the funding failure as zero economic funding.
            rates=load(symbol,"settled_funding")
            finfo={"historical_rates_observed":len(rates),
                   "funding_error_type":type(exc).__name__,
                   "funding_error":str(exc)[:160]}
            funding_error=type(exc).__name__
        complete=funding_src.coverage(rates,start,end)
        results[symbol]={
            "venue":"okx-swap","instrument":symbol+"-USDT-SWAP",
            "price_hash_sha256":digest(rows),
            "confirmed_bars":len(rows),
            "historical_start_utc":dt.datetime.fromtimestamp(start/1000,UTC).isoformat(),
            "historical_end_exclusive_utc":dt.datetime.fromtimestamp(end/1000,UTC).isoformat(),
            "actual_verified_history_days":round(len(rows)/BARS_PER_DAY,4),
            "one_year_price_verified":len(rows)>=365*BARS_PER_DAY,
            "two_year_price_verified":len(rows)>=730*BARS_PER_DAY,
            "three_year_price_verified":len(rows)>=1095*BARS_PER_DAY,
            "funding_events":len(rates),
            "funding_events_sha256":digest(rates),
            "settled_funding_full_price_window":bool(complete),
            "funding_missing_cannot_be_assumed_zero":not complete,
            "funding_fetch_failed":funding_error is not None,
            "price_ingestion":pinfo,"funding_ingestion":finfo,
        }
    report={
        "schema":SCHEMA,"research_only":True,"never_submits_orders":True,
        "asof_utc":now.astimezone(UTC).isoformat(),
        "target_price_window_days":target_days,"symbols":results,
        "multi_year_goals_not_inferred_when_short":True,
        "source_coverage_is_not_liquidity_or_fill_validation":True,
    }
    WAREHOUSE.mkdir(parents=True,exist_ok=True)
    tmp=WAREHOUSE/"manifest.tmp"
    tmp.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+"\n",
                   encoding="utf-8")
    os.replace(tmp,WAREHOUSE/"manifest.json")
    return report


def main():
    parser=argparse.ArgumentParser(description="Authentic-only progressive 2y OKX historical warehouse")
    parser.add_argument("--symbols",nargs="+",default=list(SYMBOLS),choices=SYMBOLS)
    parser.add_argument("--target-days",type=int,default=TARGET_DAYS)
    parser.add_argument("--price-backfill-pages",type=int,default=40)
    parser.add_argument("--funding-backfill-pages",type=int,default=20)
    args=parser.parse_args()
    print(json.dumps(build(tuple(args.symbols),target_days=args.target_days,
                           price_backfill_pages=args.price_backfill_pages,
                           funding_backfill_pages=args.funding_backfill_pages),
                     sort_keys=True))


if __name__=="__main__":
    main()
