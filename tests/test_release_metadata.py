# -*- coding: utf-8 -*-
"""验证预发布版本号在用户可见入口中保持一致。"""

from __future__ import annotations

import unittest
from pathlib import Path

from abaqus_codex import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    """避免标签、Python 包、引用信息和插件显示不同版本。"""

    def test_python_and_public_metadata_match_alpha_release(self):
        """Python 使用 PEP 440 写法，公开发布名使用 alpha 写法。"""

        self.assertEqual(__version__, "0.2.0a1")
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        citation = (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn('version = "0.2.0a1"', pyproject)
        self.assertIn('version: "0.2.0-alpha"', citation)
        self.assertIn("## [0.2.0-alpha] - 2026-08-31", changelog)

    def test_abaqus_plugins_show_the_same_minor_release(self):
        """两个 Abaqus 菜单入口都应显示 0.2.0。"""

        for relative in (
            "abaqus_plugins/ai_modeling_assistant/ai_modeling_assistant_plugin.py",
            "abaqus_plugins/safe_material_action/safe_material_action_plugin.py",
        ):
            with self.subTest(relative=relative):
                source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('version="0.2.0"', source)


if __name__ == "__main__":
    unittest.main()
