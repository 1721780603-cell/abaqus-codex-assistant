# -*- coding: utf-8 -*-
"""不用 Abaqus，验证二维矩形板的中文命令和安全计划。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from abaqus_codex.assistant_protocol import validate_action_plan
from abaqus_codex.desktop_assistant.controller import classify_command
from abaqus_codex.desktop_assistant.rectangle_flow import (
    RectangleCommandError,
    build_rectangle_plan,
    format_rectangle_plan,
    parse_rectangle_command,
)


COMMAND = (
    "创建一个长 100 mm、宽 20 mm 的二维矩形板，"
    "模型名 Model-1，零件名 Plate"
)


class RectangleCreationFlowTests(unittest.TestCase):
    """确认首个几何动作严格、可审阅且默认不执行。"""

    def test_chinese_command_is_parsed_without_ai(self):
        """固定中文句式应准确得到四个几何参数。"""

        request = parse_rectangle_command(COMMAND)
        self.assertEqual(request.model_name, "Model-1")
        self.assertEqual(request.part_name, "Plate")
        self.assertEqual(request.length, 100.0)
        self.assertEqual(request.width, 20.0)

    def test_incomplete_rectangle_command_is_rejected(self):
        """缺少宽度时不得靠猜测补全。"""

        with self.assertRaises(RectangleCommandError):
            parse_rectangle_command(
                "创建一个长 100 mm 的二维矩形板，模型名 Model-1，零件名 Plate"
            )

    def test_plan_is_signed_and_marks_geometry_only(self):
        """计划必须通过通用协议，并明确后续步骤尚未完成。"""

        request = parse_rectangle_command(COMMAND)
        created_at = datetime.now(timezone.utc)
        plan = build_rectangle_plan(
            request,
            snapshot_fingerprint="a" * 64,
            model_exists=True,
            part_exists=False,
            now=created_at,
            id_factory=lambda: "rectangletest1234567890abcd",
        )
        checked = validate_action_plan(
            plan, now=created_at
        )
        action = checked["actions"][0]
        self.assertEqual(checked["model_fingerprint"], "sha256:" + "a" * 64)
        self.assertEqual(action["type"], "create_rectangle_part")
        self.assertEqual(action["after"]["dimensionality"], "TWO_D_PLANAR")
        self.assertTrue(checked["requires_backup"])
        display = format_rectangle_plan(plan)
        self.assertIn("1/10 创建几何", display)
        self.assertIn("下一步：定义材料", display)

    def test_existing_part_cannot_be_overwritten(self):
        """摘要发现同名零件时必须在生成计划阶段停止。"""

        with self.assertRaises(RectangleCommandError):
            build_rectangle_plan(
                parse_rectangle_command(COMMAND),
                snapshot_fingerprint="b" * 64,
                model_exists=True,
                part_exists=True,
            )

    def test_controller_routes_rectangle_to_review_plan(self):
        """发送按钮只应生成计划，不直接执行几何动作。"""

        decision = classify_command(COMMAND)
        self.assertEqual(decision.action, "rectangle_plan")
        self.assertIsNotNone(decision.rectangle_request)


if __name__ == "__main__":
    unittest.main()
