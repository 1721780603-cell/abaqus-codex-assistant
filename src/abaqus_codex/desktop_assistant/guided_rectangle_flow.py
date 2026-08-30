# -*- coding: utf-8 -*-
"""矩形板拉伸第 2 到 10 步的离线中文向导。"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional

from abaqus_codex.assistant_protocol import seal_action_plan, validate_action_plan


STAGE_MATERIAL = "material"
STAGE_SECTION = "section"
STAGE_ASSEMBLY = "assembly"
STAGE_STEP = "step"
STAGE_INTERACTION = "interaction"
STAGE_BCS = "bcs"
STAGE_MESH = "mesh"
STAGE_JOB = "job"
STAGE_RESULTS = "results"

STAGE_NUMBERS = {
    STAGE_MATERIAL: 2,
    STAGE_SECTION: 3,
    STAGE_ASSEMBLY: 4,
    STAGE_STEP: 5,
    STAGE_INTERACTION: 6,
    STAGE_BCS: 7,
    STAGE_MESH: 8,
    STAGE_JOB: 9,
    STAGE_RESULTS: 10,
}

NAME_PATTERN = re.compile(r'^[^\\/:*?"<>|\x00-\x1f\x7f]{1,80}$')
NUMBER = r"[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"

MATERIAL_PATTERN = re.compile(
    r"^为\s*(?P<model>[^，,\s]+)\s*创建材料\s*(?P<material>[^，,\s]+)[，,\s]*"
    r"弹性模量\s*(?P<youngs>" + NUMBER + r")\s*MPa[，,\s]*"
    r"泊松比\s*(?P<poisson>" + NUMBER + r")[。\s]*$"
)
SECTION_PATTERN = re.compile(
    r"^为\s*(?P<model>[^，,\s]+)\s*的零件\s*(?P<part>[^，,\s]+)\s*"
    r"创建截面\s*(?P<section>[^，,\s]+)[，,\s]*材料\s*(?P<material>[^，,\s]+)"
    r"[，,\s]*厚度\s*(?P<thickness>" + NUMBER + r")\s*mm[。\s]*$"
)
ASSEMBLY_PATTERN = re.compile(
    r"^在\s*(?P<model>[^，,\s]+)\s*中装配零件\s*(?P<part>[^，,\s]+)"
    r"[，,\s]*实例名\s*(?P<instance>[^，,\s。]+)[。\s]*$"
)
STEP_PATTERN = re.compile(
    r"^在\s*(?P<model>[^，,\s]+)\s*中创建静力分析步\s*"
    r"(?P<step>[^，,\s。]+)[。\s]*$"
)
INTERACTION_PATTERN = re.compile(
    r"^确认\s*(?P<model>[^，,\s]+)\s*的矩形板拉伸不需要相互作用[。\s]*$"
)
BC_PATTERN = re.compile(
    r"^为\s*(?P<model>[^，,\s]+)\s*的实例\s*(?P<instance>[^，,\s]+)\s*"
    r"设置拉伸边界[，,\s]*分析步\s*(?P<step>[^，,\s]+)[，,\s]*"
    r"右边位移\s*(?P<displacement>" + NUMBER + r")\s*mm[。\s]*$"
)
MESH_PATTERN = re.compile(
    r"^为\s*(?P<model>[^，,\s]+)\s*的零件\s*(?P<part>[^，,\s]+)\s*"
    r"设置\s*(?P<size>" + NUMBER + r")\s*mm\s*网格并划分[。\s]*$"
)
JOB_PATTERN = re.compile(
    r"^为\s*(?P<model>[^，,\s]+)\s*创建并提交\s*Job\s*"
    r"(?P<job>[^，,\s]+)[，,\s]*使用\s*(?P<cpus>[0-9]+)\s*个\s*CPU[。\s]*$",
    re.IGNORECASE,
)
RESULTS_PATTERN = re.compile(
    r"^读取\s*Job\s*(?P<job>[^，,\s]+)\s*的最大位移和最大\s*Mises\s*应力"
    r"并生成中文报告[。\s]*$",
    re.IGNORECASE,
)


DEFAULT_COMMANDS = {
    STAGE_MATERIAL: (
        "为 Model-1 创建材料 Steel，弹性模量 210000 MPa，泊松比 0.3"
    ),
    STAGE_SECTION: (
        "为 Model-1 的零件 Plate 创建截面 PlateSection，材料 Steel，厚度 1 mm"
    ),
    STAGE_ASSEMBLY: "在 Model-1 中装配零件 Plate，实例名 Plate-1",
    STAGE_STEP: "在 Model-1 中创建静力分析步 TensionStep",
    STAGE_INTERACTION: "确认 Model-1 的矩形板拉伸不需要相互作用",
    STAGE_BCS: (
        "为 Model-1 的实例 Plate-1 设置拉伸边界，分析步 TensionStep，"
        "右边位移 0.1 mm"
    ),
    STAGE_MESH: "为 Model-1 的零件 Plate 设置 2 mm 网格并划分",
    STAGE_JOB: (
        "为 Model-1 创建并提交 Job rectangle_tension_2d，使用 1 个 CPU"
    ),
    STAGE_RESULTS: (
        "读取 Job rectangle_tension_2d 的最大位移和最大 Mises 应力并生成中文报告"
    ),
}

NEXT_STAGE = {
    STAGE_MATERIAL: STAGE_SECTION,
    STAGE_SECTION: STAGE_ASSEMBLY,
    STAGE_ASSEMBLY: STAGE_STEP,
    STAGE_STEP: STAGE_INTERACTION,
    STAGE_INTERACTION: STAGE_BCS,
    STAGE_BCS: STAGE_MESH,
    STAGE_MESH: STAGE_JOB,
    STAGE_JOB: STAGE_RESULTS,
}


class GuidedCommandError(ValueError):
    """表示向导命令与固定句式或安全范围不符。"""


@dataclass(frozen=True)
class GuidedStageRequest:
    """一个经过固定规则解析的向导步骤请求。"""

    stage: str
    model_name: str
    values: Mapping[str, object]


def _name(value: str, label: str) -> str:
    """校验对象名，防止把路径或控制字符送入 Abaqus。"""

    name = value.strip()
    if name != value or NAME_PATTERN.fullmatch(name) is None:
        raise GuidedCommandError(
            "{0}不能为空、不能超过 80 字符，也不能包含路径字符。".format(label)
        )
    return name


def _number(
    value: str,
    label: str,
    *,
    minimum: float,
    maximum: float,
    exclude_minimum: bool = False,
) -> float:
    """读取有限数值并按可信边界限制。"""

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise GuidedCommandError("{0}不是有效数值。".format(label)) from error
    if not math.isfinite(result):
        raise GuidedCommandError("{0}必须是有限数值。".format(label))
    if result < minimum or (exclude_minimum and result == minimum) or result > maximum:
        raise GuidedCommandError(
            "{0}必须在安全范围内。".format(label)
        )
    return result


def _request(stage: str, match: re.Match[str]) -> GuidedStageRequest:
    """把一个已匹配句式转换为严格的步骤参数。"""

    data = match.groupdict()
    model = _name(data.get("model", "Model-1"), "模型名")
    values: dict[str, object] = {}
    for field, label in (
        ("material", "材料名"),
        ("part", "零件名"),
        ("section", "截面名"),
        ("instance", "实例名"),
        ("step", "分析步名"),
        ("job", "Job 名"),
    ):
        if data.get(field) is not None:
            values[field] = _name(str(data[field]), label)
    if data.get("youngs") is not None:
        values["youngs_modulus"] = _number(
            data["youngs"], "弹性模量", minimum=0.0, maximum=1.0e12,
            exclude_minimum=True,
        )
        poisson = _number(
            data["poisson"], "泊松比", minimum=-1.0, maximum=0.5
        )
        if poisson in (-1.0, 0.5):
            raise GuidedCommandError("泊松比必须大于 -1 且小于 0.5。")
        values["poisson_ratio"] = poisson
    if data.get("thickness") is not None:
        values["thickness"] = _number(
            data["thickness"], "厚度", minimum=0.0, maximum=1.0e9,
            exclude_minimum=True,
        )
    if data.get("displacement") is not None:
        displacement = _number(
            data["displacement"], "右边位移", minimum=-1.0e9, maximum=1.0e9
        )
        if displacement == 0.0:
            raise GuidedCommandError("右边位移不能为 0。")
        values["right_displacement"] = displacement
    if data.get("size") is not None:
        values["mesh_size"] = _number(
            data["size"], "网格尺寸", minimum=0.0, maximum=1.0e9,
            exclude_minimum=True,
        )
    if data.get("cpus") is not None:
        cpus = int(data["cpus"])
        if cpus < 1 or cpus > 64:
            raise GuidedCommandError("CPU 数量必须在 1 到 64 之间。")
        values["num_cpus"] = cpus
    return GuidedStageRequest(stage=stage, model_name=model, values=values)


def parse_guided_command(value: object) -> Optional[GuidedStageRequest]:
    """按顺序识别第 2 到 10 步；不属于向导的命令返回 None。"""

    text = " ".join(str(value).split())
    patterns = (
        (STAGE_MATERIAL, MATERIAL_PATTERN),
        (STAGE_SECTION, SECTION_PATTERN),
        (STAGE_ASSEMBLY, ASSEMBLY_PATTERN),
        (STAGE_STEP, STEP_PATTERN),
        (STAGE_INTERACTION, INTERACTION_PATTERN),
        (STAGE_BCS, BC_PATTERN),
        (STAGE_MESH, MESH_PATTERN),
        (STAGE_JOB, JOB_PATTERN),
        (STAGE_RESULTS, RESULTS_PATTERN),
    )
    for stage, pattern in patterns:
        match = pattern.fullmatch(text)
        if match is not None:
            return _request(stage, match)
    trigger_words = (
        "创建材料", "创建截面", "装配零件", "静力分析步",
        "不需要相互作用", "设置拉伸边界", "网格并划分",
        "创建并提交 Job", "最大 Mises 应力并生成中文报告",
    )
    if any(word in text for word in trigger_words):
        raise GuidedCommandError(
            "这条向导命令不完整。请使用界面自动填入的当前步骤示例句式。"
        )
    return None


def _fingerprint(value: str) -> str:
    """把摘要中的裸哈希转换为动作协议指纹。"""

    result = str(value).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", result):
        result = "sha256:" + result
    if re.fullmatch(r"sha256:[0-9a-f]{64}", result) is None:
        raise GuidedCommandError("当前模型摘要指纹无效，请重新刷新模型。")
    return result


def _action_for_request(
    request: GuidedStageRequest, token: str
) -> dict[str, object]:
    """把一个步骤请求限制为一个白名单 Action。"""

    model = request.model_name
    values = request.values
    common = {
        "id": "guided-" + token[:20],
        "warnings": [],
    }
    if request.stage == STAGE_MATERIAL:
        return dict(common, **{
            "type": "set_material_elastic",
            "target": {"model": model, "material": values["material"]},
            "before": None,
            "after": {
                "youngs_modulus": values["youngs_modulus"],
                "poisson_ratio": values["poisson_ratio"],
                "stress_unit": "MPa",
            },
            "risk": "low",
        })
    if request.stage == STAGE_SECTION:
        return dict(common, **{
            "type": "create_section_assignment",
            "target": {
                "model": model,
                "part": values["part"],
                "section": values["section"],
                "material": values["material"],
            },
            "before": None,
            "after": {
                "thickness": values["thickness"],
                "length_unit": "mm",
                "section_type": "HOMOGENEOUS_SOLID",
                "region": "ALL_FACES",
            },
            "risk": "medium",
        })
    if request.stage == STAGE_ASSEMBLY:
        return dict(common, **{
            "type": "create_instance",
            "target": {
                "model": model,
                "part": values["part"],
                "instance": values["instance"],
            },
            "before": None,
            "after": {"dependent": True, "coordinate_system": "CARTESIAN"},
            "risk": "medium",
        })
    if request.stage == STAGE_STEP:
        return dict(common, **{
            "type": "create_static_step",
            "target": {"model": model, "step": values["step"]},
            "before": None,
            "after": {"previous_step": "Initial", "time_period": 1.0, "nlgeom": False},
            "risk": "medium",
        })
    if request.stage == STAGE_BCS:
        return dict(common, **{
            "type": "configure_rectangle_tension_bcs",
            "target": {
                "model": model,
                "instance": values["instance"],
                "step": values["step"],
            },
            "before": None,
            "after": {
                "right_displacement": values["right_displacement"],
                "length_unit": "mm",
                "selection_strategy": "RECTANGLE_BOUNDING_BOX",
                "bc_names": {
                    "left_horizontal": "LeftHorizontalFix",
                    "anchor_vertical": "AnchorVerticalFix",
                    "right_tension": "RightTension",
                },
            },
            "risk": "medium",
        })
    if request.stage == STAGE_MESH:
        return dict(common, **{
            "type": "set_mesh_size",
            "target": {"model": model, "part": values["part"]},
            "before": {"seed_size": None, "has_mesh": False},
            "after": {"size": values["mesh_size"], "length_unit": "mm"},
            "risk": "medium",
        })
    if request.stage == STAGE_JOB:
        return dict(common, **{
            "type": "create_submit_job",
            "target": {"model": model, "job": values["job"]},
            "before": {"job_exists": False},
            "after": {
                "num_cpus": values["num_cpus"],
                "submit": True,
                "consistency_checking": True,
                "wait": False,
                "auto_retry": False,
            },
            "risk": "high",
            "warnings": ["提交 Job 会占用 Abaqus 许可证和本机计算资源。"],
        })
    if request.stage == STAGE_RESULTS:
        return dict(common, **{
            "type": "read_job_results_report",
            "target": {"model": model, "job": values["job"]},
            "before": None,
            "after": {
                "odb_source": "CURRENT_CAE_JOB_DIRECTORY",
                "report_format": "markdown",
                "report_language": "zh-CN",
                "overwrite": False,
            },
            "risk": "medium",
            "warnings": [
                "只有 Job 成功完成并生成 ODB 后才能读取结果。",
                "报告只总结数值，不自动判断模型是否符合工程规范。",
            ],
        })
    raise GuidedCommandError("这个步骤不产生写计划。")


def build_guided_plan(
    request: GuidedStageRequest,
    *,
    snapshot_fingerprint: str,
    now: Optional[datetime] = None,
    id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> dict[str, object]:
    """为第 2–9 步中的一个写步骤生成十分钟有效计划。"""

    if request.stage == STAGE_INTERACTION:
        raise GuidedCommandError("当前步骤不需要写计划。")
    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        raise GuidedCommandError("计划时间必须包含时区。")
    token = id_factory()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", token) is None:
        raise GuidedCommandError("计划随机标识格式无效。")
    to_utc = lambda value: value.astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    action = _action_for_request(request, token)
    plan = {
        "schema_version": "abaqus.action.v1",
        "abaqus_release": "2021",
        "plan_id": "plan-" + token[:24],
        "created_at": to_utc(created_at),
        "expires_at": to_utc(created_at + timedelta(minutes=10)),
        "model_name": request.model_name,
        "model_fingerprint": _fingerprint(snapshot_fingerprint),
        "unit_system": "mm-N-s-MPa",
        "actions": [action],
        "warnings": [
            "本步骤只执行计划中显示的一个固定动作。",
            "应用时先创建新的 CAE 工作副本，原文件不会被覆盖。",
        ],
        "requires_backup": request.stage != STAGE_RESULTS,
        "requires_job_confirmation": request.stage == STAGE_JOB,
    }
    return validate_action_plan(seal_action_plan(plan), now=created_at)


def format_guided_plan(plan: Mapping[str, object], stage: str) -> str:
    """把一个步骤计划转换成初学者可审阅的中文摘要。"""

    checked = validate_action_plan(plan)
    action = checked["actions"][0]
    target = action["target"]
    after = action["after"]
    number = STAGE_NUMBERS[stage]
    lines = [
        "【教学路线：二维矩形板拉伸】",
        "当前步骤：{0}/10".format(number),
        "状态：计划已生成，尚未执行",
        "模型：{0}".format(checked["model_name"]),
        "",
    ]
    if stage == STAGE_MATERIAL:
        lines.extend([
            "创建材料：{0}".format(target["material"]),
            "弹性模量：{0:g} MPa".format(after["youngs_modulus"]),
            "泊松比：{0:g}".format(after["poisson_ratio"]),
        ])
    elif stage == STAGE_SECTION:
        lines.extend([
            "零件：{0}".format(target["part"]),
            "截面：{0}".format(target["section"]),
            "材料：{0}".format(target["material"]),
            "平面应力厚度：{0:g} mm".format(after["thickness"]),
        ])
    elif stage == STAGE_ASSEMBLY:
        lines.extend([
            "装配零件：{0}".format(target["part"]),
            "创建依赖实例：{0}".format(target["instance"]),
        ])
    elif stage == STAGE_STEP:
        lines.extend([
            "创建静力分析步：{0}".format(target["step"]),
            "前一步：Initial",
            "几何非线性：关闭",
        ])
    elif stage == STAGE_BCS:
        lines.extend([
            "实例：{0}".format(target["instance"]),
            "分析步：{0}".format(target["step"]),
            "左边水平约束 + 左下角竖直锚定",
            "右边水平位移：{0:g} mm".format(after["right_displacement"]),
        ])
    elif stage == STAGE_MESH:
        lines.extend([
            "零件：{0}".format(target["part"]),
            "全局网格尺寸：{0:g} mm".format(after["size"]),
            "单元类型：CPS4R，必要时允许 CPS3",
        ])
    elif stage == STAGE_JOB:
        lines.extend([
            "创建并提交 Job：{0}".format(target["job"]),
            "CPU：{0}".format(after["num_cpus"]),
            "不阻塞等待、不自动重试",
        ])
    elif stage == STAGE_RESULTS:
        lines.extend([
            "读取 Job：{0}".format(target["job"]),
            "输出：最大位移模、最大 Mises 应力",
            "报告：新建中文 Markdown，不覆盖同名文件",
            "CAE 模型：不修改",
        ])
    next_stage = NEXT_STAGE.get(stage)
    if next_stage:
        lines.extend(["", "下一步：{0}/10。".format(STAGE_NUMBERS[next_stage])])
    return "\n".join(lines)


__all__ = [
    "DEFAULT_COMMANDS",
    "GuidedCommandError",
    "GuidedStageRequest",
    "NEXT_STAGE",
    "STAGE_ASSEMBLY",
    "STAGE_BCS",
    "STAGE_INTERACTION",
    "STAGE_JOB",
    "STAGE_MATERIAL",
    "STAGE_MESH",
    "STAGE_NUMBERS",
    "STAGE_RESULTS",
    "STAGE_SECTION",
    "STAGE_STEP",
    "build_guided_plan",
    "format_guided_plan",
    "parse_guided_command",
]
