import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import health


class HealthTests(unittest.TestCase):
    def test_stale_detection_and_success(self):
        at=dt.datetime(2026,10,8,9,0,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            (root/"data").mkdir()
            (root/"data"/"report.json").write_text(
                '{"timestamp":"2026-10-08T09:00:00Z","provider_observations":12}')
            with patch.object(health.audit,"verify",return_value={"verified":True,"events":20}):
                self.assertEqual(health.check(root,moment=at)["health"],"OK")
                with self.assertRaisesRegex(RuntimeError,"STALE_RUN"):
                    health.check(root,moment=at+dt.timedelta(hours=4))
                with self.assertRaisesRegex(RuntimeError,"CLOCK_INTEGRITY"):
                    health.check(root,moment=at-dt.timedelta(hours=1))

    def test_guarded_health_reports_recovery_as_degraded_not_ok(self):
        import json
        at=dt.datetime(2026,10,8,12,0,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            (root/"data").mkdir()
            (root/"data"/"report.json").write_text(json.dumps({
                "timestamp":"2026-10-08T09:00:00Z",
                "verified_events":100,"provider_observations":12}))
            receipt={"status":"RECOVERY_DISPATCHED",
                     "inspected_at_utc":at.isoformat(),
                     "last_report_utc":"2026-10-08T09:00:00Z",
                     "ledger_events":100}
            with patch.object(health.audit,"verify",return_value={"verified":True}):
                degraded=health.check_guarded(root,moment=at,max_hours=1.25,
                                               guardian_decision=receipt)
                self.assertEqual(degraded["health"],"DEGRADED_RECOVERING")
                self.assertFalse(degraded["market_data_fresh"])
                with self.assertRaisesRegex(RuntimeError,"STALE_RUN"):
                    health.check_guarded(root,moment=at,max_hours=1.25,
                                         guardian_decision=dict(receipt,status="COOLDOWN"))
                with self.assertRaisesRegex(RuntimeError,"STALE_RUN"):
                    health.check_guarded(root,moment=at+dt.timedelta(minutes=6),
                                         max_hours=1.25,guardian_decision=receipt)
                with self.assertRaisesRegex(RuntimeError,"INTEGRITY_FAILURE"):
                    health.check_guarded(root,moment=at,max_hours=1.25,
                                         guardian_decision=dict(receipt,ledger_events=1000))

    def test_in_flight_staleness_is_bounded(self):
        import json
        at=dt.datetime(2026,10,8,12,0,tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            (root/"data").mkdir()
            (root/"data"/"report.json").write_text(json.dumps({
                "timestamp":"2026-10-08T09:00:00Z",
                "verified_events":100,"provider_observations":12}))
            receipt={"status":"IN_FLIGHT","inspected_at_utc":at.isoformat(),
                     "last_report_utc":"2026-10-08T09:00:00Z",
                     "ledger_events":100,"pending_age_minutes":40}
            with patch.object(health.audit,"verify",return_value={"verified":True}):
                self.assertEqual(health.check_guarded(root,moment=at,max_hours=1.25,
                    guardian_decision=receipt)["health"],"DEGRADED_RECOVERING")
                self.assertEqual(health.check_guarded(
                    root,moment=at,max_hours=1.25,
                    guardian_decision=dict(receipt,pending_age_minutes=210)
                    )["health"],"DEGRADED_RECOVERING")
                with self.assertRaisesRegex(RuntimeError,"STALE_RUN"):
                    health.check_guarded(root,moment=at,max_hours=1.25,
                        guardian_decision=dict(receipt,pending_age_minutes=241))


if __name__=="__main__":
    unittest.main()
