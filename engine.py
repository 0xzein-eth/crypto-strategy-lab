#!/usr/bin/env python3
"""Prospective paper-trading research engine. PUBLIC market reads, NEVER orders.

Event-sourced, append-only full individual records with SHA-256 hash chaining.
No retrospective price lookup, no backdating and no API credentials.
"""
import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import urllib.error
import urllib.request
import signals
import learner
import universe
import friction

BASE = Path(__file__).resolve().parent
EVENTS = BASE / "data" / "events"
REPORT = BASE / "data" / "report.json"
STATE = BASE / "data" / "state.json"
LEGACY = BASE / "data" / "ledger.json"
UTC = dt.timezone.utc
SYMBOLS = universe.SYMBOLS
PROVIDERS = ("bybit-linear", "okx-swap", "binance-futures",
             "kraken-spot-proxy", "coinbase-spot-proxy")
HORIZONS = (1, 2, 4, 8, 12, 24)
START_ID = 116
NOTIONAL_USD = 10000.0
FEE_SIDE_PCT = 0.05
RESEARCH_RISK_PCT = 1.5
MAX_OPEN = 850
MAX_PER_SYMBOL = 50
MAX_NEW_PER_RUN = 24
MAX_NEW_PER_UTC_DAY = 1400
MAX_NEW_PER_SYMBOL_PER_DAY = 65
MAX_QUOTE_AGE_SECONDS = 180
TIMELY_DELAY_SECONDS = 1800
MIN_QUOTE_VOLUME = 2_000_000.0
HTTP_TIMEOUT = 7
PREV_ZERO = "0" * 64


def utcnow():
    return dt.datetime.now(UTC)


def stamp(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone missing: " + value)
    return result.astimezone(UTC)


def positive(value):
    v = float(value)
    if v <= 0 or not math.isfinite(v):
        raise ValueError("price or volume must be positive finite number")
    return v


def request_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "CryptoStrategyLab-PaperOnly/3.0",
                      "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.load(resp)


def quote(symbol, provider, clock=utcnow, requester=request_json):
    """One public snapshot; no historical data, no orders and no price invention."""
    observed = clock()
    bid_px = ask_px = None
    if provider == "bybit-linear":
        raw = requester("https://api.bybit.com/v5/market/tickers?category=linear&symbol=" + symbol + "USDT")
        if str(raw.get("retCode")) != "0" or not raw.get("result", {}).get("list"):
            raise ValueError("Bybit missing ticker")
        item = raw["result"]["list"][0]
        px = positive(item["lastPrice"])
        pct = float(item["price24hPcnt"]) * 100
        volume = float(item.get("turnover24h", 0))
        market_type, instrument = "perpetual", symbol + "USDT"
        bid_px, ask_px = item.get("bid1Price"), item.get("ask1Price")
    elif provider == "okx-swap":
        raw = requester("https://www.okx.com/api/v5/market/ticker?instId=" + symbol + "-USDT-SWAP")
        if raw.get("code") != "0" or not raw.get("data"):
            raise ValueError("OKX missing ticker")
        item = raw["data"][0]
        px = positive(item["last"])
        pct = (px / positive(item["open24h"]) - 1) * 100
        # volCcy24h usually base units; convert to approximate quote notional.
        volume = float(item.get("volCcy24h") or 0) * px
        observed = dt.datetime.fromtimestamp(int(item["ts"]) / 1000, UTC)
        market_type, instrument = "perpetual", symbol + "-USDT-SWAP"
        bid_px, ask_px = item.get("bidPx"), item.get("askPx")
    elif provider == "binance-futures":
        raw = requester("https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=" + symbol + "USDT")
        px = positive(raw["lastPrice"])
        pct = float(raw["priceChangePercent"])
        volume = float(raw.get("quoteVolume", 0))
        observed = dt.datetime.fromtimestamp(int(raw["closeTime"]) / 1000, UTC)
        market_type, instrument = "perpetual", symbol + "USDT"
    elif provider == "kraken-spot-proxy":
        mapping = {"BTC": "XBTUSD"}
        pair = mapping.get(symbol, symbol + "USD")
        raw = requester("https://api.kraken.com/0/public/Ticker?pair=" + pair)
        if raw.get("error") or not raw.get("result"):
            raise ValueError("Kraken missing ticker")
        item = next(iter(raw["result"].values()))
        px = positive(item["c"][0])
        pct = (px / positive(item["o"]) - 1) * 100
        volume = float(item["v"][1]) * px
        market_type, instrument = "spot_proxy", pair
        bid_px = item.get("b", [None])[0]
        ask_px = item.get("a", [None])[0]
    elif provider == "coinbase-spot-proxy":
        pair = symbol + "-USD"
        raw = requester("https://api.exchange.coinbase.com/products/" + pair + "/stats")
        px = positive(raw["last"])
        pct = (px / positive(raw["open"]) - 1) * 100
        volume = float(raw["volume"]) * px
        market_type, instrument = "spot_proxy", pair
    else:
        raise ValueError("unknown market provider: " + provider)
    after = clock()
    age = (after - observed).total_seconds()
    if age < -30 or age > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("stale or future quote, age=" + str(round(age)))
    if abs(pct) > 95 or not math.isfinite(pct) or not math.isfinite(volume) or volume < 0:
        raise ValueError("invalid change/volume")
    period = "UTC-day-open-to-now" if provider == "kraken-spot-proxy" else "provider-24h-window"
    return {"symbol": symbol, "price": px, "pct24h": pct,
            "price_change_reference": period,
            "quote_volume_24h": volume, "observed_at": stamp(observed),
            "provider": provider, "market_type": market_type,
            "instrument": instrument,
            "spread_pct_observed": friction.observed_spread_pct(bid_px,ask_px)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def seal(seq, prev_hash, kind, record):
    raw = {"seq": seq, "prev_hash": prev_hash, "kind": kind, "record": record}
    return dict(raw, hash=hashlib.sha256(canonical(raw).encode("utf-8")).hexdigest())


def validate_open(r):
    mandatory = ("id", "created_at", "evaluate_at", "symbol", "strategy",
                 "provider", "market_type", "instrument", "entry_observed_at",
                 "entry_price", "horizon_hours", "side", "research_risk_pct", "notional_usd")
    for key in mandatory:
        if key not in r:
            raise ValueError("INTEGRITY_FAILURE missing OPEN field " + key)
    if r["status"] != "OPEN" or r["side"] not in ("LONG", "SHORT"):
        raise ValueError("INTEGRITY_FAILURE invalid OPEN status or side")
    if not r["id"].startswith("LAB-") or not r["id"][4:].isdigit():
        raise ValueError("INTEGRITY_FAILURE invalid ID")
    if parse(r["evaluate_at"]) <= parse(r["created_at"]):
        raise ValueError("INTEGRITY_FAILURE nonprospective evaluation")
    if parse(r["entry_observed_at"]) > parse(r["created_at"]):
        raise ValueError("INTEGRITY_FAILURE entry observation in future")
    if r["horizon_hours"] not in HORIZONS or r["provider"] not in PROVIDERS:
        raise ValueError("INTEGRITY_FAILURE unsupported horizon/provider")
    if r["market_type"] != ("perpetual" if "proxy" not in r["provider"] else "spot_proxy"):
        raise ValueError("INTEGRITY_FAILURE mislabeled instrument")
    if r["symbol"] not in SYMBOLS:
        raise ValueError("INTEGRITY_FAILURE unknown asset")
    instrument_by_venue = {
        "bybit-linear": r["symbol"]+"USDT",
        "binance-futures": r["symbol"]+"USDT",
        "okx-swap": r["symbol"]+"-USDT-SWAP",
        "kraken-spot-proxy": "XBTUSD" if r["symbol"]=="BTC" else r["symbol"]+"USD",
        "coinbase-spot-proxy": r["symbol"]+"-USD"}
    if r["instrument"] != instrument_by_venue[r["provider"]]:
        raise ValueError("INTEGRITY_FAILURE instrument/provider mismatch")
    positive(r["entry_price"]); positive(r["research_risk_pct"])
    if abs((parse(r["evaluate_at"])-parse(r["created_at"])).total_seconds()
           - r["horizon_hours"]*3600) > 0.001:
        raise ValueError("INTEGRITY_FAILURE horizon was retroactively moved")
    if abs(r["notional_usd"] - NOTIONAL_USD) > 1e-8:
        raise ValueError("INTEGRITY_FAILURE changed research notional")
    if abs(r["fee_per_side_pct"] - FEE_SIDE_PCT) > 1e-8:
        raise ValueError("INTEGRITY_FAILURE changed research fee")
    if "friction_stress" in r:
        m=r["friction_stress"]
        if (not isinstance(m,dict) or m.get("version")!=friction.VERSION or
            m.get("description")!="hypothetical crossing and impact stress, NOT a real fill"):
            raise ValueError("INTEGRITY_FAILURE invalid friction scenario version")
        if (not isinstance(m.get("assumed_round_trip_extra_pct"),(int,float)) or
            not 0<=m["assumed_round_trip_extra_pct"]<=friction.MAX_ROUND_TRIP_EXTRA_PCT):
            raise ValueError("INTEGRITY_FAILURE invalid friction scenario value")


def validate_close(prior, record):
    """Recompute all stored outcomes to detect tampering even with a rebuilt hash."""
    if parse(record["resolved_at"]) < parse(record["exit_observed_at"]):
        raise ValueError("INTEGRITY_FAILURE closure timestamp precedes price observation")
    observed_delay = int((parse(record["exit_observed_at"])-parse(prior["evaluate_at"])).total_seconds())
    if record["delay_seconds"] != observed_delay or observed_delay < 0:
        raise ValueError("INTEGRITY_FAILURE outcome delay mismatch")
    signed = (positive(record["exit_price"])/positive(prior["entry_price"])-1)*100
    signed *= 1 if prior["side"]=="LONG" else -1
    fees = prior["notional_usd"] * 2 * FEE_SIDE_PCT / 100
    pnl = prior["notional_usd"]*signed/100 - fees
    nr = (signed-2*FEE_SIDE_PCT)/prior["research_risk_pct"]
    if (abs(record["signed_return_pct"]-signed)>1e-6 or
        abs(record["fee_round_trip_usd"]-fees)>1e-6 or
        abs(record["net_pnl_usd"]-pnl)>1e-4 or
        abs(record["normalized_R"]-nr)>1e-6):
        raise ValueError("INTEGRITY_FAILURE outcome arithmetic mismatch")
    expected="WIN" if pnl>1e-7 else "LOSS" if pnl< -1e-7 else "BREAKEVEN"
    if record["outcome"]!=expected:
        raise ValueError("INTEGRITY_FAILURE outcome label mismatch")
    if record.get("late_excluded") != (observed_delay > TIMELY_DELAY_SECONDS):
        raise ValueError("INTEGRITY_FAILURE delayed-sample inclusion mismatch")
    if "friction_stress" in prior:
        expected_stress=friction.scenario(signed,prior["notional_usd"],
            prior["research_risk_pct"],prior["friction_stress"]["assumed_round_trip_extra_pct"])
        if any(key not in record or abs(record[key]-value)>1e-4
               for key,value in expected_stress.items()):
            raise ValueError("INTEGRITY_FAILURE changed frozen friction-stress scenario")


def replay(base=None):
    """Validate every event and return reconstructed state. Fail closed on edits."""
    if base is None:
        base = BASE
    events = base / "data" / "events"
    records, sequence, head = {}, 0, PREV_ZERO
    for path in sorted(events.glob("????-??*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                if not line.strip():
                    raise ValueError("INTEGRITY_FAILURE blank event line")
                try:
                    obj = json.loads(line)
                    expected = seal(sequence + 1, head, obj["kind"], obj["record"])
                    if obj != expected:
                        raise ValueError("hash/sequence mismatch")
                    r = obj["record"]
                    ident = r["id"]
                    if obj["kind"] == "OPEN":
                        validate_open(r)
                        if ident in records or int(ident[4:]) < START_ID:
                            raise ValueError("duplicate or legacy ID")
                        records[ident] = r
                    elif obj["kind"] == "CLOSE":
                        prior = records.get(ident)
                        if prior is None or prior["status"] != "OPEN" or r["status"] != "CLOSED":
                            raise ValueError("closing unknown/already-closed record")
                        if any(r.get(k) != v for k, v in prior.items() if k != "status"):
                            raise ValueError("CLOSE modified original OPEN record")
                        for key in ("exit_price", "exit_observed_at", "resolved_at", "delay_seconds",
                                    "net_pnl_usd", "normalized_R", "fee_round_trip_usd",
                                    "exit_provider", "exit_instrument", "outcome"):
                            if key not in r:
                                raise ValueError("missing CLOSE field: " + key)
                        if r["exit_provider"] != prior["provider"] or r["exit_instrument"] != prior["instrument"]:
                            raise ValueError("CLOSE changed venue/instrument")
                        if parse(r["exit_observed_at"]) < parse(r["evaluate_at"]):
                            raise ValueError("CLOSE uses price before evaluation")
                        validate_close(prior, r)
                        records[ident] = r
                    else:
                        raise ValueError("unsupported event kind")
                    sequence += 1
                    head = expected["hash"]
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("INTEGRITY_FAILURE in %s:%s: %s" % (path, line_number, exc)) from exc
    legacy = base / "data" / "ledger.json"
    if legacy.exists():
        old = json.loads(legacy.read_text(encoding="utf-8"))
        if old.get("records"):
            raise ValueError("INTEGRITY_FAILURE historic ledger not migrated; cannot run dual sources")
    next_id = max([START_ID - 1] + [int(x[4:]) for x in records]) + 1
    return records, sequence, head, next_id


def close_due(records, read_quote, moment, clock=None):
    """Close against same-venue/same-instrument observation, never historical fills."""
    outputs, late, missing = [], 0, 0
    clock = clock or (lambda: moment)
    for r in sorted(records.values(), key=lambda rec: rec["evaluate_at"]):
        if r["status"] != "OPEN" or parse(r["evaluate_at"]) > moment:
            continue
        try:
            q = read_quote(r["symbol"], r["provider"])
        except Exception:
            missing += 1
            continue
        if (q["provider"], q["instrument"], q["market_type"]) != (
                r["provider"], r["instrument"], r["market_type"]):
            missing += 1
            continue
        observed = parse(q["observed_at"])
        if observed < parse(r["evaluate_at"]):
            missing += 1
            continue
        signed = (q["price"] / r["entry_price"] - 1) * 100
        if r["side"] == "SHORT":
            signed *= -1
        fees = r["notional_usd"] * 2 * FEE_SIDE_PCT / 100
        pnl = r["notional_usd"] * signed / 100 - fees
        delay = int((observed - parse(r["evaluate_at"])).total_seconds())
        close = dict(r)
        close.update(status="CLOSED", exit_price=q["price"],
                     exit_observed_at=q["observed_at"], exit_provider=q["provider"],
                     exit_instrument=q["instrument"], resolved_at=stamp(max(moment, observed, clock())),
                     delay_seconds=delay, late_excluded=delay > TIMELY_DELAY_SECONDS,
                     fee_round_trip_usd=round(fees, 6), signed_return_pct=round(signed, 8),
                     net_pnl_usd=round(pnl, 6),
                     normalized_R=round((signed - 2 * FEE_SIDE_PCT) / r["research_risk_pct"], 8),
                     outcome="WIN" if pnl > 1e-7 else "LOSS" if pnl < -1e-7 else "BREAKEVEN",
                     funding_assumption_usd=0.0)
        if "friction_stress" in r:
            close.update(friction.scenario(signed,r["notional_usd"],
                         r["research_risk_pct"],r["friction_stress"]["assumed_round_trip_extra_pct"]))
        outputs.append(close)
        late += int(close["late_excluded"])
    return outputs, late, missing



def diversified_quotes(quotes, slot):
    """Interleave predeclared sector/direction/volatility strata deterministically.

    Sector groupings improve representation but do not create statistical independence.
    No retrospective outcomes influence ranking or features.
    """
    buckets = defaultdict(list)
    for q in quotes:
        buckets[universe.bucket(q["symbol"], q["pct24h"], q["quote_volume_24h"])].append(q)
    for key, rows in buckets.items():
        rows.sort(key=lambda q: (
            hashlib.sha256(f"{slot}:{q['symbol']}:{key}".encode()).hexdigest(),
            q["symbol"]))
    keys = sorted(buckets)
    if keys:
        start = slot % len(keys)
        keys = keys[start:] + keys[:start]
    ordered = []
    while any(buckets.values()):
        for key in keys:
            if buckets[key]:
                ordered.append(buckets[key].pop(0))
    return ordered


def new_candidates(records, read_quote, moment, next_id, requested, advanced=None, reobserve=None, clock=None):
    """Validated candle hypotheses when observable; deterministic proxy controls otherwise."""
    # UTC-day budgets bound public CI/storage use and avoid accidental flood
    # from repeated manual dispatches. Existing full event history remains intact.
    utc_day = moment.date()
    opened_today = [r for r in records.values()
                    if parse(r["created_at"]).date() == utc_day]
    daily_capacity = MAX_NEW_PER_UTC_DAY - len(opened_today)
    slots = max(0, min(requested, MAX_NEW_PER_RUN, daily_capacity, MAX_OPEN -
                       sum(r["status"] == "OPEN" for r in records.values())))
    if not slots:
        return []
    slot = int(moment.timestamp() // 900)
    clock = clock or (lambda:moment)
    daily_by_symbol = defaultdict(int)
    for r in opened_today:
        daily_by_symbol[r["symbol"]] += 1
    quotes = []
    for symbol in SYMBOLS:
        try:
            q = read_quote(symbol, None)
            if (q["quote_volume_24h"] >= MIN_QUOTE_VOLUME and
                    abs(q["pct24h"]) >= 0.5 and
                    (moment - parse(q["observed_at"])).total_seconds() <= MAX_QUOTE_AGE_SECONDS):
                quotes.append(q)
        except Exception:
            continue
    quotes = diversified_quotes(quotes, slot)
    output, one_per_run = [], set()
    for rank, q in enumerate(quotes):
        if len(output) >= slots:
            break
        symbol = q["symbol"]
        if (symbol in one_per_run or
            daily_by_symbol[symbol] >= MAX_NEW_PER_SYMBOL_PER_DAY or
            sum(r["symbol"] == symbol and r["status"] == "OPEN"
                for r in records.values()) >= MAX_PER_SYMBOL):
            continue
        # The online allocator only selects among pre-registered, observable
        # hypotheses. Controls remain available regardless of apparent results.
        move=q["pct24h"]
        baseline=[
            {"strategy":"BR-proxy-v1","side":"LONG" if move>=0 else "SHORT"},
            {"strategy":"MR-proxy-v1","side":"SHORT" if move>=0 else "LONG"},
            {"strategy":"CTRL-v1",
             "side":"LONG" if hashlib.sha256((symbol+":"+str(slot)).encode()).digest()[0]%2==0 else "SHORT"}]
        detections=[]
        if advanced is not None and q["provider"]=="okx-swap":
            detections=advanced(symbol,q) or []
        # Indicator-based candidates can never be synthesized from a missing,
        # stale, unconfirmed or wrong-instrument candle.
        options=baseline+[
            {"strategy":x["strategy"],"side":x["side"],"evidence":x["evidence"]}
            for x in detections
            if x.get("strategy") in learner.ADVANCED and x.get("side") in ("LONG","SHORT")
        ]
        # Deduplicate arm labels without rewriting evidence.
        options=list({x["strategy"]:x for x in options}.values())
        # Rotate across pre-registered horizons when a symbol/arm/horizon is
        # already OPEN. This prevents artificial throughput loss from repeated
        # identical signatures; no future outcome participates in selection.
        chosen=allocation=None
        horizon_retry=0
        h=None
        for offset in range(len(HORIZONS)):
            candidate_h=HORIZONS[(slot+rank+offset)%len(HORIZONS)]
            picked,mode=learner.choose(options, records, symbol, candidate_h, slot, rank+offset)
            if picked is None:
                continue
            if any(r["status"] == "OPEN" and r["symbol"] == symbol and
                   r["provider"] == q["provider"] and
                   r["strategy"] == picked["strategy"] and
                   r["horizon_hours"] == candidate_h for r in records.values()):
                continue
            h=candidate_h
            chosen,allocation=picked,mode
            horizon_retry=offset
            break
        if chosen is None:
            continue
        style,side=chosen["strategy"],chosen["side"]
        evidence={"price_change_24h_pct":round(q["pct24h"],6),
                  "quote_volume_24h":round(q["quote_volume_24h"],2),
                  "price_change_reference":q.get("price_change_reference","provider-24h-window"),
                  "signal_rule":"pre-registered confirmed-candle or 24h baseline",
                  "research_only":True,
                  "allocation_policy":"learner-v1-fixed-day-holdout",
                  "selection_mode":allocation,
                  "horizon_conflict_retries":horizon_retry,
                  "signal_catalog_version":"2026-10-08",
                  "universe_version":universe.UNIVERSE_VERSION,
                  "sampling_stratum":list(universe.bucket(symbol, q["pct24h"], q["quote_volume_24h"])),
                  "sampling_rule":"sector-direction-volatility-roundrobin-15m"}
        quality="exploratory; no tradable-edge claim"
        if chosen.get("evidence"):
            evidence.update(chosen["evidence"])
            quality="confirmed historical 15m OHLCV; still experimental"
        # A fresh same-venue quote is captured AFTER indicators are evaluated.
        # We never pretend the earlier screening ticker was an executable entry.
        try:
            entry = reobserve(symbol, q["provider"]) if reobserve else q
        except Exception:
            continue
        if (entry["provider"], entry["market_type"], entry["instrument"]) != (
                q["provider"], q["market_type"], q["instrument"]):
            continue
        if (clock()-parse(entry["observed_at"])).total_seconds() > MAX_QUOTE_AGE_SECONDS:
            continue
        rid = "LAB-" + str(next_id + len(output))
        entered_at = max(moment, clock(), parse(entry["observed_at"]))
        rec = {"id": rid, "status": "OPEN", "created_at": stamp(entered_at),
               "entry_observed_at": entry["observed_at"], "entry_price": entry["price"],
               "evaluate_at": stamp(entered_at + dt.timedelta(hours=h)),
               "symbol": symbol, "instrument": entry["instrument"],
               "provider": entry["provider"], "market_type": entry["market_type"],
               "strategy": style, "side": side, "horizon_hours": h,
               "evidence": evidence,
               "cluster": "CRYPTO_BETA", "regime": "24h_down" if q["pct24h"] < 0 else "24h_up",
               "notional_usd": NOTIONAL_USD, "hypothetical_leverage": 3,
               "fee_per_side_pct": FEE_SIDE_PCT, "research_risk_pct": RESEARCH_RISK_PCT,
               "funding_assumption_usd": 0, "quality": quality,
               "friction_stress":friction.estimate_extra_round_trip_pct(
                    symbol,entry["pct24h"],entry["quote_volume_24h"],
                    entry.get("spread_pct_observed"))}
        validate_open(rec)
        output.append(rec)
        one_per_run.add(symbol)
    return output


def summarize(records, moment):
    closed = [r for r in records.values() if r["status"] == "CLOSED"]
    opened = [r for r in records.values() if r["status"] == "OPEN"]
    pending = sum(parse(r["evaluate_at"]) <= moment for r in opened)
    pnl = [r["net_pnl_usd"] for r in closed]
    gross_win = sum(p for p in pnl if p > 0)
    gross_loss = -sum(p for p in pnl if p < 0)
    by = defaultdict(list)
    for r in closed:
        by[r["strategy"] + " / " + str(r["horizon_hours"]) + "h"].append(r)
    eligible = [r for r in closed if not r.get("late_excluded") and
                r["market_type"] == "perpetual"]
    balance = peak = max_dd = 0.0
    for r in sorted(closed, key=lambda x: (x["resolved_at"], x["id"])):
        balance += r["net_pnl_usd"]
        peak = max(peak, balance)
        max_dd = max(max_dd, peak - balance)
    stress_rows=[r for r in closed if "stress_net_pnl_usd" in r]
    sample = lambda arr: {
        "n": len(arr),
        "net_R": round(sum(r["normalized_R"] for r in arr), 5),
        "expectancy_R": round(sum(r["normalized_R"] for r in arr)/len(arr), 5) if arr else None
    }
    return {"schema_version": 8, "created": len(records), "closed": len(closed),
            "open": len(opened)-pending, "pending": pending,
            "wins": sum(p > 0 for p in pnl), "losses": sum(p < 0 for p in pnl),
            "win_rate": round(sum(p > 0 for p in pnl) / len(pnl), 4) if pnl else None,
            "net_pnl_usd": round(sum(pnl), 2),
            "net_R": round(sum(r["normalized_R"] for r in closed), 5),
            "net_expectancy_R": sample(closed)["expectancy_R"],
            "profit_factor": round(gross_win/gross_loss, 4) if gross_loss else None,
            "max_closed_equity_drawdown_usd": round(max_dd, 2),
            "total_round_trip_fees_usd": round(sum(r["fee_round_trip_usd"] for r in closed), 2),
            "friction_stress_scenario": {
                "modeled_closes":len(stress_rows),
                "net_pnl_usd":round(sum(r["stress_net_pnl_usd"] for r in stress_rows),2),
                "net_R":round(sum(r["stress_normalized_R"] for r in stress_rows),5),
                "additional_assumed_cost_usd":round(
                    sum(r["stress_extra_cost_usd"] for r in stress_rows),2),
                "assumption":"entry bid-ask crossing plus hypothetical impact; not observed fills"},
            "universe_size":len(SYMBOLS),
            "universe_version":universe.UNIVERSE_VERSION,
            "capacity_policy":{
                "max_new_per_run":MAX_NEW_PER_RUN,
                "max_new_per_utc_day":MAX_NEW_PER_UTC_DAY,
                "max_open":MAX_OPEN,
                "max_open_per_symbol":MAX_PER_SYMBOL},
            "late_closures": sum(r.get("late_excluded", False) for r in closed),
            "spot_proxy_closures": sum(r["market_type"] == "spot_proxy" for r in closed),
            "eligible_perpetual_timely": sample(eligible),
            "adaptive_research": learner.analysis(records),
            "strategy_horizon": {
                k: dict(sample(v), evidence="collect" if len(v) < 10 else
                        "hypothesis" if len(v) < 30 else "preliminary, correlated" if len(v) < 50
                        else "multi-regime validation needed")
                for k, v in sorted(by.items())},
            "limitations": [
                "Correlated trades are not independent evidence of edge",
                "Fixed-horizon observed snapshots; delayed observations excluded from eligible sample",
                "Spot proxies excluded from eligible perpetual sample",
                "No actual order fills, variable funding, spread, slippage or liquidation",
                "Historical LAB-074..115 NOT imported; no verified robust edge"]}


def append_events(events, prev_seq, prev_hash, moment):
    if not events:
        return prev_seq, prev_hash
    EVENTS.mkdir(parents=True, exist_ok=True)
    # Legacy month files sort before this day's shard in lexicographic replay.
    # Monthly legacy 2026-10.jsonl => daily 2026-10_daily_08.jsonl.
    path = EVENTS / (moment.strftime("%Y-%m_daily_%d") + ".jsonl")
    seq, head = prev_seq, prev_hash
    with path.open("a", encoding="utf-8") as out:
        for kind, record in events:
            seq += 1
            obj = seal(seq, head, kind, record)
            out.write(canonical(obj) + "\n")
            head = obj["hash"]
        out.flush()
    return seq, head


def atomic_json(path, obj):
    import os, tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(obj, out, sort_keys=True, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run(requested=14, clock=utcnow):
    current = clock()
    records, seq, prev_hash, next_id = replay()
    if REPORT.exists():
        previous = json.loads(REPORT.read_text(encoding="utf-8"))
        if previous.get("schema_version") == 8:
            if previous.get("verified_events") != seq or previous.get("ledger_tip_sha256") != prev_hash:
                raise ValueError("INTEGRITY_FAILURE: persisted report disagrees with event chain")
    if any(int(r["id"][4:]) >= next_id for r in records.values()):
        raise ValueError("INTEGRITY_FAILURE ID counter")
    cache, errors, blocked_providers = {}, {}, {}
    def read_quote(symbol, provider=None):
        providers = (provider,) if provider else PROVIDERS
        for name in providers:
            if name in blocked_providers:
                continue
            key = (symbol, name)
            if key not in cache:
                try:
                    cache[key] = quote(symbol, name, clock=clock)
                except urllib.error.HTTPError as exc:
                    cache[key] = None
                    errors[symbol + ":" + name] = "HTTP " + str(exc.code)
                    if exc.code in (401, 403, 451):
                        blocked_providers[name] = exc.code
                        errors["PROVIDER_BLOCKED:" + name] = "HTTP " + str(exc.code)
                except (urllib.error.URLError, TimeoutError, KeyError, TypeError,
                        ValueError, IndexError, RuntimeError, OSError) as exc:
                    cache[key] = None
                    errors[symbol + ":" + name] = str(exc)[:130]
            if cache[key] is not None:
                return cache[key]
        raise RuntimeError("DATA_UNAVAILABLE: no provider for " + symbol)
    closures, late, missing = close_due(records, read_quote, current, clock=clock)
    for r in closures:
        records[r["id"]] = r
    def advanced(symbol, snapshot):
        try:
            return signals.from_okx(symbol, snapshot, request_json, clock)
        except (urllib.error.URLError, TimeoutError, KeyError, TypeError,
                ValueError, IndexError, RuntimeError, OSError) as exc:
            errors["15m_OHLCV:" + symbol] = str(exc)[:150]
            return []
    def reobserve(symbol, provider):
        return quote(symbol, provider, clock=clock)
    opens = new_candidates(records, read_quote, current, next_id, requested,
                           advanced=advanced, reobserve=reobserve, clock=clock)
    for r in opens:
        records[r["id"]] = r
    events = [("CLOSE", r) for r in closures] + [("OPEN", r) for r in opens]
    # Avoid writing a partial ledger and misreporting green on total provider failure.
    observations = sum(x is not None for x in cache.values())
    if not observations:
        raise RuntimeError("DATA_UNAVAILABLE: all public market sources failed: " +
                           json.dumps(errors, sort_keys=True)[:1000])
    # In CI/GitHub Actions, ledger + summary are committed together as one Git commit.
    seq, prev_hash = append_events(events, seq, prev_hash, current)
    # Replay *after* writing ensures hash-chain + individual records are consistent.
    confirmed, seq2, head2, _ = replay()
    if seq != seq2 or prev_hash != head2 or confirmed != records:
        raise ValueError("INTEGRITY_FAILURE: event replay mismatch")
    result = summarize(records, current)
    result.update(status="OK" if opens else "NO_NEW_SIGNALS",
                  timestamp=stamp(current), added=len(opens), closed_this_run=len(closures),
                  late_closed_this_run=late, missed_due_snapshots=missing,
                  provider_observations=observations, source_errors=errors,
                  blocked_market_providers=blocked_providers,
                  verified_events=seq, ledger_tip_sha256=prev_hash,
                  workflow_interval_note="GitHub scheduled triggers are best-effort")
    active = [r for r in records.values() if r["status"] == "OPEN"]
    recent_closed = sorted((r for r in records.values() if r["status"] == "CLOSED"),
                           key=lambda r: (r["resolved_at"], r["id"]), reverse=True)[:80]
    recent = sorted(active, key=lambda r: (r["created_at"], r["id"]), reverse=True) + recent_closed
    atomic_json(STATE, {"schema_version": 8, "timestamp": stamp(current),
                        "records": recent, "ledger_tip_sha256": prev_hash,
                        "all_events_verified": seq})
    atomic_json(REPORT, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Strict prospective paper research")
    ap.add_argument("--count", type=int, default=14)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()
    if args.verify_only:
        rs, seq, head, nxt = replay()
        print(json.dumps({"verified": True, "events": seq,
                          "records": len(rs), "next_id": nxt, "hash": head}))
    else:
        run(args.count)
