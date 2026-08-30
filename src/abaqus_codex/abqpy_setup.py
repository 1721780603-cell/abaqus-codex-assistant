# -*- coding: utf-8 -*-
"""在用户确认后为检测到的 Abaqus 年份安装匹配的 abqpy。"""

from __future__ import annotations

import subprocess
import sys
from typing import Dict, List

from abaqus_codex.abqpy_environment import (
    inspect_abqpy,
    is_known_incompatible,
    recommended_abqpy_requirement,
)
from abaqus_codex.environment import inspect_abaqus


class AbqpySetupError(RuntimeError):
    """表示 abqpy 安装计划或安装验证没有安全完成。"""


def build_install_command(requirement: str) -> List[str]:
    """构造固定参数列表，确保依赖安装到当前项目 Python。"""

    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        requirement,
    ]


def _run_install(command: List[str], timeout_seconds: int = 600) -> None:
    """运行 pip，并只在失败时保留末尾诊断信息。"""

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AbqpySetupError("无法完成 abqpy 安装：{0}".format(error)) from error

    if completed.returncode != 0:
        output = completed.stdout.decode("utf-8", errors="replace")
        tail = "\n".join(output.splitlines()[-20:])
        raise AbqpySetupError(
            "匹配年份的 abqpy 安装失败；没有改装其他年份。\n{0}".format(
                tail or "pip 没有返回详细信息。"
            )
        )


def setup_abqpy(confirmed: bool) -> Dict[str, object]:
    """检测 Abaqus 年份、安装对应 abqpy，并重新检查版本。"""

    if not confirmed:
        raise AbqpySetupError(
            "abqpy 安装会联网并修改当前项目 Python；请检查版本计划后使用 --yes 确认。"
        )

    abaqus = inspect_abaqus()
    if not abaqus["usable"]:
        raise AbqpySetupError(
            "没有检测到可用的 Abaqus 及其内置 Python，未安装 abqpy。"
        )
    if is_known_incompatible(abaqus["version"]):
        raise AbqpySetupError(
            "Abaqus {0} 已被项目列为已知不兼容，未安装 abqpy。".format(
                abaqus["version"]
            )
        )

    requirement = recommended_abqpy_requirement(abaqus["version"])
    if requirement is None:
        raise AbqpySetupError(
            "无法从 Abaqus 版本生成安全的 abqpy 年份规格，未执行安装。"
        )

    before = inspect_abqpy(abaqus["version"])
    if before["usable"]:
        return {
            "changed": False,
            "abaqus": abaqus,
            "requirement": requirement,
            "abqpy": before,
            "message": "匹配年份的 abqpy 已可用，未重复安装。",
        }

    command = build_install_command(requirement)
    _run_install(command)
    after = inspect_abqpy(abaqus["version"])
    if not after["usable"]:
        raise AbqpySetupError(
            "pip 已结束，但重新检查后 abqpy 仍未与 Abaqus 年份匹配。"
        )

    return {
        "changed": True,
        "abaqus": abaqus,
        "requirement": requirement,
        "abqpy": after,
        "message": "已安装并验证 {0}。".format(requirement),
    }


def main(confirmed: bool = False) -> int:
    """运行安全安装流程，并显示版本和目标 Python。"""

    result = setup_abqpy(confirmed=confirmed)
    print(result["message"])
    print("Abaqus 版本：{0}".format(result["abaqus"]["version"]))
    print("Abaqus 内置 Python：{0}".format(result["abaqus"]["python_version"]))
    print("项目 Python：{0}".format(result["abqpy"]["python_executable"]))
    print("abqpy 版本：{0}".format(result["abqpy"]["version"]))
    return 0
