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
        "slots_with_any_confirmed_signal": 0,
        "slots_with_no_confirmed_signal": 0,
        "confirmed_arm_opportunities": {},
        "new_paper_opens_by_arm": {},
        "skipped_by_symbol_slot_or_capacity": 0,
        "fresh_entry_quote_rejections": 0,
        "recent_7d_confirmed_open_counts": {},
        "note": "Counts candidate opportunities only when evaluated, not all market patterns. Sampled arm counts contain NO CLOSE outcomes, and don't establish edge.",
    }


def increment(counter, arm):
    counter[arm] = counter.get(arm, 0) + 1
