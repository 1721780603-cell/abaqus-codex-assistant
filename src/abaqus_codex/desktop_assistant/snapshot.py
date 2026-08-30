# -*- coding: utf-8 -*-
"""裁剪并显示只读模型概要，默认移除本机完整路径。"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple


MAX_NAME_LENGTH = 160
MAX_MODELS = 50
MAX_NAMES_PER_FIELD = 200


def _clean_text(value: object, *, maximum: int = MAX_NAME_LENGTH) -> str:
    """把对象名称转换为有限文本，并移除控制字符。"""

    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        return "<无法读取>"
    cleaned = "".join(
        character if ord(character) >= 32 and ord(character) != 127 else " "
        for character in str(value)
    )
    return " ".join(cleaned.split())[:maximum]


def _name_tuple(value: object) -> Tuple[str, ...]:
    """只保留名称列表，不把未知 Abaqus 对象序列化到应用中。"""

    if not isinstance(value, (list, tuple)):
        return ()
    names = []
    for item in value[:MAX_NAMES_PER_FIELD]:
        text = _clean_text(item)
        if text:
            names.append(text)
    return tuple(names)


@dataclass(frozen=True)
class ModelOverview:
    """一个模型的有限对象名称概要。"""

    name: str
    parts: Tuple[str, ...]
    materials: Tuple[str, ...]
    steps: Tuple[str, ...]
    instances: Tuple[str, ...]
    loads: Tuple[str, ...]
    boundary_conditions: Tuple[str, ...]
    interactions: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        """返回用于指纹计算的稳定字典。"""

        return {
            "name": self.name,
            "parts": self.parts,
            "materials": self.materials,
            "steps": self.steps,
            "instances": self.instances,
            "loads": self.loads,
            "boundary_conditions": self.boundary_conditions,
            "interactions": self.interactions,
        }


@dataclass(frozen=True)
class ModelSnapshot:
    """可安全展示的只读快照；不包含工作目录和工程文件路径。"""

    models: Tuple[ModelOverview, ...]
    current_viewport: Optional[str]
    source: str
    is_mock: bool
    warning: Optional[str]
    truncated: bool
    fingerprint: str
    captured_at: str


def normalize_model_info(
    payload: Mapping[str, object], *, source: str, is_mock: bool = False
) -> ModelSnapshot:
    """把第三方 get_model_info 返回值收敛到项目自己的只读结构。"""

    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("模型概要中的 models 必须是列表。")

    overviews = []
    truncated = len(raw_models) > MAX_MODELS
    for raw_model in raw_models[:MAX_MODELS]:
        if not isinstance(raw_model, Mapping):
            continue
        for field in (
            "parts",
            "materials",
            "steps",
            "assemblies",
            "loads",
            "bcs",
            "interactions",
        ):
            field_value = raw_model.get(field)
            if (
                isinstance(field_value, (list, tuple))
                and len(field_value) > MAX_NAMES_PER_FIELD
            ):
                truncated = True
        name = _clean_text(raw_model.get("name")) or "<未命名模型>"
        overviews.append(
            ModelOverview(
                name=name,
                parts=_name_tuple(raw_model.get("parts")),
                materials=_name_tuple(raw_model.get("materials")),
                steps=_name_tuple(raw_model.get("steps")),
                instances=_name_tuple(raw_model.get("assemblies")),
                loads=_name_tuple(raw_model.get("loads")),
                boundary_conditions=_name_tuple(raw_model.get("bcs")),
                interactions=_name_tuple(raw_model.get("interactions")),
            )
        )

    current_viewport = _clean_text(payload.get("current_viewport")) or None
    warning = None
    if payload.get("error") or payload.get("partial"):
        # 第三方异常经常包含完整 CAE 路径，默认不把原文带入界面或 AI 上下文。
        warning = "Abaqus 返回了部分信息；某些对象名称无法读取。"

    # 指纹只覆盖允许展示的字段；以后可用于拒绝过期修改计划。
    fingerprint_source = {
        "models": [overview.as_dict() for overview in overviews],
    }
    canonical = json.dumps(
        fingerprint_source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    raw_captured_at = payload.get("snapshot_generated_at")
    if (
        isinstance(raw_captured_at, (int, float))
        and not isinstance(raw_captured_at, bool)
        and math.isfinite(raw_captured_at)
    ):
        try:
            captured_at = datetime.fromtimestamp(
                raw_captured_at
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        except (OSError, OverflowError, ValueError):
            captured_at = datetime.now().astimezone().strftime(
                "%Y-%m-%d %H:%M:%S %z"
            )
    else:
        captured_at = datetime.now().astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %z"
        )
    return ModelSnapshot(
        models=tuple(overviews),
        current_viewport=current_viewport,
        source=source,
        is_mock=is_mock,
        warning=warning,
        truncated=truncated,
        fingerprint=fingerprint,
        captured_at=captured_at,
    )


def _format_names(label: str, names: Sequence[str]) -> str:
    """把对象名称压缩成适合新手快速浏览的一行。"""

    if not names:
        return "  {0}：无".format(label)
    shown = list(names[:12])
    suffix = "，另有 {0} 个".format(len(names) - 12) if len(names) > 12 else ""
    return "  {0}（{1}）：{2}{3}".format(
        label, len(names), "、".join(shown), suffix
    )


def format_snapshot(snapshot: ModelSnapshot) -> str:
    """生成不夸大读取能力的中文模型摘要。"""

    lines = []
    if snapshot.is_mock:
        lines.append("【模拟数据】以下内容没有从 Abaqus 读取。")
    else:
        lines.append("【只读快照】模型未被修改。")
    lines.append("数据来源：{0}".format(snapshot.source))
    lines.append("读取时间：{0}".format(snapshot.captured_at))
    lines.append("单位约定：未知（Abaqus 不内置单位制）")
    if snapshot.current_viewport:
        lines.append("当前视口：{0}".format(snapshot.current_viewport))
    lines.append("模型数量：{0}".format(len(snapshot.models)))

    if not snapshot.models:
        lines.append("")
        lines.append("当前 MDB 中没有可读取的模型。")
    for index, model in enumerate(snapshot.models, start=1):
        lines.extend(
            (
                "",
                "模型 {0}：{1}".format(index, model.name),
                _format_names("零件", model.parts),
                _format_names("材料", model.materials),
                _format_names("分析步", model.steps),
                _format_names("装配实例", model.instances),
                _format_names("载荷", model.loads),
                _format_names("边界条件", model.boundary_conditions),
                _format_names("接触/相互作用", model.interactions),
            )
        )

    if snapshot.warning:
        lines.extend(("", "注意：{0}".format(snapshot.warning)))
    if snapshot.truncated:
        lines.extend(("", "注意：模型数量过多，当前摘要已截断。"))
    lines.extend(
        (
            "",
            "当前能力边界：只读取对象名称，不读取材料数值、几何坐标或完整路径。",
            "快照指纹：{0}".format(snapshot.fingerprint[:12]),
        )
    )
    return "\n".join(lines)


__all__ = [
    "ModelOverview",
    "ModelSnapshot",
    "format_snapshot",
    "normalize_model_info",
]
