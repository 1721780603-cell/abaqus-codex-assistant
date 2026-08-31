# -*- coding: utf-8 -*-
"""汇总 Abaqus、abqpy 和 Abaqus MCP 的环境体检结果。"""

from __future__ import annotations

from typing import Dict

from abaqus_codex.abqpy_environment import inspect_abqpy
from abaqus_codex.environment import inspect_abaqus
from abaqus_codex.mcp_environment import inspect_abaqus_mcp
from abaqus_codex.paths import activate_user_python_packages


def inspect_environment() -> Dict[str, object]:
    """执行三项检测，并区分本地基础模式和 Codex 智能模式。"""

    # 安装版 abqpy 可能在助手进程启动后才由用户完成安装；每次体检
    # 都重新把用户包目录放入 sys.path，避免为刷新状态强制重启助手。
    activate_user_python_packages()
    abaqus = inspect_abaqus()
    abqpy = inspect_abqpy(abaqus["version"])
    mcp = inspect_abaqus_mcp()

    core_usable = bool(abaqus["usable"] and abqpy["usable"])
    ai_configured = bool(core_usable and mcp["usable"])
    ai_usable = bool(ai_configured and mcp["responsive"])
    return {
        "core_usable": core_usable,
        "ai_configured": ai_configured,
        "ai_usable": ai_usable,
        "abaqus": abaqus,
        "abqpy": abqpy,
        "mcp": mcp,
    }


def print_environment_report(result: Dict[str, object]) -> None:
    """以简洁中文输出环境体检结果。"""

    abaqus = result["abaqus"]
    abqpy = result["abqpy"]
    mcp = result["mcp"]

    print("Abaqus Codex Assistant 环境体检")
    print("================================")
    print("Abaqus：{0}".format(abaqus["message"]))
    if abaqus["version"]:
        print("  版本：{0}".format(abaqus["version"]))
    print("abqpy：{0}".format(abqpy["message"]))
    if abqpy["version"]:
        print("  版本：{0}".format(abqpy["version"]))
    print("Abaqus MCP：{0}".format(mcp["message"]))
    if not mcp["responsive"]:
        print("  桥接诊断：{0}".format(mcp["bridge_status"]["message"]))
    print("本地基础模式：{0}".format("可用" if result["core_usable"] else "不可用"))
    print(
        "Codex MCP 配置：{0}".format(
            "完成" if result["ai_configured"] else "未完成"
        )
    )
    print("Codex 智能模式：{0}".format("可用" if result["ai_usable"] else "不可用"))


def main() -> int:
    """运行综合环境体检；基础模式可用时返回成功。"""

    result = inspect_environment()
    print_environment_report(result)
    return 0 if result["core_usable"] else 1
