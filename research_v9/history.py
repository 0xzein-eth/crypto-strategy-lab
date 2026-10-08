"""Auditable OKX USDT-SWAP confirmed 15m historical candles with bounded cache.

Historical OHLCV is BACKTEST data, never masquerading as prospective orders.
The upstream candle endpoint must match the exact derivative instrument.
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

BAR_MS = 900_000
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "research_cache" / "okx_swap_15m"
USER_AGENT = "CryptoStrategyLab-PaperResearch/9.0 (public-data-only)"


def parse_confirmed(payload, now=None):
    """Validate complete confirmed candles; reject malformed/out-of-window values."""
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        raise ValueError("DATA_UNAVAILABLE: unexpected OKX history response")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("DATA_UNAVAILABLE: missing candle array")
    current = now or dt.datetime.now(dt.timezone.utc)
    current_ms = int(current.timestamp() * 1000)
    candles = {}
    for r in rows:
        if not isinstance(r, list) or len(r) < 9:
            raise ValueError("DATA_INVALID: short candle")
        if str(r[8]) != "1":
            continue
        try:
            ts = int(r[0])
            values = [float(r[i]) for i in (1, 2, 3, 4, 5)]
            op, high, low, close, volume = values
        except (TypeError, ValueError, OverflowError, IndexError) as exc:
            raise ValueError("DATA_INVALID: malformed confirmed candle") from exc
        if ts <= 0 or ts % BAR_MS or ts + BAR_MS > current_ms + 15_000:
            continue
        if (not all(math.isfinite(x) for x in values) or
                min(op, high, low, close) <= 0 or volume < 0 or
                low > min(op, close) or high < max(op, close) or high < low):
            raise ValueError("DATA_INVALID: inconsistent OHLCV")
        item = [ts, op, high, low, close, volume]
        if ts in candles and candles[ts] != item:
            raise ValueError("DATA_INVALID: conflicting same-time candles")
        candles[ts] = item
    return [candles[k] for k in sorted(candles)]


def validate_series(candles, min_bars=2):
    if not isinstance(candles, list) or len(candles) < min_bars:
        raise ValueError("DATA_INVALID: too few bars")
    previous = None
    for item in candles:
        if not isinstance(item, list) or len(item) != 6:
            raise ValueError("DATA_INVALID: unexpected cache shape")
        ts, op, high, low, close, volume = item
        if (not isinstance(ts, int) or ts <= 0 or ts % BAR_MS or
                not all(isinstance(v, (int, float)) and math.isfinite(v)
                        for v in item[1:]) or
                min(op, high, low, close) <= 0 or volume < 0 or
                high < max(op, close) or low > min(op, close)):
            raise ValueError("DATA_INVALID: invalid cached candle")
        if previous is not None and ts - previous != BAR_MS:
            raise ValueError("DATA_INVALID: missing, duplicate or nonsequential bars")
        previous = ts
    return candles


def merge_series(existing, incoming, max_bars=6_000):
    if existing:
        validate_series(existing)
    if incoming:
        validate_series(incoming, min_bars=1)
    if not incoming:
        raise ValueError("DATA_UNAVAILABLE: no confirmed candles")
    combined = {r[0]: r for r in existing}
    common = 0
    for row in incoming:
        old = combined.get(row[0])
        if old is not None:
            if old != row:
                raise ValueError("INTEGRITY_FAILURE: exchange revised confirmed historical candle")
            common += 1
        combined[row[0]] = row
    if existing and common == 0:
        raise ValueError("DATA_INVALID: no overlap with saved history; refusing silent gap")
    rows = [combined[k] for k in sorted(combined)]
    validate_series(rows)
    if max_bars < 200:
        raise ValueError("max_bars must be at least 200")
    return rows[-max_bars:]


def cache_path(symbol):
    if not symbol.isascii() or not symbol.isalnum() or symbol.upper() != symbol:
        raise ValueError("invalid research symbol")
    return CACHE_DIR / (symbol + ".json.gz")


def load_cache(symbol):
    path = cache_path(symbol)
    if not path.exists():
        return []
    obj = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    if obj.get("venue") != "okx-swap" or obj.get("instrument") != symbol + "-USDT-SWAP" or obj.get("bar") != "15m":
        raise ValueError("INTEGRITY_FAILURE: cached venue/instrument mismatch")
    return validate_series(obj["candles"])


def save_cache(symbol, candles):
    validate_series(candles)
    path = cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"venue": "okx-swap", "instrument": symbol + "-USDT-SWAP",
           "bar": "15m", "schema_version": 1, "candles": candles}
    encoded = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload = gzip.compress(encoded, compresslevel=9, mtime=0)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(payload)
    temp.replace(path)


def okx_page(symbol, after=None, getter=None, sleeper=time.sleep):
    """Fetch at most 100 older candles; 429/5xx retries never fabricate bars."""
    params = {"instId": symbol + "-USDT-SWAP", "bar": "15m", "limit": "100"}
    if after is not None:
        params["after"] = str(after)
    url = "https://www.okx.com/api/v5/market/history-candles?" + urllib.parse.urlencode(params)
    def real_get(uri):
        req = urllib.request.Request(uri, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as response:
            return json.load(response)
    do_get = getter or real_get
    for attempt in range(3):
        try:
            return do_get(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError) :
            if attempt == 2:
                raise
        sleeper(min(6, 2 ** attempt))
    raise RuntimeError("unreachable")


def refresh_symbol(symbol, cold_pages=16, update_pages=10, now=None,
                   getter=None, sleeper=time.sleep):
    """Bounded backfill; cache updated only if feed is complete and consistent."""
    existing = load_cache(symbol)
    pages = update_pages if existing else cold_pages
    if not 1 <= pages <= 60:
        raise ValueError("pages out of supported 1..60 range")
    seen = {}
    cursor = None
    oldest = None
    for index in range(pages):
        payload = okx_page(symbol, after=cursor, getter=getter, sleeper=sleeper)
        batch = parse_confirmed(payload, now=now)
        if not batch:
            if index == 0:
                raise ValueError("DATA_UNAVAILABLE: empty confirmed OKX response")
            break
        if oldest is not None and batch[-1][0] >= oldest:
            raise ValueError("DATA_INVALID: backwards pagination made no progress")
        for item in batch:
            if item[0] in seen and seen[item[0]] != item:
                raise ValueError("DATA_INVALID: inconsistent overlapping history pages")
            seen[item[0]] = item
        oldest = batch[0][0]
        if existing and oldest <= existing[-1][0] - 2 * BAR_MS:
            break
        cursor = oldest
        if index + 1 < pages:
            sleeper(0.11)  # Below documented public endpoint IP rate limit
    fresh = [seen[k] for k in sorted(seen)]
    merged = merge_series(existing, fresh)
    current = now or dt.datetime.now(dt.timezone.utc)
    age_s = current.timestamp() - (merged[-1][0] + BAR_MS) / 1000
    if age_s > 3 * 3600:
        raise ValueError("DATA_STALE: newest confirmed bar older than three hours")
    if age_s < -20:
        raise ValueError("DATA_INVALID: candle ends in future")
    save_cache(symbol, merged)
    return merged
