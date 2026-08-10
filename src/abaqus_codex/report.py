# -*- coding: utf-8 -*-
"""根据结构化 Abaqus 结果生成简单中文 Markdown 报告。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


def _number(value: object) -> str:
    """使用紧凑但足够核查的有效数字显示计算结果。"""

    return "{0:.8g}".format(float(value))


def _model_specific_text(
    model_type: str,
    model: Mapping[str, object],
    analysis: Mapping[str, object],
    units: Mapping[str, object],
) -> tuple[str, str, str, str]:
    """返回模型标题、额外参数、边界条件和结果说明。"""

    length_unit = units["length"]
    stress_unit = units["stress"]

    if model_type == "plate_with_hole":
        title = "二维中心圆孔板拉伸分析报告"
        extra_parameters = (
            "- 圆孔半径：{0} {1}\n"
            "- 孔边网格尺寸：{2} {1}\n"
        ).format(
            _number(model["hole_radius"]),
            length_unit,
            _number(analysis["hole_mesh_size"]),
        )
        boundary_conditions = (
            "- 左边界：约束水平方向位移；\n"
            "- 左下角：约束竖直方向位移，用于消除刚体运动；\n"
            "- 右边界：施加 {0} {1} 的水平拉伸位移；"
        ).format(_number(analysis["right_edge_displacement"]), length_unit)
        note = (
            "圆孔附近存在应力集中，最大应力会对孔边网格尺寸较敏感。"
            "用于论文或工程项目前，应继续进行网格收敛性分析。"
        )
    elif model_type == "cantilever_bending":
        title = "二维悬臂梁均布载荷弯曲分析报告"
        extra_parameters = "- 上边界均布载荷：{0} {1}\n".format(
            _number(analysis["top_edge_pressure"]), stress_unit
        )
        boundary_conditions = (
            "- 左边界：约束水平和竖直方向位移，形成固定端；\n"
            "- 上边界：施加竖直向下、大小为 {0} {1} 的均布载荷；"
        ).format(_number(analysis["top_edge_pressure"]), stress_unit)
        note = (
            "固定端角点附近的最大应力可能对网格尺寸较敏感。"
            "学习时可用材料力学梁理论核对位移趋势；用于正式项目时应进行网格收敛分析。"
        )
    elif model_type == "biaxial_tension":
        title = "二维方板双向拉伸分析报告"
        extra_parameters = ""
        boundary_conditions = (
            "- 左边界：约束水平方向位移；\n"
            "- 下边界：约束竖直方向位移；\n"
            "- 右边界：施加 {0} {1} 的水平拉伸位移；\n"
            "- 上边界：施加 {2} {1} 的竖直拉伸位移；"
        ).format(
            _number(analysis["right_edge_displacement"]),
            length_unit,
            _number(analysis["top_edge_displacement"]),
        )
        note = (
            "方板采用相同的两个方向应变时，板内应接近均匀双向应力状态。"
            "可用平面应力理论值进行入门核对，但必须保证材料和几何参数使用同一套单位制。"
        )
    else:
        title = "二维矩形板拉伸分析报告"
        extra_parameters = ""
        boundary_conditions = (
            "- 左边界：约束水平方向位移；\n"
            "- 左下角：约束竖直方向位移，用于消除刚体运动；\n"
            "- 右边界：施加 {0} {1} 的水平拉伸位移；"
        ).format(_number(analysis["right_edge_displacement"]), length_unit)
        note = ""

    return title, extra_parameters, boundary_conditions, note


def build_chinese_report(results: Mapping[str, object]) -> str:
    """生成包含模型参数、边界条件和极值结果的中文报告文本。"""

    config = results["config"]
    model = config["model"]
    material = config["material"]
    analysis = config["analysis"]
    units = config["units"]
    displacement_location = results["maximum_displacement_location"]
    stress_location = results["maximum_mises_stress_location"]

    model_type = str(model.get("type", "rectangle"))
    report_title, extra_parameters, boundary_conditions, model_note = (
        _model_specific_text(model_type, model, analysis, units)
    )

    return """# {report_title}

## 1. 计算概况

- 作业名称：`{job_name}`
- 模型名称：`{model_name}`
- 计算状态：已完成
- 结果生成时间：{generated_at}
- Abaqus Python：{abaqus_python_version}

## 2. 模型与材料

- 板长：{length} {length_unit}
- 板高：{height} {length_unit}
- 板厚：{thickness} {length_unit}
{extra_parameters}- 材料：{material_name}
- 弹性模量：{youngs_modulus} {stress_unit}
- 泊松比：{poisson_ratio}
- 全局网格尺寸：{mesh_size} {length_unit}

## 3. 边界条件

{boundary_conditions}
- 分析类型：二维平面应力、线弹性、静力分析。

## 4. 主要结果

- **最大位移模：{maximum_displacement} {length_unit}**
  - 位置：实例 `{u_instance}`，节点 {u_node}
- **最大 Mises 应力：{maximum_mises_stress} {stress_unit}**
  - 位置：实例 `{s_instance}`，单元 {s_element}，积分点 {s_point}

## 5. 结果说明

本报告读取 ODB 最后一个分析帧，并在全模型范围内搜索位移模和 Mises 应力最大值。Abaqus 不内置单位制，本报告中的单位来自输入配置；使用结果前应核对材料参数、几何尺寸和载荷采用了同一套单位制。

{model_note}

> 本报告由 Abaqus Codex Assistant 自动生成。第一阶段结果仅用于示例与流程验证，实际工程项目仍需由具备相应资质的工程师复核。
""".format(
        report_title=report_title,
        job_name=results["job_name"],
        model_name=results["model_name"],
        generated_at=results["generated_at"],
        abaqus_python_version=results["abaqus_python_version"],
        length=_number(model["length"]),
        height=_number(model["height"]),
        thickness=_number(model["thickness"]),
        extra_parameters=extra_parameters,
        length_unit=units["length"],
        material_name=material["name"],
        youngs_modulus=_number(material["youngs_modulus"]),
        stress_unit=units["stress"],
        poisson_ratio=_number(material["poisson_ratio"]),
        mesh_size=_number(analysis["mesh_size"]),
        boundary_conditions=boundary_conditions,
        maximum_displacement=_number(results["maximum_displacement"]),
        u_instance=displacement_location["instance"],
        u_node=displacement_location["node_label"],
        maximum_mises_stress=_number(results["maximum_mises_stress"]),
        s_instance=stress_location["instance"],
        s_element=stress_location["element_label"],
        s_point=stress_location["integration_point"],
        model_note=model_note,
    )


def write_chinese_report(path: Path, results: Mapping[str, object]) -> None:
    """把中文报告写入 UTF-8 Markdown 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_chinese_report(results), encoding="utf-8", newline="\n")
