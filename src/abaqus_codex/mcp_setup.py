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
from abaqus_codex.mcp_guard import MANAGED_GUARD_MARKER


MCP_REPOSITORY = "https://github.com/Cai-aa/abaqus-mcp.git"
MCP_COMMIT = "48aa612ad37bfdc1a7af96181edc749273cc6987"
MCP_PYTHON_PACKAGE = "mcp==1.28.1"
MCP_SERVER_NAME = "abaqus-mcp-server"


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


def _ensure_guard_launcher(target: Path) -> str:
    """安装项目管理的防卡启动器；不覆盖用户自己编写的同名文件。"""

    source = Path(__file__).with_name("mcp_guard.py")
    destination = target / "mcp_guard.py"
    source_text = source.read_text(encoding="utf-8")
    if destination.is_file():
        existing_text = destination.read_text(encoding="utf-8", errors="replace")
        if MANAGED_GUARD_MARKER not in existing_text:
            raise McpSetupError(
                "发现非本项目管理的 mcp_guard.py，未覆盖：{0}".format(destination)
            )
        if existing_text == source_text:
            return "MCP 防卡启动器已是最新版本。"
    destination.write_text(source_text, encoding="utf-8")
    return "已安装 MCP 防卡启动器。"


def _registration_command(codex_cli: Path, target: Path, entry: Path) -> List[str]:
    """构造参数列表，不使用 shell 拼接命令。"""

    vendor = target / "vendor"
    python_path = os.pathsep.join(str(path) for path in vendor_python_paths(vendor))
    return [
        str(codex_cli),
        "mcp",
        "add",
        MCP_SERVER_NAME,
        "--env",
        "ABAQUS_MCP_HOME={0}".format(target),
        "--env",
        "PYTHONPATH={0}".format(python_path),
        "--",
        sys.executable,
        str(entry),
    ]


def _ensure_codex_registration(target: Path, repair: bool = False) -> str:
    """注册防卡启动器；已有注册只有明确 repair 时才替换。"""

    codex_cli, output = query_codex_mcp_list()
    if codex_cli is None:
        raise McpSetupError("没有找到可用的 Codex CLI，无法注册 MCP。")
    registered_names = parse_abaqus_mcp_names(output)
    if registered_names and not repair:
        return "Codex 中已有 MCP 注册；未替换。需要防卡修复时增加 --repair。"

    guard_entry = target / "mcp_guard.py"
    if MCP_SERVER_NAME in registered_names:
        _run_command([str(codex_cli), "mcp", "remove", MCP_SERVER_NAME])
    elif registered_names:
        raise McpSetupError(
            "检测到其他 Abaqus MCP 名称，未自动删除：{0}".format(
                "、".join(registered_names)
            )
        )

    try:
        _run_command(_registration_command(codex_cli, target, guard_entry))
    except McpSetupError as error:
        # 替换失败时尽力恢复原服务器，避免让原有配置彻底消失。
        if MCP_SERVER_NAME in registered_names:
            try:
                _run_command(
                    _registration_command(codex_cli, target, target / "mcp_server.py")
                )
            except McpSetupError:
                pass
        raise McpSetupError("防卡启动器注册失败：{0}".format(error)) from error
    return "已将 Abaqus MCP 防卡启动器注册到 Codex。"


def setup_mcp(
    confirmed: bool, target: Optional[Path] = None, repair: bool = False
) -> Dict[str, object]:
    """执行安装、插件配置、Codex 注册和最终验证。"""

    if not confirmed:
        raise McpSetupError(
            "MCP 安装会下载代码并修改用户配置；请检查说明后使用 --yes 确认。"
        )

    install_target = (target or (Path.home() / ".abaqus-mcp")).resolve()
    messages = [
        _ensure_source(install_target),
        _ensure_dependencies(install_target),
        _ensure_guard_launcher(install_target),
    ]
    messages.extend(_ensure_abaqus_plugin(install_target))
    messages.append(_ensure_codex_registration(install_target, repair=repair))

    result = inspect_abaqus_mcp()
    if not result["usable"]:
        raise McpSetupError(
            "安装步骤已结束，但最终验证未通过：{0}".format(result["message"])
        )
    return {"target": str(install_target), "messages": messages, "result": result}


def main(confirmed: bool = False, repair: bool = False) -> int:
    """运行 MCP 设置并显示每一步是否执行或跳过。"""

    setup_result = setup_mcp(confirmed=confirmed, repair=repair)
    for message in setup_result["messages"]:
        print("- {0}".format(message))
    print("最终状态：{0}".format(setup_result["result"]["message"]))
    return 0
