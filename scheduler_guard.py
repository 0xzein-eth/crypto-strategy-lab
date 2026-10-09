#!/usr/bin/env python3
"""Independent, auditable GitHub Actions schedule guardian (paper only).

Reads the current DEFAULT-BRANCH canonical report through the GitHub API,
checks the paper workflow's queue, and requests at most one authenticated
workflow_dispatch when a real observation is overdue.

The guardian never calls an exchange, writes the event ledger, or guesses
historical prices. A *GitHub* scheduler outage can still stop BOTH clocks.
"""
import argparse
import base64
import binascii
import datetime as dt
import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.request

WORKFLOW = "lab.yml"
MAX_REPORT_AGE_MINUTES = 25
RECENT_RUN_COOLDOWN_MINUTES = 12
# Paper workflow can intentionally run a bounded 6x10min recovery window.
# Its Actions job timeout is 85min; allow runner-queue overhead before
# treating an active job as stuck. Still fail closed at 100min.
PENDING_RUN_ALERT_MINUTES = 100
BASE = "https://api.github.com"
UTC = dt.timezone.utc
REPOSITORY_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*/[a-zA-Z0-9_][a-zA-Z0-9_.-]*$")


def utc(value):
    """Strictly parse GitHub/report ISO datetimes without interpreting local time."""
    if not isinstance(value, str):
        raise ValueError("DATA_INVALID: timestamp must be a string")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: timestamp missing timezone")
    return parsed.astimezone(UTC)


def minutes_since(stamp, now):
    diff = (now - utc(stamp)).total_seconds() / 60
    if diff < -5:
        raise ValueError("CLOCK_INTEGRITY: timestamp is in the future")
    return round(diff, 3)


def decode_report(doc):
    """The authoritative report is fetched from main, not a stale checkout."""
    if not isinstance(doc, dict) or doc.get("encoding") != "base64":
        raise ValueError("DATA_INVALID: expected base64 GitHub contents response")
    try:
        content = base64.b64decode(doc["content"], validate=False)
        report = json.loads(content.decode("utf-8"))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError,
            binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("DATA_INVALID: cannot decode authoritative report") from exc
    if (not isinstance(report, dict) or report.get("schema_version") != 8
            or not isinstance(report.get("timestamp"), str)
            or not isinstance(report.get("verified_events"), int)
            or report["verified_events"] <= 0):
        raise ValueError("INTEGRITY_FAILURE: unexpected canonical paper report")
    return report


def evaluate(report, workflow_runs, now, threshold_minutes=MAX_REPORT_AGE_MINUTES,
             cooldown_minutes=RECENT_RUN_COOLDOWN_MINUTES):
    """Pure decision function, independent of all clocks, network, and tokens."""
    if now.tzinfo is None:
        raise ValueError("CLOCK_INTEGRITY: naive guardian clock")
    if not 5 <= threshold_minutes <= 120 or not 1 <= cooldown_minutes <= 60:
        raise ValueError("DATA_INVALID: unsafe scheduler parameter")
    if not isinstance(workflow_runs, list):
        raise ValueError("DATA_INVALID: missing workflow run list")
    age = minutes_since(report["timestamp"], now)
    result = {
        "status": "HEALTHY", "report_age_minutes": age,
        "threshold_minutes": threshold_minutes,
        "last_report_utc": report["timestamp"],
        "ledger_events": report["verified_events"],
        "recovery_requested": False,
        "reason": "Current report is within the observation freshness target",
    }
    if age <= threshold_minutes:
        return result

    # Use only the workflow-specific run endpoint, not a page of unrelated CI.
    runs = []
    for item in workflow_runs:
        if not isinstance(item, dict) or not item.get("created_at"):
            raise ValueError("DATA_INVALID: malformed workflow-run metadata")
        if item.get("head_branch") != "main":
            continue
        runs.append(item)
    for item in runs:
        if item.get("status") in ("queued", "in_progress", "waiting",
                                  "pending", "requested"):
            elapsed = minutes_since(item["created_at"], now)
            result["last_workflow_run"] = item.get("html_url")
            result["pending_age_minutes"] = elapsed
            if elapsed > PENDING_RUN_ALERT_MINUTES:
                result.update(status="STUCK", reason="An existing lab run is stuck; refusing duplicate dispatch")
            else:
                result.update(status="IN_FLIGHT", reason="An existing lab run is queued or executing")
            return result
    if runs:
        latest = max(runs, key=lambda item: utc(item["created_at"]))
        elapsed = minutes_since(latest["created_at"], now)
        result["last_workflow_run"] = latest.get("html_url")
        result["last_workflow_run_age_minutes"] = elapsed
        if elapsed < cooldown_minutes:
            result.update(status="COOLDOWN", reason="Recent workflow run; avoid duplicate or retry storm")
            return result
    result.update(status="NEEDS_DISPATCH",
                  reason="Canonical report is stale and no active/recent lab run was found")
    return result


class GithubAPI:
    def __init__(self, token):
        if not token:
            raise RuntimeError("AUTH_REQUIRED: guardian needs repository-scoped GITHUB_TOKEN")
        self.token = token

    def call(self, path, payload=None):
        if not path.startswith("/repos/") or "://" in path:
            raise ValueError("invalid GitHub API path")
        data = (json.dumps(payload, separators=(",", ":")).encode("utf-8")
                if payload is not None else None)
        request = urllib.request.Request(
            BASE + path, data=data,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "crypto-strategy-lab-schedule-guardian/1.0",
                **({"Content-Type": "application/json"} if data is not None else {}),
            }, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read()
                if payload is not None:
                    if response.status not in (200, 201, 202, 204):
                        raise RuntimeError("DISPATCH_FAILED: unexpected API response status")
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Never print headers, request objects, tokens, or response bodies.
            raise RuntimeError("GITHUB_API_FAILURE: HTTP " + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("GITHUB_API_UNAVAILABLE: " + type(exc).__name__) from None


def execute(repo, api, now=None, allow_dispatch=False,
            threshold_minutes=MAX_REPORT_AGE_MINUTES):
    if not REPOSITORY_RE.fullmatch(repo):
        raise ValueError("invalid GITHUB_REPOSITORY")
    now = now or dt.datetime.now(UTC)
    prefix = "/repos/" + repo
    main = api.call(prefix + "/contents/data/report.json?ref=main")
    report = decode_report(main)
    runs_response = api.call(prefix + "/actions/workflows/" + WORKFLOW +
                             "/runs?per_page=40")
    if not isinstance(runs_response, dict) or not isinstance(runs_response.get("workflow_runs"), list):
        raise RuntimeError("DATA_UNAVAILABLE: unable to inspect lab workflow status")
    state = evaluate(report, runs_response["workflow_runs"], now,
                     threshold_minutes=threshold_minutes)
    if state["status"] == "STUCK":
        raise RuntimeError("STUCK_RUN: a workflow is still pending/running after " +
                           str(PENDING_RUN_ALERT_MINUTES) +
                           " minutes; manual investigation needed")
    if state["status"] == "NEEDS_DISPATCH" and allow_dispatch:
        # A primary paper run can finish between the first GET and this POST.
        # Re-read both sources immediately before writing; two staggered GitHub
        # guardians share a repository-wide concurrency group, but a scheduled
        # primary job is independent and may start at any moment.
        confirmation = decode_report(
            api.call(prefix + "/contents/data/report.json?ref=main"))
        current_runs = api.call(prefix + "/actions/workflows/" + WORKFLOW +
                                "/runs?per_page=40")
        if (not isinstance(current_runs, dict) or
                not isinstance(current_runs.get("workflow_runs"), list)):
            raise RuntimeError("DATA_UNAVAILABLE: cannot confirm workflow queue")
        fresh_state = evaluate(confirmation, current_runs["workflow_runs"], now,
                               threshold_minutes=threshold_minutes)
        if fresh_state["status"] == "STUCK":
            raise RuntimeError("STUCK_RUN: primary workflow has stalled")
        if fresh_state["status"] != "NEEDS_DISPATCH":
            state = fresh_state
            state["recheck_prevented_duplicate"] = True
        else:
            api.call(prefix + "/actions/workflows/" + WORKFLOW +
                     "/dispatches", {"ref": "main"})
            state.update(status="RECOVERY_DISPATCHED", recovery_requested=True,
                         recheck_prevented_duplicate=False,
                         reason="Authenticated workflow_dispatch accepted by GitHub API; "
                                "new paper observation NOT YET CONFIRMED")
    state["inspected_at_utc"] = now.astimezone(UTC).isoformat()
    state["guardian_source"] = "main report + GitHub workflow-specific runs API"
    state["real_exchange_orders"] = False
    return state


def main():
    parser = argparse.ArgumentParser(description="Paper lab schedule guardian")
    parser.add_argument("--recover", action="store_true",
                        help="Dispatch a missed lab workflow if safely necessary")
    parser.add_argument("--threshold-minutes", type=int,
                        default=MAX_REPORT_AGE_MINUTES)
    parser.add_argument("--status-file", type=Path, default=None,
                        help="Write an atomic decision receipt for the following health check")
    args = parser.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    api = GithubAPI(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    state = execute(repo, api, allow_dispatch=args.recover,
                    threshold_minutes=args.threshold_minutes)
    print(json.dumps(state, indent=2, sort_keys=True))
    if args.status_file is not None:
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix=".guardian-", dir=args.status_file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, args.status_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("### Schedule guardian\n\n")
            out.write("Status: **" + state["status"] + "**; canonical report age: " +
                      str(state["report_age_minutes"]) + " minutes.\n\n")
            out.write("The guardian dispatches a workflow, not a trade; successful "
                      "dispatch does not prove a fresh observed price.\n\n")
    if state["status"] == "NEEDS_DISPATCH":
        raise SystemExit("SCHEDULE_STALE: recovery needed but not enabled")


if __name__ == "__main__":
    main()
