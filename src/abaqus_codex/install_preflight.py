# -*- coding: utf-8 -*-
"""为统一安装器提供与具体 Abaqus 年份解耦的只读检查。"""

from __future__ import annotations

import json
from typing import Dict

from abaqus_codex.abqpy_environment import parse_release_year
from abaqus_codex.environment import inspect_abaqus


SAFE_PLUGIN_VERIFIED_YEAR = 2021


def inspect_installation_target() -> Dict[str, object]:
    """检测任意 Abaqus，并单独报告安全插件是否已适配。"""

    abaqus = inspect_abaqus()
    detected = bool(abaqus.get("installed") and abaqus.get("command"))
    year = parse_release_year(abaqus.get("version"))
    usable = bool(abaqus.get("usable"))
    safe_plugin_supported = usable and year == SAFE_PLUGIN_VERIFIED_YEAR

    if not detected:
        message = "没有找到 Abaqus 启动命令，统一安装已停止。"
    elif safe_plugin_supported:
        message = "已检测到 Abaqus 2021，可安装核心组件和已验证的安全修改插件。"
    elif usable:
        message = (
            "已检测到 Abaqus，可安装桌面助手和 Codex Skill；"
            "当前安全修改插件尚未针对该版本完成验证。"
        )
    else:
        message = (
            "已找到 Abaqus 命令，可安装桌面助手和 Codex Skill；"
            "当前 Abaqus 状态未通过可用性检查，安全修改插件将跳过。"
        )

    return {
        "detected": detected,
        "usable": usable,
        "command": abaqus.get("command"),
        "version": abaqus.get("version"),
        "year": year,
        "safe_plugin_supported": safe_plugin_supported,
        "message": message,
    }


def main(json_output: bool = False) -> int:
    """输出安装后诊断结果；命令本身不决定核心程序能否安装。"""

    result = inspect_installation_target()
    if json_output:
        # PowerShell 5.1 只需解析 ASCII JSON，避免控制台代码页影响。
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    else:
        print(result["message"])
        if result["command"]:
            print("启动命令：{0}".format(result["command"]))
        if result["version"]:
            print("Abaqus 版本：{0}".format(result["version"]))
        print(
            "安全修改插件：{0}".format(
                "可安装" if result["safe_plugin_supported"] else "跳过"
            )
        )
    return 0 if result["detected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
