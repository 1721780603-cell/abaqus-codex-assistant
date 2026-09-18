"""Keep the release-facing CI installation checks from silently weakening."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


class ContinuousIntegrationWorkflowTests(unittest.TestCase):
    def test_ci_installs_the_normal_distribution_and_checks_dependencies(self) -> None:
        """CI must cover the package form that ordinary developers install."""
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('python -m pip install ".[test]"', source)
        self.assertNotIn('python -m pip install -e ".[test]"', source)
        self.assertIn("python -m pip check", source)


if __name__ == "__main__":
    unittest.main()
