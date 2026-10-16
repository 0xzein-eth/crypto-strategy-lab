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

HORIZONS = (4, 8, 16, 32, 48, 96)  # 1h, 2h, 4h, 8h, 12h, 24h on 15m candles
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
    """Versioned deterministic catalogue; first 1200 IDs remain stable.

    The original 1200-variant order is never silently shuffled: adding new
    families must not rewrite prior experimental hypotheses or introduce
    retrospective selection changes. Expansion is historical/backtest-only.
    """
    if not 1 <= max_variants <= 1600:
        raise ValueError("max_variants must be within 1..1600")

    def drain(by_family, limit):
        output = []
        families = sorted(by_family)
        while len(output) < limit and any(by_family.values()):
            for name in families:
                if by_family[name]:
                    output.append(by_family[name].pop(0))
                    if len(output) >= limit:
                        break
        return output

    original = defaultdict(list)
    for fast, slow, gate, h in product((6, 8, 12, 20), (36, 60),
                                       (0.001, 0.003), HORIZONS):
        if fast < slow:
            original["trend"].append(Variant("trend", fast, gate, slow, h))
    for lookback, gate, h in product((4, 8, 16, 24, 32, 48),
                                     (0.001, 0.002, 0.004, 0.008), HORIZONS):
        original["momentum"].append(Variant("momentum", lookback, gate, 0, h))
    for lookback, z, h in product((12, 20, 32, 48),
                                  (1.3, 1.8, 2.3, 2.8), HORIZONS):
        original["mean_revert"].append(Variant("mean_revert", lookback, z, 0, h))
    for lookback, vol, h in product((12, 20, 40, 60),
                                    (0.8, 1.2, 1.6), HORIZONS):
        original["breakout"].append(Variant("breakout", lookback, vol, 0, h))
    for period, threshold, h in product((7, 14, 21, 28),
                                        (25, 30, 35, 40), HORIZONS):
        original["rsi_revert"].append(Variant("rsi_revert", period, threshold, 0, h))
    for h in HORIZONS:
        original["control"].extend([
            Variant("control", 0, 0.0, 0, h),
            Variant("long_control", 0, 0.0, 0, h)])

    selected = drain(original, min(500, max_variants))
    if max_variants > 500:
        extended = original  # include any remaining legacy hypotheses first
        for lookback, vol_gate, h in product((12, 20, 32, 48),
                                             (0.85, 1.1, 1.35), HORIZONS):
            extended["donchian"].append(
                Variant("donchian", lookback, vol_gate, 0, h))
        for lookback, z, h in product((12, 20, 32, 48),
                                      (0.6, 1.0, 1.4, 1.8), HORIZONS):
            extended["ztrend"].append(Variant("ztrend", lookback, z, 0, h))
        for period, threshold, h in product((7, 14, 21, 28),
                                            (55, 60, 65, 70), HORIZONS):
            extended["rsi_trend"].append(
                Variant("rsi_trend", period, threshold, 0, h))
        selected.extend(drain(extended, min(750, max_variants) - len(selected)))
    if max_variants > 750:
        # A NEW versioned expansion: the first 750 experiment IDs/order are frozen.
        # Additional arms do not alter the original selection and results.
        new_families = defaultdict(list)
        for lookback, ratio, h in product(
                (12, 16, 20, 32, 48), (0.5, 0.65, 0.8, 0.95, 1.1, 1.25), HORIZONS):
            new_families["compression_breakout"].append(
                Variant("compression_breakout", lookback, ratio, 0, h))
        for lookback, magnitude, h in product(
                (8, 12, 16, 24, 32), (0.5, 0.75, 1.0, 1.25, 1.5, 1.75), HORIZONS):
            new_families["volatility_impulse"].append(
                Variant("volatility_impulse", lookback, magnitude, 0, h))
        for lookback, threshold, h in product(
                (8, 12, 16, 24, 32), (0.0, 0.1, 0.2, 0.3, 0.4, 0.5), HORIZONS):
            new_families["trend_reclaim"].append(
                Variant("trend_reclaim", lookback, threshold, 50, h))
        selected.extend(drain(new_families, min(1200,max_variants) - len(selected)))
    if max_variants > 1200:
        # Experiment catalogue v5. First 1200 IDs/order must remain unchanged.
        novel = defaultdict(list)
        for lookback, volume_multiple, h in product(
                (8, 12, 16, 20, 32, 48, 60),
                (1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0), HORIZONS):
            novel["volume_climax_fade"].append(
                Variant("volume_climax_fade",lookback,volume_multiple,0,h))
        for period, threshold, h in product(
                (7, 10, 14, 18, 21, 28, 35), (25, 30, 35, 40, 45, 50), HORIZONS):
            novel["rsi_recovery"].append(
                Variant("rsi_recovery",period,threshold,0,h))
        selected.extend(drain(novel,max_variants-len(selected)))
    if len(selected) != max_variants or len({v.id for v in selected}) != len(selected):
        raise AssertionError("insufficient unique predeclared research hypotheses")
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
    if v.family == "donchian":
        top=max(f.high[j-v.lookback:j])
        bottom=min(f.low[j-v.lookback:j])
        prior_volume=f.window(f.vsum,j-1,20)
        if prior_volume<=0 or f.vol[j]<v.threshold*prior_volume:
            return 0
        return 1 if close>top else -1 if close<bottom else 0
    if v.family == "ztrend":
        sd=f.std(j,v.lookback)
        z=(close-f.mean(j,v.lookback))/sd if sd>0 else 0.0
        trend=f.mean(j,20)/f.mean(j,50)-1
        return (1 if z>v.threshold and trend>0
                else -1 if z< -v.threshold and trend<0 else 0)
    if v.family == "rsi_trend":
        rsi=f.rsi(j,v.lookback)
        trend_base=f.mean(j,50)
        return (1 if rsi>v.threshold and close>trend_base
                else -1 if rsi<100-v.threshold and close<trend_base else 0)
    if v.family == "compression_breakout":
        n = v.lookback
        if j < 2*n:
            return 0
        preceding_high = max(f.high[j-n:j])
        preceding_low = min(f.low[j-n:j])
        previous_width = max(f.high[j-2*n:j-n])-min(f.low[j-2*n:j-n])
        if previous_width <= 0 or preceding_high-preceding_low > v.threshold*previous_width:
            return 0
        return 1 if close > preceding_high else -1 if close < preceding_low else 0
    if v.family == "volatility_impulse":
        n = v.lookback
        prior_range = sum(f.high[k]-f.low[k] for k in range(j-n,j))/n
        if prior_range <= 0:
            return 0
        delta = close-f.close[j-1]
        return 1 if delta > v.threshold*prior_range else -1 if delta < -v.threshold*prior_range else 0
    if v.family == "trend_reclaim":
        n = v.lookback
        current_fast = f.mean(j,n)
        previous_fast = f.mean(j-1,n)
        slow = f.mean(j,v.second)
        reference_range = sum(f.high[k]-f.low[k] for k in range(j-n,j))/n
        if reference_range <= 0:
            return 0
        return (1 if current_fast > slow and f.close[j-1] <= previous_fast and
                close > current_fast + v.threshold*reference_range
                else -1 if current_fast < slow and f.close[j-1] >= previous_fast and
                close < current_fast - v.threshold*reference_range else 0)
    if v.family == "volume_climax_fade":
        prior_volume=f.window(f.vsum,j-1,v.lookback)
        bar_range=f.high[j]-f.low[j]
        if prior_volume<=0 or bar_range<=0 or f.vol[j]<v.threshold*prior_volume:
            return 0
        upper_wick=(f.high[j]-max(close,f.open[j]))/bar_range
        lower_wick=(min(close,f.open[j])-f.low[j])/bar_range
        return (-1 if upper_wick>=0.45 and close<f.open[j]
                else 1 if lower_wick>=0.45 and close>f.open[j] else 0)
    if v.family == "rsi_recovery":
        previous=f.rsi(j-1,v.lookback)
        current=f.rsi(j,v.lookback)
        return (1 if previous<v.threshold<=current and close>f.close[j-1]
                else -1 if previous>100-v.threshold>=current and
                close<f.close[j-1] else 0)
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
    # Fixed additional 25bp round-trip impact on top of the 0.22% base.
    # Cluster across entry UTC days, not dependent per-trade samples.
    extra_cost_R = 0.25 / R_DENOMINATOR_PCT
    stress_days = [m-extra_cost_R for m in day_means]
    stress_lcb = (statistics.mean(stress_days) - 1.96 *
                  statistics.stdev(stress_days) / math.sqrt(len(stress_days))
                  if len(stress_days) >= 4 else None)
    fully_funded = count > 0 and len(measured) == count
    return {
        "n": count, "days": len(days),
        "measured_funding_n": len(measured),
        "extra_25bps_after_cost_avg_R": round(
            statistics.mean(values)-extra_cost_R, 6) if count else None,
        "extra_25bps_day_cluster_lcb_R": round(stress_lcb, 6)
                                          if stress_lcb is not None else None,
        "funding_plus_extra_25bps_avg_R": round(
            statistics.mean(measured)-extra_cost_R, 6) if fully_funded else None,
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
    variants_by_id = {v.id:v for v in variants}
    # Bounded memory: keep aggregate TRAIN statistics, not every trade from
    # every variant. Recompute only frozen TRAIN-selected validation/shadow
    # arms when required; never use validation outcomes for arm selection.
    training_by_fold = [dict() for _ in boundaries]
    controls_by_fold = [dict() for _ in boundaries]
    trade_counts_by_family = defaultdict(int)
    trade_counts_by_symbol = defaultdict(int)
    simulated_trades_total = 0
    for variant in variants:
        trades = []
        for symbol, rows in sorted(datasets.items()):
            batch = backtest(rows,variant,symbol,
                             funding_events=funding_by_symbol.get(symbol))
            trades.extend(batch)
            trade_counts_by_symbol[symbol] += len(batch)
            simulated_trades_total += len(batch)
        trade_counts_by_family[variant.family] += len(trades)
        for idx,(val_start,val_end) in enumerate(boundaries):
            cutoff=val_start-EMBARGO_BARS*BAR_MS
            if variant.family not in ("control","long_control"):
                train_rows=[r for r in trades if r["entry_ts"]>=start
                            and r["exit_ts"]<cutoff]
                training_by_fold[idx][variant.id]=statistics_for(train_rows)
            else:
                validation_rows=[r for r in trades if
                                 val_start<=r["entry_ts"] and r["exit_ts"]<val_end]
                controls_by_fold[idx][variant.id]=statistics_for(validation_rows)
        # Release variant-specific trade objects before processing next arm.
        del trades

    def validation_rows_for(ident,val_start,val_end):
        """Re-run only a frozen selected/shadow arm's historical validation."""
        variant=variants_by_id[ident]
        result=[]
        for symbol,rows in sorted(datasets.items()):
            for trade in backtest(rows,variant,symbol,
                                  funding_events=funding_by_symbol.get(symbol)):
                if val_start<=trade["entry_ts"] and trade["exit_ts"]<val_end:
                    result.append(trade)
        return result

    fold_reports = []
    combined = defaultdict(list)
    all_chosen = set()
    control_by_fold = []
    for fold_number, (val_start, val_end) in enumerate(boundaries, 1):
        train_cutoff = val_start - EMBARGO_BARS*BAR_MS
        eligible_train = {}
        train_screen = []
        disqualified = defaultdict(int)
        for v in variants:
            if v.family in ("control", "long_control"):
                continue
            stat = training_by_fold[fold_number-1][v.id]
            reasons=[]
            if stat["n"] < 10:
                reasons.append("TOO_FEW_TRAINING_TRADES")
            if stat["days"] < 4:
                reasons.append("TOO_FEW_TRAINING_UTC_DAYS")
            if stat["day_lcb_R"] is None or stat["day_lcb_R"] <= 0:
                reasons.append("NONPOSITIVE_OR_UNAVAILABLE_DAILY_LCB")
            for reason in reasons:
                disqualified[reason]+=1
            if not reasons:
                eligible_train[v.id] = stat
            elif stat["n"]>=10 and stat["days"]>=4:
                # Reporting only: do not select these failed hypotheses for
                # validation and NEVER inspect their future validation bars.
                train_screen.append({
                    "variant_id":v.id,"family":v.family,
                    "training_trades":stat["n"],
                    "training_days":stat["days"],
                    "training_after_fee_mean_R":stat["avg_R"],
                    "training_day_cluster_lcb_R":stat["day_lcb_R"],
                    "blocking_reasons":reasons,
                })
        train_screen.sort(key=lambda r:(
            -(r["training_day_cluster_lcb_R"] if r["training_day_cluster_lcb_R"] is not None else -1e9),
            -r["training_trades"],r["variant_id"]))

        ranked = sorted(eligible_train, key=lambda ident: (
            -eligible_train[ident]["day_lcb_R"],
            -eligible_train[ident]["avg_R"], ident))
        selected_ids = ranked[:selections_per_fold]
        validated = []
        for ident in selected_ids:
            selected = validation_rows_for(ident,val_start,val_end)
            all_chosen.add(ident)
            combined[ident].extend(selected)
            validated.append({"variant_id": ident, "train": eligible_train[ident],
                              "validation": statistics_for(selected)})
        controls = controls_by_fold[fold_number-1]
        control_by_fold.append(controls)
        # Predeclared shadow-audit budget, selected SOLELY from the
        # disqualified TRAINING screen. This intentionally evaluates a
        # small number of rejected ideas in future chronological folds to
        # learn whether apparent weak ideas generalize. Crucially these
        # are NEVER included in selected_for_validation, all_chosen,
        # combined, the review queue, or the online paper allocator.
        # One candidate per family first: correlated parameter variants
        # must not consume all the descriptive diagnostic space.
        shadow_picks = []
        seen_families = set()
        for candidate in train_screen:
            if candidate["family"] not in seen_families:
                shadow_picks.append(candidate)
                seen_families.add(candidate["family"])
            if len(shadow_picks) >= 4:
                break
        if len(shadow_picks) < 4:
            chosen_ids = {c["variant_id"] for c in shadow_picks}
            for candidate in train_screen:
                if candidate["variant_id"] not in chosen_ids:
                    shadow_picks.append(candidate)
                if len(shadow_picks) >= 4:
                    break
        shadow_evaluations = []
        for candidate in shadow_picks:
            ident = candidate["variant_id"]
            future_stat = statistics_for(
                validation_rows_for(ident,val_start,val_end))
            horizon = int(ident.rsplit("-H", 1)[1])
            comparators = [
                c["avg_R"] for name,c in controls.items()
                if name.endswith("-H" + str(horizon))
                and c["avg_R"] is not None and c["n"] >= 10
            ]
            baseline = max(comparators) if len(comparators) == 2 else None
            shadow_evaluations.append({
                "variant_id":ident,"family":candidate["family"],
                "training_failed_reasons":candidate["blocking_reasons"],
                "training_day_cluster_lcb_R":candidate["training_day_cluster_lcb_R"],
                "shadow_validation":future_stat,
                "compared_both_control_means":baseline is not None,
                "descriptive_delta_vs_better_control_mean_R":(
                    round(future_stat["avg_R"] - baseline,6)
                    if baseline is not None and future_stat["avg_R"] is not None
                    else None),
                "eligible_for_promotion":False,
                "status":"SHADOW_EXPLORATORY_ONLY",
            })
        fold_reports.append({
            "fold": fold_number, "validation_start_utc":
                dt.datetime.fromtimestamp(val_start/1000, dt.timezone.utc).isoformat(),
            "validation_end_exclusive_utc":
                dt.datetime.fromtimestamp(val_end/1000, dt.timezone.utc).isoformat(),
            "purge_bars": EMBARGO_BARS,
            "train_qualified": len(ranked),
            "training_screen_rejection_counts":dict(sorted(disqualified.items())),
            "highest_scoring_unqualified_training_only":train_screen[:10],
            "training_screen_note":(
                "Training-only candidate choice; highest rejected variants are NOT winners; "
                "shadow validation is explicitly exploratory and repeatedly inspected"),
            "shadow_evaluations":shadow_evaluations,
            "shadow_policy":(
                "At most four TRAINING-selected failed hypotheses with family "
                "diversity, scored only on chronological purged validation; "
                "never added to promotion queue or forward allocation"),
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
    family_counts = {name:sum(v.family==name for v in variants)
                     for name in sorted({v.family for v in variants})}
    return {
        "schema_version": 1, "factory_version": "v9-param-grid-5-1600-streaming-stress25bp",
        "validation_method": "expanding_train_three_chronological_folds_purged_96bars",
        "historical_only": True, "proven_edge": False, "champion": None,
        "measured_funding_symbols": sorted(funding_by_symbol),
        "margin_scenario": {"hypothetical_leverage": 3,
                            "maintenance_margin_pct_assumed": 0.5,
                            "not_actual_liquidation": True},
        "candidates_evaluated": len(variants),
        "hypothetical_historical_trades_tested": simulated_trades_total,
        "hypothetical_trades_by_family": dict(sorted(trade_counts_by_family.items())),
        "hypothetical_trades_by_symbol": dict(sorted(trade_counts_by_symbol.items())),
        "simulation_accounting_note": (
            "Overlapping hypothetical historical trades across correlated "
            "variants are NOT independent observations, forward paper fills, "
            "or evidence of a profitable trading strategy."),
        "memory_policy": "aggregate_training_then_recompute_only_selected_validation",
        "predeclared_variants_by_family": family_counts,
        "hypothesis_selection_policy": (
            "First 1200 IDs unchanged; new deterministic families historical-only;"
            " shadow evaluations of failed training variants NEVER promoted;"
            " not an independent alpha test"),
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
            "An extra predeclared 0.25% roundtrip impact is stress-tested on UTC day clusters; no actual fill data.",
            "Shadow evaluations for training-rejected hypotheses are exploratory, not formal candidate selection.",
            "Both ordinary and shadow walk-forward validation are REPEATEDLY inspected, not an untouched final holdout.",
            "Purge between training and validation; validation is REPEATEDLY observed.",
            "1600 parameter variants expand multiplicity; no family-wise alpha correction or tradable-edge claim.",
            "Multiple-parameter testing and correlated assets inflate apparent winners.",
            "A frozen untouched future dataset and prospective paper trials are REQUIRED."
        ],
    }
