# -*- coding: utf-8 -*-
"""测试中文 Markdown 报告中的关键结果和单位。"""

import unittest

from abaqus_codex.configuration import validate_config
from abaqus_codex.report import build_chinese_report
from test_configuration import valid_config, valid_hole_config


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


if __name__ == "__main__":
    unittest.main()
