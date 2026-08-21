# -*- coding: utf-8 -*-
"""测试 MCP 心跳诊断和防卡启动器，不启动 Abaqus 或 Codex。"""

import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.doctor import inspect_environment
from abaqus_codex.mcp_guard import (
    guarded_sender,
    inspect_bridge_status,
    process_is_running,
)
from abaqus_codex.mcp_setup import (
    MCP_SERVER_NAME,
    McpSetupError,
    _ensure_codex_registration,
    _ensure_guard_launcher,
)


def write_status(directory: Path, **changes) -> Path:
    """创建一份可按测试需要修改的插件心跳。"""

    status = {
        "status": "running",
        "timestamp": 1000.0,
        "pid": 1234,
        "message": "Polling active",
    }
    status.update(changes)
    path = directory / "status.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    return path


class McpBridgeStatusTests(unittest.TestCase):
    """确认过期状态不会再被误判成真实在线。"""

    def test_missing_status_is_offline(self):
        """没有状态文件时应提示先启动 Abaqus/CAE。"""

        with tempfile.TemporaryDirectory() as directory:
            result = inspect_bridge_status(Path(directory) / "status.json")
        self.assertFalse(result["responsive"])
        self.assertEqual(result["status"], "missing")

    def test_stale_heartbeat_is_offline(self):
        """即使文字仍为 running，过期心跳也必须判为离线。"""

        with tempfile.TemporaryDirectory() as directory:
            path = write_status(Path(directory))
            result = inspect_bridge_status(path, now=1020.0)
        self.assertFalse(result["responsive"])
        self.assertEqual(result["status"], "stale")

    def test_dead_process_is_offline(self):
        """心跳较新但 PID 已消失时不能继续发送命令。"""

        with tempfile.TemporaryDirectory() as directory:
            path = write_status(Path(directory))
            result = inspect_bridge_status(
                path, now=1001.0, process_checker=lambda pid: False
            )
        self.assertFalse(result["responsive"])
        self.assertEqual(result["status"], "dead-process")

    def test_fresh_heartbeat_and_process_are_online(self):
        """心跳和进程都正常时才允许工具继续工作。"""

        with tempfile.TemporaryDirectory() as directory:
            path = write_status(Path(directory))
            result = inspect_bridge_status(
                path, now=1002.0, process_checker=lambda pid: pid == 1234
            )
        self.assertTrue(result["responsive"])
        self.assertEqual(result["status"], "running")

    def test_future_heartbeat_is_rejected(self):
        """明显位于未来的时间不能绕过新鲜度检查。"""

        with tempfile.TemporaryDirectory() as directory:
            path = write_status(Path(directory), timestamp=1100.0)
            result = inspect_bridge_status(path, now=1000.0)
        self.assertFalse(result["responsive"])
        self.assertEqual(result["status"], "future")

    def test_current_process_is_running(self):
        """当前测试进程必须能在 Windows 和 Linux 上被安全识别。"""

        self.assertTrue(process_is_running(os.getpid()))

    def test_impossible_process_is_not_running(self):
        """明显无效的高 PID 不应被误报为在线。"""

        self.assertFalse(process_is_running(2147483647))


class McpGuardSenderTests(unittest.TestCase):
    """确认防卡包装器只在桥接健康时调用第三方发送器。"""

    def test_offline_bridge_returns_immediately(self):
        """CAE 关闭时应直接返回错误，不创建或等待命令。"""

        calls = []

        def original_sender(*args, **kwargs):
            calls.append((args, kwargs))
            return {"success": True}

        with tempfile.TemporaryDirectory() as directory:
            sender = guarded_sender(
                original_sender, Path(directory) / "status.json"
            )
            result = sender("ping", timeout=10.0)
        self.assertFalse(result["success"])
        self.assertIn("防卡检查失败", result["error"])
        self.assertEqual(calls, [])

    def test_online_bridge_forwards_original_arguments(self):
        """桥接正常时不得改变原工具的超时和参数。"""

        calls = []

        def original_sender(*args, **kwargs):
            calls.append((args, kwargs))
            return {"success": True, "data": "pong"}

        with tempfile.TemporaryDirectory() as directory:
            path = write_status(Path(directory), timestamp=2000.0)
            sender = guarded_sender(
                original_sender,
                path,
                process_checker=lambda pid: True,
            )
            with patch("abaqus_codex.mcp_guard.time.time", return_value=2001.0):
                result = sender("ping", timeout=8.0, value=1)
        self.assertTrue(result["success"])
        self.assertEqual(calls, [(('ping',), {"timeout": 8.0, "value": 1})])


class McpGuardSetupTests(unittest.TestCase):
    """确认修复操作需要明确授权语义并保护用户文件。"""

    def test_unmanaged_guard_file_is_not_overwritten(self):
        """同名用户文件不存在管理标记时必须停止。"""

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "mcp_guard.py").write_text("# user file", encoding="utf-8")
            with self.assertRaises(McpSetupError):
                _ensure_guard_launcher(target)

    @patch("abaqus_codex.mcp_setup._run_command")
    @patch("abaqus_codex.mcp_setup.query_codex_mcp_list")
    def test_existing_registration_is_unchanged_without_repair(
        self, query_mock, run_mock
    ):
        """没有 --repair 时不能删除已有 Codex 注册。"""

        query_mock.return_value = (
            Path("codex.exe"),
            "Name Status\n{0} enabled\n".format(MCP_SERVER_NAME),
        )
        message = _ensure_codex_registration(Path("mcp-home"), repair=False)
        self.assertIn("未替换", message)
        run_mock.assert_not_called()

    @patch("abaqus_codex.mcp_setup._run_command")
    @patch("abaqus_codex.mcp_setup.query_codex_mcp_list")
    def test_repair_replaces_registration_with_guard(self, query_mock, run_mock):
        """明确修复时应先移除旧注册，再注册 mcp_guard.py。"""

        query_mock.return_value = (
            Path("codex.exe"),
            "Name Status\n{0} enabled\n".format(MCP_SERVER_NAME),
        )
        message = _ensure_codex_registration(Path("mcp-home"), repair=True)
        self.assertIn("防卡启动器", message)
        self.assertEqual(run_mock.call_args_list[0].args[0][-2:], ["remove", MCP_SERVER_NAME])
        add_command = run_mock.call_args_list[1].args[0]
        self.assertEqual(add_command[1:4], ["mcp", "add", MCP_SERVER_NAME])
        self.assertTrue(str(add_command[-1]).endswith("mcp_guard.py"))


class McpDoctorModeTests(unittest.TestCase):
    """确认配置完成不等于 MCP 当前可以调用。"""

    @patch("abaqus_codex.doctor.inspect_abaqus_mcp")
    @patch("abaqus_codex.doctor.inspect_abqpy")
    @patch("abaqus_codex.doctor.inspect_abaqus")
    def test_offline_bridge_disables_smart_mode(
        self, abaqus_mock, abqpy_mock, mcp_mock
    ):
        """桥接离线时应保留配置完成状态，但智能模式不可用。"""

        abaqus_mock.return_value = {"usable": True, "version": "2021"}
        abqpy_mock.return_value = {"usable": True, "version": "2021.7.3"}
        mcp_mock.return_value = {"usable": True, "responsive": False}
        result = inspect_environment()
        self.assertTrue(result["ai_configured"])
        self.assertFalse(result["ai_usable"])


if __name__ == "__main__":
    unittest.main()
