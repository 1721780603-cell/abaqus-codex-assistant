# -*- coding: utf-8 -*-
"""根据结构化 Abaqus 结果生成简单中文 Markdown 报告。"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


def _number(value: object) -> str:
    """使用紧凑但足够核查的有效数字显示计算结果。"""

    return "{0:.8g}".format(float(value))


def build_chinese_report(results: Mapping[str, object]) -> str:
    """生成包含模型参数、边界条件和极值结果的中文报告文本。"""

    config = results["config"]
    model = config["model"]
    material = config["material"]
    analysis = config["analysis"]
    units = config["units"]
    displacement_location = results["maximum_displacement_location"]
    stress_location = results["maximum_mises_stress_location"]

    return """# 二维矩形板拉伸分析报告

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
- 材料：{material_name}
- 弹性模量：{youngs_modulus} {stress_unit}
- 泊松比：{poisson_ratio}
- 网格尺寸：{mesh_size} {length_unit}

## 3. 边界条件

- 左边界：约束水平方向位移；
- 左下角：约束竖直方向位移，用于消除刚体运动；
- 右边界：施加 {prescribed_displacement} {length_unit} 的水平拉伸位移；
- 分析类型：二维平面应力、线弹性、静力分析。

## 4. 主要结果

- **最大位移模：{maximum_displacement} {length_unit}**
  - 位置：实例 `{u_instance}`，节点 {u_node}
- **最大 Mises 应力：{maximum_mises_stress} {stress_unit}**
  - 位置：实例 `{s_instance}`，单元 {s_element}，积分点 {s_point}

## 5. 结果说明

本报告读取 ODB 最后一个分析帧，并在全模型范围内搜索位移模和 Mises 应力最大值。Abaqus 不内置单位制，本报告中的单位来自输入配置；使用结果前应核对材料参数、几何尺寸和载荷采用了同一套单位制。

> 本报告由 Abaqus Codex Assistant 自动生成。第一阶段结果仅用于示例与流程验证，实际工程项目仍需由具备相应资质的工程师复核。
""".format(
        job_name=results["job_name"],
        model_name=results["model_name"],
        generated_at=results["generated_at"],
        abaqus_python_version=results["abaqus_python_version"],
        length=_number(model["length"]),
        height=_number(model["height"]),
        thickness=_number(model["thickness"]),
        length_unit=units["length"],
        material_name=material["name"],
        youngs_modulus=_number(material["youngs_modulus"]),
        stress_unit=units["stress"],
        poisson_ratio=_number(material["poisson_ratio"]),
        mesh_size=_number(analysis["mesh_size"]),
        prescribed_displacement=_number(analysis["right_edge_displacement"]),
        maximum_displacement=_number(results["maximum_displacement"]),
        u_instance=displacement_location["instance"],
        u_node=displacement_location["node_label"],
        maximum_mises_stress=_number(results["maximum_mises_stress"]),
        s_instance=stress_location["instance"],
        s_element=stress_location["element_label"],
        s_point=stress_location["integration_point"],
    )


def write_chinese_report(path: Path, results: Mapping[str, object]) -> None:
    """把中文报告写入 UTF-8 Markdown 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_chinese_report(results), encoding="utf-8", newline="\n")
