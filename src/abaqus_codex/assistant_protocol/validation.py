# -*- coding: utf-8 -*-
"""严格校验中文建模助手的 Action Plan。

语言模型产生的内容始终是不可信提案。本模块只接受固定字段和固定动作，
并拒绝任意 Python、任意文件路径、非有限数值和未知 Abaqus 版本。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Dict, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = "abaqus.action.v1"
SUPPORTED_ABAQUS_RELEASES = ("2021",)
SUPPORTED_UNIT_SYSTEM = "mm-N-s-MPa"

ACTION_GET_MODEL_SUMMARY = "get_model_summary"
ACTION_SET_MATERIAL_ELASTIC = "set_material_elastic"
ACTION_CREATE_RECTANGLE_PART = "create_rectangle_part"
ACTION_CREATE_SECTION_ASSIGNMENT = "create_section_assignment"
ACTION_CREATE_INSTANCE = "create_instance"
ACTION_SET_PART_PARAMETER = "set_part_parameter"
ACTION_SET_MESH_SIZE = "set_mesh_size"
ACTION_CREATE_STATIC_STEP = "create_static_step"
ACTION_CREATE_DISPLACEMENT_BC = "create_displacement_bc"
ACTION_CONFIGURE_RECTANGLE_TENSION_BCS = "configure_rectangle_tension_bcs"
ACTION_SAVE_CAE_AS = "save_cae_as"
ACTION_SUBMIT_JOB = "submit_job"
ACTION_CREATE_SUBMIT_JOB = "create_submit_job"
ACTION_READ_JOB_RESULTS_REPORT = "read_job_results_report"

ACTION_TYPES = (
    ACTION_GET_MODEL_SUMMARY,
    ACTION_SET_MATERIAL_ELASTIC,
    ACTION_CREATE_RECTANGLE_PART,
    ACTION_CREATE_SECTION_ASSIGNMENT,
    ACTION_CREATE_INSTANCE,
    ACTION_SET_PART_PARAMETER,
    ACTION_SET_MESH_SIZE,
    ACTION_CREATE_STATIC_STEP,
    ACTION_CREATE_DISPLACEMENT_BC,
    ACTION_CONFIGURE_RECTANGLE_TENSION_BCS,
    ACTION_SAVE_CAE_AS,
    ACTION_SUBMIT_JOB,
    ACTION_CREATE_SUBMIT_JOB,
    ACTION_READ_JOB_RESULTS_REPORT,
)

# 风险等级由可信代码固定，AI 不能把高风险动作自行降级。
ACTION_RISKS = {
    ACTION_GET_MODEL_SUMMARY: "read_only",
    ACTION_SET_MATERIAL_ELASTIC: "low",
    ACTION_CREATE_RECTANGLE_PART: "medium",
    ACTION_CREATE_SECTION_ASSIGNMENT: "medium",
    ACTION_CREATE_INSTANCE: "medium",
    ACTION_SET_PART_PARAMETER: "medium",
    ACTION_SET_MESH_SIZE: "medium",
    ACTION_CREATE_STATIC_STEP: "medium",
    ACTION_CREATE_DISPLACEMENT_BC: "medium",
    ACTION_CONFIGURE_RECTANGLE_TENSION_BCS: "medium",
    ACTION_SAVE_CAE_AS: "medium",
    ACTION_SUBMIT_JOB: "high",
    ACTION_CREATE_SUBMIT_JOB: "high",
    ACTION_READ_JOB_RESULTS_REPORT: "medium",
}

ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "abaqus_release",
        "plan_id",
        "created_at",
        "expires_at",
        "model_name",
        "model_fingerprint",
        "unit_system",
        "actions",
        "warnings",
        "requires_backup",
        "requires_job_confirmation",
        "plan_digest",
    }
)
ACTION_FIELDS = frozenset(
    {"id", "type", "target", "before", "after", "risk", "warnings"}
)

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
UNSAFE_NAME_CHARACTER_PATTERN = re.compile(r"[\\/:*?\"<>|]")

MAX_OBJECT_NAME_LENGTH = 80
MAX_WARNING_LENGTH = 500
MAX_WARNINGS = 20
MAX_PLAN_LIFETIME_SECONDS = 30 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60
MAX_PLAN_BYTES = 256 * 1024
MAX_JSON_DEPTH = 24
MAX_LENGTH_MM = 1.0e9
MAX_STRESS_MPA = 1.0e12


class ActionPlanValidationError(ValueError):
    """表示计划不符合白名单协议，不能交给 Abaqus。"""


def _strict_mapping(
    value: object,
    required: Sequence[str],
    optional: Sequence[str],
    label: str,
) -> Mapping[str, object]:
    """读取对象并拒绝缺失字段和额外字段。"""

    if not isinstance(value, Mapping):
        raise ActionPlanValidationError("{0}必须是 JSON 对象。".format(label))
    if not all(isinstance(key, str) for key in value):
        raise ActionPlanValidationError("{0}的字段名必须是文本。".format(label))
    allowed = set(required) | set(optional)
    unknown = sorted(set(value) - allowed)
    missing = sorted(set(required) - set(value))
    if unknown:
        raise ActionPlanValidationError(
            "{0}包含不允许的字段：{1}。".format(label, "、".join(unknown))
        )
    if missing:
        raise ActionPlanValidationError(
            "{0}缺少字段：{1}。".format(label, "、".join(missing))
        )
    return value


def _strict_exact_mapping(
    value: object, fields: Sequence[str], label: str
) -> Mapping[str, object]:
    """读取字段集合完全固定的对象。"""

    return _strict_mapping(value, fields, (), label)


def _identifier(value: object, label: str) -> str:
    """读取协议内部 ID，避免控制字符和超长内容。"""

    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ActionPlanValidationError(
            "{0}必须由字母、数字、下划线或短横线组成，且不超过 64 个字符。".format(
                label
            )
        )
    return value


def _object_name(value: object, label: str) -> str:
    """读取 Abaqus 对象名；允许中文，但禁止路径和控制字符。"""

    if not isinstance(value, str):
        raise ActionPlanValidationError("{0}必须是文本。".format(label))
    name = value.strip()
    if name != value:
        raise ActionPlanValidationError(
            "{0}不能以空白字符开头或结尾。".format(label)
        )
    if not name or len(name) > MAX_OBJECT_NAME_LENGTH:
        raise ActionPlanValidationError(
            "{0}不能为空，且不能超过 {1} 个字符。".format(
                label, MAX_OBJECT_NAME_LENGTH
            )
        )
    if CONTROL_CHARACTER_PATTERN.search(name) or UNSAFE_NAME_CHARACTER_PATTERN.search(
        name
    ):
        raise ActionPlanValidationError(
            "{0}不能包含控制字符或路径字符。".format(label)
        )
    return name


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    exclusive_minimum: bool = False,
    exclusive_maximum: bool = False,
) -> float:
    """读取有限数值，并按可信代码中的上下限检查。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionPlanValidationError("{0}必须是数值。".format(label))
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ActionPlanValidationError("{0}必须是有限数值。".format(label)) from error
    if not math.isfinite(number):
        raise ActionPlanValidationError("{0}必须是有限数值。".format(label))
    if minimum is not None:
        too_small = number <= minimum if exclusive_minimum else number < minimum
        if too_small:
            symbol = "大于" if exclusive_minimum else "大于等于"
            raise ActionPlanValidationError(
                "{0}必须{1} {2}。".format(label, symbol, minimum)
            )
    if maximum is not None:
        too_large = number >= maximum if exclusive_maximum else number > maximum
        if too_large:
            symbol = "小于" if exclusive_maximum else "小于等于"
            raise ActionPlanValidationError(
                "{0}必须{1} {2}。".format(label, symbol, maximum)
            )
    return number


def _boolean(value: object, label: str) -> bool:
    """读取真正的 JSON 布尔值。"""

    if not isinstance(value, bool):
        raise ActionPlanValidationError("{0}必须是布尔值。".format(label))
    return value


def _warnings(value: object, label: str) -> Tuple[str, ...]:
    """校验适合界面展示的简短风险提示。"""

    if not isinstance(value, list):
        raise ActionPlanValidationError("{0}必须是字符串数组。".format(label))
    if len(value) > MAX_WARNINGS:
        raise ActionPlanValidationError(
            "{0}最多允许 {1} 条。".format(label, MAX_WARNINGS)
        )
    normalized = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ActionPlanValidationError(
                "{0}[{1}]必须是非空文本。".format(label, index)
            )
        text = item.strip()
        if text != item:
            raise ActionPlanValidationError(
                "{0}[{1}]不能以空白字符开头或结尾。".format(label, index)
            )
        if len(item) > MAX_WARNING_LENGTH or CONTROL_CHARACTER_PATTERN.search(item):
            raise ActionPlanValidationError(
                "{0}[{1}]过长或包含控制字符。".format(label, index)
            )
        normalized.append(item)
    return tuple(normalized)


def _utc_datetime(value: object, label: str) -> datetime:
    """读取带时区的 ISO 8601 时间。"""

    if not isinstance(value, str) or not value.strip():
        raise ActionPlanValidationError("{0}必须是 ISO 8601 时间。".format(label))
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ActionPlanValidationError(
            "{0}必须是有效的 ISO 8601 时间。".format(label)
        ) from error
    if parsed.tzinfo is None:
        raise ActionPlanValidationError("{0}必须包含时区。".format(label))
    return parsed.astimezone(timezone.utc)


def _fingerprint(value: object, label: str) -> str:
    """读取 SHA-256 指纹。"""

    if not isinstance(value, str) or FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ActionPlanValidationError(
            "{0}必须是 sha256: 加 64 位小写十六进制。".format(label)
        )
    return value


def _nullable_finite(value: object, label: str, maximum: float) -> Optional[float]:
    """读取可省略自由度；null 表示 Abaqus 的 UNSET。"""

    if value is None:
        return None
    return _finite_number(value, label, minimum=-maximum, maximum=maximum)


def _validate_common_action(action: object, index: int) -> Mapping[str, object]:
    """校验所有动作共享的字段。"""

    label = "actions[{0}]".format(index)
    mapping = _strict_exact_mapping(action, ACTION_FIELDS, label)
    _identifier(mapping["id"], label + ".id")
    action_type = mapping["type"]
    if action_type not in ACTION_TYPES:
        raise ActionPlanValidationError(
            "{0}.type 不是允许的动作：{1}。".format(
                label, "、".join(ACTION_TYPES)
            )
        )
    expected_risk = ACTION_RISKS[str(action_type)]
    if mapping["risk"] != expected_risk:
        raise ActionPlanValidationError(
            "{0}.risk 必须是 {1}，不能由计划自行降级。".format(
                label, expected_risk
            )
        )
    _warnings(mapping["warnings"], label + ".warnings")
    return mapping


def _validate_get_model_summary(action: Mapping[str, object], label: str) -> None:
    """校验只读模型摘要动作。"""

    target = _strict_exact_mapping(action["target"], ("model",), label + ".target")
    _object_name(target["model"], label + ".target.model")
    if action["before"] is not None or action["after"] is not None:
        raise ActionPlanValidationError(
            "{0}的 before 和 after 必须为 null。".format(label)
        )


def _validate_material(action: Mapping[str, object], label: str) -> None:
    """校验创建或修改简单各向同性线弹性材料。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "material"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["material"], label + ".target.material")
    if action["before"] is not None:
        before = _strict_exact_mapping(
            action["before"],
            ("youngs_modulus", "poisson_ratio", "stress_unit"),
            label + ".before",
        )
        _validate_elastic_values(before, label + ".before")
    after = _strict_exact_mapping(
        action["after"],
        ("youngs_modulus", "poisson_ratio", "stress_unit"),
        label + ".after",
    )
    _validate_elastic_values(after, label + ".after")


def _validate_rectangle_part(
    action: Mapping[str, object], label: str
) -> None:
    """校验二维矩形板几何创建动作。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "part"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["part"], label + ".target.part")
    before = _strict_exact_mapping(
        action["before"],
        ("model_exists", "part_exists"),
        label + ".before",
    )
    _boolean(before["model_exists"], label + ".before.model_exists")
    if _boolean(before["part_exists"], label + ".before.part_exists"):
        raise ActionPlanValidationError(
            "{0}检测到同名零件，第一版禁止覆盖。".format(label)
        )
    after = _strict_exact_mapping(
        action["after"],
        (
            "length",
            "width",
            "length_unit",
            "dimensionality",
            "part_type",
            "origin",
        ),
        label + ".after",
    )
    for field in ("length", "width"):
        _finite_number(
            after[field],
            label + ".after." + field,
            minimum=0.0,
            maximum=MAX_LENGTH_MM,
            exclusive_minimum=True,
        )
    if after["length_unit"] != "mm":
        raise ActionPlanValidationError(
            "{0}.after.length_unit 必须是 mm。".format(label)
        )
    if after["dimensionality"] != "TWO_D_PLANAR":
        raise ActionPlanValidationError(
            "{0}.after.dimensionality 必须是 TWO_D_PLANAR。".format(label)
        )
    if after["part_type"] != "DEFORMABLE_BODY":
        raise ActionPlanValidationError(
            "{0}.after.part_type 必须是 DEFORMABLE_BODY。".format(label)
        )
    if after["origin"] != "lower_left_0_0":
        raise ActionPlanValidationError(
            "{0}.after.origin 必须是 lower_left_0_0。".format(label)
        )


def _validate_section_assignment(
    action: Mapping[str, object], label: str
) -> None:
    """校验创建均质实体截面并赋给二维零件的动作。"""

    target = _strict_exact_mapping(
        action["target"],
        ("model", "part", "section", "material"),
        label + ".target",
    )
    for field in ("model", "part", "section", "material"):
        _object_name(target[field], label + ".target." + field)
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        ("thickness", "length_unit", "section_type", "region"),
        label + ".after",
    )
    _finite_number(
        after["thickness"],
        label + ".after.thickness",
        minimum=0.0,
        maximum=MAX_LENGTH_MM,
        exclusive_minimum=True,
    )
    if after["length_unit"] != "mm":
        raise ActionPlanValidationError(
            "{0}.after.length_unit 必须是 mm。".format(label)
        )
    if after["section_type"] != "HOMOGENEOUS_SOLID":
        raise ActionPlanValidationError(
            "{0}.after.section_type 必须是 HOMOGENEOUS_SOLID。".format(label)
        )
    if after["region"] != "ALL_FACES":
        raise ActionPlanValidationError(
            "{0}.after.region 必须是 ALL_FACES。".format(label)
        )


def _validate_instance(action: Mapping[str, object], label: str) -> None:
    """校验创建单个依赖实例的装配动作。"""

    target = _strict_exact_mapping(
        action["target"],
        ("model", "part", "instance"),
        label + ".target",
    )
    for field in ("model", "part", "instance"):
        _object_name(target[field], label + ".target." + field)
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        ("dependent", "coordinate_system"),
        label + ".after",
    )
    if _boolean(after["dependent"], label + ".after.dependent") is not True:
        raise ActionPlanValidationError(
            "{0}.after.dependent 必须为 true。".format(label)
        )
    if after["coordinate_system"] != "CARTESIAN":
        raise ActionPlanValidationError(
            "{0}.after.coordinate_system 必须是 CARTESIAN。".format(label)
        )


def _validate_elastic_values(values: Mapping[str, object], label: str) -> None:
    """校验弹性模量、泊松比和应力单位。"""

    _finite_number(
        values["youngs_modulus"],
        label + ".youngs_modulus",
        minimum=0.0,
        maximum=MAX_STRESS_MPA,
        exclusive_minimum=True,
    )
    _finite_number(
        values["poisson_ratio"],
        label + ".poisson_ratio",
        minimum=-1.0,
        maximum=0.5,
        exclusive_minimum=True,
        exclusive_maximum=True,
    )
    if values["stress_unit"] != "MPa":
        raise ActionPlanValidationError("{0}.stress_unit 必须是 MPa。".format(label))


def _validate_part_parameter(action: Mapping[str, object], label: str) -> None:
    """校验已登记零件参数；不接受任意几何脚本。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "part", "parameter"), label + ".target"
    )
    for field in ("model", "part", "parameter"):
        _object_name(target[field], label + ".target." + field)
    for side in ("before", "after"):
        values = _strict_exact_mapping(
            action[side], ("value", "length_unit"), label + "." + side
        )
        _finite_number(
            values["value"],
            label + "." + side + ".value",
            minimum=0.0,
            maximum=MAX_LENGTH_MM,
            exclusive_minimum=True,
        )
        if values["length_unit"] != "mm":
            raise ActionPlanValidationError(
                "{0}.{1}.length_unit 必须是 mm。".format(label, side)
            )


def _validate_mesh_size(action: Mapping[str, object], label: str) -> None:
    """校验零件级全局网格尺寸。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "part"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["part"], label + ".target.part")
    before = _strict_exact_mapping(
        action["before"], ("seed_size", "has_mesh"), label + ".before"
    )
    if before["seed_size"] is not None:
        _finite_number(
            before["seed_size"],
            label + ".before.seed_size",
            minimum=0.0,
            maximum=MAX_LENGTH_MM,
            exclusive_minimum=True,
        )
    if _boolean(before["has_mesh"], label + ".before.has_mesh"):
        raise ActionPlanValidationError(
            "{0}检测到已有网格，第一版不会隐式删除或重建网格。".format(label)
        )
    _validate_mesh_value(action["after"], label + ".after")


def _validate_mesh_value(value: object, label: str) -> None:
    """校验网格尺寸对象。"""

    values = _strict_exact_mapping(value, ("size", "length_unit"), label)
    _finite_number(
        values["size"],
        label + ".size",
        minimum=0.0,
        maximum=MAX_LENGTH_MM,
        exclusive_minimum=True,
    )
    if values["length_unit"] != "mm":
        raise ActionPlanValidationError("{0}.length_unit 必须是 mm。".format(label))


def _validate_static_step(action: Mapping[str, object], label: str) -> None:
    """校验新建静力分析步。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "step"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["step"], label + ".target.step")
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        ("previous_step", "time_period", "nlgeom"),
        label + ".after",
    )
    _object_name(after["previous_step"], label + ".after.previous_step")
    _finite_number(
        after["time_period"],
        label + ".after.time_period",
        minimum=0.0,
        maximum=1.0e12,
        exclusive_minimum=True,
    )
    _boolean(after["nlgeom"], label + ".after.nlgeom")


def _validate_displacement_bc(action: Mapping[str, object], label: str) -> None:
    """校验引用已有 Set 的位移边界条件。"""

    target = _strict_exact_mapping(
        action["target"],
        ("model", "bc", "region_type", "region_owner", "region_name"),
        label + ".target",
    )
    for field in ("model", "bc", "region_name"):
        _object_name(target[field], label + ".target." + field)
    if target["region_type"] != "set":
        raise ActionPlanValidationError(
            "{0}.target.region_type 第一版只能是 set。".format(label)
        )
    if target["region_owner"] != "assembly":
        raise ActionPlanValidationError(
            "{0}.target.region_owner 第一版只能是 assembly。".format(label)
        )
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        ("step", "u1", "u2"),
        label + ".after",
    )
    _object_name(after["step"], label + ".after.step")
    values = []
    for field in ("u1", "u2"):
        values.append(
            _nullable_finite(
                after[field], label + ".after." + field, MAX_LENGTH_MM
            )
        )
    if all(value is None for value in values):
        raise ActionPlanValidationError(
            "{0}至少要设置一个位移或转动自由度。".format(label)
        )


def _validate_rectangle_tension_bcs(
    action: Mapping[str, object], label: str
) -> None:
    """校验矩形板拉伸所需的三个固定边界条件。"""

    target = _strict_exact_mapping(
        action["target"],
        ("model", "instance", "step"),
        label + ".target",
    )
    for field in ("model", "instance", "step"):
        _object_name(target[field], label + ".target." + field)
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        (
            "right_displacement",
            "length_unit",
            "selection_strategy",
            "bc_names",
        ),
        label + ".after",
    )
    _finite_number(
        after["right_displacement"],
        label + ".after.right_displacement",
        minimum=-MAX_LENGTH_MM,
        maximum=MAX_LENGTH_MM,
    )
    if float(after["right_displacement"]) == 0.0:
        raise ActionPlanValidationError(
            "{0}.after.right_displacement 不能为 0。".format(label)
        )
    if after["length_unit"] != "mm":
        raise ActionPlanValidationError(
            "{0}.after.length_unit 必须是 mm。".format(label)
        )
    if after["selection_strategy"] != "RECTANGLE_BOUNDING_BOX":
        raise ActionPlanValidationError(
            "{0}.after.selection_strategy 必须是 RECTANGLE_BOUNDING_BOX。".format(
                label
            )
        )
    names = _strict_exact_mapping(
        after["bc_names"],
        ("left_horizontal", "anchor_vertical", "right_tension"),
        label + ".after.bc_names",
    )
    for field in ("left_horizontal", "anchor_vertical", "right_tension"):
        _object_name(names[field], label + ".after.bc_names." + field)


def _validate_create_submit_job(
    action: Mapping[str, object], label: str
) -> None:
    """校验创建并异步提交一个 Abaqus/Standard Job。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "job"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["job"], label + ".target.job")
    before = _strict_exact_mapping(
        action["before"], ("job_exists",), label + ".before"
    )
    if _boolean(before["job_exists"], label + ".before.job_exists"):
        raise ActionPlanValidationError(
            "{0}检测到同名 Job，禁止覆盖或重复提交。".format(label)
        )
    after = _strict_exact_mapping(
        action["after"],
        (
            "num_cpus",
            "submit",
            "consistency_checking",
            "wait",
            "auto_retry",
        ),
        label + ".after",
    )
    cpu_count = after["num_cpus"]
    if isinstance(cpu_count, bool) or not isinstance(cpu_count, int):
        raise ActionPlanValidationError(
            "{0}.after.num_cpus 必须是整数。".format(label)
        )
    if cpu_count < 1 or cpu_count > 64:
        raise ActionPlanValidationError(
            "{0}.after.num_cpus 必须在 1 到 64 之间。".format(label)
        )
    if after["submit"] is not True or after["consistency_checking"] is not True:
        raise ActionPlanValidationError(
            "{0}必须启用提交和一致性检查。".format(label)
        )
    if after["wait"] is not False or after["auto_retry"] is not False:
        raise ActionPlanValidationError(
            "{0}禁止阻塞等待或自动重试。".format(label)
        )


def _validate_read_job_results_report(
    action: Mapping[str, object], label: str
) -> None:
    """校验固定 ODB 极值读取和不覆盖中文报告动作。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "job"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["job"], label + ".target.job")
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"],
        ("odb_source", "report_format", "report_language", "overwrite"),
        label + ".after",
    )
    if after["odb_source"] != "CURRENT_CAE_JOB_DIRECTORY":
        raise ActionPlanValidationError(
            "{0}.after.odb_source 必须来自当前 CAE 的 Job 目录。".format(label)
        )
    if after["report_format"] != "markdown":
        raise ActionPlanValidationError(
            "{0}.after.report_format 必须是 markdown。".format(label)
        )
    if after["report_language"] != "zh-CN":
        raise ActionPlanValidationError(
            "{0}.after.report_language 必须是 zh-CN。".format(label)
        )
    if after["overwrite"] is not False:
        raise ActionPlanValidationError("{0}禁止覆盖已有报告。".format(label))


def _validate_save_cae(action: Mapping[str, object], label: str) -> None:
    """校验另存为动作；真实路径只能由用户或可信备份器决定。"""

    target = _strict_exact_mapping(action["target"], ("model",), label + ".target")
    _object_name(target["model"], label + ".target.model")
    if action["before"] is not None:
        raise ActionPlanValidationError("{0}.before 必须为 null。".format(label))
    after = _strict_exact_mapping(
        action["after"], ("destination_mode", "overwrite"), label + ".after"
    )
    if after["destination_mode"] != "prompt_user":
        raise ActionPlanValidationError(
            "{0}.after.destination_mode 必须是 prompt_user。".format(label)
        )
    if after["overwrite"] is not False:
        raise ActionPlanValidationError("{0}禁止覆盖现有 CAE 文件。".format(label))


def _validate_submit_job(action: Mapping[str, object], label: str) -> None:
    """校验已有 Job 的单次提交动作。"""

    target = _strict_exact_mapping(
        action["target"], ("model", "job"), label + ".target"
    )
    _object_name(target["model"], label + ".target.model")
    _object_name(target["job"], label + ".target.job")
    before = _strict_exact_mapping(
        action["before"], ("status",), label + ".before"
    )
    allowed_statuses = ("CREATED", "CHECK_COMPLETED", "NONE")
    if before["status"] not in allowed_statuses:
        raise ActionPlanValidationError(
            "{0}.before.status 必须是未提交状态：{1}。".format(
                label, "、".join(allowed_statuses)
            )
        )
    after = _strict_exact_mapping(
        action["after"],
        ("submit", "consistency_checking", "wait", "auto_retry"),
        label + ".after",
    )
    if after["submit"] is not True or after["consistency_checking"] is not True:
        raise ActionPlanValidationError(
            "{0}必须启用提交和一致性检查。".format(label)
        )
    if after["wait"] is not False or after["auto_retry"] is not False:
        raise ActionPlanValidationError(
            "{0}禁止等待求解完成或自动重试。".format(label)
        )


ACTION_VALIDATORS = {
    ACTION_GET_MODEL_SUMMARY: _validate_get_model_summary,
    ACTION_SET_MATERIAL_ELASTIC: _validate_material,
    ACTION_CREATE_RECTANGLE_PART: _validate_rectangle_part,
    ACTION_CREATE_SECTION_ASSIGNMENT: _validate_section_assignment,
    ACTION_CREATE_INSTANCE: _validate_instance,
    ACTION_SET_PART_PARAMETER: _validate_part_parameter,
    ACTION_SET_MESH_SIZE: _validate_mesh_size,
    ACTION_CREATE_STATIC_STEP: _validate_static_step,
    ACTION_CREATE_DISPLACEMENT_BC: _validate_displacement_bc,
    ACTION_CONFIGURE_RECTANGLE_TENSION_BCS: _validate_rectangle_tension_bcs,
    ACTION_SAVE_CAE_AS: _validate_save_cae,
    ACTION_SUBMIT_JOB: _validate_submit_job,
    ACTION_CREATE_SUBMIT_JOB: _validate_create_submit_job,
    ACTION_READ_JOB_RESULTS_REPORT: _validate_read_job_results_report,
}


def _reject_json_constant(value: str) -> None:
    """拒绝 Python JSON 解析器默认接受的 NaN 和 Infinity。"""

    raise ActionPlanValidationError("JSON 中不允许非有限常量：{0}。".format(value))


def _unique_object_pairs(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
    """拒绝重复 JSON 字段，避免后一个值静默覆盖前一个值。"""

    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ActionPlanValidationError("JSON 字段不能重复：{0}。".format(key))
        result[key] = value
    return result


def _check_json_depth(value: object, depth: int = 1) -> None:
    """限制嵌套深度，避免异常输入消耗过多资源。"""

    if depth > MAX_JSON_DEPTH:
        raise ActionPlanValidationError(
            "JSON 嵌套不能超过 {0} 层。".format(MAX_JSON_DEPTH)
        )
    if isinstance(value, Mapping):
        for child in value.values():
            _check_json_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json_depth(child, depth + 1)


def _check_plan_size(value: object) -> None:
    """让直接传入的 Python 对象也遵守与 JSON 入口相同的大小限制。"""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            # 此处只计算体积；NaN/Infinity 由后面的数值字段校验给出更准确提示。
            allow_nan=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError, RecursionError) as error:
        raise ActionPlanValidationError("计划包含无法安全序列化的值。") from error
    if len(encoded) > MAX_PLAN_BYTES:
        raise ActionPlanValidationError("Action Plan 不能超过 256 KiB。")


def load_action_plan_json(
    payload: object, *, now: Optional[datetime] = None
) -> Dict[str, object]:
    """从有限大小的 UTF-8 JSON 读取并校验 Action Plan。"""

    if isinstance(payload, bytes):
        if len(payload) > MAX_PLAN_BYTES:
            raise ActionPlanValidationError("Action Plan 不能超过 256 KiB。")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ActionPlanValidationError("Action Plan 必须是 UTF-8 JSON。") from error
    elif isinstance(payload, str):
        try:
            encoded = payload.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ActionPlanValidationError("Action Plan 必须是 UTF-8 JSON。") from error
        if len(encoded) > MAX_PLAN_BYTES:
            raise ActionPlanValidationError("Action Plan 不能超过 256 KiB。")
        text = payload
    else:
        raise ActionPlanValidationError("Action Plan 必须是文本或 UTF-8 字节。")

    try:
        data = json.loads(
            text,
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except ActionPlanValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as error:
        raise ActionPlanValidationError("Action Plan 不是有效 JSON。") from error
    _check_json_depth(data)
    if not isinstance(data, Mapping):
        raise ActionPlanValidationError("Action Plan 最外层必须是 JSON 对象。")
    return validate_action_plan(data, now=now)


def compute_plan_digest(plan: Mapping[str, object]) -> str:
    """计算稳定的内容校验摘要；它不是授权或防重放令牌。"""

    if not isinstance(plan, Mapping):
        raise ActionPlanValidationError("计划必须是 JSON 对象。")
    payload = copy.deepcopy(dict(plan))
    payload.pop("plan_digest", None)
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ActionPlanValidationError(
            "计划包含无法稳定序列化的值。"
        ) from error
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def seal_action_plan(plan: Mapping[str, object]) -> Dict[str, object]:
    """为计划添加内容摘要；不会代表用户确认，也不能防止重复应用。"""

    sealed = copy.deepcopy(dict(plan))
    sealed["plan_digest"] = compute_plan_digest(sealed)
    return sealed


def validate_action_plan(
    plan: Mapping[str, object], *, now: Optional[datetime] = None
) -> Dict[str, object]:
    """校验计划并返回独立副本；失败时绝不进入 Abaqus。"""

    _check_json_depth(plan)
    _check_plan_size(plan)
    root = _strict_exact_mapping(plan, ROOT_FIELDS, "计划")
    if root["schema_version"] != SCHEMA_VERSION:
        raise ActionPlanValidationError(
            "只支持协议版本 {0}。".format(SCHEMA_VERSION)
        )
    if root["abaqus_release"] not in SUPPORTED_ABAQUS_RELEASES:
        raise ActionPlanValidationError(
            "第一版只支持 Abaqus 2021，收到版本：{0}。".format(
                root["abaqus_release"]
            )
        )
    _identifier(root["plan_id"], "plan_id")
    created_at = _utc_datetime(root["created_at"], "created_at")
    expires_at = _utc_datetime(root["expires_at"], "expires_at")
    if expires_at <= created_at:
        raise ActionPlanValidationError("expires_at 必须晚于 created_at。")
    if (expires_at - created_at).total_seconds() > MAX_PLAN_LIFETIME_SECONDS:
        raise ActionPlanValidationError("计划有效期不能超过 30 分钟。")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ActionPlanValidationError("校验时间必须包含时区。")
    current_time_utc = current_time.astimezone(timezone.utc)
    if (created_at - current_time_utc).total_seconds() > MAX_CLOCK_SKEW_SECONDS:
        raise ActionPlanValidationError(
            "created_at 明显晚于当前时间，请重新读取模型并生成计划。"
        )
    if expires_at <= current_time_utc:
        raise ActionPlanValidationError("计划已经过期，请重新读取模型并生成计划。")

    model_name = _object_name(root["model_name"], "model_name")
    _fingerprint(root["model_fingerprint"], "model_fingerprint")
    if root["unit_system"] != SUPPORTED_UNIT_SYSTEM:
        raise ActionPlanValidationError(
            "第一版只支持单位制 {0}。".format(SUPPORTED_UNIT_SYSTEM)
        )
    _warnings(root["warnings"], "warnings")
    requires_backup = _boolean(root["requires_backup"], "requires_backup")
    requires_job_confirmation = _boolean(
        root["requires_job_confirmation"], "requires_job_confirmation"
    )

    actions = root["actions"]
    if not isinstance(actions, list) or not actions:
        raise ActionPlanValidationError("actions 必须是非空数组。")
    if len(actions) > 20:
        raise ActionPlanValidationError("单个计划最多允许 20 个动作。")

    action_ids = set()
    action_types = []
    action_targets = set()
    for index, raw_action in enumerate(actions):
        action = _validate_common_action(raw_action, index)
        action_id = str(action["id"])
        if action_id in action_ids:
            raise ActionPlanValidationError("动作 ID 不能重复：{0}。".format(action_id))
        action_ids.add(action_id)
        action_type = str(action["type"])
        ACTION_VALIDATORS[action_type](action, "actions[{0}]".format(index))
        target = action["target"]
        assert isinstance(target, Mapping)
        if target.get("model") != model_name:
            raise ActionPlanValidationError(
                "actions[{0}] 的模型名必须与计划 model_name 一致。".format(index)
            )
        target_key = (
            action_type,
            json.dumps(target, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if target_key in action_targets:
            raise ActionPlanValidationError(
                "同一计划不能重复修改相同目标：actions[{0}]。".format(index)
            )
        action_targets.add(target_key)
        action_types.append(action_type)

    if ACTION_GET_MODEL_SUMMARY in action_types and len(action_types) != 1:
        raise ActionPlanValidationError(
            "get_model_summary 是独立只读动作，不能和写操作混在同一计划。"
        )

    # 若同一计划创建 Step 并引用它，创建动作必须排在边界条件之前。
    created_steps = {}
    part_changes = {}
    mesh_changes = {}
    save_indexes = []
    for index, action in enumerate(actions):
        action_type = str(action["type"])
        target = action["target"]
        assert isinstance(target, Mapping)
        if action_type == ACTION_CREATE_STATIC_STEP:
            created_steps[(target["model"], target["step"])] = index
        elif action_type == ACTION_SET_PART_PARAMETER:
            part_changes.setdefault((target["model"], target["part"]), []).append(index)
        elif action_type == ACTION_SET_MESH_SIZE:
            mesh_changes[(target["model"], target["part"])] = index
        elif action_type == ACTION_SAVE_CAE_AS:
            save_indexes.append(index)

    for index, action in enumerate(actions):
        if action["type"] != ACTION_CREATE_STATIC_STEP:
            continue
        target = action["target"]
        after = action["after"]
        assert isinstance(target, Mapping) and isinstance(after, Mapping)
        previous_index = created_steps.get((target["model"], after["previous_step"]))
        if previous_index is not None and previous_index >= index:
            raise ActionPlanValidationError(
                "新建静力步必须排在依赖它的后续静力步之前。"
            )

    for index, action in enumerate(actions):
        if action["type"] != ACTION_CREATE_DISPLACEMENT_BC:
            continue
        target = action["target"]
        after = action["after"]
        assert isinstance(target, Mapping) and isinstance(after, Mapping)
        created_index = created_steps.get((target["model"], after["step"]))
        if created_index is not None and created_index > index:
            raise ActionPlanValidationError(
                "创建静力步的动作必须排在引用该步的边界条件之前。"
            )
    for part_key, mesh_index in mesh_changes.items():
        if any(index > mesh_index for index in part_changes.get(part_key, [])):
            raise ActionPlanValidationError(
                "零件尺寸修改必须排在同一零件的网格尺寸设置之前。"
            )
    if len(save_indexes) > 1:
        raise ActionPlanValidationError("单个计划最多只能包含一个 save_cae_as。")
    if save_indexes:
        expected_save_index = len(actions) - (
            2
            if action_types[-1] in (ACTION_SUBMIT_JOB, ACTION_CREATE_SUBMIT_JOB)
            else 1
        )
        if save_indexes[0] != expected_save_index:
            raise ActionPlanValidationError(
                "save_cae_as 必须是最后一个普通动作，并位于 submit_job 之前。"
            )

    no_cae_backup_actions = (
        ACTION_GET_MODEL_SUMMARY,
        ACTION_READ_JOB_RESULTS_REPORT,
    )
    has_cae_write = any(value not in no_cae_backup_actions for value in action_types)
    if requires_backup != has_cae_write:
        raise ActionPlanValidationError(
            "requires_backup 必须准确反映计划是否修改 CAE。"
        )
    job_action_types = (ACTION_SUBMIT_JOB, ACTION_CREATE_SUBMIT_JOB)
    has_job = any(value in job_action_types for value in action_types)
    if requires_job_confirmation != has_job:
        raise ActionPlanValidationError(
            "requires_job_confirmation 必须准确反映是否提交 Job。"
        )
    if has_job and action_types[-1] not in job_action_types:
        raise ActionPlanValidationError("Job 提交动作必须是计划中的最后一个动作。")
    if sum(action_types.count(value) for value in job_action_types) > 1:
        raise ActionPlanValidationError("单个计划最多只能提交一个 Job。")

    _fingerprint(root["plan_digest"], "plan_digest")
    expected_digest = compute_plan_digest(root)
    if root["plan_digest"] != expected_digest:
        raise ActionPlanValidationError("plan_digest 与计划内容不一致。")

    # 返回深拷贝，避免后续步骤意外修改已经校验过的原始对象。
    return copy.deepcopy(dict(root))
