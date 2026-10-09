"""Offline deterministic tests for short bounded recovery observation windows."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import engine
import recovery_window as window

NOW = dt.datetime(2026, 10, 9, 1, 0, tzinfo=dt.timezone.utc)


def report(t, gap=130, recover=True):
    return {"schema_version": 8, "timestamp": engine.stamp(t),
            "verified_events": 404,
            "scheduling_diagnostics": {
                "prior_observation_gap_minutes": gap,
                "recovery_throttled": recover,
            }}


class RecoveryWindowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "data").mkdir()

    def save(self, obj):
        (self.root / "data" / "report.json").write_text(
            json.dumps(obj), encoding="utf-8")

    def test_does_not_hold_runner_open_on_healthy_report(self):
        self.save(report(NOW, gap=5, recover=False))
        def forbidden(*a, **kw):
            self.fail("No Git commands or sleeps if recovery not necessary")
        result = window.run_window(root=self.root, pulses=2,
                                   now=lambda: NOW, sleeper=forbidden,
                                   runner=forbidden)
        self.assertEqual(result["status"], "SKIPPED_NO_RECOVERY")
        self.assertEqual(result["completed_pulses"], 0)

    def test_stale_initial_trigger_cannot_start_idle_window(self):
        self.save(report(NOW - dt.timedelta(minutes=30)))
        result = window.run_window(root=self.root, now=lambda: NOW,
                                   sleeper=lambda _: self.fail("not allowed"),
                                   runner=lambda *_: self.fail("not allowed"))
        self.assertEqual(result["status"], "SKIPPED_NO_RECOVERY")

    def test_elapsed_wait_and_clock_bounds(self):
        self.assertEqual(window.remaining_seconds(engine.stamp(NOW),
                         NOW, 10), 600)
        self.assertEqual(window.remaining_seconds(engine.stamp(NOW),
                         NOW + dt.timedelta(minutes=14), 10), 0)
        self.assertEqual(window.remaining_seconds(engine.stamp(NOW),
                         NOW + dt.timedelta(minutes=7), 10), 180)
        with self.assertRaises(ValueError):
            window.remaining_seconds(engine.stamp(NOW), NOW, 20)
        with self.assertRaisesRegex(ValueError, "CLOCK_INTEGRITY"):
            window.remaining_seconds(engine.stamp(NOW + dt.timedelta(minutes=10)),
                                     NOW, 10)

    def test_bounded_two_observations_and_independent_commits(self):
        now = [NOW]
        sleeps, commands = [], []
        self.save(report(NOW - dt.timedelta(minutes=1)))
        def sleeper(seconds):
            sleeps.append(seconds)
            now[0] += dt.timedelta(seconds=seconds)
        def runner(args, root):
            commands.append(args)
            if args[:2] == ["git", "status"]:
                return ""
            if args[:4] == ["git", "diff", "--cached", "--name-only"]:
                return "data/report.json"
            if args[:2] == ["python", "engine.py"] and "--count" in args:
                updated = report(now[0], gap=10, recover=False)
                updated["added"] = 2
                updated["closed_this_run"] = 1
                self.save(updated)
            return ""
        result = window.run_window(root=self.root, pulses=2,
                                   now=lambda: now[0], sleeper=sleeper,
                                   runner=runner)
        self.assertEqual(result["completed_pulses"], 2)
        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 540, delta=1)
        self.assertAlmostEqual(sleeps[1], 600, delta=1)
        self.assertEqual(sum(c[:3] == ["python", "engine.py", "--count"]
                             for c in commands), 2)
        self.assertEqual(sum(c[:2] == ["git", "commit"]
                             for c in commands), 2)
        self.assertEqual(sum(c[:2] == ["git", "push"]
                             for c in commands), 2)
        self.assertTrue(all(x["status"] == "PUBLISHED"
                            for x in result["observations"]))

    def test_new_remote_observation_is_not_overwritten(self):
        now = [NOW]
        self.save(report(NOW))
        def runner(args, root):
            if args[:2] == ["git", "status"]:
                return ""
            if args[:3] == ["git", "merge", "--ff-only"]:
                self.save(report(now[0]))
            if args[:2] == ["python", "engine.py"]:
                self.fail("No extra quote requested after newer canonical commit")
            return ""
        def sleeper(seconds):
            now[0] += dt.timedelta(seconds=seconds)
        result = window.run_window(root=self.root, pulses=1,
                                   now=lambda: now[0], sleeper=sleeper,
                                   runner=runner)
        self.assertEqual(result["completed_pulses"], 0)
        self.assertEqual(result["observations"][0]["status"], "SKIPPED_NEWER_MAIN")

    def test_dirty_workspace_fails_closed_without_sleep(self):
        self.save(report(NOW))
        with self.assertRaisesRegex(RuntimeError, "dirty checkout"):
            window.run_window(root=self.root, now=lambda: NOW,
                              runner=lambda *_: " M data/report.json",
                              sleeper=lambda *_: self.fail("must not sleep"))

    def test_cannot_request_unbounded_runner(self):
        self.save(report(NOW))
        with self.assertRaisesRegex(ValueError, "max recovery pulses"):
            window.run_window(root=self.root, pulses=7)
        with self.assertRaisesRegex(ValueError, "recovery cadence"):
            window.run_window(root=self.root, interval_minutes=60)

    def test_policy_requires_truly_degraded_report(self):
        self.assertFalse(window.recovery_eligible(
            report(NOW, gap=40, recover=True), NOW))
        self.assertFalse(window.recovery_eligible(
            report(NOW, gap=200, recover=False), NOW))
        self.assertTrue(window.recovery_eligible(
            report(NOW - dt.timedelta(minutes=1)), NOW))


if __name__ == "__main__":
    unittest.main()
