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
                "version": None,
                "message": "当前环境没有安装 abqpy。",
            },
            "mcp": {
                "responsive": False,
                "message": "MCP 文件存在，但尚未注册。",
            },
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

        self.assertEqual(abqpy.status, "待配置")
        self.assertIn("询问是否安装", abqpy.next_step)
        self.assertIn("建议先处理 abqpy", summarize_environment(items))

    def test_detail_repeats_read_only_boundary(self):
        """每个详情都持续说明体检不会修改电脑或模型。"""

        item = build_environment_items(sample_result(), None)[0]
        detail = format_environment_detail(item)

        self.assertIn("本窗口只做检查", detail)
        self.assertIn("不会安装软件", detail)


if __name__ == "__main__":
    unittest.main()
