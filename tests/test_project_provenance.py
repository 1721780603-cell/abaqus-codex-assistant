# -*- coding: utf-8 -*-
"""检查公开发行物是否持续保留项目来源和作者证据。"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OWNER = "1721780603-cell"
CANONICAL_REPOSITORY = (
    "https://github.com/1721780603-cell/abaqus-codex-assistant"
)


class ProjectProvenanceTests(unittest.TestCase):
    """防止发布或重构时意外删除规范署名。"""

    def test_legal_and_citation_files_name_the_origin(self):
        """许可证、来源声明和引用文件必须指向同一作者与仓库。"""

        for name in ("LICENSE", "NOTICE.md", "AUTHORS.md", "CITATION.cff"):
            with self.subTest(name=name):
                text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
                self.assertIn(OWNER, text)
        citation = (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(CANONICAL_REPOSITORY, citation)

    def test_package_and_readme_keep_the_public_attribution(self):
        """安装元数据和项目首页必须保留可见署名。"""

        for name in ("pyproject.toml", "README.md"):
            with self.subTest(name=name):
                text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
                self.assertIn(OWNER, text)
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(CANONICAL_REPOSITORY, readme)

    def test_desktop_assistant_displays_the_owner(self):
        """桌面程序底部必须持续显示原始项目署名。"""

        source = (
            PROJECT_ROOT
            / "src"
            / "abaqus_codex"
            / "desktop_assistant"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(OWNER, source)
        self.assertIn(CANONICAL_REPOSITORY, source)


if __name__ == "__main__":
    unittest.main()
