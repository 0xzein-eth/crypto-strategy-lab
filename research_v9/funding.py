"""OKX SETTLED funding-rate history for retrospective scenario analysis only.

Uses historical realizedRate, not projected nextFundingRate. Every number is
an approximation of a constant-notional position's funding cash flow; not a
statement about a particular account's execution or real exchange balance.
"""
import datetime as dt
import gzip
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from research_v9.history import ROOT, USER_AGENT

CACHE_DIR = ROOT / "research_cache" / "okx_funding"
MAX_FUNDING_GAP_MS = 12 * 3600 * 1000


def parse_settled(payload, symbol, now=None):
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError("DATA_UNAVAILABLE: invalid OKX funding response")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("DATA_UNAVAILABLE: missing funding events")
    current = now or dt.datetime.now(dt.timezone.utc)
    ceiling = int(current.timestamp() * 1000) + 15_000
    items = {}
    expected = symbol + "-USDT-SWAP"
    for row in rows:
        if row.get("instId") != expected or row.get("instType", "SWAP") != "SWAP":
            raise ValueError("DATA_INVALID: funding rate belongs to a different contract")
        realized = row.get("realizedRate")
        if realized is None or realized == "":
            # Exclude unconfirmed prospective funding observations.
            continue
        try:
            timestamp = int(row["fundingTime"])
            rate = float(realized)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("DATA_INVALID: malformed settled funding") from exc
        if timestamp <= 0 or timestamp > ceiling or not math.isfinite(rate) or abs(rate) > 0.10:
            raise ValueError("DATA_INVALID: impossible historical funding")
        item = [timestamp, rate]
        if timestamp in items and items[timestamp] != item:
            raise ValueError("INTEGRITY_FAILURE: conflicting funding settlement")
        items[timestamp] = item
    return [items[k] for k in sorted(items)]


def validate_rates(events):
    if not isinstance(events, list):
        raise ValueError("DATA_INVALID: funding cache is not list")
    prior = None
    for event in events:
        if (not isinstance(event, list) or len(event) != 2
                or not isinstance(event[0], int) or event[0] <= 0
                or not isinstance(event[1], (float, int))
                or not math.isfinite(event[1]) or abs(event[1]) > 0.10):
            raise ValueError("DATA_INVALID: malformed cached funding event")
        if prior is not None and event[0] <= prior:
            raise ValueError("DATA_INVALID: duplicate or unsorted funding times")
        prior = event[0]
    return events


def cache_path(symbol):
    if not symbol.isascii() or not symbol.isalnum() or symbol.upper() != symbol:
        raise ValueError("invalid funding symbol")
    return CACHE_DIR / (symbol + ".json.gz")


def load_cache(symbol):
    path = cache_path(symbol)
    if not path.exists():
        return []
    obj = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    if obj.get("instrument") != symbol + "-USDT-SWAP" or obj.get("venue") != "okx-swap":
        raise ValueError("INTEGRITY_FAILURE: funding cache instrument mismatch")
    return validate_rates(obj["settlements"])


def save_cache(symbol, rows):
    validate_rates(rows)
    path = cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema_version": 1, "venue": "okx-swap",
                          "instrument": symbol + "-USDT-SWAP", "settlements": rows},
                         sort_keys=True, separators=(",", ":")).encode()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    temp.replace(path)


def fetch_page(symbol, after=None, getter=None, sleeper=time.sleep):
    params = {"instId": symbol+"-USDT-SWAP", "limit": "100"}
    if after is not None:
        params["after"] = str(after)
    url = "https://www.okx.com/api/v5/public/funding-rate-history?" + urllib.parse.urlencode(params)
    def network_get(uri):
        req = urllib.request.Request(uri, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.load(response)
    getter = getter or network_get
    for attempt in range(3):
        try:
            return getter(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        sleeper(min(6, 2**attempt))
    raise RuntimeError("unreachable")


def refresh_symbol(symbol, pages=5, now=None, getter=None, sleeper=time.sleep,
                   max_events=4_000, first_bar_ms=None, backfill_pages=5):
    if (not 1 <= pages <= 60 or not 100 <= max_events <= 10_000
            or not 0 <= backfill_pages <= 60):
        raise ValueError("invalid funding pagination budget")
    existing = load_cache(symbol)
    observed = {}
    cursor = None
    for index in range(pages):
        payload = fetch_page(symbol, after=cursor, getter=getter, sleeper=sleeper)
        batch = parse_settled(payload, symbol, now=now)
        if not batch:
            if index == 0:
                raise ValueError("DATA_UNAVAILABLE: no settled funding rates")
            break
        if cursor is not None and batch[-1][0] >= cursor:
            raise ValueError("DATA_INVALID: funding backwards pagination did not progress")
        for row in batch:
            if row[0] in observed and observed[row[0]] != row:
                raise ValueError("DATA_INVALID: conflicting funding history pages")
            observed[row[0]] = row
        cursor = batch[0][0]
        if existing and cursor <= existing[-1][0]:
            break
        if index + 1 < pages:
            sleeper(0.11)
    merged = {event[0]: event for event in existing}
    for row in observed.values():
        if row[0] in merged and merged[row[0]] != row:
            raise ValueError("INTEGRITY_FAILURE: historical funding settlement changed")
        merged[row[0]] = row
    # Refresh newest settlements first; extend older history separately so
    # daily refreshes do not repeatedly spend every page on the same range.
    if first_bar_ms is not None and merged:
        cursor = min(merged)
        for _ in range(backfill_pages):
            if cursor <= first_bar_ms:
                break
            sleeper(0.11)
            batch = parse_settled(fetch_page(symbol, after=cursor, getter=getter,
                                           sleeper=sleeper), symbol, now=now)
            if not batch:
                break
            if batch[-1][0] >= cursor:
                raise ValueError("DATA_INVALID: funding backfill did not progress")
            for row in batch:
                if row[0] in merged and merged[row[0]] != row:
                    raise ValueError("INTEGRITY_FAILURE: historical funding settlement changed")
                merged[row[0]] = row
            cursor = batch[0][0]
    result = [merged[ts] for ts in sorted(merged)][-max_events:]
    validate_rates(result)
    save_cache(symbol, result)
    return result


def coverage(events, first_bar_ms, last_bar_ms):
    """Conservative full-window check; missing/irregular rates are NOT zeroed."""
    validate_rates(events)
    if not events or first_bar_ms > last_bar_ms:
        return False
    if events[0][0] > first_bar_ms + MAX_FUNDING_GAP_MS:
        return False
    if events[-1][0] < last_bar_ms - MAX_FUNDING_GAP_MS:
        return False
    # An unexpectedly missing funding event disqualifies the measured series.
    return all(b[0]-a[0] <= MAX_FUNDING_GAP_MS
               for a, b in zip(events, events[1:]))


def payment_pct(events, side, entry_ms, exit_ms):
    """Cash paid in % of CONSTANT notional; negative means funding received.

    The position must exist across the settlement instant: (entry, exit].
    100 * sum(decimal settled rates) for LONG, negative for SHORT.
    """
    validate_rates(events)
    if side not in (-1, 1) or entry_ms >= exit_ms:
        raise ValueError("invalid funded trade")
    return 100 * side * sum(rate for when, rate in events
                            if entry_ms < when <= exit_ms)
