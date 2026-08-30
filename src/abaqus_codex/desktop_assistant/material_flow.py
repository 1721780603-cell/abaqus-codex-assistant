# -*- coding: utf-8 -*-
"""把首个中文材料命令转换为可审阅的白名单 Action Plan。"""

from __future__ import annotations

import math
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Mapping, Optional

from abaqus_codex.assistant_protocol import (
    ActionPlanValidationError,
    seal_action_plan,
    validate_action_plan,
)


NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
MATERIAL_COMMAND_PATTERN = re.compile(
    r"^\s*(?:请\s*)?(?:把|将)\s*"
    r"(?P<model>.+?)\s*(?:中|里的?)\s*"
    r"(?P<material>.+?)\s*(?:的\s*)?弹性模量\s*"
    r"(?:改为|修改为|设为|设置为|=)\s*"
    r"(?P<youngs>" + NUMBER_PATTERN + r")\s*"
    r"(?P<unit>MPa|mpa|兆帕)"
    r"(?:\s*[,，;；]?\s*泊松比\s*"
    r"(?:改为|修改为|设为|设置为|为|=)?\s*"
    r"(?P<poisson>" + NUMBER_PATTERN + r"))?"
    r"\s*[。.]?\s*$"
)
FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_OBJECT_NAME_LENGTH = 80
MAX_STRESS_MPA = 1.0e12
PLAN_LIFETIME_MINUTES = 10


class MaterialCommandError(ValueError):
    """表示中文材料命令不完整或超出第一版范围。"""


@dataclass(frozen=True)
class MaterialEditRequest:
    """从中文命令中提取的目标和新值。"""

    model_name: str
    material_name: str
    youngs_modulus: float
    poisson_ratio: Optional[float]


@dataclass(frozen=True)
class MaterialElasticState:
    """Abaqus 执行端刚刚读取的简单各向同性弹性参数。"""

    model_name: str
    material_name: str
    youngs_modulus: float
    poisson_ratio: float
    stress_unit: str
    fingerprint: str


def compute_material_fingerprint(
    model_name: str,
    material_name: str,
    youngs_modulus: float,
    poisson_ratio: float,
) -> str:
    """按桌面端和 Abaqus 端共享的规则计算材料状态指纹。"""

    canonical_value = {
        "model": _safe_object_name(model_name, "模型名"),
        "material": _safe_object_name(material_name, "材料名"),
        "youngs_modulus": _finite_number(
            youngs_modulus,
            "弹性模量",
            minimum=0.0,
            maximum=MAX_STRESS_MPA,
            exclusive_minimum=True,
        ),
        "poisson_ratio": _finite_number(
            poisson_ratio,
            "泊松比",
            minimum=-1.0,
            maximum=0.5,
            exclusive_minimum=True,
            exclusive_maximum=True,
        ),
        "stress_unit": "MPa",
    }
    canonical = json.dumps(
        canonical_value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _safe_object_name(value: str, label: str) -> str:
    """限制 Abaqus 对象名，避免把路径或控制字符放入计划。"""

    name = value.strip()
    if not name or len(name) > MAX_OBJECT_NAME_LENGTH:
        raise MaterialCommandError(
            "{0}不能为空，且不能超过 {1} 个字符。".format(
                label, MAX_OBJECT_NAME_LENGTH
            )
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise MaterialCommandError("{0}不能包含控制字符。".format(label))
    if re.search(r"[\\/:*?\"<>|]", name):
        raise MaterialCommandError("{0}不能包含路径字符。".format(label))
    return name


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: float,
    maximum: float,
    exclusive_minimum: bool = False,
    exclusive_maximum: bool = False,
) -> float:
    """拒绝布尔值、非有限数和超出首版范围的材料参数。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MaterialCommandError("{0}必须是数值。".format(label))
    number = float(value)
    if not math.isfinite(number):
        raise MaterialCommandError("{0}必须是有限数值。".format(label))
    if number < minimum or (exclusive_minimum and number == minimum):
        relation = "大于" if exclusive_minimum else "大于等于"
        raise MaterialCommandError(
            "{0}必须{1} {2}。".format(label, relation, minimum)
        )
    if number > maximum or (exclusive_maximum and number == maximum):
        relation = "小于" if exclusive_maximum else "小于等于"
        raise MaterialCommandError(
            "{0}必须{1} {2}。".format(label, relation, maximum)
        )
    return number


def parse_material_command(value: object) -> Optional[MaterialEditRequest]:
    """识别首批固定中文句式；其他命令返回 ``None``。"""

    text = str(value)
    if "弹性模量" not in text:
        return None
    match = MATERIAL_COMMAND_PATTERN.fullmatch(text)
    if match is None:
        raise MaterialCommandError(
            "第一版请使用：把 Model-1 中 Steel 的弹性模量改为 "
            "210000 MPa；需要时可在后面补充“泊松比 0.3”。"
        )

    model_name = _safe_object_name(match.group("model"), "模型名")
    material_name = _safe_object_name(match.group("material"), "材料名")
    try:
        youngs_modulus = float(match.group("youngs"))
        poisson_text = match.group("poisson")
        poisson_ratio = float(poisson_text) if poisson_text is not None else None
    except (TypeError, ValueError, OverflowError) as error:
        raise MaterialCommandError("材料参数不是有效数值。") from error

    youngs_modulus = _finite_number(
        youngs_modulus,
        "弹性模量",
        minimum=0.0,
        maximum=MAX_STRESS_MPA,
        exclusive_minimum=True,
    )
    if poisson_ratio is not None:
        poisson_ratio = _finite_number(
            poisson_ratio,
            "泊松比",
            minimum=-1.0,
            maximum=0.5,
            exclusive_minimum=True,
            exclusive_maximum=True,
        )
    return MaterialEditRequest(
        model_name=model_name,
        material_name=material_name,
        youngs_modulus=youngs_modulus,
        poisson_ratio=poisson_ratio,
    )


def normalize_material_state(payload: Mapping[str, object]) -> MaterialElasticState:
    """严格读取安全插件返回的当前材料旧值。"""

    expected_fields = {
        "model",
        "material",
        "youngs_modulus",
        "poisson_ratio",
        "stress_unit",
        "fingerprint",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected_fields:
        raise MaterialCommandError("Abaqus 返回的材料参数结构不完整。")
    model_name = _safe_object_name(str(payload["model"]), "模型名")
    material_name = _safe_object_name(str(payload["material"]), "材料名")
    youngs_modulus = _finite_number(
        payload["youngs_modulus"],
        "当前弹性模量",
        minimum=0.0,
        maximum=MAX_STRESS_MPA,
        exclusive_minimum=True,
    )
    poisson_ratio = _finite_number(
        payload["poisson_ratio"],
        "当前泊松比",
        minimum=-1.0,
        maximum=0.5,
        exclusive_minimum=True,
        exclusive_maximum=True,
    )
    if payload["stress_unit"] != "MPa":
        raise MaterialCommandError("第一版只接受 MPa 应力单位。")
    fingerprint = payload["fingerprint"]
    if not isinstance(fingerprint, str) or FINGERPRINT_PATTERN.fullmatch(
        fingerprint
    ) is None:
        raise MaterialCommandError("材料状态指纹格式无效。")
    return MaterialElasticState(
        model_name=model_name,
        material_name=material_name,
        youngs_modulus=youngs_modulus,
        poisson_ratio=poisson_ratio,
        stress_unit="MPa",
        fingerprint=fingerprint,
    )


def _utc_text(value: datetime) -> str:
    """生成 Python 2.7 执行端也能稳定解析的 UTC 时间。"""

    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_material_plan(
    request: MaterialEditRequest,
    current: MaterialElasticState,
    *,
    now: Optional[datetime] = None,
    id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> Dict[str, object]:
    """用实时旧值构造并复核一个十分钟内有效的写计划。"""

    if request.model_name != current.model_name:
        raise MaterialCommandError("命令中的模型与 Abaqus 实时结果不一致。")
    if request.material_name != current.material_name:
        raise MaterialCommandError("命令中的材料与 Abaqus 实时结果不一致。")
    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        raise MaterialCommandError("计划生成时间必须包含时区。")
    expires_at = created_at + timedelta(minutes=PLAN_LIFETIME_MINUTES)
    new_poisson = (
        current.poisson_ratio
        if request.poisson_ratio is None
        else request.poisson_ratio
    )
    token = id_factory()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token):
        raise MaterialCommandError("计划随机标识格式无效。")

    before = {
        "youngs_modulus": current.youngs_modulus,
        "poisson_ratio": current.poisson_ratio,
        "stress_unit": "MPa",
    }
    after = {
        "youngs_modulus": request.youngs_modulus,
        "poisson_ratio": new_poisson,
        "stress_unit": "MPa",
    }
    plan = {
        "schema_version": "abaqus.action.v1",
        "abaqus_release": "2021",
        "plan_id": "plan-" + token[:24],
        "created_at": _utc_text(created_at),
        "expires_at": _utc_text(expires_at),
        "model_name": current.model_name,
        "model_fingerprint": current.fingerprint,
        "unit_system": "mm-N-s-MPa",
        "actions": [
            {
                "id": "material-" + token[:20],
                "type": "set_material_elastic",
                "target": {
                    "model": current.model_name,
                    "material": current.material_name,
                },
                "before": before,
                "after": after,
                "risk": "low",
                "warnings": [
                    "只支持已有的单行各向同性线弹性材料。",
                    "执行前会再次核对旧值，变化后必须重新生成计划。",
                ],
            }
        ],
        "warnings": [
            "Abaqus 不保存单位制；请确认当前模型采用 mm-N-s-MPa。",
            "应用前会另存为新的受保护工作副本，不覆盖原 CAE 文件。",
        ],
        "requires_backup": True,
        "requires_job_confirmation": False,
    }
    try:
        return validate_action_plan(seal_action_plan(plan), now=created_at)
    except ActionPlanValidationError as error:
        raise MaterialCommandError("修改计划没有通过安全校验。") from error


def format_material_plan(plan: Mapping[str, object]) -> str:
    """把已校验计划转换为初学者可审阅的中文说明。"""

    checked = validate_action_plan(plan)
    action = checked["actions"][0]
    target = action["target"]
    before = action["before"]
    after = action["after"]
    warnings = list(checked["warnings"]) + list(action["warnings"])
    lines = [
        "【修改计划｜尚未执行】",
        "涉及模型：{0}".format(target["model"]),
        "涉及材料：{0}".format(target["material"]),
        "动作类型：修改已有各向同性线弹性参数",
        "",
        "旧弹性模量：{0:g} MPa".format(before["youngs_modulus"]),
        "新弹性模量：{0:g} MPa".format(after["youngs_modulus"]),
        "旧泊松比：{0:g}".format(before["poisson_ratio"]),
        "新泊松比：{0:g}".format(after["poisson_ratio"]),
        "风险等级：低（仍属于模型写操作）",
        "",
        "保护措施：点击“应用修改”前不会改变模型；应用时先创建新的 CAE 工作副本。",
        "计划有效期：10 分钟；旧值变化后自动拒绝。",
    ]
    if warnings:
        lines.append("")
        lines.append("风险提示：")
        lines.extend("- " + str(item) for item in warnings)
    lines.extend(("", "计划编号：{0}".format(checked["plan_id"])))
    return "\n".join(lines)


__all__ = [
    "MaterialCommandError",
    "MaterialEditRequest",
    "MaterialElasticState",
    "build_material_plan",
    "compute_material_fingerprint",
    "format_material_plan",
    "normalize_material_state",
    "parse_material_command",
]
