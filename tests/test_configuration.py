# -*- coding: utf-8 -*-
"""测试二维矩形板配置的输入校验。"""

import unittest

from abaqus_codex.configuration import (
    ConfigurationError,
    validate_rectangle_config,
)


def valid_config():
    """返回一份可独立修改的有效测试配置。"""

    return {
        "model": {
            "name": "RectanglePlate2D",
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
            "job_name": "rectangle_tension_2d",
            "right_edge_displacement": 0.1,
            "mesh_size": 2.0,
            "num_cpus": 1,
        },
        "units": {"length": "mm", "stress": "MPa"},
    }


class RectangleConfigurationTests(unittest.TestCase):
    """确认错误参数在进入 Abaqus 前被拦截。"""

    def test_valid_config_is_normalized(self):
        """有效配置应转换为稳定的浮点数格式。"""

        result = validate_rectangle_config(valid_config())
        self.assertEqual(result["model"]["length"], 100.0)
        self.assertEqual(result["analysis"]["num_cpus"], 1)

    def test_negative_length_is_rejected(self):
        """负板长不应进入建模脚本。"""

        config = valid_config()
        config["model"]["length"] = -1.0
        with self.assertRaises(ConfigurationError):
            validate_rectangle_config(config)

    def test_invalid_poisson_ratio_is_rejected(self):
        """不可压缩极限之外的泊松比应被拒绝。"""

        config = valid_config()
        config["material"]["poisson_ratio"] = 0.5
        with self.assertRaises(ConfigurationError):
            validate_rectangle_config(config)

    def test_unsafe_job_name_is_rejected(self):
        """含命令符号的作业名应被拒绝。"""

        config = valid_config()
        config["analysis"]["job_name"] = "job & delete"
        with self.assertRaises(ConfigurationError):
            validate_rectangle_config(config)

    def test_oversized_mesh_is_rejected(self):
        """大于最短边的网格尺寸应被拒绝。"""

        config = valid_config()
        config["analysis"]["mesh_size"] = 25.0
        with self.assertRaises(ConfigurationError):
            validate_rectangle_config(config)


if __name__ == "__main__":
    unittest.main()
