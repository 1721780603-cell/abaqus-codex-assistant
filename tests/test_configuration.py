# -*- coding: utf-8 -*-
"""测试二维矩形板和中心圆孔板配置的输入校验。"""

import unittest

from abaqus_codex.configuration import (
    ConfigurationError,
    validate_config,
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


def valid_hole_config():
    """返回一份有效的中心圆孔板测试配置。"""

    config = valid_config()
    config["model"].update(
        {
            "type": "plate_with_hole",
            "name": "PlateWithHole2D",
            "height": 50.0,
            "hole_radius": 5.0,
        }
    )
    config["analysis"].update(
        {
            "job_name": "plate_with_hole_tension_2d",
            "hole_mesh_size": 0.5,
        }
    )
    return config


def valid_cantilever_config():
    """返回一份有效的悬臂梁弯曲测试配置。"""

    config = valid_config()
    config["model"].update(
        {
            "type": "cantilever_bending",
            "name": "CantileverBeam2D",
        }
    )
    config["analysis"].update(
        {
            "step_name": "BendingStep",
            "job_name": "cantilever_bending_2d",
            "top_edge_pressure": 1.0,
        }
    )
    del config["analysis"]["right_edge_displacement"]
    return config


def valid_biaxial_config():
    """返回一份有效的方板双向拉伸测试配置。"""

    config = valid_config()
    config["model"].update(
        {
            "type": "biaxial_tension",
            "name": "BiaxialPlate2D",
            "height": 100.0,
        }
    )
    config["analysis"].update(
        {
            "step_name": "BiaxialStep",
            "job_name": "biaxial_tension_2d",
            "top_edge_displacement": 0.1,
            "mesh_size": 5.0,
        }
    )
    return config


class RectangleConfigurationTests(unittest.TestCase):
    """确认错误参数在进入 Abaqus 前被拦截。"""

    def test_valid_config_is_normalized(self):
        """有效配置应转换为稳定的浮点数格式。"""

        result = validate_rectangle_config(valid_config())
        self.assertEqual(result["model"]["type"], "rectangle")
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


class PlateWithHoleConfigurationTests(unittest.TestCase):
    """确认圆孔参数在启动 Abaqus 前得到严格校验。"""

    def test_valid_hole_config_is_normalized(self):
        """有效孔径和孔边网格尺寸应转换为浮点数。"""

        result = validate_config(valid_hole_config())
        self.assertEqual(result["model"]["type"], "plate_with_hole")
        self.assertEqual(result["model"]["hole_radius"], 5.0)
        self.assertEqual(result["analysis"]["hole_mesh_size"], 0.5)

    def test_default_hole_mesh_size_is_added(self):
        """未填写孔边网格时应生成可解释的默认细化尺寸。"""

        config = valid_hole_config()
        del config["analysis"]["hole_mesh_size"]
        result = validate_config(config)
        self.assertEqual(result["analysis"]["hole_mesh_size"], 1.25)

    def test_hole_touching_plate_edge_is_rejected(self):
        """圆孔不能接触或穿出板的外边界。"""

        config = valid_hole_config()
        config["model"]["hole_radius"] = 25.0
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_coarse_hole_mesh_is_rejected(self):
        """孔边网格不能比全局网格更粗。"""

        config = valid_hole_config()
        config["analysis"]["hole_mesh_size"] = 3.0
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_unknown_model_type_is_rejected(self):
        """未知模型类型不能被当作矩形板悄悄运行。"""

        config = valid_hole_config()
        config["model"]["type"] = "unknown_model"
        with self.assertRaises(ConfigurationError):
            validate_config(config)


class CantileverConfigurationTests(unittest.TestCase):
    """确认悬臂梁均布载荷在启动 Abaqus 前得到校验。"""

    def test_valid_pressure_is_normalized(self):
        """有效的均布载荷应转换为浮点数。"""

        result = validate_config(valid_cantilever_config())
        self.assertEqual(result["model"]["type"], "cantilever_bending")
        self.assertEqual(result["analysis"]["top_edge_pressure"], 1.0)
        self.assertNotIn("right_edge_displacement", result["analysis"])

    def test_zero_pressure_is_rejected(self):
        """零载荷不能形成有意义的弯曲入门算例。"""

        config = valid_cantilever_config()
        config["analysis"]["top_edge_pressure"] = 0.0
        with self.assertRaises(ConfigurationError):
            validate_config(config)


class BiaxialConfigurationTests(unittest.TestCase):
    """确认方板两个方向的拉伸位移都经过校验。"""

    def test_two_displacements_are_normalized(self):
        """水平和竖直拉伸位移都应转换为浮点数。"""

        result = validate_config(valid_biaxial_config())
        self.assertEqual(result["model"]["type"], "biaxial_tension")
        self.assertEqual(result["analysis"]["right_edge_displacement"], 0.1)
        self.assertEqual(result["analysis"]["top_edge_displacement"], 0.1)

    def test_missing_top_displacement_is_rejected(self):
        """缺少竖直拉伸位移时不能悄悄退化成单向拉伸。"""

        config = valid_biaxial_config()
        del config["analysis"]["top_edge_displacement"]
        with self.assertRaises(ConfigurationError):
            validate_config(config)

if __name__ == "__main__":
    unittest.main()
