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


if __name__=="__main__":
    unittest.main()
