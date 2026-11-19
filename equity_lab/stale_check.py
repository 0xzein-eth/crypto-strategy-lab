"""Fail-loud freshness alarm for the isolated Nasdaq and LQ45 paper journals.

This is an operational monitor, not an alpha test. It never fetches prices,
modifies journals, backfills observations, or places orders.
"""
import argparse
import datetime as dt
import json
import sys

from equity_lab import forward

UTC = dt.timezone.utc

# Calendar-day buffers intentionally tolerate weekends and ordinary holidays.
STALENESS_BUDGET_DAYS = {"NASDAQ": 5, "LQ45": 7}


def journal_last_session(market):
    """Return the last journal session, or None when no journal exists."""
    if market not in STALENESS_BUDGET_DAYS:
        raise ValueError("MARKET_INVALID: unknown staleness-monitor market")
    event_path, _, _ = forward.state_paths(market)
    if not event_path.exists():
        return None
    events = forward.read_events(market)
    if not events:
        return None
    snapshot = events[-1].get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("INTEGRITY_FAILURE: final event has no snapshot")
    session = snapshot.get("session")
    if not isinstance(session, str):
        raise ValueError("INTEGRITY_FAILURE: final event has no session date")
    # Strict ISO date parsing prevents malformed journal metadata from being
    # misreported as a freshness success.
    parsed = dt.date.fromisoformat(session)
    if parsed.isoformat() != session:
        raise ValueError("INTEGRITY_FAILURE: non-canonical journal session date")
    return session


def check(market, *, now=None):
    """Return (is_stale, detail) for a market; future-dated journals fail closed."""
    if market not in STALENESS_BUDGET_DAYS:
        raise ValueError("MARKET_INVALID: unknown staleness-monitor market")
    now = now or dt.datetime.now(UTC)
    if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("CLOCK_INVALID: timezone-aware current time required")
    today = now.astimezone(UTC).date()
    budget = STALENESS_BUDGET_DAYS[market]
    last_session = journal_last_session(market)
    if last_session is None:
        return True, {
            "market": market, "status": "STALE_NO_JOURNAL",
            "last_market_session": None,
            "staleness_budget_calendar_days": budget,
            "action_required": "Run the dual-equity observer and verify that its new paper epoch is persisted",
        }
    session_date = dt.date.fromisoformat(last_session)
    age_days = (today - session_date).days
    if age_days < 0:
        return True, {
            "market": market, "status": "FUTURE_SESSION",
            "last_market_session": last_session,
            "session_age_calendar_days": age_days,
            "staleness_budget_calendar_days": budget,
            "action_required": "Investigate the future-dated session; do not rewrite or backfill the journal",
        }
    stale = age_days > budget
    return stale, {
        "market": market,
        "last_market_session": last_session,
        "session_age_calendar_days": age_days,
        "staleness_budget_calendar_days": budget,
        "status": "STALE" if stale else "OK",
        "action_required": None if not stale else (
            "Inspect the latest dual-equity-lab workflow and source diagnostics, "
            "then run the observer to capture any still-available authentic EOD session"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--market", choices=tuple(STALENESS_BUDGET_DAYS))
    group.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true", help="print machine-readable detail")
    args = parser.parse_args()
    markets = tuple(STALENESS_BUDGET_DAYS) if args.all else (args.market,)
    details = []
    stale = []
    for market in markets:
        is_stale, detail = check(market)
        stale.append(is_stale)
        details.append(detail)
    if args.json:
        print(json.dumps(details, indent=2, sort_keys=True))
    else:
        for detail in details:
            age = detail.get("session_age_calendar_days")
            suffix = f" ({age}d old)" if age is not None else ""
            print(f"[{detail['status']}] {detail['market']}: "
                  f"last session {detail['last_market_session']}{suffix}")
            if detail.get("action_required"):
                print("       " + detail["action_required"])
    if any(stale):
        sys.exit(1)


if __name__ == "__main__":
    main()
