# -*- coding: utf-8 -*-
"""不用 Abaqus，验证桌面端白名单材料动作文件协议。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from abaqus_codex.desktop_assistant.material_flow import (
    MaterialElasticState,
    build_material_plan,
    compute_material_fingerprint,
    parse_material_command,
)
from abaqus_codex.desktop_assistant.safe_action_bridge import (
    PROTOCOL_NAME,
    STATUS_SCHEMA,
    SafeActionBridgeError,
    SafeActionFileBridge,
    SafeActionOfflineError,
    SafeActionProtocolError,
    SafeActionTimeoutError,
)


def _write_json(path: Path, value: object) -> None:
    """用临时文件替换，模拟插件不会暴露半截 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def _write_running_status(home: Path) -> None:
    """写入一个由测试进程承载的新鲜 Abaqus 插件心跳。"""

    _write_json(
        home / "status.json",
        {
            "schema": STATUS_SCHEMA,
            "version": "0.1.0",
            "abaqus_release": "2021",
            "status": "running",
            "timestamp": time.time(),
            "pid": os.getpid(),
            "message": "test",
        },
    )


def _current_state() -> MaterialElasticState:
    """返回测试使用的确定性实时材料状态。"""

    return MaterialElasticState(
        model_name="Model-1",
        material_name="Steel",
        youngs_modulus=200000.0,
        poisson_ratio=0.3,
        stress_unit="MPa",
        fingerprint=compute_material_fingerprint(
            "Model-1", "Steel", 200000.0, 0.3
        ),
    )


class SafeActionBridgeTests(unittest.TestCase):
    """确认协议只有固定白名单入口，并对失败采取关闭策略。"""

    def _bridge(self, home: Path) -> SafeActionFileBridge:
        """创建使用真实时钟、但不依赖真实进程查询的桥接。"""

        return SafeActionFileBridge(
            home=home,
            process_checker=lambda pid: pid == os.getpid(),
            poll_interval_seconds=0.01,
        )

    def _respond_once(self, home: Path, queue_name: str, result_builder) -> threading.Thread:
        """启动一个只领取单个请求的最小假插件。"""

        def worker() -> None:
            queue_directory = home / queue_name
            deadline = time.monotonic() + 2.0
            request_path = None
            while time.monotonic() < deadline:
                candidates = list(queue_directory.glob("cmd_*.json"))
                if candidates:
                    request_path = candidates[0]
                    break
                time.sleep(0.005)
            if request_path is None:
                return
            processing = home / "processing" / request_path.name
            processing.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(request_path), str(processing))
            request = json.loads(processing.read_text(encoding="utf-8"))
            result = result_builder(request)
            _write_json(home / "results" / (request["id"] + ".json"), result)
            processing.unlink(missing_ok=True)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    def test_offline_check_does_not_create_request_directories(self):
        """插件离线时必须快速失败，也不能遗留假请求。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "safe_actions"
            bridge = self._bridge(home)
            with self.assertRaises(SafeActionOfflineError):
                bridge.inspect_material_elastic("Model-1", "Steel")
            self.assertFalse((home / "requests").exists())
            self.assertFalse((home / "approved").exists())

    def test_inspect_uses_fixed_request_and_strict_material_payload(self):
        """读取旧值只允许固定类型和两个对象名。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _write_running_status(home)

            def result_builder(request):
                self.assertEqual(request["protocol"], PROTOCOL_NAME)
                self.assertEqual(request["type"], "inspect_material_elastic")
                self.assertEqual(
                    request["target"], {"model": "Model-1", "material": "Steel"}
                )
                self.assertNotIn("script", request)
                state = _current_state()
                return {
                    "protocol": PROTOCOL_NAME,
                    "id": request["id"],
                    "success": True,
                    "data": {
                        "model": state.model_name,
                        "material": state.material_name,
                        "youngs_modulus": state.youngs_modulus,
                        "poisson_ratio": state.poisson_ratio,
                        "stress_unit": state.stress_unit,
                        "fingerprint": state.fingerprint,
                    },
                }

            thread = self._respond_once(home, "requests", result_builder)
            state = self._bridge(home).inspect_material_elastic(
                "Model-1", "Steel", timeout_seconds=1.0
            )
            thread.join(timeout=1.0)
            self.assertEqual(state.youngs_modulus, 200000.0)

    def test_snapshot_refresh_uses_empty_fixed_request(self):
        """自动摘要刷新不得携带路径、对象名或脚本文本。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _write_running_status(home)

            def result_builder(request):
                self.assertEqual(request["type"], "refresh_readonly_snapshot")
                self.assertEqual(
                    set(request),
                    {"protocol", "id", "type", "created_at", "expires_at"},
                )
                return {
                    "protocol": PROTOCOL_NAME,
                    "id": request["id"],
                    "success": True,
                    "data": {"refreshed": True},
                }

            thread = self._respond_once(home, "requests", result_builder)
            self._bridge(home).refresh_readonly_snapshot(timeout_seconds=1.0)
            thread.join(timeout=1.0)

    def test_apply_sends_sealed_plan_and_accepts_safe_receipt(self):
        """写队列只接收已校验计划，并只返回工作副本文件名。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _write_running_status(home)
            request = parse_material_command(
                "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
            )
            plan = build_material_plan(request, _current_state())

            def result_builder(envelope):
                self.assertEqual(envelope["type"], "apply_material_plan")
                self.assertEqual(envelope["plan"], plan)
                self.assertNotIn("script", envelope)
                action = plan["actions"][0]
                return {
                    "protocol": PROTOCOL_NAME,
                    "id": envelope["id"],
                    "success": True,
                    "data": {
                        "plan_id": plan["plan_id"],
                        "action_id": action["id"],
                        "model": "Model-1",
                        "material": "Steel",
                        "before": action["before"],
                        "after": action["after"],
                        "working_copy_name": "plate__aca_edit_001.cae",
                        "same_directory": True,
                        "original_untouched": True,
                    },
                }

            thread = self._respond_once(home, "approved", result_builder)
            receipt = self._bridge(home).apply_material_plan(
                plan, timeout_seconds=1.0
            )
            thread.join(timeout=1.0)
            self.assertEqual(receipt["working_copy_name"], "plate__aca_edit_001.cae")
            self.assertNotIn("path", receipt)

    def test_error_code_does_not_echo_plugin_path_or_details(self):
        """执行端错误原文可能含路径，桌面端只能显示固定中文。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _write_running_status(home)

            def result_builder(request):
                return {
                    "protocol": PROTOCOL_NAME,
                    "id": request["id"],
                    "success": False,
                    "error_code": "MODEL_NOT_FOUND",
                    "error_message": r"C:\Users\Alice\secret.cae",
                }

            thread = self._respond_once(home, "requests", result_builder)
            with self.assertRaises(SafeActionBridgeError) as captured:
                self._bridge(home).inspect_material_elastic(
                    "Model-1", "Steel", timeout_seconds=1.0
                )
            thread.join(timeout=1.0)
            self.assertNotIn("Alice", str(captured.exception))
            self.assertNotIn("secret", str(captured.exception))

    def test_invalid_plan_is_rejected_before_any_dispatch(self):
        """缺少签名或字段的字典不能进入已批准队列。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with self.assertRaises(SafeActionProtocolError):
                self._bridge(home).apply_material_plan({})
            self.assertFalse((home / "approved").exists())

    def test_claimed_write_timeout_is_marked_as_unknown_outcome(self):
        """已被插件领取但未回执时，界面必须阻止用户盲目重试。"""

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            _write_running_status(home)
            request = parse_material_command(
                "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
            )
            plan = build_material_plan(request, _current_state())

            def claim_without_result() -> None:
                queue_directory = home / "approved"
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    candidates = list(queue_directory.glob("cmd_*.json"))
                    if candidates:
                        processing = home / "processing" / candidates[0].name
                        processing.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(str(candidates[0]), str(processing))
                        return
                    time.sleep(0.005)

            thread = threading.Thread(target=claim_without_result, daemon=True)
            thread.start()
            with self.assertRaises(SafeActionTimeoutError) as captured:
                self._bridge(home).apply_material_plan(
                    plan, timeout_seconds=0.15
                )
            thread.join(timeout=1.0)
            self.assertTrue(captured.exception.outcome_unknown)


if __name__ == "__main__":
    unittest.main()
