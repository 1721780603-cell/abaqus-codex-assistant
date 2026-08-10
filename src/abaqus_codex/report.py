# -*- coding: utf-8 -*-
"""根据结构化 Abaqus 结果生成简单中文 Markdown 报告。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


def _number(value: object) -> str:
    """使用紧凑但足够核查的有效数字显示计算结果。"""

    return "{0:.8g}".format(float(value))


def _build_moving_load_report(results: Mapping[str, object]) -> str:
    """生成三维路面移动轮载专用报告，避免沿用二维静力描述。"""

    config = results["config"]
    model = config["model"]
    material = config["material"]
    analysis = config["analysis"]
    units = config["units"]
    displacement_location = results["maximum_displacement_location"]
    vertical_location = results["maximum_vertical_displacement_location"]
    stress_location = results["maximum_mises_stress_location"]
    speed_kmh = float(analysis["load_speed"]) * 3.6 / 1000.0

    return """# 三维路面单轮移动载荷教学分析报告

## 1. 计算概况

- 作业名称：`{job_name}`
- 模型名称：`{model_name}`
- 计算状态：已完成
- 结果生成时间：{generated_at}
- Abaqus Python：{abaqus_python_version}
- 用户子程序：`{user_subroutine}`
- 动力结果帧数：{frame_count}

## 2. 模型与材料

- 路面长度：{length} {length_unit}
- 路面宽度：{width} {length_unit}
- 路面深度：{depth} {length_unit}
- 材料：{material_name}
- 弹性模量：{youngs_modulus} {stress_unit}
- 泊松比：{poisson_ratio}
- 密度：{density} {mass_unit}/{length_unit}³
- 全局网格尺寸：{mesh_size} {length_unit}

## 3. 移动载荷与边界条件

- 接触压力：{load_pressure} {stress_unit}
- 接触区：{load_length} × {load_width} {length_unit}
- 移动速度：{load_speed} {length_unit}/{time_unit}（约 {speed_kmh} km/h）
- 横向中心坐标：{load_center_y} {length_unit}
- 载荷中心起点：{load_start_x} {length_unit}
- 分析时长：{time_period} {time_unit}
- 最大时间增量：{max_time_increment} {time_unit}
- 路面底面：约束三个方向的位移；
- 路面侧面：自由；
- 分析类型：三维线弹性、动力隐式分析。

## 4. 主要结果

- **全程最大位移模：{maximum_displacement} {length_unit}**
  - 时间：{u_time} {time_unit}；实例 `{u_instance}`，节点 {u_node}
- **全程最大竖向位移绝对值：{maximum_vertical_displacement} {length_unit}**
  - 带符号 U3：{vertical_signed_value} {length_unit}
  - 时间：{vertical_time} {time_unit}；实例 `{vertical_instance}`，节点 {vertical_node}
- **全程最大 Mises 应力：{maximum_mises_stress} {stress_unit}**
  - 时间：{s_time} {time_unit}；实例 `{s_instance}`，单元 {s_element}，积分点 {s_point}

## 5. 结果说明

本报告遍历动力分析的全部输出帧，而不是只读取最后一帧。DLOAD 根据时间和顶面积分点坐标移动矩形压力区。

本算例仅用于验证 Fortran 子程序、移动载荷和结果读取流程。单层线弹性材料、固定底面和教学轮载参数不能直接代表三级公路正式设计；工程使用前还需要依据项目标准确定路面结构层、轴载、轮胎接地、速度、不平度、边界距离、阻尼和材料模型。

> 本报告由 Abaqus Codex Assistant 自动生成。实际工程项目仍需由具备相应资质的工程师复核。
""".format(
        job_name=results["job_name"],
        model_name=results["model_name"],
        generated_at=results["generated_at"],
        abaqus_python_version=results["abaqus_python_version"],
        user_subroutine=results["user_subroutine"],
        frame_count=results["frame_count"],
        length=_number(model["length"]),
        width=_number(model["width"]),
        depth=_number(model["depth"]),
        length_unit=units["length"],
        material_name=material["name"],
        youngs_modulus=_number(material["youngs_modulus"]),
        stress_unit=units["stress"],
        poisson_ratio=_number(material["poisson_ratio"]),
        density=_number(material["density"]),
        mass_unit=units["mass"],
        mesh_size=_number(analysis["mesh_size"]),
        load_pressure=_number(analysis["load_pressure"]),
        load_length=_number(analysis["load_length"]),
        load_width=_number(analysis["load_width"]),
        load_speed=_number(analysis["load_speed"]),
        time_unit=units["time"],
        speed_kmh=_number(speed_kmh),
        load_center_y=_number(analysis["load_center_y"]),
        load_start_x=_number(analysis["load_start_x"]),
        time_period=_number(analysis["time_period"]),
        max_time_increment=_number(analysis["max_time_increment"]),
        maximum_displacement=_number(results["maximum_displacement"]),
        u_time=_number(displacement_location["frame_time"]),
        u_instance=displacement_location["instance"],
        u_node=displacement_location["node_label"],
        maximum_vertical_displacement=_number(
            results["maximum_vertical_displacement"]
        ),
        vertical_signed_value=_number(vertical_location["signed_value"]),
        vertical_time=_number(vertical_location["frame_time"]),
        vertical_instance=vertical_location["instance"],
        vertical_node=vertical_location["node_label"],
        maximum_mises_stress=_number(results["maximum_mises_stress"]),
        s_time=_number(stress_location["frame_time"]),
        s_instance=stress_location["instance"],
        s_element=stress_location["element_label"],
        s_point=stress_location["integration_point"],
    )


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
    if model_type == "moving_load_road":
        return _build_moving_load_report(results)
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
