# -*- coding: utf-8 -*-
"""不启动 Abaqus，验证首个中文材料修改计划。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from abaqus_codex.desktop_assistant.material_flow import (
    MaterialCommandError,
    MaterialElasticState,
    build_material_plan,
    compute_material_fingerprint,
    format_material_plan,
    normalize_material_state,
    parse_material_command,
)
from abaqus_codex.desktop_assistant.mock_bridge import MockReadOnlyBridge


NOW = datetime(2026, 8, 30, 8, 0, 0, tzinfo=timezone.utc)
FINGERPRINT = "sha256:" + "a" * 64


def current_state() -> MaterialElasticState:
    """返回一个确定性的 Abaqus 实时材料状态。"""

    return MaterialElasticState(
        model_name="Model-1",
        material_name="Steel",
        youngs_modulus=200000.0,
        poisson_ratio=0.3,
        stress_unit="MPa",
        fingerprint=FINGERPRINT,
    )


class MaterialCommandParsingTests(unittest.TestCase):
    """确认本地解析器只接受第一版明确句式。"""

    def test_chinese_command_extracts_model_material_and_modulus(self):
        """示例命令应稳定提取目标和科学计数法。"""

        request = parse_material_command(
            "把 Model-1 中 Steel 的弹性模量改为 2.1e5 MPa"
        )
        self.assertIsNotNone(request)
        self.assertEqual(request.model_name, "Model-1")
        self.assertEqual(request.material_name, "Steel")
        self.assertEqual(request.youngs_modulus, 210000.0)
        self.assertIsNone(request.poisson_ratio)

    def test_optional_poisson_ratio_is_parsed(self):
        """用户明确给出泊松比时不得忽略。"""

        request = parse_material_command(
            "将 Model-1 里的 钢材 弹性模量设置为 210000 兆帕，泊松比 0.29"
        )
        self.assertEqual(request.material_name, "钢材")
        self.assertEqual(request.poisson_ratio, 0.29)

    def test_other_command_is_not_misclassified_as_material_edit(self):
        """查看模型等其他命令应交回现有分类器。"""

        self.assertIsNone(parse_material_command("查看当前模型信息"))

    def test_incomplete_or_unsafe_material_command_is_rejected(self):
        """缺单位、路径名和越界数值不能进入计划。"""

        values = (
            "把 Model-1 中 Steel 的弹性模量改为 210000",
            r"把 Model-1 中 ../Steel 的弹性模量改为 210000 MPa",
            "把 Model-1 中 Steel 的弹性模量改为 0 MPa",
            "把 Model-1 中 Steel 的弹性模量改为 210000 MPa，泊松比 0.5",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(MaterialCommandError):
                parse_material_command(value)


class MaterialPlanTests(unittest.TestCase):
    """确认计划只预览，并准确保存旧值和新值。"""

    def test_plan_preserves_current_poisson_ratio_when_omitted(self):
        """用户没说泊松比时必须沿用实时值，不能猜默认值。"""

        request = parse_material_command(
            "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
        )
        plan = build_material_plan(
            request,
            current_state(),
            now=NOW,
            id_factory=lambda: "1234567890abcdef1234567890abcdef",
        )
        action = plan["actions"][0]
        self.assertEqual(action["before"]["youngs_modulus"], 200000.0)
        self.assertEqual(action["after"]["youngs_modulus"], 210000.0)
        self.assertEqual(action["after"]["poisson_ratio"], 0.3)
        self.assertTrue(plan["requires_backup"])
        self.assertEqual(plan["model_fingerprint"], FINGERPRINT)

    def test_material_fingerprint_has_a_fixed_cross_process_vector(self):
        """桌面端与 Python 2.7 插件必须得到完全相同的指纹。"""

        fingerprint = compute_material_fingerprint(
            "Model-1", "Steel", 200000.0, 0.3
        )
        self.assertEqual(
            fingerprint,
            "sha256:98e2206f558af609879b700e487e8581f0fc980bd94cf21734c7a95e623262c8",
        )

    def test_plan_preview_shows_objects_old_new_and_protection(self):
        """预览必须让初学者看见修改对象、旧值、新值和保护措施。"""

        request = parse_material_command(
            "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
        )
        plan = build_material_plan(request, current_state())
        text = format_material_plan(plan)
        for expected in (
            "尚未执行",
            "Model-1",
            "Steel",
            "200000 MPa",
            "210000 MPa",
            "受保护工作副本",
            "应用修改",
        ):
            self.assertIn(expected, text)

    def test_state_payload_is_strict_and_target_must_match(self):
        """实时旧值不能带额外字段，目标也不能悄悄切换。"""

        payload = {
            "model": "Model-1",
            "material": "Steel",
            "youngs_modulus": 200000.0,
            "poisson_ratio": 0.3,
            "stress_unit": "MPa",
            "fingerprint": FINGERPRINT,
        }
        state = normalize_material_state(payload)
        self.assertEqual(state.youngs_modulus, 200000.0)

        payload["path"] = r"C:\private\model.cae"
        with self.assertRaises(MaterialCommandError):
            normalize_material_state(payload)

        request = parse_material_command(
            "把 Model-2 中 Steel 的弹性模量改为 210000 MPa"
        )
        with self.assertRaisesRegex(MaterialCommandError, "模型"):
            build_material_plan(request, current_state(), now=NOW)

    def test_mock_bridge_completes_once_and_rejects_stale_replay(self):
        """无 Abaqus 演示也要复现一次性计划和旧值复核。"""

        bridge = MockReadOnlyBridge()
        request = parse_material_command(
            "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
        )
        plan = build_material_plan(
            request,
            bridge.inspect_material_elastic("Model-1", "Steel"),
        )
        receipt = bridge.apply_material_plan(plan)
        self.assertEqual(receipt["before"]["youngs_modulus"], 200000.0)
        self.assertEqual(receipt["after"]["youngs_modulus"], 210000.0)
        self.assertEqual(
            bridge.inspect_material_elastic(
                "Model-1", "Steel"
            ).youngs_modulus,
            210000.0,
        )
        with self.assertRaisesRegex(MaterialCommandError, "旧值"):
            bridge.apply_material_plan(plan)


if __name__ == "__main__":
    unittest.main()
