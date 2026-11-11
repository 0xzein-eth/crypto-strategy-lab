"""Negative controls for read-only cross-ledger acceptance evidence."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_quality
from research_quality import gates, readiness


class RoadmapAuditTests(unittest.TestCase):
    def test_public_gate_survives_submodule_imports(self):
        from research_quality import equity_ensemble, after_cost_gate
        self.assertIs(research_quality.evaluate,gates.evaluate)
        self.assertEqual(len(equity_ensemble.FAMILIES),5)
        self.assertFalse(after_cost_gate.evaluate(None,.1,.1)["live_orders"])

    def test_reconcile_fails_on_missing_and_tampered_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"report.json"
            with self.assertRaisesRegex(ValueError,"missing/divergent"):
                readiness.reconcile(target,{"equity":"10.00"})
            target.write_text(json.dumps({"equity":"1000.00"}))
            original=target.read_bytes()
            with self.assertRaisesRegex(ValueError,"missing/divergent"):
                readiness.reconcile(target,{"equity":"10.00"})
            self.assertEqual(original,target.read_bytes())

    def test_failed_market_does_not_prevent_remaining_diagnostics(self):
        def corrupt():
            raise ValueError("INTEGRITY_FAILURE: bad hash")
        checks={}
        readiness.run_check("bad",corrupt,checks)
        readiness.run_check("other",lambda:{"observations":2},checks)
        self.assertEqual(checks["bad"]["status"],"FAILED")
        self.assertIn("bad hash",checks["bad"]["error"])
        self.assertEqual(checks["other"]["status"],"VERIFIED")

    def test_cli_refuses_to_overwrite_source_evidence_before_running(self):
        target=readiness.ROOT/"data/report.json"
        with patch("sys.argv",["readiness","--output",str(target)]),patch.object(readiness,"inspect") as inspect:
            with self.assertRaises(SystemExit) as stopped:
                readiness.main()
            self.assertEqual(stopped.exception.code,2)
            inspect.assert_not_called()

    def test_naive_audit_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"aware audit time"):
            readiness.inspect(now=dt.datetime(2026,10,22))


if __name__=="__main__":
    unittest.main()
