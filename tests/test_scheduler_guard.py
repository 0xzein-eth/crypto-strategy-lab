"""Offline regression tests for the authenticated GH Actions schedule guardian."""
import base64
import datetime as dt
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scheduler_guard as guard


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 8, 15, 0, tzinfo=UTC)


def timestamp(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def report(age):
    return {
        "schema_version": 8, "timestamp": timestamp(age),
        "verified_events": 344, "status": "OK", "provider_observations": 38,
    }


def run(minutes_ago, status="completed", branch="main"):
    return {
        "status": status, "head_branch": branch,
        "created_at": timestamp(minutes_ago),
        "html_url": "https://github.com/example/repo/actions/runs/42",
    }


class FakeApi:
    def __init__(self, latest, runs, next_report=None, next_runs=None):
        self.latest = latest
        self.runs = runs
        self.next_report = next_report
        self.next_runs = next_runs
        self.calls = []
    def call(self, path, payload=None):
        self.calls.append((path, payload))
        if path.endswith("contents/data/report.json?ref=main"):
            reads = sum(p.endswith("contents/data/report.json?ref=main")
                        for p, _ in self.calls)
            current = (self.next_report if reads > 1 and
                       self.next_report is not None else self.latest)
            return {
                "encoding": "base64",
                "content": base64.b64encode(json.dumps(current).encode()).decode(),
            }
        if path.endswith("actions/workflows/lab.yml/runs?per_page=40"):
            reads = sum(p.endswith("actions/workflows/lab.yml/runs?per_page=40")
                        for p, _ in self.calls)
            current = (self.next_runs if reads > 1 and
                       self.next_runs is not None else self.runs)
            return {"total_count": len(current), "workflow_runs": current}
        if path.endswith("actions/workflows/lab.yml/dispatches"):
            if payload != {"ref": "main"}:
                raise AssertionError("unexpected dispatch arguments")
            return None
        raise AssertionError("Unexpected endpoint: " + path)


class GuardianTests(unittest.TestCase):
    def test_three_native_cron_clocks_are_staggered(self):
        root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        expected = {
            "lab.yml": [4, 14, 24, 34, 44, 54],
            "health.yml": [9, 19, 29, 39, 49, 59],
            "rescue.yml": [2, 12, 22, 32, 42, 52],
        }
        seen = set()
        for filename, minutes in expected.items():
            content = (root / filename).read_text(encoding="utf-8")
            match = re.search(r"cron: '([0-9,]+) [*] [*] [*] [*]'", content)
            self.assertIsNotNone(match, filename)
            observed = [int(x) for x in match.group(1).split(",")]
            self.assertEqual(observed, minutes)
            self.assertEqual(len(observed), len(set(observed)))
            for index in range(len(observed)):
                self.assertEqual((observed[(index+1) % len(observed)] -
                                  observed[index]) % 60, 10)
                self.assertNotIn(observed[index], seen)
                seen.add(observed[index])
        self.assertEqual(len(seen), 18)

    def test_recovery_workflows_share_lease_and_ignore_foreign_pull_requests(self):
        root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        for filename in ("health.yml", "rescue.yml"):
            with self.subTest(filename=filename):
                s = (root / filename).read_text(encoding="utf-8")
                self.assertIn("group: schedule-guardian-main", s)
                self.assertIn("cancel-in-progress: false", s)
                self.assertIn("actions: write", s)
                self.assertIn("contents: read", s)
                self.assertIn("ref: main", s)
                self.assertIn("head_repository.full_name == github.repository", s)
                self.assertIn("github.event.workflow_run.event != 'pull_request'", s)
                self.assertIn("scheduler_guard.py --recover --threshold-minutes 14", s)
                self.assertNotIn("  pull_request:", s)
        paper = (root / "lab.yml").read_text(encoding="utf-8")
        self.assertIn("group: continuous-canonical-paper-ledger", paper)
        self.assertIn("cancel-in-progress: false", paper)
        self.assertIn("workflow_dispatch:", paper)

    def test_healthy_report_never_dispatches(self):
        api = FakeApi(report(8), [])
        state = guard.execute("0xzein-eth/crypto-strategy-lab",
                              api, NOW, allow_dispatch=True)
        self.assertEqual(state["status"], "HEALTHY")
        self.assertFalse(state["recovery_requested"])
        self.assertEqual(len(api.calls), 2)

    def test_older_report_requests_one_dispatch_and_only_to_main(self):
        api = FakeApi(report(40), [run(65)])
        state = guard.execute("0xzein-eth/crypto-strategy-lab",
                              api, NOW, allow_dispatch=True)
        self.assertEqual(state["status"], "RECOVERY_DISPATCHED")
        self.assertTrue(state["recovery_requested"])
        self.assertEqual(len(api.calls), 5)
        self.assertEqual(api.calls[-1], (
            "/repos/0xzein-eth/crypto-strategy-lab/actions/workflows/lab.yml/dispatches",
            {"ref": "main"}))
        self.assertIn("NOT YET CONFIRMED", state["reason"])

    def test_race_fresh_report_prevents_duplicate_dispatch(self):
        api = FakeApi(report(45), [run(65)], next_report=report(2))
        state = guard.execute("0xzein-eth/crypto-strategy-lab",
                              api, NOW, allow_dispatch=True)
        self.assertEqual(state["status"], "HEALTHY")
        self.assertTrue(state["recheck_prevented_duplicate"])
        self.assertFalse(state["recovery_requested"])
        self.assertEqual(len(api.calls), 4)

    def test_race_new_running_primary_prevents_duplicate_dispatch(self):
        api = FakeApi(report(45), [run(65)],
                      next_runs=[run(1, "in_progress"), run(65)])
        state = guard.execute("0xzein-eth/crypto-strategy-lab",
                              api, NOW, allow_dispatch=True)
        self.assertEqual(state["status"], "IN_FLIGHT")
        self.assertTrue(state["recheck_prevented_duplicate"])
        self.assertEqual(len(api.calls), 4)

    def test_guardian_does_not_dispatch_an_active_job(self):
        for status in ("queued", "in_progress", "waiting", "pending", "requested"):
            with self.subTest(status=status):
                api = FakeApi(report(50), [run(4, status)])
                result = guard.execute("0xzein-eth/crypto-strategy-lab",
                                       api, NOW, allow_dispatch=True)
                self.assertEqual(result["status"], "IN_FLIGHT")
                self.assertEqual(len(api.calls), 2)

    def test_stuck_active_job_is_detected_not_duplicated(self):
        api = FakeApi(report(65), [run(61, "in_progress")])
        with self.assertRaisesRegex(RuntimeError, "STUCK_RUN"):
            guard.execute("0xzein-eth/crypto-strategy-lab",
                          api, NOW, allow_dispatch=True)
        self.assertEqual(len(api.calls), 2)

    def test_recent_completed_run_has_cooldown_even_if_failed(self):
        for status in ("completed",):
            api = FakeApi(report(36), [run(5, status)])
            result = guard.execute("0xzein-eth/crypto-strategy-lab",
                                   api, NOW, allow_dispatch=True)
            self.assertEqual(result["status"], "COOLDOWN")
            self.assertFalse(result["recovery_requested"])
            self.assertEqual(len(api.calls), 2)

    def test_non_main_runs_cannot_block_recovery(self):
        api = FakeApi(report(41), [run(1, "in_progress", branch="feature/test")])
        state = guard.execute("0xzein-eth/crypto-strategy-lab",
                              api, NOW, allow_dispatch=True)
        self.assertEqual(state["status"], "RECOVERY_DISPATCHED")

    def test_read_only_mode_reports_need_for_recovery_without_side_effects(self):
        api = FakeApi(report(35), [run(60)])
        result = guard.execute("0xzein-eth/crypto-strategy-lab",
                               api, NOW, allow_dispatch=False)
        self.assertEqual(result["status"], "NEEDS_DISPATCH")
        self.assertEqual(len(api.calls), 2)

    def test_clock_future_rejected_without_dispatch(self):
        with self.assertRaisesRegex(ValueError, "CLOCK_INTEGRITY"):
            guard.evaluate(report(-10), [], NOW)

    def test_malformed_repo_or_report_rejected(self):
        api = FakeApi(report(50), [])
        with self.assertRaisesRegex(ValueError, "invalid GITHUB_REPOSITORY"):
            guard.execute("../evil", api, NOW, allow_dispatch=True)
        self.assertEqual(api.calls, [])
        for bad in ({"schema_version": 7, "timestamp": timestamp(50),
                     "verified_events": 344},
                    {"schema_version": 8, "timestamp": timestamp(50),
                     "verified_events": 0}):
            bad_api = FakeApi(bad, [])
            with self.assertRaisesRegex(ValueError, "INTEGRITY_FAILURE"):
                guard.execute("0xzein-eth/crypto-strategy-lab", bad_api,
                              NOW, allow_dispatch=True)
            self.assertEqual(len(bad_api.calls), 1)

    def test_missing_token_rejected_without_printing_secret(self):
        with self.assertRaisesRegex(RuntimeError, "AUTH_REQUIRED"):
            guard.GithubAPI("")
        self.assertFalse("my-secret" in str(guard.GithubAPI("my-secret")))

    def test_empty_runners_is_allowed_when_report_stale(self):
        api = FakeApi(report(37), [])
        result = guard.execute("0xzein-eth/crypto-strategy-lab",
                               api, NOW, allow_dispatch=True)
        self.assertEqual(result["status"], "RECOVERY_DISPATCHED")

    def test_bad_workflow_metadata_fails_closed(self):
        api = FakeApi(report(40), [{"head_branch": "main", "status": "completed"}])
        with self.assertRaisesRegex(ValueError, "DATA_INVALID"):
            guard.execute("0xzein-eth/crypto-strategy-lab", api,
                          NOW, allow_dispatch=True)
        self.assertEqual(len(api.calls), 2)


if __name__ == "__main__":
    unittest.main()
