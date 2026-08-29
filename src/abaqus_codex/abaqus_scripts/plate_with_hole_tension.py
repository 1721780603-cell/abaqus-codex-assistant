# -*- coding: utf-8 -*-
"""在 Abaqus/CAE 中建立、求解并读取二维中心圆孔板拉伸模型。"""

from __future__ import print_function

import datetime as _datetime
import json
import math
import os
import sys
import traceback

from abaqus import mdb
from abaqusConstants import (
    CARTESIAN,
    CPS3,
    CPS4R,
    DEFORMABLE_BODY,
    FINER,
    OFF,
    ON,
    STANDARD,
    TWO_D_PLANAR,
    UNSET,
)
# 无界面模式需要显式加载 CAE 功能模块，才能注册输出请求等接口。
from caeModules import *
from odbAccess import openOdb
import mesh
import regionToolset


# Abaqus 2021 使用 Python 2，Abaqus 2024 及更新版本使用 Python 3。
try:
    _TEXT_TYPE = unicode
except NameError:
    _TEXT_TYPE = str


def _input_paths():
    """读取 abqpy 放在双横线之后的配置和结果路径。"""

    arguments = [value for value in sys.argv[1:] if value != "--"]
    if len(arguments) < 2:
        raise RuntimeError("需要提供配置文件和结果文件路径。")
    return os.path.abspath(arguments[-2]), os.path.abspath(arguments[-1])


def _load_config(path):
    """读取已由主程序校验过的 JSON 配置。"""

    with open(path, "rb") as stream:
        return _byteify(json.load(stream))


def _byteify(value):
    """仅在 Python 2 中把 JSON unicode 转为 Abaqus 接口需要的字节串。"""

    if sys.version_info[0] < 3 and isinstance(value, _TEXT_TYPE):
        return value.encode("utf-8")
    if isinstance(value, list):
        return [_byteify(item) for item in value]
    if isinstance(value, dict):
        return dict(
            (_byteify(key), _byteify(item)) for key, item in value.items()
        )
    return value


def _write_result(path, data):
    """用 UTF-8 JSON 保存结果，供现代 Python 生成中文报告。"""

    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as stream:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if not isinstance(text, bytes):
            text = text.encode("utf-8")
        stream.write(text)
        stream.write(b"\n")


def _build_model(config):
    """按照配置建立平面应力圆孔板、材料、边界条件和网格。"""

    model_config = config["model"]
    material_config = config["material"]
    analysis_config = config["analysis"]

    model_name = model_config["name"]
    length = float(model_config["length"])
    height = float(model_config["height"])
    thickness = float(model_config["thickness"])
    hole_radius = float(model_config["hole_radius"])
    center_x = length / 2.0
    center_y = height / 2.0
    tolerance = max(length, height) * 1.0e-6

    if model_name in mdb.models.keys():
        del mdb.models[model_name]
    model = mdb.Model(name=model_name)

    # 一个草图同时包含外矩形和内圆，BaseShell 会把内圆识别为通孔。
    sketch = model.ConstrainedSketch(
        name="plate_with_hole_profile", sheetSize=max(length, height) * 2.0
    )
    sketch.rectangle(point1=(0.0, 0.0), point2=(length, height))
    sketch.CircleByCenterPerimeter(
        center=(center_x, center_y),
        point1=(center_x + hole_radius, center_y),
    )
    part = model.Part(
        name="Plate", dimensionality=TWO_D_PLANAR, type=DEFORMABLE_BODY
    )
    part.BaseShell(sketch=sketch)
    del model.sketches["plate_with_hole_profile"]

    # Abaqus 不预设单位；材料数值必须和几何、位移采用同一套单位制。
    material = model.Material(name=material_config["name"])
    material.Elastic(
        table=((
            float(material_config["youngs_modulus"]),
            float(material_config["poisson_ratio"]),
        ),)
    )
    section_name = "PlateSection"
    model.HomogeneousSolidSection(
        name=section_name,
        material=material_config["name"],
        thickness=thickness,
    )
    part.SectionAssignment(
        region=regionToolset.Region(faces=part.faces), sectionName=section_name
    )

    # 全板使用普通网格，孔边单独细化以更好捕捉应力集中。
    element_quad = mesh.ElemType(elemCode=CPS4R, elemLibrary=STANDARD)
    element_tri = mesh.ElemType(elemCode=CPS3, elemLibrary=STANDARD)
    part.setElementType(
        regions=(part.faces,), elemTypes=(element_quad, element_tri)
    )
    part.seedPart(
        size=float(analysis_config["mesh_size"]),
        deviationFactor=0.1,
        minSizeFactor=0.1,
    )
    hole_edges = part.edges.getByBoundingBox(
        xMin=center_x - hole_radius - tolerance,
        xMax=center_x + hole_radius + tolerance,
        yMin=center_y - hole_radius - tolerance,
        yMax=center_y + hole_radius + tolerance,
    )
    if len(hole_edges) == 0:
        raise RuntimeError("没有正确找到圆孔边界，请检查孔径参数。")
    part.seedEdgeBySize(
        edges=hole_edges,
        size=float(analysis_config["hole_mesh_size"]),
        deviationFactor=0.1,
        constraint=FINER,
    )
    part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Plate-1", part=part, dependent=ON)

    model.StaticStep(name=analysis_config["step_name"], previous="Initial")
    # 显式请求应力和位移，避免依赖不同 Abaqus 版本的默认输出。
    model.FieldOutputRequest(
        name="OutputForReport",
        createStepName=analysis_config["step_name"],
        variables=("S", "U"),
    )

    # 只选择外部左右直边；中心圆孔不会落入这些包围盒。
    left_edges = instance.edges.getByBoundingBox(
        xMin=-tolerance,
        xMax=tolerance,
        yMin=-tolerance,
        yMax=height + tolerance,
    )
    right_edges = instance.edges.getByBoundingBox(
        xMin=length - tolerance,
        xMax=length + tolerance,
        yMin=-tolerance,
        yMax=height + tolerance,
    )
    anchor_vertices = instance.vertices.getByBoundingBox(
        xMin=-tolerance,
        xMax=tolerance,
        yMin=-tolerance,
        yMax=tolerance,
    )
    if len(left_edges) == 0 or len(right_edges) == 0 or len(anchor_vertices) == 0:
        raise RuntimeError("没有正确找到圆孔板外边界，请检查几何参数。")

    # 左边只固定水平位移，允许板在竖直方向发生泊松收缩。
    model.DisplacementBC(
        name="LeftHorizontalFix",
        createStepName="Initial",
        region=regionToolset.Region(edges=left_edges),
        u1=0.0,
        u2=UNSET,
    )
    # 左下角固定竖直位移，用最少约束消除整体刚体运动。
    model.DisplacementBC(
        name="AnchorVerticalFix",
        createStepName="Initial",
        region=regionToolset.Region(vertices=anchor_vertices),
        u1=UNSET,
        u2=0.0,
    )
    model.DisplacementBC(
        name="RightTension",
        createStepName=analysis_config["step_name"],
        region=regionToolset.Region(edges=right_edges),
        u1=float(analysis_config["right_edge_displacement"]),
        u2=UNSET,
    )

    return model_name, instance.name


def _run_job(config, model_name):
    """提交 Abaqus/Standard 作业并等待结束。"""

    analysis_config = config["analysis"]
    job_name = analysis_config["job_name"]
    job = mdb.Job(
        name=job_name,
        model=model_name,
        numCpus=int(analysis_config["num_cpus"]),
    )

    # 保存 CAE 文件便于初学者在图形界面中复查圆孔和边界条件。
    mdb.saveAs(pathName=os.path.abspath(model_name + ".cae"))
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    odb_path = os.path.abspath(job_name + ".odb")
    status_path = os.path.abspath(job_name + ".sta")

    # 部分 Abaqus 2021 环境在完成后仍返回空 job.status，因此核对实际文件。
    status_text = ""
    if os.path.isfile(status_path):
        with open(status_path, "rb") as stream:
            status_text = stream.read()
    completed_marker = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
    if not os.path.isfile(odb_path) or completed_marker not in status_text:
        raise RuntimeError(
            "Abaqus 作业没有正常完成，状态：{0}".format(job.status)
        )
    return job_name, odb_path


def _read_results(config, instance_name, odb_path):
    """读取最后一帧，并寻找最大位移模和最大 Mises 应力。"""

    step_name = config["analysis"]["step_name"]
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        if step_name not in odb.steps.keys():
            raise RuntimeError("ODB 中没有找到分析步：{0}".format(step_name))
        frame = odb.steps[step_name].frames[-1]
        displacement_field = frame.fieldOutputs["U"]
        stress_field = frame.fieldOutputs["S"]

        max_displacement = None
        max_displacement_location = None
        for value in displacement_field.values:
            # caeModules 中存在同名 sum，因此显式循环计算位移模。
            squared_magnitude = 0.0
            for component in value.data:
                squared_magnitude += float(component) ** 2
            magnitude = math.sqrt(squared_magnitude)
            if max_displacement is None or magnitude > max_displacement:
                max_displacement = magnitude
                max_displacement_location = {
                    "instance": value.instance.name,
                    "node_label": int(value.nodeLabel),
                }

        max_mises = None
        max_mises_location = None
        for value in stress_field.values:
            mises = float(value.mises)
            if max_mises is None or mises > max_mises:
                max_mises = mises
                max_mises_location = {
                    "instance": value.instance.name,
                    "element_label": int(value.elementLabel),
                    "integration_point": int(getattr(value, "integrationPoint", 0)),
                }

        if max_displacement is None or max_mises is None:
            raise RuntimeError("ODB 中没有可用的位移或应力结果。")

        return {
            "status": "completed",
            "generated_at": _datetime.datetime.utcnow().strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "abaqus_python_version": sys.version.split()[0],
            "job_name": config["analysis"]["job_name"],
            "model_name": config["model"]["name"],
            "instance_name": instance_name,
            "step_name": step_name,
            "frame_time": float(frame.frameValue),
            "odb_path": odb_path,
            "maximum_displacement": float(max_displacement),
            "maximum_displacement_location": max_displacement_location,
            "maximum_mises_stress": float(max_mises),
            "maximum_mises_stress_location": max_mises_location,
            "node_value_count": len(displacement_field.values),
            "stress_value_count": len(stress_field.values),
        }
    finally:
        odb.close()


def main():
    """执行完整 Abaqus 端流程，并把异常返回给外层程序。"""

    config_path, result_path = _input_paths()
    config = _load_config(config_path)
    model_name, instance_name = _build_model(config)
    job_name, odb_path = _run_job(config, model_name)
    result = _read_results(config, instance_name, odb_path)
    result["job_name"] = job_name
    result["config"] = config
    _write_result(result_path, result)
    print("ABAQUS_CODEX_RESULT={0}".format(result_path))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
