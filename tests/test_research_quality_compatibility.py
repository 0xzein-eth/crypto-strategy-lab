import unittest
import research_quality
from research_quality import audit, calendar_evidence, crypto_forensics

class LegacyResearchQualityCompatibility(unittest.TestCase):
    def test_existing_engine_api_is_available(self):
        self.assertTrue(callable(research_quality.evaluate))
    def test_legacy_api_is_the_restored_implementation(self):
        self.assertEqual(research_quality.evaluate.__module__,
                         "research_quality.legacy_quality")
    def test_new_modules_can_coexist_with_old_import(self):
        self.assertTrue(callable(audit.audit))
        self.assertTrue(callable(calendar_evidence.interval_by_entry_day))
        self.assertTrue(callable(crypto_forensics.analyze))
    def test_quality_entry_day_is_utc(self):
        self.assertEqual(research_quality._day("2026-10-20T00:30:00+07:00"),"2026-10-19")
