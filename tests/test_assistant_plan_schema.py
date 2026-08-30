# -*- coding: utf-8 -*-
"""测试中文建模助手的白名单 Action Plan，不启动 Abaqus。"""

import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from jsonschema import Draft202012Validator, FormatChecker

from abaqus_codex.assistant_protocol import (
    ActionPlanValidationError,
    load_action_plan_json,
    seal_action_plan,
    validate_action_plan,
)


NOW = datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc)


def fingerprint(text):
    """为测试对象生成格式正确的 SHA-256 指纹。"""

    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def material_action(action_id="material-1"):
    """返回修改中文材料弹性参数的有效动作。"""

    return {
        "id": action_id,
        "type": "set_material_elastic",
        "target": {"model": "Model-1", "material": "钢材"},
        "before": {
            "youngs_modulus": 200000.0,
            "poisson_ratio": 0.3,
            "stress_unit": "MPa",
        },
        "after": {
            "youngs_modulus": 210000.0,
            "poisson_ratio": 0.3,
            "stress_unit": "MPa",
        },
        "risk": "low",
        "warnings": [],
    }


def summary_action():
    """返回独立的只读模型摘要动作。"""

    return {
        "id": "summary-1",
        "type": "get_model_summary",
        "target": {"model": "Model-1"},
        "before": None,
        "after": None,
        "risk": "read_only",
        "warnings": [],
    }


def save_action():
    """返回不包含任何路径的安全另存为动作。"""

    return {
        "id": "save-1",
        "type": "save_cae_as",
        "target": {"model": "Model-1"},
        "before": None,
        "after": {"destination_mode": "prompt_user", "overwrite": False},
        "risk": "medium",
        "warnings": ["应用前将由用户选择新的 CAE 工作副本。"],
    }


def job_action():
    """返回只提交现有 Job、且不等待和不重试的动作。"""

    return {
        "id": "job-1",
        "type": "submit_job",
        "target": {"model": "Model-1", "job": "Job-1"},
        "before": {"status": "CREATED"},
        "after": {
            "submit": True,
            "consistency_checking": True,
            "wait": False,
            "auto_retry": False,
        },
        "risk": "high",
        "warnings": ["提交 Job 会占用 Abaqus 许可证。"],
    }


def part_action():
    """返回修改项目已登记长度参数的动作。"""

    return {
        "id": "part-1",
        "type": "set_part_parameter",
        "target": {
            "model": "Model-1",
            "part": "Plate",
            "parameter": "length",
        },
        "before": {"value": 200.0, "length_unit": "mm"},
        "after": {"value": 250.0, "length_unit": "mm"},
        "risk": "medium",
        "warnings": [],
    }


def mesh_action():
    """返回只作用于尚未生成网格零件的全局种子动作。"""

    return {
        "id": "mesh-1",
        "type": "set_mesh_size",
        "target": {"model": "Model-1", "part": "Plate"},
        "before": {"seed_size": 10.0, "has_mesh": False},
        "after": {"size": 5.0, "length_unit": "mm"},
        "risk": "medium",
        "warnings": [],
    }


def static_step_action():
    """返回使用执行器固定增量策略的静力分析步动作。"""

    return {
        "id": "step-1",
        "type": "create_static_step",
        "target": {"model": "Model-1", "step": "LoadStep"},
        "before": None,
        "after": {
            "previous_step": "Initial",
            "time_period": 1.0,
            "nlgeom": False,
        },
        "risk": "medium",
        "warnings": [],
    }


def displacement_bc_action():
    """返回引用装配 Set 的二维位移边界条件动作。"""

    return {
        "id": "bc-1",
        "type": "create_displacement_bc",
        "target": {
            "model": "Model-1",
            "bc": "PullBC",
            "region_type": "set",
            "region_owner": "assembly",
            "region_name": "RIGHT_EDGE",
        },
        "before": None,
        "after": {"step": "LoadStep", "u1": 0.2, "u2": None},
        "risk": "medium",
        "warnings": [],
    }


def plan_with(actions):
    """把动作装入由可信程序补充元数据并加摘要的计划。"""

    action_types = [action["type"] for action in actions]
    plan = {
        "schema_version": "abaqus.action.v1",
        "abaqus_release": "2021",
        "plan_id": "plan-20210829-001",
        "created_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
        "model_name": "Model-1",
        "model_fingerprint": fingerprint("Model-1:mm-N-s-MPa:state-1"),
        "unit_system": "mm-N-s-MPa",
        "actions": actions,
        "warnings": [],
        "requires_backup": any(value != "get_model_summary" for value in action_types),
        "requires_job_confirmation": "submit_job" in action_types,
    }
    return seal_action_plan(plan)


class ActionSchemaFileTests(unittest.TestCase):
    """确认发布包中的 JSON Schema 与 2021 边界一致。"""

    def setUp(self):
        """从将要随安装包发布的位置读取并编译 Schema。"""

        schema_path = files("abaqus_codex.assistant_protocol").joinpath(
            "action_schema_v1.json"
        )
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(self.schema)
        self.schema_validator = Draft202012Validator(
            self.schema, format_checker=FormatChecker()
        )

    def assert_schema_and_runtime_reject(self, plan):
        """断言 Schema 与 Python 可信层都拒绝同一份危险计划。"""

        self.assertTrue(list(self.schema_validator.iter_errors(plan)))
        with self.assertRaises(ActionPlanValidationError):
            validate_action_plan(plan, now=NOW)

    def test_schema_is_packaged_and_locks_release_to_2021(self):
        """Schema 必须可读取，并且不能暗中接受 2022。"""

        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(
            self.schema["properties"]["abaqus_release"]["const"], "2021"
        )
        self.assertEqual(
            len(self.schema["properties"]["actions"]["items"]["oneOf"]), 14
        )

    def test_schema_and_runtime_accept_the_same_valid_plan(self):
        """标准 Schema 和可信层都应接受有效的中文材料计划。"""

        plan = plan_with([material_action()])
        self.assertEqual(list(self.schema_validator.iter_errors(plan)), [])
        validate_action_plan(plan, now=NOW)

    def test_schema_and_runtime_share_numeric_and_text_limits(self):
        """模型输出层不能放过随后一定会被可信层拒绝的明显参数。"""

        long_step = static_step_action()
        long_step["after"]["time_period"] = 2.0e12
        self.assert_schema_and_runtime_reject(plan_with([long_step]))

        large_bc = displacement_bc_action()
        large_bc["after"]["u1"] = 2.0e9
        self.assert_schema_and_runtime_reject(plan_with([large_bc]))

        empty_bc = displacement_bc_action()
        empty_bc["after"]["u1"] = None
        self.assert_schema_and_runtime_reject(plan_with([empty_bc]))

        padded = material_action()
        padded["target"]["material"] = " 钢材 "
        self.assert_schema_and_runtime_reject(plan_with([padded]))


class ActionPlanValidationTests(unittest.TestCase):
    """确认可信层只能接收严格白名单计划。"""

    def test_valid_chinese_material_plan(self):
        """中文对象名和 2.1e5 MPa 应稳定通过。"""

        plan = plan_with([material_action()])
        result = validate_action_plan(plan, now=NOW)
        self.assertEqual(result["abaqus_release"], "2021")
        self.assertEqual(result["actions"][0]["target"]["material"], "钢材")
        self.assertEqual(result["actions"][0]["after"]["youngs_modulus"], 210000.0)

    def test_valid_plan_can_round_trip_through_utf8_json(self):
        """无需 Abaqus 也能模拟网关收到的 UTF-8 JSON。"""

        plan = plan_with([material_action()])
        payload = json.dumps(plan, ensure_ascii=False).encode("utf-8")
        result = load_action_plan_json(payload, now=NOW)
        self.assertEqual(result["plan_digest"], plan["plan_digest"])

    def test_release_other_than_2021_is_rejected(self):
        """2022 留待以后适配，本版必须明确停止。"""

        plan = plan_with([material_action()])
        plan["abaqus_release"] = "2022"
        with self.assertRaisesRegex(ActionPlanValidationError, "只支持 Abaqus 2021"):
            validate_action_plan(plan, now=NOW)

    def test_extra_root_and_nested_fields_are_rejected(self):
        """未知字段不能成为脚本或绕过参数。"""

        root_plan = plan_with([material_action()])
        root_plan["python_script"] = "print('unsafe')"
        with self.assertRaisesRegex(ActionPlanValidationError, "不允许的字段"):
            validate_action_plan(root_plan, now=NOW)

        nested_plan = plan_with([material_action()])
        nested_plan["actions"][0]["after"]["script"] = "dangerous.py"
        with self.assertRaisesRegex(ActionPlanValidationError, "不允许的字段"):
            validate_action_plan(nested_plan, now=NOW)

    def test_non_finite_and_boolean_numbers_are_rejected(self):
        """NaN、Infinity 和布尔值都不能冒充 Abaqus 数值。"""

        for value in (float("nan"), float("inf"), float("-inf"), True):
            plan = plan_with([material_action()])
            plan["actions"][0]["after"]["youngs_modulus"] = value
            with self.subTest(value=value), self.assertRaises(ActionPlanValidationError):
                validate_action_plan(plan, now=NOW)

    def test_json_parser_rejects_constants_overflow_and_duplicate_keys(self):
        """解析阶段必须拒绝非标准常量、溢出和重复字段。"""

        with self.assertRaisesRegex(ActionPlanValidationError, "非有限常量"):
            load_action_plan_json('{"value": NaN, "value2": Infinity}', now=NOW)

        plan = plan_with([material_action()])
        overflow = json.dumps(plan).replace("210000.0", "1e309", 1)
        with self.assertRaisesRegex(ActionPlanValidationError, "有限数值"):
            load_action_plan_json(overflow, now=NOW)

        text = json.dumps(plan)
        duplicate = text.replace(
            '"schema_version": "abaqus.action.v1"',
            '"schema_version": "abaqus.action.v1", "schema_version": "abaqus.action.v1"',
            1,
        )
        with self.assertRaisesRegex(ActionPlanValidationError, "不能重复"):
            load_action_plan_json(duplicate, now=NOW)

    def test_json_parser_rejects_excessive_depth_cleanly(self):
        """解析器自身遇到深度炸弹时也要返回统一的校验错误。"""

        payload = "[" * 1100 + "0" + "]" * 1100
        with self.assertRaisesRegex(ActionPlanValidationError, "有效 JSON|嵌套"):
            load_action_plan_json(payload, now=NOW)

    def test_plan_digest_detects_any_change(self):
        """用户预览后的计划被改动时必须失效。"""

        plan = plan_with([material_action()])
        plan["actions"][0]["after"]["youngs_modulus"] = 220000.0
        with self.assertRaisesRegex(ActionPlanValidationError, "plan_digest"):
            validate_action_plan(plan, now=NOW)

    def test_expired_plan_is_rejected(self):
        """旧模型状态生成的计划不能长期保留后再应用。"""

        plan = plan_with([material_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "已经过期"):
            validate_action_plan(plan, now=NOW + timedelta(minutes=11))

    def test_far_future_plan_is_rejected(self):
        """未来时间不能被用来延长计划的实际有效期。"""

        plan = plan_with([material_action()])
        plan["created_at"] = (NOW + timedelta(minutes=10)).isoformat()
        plan["expires_at"] = (NOW + timedelta(minutes=20)).isoformat()
        plan = seal_action_plan(plan)
        with self.assertRaisesRegex(ActionPlanValidationError, "晚于当前时间"):
            validate_action_plan(plan, now=NOW)

    def test_summary_is_a_standalone_read_only_action(self):
        """只读模型信息不需要备份，也不能夹带写操作。"""

        plan = plan_with([summary_action()])
        result = validate_action_plan(plan, now=NOW)
        self.assertFalse(result["requires_backup"])

        mixed = plan_with([summary_action(), material_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "独立只读动作"):
            validate_action_plan(mixed, now=NOW)

    def test_save_action_cannot_contain_path_or_overwrite(self):
        """保存位置必须到应用阶段由用户选择。"""

        plan = plan_with([save_action()])
        validate_action_plan(plan, now=NOW)

        unsafe = plan_with([save_action()])
        unsafe["actions"][0]["after"] = {
            "destination_mode": "prompt_user",
            "overwrite": False,
            "path": "C:/private/original.cae",
        }
        with self.assertRaisesRegex(ActionPlanValidationError, "不允许的字段"):
            validate_action_plan(unsafe, now=NOW)

    def test_job_requires_confirmation_is_last_and_never_auto_retries(self):
        """Job 是不可回滚动作，必须保持最高风险和终端位置。"""

        plan = plan_with([material_action(), save_action(), job_action()])
        result = validate_action_plan(plan, now=NOW)
        self.assertTrue(result["requires_job_confirmation"])

        wrong_order = plan_with([job_action(), save_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "最后一个动作"):
            validate_action_plan(wrong_order, now=NOW)

        retry = plan_with([job_action()])
        retry["actions"][0]["after"]["auto_retry"] = True
        with self.assertRaisesRegex(ActionPlanValidationError, "自动重试"):
            validate_action_plan(retry, now=NOW)

    def test_geometry_step_and_bc_order_is_enforced(self):
        """尺寸在网格前，分析步在引用它的边界条件前。"""

        valid = plan_with(
            [part_action(), mesh_action(), static_step_action(), displacement_bc_action()]
        )
        validate_action_plan(valid, now=NOW)

        mesh_first = plan_with([mesh_action(), part_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "尺寸修改必须排在"):
            validate_action_plan(mesh_first, now=NOW)

        bc_first = plan_with([displacement_bc_action(), static_step_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "静力步的动作必须排在"):
            validate_action_plan(bc_first, now=NOW)

        later_step = static_step_action()
        later_step["id"] = "step-2"
        later_step["target"]["step"] = "Step-2"
        later_step["after"]["previous_step"] = "LoadStep"
        reverse_steps = plan_with([later_step, static_step_action()])
        with self.assertRaisesRegex(ActionPlanValidationError, "后续静力步"):
            validate_action_plan(reverse_steps, now=NOW)

    def test_existing_mesh_and_unsupported_3d_dof_are_rejected(self):
        """第一版不隐式删除网格，也不假装支持三维自由度。"""

        existing_mesh = plan_with([mesh_action()])
        existing_mesh["actions"][0]["before"]["has_mesh"] = True
        with self.assertRaisesRegex(ActionPlanValidationError, "已有网格"):
            validate_action_plan(existing_mesh, now=NOW)

        three_dimensional = plan_with([displacement_bc_action()])
        three_dimensional["actions"][0]["after"]["u3"] = 0.0
        with self.assertRaisesRegex(ActionPlanValidationError, "不允许的字段"):
            validate_action_plan(three_dimensional, now=NOW)

    def test_model_name_must_match_and_path_characters_are_rejected(self):
        """动作不能悄悄切换模型或把对象名当路径。"""

        wrong_model = plan_with([material_action()])
        wrong_model["actions"][0]["target"]["model"] = "Model-2"
        with self.assertRaisesRegex(ActionPlanValidationError, "model_name 一致"):
            validate_action_plan(wrong_model, now=NOW)

        path_name = plan_with([material_action()])
        path_name["actions"][0]["target"]["material"] = "../Steel"
        with self.assertRaisesRegex(ActionPlanValidationError, "路径字符"):
            validate_action_plan(path_name, now=NOW)

        padded_name = plan_with([material_action()])
        padded_name["actions"][0]["target"]["material"] = " 钢材 "
        with self.assertRaisesRegex(ActionPlanValidationError, "空白字符"):
            validate_action_plan(padded_name, now=NOW)

    def test_extremely_large_integer_is_rejected_cleanly(self):
        """超大整数不能让校验器抛出未处理的 OverflowError。"""

        plan = plan_with([material_action()])
        plan["actions"][0]["after"]["youngs_modulus"] = 10**1000
        with self.assertRaisesRegex(ActionPlanValidationError, "有限数值"):
            validate_action_plan(plan, now=NOW)

    def test_direct_plan_size_and_padded_warning_are_rejected(self):
        """绕过 JSON 入口也不能提交超大对象或隐藏空白提示。"""

        oversized = plan_with([material_action()])
        oversized["unexpected_padding"] = "x" * (300 * 1024)
        with self.assertRaisesRegex(ActionPlanValidationError, "256 KiB"):
            validate_action_plan(oversized, now=NOW)

        padded_warning = plan_with([material_action()])
        padded_warning["actions"][0]["warnings"] = [" 风险提示 "]
        with self.assertRaisesRegex(ActionPlanValidationError, "空白字符"):
            validate_action_plan(padded_warning, now=NOW)

    def test_validator_returns_independent_copy(self):
        """后续界面修改返回值时不能改变原始计划。"""

        plan = plan_with([material_action()])
        result = validate_action_plan(plan, now=NOW)
        result["actions"][0]["after"]["youngs_modulus"] = 1.0
        self.assertEqual(plan["actions"][0]["after"]["youngs_modulus"], 210000.0)


if __name__ == "__main__":
    unittest.main()
