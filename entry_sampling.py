"""PAPER-only entry-time evidence coverage; NEVER uses P&L or CLOSE outcomes.

Counts ALL immutable prospective OPEN decisions, regardless of whether they
are still OPEN, won, lost or were closed late. Used only to sample genuine
currently offered confirmed signals more evenly; not an alpha estimator.
"""
from collections import Counter
import datetime as dt
import learner

ROLLING_DAYS = 7
UTC = dt.timezone.utc


def recent_confirmed_open_counts(records, moment, days=ROLLING_DAYS):
    """Trailing actual-time counts of confirmed-arm entries; no backfilling.

    Uses ONLY fields frozen at OPEN (strategy, created_at, market_type).
    Doesn't read CLOSE performance, status, normalized_R, win/loss, or
    learner monitoring partitions; a historical OHLCV cache is never used.
    """
    if moment.tzinfo is None:
        raise ValueError("INTEGRITY_FAILURE: naive observation moment")
    if isinstance(days, bool) or not isinstance(days, int) or days < 1 or days > 30:
        raise ValueError("invalid rolling entry days")
    now = moment.astimezone(UTC)
    source = records.values() if isinstance(records, dict) else records
    counts = Counter({name: 0 for name in learner.ADVANCED})
    for record in source:
        arm = record.get("strategy")
        if arm not in counts or record.get("market_type") != "perpetual":
            continue
        at = dt.datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("INTEGRITY_FAILURE: naive historical entry")
        age = (now - at.astimezone(UTC)).total_seconds()
        if 0 <= age < days*86400:
            counts[arm] += 1
    return dict(counts)


def make_opportunity_audit(requested):
    """A run-local, ephemeral counter, never part of the canonical ledger."""
    return {
        "version": "confirmed-entry-opportunity-v1",
        "paper_only": True,
        "training_or_monitoring_returns_used": False,
        "scope": "real fresh market quote, distinct unsampled instrument/15m slot, within quota",
        "requested_new_slots": requested,
        "eligible_quote_symbols": 0,
        "screened_symbol_slots": 0,
        "advanced_source_checks": 0,
        "unavailable_confirmed_candle_slots": 0,
        "slots_with_any_confirmed_signal": 0,
        "slots_with_no_confirmed_signal": 0,
        "no_confirmed_signal_proxy_slots_skipped": 0,
        "no_confirmed_signal_baseline_probes_allowed": 0,
        "no_signal_baseline_probe_percent": 12,
        "confirmed_arm_opportunities": {},
        "new_paper_opens_by_arm": {},
        "skipped_by_symbol_slot_or_capacity": 0,
        "fresh_entry_quote_rejections": 0,
        "recent_7d_confirmed_open_counts": {},
        "note": "Counts ONLY inspected real opportunities. Missing/failed OKX candles are excluded and never counted as genuine no-signal. A 12%-of-unique-symbol-slot fallback probe is permitted after valid candles with NO confirmed signal; monitoring and other CLOSE outcomes never drive fallback inclusion. Strategy evidence still requires independent forward validation.",
    }


NO_CONFIRMED_BASELINE_PROBE_PERCENT = 12


def no_confirmed_baseline_probe(symbol, signal_slot, pct=NO_CONFIRMED_BASELINE_PROBE_PERCENT):
    """Only sparse no-candle-signal control probes; never SELECT winners.

    Hash the original *15-minute* frozen symbol slot, not a later outcome,
    scheduler wall-clock date, or historical backtest score. A control
    sample remains possible in every real market regime without flooding
    the ledger with directional 24h-only baseline hypotheses.
    """
    if (not isinstance(symbol,str) or not symbol or
            isinstance(signal_slot,bool) or not isinstance(signal_slot,int) or
            isinstance(pct,bool) or not isinstance(pct,int) or not 0<=pct<=100):
        raise ValueError("invalid no-signal baseline sampling policy")
    return learner.stable_bucket(
        "no-confirmed-control-probe-v1:%s:%s"%(symbol,signal_slot),100) < pct


def increment(counter, arm):
    counter[arm] = counter.get(arm, 0) + 1
