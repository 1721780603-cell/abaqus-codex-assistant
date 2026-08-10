# -*- coding: utf-8 -*-
"""在用户明确确认后安装并注册固定版本的 Abaqus MCP。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from abaqus_codex.mcp_environment import (
    inspect_abaqus_mcp,
    parse_abaqus_mcp_names,
    query_codex_mcp_list,
    vendor_python_paths,
)


MCP_REPOSITORY = "https://github.com/Cai-aa/abaqus-mcp.git"
MCP_COMMIT = "48aa612ad37bfdc1a7af96181edc749273cc6987"
MCP_PYTHON_PACKAGE = "mcp==1.28.1"


class McpSetupError(RuntimeError):
    """表示 MCP 安装或注册没有安全完成。"""


def _run_command(
    command: List[str], cwd: Optional[Path] = None, timeout_seconds: int = 300
) -> str:
    """执行固定参数命令，并在失败时返回适合初学者阅读的信息。"""

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise McpSetupError("命令无法完成：{0}".format(error)) from error

    output = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        tail = "\n".join(output.splitlines()[-20:])
        raise McpSetupError(
            "命令返回退出码 {0}：\n{1}".format(completed.returncode, tail)
        )
    return output


def _ensure_source(target: Path) -> str:
    """下载固定 commit；已有完整目录时不覆盖。"""

    entry = target / "mcp_server.py"
    if entry.is_file():
        return "MCP 源码已存在，未重复下载。"
    if target.exists():
        raise McpSetupError(
            "目标目录已存在但缺少 mcp_server.py，请人工检查：{0}".format(target)
        )

    git_command = shutil.which("git")
    if not git_command:
        raise McpSetupError("没有找到 Git，无法下载固定版本的 MCP 源码。")

    _run_command([git_command, "clone", "--no-checkout", MCP_REPOSITORY, str(target)])
    _run_command(
        [git_command, "checkout", "--detach", MCP_COMMIT], cwd=target
    )
    if not entry.is_file():
        raise McpSetupError("下载完成后仍没有找到 mcp_server.py。")
    return "已下载固定版本的 MCP 源码。"


def _ensure_dependencies(target: Path) -> str:
    """把固定版本 MCP 依赖安装到独立 vendor 目录。"""

    vendor = target / "vendor"
    if (vendor / "mcp").is_dir():
        return "MCP Python 依赖已存在，未重复安装。"

    vendor.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--target",
            str(vendor),
            MCP_PYTHON_PACKAGE,
        ],
        timeout_seconds=600,
    )
    return "已将固定版本 MCP 依赖安装到 vendor 目录。"


def _ensure_abaqus_plugin(target: Path) -> List[str]:
    """安装自动加载文件和 GUI 菜单，但绝不覆盖已有用户文件。"""

    messages: List[str] = []
    home = Path.home()
    environment_source = target / "abaqus_v6.env.example"
    environment_target = home / "abaqus_v6.env"
    if environment_target.exists():
        messages.append("用户 abaqus_v6.env 已存在，未覆盖。")
    elif environment_source.is_file():
        shutil.copy2(environment_source, environment_target)
        messages.append("已安装 Abaqus MCP 自动加载环境文件。")
    else:
        messages.append("没有找到自动加载模板，请按 MCP 文档人工配置。")

    plugin_source = target / "abaqus_plugins" / "mcp_control"
    plugin_target = home / "abaqus_plugins" / "mcp_control"
    if plugin_target.exists():
        messages.append("Abaqus MCP GUI 插件已存在，未覆盖。")
    elif plugin_source.is_dir():
        plugin_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin_source, plugin_target)
        messages.append("已安装 Abaqus MCP GUI 插件。")
    else:
        messages.append("没有找到 GUI 插件目录，请按 MCP 文档人工配置。")
    return messages


def _ensure_codex_registration(target: Path) -> str:
    """把本地 MCP 注册到 Codex；已注册时不修改配置。"""

    codex_cli, output = query_codex_mcp_list()
    if codex_cli is None:
        raise McpSetupError("没有找到可用的 Codex CLI，无法注册 MCP。")
    if parse_abaqus_mcp_names(output):
        return "Codex 中已存在 Abaqus MCP 注册，未重复修改。"

    vendor = target / "vendor"
    entry = target / "mcp_server.py"
    python_path = os.pathsep.join(
        str(path) for path in vendor_python_paths(vendor)
    )
    command = [
        str(codex_cli),
        "mcp",
        "add",
        "abaqus-mcp-server",
        "--env",
        "ABAQUS_MCP_HOME={0}".format(target),
        "--env",
        "PYTHONPATH={0}".format(python_path),
        "--",
        sys.executable,
        str(entry),
    ]
    _run_command(command)
    return "已将 Abaqus MCP 注册到 Codex。"


def setup_mcp(confirmed: bool, target: Optional[Path] = None) -> Dict[str, object]:
    """执行安装、插件配置、Codex 注册和最终验证。"""

    if not confirmed:
        raise McpSetupError(
            "MCP 安装会下载代码并修改用户配置；请检查说明后使用 --yes 确认。"
        )

    install_target = (target or (Path.home() / ".abaqus-mcp")).resolve()
    messages = [
        _ensure_source(install_target),
        _ensure_dependencies(install_target),
    ]
    messages.extend(_ensure_abaqus_plugin(install_target))
    messages.append(_ensure_codex_registration(install_target))

    result = inspect_abaqus_mcp()
    if not result["usable"]:
        raise McpSetupError(
            "安装步骤已结束，但最终验证未通过：{0}".format(result["message"])
        )
    return {"target": str(install_target), "messages": messages, "result": result}


def main(confirmed: bool = False) -> int:
    """运行 MCP 设置并显示每一步是否执行或跳过。"""

    setup_result = setup_mcp(confirmed=confirmed)
    for message in setup_result["messages"]:
        print("- {0}".format(message))
    print("最终状态：{0}".format(setup_result["result"]["message"]))
    return 0
