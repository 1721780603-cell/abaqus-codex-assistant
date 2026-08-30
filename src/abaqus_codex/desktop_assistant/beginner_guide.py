# -*- coding: utf-8 -*-
"""为初学者展示完整十步路线，不参与 Abaqus 写操作。"""

from __future__ import annotations

from abaqus_codex.desktop_assistant.guided_rectangle_flow import (
    DEFAULT_COMMANDS,
    STAGE_ASSEMBLY,
    STAGE_BCS,
    STAGE_INTERACTION,
    STAGE_JOB,
    STAGE_MATERIAL,
    STAGE_MESH,
    STAGE_RESULTS,
    STAGE_SECTION,
    STAGE_STEP,
)
from abaqus_codex.desktop_assistant.rectangle_flow import (
    DEFAULT_RECTANGLE_COMMAND,
)


# 每一步同时说明目的和可执行句式，避免用户只会照抄而不理解。
BEGINNER_STEPS = (
    (1, "几何", "创建二维矩形板零件。", DEFAULT_RECTANGLE_COMMAND),
    (2, "材料", "定义钢材的线弹性参数。", DEFAULT_COMMANDS[STAGE_MATERIAL]),
    (3, "截面", "创建截面并赋给整个零件。", DEFAULT_COMMANDS[STAGE_SECTION]),
    (4, "装配", "把零件实例化到装配中。", DEFAULT_COMMANDS[STAGE_ASSEMBLY]),
    (5, "分析步", "创建静力分析步并请求 S、U 输出。", DEFAULT_COMMANDS[STAGE_STEP]),
    (
        6,
        "相互作用",
        "解释单一连续板为何不需要接触，本步不修改模型。",
        DEFAULT_COMMANDS[STAGE_INTERACTION],
    ),
    (7, "边界与载荷", "约束刚体位移并施加右边拉伸位移。", DEFAULT_COMMANDS[STAGE_BCS]),
    (8, "网格", "设置全局尺寸并划分网格。", DEFAULT_COMMANDS[STAGE_MESH]),
    (9, "Job", "创建并异步提交计算任务。", DEFAULT_COMMANDS[STAGE_JOB]),
    (10, "结果与报告", "读取 ODB 极值并新建中文报告。", DEFAULT_COMMANDS[STAGE_RESULTS]),
)


def format_beginner_guide(current_step: int = 1) -> str:
    """生成可复制的十步说明，并突出当前步骤。"""

    lines = [
        "矩形板拉伸十步指令",
        "输入框会在每一步成功后自动填入下一条；无需背诵。",
        "每一步都先生成计划，核对后再应用。",
        "",
    ]
    for number, title, purpose, command in BEGINNER_STEPS:
        marker = "▶ 当前" if number == current_step else "  "
        lines.extend(
            [
                "{0} 第 {1}/10 步｜{2}".format(marker, number, title),
                "目的：" + purpose,
                "指令：" + command,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


__all__ = ["BEGINNER_STEPS", "format_beginner_guide"]
