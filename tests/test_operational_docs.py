"""Prevent misleading docs drift from the real prospective PAPER runtime."""
from pathlib import Path
import unittest

import engine
import learner

ROOT = Path(__file__).resolve().parents[1]


class OperationalDocumentationTests(unittest.TestCase):
    def test_readme_and_learning_link_current_research_policy(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        learning = (ROOT / "LEARNING.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "LONG_TERM_RESEARCH_PROGRAM.md").read_text(encoding="utf-8")
        for name in ("BRREG-v1", "TPREG-v1"):
            self.assertIn(name, readme)
            self.assertIn(name, learning)
            self.assertIn(name, guide)
            self.assertIn(name, learner.ADVANCED)
        self.assertIn("docs/LONG_TERM_RESEARCH_PROGRAM.md", readme)
        self.assertIn("performance-neutral", learning)
        self.assertIn("Tidak ada stop-loss", readme)

    def test_core_fixed_horizon_and_capacity_contract(self):
        self.assertEqual(engine.HORIZONS, (1, 2, 4, 8, 12, 24))
        self.assertEqual(engine.SIGNAL_SLOT_SECONDS, 900)
        self.assertEqual(engine.MAX_NEW_PER_RUN, 44)
        self.assertEqual(engine.MAX_OPEN, 1050)
        self.assertEqual(engine.MAX_NEW_PER_UTC_DAY, 1750)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("hingga 44 eksperimen baru per run", readme)
        self.assertIn("1.050 posisi OPEN", readme)
        self.assertIn("1.750 OPEN baru", readme)


if __name__ == "__main__":
    unittest.main()
