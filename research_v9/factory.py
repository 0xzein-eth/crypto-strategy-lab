"""Deterministic, no-lookahead parameterized strategy research factory.

Backtest-only, NOT the v8 prospective event engine. All signals use completed
bars and hypothetical entry at the NEXT bar open. Exit: future bar open after
a predeclared fixed horizon; no stops, no TP. Market fills are not simulated.
"""
import dataclasses
import datetime as dt
import hashlib
import math
import statistics
from collections import defaultdict
from itertools import product

from research_v9.history import BAR_MS, validate_series
from research_v9.funding import payment_pct, validate_rates

HORIZONS = (4, 8, 16, 32, 96)  # 1h, 2h, 4h, 8h, 24h on 15m candles
FEE_PCT = 0.10                # 0.05% each side (hypothetical)
STRESS_PCT = 0.12             # Additional assumed round-trip spread/impact
R_DENOMINATOR_PCT = 1.5       # Research normalization, NOT an executed stop
LOOKBACK_BARS = 65
EMBARGO_BARS = max(HORIZONS)


@dataclasses.dataclass(frozen=True)
class Variant:
    family: str
    lookback: int
    threshold: float
    second: int
    horizon: int

    @property
    def id(self):
        return "%s-L%s-T%s-S%s-H%s" % (
            self.family, self.lookback, str(self.threshold).replace(".", "p"),
            self.second, self.horizon)

    def as_dict(self):
        return dataclasses.asdict(self) | {"id": self.id}


def variant_catalog(max_variants=300):
    """Fixed, versioned parameter grid, then deterministic family round robin."""
    by_family = defaultdict(list)
    for fast, slow, gate, h in product((8, 12, 20), (36, 60),
                                       (0.001, 0.003), HORIZONS):
        if fast < slow:
            by_family["trend"].append(Variant("trend", fast, gate, slow, h))
    for lookback, gate, h in product((4, 8, 16, 32),
                                     (0.002, 0.004, 0.008), HORIZONS):
        by_family["momentum"].append(Variant("momentum", lookback, gate, 0, h))
    for lookback, z, h in product((12, 20, 32), (1.3, 1.8, 2.3), HORIZONS):
        by_family["mean_revert"].append(Variant("mean_revert", lookback, z, 0, h))
    for lookback, vol, h in product((12, 20, 40), (0.8, 1.2), HORIZONS):
        by_family["breakout"].append(Variant("breakout", lookback, vol, 0, h))
    for period, threshold, h in product((7, 14, 21), (25, 30, 35), HORIZONS):
        by_family["rsi_revert"].append(Variant("rsi_revert", period, threshold, 0, h))
    for h in HORIZONS:
        by_family["control"].extend([
            Variant("control", 0, 0.0, 0, h),
            Variant("long_control", 0, 0.0, 0, h)])
    if not 1 <= max_variants <= 500:
        raise ValueError("max_variants must be within 1..500")
    families = sorted(by_family)
    selected = []
    while len(selected) < max_variants and any(by_family.values()):
        for family in families:
            if by_family[family]:
                selected.append(by_family[family].pop(0))
                if len(selected) >= max_variants:
                    break
    if len({v.id for v in selected}) != len(selected):
        raise AssertionError("duplicate variant id")
    return selected


class Features:
    def __init__(self, candles):
        validate_series(candles, min_bars=LOOKBACK_BARS + 2)
        self.bars = candles
        self.ts = [r[0] for r in candles]
        self.open = [r[1] for r in candles]
        self.high = [r[2] for r in candles]
        self.low = [r[3] for r in candles]
        self.close = [r[4] for r in candles]
        self.vol = [r[5] for r in candles]
        self.cumsum = [0.0]
        self.sumsq = [0.0]
        self.vsum = [0.0]
        self.gain = [0.0]
        self.loss = [0.0]
        for i, c in enumerate(self.close):
            self.cumsum.append(self.cumsum[-1] + c)
            self.sumsq.append(self.sumsq[-1] + c*c)
            self.vsum.append(self.vsum[-1] + self.vol[i])
            change = c-self.close[i-1] if i else 0.0
            self.gain.append(self.gain[-1] + max(0.0, change))
            self.loss.append(self.loss[-1] + max(0.0, -change))

    @staticmethod
    def window(prefix, j, n):
        return (prefix[j+1] - prefix[j+1-n]) / n

    def mean(self, j, n):
        return self.window(self.cumsum, j, n)

    def std(self, j, n):
        mean = self.mean(j, n)
        return math.sqrt(max(0, self.window(self.sumsq, j, n) - mean*mean))

    def rsi(self, j, n):
        gains = self.gain[j+1] - self.gain[j+1-n]
        losses = self.loss[j+1] - self.loss[j+1-n]
        if losses <= 0:
            return 100.0 if gains > 0 else 50.0
        return 100.0 - 100.0/(1+gains/losses)


def signal(f, v, closed):
    """LONG=1, SHORT=-1, or no signal=0; depends only on bars <= closed."""
    j = closed
    if j < LOOKBACK_BARS:
        return 0
    close = f.close[j]
    if v.family == "trend":
        short = f.mean(j, v.lookback)
        long = f.mean(j, v.second)
        spread = (short/long-1)
        return 1 if spread > v.threshold else -1 if spread < -v.threshold else 0
    if v.family == "momentum":
        pct = close/f.close[j-v.lookback]-1
        return 1 if pct > v.threshold else -1 if pct < -v.threshold else 0
    if v.family == "mean_revert":
        std = f.std(j, v.lookback)
        z = (close-f.mean(j, v.lookback))/std if std > 0 else 0.0
        return -1 if z >= v.threshold else 1 if z <= -v.threshold else 0
    if v.family == "breakout":
        top = max(f.high[j-v.lookback:j])
        bottom = min(f.low[j-v.lookback:j])
        volume_prior = f.window(f.vsum, j-1, 20)
        if volume_prior <= 0 or f.vol[j] < v.threshold*volume_prior:
            return 0
        return 1 if close > top else -1 if close < bottom else 0
    if v.family == "rsi_revert":
        rsi = f.rsi(j, v.lookback)
        return 1 if rsi < v.threshold else -1 if rsi > 100-v.threshold else 0
    if v.family == "long_control":
        return 1
    if v.family == "control":
        digest = hashlib.sha256(("%s:%s:%s" %
                 (f.ts[j], v.horizon, "control")).encode()).digest()
        return 1 if digest[0] % 2 == 0 else -1
    raise ValueError("unregistered strategy family")


def backtest(candles, variant, symbol="BTC", fee_pct=FEE_PCT,
             extra_cost_pct=STRESS_PCT, funding_events=None,
             leverage=3.0, maintenance_margin_pct=0.5):
    """Hypothetical next-bar fills, funding sensitivities and barrier-only risk.

    Never claims actual exchange liquidation: high/low do not reveal tick path,
    exact maintenance margin or bankruptcy price. Neither SL nor TP is used.
    """
    f = Features(candles)
    total_cost = fee_pct + extra_cost_pct
    if not (0 <= total_cost < 5):
        raise ValueError("invalid cost assumption")
    if not (1 <= leverage <= 20 and 0 <= maintenance_margin_pct < 100/leverage):
        raise ValueError("invalid hypothetical margin assumptions")
    if funding_events is not None:
        validate_rates(funding_events)
    barrier_pct = 100/leverage - maintenance_margin_pct
    events = []
    i = LOOKBACK_BARS + 1
    while i + variant.horizon < len(f.ts):
        side = signal(f, variant, i-1)
        if side == 0:
            i += 1
            continue
        entry_price, exit_price = f.open[i], f.open[i+variant.horizon]
        signed_pct = 100 * side * (exit_price/entry_price-1)
        net_pct = signed_pct-total_cost
        # Trade exists from bar OPEN[i] until OPEN[i+h]; only intrabar
        # extremes for indices i..i+h-1 can trigger a hypothetical barrier.
        touched = (min(f.low[i:i+variant.horizon]) <=
                   entry_price*(1-barrier_pct/100)) if side == 1 else (
                   max(f.high[i:i+variant.horizon]) >=
                   entry_price*(1+barrier_pct/100))
        paid = (payment_pct(funding_events, side, f.ts[i],
                            f.ts[i+variant.horizon]) if funding_events is not None
                else None)
        funded = net_pct-paid if paid is not None else None
        events.append({
            "symbol": symbol, "variant": variant.id, "entry_ts": f.ts[i],
            "exit_ts": f.ts[i+variant.horizon], "side": "LONG" if side > 0 else "SHORT",
            "signed_pct": round(signed_pct, 9),
            "net_pct": round(net_pct, 9),
            "net_R": round(net_pct/R_DENOMINATOR_PCT, 9),
            "settled_funding_paid_pct": round(paid, 9) if paid is not None else None,
            "funding_adjusted_net_pct": round(funded, 9) if funded is not None else None,
            "funding_adjusted_R": round(funded/R_DENOMINATOR_PCT, 9) if funded is not None else None,
            "barrier_touch_proxy": bool(touched),
            "barrier_adverse_move_pct": round(barrier_pct, 6),
        })
        i += variant.horizon  # nonoverlapping per strategy and symbol
    return events


def statistics_for(rows):
    rows = sorted(rows, key=lambda r: (r["exit_ts"], r["symbol"], r["variant"]))
    count = len(rows)
    days = defaultdict(list)
    cumulative, peak, drawdown = 0.0, 0.0, 0.0
    for r in rows:
        day = dt.datetime.fromtimestamp(r["entry_ts"]/1000, dt.timezone.utc).date().isoformat()
        days[day].append(r["net_R"])
        cumulative += r["net_pct"]
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak-cumulative)
    values = [r["net_R"] for r in rows]
    day_means = [statistics.mean(v) for v in days.values()]
    daily_lcb = None
    if len(day_means) >= 4:
        daily_lcb = statistics.mean(day_means) - 1.96 * (
            statistics.stdev(day_means) / math.sqrt(len(day_means)))
    measured = [r["funding_adjusted_R"] for r in rows
                if r.get("funding_adjusted_R") is not None]
    return {
        "n": count, "days": len(days),
        "measured_funding_n": len(measured),
        "funding_adjusted_avg_R": round(statistics.mean(measured), 6)
                                  if count and len(measured) == count else None,
        "barrier_touches": sum(bool(r.get("barrier_touch_proxy")) for r in rows),
        "barrier_model": "high-low threshold flag only; NOT simulated exchange liquidation",
        "win_rate": round(sum(r["net_pct"] > 0 for r in rows)/count, 5) if count else None,
        "avg_R": round(statistics.mean(values), 6) if count else None,
        "day_mean_R": round(statistics.mean(day_means), 6) if days else None,
        "day_lcb_R": round(daily_lcb, 6) if daily_lcb is not None else None,
        "sum_pct_per_trade": round(cumulative, 6),
        "max_sequential_pct_drawdown": round(drawdown, 6),
    }


def walk_forward(datasets, max_variants=300, selections_per_fold=4,
                 funding_by_symbol=None):
    """Three chronological expanding-window trials with 96-bar purging.

    Only training data chooses each fold's candidates. Validation is examined
    repeatedly across daily runs: descriptive WALK-FORWARD, never a final holdout.
    """
    if not datasets:
        raise ValueError("DATA_UNAVAILABLE: no historical datasets")
    if not 1 <= selections_per_fold <= 20:
        raise ValueError("invalid selection budget")
    for bars in datasets.values():
        validate_series(bars, min_bars=400)
    funding_by_symbol = funding_by_symbol or {}
    if any(symbol not in datasets for symbol in funding_by_symbol):
        raise ValueError("unknown symbol in funding mapping")
    start = max(rows[0][0] for rows in datasets.values())
    end = min(rows[-1][0] for rows in datasets.values())
    if end-start < 700*BAR_MS:
        raise ValueError("DATA_UNAVAILABLE: need >=700 overlapping 15m bars across symbols")
    n_bars = (end-start)//BAR_MS+1
    points = [start + int(n_bars*p)*BAR_MS for p in (0.55, 0.70, 0.85)]
    boundaries = list(zip(points, points[1:]+[end+BAR_MS]))
    variants = variant_catalog(max_variants)
    per_variant = {}
    for variant in variants:
        trades = []
        for symbol, rows in sorted(datasets.items()):
            trades.extend(backtest(rows, variant, symbol,
                                   funding_events=funding_by_symbol.get(symbol)))
        per_variant[variant.id] = trades

    fold_reports = []
    combined = defaultdict(list)
    all_chosen = set()
    control_by_fold = []
    for fold_number, (val_start, val_end) in enumerate(boundaries, 1):
        train_cutoff = val_start - EMBARGO_BARS*BAR_MS
        eligible_train = {}
        for v in variants:
            trades = per_variant[v.id]
            sample = [r for r in trades if r["entry_ts"] >= start
                      and r["exit_ts"] < train_cutoff]
            stat = statistics_for(sample)
            if v.family not in ("control", "long_control") and (
                stat["n"] >= 10 and stat["days"] >= 4 and
                stat["day_lcb_R"] is not None and stat["day_lcb_R"] > 0):
                eligible_train[v.id] = stat

        ranked = sorted(eligible_train, key=lambda ident: (
            -eligible_train[ident]["day_lcb_R"],
            -eligible_train[ident]["avg_R"], ident))
        selected_ids = ranked[:selections_per_fold]
        validated = []
        for ident in selected_ids:
            selected = [r for r in per_variant[ident]
                        if val_start <= r["entry_ts"] and r["exit_ts"] < val_end]
            all_chosen.add(ident)
            combined[ident].extend(selected)
            validated.append({"variant_id": ident, "train": eligible_train[ident],
                              "validation": statistics_for(selected)})
        controls = {}
        for v in variants:
            if v.family not in ("control", "long_control"):
                continue
            selected = [r for r in per_variant[v.id]
                        if val_start <= r["entry_ts"] and r["exit_ts"] < val_end]
            controls[v.id] = statistics_for(selected)
        control_by_fold.append(controls)
        fold_reports.append({
            "fold": fold_number, "validation_start_utc":
                dt.datetime.fromtimestamp(val_start/1000, dt.timezone.utc).isoformat(),
            "validation_end_exclusive_utc":
                dt.datetime.fromtimestamp(val_end/1000, dt.timezone.utc).isoformat(),
            "purge_bars": EMBARGO_BARS,
            "train_qualified": len(ranked),
            "selected_for_validation": validated,
            "controls": controls,
        })
    summaries = [{
        "variant_id": v, "walk_forward": statistics_for(combined[v]),
        "folds_selected": sum(any(x["variant_id"] == v
                               for x in fr["selected_for_validation"])
                              for fr in fold_reports)
    } for v in sorted(all_chosen)]
    summaries.sort(key=lambda x: (
        -(x["walk_forward"]["day_lcb_R"] or -999),
        -(x["walk_forward"]["avg_R"] or -999), x["variant_id"]))
    return {
        "schema_version": 1, "factory_version": "v9-param-grid-1",
        "validation_method": "expanding_train_three_chronological_folds_purged_96bars",
        "historical_only": True, "proven_edge": False, "champion": None,
        "measured_funding_symbols": sorted(funding_by_symbol),
        "margin_scenario": {"hypothetical_leverage": 3,
                            "maintenance_margin_pct_assumed": 0.5,
                            "not_actual_liquidation": True},
        "candidates_evaluated": len(variants),
        "datasets_evaluated": len(datasets),
        "common_bars": n_bars,
        "walk_forward_selected": summaries[:25], "folds": fold_reports,
        "limitations": [
            "All signals use the last confirmed candle and hypothetical next-bar OPEN.",
            "Historical OHLCV trading is not an executed or forward paper trade.",
            "No actual fills, exchange liquidation or true slippage are simulated.",
            "Settled historical funding is a constant-notional sensitivity only where coverage is complete.",
            "Intrabar high/low margin proxy does not confirm real liquidation, margin tier or path.",
            "0.10% roundtrip fees plus 0.12% additional hypothetical friction.",
            "Purge between training and validation; validation is REPEATEDLY observed.",
            "Multiple-parameter testing and correlated assets inflate apparent winners.",
            "A frozen untouched future dataset and prospective paper trials are REQUIRED."
        ],
    }
