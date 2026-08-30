# -*- coding: utf-8 -*-
"""二维矩形板第一步的中文解析、计划生成和展示。"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from abaqus_codex.assistant_protocol import seal_action_plan, validate_action_plan


MAX_LENGTH_MM = 1.0e9
DEFAULT_RECTANGLE_COMMAND = (
    "创建一个长 100 mm、宽 20 mm 的二维矩形板，"
    "模型名 Model-1，零件名 Plate"
)
NAME_PATTERN = re.compile(r'^[^\\/:*?"<>|\x00-\x1f\x7f]{1,80}$')
RECTANGLE_PATTERN = re.compile(
    r"^创建一个长\s*(?P<length>[0-9]+(?:\.[0-9]+)?)\s*mm[、,，\s]*"
    r"宽\s*(?P<width>[0-9]+(?:\.[0-9]+)?)\s*mm\s*的二维矩形板[，,\s]*"
    r"模型名\s*(?P<model>[^，,\s]+)[，,\s]*"
    r"零件名\s*(?P<part>[^，,\s。]+)[。\s]*$"
)


class RectangleCommandError(ValueError):
    """表示矩形板命令不完整或数值不安全。"""


@dataclass(frozen=True)
class RectangleCreateRequest:
    """经过本地固定句式解析的矩形板请求。"""

    model_name: str
    part_name: str
    length: float
    width: float


def _safe_name(value: str, label: str) -> str:
    """校验 Abaqus 对象名，但不允许把路径当名称。"""

    name = value.strip()
    if name != value or NAME_PATTERN.fullmatch(name) is None:
        raise RectangleCommandError(
            "{0}不能为空、不能超过 80 字符，也不能包含路径字符。".format(label)
        )
    return name


def _dimension(value: str, label: str) -> float:
    """把毫米数值限制为有限正数。"""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise RectangleCommandError("{0}不是有效毫米数值。".format(label)) from error
    if not math.isfinite(number) or number <= 0.0 or number > MAX_LENGTH_MM:
        raise RectangleCommandError(
            "{0}必须大于 0 且不超过 {1:g} mm。".format(label, MAX_LENGTH_MM)
        )
    return number


def parse_rectangle_command(value: object) -> Optional[RectangleCreateRequest]:
    """识别唯一矩形板固定句式；非矩形板命令返回 None。"""

    text = " ".join(str(value).split())
    if "二维矩形板" not in text:
        return None
    match = RECTANGLE_PATTERN.fullmatch(text)
    if match is None:
        raise RectangleCommandError(
            "第一步请使用：" + DEFAULT_RECTANGLE_COMMAND
        )
    return RectangleCreateRequest(
        model_name=_safe_name(match.group("model"), "模型名"),
        part_name=_safe_name(match.group("part"), "零件名"),
        length=_dimension(match.group("length"), "长度"),
        width=_dimension(match.group("width"), "宽度"),
    )


def build_rectangle_plan(
    request: RectangleCreateRequest,
    *,
    snapshot_fingerprint: str,
    model_exists: bool,
    part_exists: bool,
    now: Optional[datetime] = None,
    id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> dict[str, object]:
    """根据已读取摘要生成十分钟有效的几何计划。"""

    if part_exists:
        raise RectangleCommandError("目标模型中已经存在同名零件，禁止覆盖。")
    # 模型摘要内部保存裸 SHA-256；动作协议显式标注算法名称。
    fingerprint = str(snapshot_fingerprint).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        fingerprint = "sha256:" + fingerprint
    if re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint) is None:
        raise RectangleCommandError("当前模型摘要指纹无效，请重新刷新模型。")
    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        raise RectangleCommandError("计划时间必须包含时区。")
    token = id_factory()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token) is None:
        raise RectangleCommandError("计划随机标识格式无效。")
    utc = lambda value: value.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    plan = {
        "schema_version": "abaqus.action.v1",
        "abaqus_release": "2021",
        "plan_id": "plan-" + token[:24],
        "created_at": utc(created_at),
        "expires_at": utc(created_at + timedelta(minutes=10)),
        "model_name": request.model_name,
        "model_fingerprint": fingerprint,
        "unit_system": "mm-N-s-MPa",
        "actions": [
            {
                "id": "rectangle-" + token[:20],
                "type": "create_rectangle_part",
                "target": {
                    "model": request.model_name,
                    "part": request.part_name,
                },
                "before": {
                    "model_exists": bool(model_exists),
                    "part_exists": False,
                },
                "after": {
                    "length": request.length,
                    "width": request.width,
                    "length_unit": "mm",
                    "dimensionality": "TWO_D_PLANAR",
                    "part_type": "DEFORMABLE_BODY",
                    "origin": "lower_left_0_0",
                },
                "risk": "medium",
                "warnings": [
                    "本步骤只创建几何，不创建材料、截面、网格、载荷或 Job。",
                    "二维类型暂定为平面几何；平面应力或平面应变将在单元类型步骤确认。",
                ],
            }
        ],
        "warnings": [
            "Abaqus 不保存单位制；当前按 mm-N-s-MPa 解释尺寸。",
            "应用时先建立受保护工作副本，原 CAE 文件不会被覆盖。",
        ],
        "requires_backup": True,
        "requires_job_confirmation": False,
    }
    return validate_action_plan(seal_action_plan(plan), now=created_at)


def format_rectangle_plan(plan: Mapping[str, object]) -> str:
    """把几何计划转换为初学者可审阅的中文说明。"""

    checked = validate_action_plan(plan)
    action = checked["actions"][0]
    target = action["target"]
    before = action["before"]
    after = action["after"]
    lines = [
        "【教学路线：二维矩形板拉伸】",
        "当前步骤：1/10 创建几何",
        "状态：计划已生成，尚未执行",
        "",
        "模型：{0}（{1}）".format(
            target["model"], "复用现有模型" if before["model_exists"] else "创建新模型"
        ),
        "零件：{0}".format(target["part"]),
        "几何：二维可变形矩形板",
        "长度：{0:g} mm".format(after["length"]),
        "宽度：{0:g} mm".format(after["width"]),
        "原点：左下角 (0, 0)",
        "",
        "本次不会创建：材料、截面、装配、分析步、载荷、网格或 Job。",
        "确认后将先创建工作副本，再在副本中建立几何。",
        "下一步：定义材料。",
    ]
    return "\n".join(lines)


__all__ = [
    "RectangleCommandError",
    "RectangleCreateRequest",
    "build_rectangle_plan",
    "format_rectangle_plan",
    "parse_rectangle_command",
]
