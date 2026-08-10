# -*- coding: utf-8 -*-
"""测试场景配置不记录身份凭证或机构登录信息。"""

import unittest

from abaqus_codex.configuration import ConfigurationError
from abaqus_codex.scenario import build_profile


class ScenarioProfileTests(unittest.TestCase):
    """确认场景选择保持最小数据原则。"""

    def test_paper_profile_contains_access_notice(self):
        """论文场景应明确合法访问边界。"""

        profile = build_profile("paper")
        self.assertEqual(profile["scenario_name"], "单篇论文复现")
        self.assertIn("不保存机构密码", profile["paper_access_notice"])
        self.assertNotIn("password", profile)

    def test_unknown_scenario_is_rejected(self):
        """未知场景不应被悄悄保存。"""

        with self.assertRaises(ConfigurationError):
            build_profile("unknown")


if __name__ == "__main__":
    unittest.main()
