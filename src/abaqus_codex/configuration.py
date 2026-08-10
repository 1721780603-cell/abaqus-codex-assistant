# -*- coding: utf-8 -*-
"""读取并校验二维板拉伸模型的 JSON 配置。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Mapping


# Abaqus 作业名只允许安全字符，避免空格和命令符号进入外部程序。
JOB_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")

# 旧配置没有 type 字段，因此必须继续把它解释为最初的矩形板模型。
MODEL_TYPE_RECTANGLE = "rectangle"
MODEL_TYPE_PLATE_WITH_HOLE = "plate_with_hole"
MODEL_TYPE_CANTILEVER_BENDING = "cantilever_bending"
MODEL_TYPE_BIAXIAL_TENSION = "biaxial_tension"
SUPPORTED_MODEL_TYPES = (
    MODEL_TYPE_RECTANGLE,
    MODEL_TYPE_PLATE_WITH_HOLE,
    MODEL_TYPE_CANTILEVER_BENDING,
    MODEL_TYPE_BIAXIAL_TENSION,
)


class ConfigurationError(ValueError):
    """表示配置内容缺失或数值不符合建模要求。"""


def _mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """读取必需的配置分组。"""

    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError("缺少配置分组：{0}".format(key))
    return value


def _text(data: Mapping[str, object], key: str, label: str) -> str:
    """读取非空文本。"""

    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("{0}必须是非空文本。".format(label))
    return value.strip()


def _number(data: Mapping[str, object], key: str, label: str) -> float:
    """读取数值，同时排除会被 Python 当作整数的布尔值。"""

    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError("{0}必须是数值。".format(label))
    return float(value)


def _positive_number(data: Mapping[str, object], key: str, label: str) -> float:
    """读取严格大于零的数值。"""

    value = _number(data, key, label)
    if value <= 0.0:
        raise ConfigurationError("{0}必须大于零。".format(label))
    return value


def _model_type(model: Mapping[str, object]) -> str:
    """读取模型类型，并兼容第一版没有 type 字段的矩形板配置。"""

    value = model.get("type", MODEL_TYPE_RECTANGLE)
    if not isinstance(value, str) or value not in SUPPORTED_MODEL_TYPES:
        raise ConfigurationError(
            "模型类型必须是：{0}。".format("、".join(SUPPORTED_MODEL_TYPES))
        )
    return value


def validate_config(data: Mapping[str, object]) -> Dict[str, object]:
    """校验配置并返回类型统一、可直接交给 Abaqus 的数据。"""

    model = _mapping(data, "model")
    material = _mapping(data, "material")
    analysis = _mapping(data, "analysis")
    units = _mapping(data, "units")

    model_type = _model_type(model)
    length = _positive_number(model, "length", "板长")
    height = _positive_number(model, "height", "板高")
    thickness = _positive_number(model, "thickness", "板厚")
    youngs_modulus = _positive_number(material, "youngs_modulus", "弹性模量")
    poisson_ratio = _number(material, "poisson_ratio", "泊松比")
    mesh_size = _positive_number(analysis, "mesh_size", "网格尺寸")

    if not -1.0 < poisson_ratio < 0.5:
        raise ConfigurationError("泊松比必须位于 -1 和 0.5 之间。")
    if mesh_size > min(length, height):
        raise ConfigurationError("网格尺寸不能大于板的最短边。")

    # 圆孔位于板中心，因此孔直径必须严格小于板的长和高。
    normalized_model = {
        "type": model_type,
        "name": _text(model, "name", "模型名"),
        "length": length,
        "height": height,
        "thickness": thickness,
    }
    hole_radius = None
    if model_type == MODEL_TYPE_PLATE_WITH_HOLE:
        hole_radius = _positive_number(model, "hole_radius", "圆孔半径")
        if hole_radius * 2.0 >= min(length, height):
            raise ConfigurationError("圆孔直径必须小于板的长和高。")
        normalized_model["hole_radius"] = hole_radius

    num_cpus_value = analysis.get("num_cpus", 1)
    if (
        isinstance(num_cpus_value, bool)
        or not isinstance(num_cpus_value, int)
        or num_cpus_value < 1
    ):
        raise ConfigurationError("CPU 数量必须是大于等于 1 的整数。")

    job_name = _text(analysis, "job_name", "作业名")
    if JOB_NAME_PATTERN.fullmatch(job_name) is None:
        raise ConfigurationError(
            "作业名必须以英文字母开头，并且只能包含字母、数字、下划线和短横线。"
        )

    normalized_analysis = {
        "step_name": _text(analysis, "step_name", "分析步名称"),
        "job_name": job_name,
        "mesh_size": mesh_size,
        "num_cpus": num_cpus_value,
    }
    # 不同模型采用不同载荷参数，按模型分别校验可以给初学者更准确的错误提示。
    if model_type in (
        MODEL_TYPE_RECTANGLE,
        MODEL_TYPE_PLATE_WITH_HOLE,
        MODEL_TYPE_BIAXIAL_TENSION,
    ):
        normalized_analysis["right_edge_displacement"] = _positive_number(
            analysis, "right_edge_displacement", "右边界拉伸位移"
        )
    if model_type == MODEL_TYPE_CANTILEVER_BENDING:
        normalized_analysis["top_edge_pressure"] = _positive_number(
            analysis, "top_edge_pressure", "上边界均布压力"
        )
    if model_type == MODEL_TYPE_BIAXIAL_TENSION:
        normalized_analysis["top_edge_displacement"] = _positive_number(
            analysis, "top_edge_displacement", "上边界拉伸位移"
        )
    if model_type == MODEL_TYPE_PLATE_WITH_HOLE:
        default_hole_mesh_size = min(mesh_size, float(hole_radius) / 4.0)
        if "hole_mesh_size" in analysis:
            hole_mesh_size = _positive_number(
                analysis, "hole_mesh_size", "孔边网格尺寸"
            )
        else:
            hole_mesh_size = default_hole_mesh_size
        if hole_mesh_size > mesh_size:
            raise ConfigurationError("孔边网格尺寸不能大于全局网格尺寸。")
        normalized_analysis["hole_mesh_size"] = hole_mesh_size

    # 返回新的字典，避免后续步骤意外修改用户原始配置。
    return {
        "model": normalized_model,
        "material": {
            "name": _text(material, "name", "材料名"),
            "youngs_modulus": youngs_modulus,
            "poisson_ratio": poisson_ratio,
        },
        "analysis": normalized_analysis,
        "units": {
            "length": _text(units, "length", "长度单位"),
            "stress": _text(units, "stress", "应力单位"),
        },
    }


def validate_rectangle_config(data: Mapping[str, object]) -> Dict[str, object]:
    """保留第一版函数名，内部使用新的通用配置校验。"""

    return validate_config(data)


def load_config(path: Path) -> Dict[str, object]:
    """从 UTF-8 JSON 文件读取并校验二维板配置。"""

    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError as error:
        raise ConfigurationError("没有找到配置文件：{0}".format(path)) from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            "配置文件不是有效 JSON：第 {0} 行第 {1} 列。".format(
                error.lineno, error.colno
            )
        ) from error

    if not isinstance(data, Mapping):
        raise ConfigurationError("配置文件最外层必须是 JSON 对象。")
    return validate_config(data)


def load_rectangle_config(path: Path) -> Dict[str, object]:
    """保留第一版函数名，避免已有调用代码失效。"""

    return load_config(path)


def write_json(path: Path, data: Mapping[str, object]) -> None:
    """以稳定格式写入 JSON，便于用户检查和版本管理。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
