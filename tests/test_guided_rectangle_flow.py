# -*- coding: utf-8 -*-
"""离线验证矩形板第 2–10 步向导和安全桥。"""

from __future__ import annotations

import importlib.util
import json
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from abaqus_codex.desktop_assistant.app import DesktopAssistantApp
from abaqus_codex.desktop_assistant.controller import classify_command
from abaqus_codex.desktop_assistant.guided_rectangle_flow import (
    DEFAULT_COMMANDS,
    GuidedCommandError,
    STAGE_ASSEMBLY,
    STAGE_BCS,
    STAGE_INTERACTION,
    STAGE_JOB,
    STAGE_MATERIAL,
    STAGE_MESH,
    STAGE_RESULTS,
    STAGE_SECTION,
    STAGE_STEP,
    build_guided_plan,
    parse_guided_command,
)
from abaqus_codex.desktop_assistant.safe_action_bridge import (
    SafeActionFileBridge,
    SafeActionProtocolError,
)


ROOT = Path(__file__).resolve().parents[1]
KERNEL_PATH = (
    ROOT
    / "abaqus_plugins"
    / "safe_material_action"
    / "safe_material_action_kernel.py"
)
WRITE_STAGES = (
    STAGE_MATERIAL,
    STAGE_SECTION,
    STAGE_ASSEMBLY,
    STAGE_STEP,
    STAGE_BCS,
    STAGE_MESH,
    STAGE_JOB,
    STAGE_RESULTS,
)


def _plan(stage):
    """为测试生成当前有效的真实签名计划。"""

    return build_guided_plan(
        parse_guided_command(DEFAULT_COMMANDS[stage]),
        snapshot_fingerprint="9" * 64,
    )


def _load_kernel():
    """在普通 Python 中加载 Kernel 的纯校验函数。"""

    specification = importlib.util.spec_from_file_location(
        "guided_kernel_test", KERNEL_PATH
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class GuidedRectangleFlowTests(unittest.TestCase):
    """确认所有离线步骤都有确定句式和单动作计划。"""

    def test_all_default_commands_route_to_their_stage(self):
        """界面自动填入的每条命令都必须能被控制器识别。"""

        for stage, command in DEFAULT_COMMANDS.items():
            with self.subTest(stage=stage):
                request = parse_guided_command(command)
                self.assertEqual(request.stage, stage)
                decision = classify_command(command)
                self.assertEqual(decision.action, "guided_stage")
                self.assertEqual(decision.guided_request.stage, stage)

    def test_incomplete_guided_command_is_not_guessed(self):
        """缺少材料参数时必须停止，而不是用教学默认值暗中补齐。"""

        with self.assertRaises(GuidedCommandError):
            parse_guided_command("为 Model-1 创建材料 Steel")

    def test_each_write_stage_has_one_expected_action(self):
        """每一步只允许一个动作，避免把多步修改藏在一次确认中。"""

        expected = {
            STAGE_MATERIAL: "set_material_elastic",
            STAGE_SECTION: "create_section_assignment",
            STAGE_ASSEMBLY: "create_instance",
            STAGE_STEP: "create_static_step",
            STAGE_BCS: "configure_rectangle_tension_bcs",
            STAGE_MESH: "set_mesh_size",
            STAGE_JOB: "create_submit_job",
            STAGE_RESULTS: "read_job_results_report",
        }
        for stage, action_type in expected.items():
            with self.subTest(stage=stage):
                plan = _plan(stage)
                self.assertEqual(len(plan["actions"]), 1)
                self.assertEqual(plan["actions"][0]["type"], action_type)
                self.assertEqual(plan["requires_backup"], stage != STAGE_RESULTS)
                self.assertEqual(
                    plan["requires_job_confirmation"], stage == STAGE_JOB
                )

    def test_interaction_checkpoint_has_no_write_plan(self):
        """单一连续板的第 6 步只能解释为何无需相互作用。"""

        request = parse_guided_command(DEFAULT_COMMANDS[STAGE_INTERACTION])
        with self.assertRaises(GuidedCommandError):
            build_guided_plan(request, snapshot_fingerprint="9" * 64)

    def test_schema_accepts_every_guided_plan(self):
        """发布 Schema 与 Python 可信层必须接受同一批计划。"""

        schema = json.loads(
            files("abaqus_codex.assistant_protocol")
            .joinpath("action_schema_v1.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(
            schema, format_checker=FormatChecker()
        )
        for stage in WRITE_STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(list(validator.iter_errors(_plan(stage))), [])

    def test_abaqus_kernel_independently_accepts_every_guided_plan(self):
        """Abaqus Python 2 层必须按同一字段集合进行二次校验。"""

        kernel = _load_kernel()
        for stage in WRITE_STAGES:
            with self.subTest(stage=stage):
                action, model_name, checked_stage = kernel._validate_guided_plan(
                    _plan(stage)
                )
                self.assertEqual(model_name, "Model-1")
                self.assertEqual(checked_stage, stage)
                self.assertNotIn("script", action)

    def test_kernel_has_no_arbitrary_execution_or_blocking_job_wait(self):
        """向导只能调用固定 API，Job 不得在 GUI 请求中阻塞等待。"""

        source = KERNEL_PATH.read_text(encoding="utf-8")
        self.assertNotIn("exec(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("waitForCompletion", source)
        self.assertIn("def _apply_guided(", source)
        self.assertIn("job.submit(consistencyChecking=ON)", source)
        self.assertIn("openOdb(path=odb_path, readOnly=True)", source)

    def test_material_success_text_only_reads_material_fields(self):
        """材料成功回执不能误读后续截面、网格或 Job 字段。"""

        app = DesktopAssistantApp.__new__(DesktopAssistantApp)
        text = app._format_guided_success({
            "stage": STAGE_MATERIAL,
            "details": {
                "material": "Steel",
                "youngs_modulus": 210000.0,
                "poisson_ratio": 0.3,
            },
            "working_copy_name": "guided_001.cae",
        })
        self.assertIn("材料已创建", text)
        self.assertIn("Steel", text)


class GuidedBridgeReceiptTests(unittest.TestCase):
    """确认桌面端不盲信 Abaqus 回执。"""

    def test_material_receipt_is_accepted_without_paths(self):
        """字段完整且与计划一致的材料创建回执应通过。"""

        plan = _plan(STAGE_MATERIAL)
        action = plan["actions"][0]
        receipt = {
            "plan_id": plan["plan_id"],
            "action_id": action["id"],
            "stage": "material",
            "model": "Model-1",
            "details": {
                "material": "Steel",
                "youngs_modulus": 210000.0,
                "poisson_ratio": 0.3,
                "stress_unit": "MPa",
            },
            "working_copy_name": "guided_001.cae",
            "same_directory": True,
            "original_untouched": True,
        }
        bridge = SafeActionFileBridge()
        with patch.object(
            bridge, "_exchange", return_value={"data": receipt}
        ):
            self.assertEqual(
                bridge.apply_guided_plan(plan)["stage"], "material"
            )

    def test_results_receipt_rejects_report_path(self):
        """各种平台的路径都不能伪装成报告文件名。"""

        plan = _plan(STAGE_RESULTS)
        action = plan["actions"][0]
        base_receipt = {
            "plan_id": plan["plan_id"],
            "action_id": action["id"],
            "stage": "results",
            "model": "Model-1",
            "job": "rectangle_tension_2d",
            "maximum_displacement": 0.1,
            "maximum_mises_stress": 210.0,
            "length_unit": "mm",
            "stress_unit": "MPa",
            "cae_unchanged": True,
        }
        unsafe_names = (
            "C:\\private\\report.md",
            "/private/report.md",
            "../report.md",
            "..\\report.md",
        )
        for unsafe_name in unsafe_names:
            with self.subTest(report_name=unsafe_name):
                receipt = dict(base_receipt, report_name=unsafe_name)
                bridge = SafeActionFileBridge()
                with patch.object(
                    bridge, "_exchange", return_value={"data": receipt}
                ), self.assertRaises(SafeActionProtocolError):
                    bridge.apply_guided_plan(plan)

    def test_results_receipt_accepts_safe_report_name(self):
        """安全回执可以返回固定格式的 Markdown 报告文件名。"""

        plan = _plan(STAGE_RESULTS)
        action = plan["actions"][0]
        receipt = {
            "plan_id": plan["plan_id"],
            "action_id": action["id"],
            "stage": "results",
            "model": "Model-1",
            "job": "rectangle_tension_2d",
            "maximum_displacement": 0.1,
            "maximum_mises_stress": 210.0,
            "length_unit": "mm",
            "stress_unit": "MPa",
            "report_name": "rectangle_tension_2d_report_zh_001.md",
            "cae_unchanged": True,
        }
        bridge = SafeActionFileBridge()
        with patch.object(
            bridge, "_exchange", return_value={"data": receipt}
        ):
            self.assertEqual(
                bridge.apply_guided_plan(plan)["report_name"],
                "rectangle_tension_2d_report_zh_001.md",
            )


if __name__ == "__main__":
    unittest.main()
