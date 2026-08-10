# -*- coding: utf-8 -*-
"""在 Abaqus/CAE 2021 中建立并求解三维单轮移动载荷教学模型。"""

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
    C3D4,
    C3D6,
    C3D8R,
    DEFORMABLE_BODY,
    HEX,
    OFF,
    ON,
    STANDARD,
    STRUCTURED,
    THREE_D,
    USER_DEFINED,
)
# 无界面模式需要显式加载 CAE 功能模块，才能注册动力分析和输出接口。
from caeModules import *
from odbAccess import openOdb
import mesh
import regionToolset


def _input_paths():
    """读取配置、结果和本次运行专用的 Fortran 子程序路径。"""

    arguments = [value for value in sys.argv[1:] if value != "--"]
    if len(arguments) < 3:
        raise RuntimeError("需要提供配置、结果和 Fortran 子程序路径。")
    return (
        os.path.abspath(arguments[-3]),
        os.path.abspath(arguments[-2]),
        os.path.abspath(arguments[-1]),
    )


def _load_config(path):
    """读取已由主程序校验过的 JSON 配置。"""

    with open(path, "rb") as stream:
        return _byteify(json.load(stream))


def _byteify(value):
    """把 Python 2 JSON 产生的 unicode 递归转换为 Abaqus 可接受的字符串。"""

    if isinstance(value, unicode):
        return value.encode("utf-8")
    if isinstance(value, list):
        return [_byteify(item) for item in value]
    if isinstance(value, dict):
        return dict(
            (_byteify(key), _byteify(item)) for key, item in value.items()
        )
    return value


def _write_result(path, data):
    """用 UTF-8 JSON 保存动力结果，供现代 Python 生成中文报告。"""

    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as stream:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if isinstance(text, unicode):
            text = text.encode("utf-8")
        stream.write(text)
        stream.write("\n")


def _build_model(config):
    """建立单层三维路面、动力分析步、固定底面和用户定义压力。"""

    model_config = config["model"]
    material_config = config["material"]
    analysis_config = config["analysis"]

    model_name = model_config["name"]
    length = float(model_config["length"])
    width = float(model_config["width"])
    depth = float(model_config["depth"])
    tolerance = max(length, width, depth) * 1.0e-6

    if model_name in mdb.models.keys():
        del mdb.models[model_name]
    model = mdb.Model(name=model_name)

    # 草图位于 X-Y 平面，沿 Z 正方向拉伸；车辆沿 X 正方向移动。
    sketch = model.ConstrainedSketch(
        name="road_plan", sheetSize=max(length, width) * 2.0
    )
    sketch.rectangle(point1=(0.0, 0.0), point2=(length, width))
    part = model.Part(name="Road", dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=depth)
    del model.sketches["road_plan"]

    # 动力分析必须提供密度；默认示例采用 mm-MPa-s-tonne 一致单位制。
    material = model.Material(name=material_config["name"])
    material.Elastic(
        table=((
            float(material_config["youngs_modulus"]),
            float(material_config["poisson_ratio"]),
        ),)
    )
    material.Density(table=((float(material_config["density"]),),))
    section_name = "RoadSection"
    model.HomogeneousSolidSection(
        name=section_name,
        material=material_config["name"],
    )
    part.SectionAssignment(
        region=regionToolset.Region(cells=part.cells), sectionName=section_name
    )

    # 规则长方体优先使用结构化六面体网格，便于观察轮载沿网格移动。
    element_hex = mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD)
    element_wedge = mesh.ElemType(elemCode=C3D6, elemLibrary=STANDARD)
    element_tet = mesh.ElemType(elemCode=C3D4, elemLibrary=STANDARD)
    part.setMeshControls(regions=part.cells, elemShape=HEX, technique=STRUCTURED)
    part.setElementType(
        regions=(part.cells,),
        elemTypes=(element_hex, element_wedge, element_tet),
    )
    part.seedPart(
        size=float(analysis_config["mesh_size"]),
        deviationFactor=0.1,
        minSizeFactor=0.1,
    )
    part.generateMesh()

    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    instance = assembly.Instance(name="Road-1", part=part, dependent=ON)

    max_increment = float(analysis_config["max_time_increment"])
    model.ImplicitDynamicsStep(
        name=analysis_config["step_name"],
        previous="Initial",
        timePeriod=float(analysis_config["time_period"]),
        maxNumInc=10000,
        initialInc=max_increment,
        minInc=max_increment / 1000.0,
        maxInc=max_increment,
    )
    model.FieldOutputRequest(
        name="OutputForReport",
        createStepName=analysis_config["step_name"],
        variables=("S", "U"),
        frequency=1,
    )

    bottom_faces = instance.faces.getByBoundingBox(
        xMin=-tolerance,
        xMax=length + tolerance,
        yMin=-tolerance,
        yMax=width + tolerance,
        zMin=-tolerance,
        zMax=tolerance,
    )
    top_faces = instance.faces.getByBoundingBox(
        xMin=-tolerance,
        xMax=length + tolerance,
        yMin=-tolerance,
        yMax=width + tolerance,
        zMin=depth - tolerance,
        zMax=depth + tolerance,
    )
    if len(bottom_faces) == 0 or len(top_faces) == 0:
        raise RuntimeError("没有正确找到路面顶面或底面，请检查三维几何参数。")

    # 第一版固定底面，侧面保持自由；后续分层路面会再讨论边界距离和反射。
    model.EncastreBC(
        name="FixedBottom",
        createStepName="Initial",
        region=regionToolset.Region(faces=bottom_faces),
    )

    # USER_DEFINED 让 Abaqus 在顶面各积分点调用 DLOAD 计算当前压力。
    top_surface = assembly.Surface(name="RoadTop", side1Faces=top_faces)
    model.Pressure(
        name="MovingWheelPressure",
        createStepName=analysis_config["step_name"],
        region=top_surface,
        distributionType=USER_DEFINED,
        magnitude=1.0,
    )

    return model_name, instance.name


def _run_job(config, model_name, user_subroutine_path):
    """编译 DLOAD、提交 Abaqus/Standard 作业并等待结束。"""

    if not os.path.isfile(user_subroutine_path):
        raise RuntimeError("没有找到本次运行的 Fortran 子程序。")

    analysis_config = config["analysis"]
    job_name = analysis_config["job_name"]
    job = mdb.Job(
        name=job_name,
        model=model_name,
        numCpus=int(analysis_config["num_cpus"]),
        userSubroutine=os.path.abspath(user_subroutine_path),
    )

    # 保存 CAE 文件，便于初学者查看三维网格和 USER_DEFINED 载荷。
    mdb.saveAs(pathName=os.path.abspath(model_name + ".cae"))
    job.submit(consistencyChecking=OFF)
    job.waitForCompletion()
    odb_path = os.path.abspath(job_name + ".odb")
    status_path = os.path.abspath(job_name + ".sta")

    status_text = ""
    if os.path.isfile(status_path):
        with open(status_path, "rb") as stream:
            status_text = stream.read()
    completed_marker = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
    if not os.path.isfile(odb_path) or completed_marker not in status_text:
        raise RuntimeError(
            "Abaqus 移动载荷作业没有正常完成，状态：{0}".format(job.status)
        )
    return job_name, odb_path


def _read_results(config, instance_name, odb_path):
    """遍历全部动力帧，寻找全程最大位移、竖向位移和 Mises 应力。"""

    step_name = config["analysis"]["step_name"]
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        if step_name not in odb.steps.keys():
            raise RuntimeError("ODB 中没有找到动力分析步：{0}".format(step_name))
        frames = odb.steps[step_name].frames

        max_displacement = None
        max_displacement_location = None
        max_vertical_displacement = None
        max_vertical_location = None
        max_mises = None
        max_mises_location = None
        node_value_count = 0
        stress_value_count = 0

        for frame in frames:
            if "U" in frame.fieldOutputs.keys():
                displacement_field = frame.fieldOutputs["U"]
                node_value_count += len(displacement_field.values)
                for value in displacement_field.values:
                    squared_magnitude = 0.0
                    for component in value.data:
                        squared_magnitude += float(component) ** 2
                    magnitude = math.sqrt(squared_magnitude)
                    if max_displacement is None or magnitude > max_displacement:
                        max_displacement = magnitude
                        max_displacement_location = {
                            "instance": value.instance.name,
                            "node_label": int(value.nodeLabel),
                            "frame_time": float(frame.frameValue),
                        }

                    vertical_value = float(value.data[2])
                    vertical_magnitude = abs(vertical_value)
                    if (
                        max_vertical_displacement is None
                        or vertical_magnitude > max_vertical_displacement
                    ):
                        max_vertical_displacement = vertical_magnitude
                        max_vertical_location = {
                            "instance": value.instance.name,
                            "node_label": int(value.nodeLabel),
                            "frame_time": float(frame.frameValue),
                            "signed_value": vertical_value,
                        }

            if "S" in frame.fieldOutputs.keys():
                stress_field = frame.fieldOutputs["S"]
                stress_value_count += len(stress_field.values)
                for value in stress_field.values:
                    mises = float(value.mises)
                    if max_mises is None or mises > max_mises:
                        max_mises = mises
                        max_mises_location = {
                            "instance": value.instance.name,
                            "element_label": int(value.elementLabel),
                            "integration_point": int(
                                getattr(value, "integrationPoint", 0)
                            ),
                            "frame_time": float(frame.frameValue),
                        }

        if (
            max_displacement is None
            or max_vertical_displacement is None
            or max_mises is None
        ):
            raise RuntimeError("ODB 中没有可用的动力位移或应力结果。")

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
            "frame_time": float(frames[-1].frameValue),
            "frame_count": len(frames),
            "odb_path": odb_path,
            "maximum_displacement": float(max_displacement),
            "maximum_displacement_location": max_displacement_location,
            "maximum_vertical_displacement": float(max_vertical_displacement),
            "maximum_vertical_displacement_location": max_vertical_location,
            "maximum_mises_stress": float(max_mises),
            "maximum_mises_stress_location": max_mises_location,
            "node_value_count": node_value_count,
            "stress_value_count": stress_value_count,
            "user_subroutine": os.path.basename("moving_pressure_dload.for"),
        }
    finally:
        odb.close()


def main():
    """执行三维移动轮载流程，并把异常返回给外层程序。"""

    config_path, result_path, user_subroutine_path = _input_paths()
    config = _load_config(config_path)
    model_name, instance_name = _build_model(config)
    job_name, odb_path = _run_job(config, model_name, user_subroutine_path)
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
