# -*- coding: utf-8 -*-
"""测试中文 Markdown 报告中的关键结果和单位。"""

import unittest

from abaqus_codex.configuration import validate_config
from abaqus_codex.report import build_chinese_report
from test_configuration import (
    valid_biaxial_config,
    valid_cantilever_config,
    valid_config,
    valid_hole_config,
    valid_moving_load_config,
)


def example_results(config):
    """构造只用于报告测试的最小结果数据。"""

    return {
        "job_name": config["analysis"]["job_name"],
        "model_name": config["model"]["name"],
        "generated_at": "2026-08-11T10:00:00Z",
        "abaqus_python_version": "2.7.15",
        "maximum_displacement": 0.2,
        "maximum_displacement_location": {
            "instance": "Part-1",
            "node_label": 10,
        },
        "maximum_mises_stress": 300.0,
        "maximum_mises_stress_location": {
            "instance": "Part-1",
            "element_label": 20,
            "integration_point": 1,
        },
        "config": validate_config(config),
    }


class ChineseReportTests(unittest.TestCase):
    """确保报告不会遗漏第一阶段要求的两个极值。"""

    def test_report_contains_main_results(self):
        """报告应包含最大位移、最大 Mises 应力和对应单位。"""

        results = {
            "job_name": "rectangle_tension_2d",
            "model_name": "RectanglePlate2D",
            "generated_at": "2026-08-10T10:00:00Z",
            "abaqus_python_version": "2.7.15",
            "maximum_displacement": 0.1001,
            "maximum_displacement_location": {
                "instance": "Plate-1",
                "node_label": 10,
            },
            "maximum_mises_stress": 210.0,
            "maximum_mises_stress_location": {
                "instance": "Plate-1",
                "element_label": 20,
                "integration_point": 1,
            },
            "config": valid_config(),
        }

        report = build_chinese_report(results)

        self.assertIn("最大位移模：0.1001 mm", report)
        self.assertIn("最大 Mises 应力：210 MPa", report)
        self.assertIn("二维平面应力", report)

    def test_hole_report_contains_geometry_and_mesh(self):
        """圆孔板报告应明确记录孔径和孔边局部网格。"""

        results = {
            "job_name": "plate_with_hole_tension_2d",
            "model_name": "PlateWithHole2D",
            "generated_at": "2026-08-11T10:00:00Z",
            "abaqus_python_version": "2.7.15",
            "maximum_displacement": 0.1002,
            "maximum_displacement_location": {
                "instance": "Plate-1",
                "node_label": 30,
            },
            "maximum_mises_stress": 650.0,
            "maximum_mises_stress_location": {
                "instance": "Plate-1",
                "element_label": 40,
                "integration_point": 1,
            },
            "config": validate_config(valid_hole_config()),
        }

        report = build_chinese_report(results)

        self.assertIn("二维中心圆孔板拉伸分析报告", report)
        self.assertIn("圆孔半径：5 mm", report)
        self.assertIn("孔边网格尺寸：0.5 mm", report)
        self.assertIn("网格收敛性分析", report)

    def test_cantilever_report_contains_load_and_fixed_end(self):
        """悬臂梁报告应明确写出固定端和向下均布载荷。"""

        report = build_chinese_report(
            example_results(valid_cantilever_config())
        )

        self.assertIn("二维悬臂梁均布载荷弯曲分析报告", report)
        self.assertIn("上边界均布载荷：1 MPa", report)
        self.assertIn("形成固定端", report)
        self.assertIn("材料力学梁理论", report)

    def test_biaxial_report_contains_two_displacements(self):
        """双向拉伸报告应分别记录水平和竖直位移。"""

        report = build_chinese_report(example_results(valid_biaxial_config()))

        self.assertIn("二维方板双向拉伸分析报告", report)
        self.assertIn("右边界：施加 0.1 mm 的水平拉伸位移", report)
        self.assertIn("上边界：施加 0.1 mm 的竖直拉伸位移", report)
        self.assertIn("均匀双向应力状态", report)

    def test_moving_load_report_contains_dynamic_information(self):
        """移动轮载报告应包含 DLOAD、速度、动力时间和竖向位移。"""

        config = validate_config(valid_moving_load_config())
        results = {
            "job_name": config["analysis"]["job_name"],
            "model_name": config["model"]["name"],
            "generated_at": "2026-08-11T10:00:00Z",
            "abaqus_python_version": "2.7.15",
            "user_subroutine": "moving_pressure_dload.for",
            "frame_count": 211,
            "maximum_displacement": 0.02,
            "maximum_displacement_location": {
                "instance": "ROAD-1",
                "node_label": 10,
                "frame_time": 0.2,
            },
            "maximum_vertical_displacement": 0.019,
            "maximum_vertical_displacement_location": {
                "instance": "ROAD-1",
                "node_label": 10,
                "frame_time": 0.2,
                "signed_value": -0.019,
            },
            "maximum_mises_stress": 0.8,
            "maximum_mises_stress_location": {
                "instance": "ROAD-1",
                "element_label": 20,
                "integration_point": 1,
                "frame_time": 0.21,
            },
            "config": config,
        }

        report = build_chinese_report(results)

        self.assertIn("三维路面单轮移动载荷教学分析报告", report)
        self.assertIn("moving_pressure_dload.for", report)
        self.assertIn("约 36 km/h", report)
        self.assertIn("全程最大竖向位移绝对值：0.019 mm", report)
        self.assertIn("不能直接代表三级公路正式设计", report)


if __name__ == "__main__":
    unittest.main()
