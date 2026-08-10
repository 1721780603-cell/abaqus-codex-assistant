# -*- coding: utf-8 -*-
"""测试中文 Markdown 报告中的关键结果和单位。"""

import unittest

from abaqus_codex.report import build_chinese_report
from test_configuration import valid_config


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


if __name__ == "__main__":
    unittest.main()
