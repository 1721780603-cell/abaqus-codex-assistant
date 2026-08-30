# -*- coding: utf-8 -*-
"""离线验证卸载只清理能够证明所有权的 MCP 状态。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from abaqus_codex.mcp_headless import (
    HEADLESS_PID_NAME,
    HEADLESS_SCRIPT_NAME,
    MANAGED_HEADLESS_MARKER,
)
from abaqus_codex.mcp_setup import (
    MCP_SERVER_NAME,
    remove_managed_codex_registration,
    stop_managed_headless_bridge_for_uninstall,
)
from abaqus_codex.paths import project_python_executable


def managed_payload(target: Path) -> dict[str, object]:
    """生成与安装器固定注册命令一致的 Codex JSON。"""

    vendor = target / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    return {
        "name": MCP_SERVER_NAME,
        "transport": {
            "type": "stdio",
            "command": str(project_python_executable()),
            "args": [str(target / "mcp_guard.py")],
            "env": {
                "ABAQUS_MCP_HOME": str(target),
                "PYTHONPATH": str(vendor),
            },
            "cwd": None,
            "env_vars": [],
        },
    }


def completed(payload: object, returncode: int = 0) -> SimpleNamespace:
    output = (
        json.dumps(payload).encode("utf-8")
        if returncode == 0
        else b"server not found"
    )
    return SimpleNamespace(returncode=returncode, stdout=output)


class ManagedMcpRegistrationRemovalTests(unittest.TestCase):
    """用户修改过的 Codex 注册必须原样保留。"""

    @patch("abaqus_codex.mcp_setup._run_command")
    @patch("abaqus_codex.mcp_setup.subprocess.run")
    @patch("abaqus_codex.mcp_setup._codex_candidates")
    def test_exact_managed_registration_is_removed(
        self, candidates_mock, run_mock, remove_mock
    ):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / ".abaqus-mcp"
            payload = managed_payload(target)
            codex = Path(directory) / "codex.exe"
            candidates_mock.return_value = [codex]
            run_mock.return_value = completed(payload)

            result = remove_managed_codex_registration(target)

        self.assertTrue(result["removed"])
        self.assertEqual(result["status"], "removed")
        self.assertEqual(
            run_mock.call_args.args[0],
            [str(codex), "mcp", "get", MCP_SERVER_NAME, "--json"],
        )
        self.assertEqual(
            remove_mock.call_args.args[0],
            [str(codex), "mcp", "remove", MCP_SERVER_NAME],
        )

    @patch("abaqus_codex.mcp_setup._run_command")
    @patch("abaqus_codex.mcp_setup.subprocess.run")
    @patch("abaqus_codex.mcp_setup._codex_candidates")
    def test_user_modified_registration_is_preserved(
        self, candidates_mock, run_mock, remove_mock
    ):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / ".abaqus-mcp"
            base = managed_payload(target)
            codex = Path(directory) / "codex.exe"
            candidates_mock.return_value = [codex]
            mutations = (
                (
                    "different executable",
                    lambda data: data["transport"].update(command="python"),
                ),
                (
                    "extra argument",
                    lambda data: data["transport"]["args"].append("--user"),
                ),
                (
                    "different home",
                    lambda data: data["transport"]["env"].update(
                        ABAQUS_MCP_HOME=str(target.parent)
                    ),
                ),
                (
                    "extra environment",
                    lambda data: data["transport"]["env"].update(
                        USER_SETTING="keep"
                    ),
                ),
                (
                    "custom cwd",
                    lambda data: data["transport"].update(cwd=str(target)),
                ),
            )
            for label, mutate in mutations:
                with self.subTest(label=label):
                    payload = json.loads(json.dumps(base))
                    mutate(payload)
                    run_mock.return_value = completed(payload)
                    result = remove_managed_codex_registration(target)
                    self.assertFalse(result["removed"])
                    self.assertEqual(result["status"], "preserved_unmanaged")
            remove_mock.assert_not_called()

    @patch("abaqus_codex.mcp_setup._run_command")
    @patch("abaqus_codex.mcp_setup.subprocess.run")
    @patch("abaqus_codex.mcp_setup._codex_candidates")
    def test_missing_registration_is_a_safe_noop(
        self, candidates_mock, run_mock, remove_mock
    ):
        candidates_mock.return_value = [Path("codex.exe")]
        run_mock.return_value = completed({}, returncode=1)

        result = remove_managed_codex_registration(Path(".abaqus-mcp"))

        self.assertFalse(result["removed"])
        self.assertEqual(result["status"], "not_registered_or_unreadable")
        remove_mock.assert_not_called()

    @patch("abaqus_codex.mcp_setup.subprocess.run")
    @patch("abaqus_codex.mcp_setup._codex_candidates", return_value=[])
    def test_missing_codex_cli_is_a_safe_noop(self, candidates_mock, run_mock):
        result = remove_managed_codex_registration(Path(".abaqus-mcp"))

        self.assertFalse(result["removed"])
        self.assertEqual(result["status"], "cli_unavailable")
        run_mock.assert_not_called()


class ManagedHeadlessStopTests(unittest.TestCase):
    """卸载仅协作式停止带项目标记的后台桥接。"""

    @patch("abaqus_codex.mcp_headless.stop_headless_bridge")
    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_managed_bridge_receives_cooperative_stop(
        self, inspect_mock, stop_mock
    ):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            script = target / HEADLESS_SCRIPT_NAME
            script.write_text(
                "# {0}\n".format(MANAGED_HEADLESS_MARKER), encoding="utf-8"
            )
            (target / HEADLESS_PID_NAME).write_text(
                json.dumps({"script": str(script), "launcher_pid": 123}),
                encoding="utf-8",
            )
            inspect_mock.return_value = {"managed_process_running": True}
            stop_mock.return_value = {"managed_process_running": False}

            result = stop_managed_headless_bridge_for_uninstall(target)

        self.assertTrue(result["stopped"])
        self.assertEqual(result["status"], "stopped")
        stop_mock.assert_called_once_with(target, timeout_seconds=20)

    @patch("abaqus_codex.mcp_headless.stop_headless_bridge")
    @patch("abaqus_codex.mcp_headless.inspect_headless_bridge")
    def test_unmarked_bridge_is_not_touched(self, inspect_mock, stop_mock):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            (target / HEADLESS_SCRIPT_NAME).write_text(
                "# user script\n", encoding="utf-8"
            )
            (target / HEADLESS_PID_NAME).write_text(
                json.dumps(
                    {
                        "script": str(target / HEADLESS_SCRIPT_NAME),
                        "launcher_pid": 123,
                    }
                ),
                encoding="utf-8",
            )
            inspect_mock.return_value = {"managed_process_running": True}

            result = stop_managed_headless_bridge_for_uninstall(target)

        self.assertFalse(result["stopped"])
        self.assertEqual(result["status"], "preserved_unmanaged")
        stop_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
