# -*- coding: utf-8 -*-
"""测试桌面助手命令的延迟导入和参数传递。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.cli import main


class DesktopAssistantCommandTests(unittest.TestCase):
    """确认 CLI 不会自行启动 Abaqus 或切换为模拟模式。"""

    @patch("abaqus_codex.desktop_assistant.launch", return_value=0)
    def test_default_routes_to_one_shot_snapshot(self, launch_mock):
        """默认启动必须读取静态快照，不能触发 MCP。"""

        exit_code = main(["assistant"])
        self.assertEqual(exit_code, 0)
        launch_mock.assert_called_once_with(
            mock=False, source="snapshot", mcp_home=None
        )

    @patch("abaqus_codex.desktop_assistant.launch", return_value=0)
    def test_mock_alias_is_explicit(self, launch_mock):
        """旧 --mock 参数仍应明确进入模拟模式。"""

        exit_code = main(["assistant", "--mock"])
        self.assertEqual(exit_code, 0)
        launch_mock.assert_called_once_with(
            mock=True, source="mock", mcp_home=None
        )

    @patch("abaqus_codex.desktop_assistant.launch", return_value=0)
    def test_mcp_home_requires_explicit_mcp_source(self, launch_mock):
        """只有明确兼容模式才能读取旧 MCP 工作目录。"""

        exit_code = main(
            ["assistant", "--source", "mcp", "--mcp-home", "example-mcp"]
        )
        self.assertEqual(exit_code, 0)
        launch_mock.assert_called_once_with(
            mock=False, source="mcp", mcp_home=Path("example-mcp")
        )

    def test_snapshot_rejects_mcp_home(self):
        """快照模式不能携带会误导用户的 MCP 目录参数。"""

        with self.assertRaises(SystemExit):
            main(["assistant", "--mcp-home", "example-mcp"])

    def test_mock_alias_rejects_explicit_source(self):
        """两个来源选择方式同时出现时必须停止，不能暗中选一个。"""

        with self.assertRaises(SystemExit):
            main(["assistant", "--mock", "--source", "snapshot"])

    @patch("abaqus_codex.safe_action_setup.setup_safe_action_plugin")
    def test_setup_dry_run_is_forwarded_without_confirmation(self, setup_mock):
        """演练命令必须保持零写入语义，并展示目标。"""

        setup_mock.return_value = {
            "message": "演练完成",
            "target": r"C:\Users\test\abaqus_plugins\safe_material_action",
            "backup": None,
            "dry_run": True,
            "changed": True,
        }
        exit_code = main(["assistant-setup", "--dry-run"])
        self.assertEqual(exit_code, 0)
        setup_mock.assert_called_once_with(confirmed=False, dry_run=True)

    @patch("abaqus_codex.safe_action_setup.setup_safe_action_plugin")
    def test_setup_yes_is_forwarded_as_explicit_consent(self, setup_mock):
        """真实安装只有 --yes 才能向安装器传递确认。"""

        setup_mock.return_value = {
            "message": "安装完成",
            "target": r"C:\Users\test\abaqus_plugins\safe_material_action",
            "backup": None,
            "dry_run": False,
            "changed": True,
        }
        exit_code = main(["assistant-setup", "--yes"])
        self.assertEqual(exit_code, 0)
        setup_mock.assert_called_once_with(confirmed=True, dry_run=False)


if __name__ == "__main__":
    unittest.main()
