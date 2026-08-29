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


if __name__ == "__main__":
    unittest.main()
