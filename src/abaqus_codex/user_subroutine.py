# -*- coding: utf-8 -*-
"""为需要用户子程序的内置模型生成本次运行专用的 Fortran 文件。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional


def _fortran_double(value: object) -> str:
    """把 Python 数值转换成固定、可读的 Fortran 双精度常量。"""

    return "{0:.15E}".format(float(value)).replace("E", "D")


def prepare_user_subroutine(
    config: Mapping[str, object], work_dir: Path
) -> Optional[Path]:
    """按模型类型生成受控子程序；普通模型不需要子程序并返回空值。"""

    if config["model"]["type"] != "moving_load_road":
        return None

    analysis = config["analysis"]
    template_path = (
        Path(__file__).resolve().parent
        / "user_subroutines"
        / "moving_pressure_dload.for.in"
    )
    if not template_path.is_file():
        raise RuntimeError("项目缺少移动载荷 DLOAD 模板：{0}".format(template_path))

    replacements = {
        "@LOAD_PRESSURE@": _fortran_double(analysis["load_pressure"]),
        "@LOAD_SPEED@": _fortran_double(analysis["load_speed"]),
        "@LOAD_HALF_LENGTH@": _fortran_double(
            float(analysis["load_length"]) / 2.0
        ),
        "@LOAD_HALF_WIDTH@": _fortran_double(
            float(analysis["load_width"]) / 2.0
        ),
        "@LOAD_CENTER_Y@": _fortran_double(analysis["load_center_y"]),
        "@LOAD_START_X@": _fortran_double(analysis["load_start_x"]),
    }
    source = template_path.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        source = source.replace(placeholder, value)
    if "@" in source:
        raise RuntimeError("DLOAD 模板仍包含未替换的参数占位符。")

    output_path = work_dir / "moving_pressure_dload.for"
    # 保留模板中的中文教学注释；Fortran 语句本身仍只使用 ASCII 字符。
    output_path.write_text(source, encoding="utf-8", newline="\n")
    return output_path
