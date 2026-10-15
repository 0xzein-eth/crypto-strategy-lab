"""Offline deterministic tests for short bounded recovery observation windows."""
import datetime as dt
import json
import subprocess
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

    def test_python_cache_is_ignored_but_paper_ledger_stays_visible(self):
        source = (Path(__file__).resolve().parents[1] / ".gitignore")
        (self.root / ".gitignore").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=self.root,
                       check=True, capture_output=True)
        pycache = self.root / "__pycache__"
        pycache.mkdir()
        (pycache / "engine.cpython-312.pyc").write_bytes(b"synthetic")
        (self.root / "data" / "events").mkdir()
        (self.root / "data" / "events" / "test.jsonl").write_text(
            '{"paper":true}\\n', encoding="utf-8")
        status = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=self.root, check=True, capture_output=True,
            text=True).stdout
        self.assertNotIn("__pycache__", status)
        self.assertNotIn(".pyc", status)
        self.assertIn("data/events/test.jsonl", status)

    def test_does_not_hold_runner_open_on_healthy_report(self):
        self.save(report(NOW, gap=5, recover=False))
        def forbidden(*a, **kw):
            self.fail("No Git commands or sleeps if recovery not necessary")
        result = window.run_window(root=self.root, pulses=2,
                                   now=lambda: NOW, sleeper=forbidden,
                                   runner=forbidden)
        self.assertEqual(result["status"], "SKIPPED_NO_RECOVERY")
        self.assertEqual(result["completed_pulses"], 0)

    def test_continuous_mode_bootstraps_from_fresh_healthy_tick(self):
        now=[NOW]
        self.save(report(NOW,gap=10,recover=False))
        def sleeper(seconds):
            now[0] += dt.timedelta(seconds=seconds)
        def runner(args,root):
            if args[:2]==["git","status"]:
                return ""
            if args[:4]==["git","diff","--cached","--name-only"]:
                return "data/report.json"
            if args[:3]==["python","engine.py","--count"]:
                self.assertEqual(args[3],"24")
                self.save(report(now[0],gap=10,recover=False))
            return ""
        result=window.run_window(root=self.root,pulses=3,
                   continuous=True,now=lambda:now[0],sleeper=sleeper,runner=runner)
        self.assertEqual(result["completed_pulses"],3)
        self.assertTrue(result["continuous"])
        self.assertEqual((now[0]-NOW).total_seconds(),1800)

    def test_continuous_mode_skips_stale_initial_tick(self):
        self.save(report(NOW-dt.timedelta(minutes=20),gap=10,recover=False))
        result=window.run_window(root=self.root,continuous=True,
                                 now=lambda:NOW,
                                 runner=lambda *_:self.fail("must not run"),
                                 sleeper=lambda *_:self.fail("must not sleep"))
        self.assertEqual(result["status"],"SKIPPED_NO_RECOVERY")

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

    def test_six_pulses_span_one_hour_for_one_hour_paper_horizon(self):
        now = [NOW]
        entered = NOW - dt.timedelta(seconds=30)
        self.save(report(entered))
        commit_times = []
        def sleeper(seconds):
            now[0] += dt.timedelta(seconds=seconds)
        def runner(args, root):
            if args[:2] == ["git", "status"]:
                return ""
            if args[:4] == ["git", "diff", "--cached", "--name-only"]:
                return "data/report.json"
            if args[:3] == ["python", "engine.py", "--count"]:
                self.save(report(now[0], gap=10, recover=False))
            if args[:2] == ["git", "commit"]:
                commit_times.append(now[0])
            return ""
        result = window.run_window(root=self.root, pulses=6,
                                   now=lambda: now[0], sleeper=sleeper,
                                   runner=runner)
        self.assertEqual(result["completed_pulses"], 6)
        self.assertEqual(len(commit_times), 6)
        self.assertEqual(commit_times[0], entered + dt.timedelta(minutes=10))
        self.assertEqual(commit_times[-1], entered + dt.timedelta(minutes=60))
        self.assertTrue(all(
            (commit_times[i] - commit_times[i-1]).total_seconds() == 600
            for i in range(1, len(commit_times))))
        self.assertLessEqual((now[0] - NOW).total_seconds(), 3600)

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

    def test_two_consecutive_real_remote_observations_stop_long_recovery(self):
        now=[NOW]
        self.save(report(NOW))
        merges=[]
        def runner(args,root):
            if args[:2]==["git","status"]:
                return ""
            if args[:3]==["git","merge","--ff-only"]:
                merges.append(now[0])
                self.save(report(now[0]))
            if args[:2]==["python","engine.py"]:
                self.fail("Remote observer is active; no duplicate market quote allowed")
            return ""
        def sleeper(sec):
            now[0]+=dt.timedelta(seconds=sec)
        result=window.run_window(root=self.root,pulses=18,
                  now=lambda:now[0],sleeper=sleeper,runner=runner)
        self.assertEqual(result["status"],"RECOVERY_SUPERSEDED_BY_FRESH_MAIN")
        self.assertEqual(result["completed_pulses"],0)
        self.assertEqual(result["pulses_skipped_newer_main"],2)
        self.assertEqual(len(merges),2)
        self.assertLess((now[0]-NOW).total_seconds(),1800)

    def test_dirty_workspace_fails_closed_without_sleep(self):
        self.save(report(NOW))
        with self.assertRaisesRegex(RuntimeError, "dirty checkout"):
            window.run_window(root=self.root, now=lambda: NOW,
                              runner=lambda *_: " M data/report.json",
                              sleeper=lambda *_: self.fail("must not sleep"))

    def test_adaptive_budget_respects_coverage_and_hard_limit(self):
        report_=report(NOW)
        quality=report_["scheduling_diagnostics"]
        self.assertEqual(window.adaptive_pulse_budget(report_,18),12)
        quality.update(recent_observed_intervals=42,
                       estimated_10m_slot_coverage=0.2952)
        self.assertEqual(window.adaptive_pulse_budget(report_,18),18)
        self.assertEqual(window.adaptive_pulse_budget(report_,2),2)
        quality["estimated_10m_slot_coverage"]=0.6
        self.assertEqual(window.adaptive_pulse_budget(report_,18),18)
        quality["estimated_10m_slot_coverage"]=0.9
        self.assertEqual(window.adaptive_pulse_budget(report_,18),18)
        quality["estimated_10m_slot_coverage"]=0.95
        self.assertEqual(window.adaptive_pulse_budget(report_,18),12)
        quality["estimated_10m_slot_coverage"]=1.0
        self.assertEqual(window.adaptive_pulse_budget(report_,18),12)
        quality["estimated_10m_slot_coverage"]=float("nan")
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            window.adaptive_pulse_budget(report_,18)

    def test_adaptive_eighteen_pulses_commit_prospectively(self):
        now=[NOW]
        current=report(NOW)
        current["scheduling_diagnostics"].update(
            recent_observed_intervals=67, estimated_10m_slot_coverage=0.2952)
        self.save(current)
        commits=[]
        def runner(command, root):
            if command[:2]==["git","status"]:
                return ""
            if command[:4]==["git","diff","--cached","--name-only"]:
                return "data/report.json"
            if command[:3]==["python","engine.py","--count"]:
                self.save(report(now[0],gap=10,recover=False))
            if command[:2]==["git","commit"]:
                commits.append(now[0])
            return ""
        def sleeper(seconds):
            now[0]+=dt.timedelta(seconds=seconds)
        result=window.run_window(root=self.root,pulses=18,adaptive=True,
                                 now=lambda:now[0],sleeper=sleeper,runner=runner)
        self.assertEqual(result["requested_pulses"],18)
        self.assertEqual(result["completed_pulses"],18)
        self.assertEqual(len(commits),18)
        self.assertEqual((commits[-1]-commits[0]).total_seconds(),17*600)
        self.assertEqual((commits[-1]-NOW).total_seconds(),180*60)

    def test_transient_provider_failure_skips_real_slot_without_fake_commit(self):
        now=[NOW]
        self.save(report(NOW))
        cmds=[]
        clock_attempts=[]
        def sleeper(seconds):
            now[0]+=dt.timedelta(seconds=seconds)
        def runner(cmd,root):
            cmds.append(cmd)
            if cmd[:2]==["git","status"]:
                return ""
            if cmd[:4]==["git","diff","--cached","--name-only"]:
                return "data/report.json"
            if cmd[:3]==["python","engine.py","--count"]:
                clock_attempts.append(now[0])
                if len(clock_attempts)==1:
                    raise subprocess.CalledProcessError(
                        1,cmd,output="",stderr="RuntimeError: DATA_UNAVAILABLE: no live quote")
                self.save(report(now[0],gap=20,recover=False))
            return ""
        outcome=window.run_window(root=self.root,pulses=3,now=lambda:now[0],
                                  sleeper=sleeper,runner=runner)
        self.assertEqual(outcome["completed_pulses"],2)
        self.assertEqual(outcome["pulses_skipped_provider_outage"],1)
        self.assertEqual(outcome["observations"][0]["status"],"SKIPPED_REAL_PROVIDER_OUTAGE")
        self.assertEqual(len(clock_attempts),3)
        self.assertEqual((clock_attempts[1]-clock_attempts[0]).total_seconds(),600)
        self.assertEqual(sum(cmd[:2]==["git","commit"] for cmd in cmds),2)

    def test_persistent_provider_outage_aborts_without_committing(self):
        now=[NOW]
        self.save(report(NOW))
        calls=[]
        def runner(cmd,root):
            calls.append(cmd)
            if cmd[:2]==["git","status"]:
                return ""
            if cmd[:3]==["python","engine.py","--count"]:
                raise subprocess.CalledProcessError(
                    1,cmd,output="",stderr="DATA_UNAVAILABLE: no valid market source")
            return ""
        def sleeper(sec):
            now[0]+=dt.timedelta(seconds=sec)
        with self.assertRaisesRegex(RuntimeError,"three consecutive"):
            window.run_window(root=self.root,pulses=18,
                              now=lambda:now[0],sleeper=sleeper,runner=runner)
        self.assertEqual(sum(cmd[:2]==["git","commit"] for cmd in calls),0)
        self.assertEqual(sum(cmd[:3]==["python","engine.py","--count"]
                             for cmd in calls),3)
        self.assertEqual((now[0]-NOW).total_seconds(),1800)

    def test_programming_errors_fail_closed_not_treated_as_market_outage(self):
        self.save(report(NOW))
        now=[NOW]
        def sleeper(sec):
            now[0]+=dt.timedelta(seconds=sec)
        def runner(cmd,root):
            if cmd[:2]==["git","status"]:
                return ""
            if cmd[:3]==["python","engine.py","--count"]:
                raise subprocess.CalledProcessError(
                    1,cmd,output="",stderr="ValueError: INTEGRITY_FAILURE")
            return ""
        with self.assertRaises(subprocess.CalledProcessError):
            window.run_window(root=self.root,pulses=3,now=lambda:now[0],
                              sleeper=sleeper,runner=runner)

    def test_cannot_request_unbounded_runner(self):
        self.save(report(NOW))
        with self.assertRaisesRegex(ValueError, "max recovery pulses"):
            window.run_window(root=self.root, pulses=19)
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
