# -*- coding: utf-8 -*-
"""检查可安装 Skill 与项目能力是否保持同步。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from abaqus_codex.configuration import SUPPORTED_MODEL_TYPES


SKILL_ROOT = (
    Path(__file__).resolve().parents[1] / "skills" / "abaqus-modeling-guide"
)


class ModelingGuideSkillTests(unittest.TestCase):
    """防止新增模型或移动参考文件后留下失效向导。"""

    def test_catalog_covers_every_supported_model(self):
        """代码支持的每个模型类型都必须出现在新手目录中。"""

        catalog = (SKILL_ROOT / "references" / "model-catalog.md").read_text(
            encoding="utf-8"
        )
        for model_type in SUPPORTED_MODEL_TYPES:
            with self.subTest(model_type=model_type):
                self.assertIn("`{0}`".format(model_type), catalog)

    def test_local_skill_references_exist(self):
        """安装后需要读取的本地参考链接不能指向不存在的文件。"""

        instructions = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        relative_links = re.findall(r"\]\((references/[^)#]+)\)", instructions)
        self.assertTrue(relative_links)
        for relative_link in relative_links:
            with self.subTest(relative_link=relative_link):
                self.assertTrue((SKILL_ROOT / relative_link).is_file())


if __name__ == "__main__":
    unittest.main()
