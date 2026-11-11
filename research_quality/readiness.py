"""Read-only roadmap acceptance evidence from verified raw journals.

No market requests, ledger writes, trial tuning or strategy promotion.
Integrity errors fail the CLI; missing future evidence remains a separate
research blocker even when replay is sound.
"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import audit as legacy
from equity_lab import forward as equities, universe
from research_quality import audit as economic
from v2 import data_contract, forward_paper, frozen_trial, history_warehouse
from v2 import observation_health, shadow_research

ROOT=Path(__file__).resolve().parents[1]
UTC=dt.timezone.utc


def reconcile(path,expected):
    if not path.is_file() or json.loads(path.read_text(encoding="utf-8"))!=expected:
        raise ValueError("INTEGRITY_FAILURE: missing/divergent derived output: "+path.name)


def verify_crypto_v2():
    events=forward_paper.read_events()
    if not events:
        raise ValueError("SOURCE_MISSING: no crypto v2 observations")
    report,curve=forward_paper.replay(events)
    reconcile(forward_paper.REPORT,report)
    reconcile(forward_paper.CURVE,curve)
    reconcile(forward_paper.SHADOW_REPORT,shadow_research.assess(events))
    return events,report


def warehouse_inventory():
    manifest_path=history_warehouse.WAREHOUSE/"manifest.json"
    saved=json.loads(manifest_path.read_text(encoding="utf-8"))
    result=data_contract.inventory(
        forward_paper.SYMBOLS,
        price_loader=lambda symbol:history_warehouse.load(symbol,"candles"),
        funding_loader=lambda symbol:history_warehouse.load(symbol,"settled_funding"))
    if result["markets_unavailable_or_invalid"]:
        raise ValueError("INTEGRITY_FAILURE: invalid warehouse data")
    for symbol,actual in result["verified_market_manifests"].items():
        recorded=saved["symbols"][symbol]
        if (recorded["price_hash_sha256"]!=actual["price_dataset_hash_sha256"] or
                recorded["confirmed_bars"]!=actual["price_bar_count"] or
                recorded["funding_events_sha256"]!=actual["funding_hash_sha256"] or
                recorded["funding_events"]!=actual["settled_funding_events"]):
            raise ValueError("INTEGRITY_FAILURE: warehouse manifest mismatch: "+symbol)
    return result


def run_check(name,fn,results):
    try:
        results[name]={"status":"VERIFIED",**fn()}
    except (ValueError,OSError,KeyError,TypeError) as exc:
        results[name]={"status":"FAILED","error":type(exc).__name__+": "+str(exc)[:240]}


def inspect(*,now=None):
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("CLOCK_INVALID: aware audit time required")
    checks={}

    def crypto_v8():
        verified=legacy.verify()
        report=json.loads((ROOT/"data/report.json").read_text(encoding="utf-8"))
        return {"ledger":verified,"economics":economic.historic_crypto(report)}

    def crypto_v2():
        events,report=verify_crypto_v2()
        # Only frozen trial phase/maturity counts, never candidate outcomes.
        trial=frozen_trial.evaluate(report,shadow_research.assess(events),now=now)
        return {"observations":len(events),"tip":events[-1]["hash"],
                "availability":observation_health.summarize(events,now=now),
                "trial_phase":trial["phase"],
                "trial_results_withheld":trial["results_withheld"],
                "funding_complete":report["funding_source_complete"],
                "full_cost_performance_proven":False}

    def equity(market):
        events,report,_=equities.verify_saved(market)
        if not events:
            raise ValueError("SOURCE_MISSING: no equity observations")
        config=universe.MARKETS[market]
        from zoneinfo import ZoneInfo
        today=now.astimezone(ZoneInfo(config["timezone"])).date()
        expiry=config["membership_expiry"]
        return {"observations":len(events),"tip":events[-1]["hash"],
                "latest_observed_utc":events[-1]["snapshot"]["observed_at_utc"],
                "last_session":report["last_market_session"],
                "session_age_calendar_days":(today-dt.date.fromisoformat(report["last_market_session"])).days,
                "membership_expiry":expiry,
                "membership_current":expiry is None or today<=dt.date.fromisoformat(expiry),
                "last_replayed_policy":report["schema"],
                "economics":economic.equity(report)}

    run_check("crypto_v8",crypto_v8,checks)
    run_check("crypto_v2",crypto_v2,checks)
    for market in ("NASDAQ","LQ45"):
        run_check(market,lambda market=market:equity(market),checks)
    run_check("warehouse",lambda:{"inventory":warehouse_inventory()},checks)
    if (ROOT/"adaptive_state/observations").exists():
        def adaptive():
            from adaptive_lab.engine import verify_saved
            events,report=verify_saved()
            return {"observations":len(events),"tip":report["last_source_hash"],
                    "active_tier_counts":report["active_tier_counts"],
                    "candidate_reviews":len(report["candidates_for_human_review"]),
                    "real_orders":report["real_orders"]}
        run_check("adaptive_crypto_shadow",adaptive,checks)

    # Stable input provenance lets repeated runs identify precisely which
    # evidence changed; no report is considered authoritative without replay.
    provenance={}
    for folder in ("data","v2_state","equity_state","v2_history","adaptive_state","adaptive_history"):
        for path in sorted((ROOT/folder).rglob("*")):
            if path.is_file():
                provenance[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    sources=list(ROOT.glob("*.py"))
    for package in ("v2","equity_lab","stock_lab","research_quality","research_v9","adaptive_lab"):
        sources.extend((ROOT/package).rglob("*.py"))
    code_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(sources)}
    revision=subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],
                            check=True,capture_output=True,text=True).stdout.strip()
    integrity_ok=all(row["status"]=="VERIFIED" for row in checks.values())
    blockers=["UNMEASURED_FULL_FUNDING_AND_EXECUTION_COSTS",
              "INCOMPLETE_OFFICIAL_EQUITY_CALENDAR_AND_CORPORATE_ACTION_MODEL",
              "INDEPENDENT_FUTURE_TRIAL_AND_HUMAN_REVIEW_REQUIRED"]
    if not integrity_ok:
        blockers.insert(0,"INTEGRITY_OR_SOURCE_FAILURE")
    if checks.get("LQ45",{}).get("membership_current") is False:
        blockers.append("LQ45_MEMBERSHIP_EXPIRED_STOP_NEW_ENTRIES")
    if checks.get("crypto_v2",{}).get("availability",{}).get("status") in (
            "STALE","BELOW_90_PERCENT_TARGET"):
        blockers.append("CRYPTO_OBSERVATION_COVERAGE_BELOW_TARGET")
    return {"schema":"roadmap-readiness-replay-audit-v1",
            "asof_utc":now.astimezone(UTC).isoformat(),
            "integrity_verified":integrity_ok,"checks":checks,
            "research_ready_for_champion_review":False,
            "research_blockers":blockers,
            "input_files_sha256":provenance,
            "code_revision":revision,"code_files_sha256":code_hashes,
            "real_orders_authorized":False,
            "frozen_trial_end_exclusive_utc":frozen_trial.END.isoformat()}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output",type=Path,help="Write artifact outside repository only")
    args=cli.parse_args()
    if args.output and args.output.resolve().is_relative_to(ROOT):
        cli.error("audit artifacts must be outside the checkout; preserve evidence")
    report=inspect()
    text=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding="utf-8")
        print(json.dumps({"integrity_verified":report["integrity_verified"],
                          "checks":{k:v["status"] for k,v in report["checks"].items()},
                          "research_blockers":report["research_blockers"]},sort_keys=True))
    else:
        print(text,end="")
    return 0 if report["integrity_verified"] else 1


if __name__=="__main__":
    raise SystemExit(main())
