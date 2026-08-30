# -*- coding: utf-8 -*-
"""测试无界面 MCP 后台桥接，不真实启动 Abaqus。"""

import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import Mock, patch

from abaqus_codex.mcp_headless import (
    HEADLESS_PID_NAME,
    McpHeadlessError,
    _abaqus_arguments,
    _write_managed_script,
    inspect_headless_bridge,
    start_headless_bridge,
    stop_headless_bridge,
)


def offline_result():
    """返回一份没有后台进程、插件也离线的状态。"""

    return {
        "running": False,
        "launcher_pid": None,
        "launcher_running": False,
        "bridge_pid": None,
        "bridge_process_running": False,
        "managed_process_running": False,
        "bridge": {"responsive": False, "message": "离线"},
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
    }


class HeadlessCommandTests(unittest.TestCase):
    """确认不同平台的固定命令参数正确。"""

    def test_windows_batch_uses_cmd(self):
        """Windows 批处理必须交给 cmd.exe，但不拼接用户 shell 文本。"""

        with patch.dict("os.environ", {"COMSPEC": r"C:\Windows\System32\cmd.exe"}):
            args = _abaqus_arguments(
                PureWindowsPath(r"C:\SIMULIA\Commands\abaqus.bat"),
                PureWindowsPath(
                    r"C:\Users\User\.abaqus-mcp\mcp_headless_bridge.py"
                ),
                system_name="nt",
            )
        self.assertEqual(args[1:3], ["/d", "/c"])
        self.assertEqual(args[-2], "cae")
        self.assertTrue(args[-1].startswith("noGUI="))

    def test_regular_executable_uses_direct_arguments(self):
        """非批处理命令应直接传递参数列表。"""

        args = _abaqus_arguments(
            PurePosixPath("/opt/abaqus"),
            PurePosixPath("/tmp/bridge.py"),
            system_name="posix",
        )
        self.assertEqual(args, ["/opt/abaqus", "cae", "noGUI=/tmp/bridge.py"])


class HeadlessScriptTests(unittest.TestCase):
    """确认项目脚本可更新，同时保护用户自己的文件。"""

    def test_managed_script_is_created(self):
        """首次启动应生成不含私人模型路径的通用脚本。"""

        with tempfile.TemporaryDirectory() as directory:
            path = _write_managed_script(Path(directory))
            content = path.read_text(encoding="utf-8")
        self.assertIn("mcp_loop", content)
        self.assertNotIn("MODEL_PATH", content)

    def test_unmanaged_script_is_not_overwritten(self):
        """用户自己的同名脚本不能被自动覆盖。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "mcp_headless_bridge.py").write_text(
                "# user script", encoding="utf-8"
            )
            with self.assertRaises(McpHeadlessError):
                _write_managed_script(home)


class HeadlessLifecycleTests(unittest.TestCase):
    """确认启动、状态和停止流程不会误操作其他 Abaqus 进程。"""

    @patch("abaqus_codex.mcp_headless.inspect_bridge_status")
    @patch("abaqus_codex.mcp_headless.process_is_running")
    def test_status_requires_launcher_and_heartbeat(
        self, process_mock, bridge_mock
    ):
        """启动器与插件心跳必须同时在线。"""

        process_mock.return_value = True
        bridge_mock.return_value = {
            "responsive": True,
            "message": "正常",
            "pid": 5678,
        }
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / HEADLESS_PID_NAME).write_text(
                '{"launcher_pid": 1234, "bridge_pid": 5678}', encoding="utf-8"
            )
            result = inspect_headless_bridge(home)
        self.assertTrue(result["running"])

    def test_start_requires_installed_plugin(self):
        """缺少插件时不能只启动一个无效的 Abaqus 进程。"""

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(McpHeadlessError, "请先运行 mcp-setup"):
                start_headless_bridge(Path(directory), timeout_seconds=1)

    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_start_refuses_another_online_bridge(self, inspect_mock):
        """CAE 图形桥接在线时不能再启动第二个命令消费者。"""

        value = offline_result()
        value["bridge"] = {"responsive": True, "message": "在线"}
        inspect_mock.return_value = value
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "abaqus_mcp_plugin.py").write_text("# plugin", encoding="utf-8")
            with self.assertRaisesRegex(McpHeadlessError, "已有"):
                start_headless_bridge(home, timeout_seconds=1)

    @patch("abaqus_codex.mcp_headless.subprocess.Popen")
    @patch("abaqus_codex.mcp_headless.inspect_abaqus_command")
    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_start_waits_for_real_heartbeat(
        self, inspect_mock, inspect_command_mock, popen_mock
    ):
        """只有后台进程和插件心跳都在线时才报告启动成功。"""

        online = offline_result()
        online.update(
            {
                "running": True,
                "launcher_pid": 4321,
                "launcher_running": True,
                "managed_process_running": True,
            }
        )
        online["bridge"] = {"responsive": True, "message": "正常", "pid": 8765}
        final_online = dict(online)
        final_online["bridge_pid"] = 8765
        final_online["bridge_process_running"] = True
        inspect_mock.side_effect = [offline_result(), online, final_online]
        process = Mock(pid=4321)
        process.poll.return_value = None
        popen_mock.return_value = process
        inspect_command_mock.return_value = {
            "usable": True,
            "version": "2025",
        }
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            plugin = home / "abaqus_mcp_plugin.py"
            command = home / "abaqus"
            plugin.write_text("# plugin", encoding="utf-8")
            command.write_text("", encoding="utf-8")
            result = start_headless_bridge(
                home, abaqus_command=command, timeout_seconds=1
            )
        self.assertTrue(result["running"])
        self.assertEqual(popen_mock.call_count, 1)
        inspect_command_mock.assert_called_once_with(command.resolve())

    @patch("abaqus_codex.mcp_headless.subprocess.Popen")
    @patch("abaqus_codex.mcp_headless._write_managed_script")
    @patch("abaqus_codex.mcp_headless.inspect_abaqus_command")
    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_direct_2026_command_is_rejected_before_script_or_process(
        self, inspect_mock, inspect_command_mock, write_mock, popen_mock
    ):
        """显式传入 2026 命令也不能绕过后台桥接的副作用边界。"""

        inspect_mock.return_value = offline_result()
        inspect_command_mock.return_value = {
            "usable": True,
            "version": "2026",
        }
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            command = home / "abq2026.bat"
            (home / "abaqus_mcp_plugin.py").write_text(
                "# plugin", encoding="utf-8"
            )
            command.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(McpHeadlessError, "2026.*已知不兼容"):
                start_headless_bridge(home, abaqus_command=command)

        inspect_command_mock.assert_called_once_with(command.resolve())
        write_mock.assert_not_called()
        popen_mock.assert_not_called()

    @patch("abaqus_codex.mcp_headless.subprocess.Popen")
    @patch("abaqus_codex.mcp_headless._write_managed_script")
    @patch("abaqus_codex.mcp_headless.inspect_abaqus_command")
    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_direct_unknown_command_is_rejected_before_script_or_process(
        self, inspect_mock, inspect_command_mock, write_mock, popen_mock
    ):
        """版本未知或不可用时必须失败关闭，不能写脚本或启动进程。"""

        inspect_mock.return_value = offline_result()
        inspect_command_mock.return_value = {
            "usable": False,
            "version": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            command = home / "abaqus.bat"
            (home / "abaqus_mcp_plugin.py").write_text(
                "# plugin", encoding="utf-8"
            )
            command.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(McpHeadlessError, "无法可靠读取"):
                start_headless_bridge(home, abaqus_command=command)

        inspect_command_mock.assert_called_once_with(command.resolve())
        write_mock.assert_not_called()
        popen_mock.assert_not_called()

    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_stop_without_managed_launcher_is_noop(self, inspect_mock):
        """没有本项目启动的后台进程时，停止命令不能影响 GUI Abaqus。"""

        inspect_mock.return_value = offline_result()
        with tempfile.TemporaryDirectory() as directory:
            result = stop_headless_bridge(Path(directory), timeout_seconds=1)
            self.assertFalse((Path(directory) / "stop.flag").exists())
        self.assertFalse(result["running"])


if __name__ == "__main__":
    unittest.main()
