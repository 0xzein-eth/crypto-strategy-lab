"""Leakage-aware supervised dataset builder for PAPER-only research.

Features are reconstructed only from frozen OPEN-time candle evidence.
Labels are attached only after a valid, timely fixed-horizon CLOSE. This
module does not alter the canonical ledger or choose/submit trades.
"""
import datetime as dt
import math

import learner
import universe

UTC = dt.timezone.utc
STRATEGIES = learner.BASELINES + learner.ADVANCED
HORIZONS = (1, 2, 4, 8, 12, 24)

BASE_FEATURES = (
    "close_vs_sma20_pct", "close_vs_sma50_pct", "sma20_vs_sma50_pct",
    "sma20_slope_pct", "sma50_slope_pct", "rsi14", "rsi14_change",
    "z20", "atr14_pct", "close_vs_prev_high_pct",
    "close_vs_prev_low_pct", "vol_ratio", "candle_body_pct",
    "upper_wick_ratio", "lower_wick_ratio", "prior20_range_pct",
    "older20_range_pct", "range_compression_ratio",
    "prior20_mean_range_pct", "close_vs_vwap20_pct", "vwap20_missing",
    "entry_regime_up",
)
CATEGORY_FEATURES = tuple(
    [f"side_{side}" for side in ("LONG", "SHORT")] +
    [f"horizon_{hours}h" for hours in HORIZONS] +
    [f"symbol_{symbol}" for symbol in universe.SYMBOLS] +
    [f"strategy_{strategy}" for strategy in STRATEGIES]
)
FEATURE_NAMES = BASE_FEATURES + CATEGORY_FEATURES


def _time(value):
    if not isinstance(value, str):
        raise ValueError("DATA_INVALID: timestamp missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("DATA_INVALID: timestamp malformed") from exc
    if parsed.tzinfo is None:
        raise ValueError("DATA_INVALID: timestamp timezone required")
    return parsed.astimezone(UTC)


def _number(evidence, key):
    value = evidence.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("FEATURE_INVALID: " + key)
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("FEATURE_INVALID: " + key)
    return value


def _pct(value, reference):
    if reference <= 0:
        raise ValueError("FEATURE_INVALID: nonpositive reference")
    return (value / reference - 1.0) * 100.0


def feature_values(record):
    """Create a fixed-schema vector from OPEN evidence and metadata only."""
    ev = record.get("evidence")
    if not isinstance(ev, dict) or ev.get("bar_span") != "15m confirmed OKX USDT-SWAP":
        raise ValueError("FEATURE_INVALID: no confirmed 15m evidence")
    close = _number(ev, "last_close")
    op = _number(ev, "last_open")
    high = _number(ev, "last_high")
    low = _number(ev, "last_low")
    sma20 = _number(ev, "sma20")
    sma50 = _number(ev, "sma50")
    sma20prev = _number(ev, "sma20prev")
    sma50prev = _number(ev, "sma50prev")
    rsi = _number(ev, "rsi14")
    rsi_prev = _number(ev, "rsi14prev")
    atr = _number(ev, "atr14")
    prev_high = _number(ev, "prev_high20")
    prev_low = _number(ev, "prev_low20")
    volume_ratio = _number(ev, "vol_ratio")
    prior_width = _number(ev, "prior20_range_width")
    older_width = _number(ev, "older20_range_width")
    prior_mean_range = _number(ev, "prior20_mean_range")
    upper_wick = _number(ev, "upper_wick_ratio")
    lower_wick = _number(ev, "lower_wick_ratio")
    vwap = ev.get("vwap20")
    if close <= 0 or high < low or high == low or atr <= 0:
        raise ValueError("FEATURE_INVALID: invalid candle geometry")
    vwap_missing = vwap is None
    vwap_gap = 0.0 if vwap_missing else _pct(_number(ev, "vwap20"), close)
    values = {
        "close_vs_sma20_pct": _pct(close, sma20),
        "close_vs_sma50_pct": _pct(close, sma50),
        "sma20_vs_sma50_pct": _pct(sma20, sma50),
        "sma20_slope_pct": _pct(sma20, sma20prev),
        "sma50_slope_pct": _pct(sma50, sma50prev),
        "rsi14": rsi,
        "rsi14_change": rsi - rsi_prev,
        "z20": _number(ev, "z20"),
        "atr14_pct": atr / close * 100.0,
        "close_vs_prev_high_pct": _pct(close, prev_high),
        "close_vs_prev_low_pct": _pct(close, prev_low),
        "vol_ratio": volume_ratio,
        "candle_body_pct": (close - op) / (high - low) * 100.0,
        "upper_wick_ratio": upper_wick,
        "lower_wick_ratio": lower_wick,
        "prior20_range_pct": prior_width / close * 100.0,
        "older20_range_pct": older_width / close * 100.0,
        "range_compression_ratio": prior_width / older_width if older_width > 0 else 0.0,
        "prior20_mean_range_pct": prior_mean_range / close * 100.0,
        "close_vs_vwap20_pct": vwap_gap,
        "vwap20_missing": float(vwap_missing),
        "entry_regime_up": float(record.get("regime") == "24h_up"),
    }
    side = record.get("side")
    horizon = record.get("horizon_hours")
    symbol = record.get("symbol")
    strategy = record.get("strategy")
    if (side not in ("LONG", "SHORT") or horizon not in HORIZONS or
            symbol not in universe.SYMBOLS or strategy not in STRATEGIES):
        raise ValueError("FEATURE_INVALID: unregistered categorical input")
    for item in CATEGORY_FEATURES:
        values[item] = 0.0
    values["side_" + side] = 1.0
    values[f"horizon_{horizon}h"] = 1.0
    values["symbol_" + symbol] = 1.0
    values["strategy_" + strategy] = 1.0
    result = [float(values[name]) for name in FEATURE_NAMES]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("FEATURE_INVALID: nonfinite transformed feature")
    return dict(zip(FEATURE_NAMES, result))


def eligible_closed(record):
    """Require a real, timely, same-venue perpetual outcome and frozen OPEN evidence."""
    try:
        if (record.get("status") != "CLOSED" or
                record.get("market_type") != "perpetual" or
                record.get("late_excluded", True) is not False or
                record.get("provider") != "okx-swap" or
                record.get("horizon_hours") not in HORIZONS):
            return False
        opened = _time(record["created_at"])
        due = _time(record["evaluate_at"])
        observed = _time(record["exit_observed_at"])
        resolved = _time(record["resolved_at"])
        if due <= opened or observed < due or resolved < observed:
            return False
        feature_values(record)
        target_r = learner.research_R(record)
        return math.isfinite(float(target_r))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def build_dataset(records):
    """Return labeled examples; target is positive net research R after costs."""
    values = records.values() if isinstance(records, dict) else records
    examples = []
    excluded = 0
    for record in values:
        if not eligible_closed(record):
            excluded += 1
            continue
        target_r = float(learner.research_R(record))
        examples.append({
            "record_id": record["id"],
            "entry_at": record["created_at"],
            "evaluate_at": record["evaluate_at"],
            "label_available_at": record["resolved_at"],
            "features": feature_values(record),
            "target_r": target_r,
            "label": int(target_r > 0.0),
            "label_definition": "1 iff post-fee and frozen stress-adjusted research R > 0",
        })
    examples.sort(key=lambda row: (row["entry_at"], row["record_id"]))
    return {
        "schema": "crypto-paper-supervised-dataset-v1",
        "feature_names": list(FEATURE_NAMES),
        "examples": examples,
        "eligible_examples": len(examples),
        "excluded_records": excluded,
        "target_definition": "positive net research R after frozen stress/legacy cost haircut",
        "features_are_open_time_only": True,
        "labels_available_only_after_evaluate_at": True,
        "spot_and_late_outcomes_excluded": True,
        "not_for_live_orders": True,
    }


def chronological_split(dataset, validation_fraction=0.20, embargo_hours=24):
    """Chronological train/diagnostic-validation split with outcome-time purge.

    Historical validation has previously been inspected; it is diagnostic,
    not an untouched final holdout. A future prospective holdout must be frozen
    after this model version and prediction policy are registered.
    """
    if not 0.05 <= validation_fraction <= 0.40:
        raise ValueError("invalid validation fraction")
    if not 0 <= embargo_hours <= 48:
        raise ValueError("invalid embargo")
    rows = dataset.get("examples", [])
    days = sorted({_time(row["entry_at"]).date().isoformat() for row in rows})
    if len(days) < 5:
        raise ValueError("INSUFFICIENT_DATA: at least five entry UTC days required")
    boundary_index = max(1, min(len(days)-1, int(len(days)*(1-validation_fraction))))
    validation_start = dt.datetime.combine(
        dt.date.fromisoformat(days[boundary_index]), dt.time.min, tzinfo=UTC)
    embargo = dt.timedelta(hours=embargo_hours)
    train, validation, purged = [], [], 0
    for row in rows:
        entry = _time(row["entry_at"])
        label_at = _time(row["label_available_at"])
        if entry >= validation_start:
            validation.append(row)
        elif entry < validation_start - embargo and label_at < validation_start:
            train.append(row)
        else:
            purged += 1
    if not train or not validation:
        raise ValueError("INSUFFICIENT_DATA: empty chronological split")
    return {
        "train": train,
        "validation": validation,
        "validation_start_utc": validation_start.isoformat().replace("+00:00", "Z"),
        "purged_training_rows": purged,
        "train_entry_days": len({_time(x["entry_at"]).date() for x in train}),
        "validation_entry_days": len({_time(x["entry_at"]).date() for x in validation}),
        "historical_validation_previously_inspected": True,
        "validation_is_pristine_holdout": False,
        "future_prospective_holdout_required": True,
        "max_horizon_embargo_hours": embargo_hours,
    }
