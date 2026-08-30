# -*- coding: utf-8 -*-
"""测试桌面环境体检的有限展示，不启动 Abaqus 或 Codex。"""

from __future__ import annotations

import unittest

from abaqus_codex.desktop_assistant.codex_status import CodexStatus
from abaqus_codex.desktop_assistant.environment_check import (
    build_environment_items,
    format_environment_detail,
    summarize_environment,
)


def sample_result():
    """返回包含必需环境与可选工具的最小体检结果。"""

    return {
        "project_python": {"usable": True, "version": "3.13.0"},
        "environment": {
            "abaqus": {
                "usable": True,
                "version": "2021",
                "python_version": "2.7.15",
                "message": "已找到可用的 Abaqus。",
            },
            "abqpy": {
                "usable": False,
                "installed": False,
                "version": None,
                "recommended_requirement": "abqpy==2021.*",
                "message": "当前环境没有安装 abqpy。",
            },
            "mcp": {
                "responsive": False,
                "message": "MCP 文件存在，但尚未注册。",
            },
        },
        "version_plan": {
            "recommended_abqpy_requirement": "abqpy==2021.*",
            "abqpy_action": "install_matching",
            "verification_level": "maintainer_verified",
        },
        "git": {
            "usable": True,
            "version": "2.53.0",
            "message": "Git 可以使用。",
        },
        "github": {"logged_in": False, "message": "GitHub CLI 尚未登录。"},
        "zotero": {"read_ready": False, "message": "Zotero 尚未连接。"},
    }


class EnvironmentCheckTests(unittest.TestCase):
    """确认状态分层、安全摘要和修复提示。"""

    def test_items_do_not_expose_paths_or_make_optional_tools_blocking(self):
        """展示列表不得包含本机路径，GitHub 与 Zotero 缺项仍是可选。"""

        result = sample_result()
        result["environment"]["abaqus"]["command"] = r"C:\private\abaqus.bat"
        status = CodexStatus(True, True, "chatgpt", "Codex 已登录", "online", "可用。")

        items = build_environment_items(result, status)
        combined = "\n".join(
            item.detail + "\n" + item.next_step for item in items
        )

        self.assertEqual(len(items), 10)
        self.assertNotIn("C:\\private", combined)
        self.assertEqual(next(item for item in items if item.name == "GitHub 登录").tone, "optional")
        self.assertEqual(next(item for item in items if item.name == "Zotero").tone, "optional")

    def test_missing_abqpy_gets_one_confirmed_next_step(self):
        """缺少 abqpy 时只建议询问安装，不能声称已经安装。"""

        items = build_environment_items(sample_result(), None)
        abqpy = next(item for item in items if item.name == "abqpy")

        self.assertEqual(abqpy.status, "需安装 abqpy==2021.*")
        self.assertIn("Abaqus 年份：2021", abqpy.detail)
        self.assertIn("严格匹配要求：abqpy==2021.*", abqpy.detail)
        self.assertIn("复制给 Codex", abqpy.next_step)
        self.assertIn("我确认当前使用 Abaqus 2021", abqpy.next_step)
        self.assertIn("建议先处理 abqpy", summarize_environment(items))

    def test_2022_to_2025_generate_same_year_only_instruction(self):
        """常用候选版本只能建议同年份 abqpy，并提醒先做小模型验证。"""

        for year in (2022, 2023, 2024, 2025):
            with self.subTest(year=year):
                result = sample_result()
                requirement = "abqpy=={0}.*".format(year)
                result["environment"]["abaqus"]["version"] = str(year)
                result["environment"]["abqpy"]["recommended_requirement"] = requirement
                result["version_plan"].update(
                    {
                        "recommended_abqpy_requirement": requirement,
                        "verification_level": "detected_unverified",
                    }
                )

                abqpy = next(
                    item
                    for item in build_environment_items(result, None)
                    if item.name == "abqpy"
                )

                self.assertIn(requirement, abqpy.detail)
                self.assertIn(requirement, abqpy.next_step)
                self.assertIn("尚未完成维护者真机验证", abqpy.next_step)
                for wrong_year in (2021, 2022, 2023, 2024, 2025):
                    if wrong_year != year:
                        self.assertNotIn(
                            "abqpy=={0}.*".format(wrong_year),
                            abqpy.next_step,
                        )

    def test_2026_never_offers_install_instruction(self):
        """已知不兼容年份只能阻断，不能生成可执行安装口令。"""

        result = sample_result()
        result["environment"]["abaqus"]["version"] = "2026"
        result["environment"]["abqpy"]["recommended_requirement"] = None
        result["version_plan"] = {
            "recommended_abqpy_requirement": None,
            "abqpy_action": "unsupported",
            "verification_level": "known_incompatible",
        }

        abqpy = next(
            item
            for item in build_environment_items(result, None)
            if item.name == "abqpy"
        )

        self.assertEqual(abqpy.status, "版本不支持")
        self.assertIn("禁止自动安装", abqpy.next_step)
        self.assertNotIn("请安装严格匹配", abqpy.next_step)

    def test_detail_repeats_read_only_boundary(self):
        """每个详情都持续说明体检不会修改电脑或模型。"""

        item = build_environment_items(sample_result(), None)[0]
        detail = format_environment_detail(item)

        self.assertIn("本窗口只做检查", detail)
        self.assertIn("不会安装软件", detail)


if __name__ == "__main__":
    unittest.main()
