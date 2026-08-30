# -*- coding: utf-8 -*-
"""不创建真实窗口，测试只读桌面助手的协议和状态逻辑。"""

from __future__ import annotations

import json
import ast
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from abaqus_codex.desktop_assistant import _configure_windows_dpi_awareness
from abaqus_codex.desktop_assistant.app import (
    STATUS_FONT_SIZE,
    _ui_scale_from_dpi,
    _window_metrics_for_dpi,
)
from abaqus_codex.desktop_assistant.bridge import (
    BridgeOfflineError,
    BridgeProtocolError,
    BridgeTimeoutError,
    FileIpcReadOnlyBridge,
    MAX_RESULT_BYTES,
    ReadOnlyBridgeError,
)
from abaqus_codex.desktop_assistant import _configure_tk_runtime
from abaqus_codex.desktop_assistant.controller import (
    classify_command,
    normalize_command,
    refresh_read_only,
)
from abaqus_codex.desktop_assistant.mock_bridge import MockReadOnlyBridge
from abaqus_codex.desktop_assistant.snapshot import (
    format_snapshot,
    normalize_model_info,
)


def write_online_status(home: Path) -> None:
    """写入当前测试进程的最新心跳。"""

    (home / "status.json").write_text(
        json.dumps(
            {
                "status": "running",
                "timestamp": time.time(),
                "pid": os.getpid(),
                "message": "test",
            }
        ),
        encoding="utf-8",
    )


class TkRuntimeDiscoveryTests(unittest.TestCase):
    """确认 Windows 启动器只为当前进程定位已有 Tcl/Tk。"""

    def test_existing_tcl_and_tk_are_discovered(self):
        """同时发现 init.tcl 和 tk.tcl 时应写入两个局部环境值。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tcl_directory = root / "tcl8.6"
            tk_directory = root / "tk8.6"
            tcl_directory.mkdir()
            tk_directory.mkdir()
            (tcl_directory / "init.tcl").write_text("# test", encoding="ascii")
            (tk_directory / "tk.tcl").write_text("# test", encoding="ascii")
            environment = {}

            configured = _configure_tk_runtime(
                candidate_roots=[root], environment=environment
            )

            self.assertTrue(configured)
            self.assertEqual(environment["TCL_LIBRARY"], str(tcl_directory))
            self.assertEqual(environment["TK_LIBRARY"], str(tk_directory))

    def test_incomplete_or_explicit_configuration_is_not_overwritten(self):
        """候选文件不完整时停止；用户显式配置时保持原值。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tcl_directory = root / "tcl8.6"
            tcl_directory.mkdir()
            (tcl_directory / "init.tcl").write_text("# test", encoding="ascii")
            environment = {}
            self.assertFalse(
                _configure_tk_runtime(
                    candidate_roots=[root], environment=environment
                )
            )
            self.assertEqual(environment, {})

        explicit = {"TCL_LIBRARY": "custom-tcl", "TK_LIBRARY": "custom-tk"}
        self.assertTrue(
            _configure_tk_runtime(candidate_roots=[], environment=explicit)
        )
        self.assertEqual(explicit["TCL_LIBRARY"], "custom-tcl")
        self.assertEqual(explicit["TK_LIBRARY"], "custom-tk")


class WindowsDpiAwarenessTests(unittest.TestCase):
    """确认窗口创建前优先启用清晰的按显示器 DPI 渲染。"""

    def test_per_monitor_v2_is_preferred(self):
        """新 Windows 必须优先使用 Per-Monitor V2。"""

        user32 = SimpleNamespace(
            SetProcessDpiAwarenessContext=lambda context: 1,
            SetProcessDPIAware=lambda: 1,
        )
        shcore = SimpleNamespace(SetProcessDpiAwareness=lambda value: 0)
        result = _configure_windows_dpi_awareness(
            platform_name="nt", user32=user32, shcore=shcore
        )
        self.assertEqual(result, "per-monitor-v2")

    def test_older_windows_uses_ordered_fallbacks(self):
        """V2 不可用时依次回退到按显示器和系统 DPI 感知。"""

        user32 = SimpleNamespace(
            SetProcessDpiAwarenessContext=lambda context: 0,
            SetProcessDPIAware=lambda: 1,
        )
        shcore = SimpleNamespace(SetProcessDpiAwareness=lambda value: 0)
        self.assertEqual(
            _configure_windows_dpi_awareness(
                platform_name="nt", user32=user32, shcore=shcore
            ),
            "per-monitor",
        )

        failing_shcore = SimpleNamespace(SetProcessDpiAwareness=lambda value: 1)
        self.assertEqual(
            _configure_windows_dpi_awareness(
                platform_name="nt", user32=user32, shcore=failing_shcore
            ),
            "system",
        )

    def test_non_windows_does_not_call_native_apis(self):
        """非 Windows 环境必须保持无副作用。"""

        self.assertEqual(
            _configure_windows_dpi_awareness(platform_name="posix"),
            "not-windows",
        )

    def test_125_percent_metrics_keep_the_existing_layout_proportions(self):
        """120 DPI 应把窗口和最小尺寸同步放大到 125%。"""

        self.assertEqual(_ui_scale_from_dpi(120.0), 1.25)
        self.assertEqual(
            _window_metrics_for_dpi(120.0),
            (1400, 950, 1150, 900),
        )

    def test_untrusted_dpi_falls_back_to_100_percent(self):
        """异常或不合理 DPI 不能制造巨大或不可见窗口。"""

        for dpi in (float("nan"), float("inf"), 0.0, 48.0, 500.0):
            with self.subTest(dpi=dpi):
                self.assertEqual(_ui_scale_from_dpi(dpi), 1.0)
                self.assertEqual(
                    _window_metrics_for_dpi(dpi),
                    (1120, 760, 920, 720),
                )

    def test_colored_status_badges_avoid_tiny_bold_text(self):
        """彩色状态块至少使用 10pt，避免高 DPI 下小号粗体发虚。"""

        self.assertGreaterEqual(STATUS_FONT_SIZE, 10)
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abaqus_codex"
            / "desktop_assistant"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(source.count("font=self._font(STATUS_FONT_SIZE)"), 3)


class FileIpcReadOnlyBridgeTests(unittest.TestCase):
    """确认真实适配器只发布白名单命令，并能快速失败。"""

    def test_offline_bridge_does_not_create_command_directory(self):
        """没有心跳时应立即失败，不能制造等待中的命令。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bridge = FileIpcReadOnlyBridge(home=home)
            with self.assertRaises(BridgeOfflineError):
                bridge.get_model_info(timeout_seconds=0.1)
            self.assertFalse((home / "commands").exists())

    def test_arbitrary_script_command_is_rejected(self):
        """即使调用内部方法也不能发送 execute_script。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_online_status(home)
            bridge = FileIpcReadOnlyBridge(
                home=home, process_checker=lambda pid: True
            )
            with self.assertRaisesRegex(BridgeProtocolError, "非白名单"):
                bridge._request("execute_script", timeout_seconds=0.1)
            self.assertFalse((home / "commands").exists())

    def test_get_model_info_uses_atomic_json_and_reads_matching_result(self):
        """模拟插件只看到完整 JSON，并返回同一请求 ID。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_online_status(home)
            bridge = FileIpcReadOnlyBridge(
                home=home,
                poll_interval_seconds=0.01,
                process_checker=lambda pid: True,
            )
            seen_command = {}

            def fake_plugin() -> None:
                """等待一个命令文件并生成最小只读结果。"""

                commands = home / "commands"
                deadline = time.monotonic() + 1.0
                command_path = None
                while time.monotonic() < deadline:
                    matches = list(commands.glob("cmd_*.json")) if commands.exists() else []
                    if matches:
                        command_path = matches[0]
                        break
                    time.sleep(0.005)
                if command_path is None:
                    return
                command = json.loads(command_path.read_text(encoding="utf-8"))
                seen_command.update(command)
                command_path.unlink()
                results = home / "results"
                results.mkdir(exist_ok=True)
                (results / (command["id"] + ".json")).write_text(
                    json.dumps(
                        {
                            "id": command["id"],
                            "success": True,
                            "data": {
                                "models": [],
                                "working_directory": "C:/private",
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=fake_plugin)
            worker.start()
            result = bridge.get_model_info(timeout_seconds=1.0)
            worker.join(timeout=1.0)

            self.assertEqual(result["models"], [])
            self.assertEqual(seen_command["type"], "get_model_info")
            self.assertEqual(seen_command["protocol"], "abaqus-codex-readonly/1")
            self.assertFalse(any((home / "commands").glob("cmd_*")))
            self.assertFalse(any((home / "results").glob("*.json")))

    def test_timeout_removes_its_own_command(self):
        """插件不响应时只等短超时，并删除本次查询文件。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_online_status(home)
            bridge = FileIpcReadOnlyBridge(
                home=home,
                poll_interval_seconds=0.01,
                process_checker=lambda pid: True,
            )
            with self.assertRaises(BridgeTimeoutError):
                bridge.get_model_info(timeout_seconds=0.1)
            self.assertFalse(any((home / "commands").glob("cmd_*")))

    def test_partial_result_is_retried_until_complete(self):
        """第三方插件先创建半段 JSON 时，客户端不应立刻报错。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_online_status(home)
            bridge = FileIpcReadOnlyBridge(
                home=home,
                poll_interval_seconds=0.01,
                process_checker=lambda pid: True,
            )

            def fake_partial_writer() -> None:
                """先写不完整响应，再补成有效 JSON。"""

                commands = home / "commands"
                deadline = time.monotonic() + 1.0
                command_path = None
                while time.monotonic() < deadline:
                    matches = list(commands.glob("cmd_*.json")) if commands.exists() else []
                    if matches:
                        command_path = matches[0]
                        break
                    time.sleep(0.005)
                if command_path is None:
                    return
                command = json.loads(command_path.read_text(encoding="utf-8"))
                command_path.unlink()
                results = home / "results"
                results.mkdir(exist_ok=True)
                result_path = results / (command["id"] + ".json")
                result_path.write_text('{"id":', encoding="utf-8")
                time.sleep(0.04)
                result_path.write_text(
                    json.dumps(
                        {
                            "id": command["id"],
                            "success": True,
                            "data": {"models": []},
                        }
                    ),
                    encoding="utf-8",
                )

            worker = threading.Thread(target=fake_partial_writer)
            worker.start()
            result = bridge.get_model_info(timeout_seconds=1.0)
            worker.join(timeout=1.0)
            self.assertEqual(result, {"models": []})

    def test_oversized_result_is_rejected_from_one_file_handle(self):
        """结果超过上限时不得继续解析，避免无界读取。"""

        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "aca_test.json"
            result_path.write_bytes(b"x" * (MAX_RESULT_BYTES + 1))
            bridge = FileIpcReadOnlyBridge(home=Path(directory))
            with self.assertRaisesRegex(BridgeProtocolError, "2 MiB"):
                bridge._read_result(result_path, "aca_test")

    def test_failed_result_does_not_expose_third_party_path(self):
        """第三方错误中的用户名和工程路径不得进入异常文本。"""

        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "aca_test.json"
            result_path.write_text(
                json.dumps(
                    {
                        "id": "aca_test",
                        "success": False,
                        "error": r"C:\Users\Alice\secret\paper.cae",
                    }
                ),
                encoding="utf-8",
            )
            bridge = FileIpcReadOnlyBridge(home=Path(directory))
            with self.assertRaises(ReadOnlyBridgeError) as caught:
                bridge._read_result(result_path, "aca_test")
            message = str(caught.exception)
            self.assertNotIn("Alice", message)
            self.assertNotIn("paper.cae", message)


class SnapshotTests(unittest.TestCase):
    """确认第三方结果被裁剪，不显示完整路径或虚构单位。"""

    def test_snapshot_discards_working_directory(self):
        """模型摘要不得包含第三方返回的私人工作目录。"""

        snapshot = normalize_model_info(
            {
                "working_directory": r"C:\secret\paper",
                "current_viewport": "Viewport: 1",
                "models": [
                    {
                        "name": "Model-1",
                        "parts": ["Plate"],
                        "materials": ["Steel"],
                        "steps": ["Initial"],
                        "assemblies": ["Plate-1"],
                        "loads": [],
                        "bcs": ["Fixed"],
                        "interactions": [],
                    }
                ],
            },
            source="测试",
        )
        text = format_snapshot(snapshot)
        self.assertNotIn("secret", text)
        self.assertNotIn("paper", text)
        self.assertIn("单位约定：未知", text)
        self.assertIn("读取时间：", text)
        self.assertIn("Model-1", text)
        self.assertIn("模型未被修改", text)

    def test_snapshot_hides_raw_error_path(self):
        """部分读取失败时只显示安全警告，不显示第三方原始异常。"""

        snapshot = normalize_model_info(
            {
                "models": [],
                "error": r"cannot open C:\Users\Alice\secret\paper.cae",
            },
            source="测试",
        )
        text = format_snapshot(snapshot)
        self.assertIn("某些对象名称无法读取", text)
        self.assertNotIn("Alice", text)
        self.assertNotIn("paper.cae", text)

    def test_same_allowed_data_has_same_fingerprint(self):
        """路径或当前视口变化不应被误判成模型对象变化。"""

        first = normalize_model_info(
            {
                "models": [],
                "working_directory": "C:/one",
                "current_viewport": "Viewport: 1",
            },
            source="测试",
        )
        second = normalize_model_info(
            {
                "models": [],
                "working_directory": "D:/two",
                "current_viewport": "Viewport: 2",
            },
            source="测试",
        )
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_extreme_external_timestamp_falls_back_safely(self):
        """兼容数据源给出极端时间时，摘要仍应安全生成。"""

        snapshot = normalize_model_info(
            {"models": [], "snapshot_generated_at": 1e300},
            source="测试",
        )
        text = format_snapshot(snapshot)
        self.assertIn("读取时间：", text)
        self.assertIn("模型未被修改", text)


class ControllerTests(unittest.TestCase):
    """确认中文命令不会越过当前只读范围。"""

    def test_model_info_command_routes_to_refresh(self):
        """查看模型信息应触发固定读取。"""

        decision = classify_command("请查看当前模型信息")
        self.assertEqual(decision.action, "refresh")

    def test_supported_material_command_routes_to_plan_only(self):
        """完整材料命令应只进入计划阶段，不直接执行。"""

        decision = classify_command(
            "把 Model-1 中 Steel 的弹性模量改为 2.1e5 MPa"
        )
        self.assertEqual(decision.action, "material_plan")
        self.assertEqual(decision.material_request.model_name, "Model-1")
        self.assertIn("点击“应用修改”前", decision.response)

    def test_incomplete_material_command_is_rejected(self):
        """缺模型名的自然语言不能被猜测或直接执行。"""

        decision = classify_command("把钢材弹性模量改为 2.1e5 MPa")
        self.assertEqual(decision.action, "invalid_material")

    def test_command_is_limited_and_control_characters_are_removed(self):
        """长命令和换行不会进入本地日志语义。"""

        command = normalize_command("查看\n模型\x00" + "x" * 1000)
        self.assertNotIn("\n", command)
        self.assertNotIn("\x00", command)
        self.assertLessEqual(len(command), 500)

    def test_mock_mode_is_explicit_in_summary(self):
        """模拟数据必须在连接状态和摘要中同时标注。"""

        state = refresh_read_only(MockReadOnlyBridge())
        self.assertEqual(state.tone, "mock")
        self.assertIn("模拟模式", state.connection_text)
        self.assertIn("模拟数据", state.summary_text)
        self.assertFalse(state.model_changed)

    def test_status_exception_becomes_safe_recoverable_state(self):
        """连接检查异常时应返回可恢复状态，且不泄露本机路径。"""

        class BrokenBridge:
            """模拟本地连接目录突然不可访问。"""

            is_mock = False

            def inspect_status(self):
                raise OSError(r"C:\Users\Alice\secret denied")

            def get_model_info(self, timeout_seconds=5.0):
                raise AssertionError("离线后不应读取模型")

        state = refresh_read_only(BrokenBridge())
        self.assertEqual(state.tone, "error")
        self.assertIn("模型是否改变：没有", state.summary_text)
        self.assertNotIn("Alice", state.summary_text)
        self.assertNotIn("secret", state.log_text)


class DesktopSourceSafetyTests(unittest.TestCase):
    """不加载 Tk，静态确认写入口和高风险命令保持关闭。"""

    def test_app_source_has_confirmed_whitelist_apply_button(self):
        """应用按钮必须默认锁定，并且只能发送固定材料计划。"""

        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abaqus_codex"
            / "desktop_assistant"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("尚无可应用计划｜不会自动修改模型", source)
        self.assertIn("首版关闭工具和联网，只提供中文咨询", source)
        self.assertIn("CodexReadOnlyClient", source)
        self.assertIn("AI 咨询已经完成，但尚未生成可执行修改计划", source)
        self.assertIn("Codex 已连接", source)
        self.assertIn("codex_live_connected", source)
        self.assertIn("停止回答", source)
        self.assertIn("client.interrupt", source)
        self.assertIn("AI 推理档位：", source)
        self.assertIn("REASONING_MODE_EFFORT", source)
        self.assertIn("self.apply_button", source)
        self.assertIn("self.apply_button.grid(\n            row=2", source)
        self.assertIn("messagebox.askyesno", source)
        self.assertIn("apply_material_plan", source)
        self.assertNotIn("execute_script", source)
        self.assertNotIn("submit_job", source)

    def test_worker_has_exception_boundary(self):
        """后台线程意外失败时仍必须向界面队列返回状态。"""

        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abaqus_codex"
            / "desktop_assistant"
            / "app.py"
        ).read_text(encoding="utf-8")
        worker_source = source.split("def _refresh_worker", 1)[1].split(
            "def _drain_result_queue", 1
        )[0]
        self.assertIn("except Exception", worker_source)
        self.assertIn("self.result_queue.put(state)", worker_source)

    def test_safety_label_keeps_widget_instead_of_grid_result(self):
        """需要后续更新的标签变量不能误存成 grid() 的 None。"""

        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abaqus_codex"
            / "desktop_assistant"
            / "app.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assignments = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "safety_label":
                    assignments.append(node.value)
        self.assertEqual(len(assignments), 1)
        value = assignments[0]
        self.assertIsInstance(value, ast.Call)
        self.assertIsInstance(value.func, ast.Attribute)
        self.assertEqual(value.func.attr, "Label")


if __name__ == "__main__":
    unittest.main()
