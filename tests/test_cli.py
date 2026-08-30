# -*- coding: utf-8 -*-
"""测试面向初学者的命令行检查点。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Dict
from unittest.mock import patch

from abaqus_codex.cli import main


def rectangle_config() -> Dict[str, object]:
    """返回一份最小且有效的矩形板教学配置。"""

    return {
        "model": {
            "type": "rectangle",
            "name": "BeginnerPlate",
            "length": 100.0,
            "height": 20.0,
            "thickness": 1.0,
        },
        "material": {
            "name": "Steel",
            "youngs_modulus": 210000.0,
            "poisson_ratio": 0.3,
        },
        "analysis": {
            "step_name": "TensionStep",
            "job_name": "beginner_plate",
            "right_edge_displacement": 0.1,
            "mesh_size": 2.0,
            "num_cpus": 1,
        },
        "units": {"length": "mm", "stress": "MPa"},
    }


class ValidateCommandTests(unittest.TestCase):
    """确认 validate 只检查配置，并提供清楚的中文结果。"""

    def _write_config(
        self, directory: str, data: Dict[str, object]
    ) -> Path:
        """把测试配置写入临时目录，不污染项目示例。"""

        path = Path(directory) / "model.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def test_valid_config_passes_without_running_abaqus(self):
        """有效配置应通过，并明确说明 Abaqus 尚未启动。"""

        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory, rectangle_config())
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["validate", "--config", str(path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("配置检查通过", output.getvalue())
        self.assertIn("Abaqus 尚未启动", output.getvalue())

    def test_invalid_config_returns_beginner_friendly_error(self):
        """错误尺寸应返回非零退出码和已有中文校验提示。"""

        config = rectangle_config()
        model = config["model"]
        assert isinstance(model, dict)
        model["length"] = 0.0
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_config(directory, config)
            error_output = io.StringIO()
            with redirect_stderr(error_output):
                exit_code = main(["validate", "--config", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertIn("模型长度必须大于零", error_output.getvalue())


class AbqpySetupCommandTests(unittest.TestCase):
    """确认统一 CLI 会把用户授权原样交给 abqpy 安装器。"""

    @patch("abaqus_codex.abqpy_setup.main", return_value=0)
    def test_yes_routes_to_abqpy_setup_installer(self, setup_main_mock):
        """abqpy-setup --yes 应调用安装器，不能误入 MCP 或建模流程。"""

        exit_code = main(["abqpy-setup", "--yes"])

        self.assertEqual(exit_code, 0)
        setup_main_mock.assert_called_once_with(confirmed=True)


class McpHeadlessCommandRoutingTests(unittest.TestCase):
    """确认 CLI 把启动请求交给负责版本门禁的后台桥接边界。"""

    @patch("abaqus_codex.mcp_headless.print_headless_status")
    @patch(
        "abaqus_codex.mcp_headless.start_headless_bridge",
        return_value={"running": True},
    )
    def test_start_delegates_timeout_to_headless_boundary(
        self, start_mock, print_mock
    ):
        """CLI 不重复版本判断，只向受保护的启动函数传递参数。"""

        exit_code = main(["mcp-headless", "start", "--timeout", "7"])

        self.assertEqual(exit_code, 0)
        start_mock.assert_called_once_with(timeout_seconds=7)
        print_mock.assert_called_once_with({"running": True})


class DistributionIntegrationCommandTests(unittest.TestCase):
    """确认自包含安装器只通过固定的用户集成边界写入。"""

    @patch("abaqus_codex.distribution_integration.integration_setup")
    def test_setup_forwards_confirmation_and_custom_codex_home(self, setup_mock):
        setup_mock.return_value = {
            "skill": {"target": "C:/Codex/skills/abaqus-modeling-guide"},
            "plugin": {"message": "已跳过。"},
            "manifest_path": "C:/Data/integration-manifest.json",
            "dry_run": False,
        }
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "integration-setup",
                    "--yes",
                    "--codex-home",
                    "C:/Codex",
                    "--data-root",
                    "C:/Data",
                ]
            )

        self.assertEqual(exit_code, 0)
        setup_mock.assert_called_once_with(
            confirmed=True,
            codex_home_path=Path("C:/Codex"),
            data_root=Path("C:/Data"),
            dry_run=False,
        )
        self.assertIn("用户集成清单", output.getvalue())

    @patch("abaqus_codex.distribution_integration.integration_remove")
    def test_remove_requires_explicit_yes_and_reports_recoverable_status(
        self, remove_mock
    ):
        remove_mock.return_value = {
            "skill": {"status": "restored_backup"},
            "plugin": {"status": "not_managed"},
        }
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["integration-remove", "--yes"])

        self.assertEqual(exit_code, 0)
        remove_mock.assert_called_once_with(confirmed=True, data_root=None)
        self.assertIn("restored_backup", output.getvalue())

    @patch("abaqus_codex.distribution_integration.integration_remove")
    @patch("abaqus_codex.cli.resource_root", side_effect=RuntimeError("资源损坏"))
    def test_remove_still_runs_when_installed_resources_are_damaged(
        self, resource_root_mock, remove_mock
    ):
        """卸载清理不能因只读发布资源缺失而连参数都无法解析。"""

        remove_mock.return_value = {
            "skill": {"status": "moved_to_recovery"},
            "plugin": {"status": "not_managed"},
        }
        exit_code = main(
            ["integration-remove", "--yes", "--data-root", "C:/Data"]
        )

        self.assertEqual(exit_code, 0)
        resource_root_mock.assert_not_called()
        remove_mock.assert_called_once_with(
            confirmed=True, data_root=Path("C:/Data")
        )


if __name__ == "__main__":
    unittest.main()
