# -*- coding: utf-8 -*-
"""测试桌面环境体检的有限展示，不启动 Abaqus 或 Codex。"""

from __future__ import annotations

import unittest

from abaqus_codex.desktop_assistant.codex_status import CodexStatus
from abaqus_codex.desktop_assistant.environment_check import (
    build_environment_items,
    environment_action_label,
    format_environment_detail,
    format_environment_progress,
    recommended_environment_index,
    summarize_environment,
)


def sample_result():
    """返回包含必需环境与可选工具的最小体检结果。"""

    return {
        "project_python": {"usable": True, "version": "3.13.0"},
        "environment": {
            "abaqus": {
                "installed": True,
                "usable": True,
                "command": r"C:\SIMULIA\Commands\abaqus.bat",
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
                "usable": False,
                "responsive": False,
                "message": "MCP 文件存在，但尚未注册。",
            },
        },
        "version_plan": {
            "recommended_abqpy_requirement": "abqpy==2021.*",
            "abqpy_action": "install_matching",
            "mcp_action": "wait_for_base",
            "release_year": 2021,
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
        copied = "\n".join(item.codex_prompt for item in items)
        abaqus = next(item for item in items if item.name == "Abaqus")

        self.assertEqual(len(items), 11)
        self.assertIn("C:\\private", abaqus.detail)
        self.assertNotIn("C:\\private", copied)
        self.assertEqual(next(item for item in items if item.name == "GitHub 登录").tone, "optional")
        self.assertEqual(next(item for item in items if item.name == "Zotero").tone, "optional")

    def test_missing_abqpy_gets_one_confirmed_next_step(self):
        """缺少 abqpy 时只建议询问安装，不能声称已经安装。"""

        items = build_environment_items(sample_result(), None)
        abqpy = next(item for item in items if item.name == "abqpy")

        self.assertEqual(abqpy.status, "需安装 abqpy==2021.*")
        self.assertIn("Abaqus 年份：2021", abqpy.detail)
        self.assertIn("严格匹配要求：abqpy==2021.*", abqpy.detail)
        self.assertIn("严格同年份安装请求复制给 Codex", abqpy.next_step)
        self.assertIn("我确认本次使用 Abaqus 2021", abqpy.codex_prompt)
        self.assertIn("不得回退或改装其他年份", abqpy.codex_prompt)
        self.assertIn("建议先处理 abqpy", summarize_environment(items))
        self.assertEqual(
            environment_action_label(abqpy),
            "复制同年份 abqpy 请求",
        )

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
                        "release_year": year,
                        "verification_level": "detected_unverified",
                    }
                )

                abqpy = next(
                    item
                    for item in build_environment_items(result, None)
                    if item.name == "abqpy"
                )

                self.assertIn(requirement, abqpy.detail)
                self.assertIn(requirement, abqpy.codex_prompt)
                self.assertIn("尚未完成维护者真机验证", abqpy.next_step)
                self.assertIn("教学小模型", abqpy.codex_prompt)
                for wrong_year in (2021, 2022, 2023, 2024, 2025):
                    if wrong_year != year:
                        self.assertNotIn(
                            "abqpy=={0}.*".format(wrong_year),
                            abqpy.codex_prompt,
                        )

    def test_missing_abaqus_stops_before_abqpy_install(self):
        """没有检测到 Abaqus 时，不能猜年份或生成 abqpy 安装请求。"""

        result = sample_result()
        result["environment"]["abaqus"].update(
            {
                "usable": False,
                "version": None,
                "python_version": None,
                "message": "没有检测到可用的 Abaqus。",
            }
        )
        result["environment"]["abqpy"].update(
            {
                "usable": False,
                "installed": False,
                "recommended_requirement": None,
            }
        )
        result["version_plan"] = {
            "recommended_abqpy_requirement": None,
            "abqpy_action": "wait_for_abaqus",
            "mcp_action": "wait_for_base",
            "release_year": None,
            "verification_level": "not_detected",
        }

        items = build_environment_items(result, None)
        selected = items[recommended_environment_index(items)]
        abqpy = next(item for item in items if item.name == "abqpy")

        self.assertEqual(selected.name, "Abaqus")
        self.assertEqual(abqpy.status, "等待 Abaqus")
        self.assertEqual(abqpy.codex_prompt, "")
        self.assertNotIn("abqpy==", abqpy.next_step)

    def test_2026_never_offers_install_instruction(self):
        """已知不兼容年份只能阻断，不能生成可执行安装口令。"""

        result = sample_result()
        result["environment"]["abaqus"]["version"] = "2026"
        result["environment"]["abqpy"]["recommended_requirement"] = None
        result["version_plan"] = {
            "recommended_abqpy_requirement": None,
            "abqpy_action": "unsupported",
            "mcp_action": "blocked_incompatible",
            "release_year": 2026,
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
        self.assertEqual(abqpy.codex_prompt, "")
        self.assertEqual(environment_action_label(abqpy), "请按上方说明处理")
        mcp = next(item for item in build_environment_items(result, None) if item.name == "Abaqus MCP")
        self.assertEqual(mcp.status, "当前版本已阻断")
        self.assertEqual(mcp.codex_prompt, "")

    def test_first_unfinished_required_item_is_selected(self):
        """体检完成后应直接定位 abqpy，而不是停在已经完成的项目 Python。"""

        items = build_environment_items(sample_result(), None)

        index = recommended_environment_index(items)

        self.assertEqual(items[index].name, "abqpy")

    def test_mcp_becomes_next_action_after_base_environment_is_ready(self):
        """同年份 abqpy 完成后，应把用户带到 Codex/MCP 联动。"""

        result = sample_result()
        result["environment"]["abqpy"].update(
            {"usable": True, "installed": True, "version": "2021.7.3"}
        )
        result["version_plan"]["abqpy_action"] = "ready"
        result["version_plan"]["mcp_action"] = "install"
        codex = CodexStatus(
            True,
            True,
            "chatgpt",
            "Codex 已登录",
            "online",
            "可用。",
        )
        items = build_environment_items(result, codex)

        index = recommended_environment_index(items)
        mcp = items[index]

        self.assertEqual(mcp.name, "Abaqus MCP")
        self.assertEqual(environment_action_label(mcp), "复制 MCP 检查请求")
        self.assertIn("不得把‘已注册’或‘有心跳’误报", mcp.codex_prompt)

    def test_progress_shows_the_single_current_gap(self):
        """路线条应同时展示已完成阶段和下一处待处理阶段。"""

        progress = format_environment_progress(
            build_environment_items(sample_result(), None)
        )

        self.assertIn("1 应用·完成", progress)
        self.assertIn("2 Abaqus·完成", progress)
        self.assertIn("3 同年份 abqpy·待处理", progress)
        self.assertIn("4 Codex/MCP·待处理", progress)
        self.assertTrue(progress.endswith("5 第一个模型·未到此步"))

    def test_detail_repeats_read_only_boundary(self):
        """每个详情都持续说明体检不会修改电脑或模型。"""

        item = build_environment_items(sample_result(), None)[0]
        detail = format_environment_detail(item)

        self.assertIn("本窗口只做检查", detail)
        self.assertIn("不会安装软件", detail)
        self.assertIn("本机路径", detail)

    def test_installed_abaqus_with_broken_python_does_not_suggest_reinstall(self):
        """识别到版本但内置 Python 失败时，只定位 Python 故障。"""

        result = sample_result()
        result["environment"]["abaqus"].update(
            {
                "usable": False,
                "python_version": None,
                "message": "Abaqus 可用，但自带 Python 查询超时。",
            }
        )
        result["version_plan"].update(
            {"abqpy_action": "wait_for_abaqus", "mcp_action": "wait_for_base"}
        )

        items = build_environment_items(result, None)
        selected = items[recommended_environment_index(items)]
        abaqus = next(item for item in items if item.name == "Abaqus")

        self.assertEqual(abaqus.status, "已就绪")
        self.assertEqual(selected.name, "Abaqus Python")
        self.assertNotIn("官方渠道安装", selected.next_step)

    def test_installed_but_unqueryable_abaqus_does_not_suggest_reinstall(self):
        """启动命令存在但年份查询失败时，应先修复命令而不是重装。"""

        result = sample_result()
        result["environment"]["abaqus"].update(
            {
                "usable": False,
                "version": None,
                "python_version": None,
                "message": "Abaqus 版本查询超时。",
            }
        )
        result["version_plan"].update(
            {
                "release_year": None,
                "abqpy_action": "wait_for_abaqus",
                "mcp_action": "wait_for_base",
            }
        )

        items = build_environment_items(result, None)
        selected = items[recommended_environment_index(items)]

        self.assertEqual(selected.name, "Abaqus")
        self.assertEqual(selected.status, "已找到，需检查")
        self.assertIn("不要直接重装", selected.next_step)

    def test_heartbeat_without_read_only_probe_is_not_connected(self):
        """注册和心跳成功仍不能替代真实的只读工具能力探测。"""

        result = sample_result()
        result["environment"]["abqpy"].update(
            {"usable": True, "installed": True, "version": "2021.7.3"}
        )
        result["environment"]["mcp"].update(
            {"usable": True, "responsive": True}
        )
        result["version_plan"].update(
            {"abqpy_action": "ready", "mcp_action": "ready"}
        )
        status = CodexStatus(True, True, "chatgpt", "Codex 已登录", "online", "可用。")

        mcp = next(
            item
            for item in build_environment_items(result, status)
            if item.name == "Abaqus MCP"
        )

        self.assertEqual(mcp.status, "心跳正常，待能力验证")
        self.assertEqual(mcp.tone, "warning")

    def test_full_2021_path_offers_first_model_action(self):
        """2021 全部通过后，唯一主动作应回到第 1/10 步。"""

        result = sample_result()
        result["environment"]["abqpy"].update(
            {"usable": True, "installed": True, "version": "2021.7.3"}
        )
        result["environment"]["mcp"].update(
            {
                "usable": True,
                "responsive": True,
                "read_only_probe_passed": True,
            }
        )
        result["version_plan"].update(
            {"abqpy_action": "ready", "mcp_action": "ready"}
        )
        status = CodexStatus(True, True, "chatgpt", "Codex 已登录", "online", "可用。")

        items = build_environment_items(result, status)
        selected = items[recommended_environment_index(items)]

        self.assertEqual(selected.name, "第一个模型")
        self.assertEqual(selected.action_kind, "start_model")
        self.assertEqual(
            environment_action_label(selected),
            "返回建模并开始第 1/10 步",
        )

    def test_2022_full_path_requires_candidate_smoke_test(self):
        """2022–2025 不能跳进仅对 2021 验证的桌面写动作流。"""

        result = sample_result()
        result["environment"]["abaqus"].update(
            {"version": "2022", "python_version": "3.9.0"}
        )
        result["environment"]["abqpy"].update(
            {
                "usable": True,
                "installed": True,
                "version": "2022.10.5",
                "recommended_requirement": "abqpy==2022.*",
            }
        )
        result["environment"]["mcp"].update(
            {
                "usable": True,
                "responsive": True,
                "read_only_probe_passed": True,
            }
        )
        result["version_plan"].update(
            {
                "release_year": 2022,
                "verification_level": "detected_unverified",
                "recommended_abqpy_requirement": "abqpy==2022.*",
                "abqpy_action": "ready",
                "mcp_action": "ready",
            }
        )
        status = CodexStatus(True, True, "chatgpt", "Codex 已登录", "online", "可用。")

        items = build_environment_items(result, status)
        selected = items[recommended_environment_index(items)]

        self.assertEqual(selected.name, "第一个模型")
        self.assertEqual(selected.status, "需候选版验证")
        self.assertEqual(selected.action_kind, "copy_codex")
        self.assertIn("不得调用只在 Abaqus 2021", selected.codex_prompt)

    def test_codex_login_item_has_direct_action(self):
        """基础环境完成后，未登录 Codex 应直接提供官方登录动作。"""

        result = sample_result()
        result["environment"]["abqpy"].update(
            {"usable": True, "installed": True, "version": "2021.7.3"}
        )
        result["version_plan"].update(
            {"abqpy_action": "ready", "mcp_action": "install"}
        )
        status = CodexStatus(True, False, "none", "Codex 未登录", "offline", "请登录。")

        items = build_environment_items(result, status)
        selected = items[recommended_environment_index(items)]

        self.assertEqual(selected.name, "Codex 登录")
        self.assertEqual(selected.action_kind, "codex_login")
        self.assertEqual(environment_action_label(selected), "打开官方 Codex 登录")


if __name__ == "__main__":
    unittest.main()
