# -*- coding: utf-8 -*-
"""在用户明确确认后安装并注册固定版本的 Abaqus MCP。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from abaqus_codex.abqpy_environment import (
    abaqus_verification_level,
    is_automation_allowed,
    is_known_incompatible,
    parse_release_year,
)
from abaqus_codex.environment import inspect_abaqus
from abaqus_codex.mcp_environment import (
    _codex_candidates,
    inspect_abaqus_mcp,
    parse_abaqus_mcp_names,
    query_codex_mcp_list,
    vendor_python_paths,
)
from abaqus_codex.mcp_guard import MANAGED_GUARD_MARKER
from abaqus_codex.paths import is_private_runtime, project_python_executable


MCP_REPOSITORY = "https://github.com/Cai-aa/abaqus-mcp.git"
MCP_COMMIT = "48aa612ad37bfdc1a7af96181edc749273cc6987"
MCP_PYTHON_PACKAGE = "mcp==1.28.1"
MCP_SERVER_NAME = "abaqus-mcp-server"


class McpSetupError(RuntimeError):
    """表示 MCP 安装或注册没有安全完成。"""


def _same_lexical_path(value: object, expected: Path) -> bool:
    """比较命令配置中的绝对路径，不解析链接或访问目标文件。"""

    if not isinstance(value, str) or not value.strip():
        return False
    actual_text = os.path.normcase(
        os.path.abspath(os.path.expanduser(value.strip()))
    )
    expected_text = os.path.normcase(
        os.path.abspath(os.path.expanduser(os.fspath(expected)))
    )
    return actual_text == expected_text


def _managed_registration_matches(
    payload: object, target: Path, executable: Path
) -> bool:
    """仅识别本安装版生成、且没有被用户改动的 stdio 注册。"""

    if not isinstance(payload, dict):
        return False
    transport = payload.get("transport")
    if not isinstance(transport, dict):
        return False
    if transport.get("type") != "stdio":
        return False
    if not _same_lexical_path(transport.get("command"), executable):
        return False

    arguments = transport.get("args")
    expected_guard = target / "mcp_guard.py"
    if (
        not isinstance(arguments, list)
        or len(arguments) != 1
        or not _same_lexical_path(arguments[0], expected_guard)
    ):
        return False

    environment = transport.get("env")
    if not isinstance(environment, dict):
        return False
    if not _same_lexical_path(environment.get("ABAQUS_MCP_HOME"), target):
        return False

    # 本项目注册时只写入这两个环境变量。额外变量、工作目录或继承变量
    # 都可能是用户后续修改，因此宁可留下失效注册，也绝不擅自删除。
    expected_python_path = os.pathsep.join(
        str(path) for path in vendor_python_paths(target / "vendor")
    )
    if set(environment) != {"ABAQUS_MCP_HOME", "PYTHONPATH"}:
        return False
    if environment.get("PYTHONPATH") != expected_python_path:
        return False
    if transport.get("cwd") not in (None, ""):
        return False
    if transport.get("env_vars") not in (None, []):
        return False
    return True


def remove_managed_codex_registration(
    target: Optional[Path] = None, timeout_seconds: int = 15
) -> Dict[str, object]:
    """安全移除当前运行时拥有的 MCP 注册；无法证明所有权时保持原样。"""

    install_target = (target or (Path.home() / ".abaqus-mcp")).resolve()
    result: Dict[str, object] = {
        "status": "cli_unavailable",
        "removed": False,
        "target": str(install_target),
        "codex_cli": None,
        "message": "没有找到 Codex CLI；未更改 MCP 注册。",
    }
    candidates = _codex_candidates()
    if not candidates:
        return result

    query_failures: List[str] = []
    for candidate in candidates:
        command = [
            str(candidate),
            "mcp",
            "get",
            MCP_SERVER_NAME,
            "--json",
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            query_failures.append("{0}: {1}".format(candidate, error))
            continue
        if completed.returncode != 0:
            # Codex 对“不存在”和其他读取失败均返回非零；两种情况都必须
            # 保持不变，且不依赖可能随版本/语言变化的错误文字。
            query_failures.append(
                "{0}: 退出码 {1}".format(candidate, completed.returncode)
            )
            continue
        try:
            payload = json.loads(
                completed.stdout.decode("utf-8", errors="strict")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            query_failures.append("{0}: JSON 无效（{1}）".format(candidate, error))
            continue

        result["codex_cli"] = str(candidate)
        if not _managed_registration_matches(
            payload, install_target, project_python_executable()
        ):
            result.update(
                {
                    "status": "preserved_unmanaged",
                    "message": (
                        "MCP 注册不是当前安装版的原始受管配置；已保留。"
                    ),
                }
            )
            return result
        try:
            _run_command(
                [str(candidate), "mcp", "remove", MCP_SERVER_NAME],
                timeout_seconds=timeout_seconds,
            )
        except McpSetupError as error:
            result.update(
                {
                    "status": "remove_failed",
                    "message": "受管 MCP 注册未能移除；已停止清理：{0}".format(
                        error
                    ),
                }
            )
            return result
        result.update(
            {
                "status": "removed",
                "removed": True,
                "message": "已移除当前安装版创建的 Abaqus MCP 注册。",
            }
        )
        return result

    result.update(
        {
            "status": "not_registered_or_unreadable",
            "message": "未读取到 Abaqus MCP 注册；未更改任何配置。",
            "query_failures": query_failures,
        }
    )
    return result


def stop_managed_headless_bridge_for_uninstall(
    target: Optional[Path] = None, timeout_seconds: int = 20
) -> Dict[str, object]:
    """仅向本项目标记的 headless bridge 发停止信号，绝不强杀进程。"""

    from abaqus_codex.mcp_headless import (
        HEADLESS_PID_NAME,
        HEADLESS_SCRIPT_NAME,
        MANAGED_HEADLESS_MARKER,
        McpHeadlessError,
        inspect_headless_bridge,
        stop_headless_bridge,
    )

    install_target = (target or (Path.home() / ".abaqus-mcp")).resolve()
    script = install_target / HEADLESS_SCRIPT_NAME
    launcher_path = install_target / HEADLESS_PID_NAME
    base: Dict[str, object] = {
        "status": "not_running",
        "stopped": True,
        "target": str(install_target),
        "message": "没有本项目管理的 headless bridge 需要停止。",
    }
    try:
        state = inspect_headless_bridge(install_target)
    except (OSError, ValueError) as error:
        base.update(
            {
                "status": "inspection_failed",
                "stopped": False,
                "message": "无法确认 headless bridge 所有权；未发送停止信号：{0}".format(
                    error
                ),
            }
        )
        return base
    if not state.get("managed_process_running"):
        return base

    try:
        script_text = script.read_text(encoding="utf-8", errors="replace")
        launcher = json.loads(launcher_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        launcher = None
        script_text = ""
    if (
        MANAGED_HEADLESS_MARKER not in script_text
        or not isinstance(launcher, dict)
        or not _same_lexical_path(launcher.get("script"), script)
    ):
        base.update(
            {
                "status": "preserved_unmanaged",
                "stopped": False,
                "message": "后台进程缺少本项目所有权标记；未发送停止信号。",
            }
        )
        return base

    try:
        after = stop_headless_bridge(
            install_target, timeout_seconds=timeout_seconds
        )
    except McpHeadlessError as error:
        base.update(
            {
                "status": "stop_not_confirmed",
                "stopped": False,
                "message": str(error),
            }
        )
        return base
    base.update(
        {
            "status": "stopped",
            "stopped": not bool(after.get("managed_process_running")),
            "message": "已请求本项目 headless bridge 自行停止；未强杀进程。",
        }
    )
    return base


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
    python_command = [str(project_python_executable())]
    if is_private_runtime():
        python_command.append("-I")
    _run_command(
        python_command
        + [
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
        str(project_python_executable()),
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

    # 在任何下载和配置写入前先确认真实 Abaqus 版本，避免把 MCP 装到错误环境。
    abaqus = inspect_abaqus()
    if not abaqus["usable"]:
        raise McpSetupError(
            "没有检测到可用的 Abaqus 及其内置 Python，未下载或安装 MCP。"
        )
    release_year = parse_release_year(abaqus["version"])
    if release_year is None:
        raise McpSetupError(
            "检测到的 Abaqus 版本无法按年份识别，请人工确认兼容性后再安装 MCP。"
        )
    if is_known_incompatible(abaqus["version"]):
        raise McpSetupError(
            "Abaqus {0} 已被项目列为已知不兼容，未下载或安装 MCP。".format(
                abaqus["version"]
            )
        )
    if not is_automation_allowed(abaqus["version"]):
        raise McpSetupError(
            "Abaqus {0} 尚未列入自动 MCP 流程，未下载或安装。".format(
                abaqus["version"]
            )
        )

    install_target = (target or (Path.home() / ".abaqus-mcp")).resolve()
    messages = [
        "已检测到 Abaqus {0}（内置 Python {1}）。".format(
            abaqus["version"], abaqus["python_version"]
        ),
        _ensure_source(install_target),
        _ensure_dependencies(install_target),
        _ensure_guard_launcher(install_target),
    ]
    if abaqus_verification_level(abaqus["version"]) != "maintainer_verified":
        messages.insert(
            1,
            "该年份尚未完成维护者真机求解验证；安装后仍需心跳和只读能力探测。",
        )
    messages.extend(_ensure_abaqus_plugin(install_target))
    messages.append(_ensure_codex_registration(install_target, repair=repair))

    result = inspect_abaqus_mcp()
    if not result["usable"]:
        raise McpSetupError(
            "安装步骤已结束，但最终验证未通过：{0}".format(result["message"])
        )
    return {
        "target": str(install_target),
        "abaqus": abaqus,
        "messages": messages,
        "result": result,
        # responsive 只代表桥接心跳，仍不能替代一次只读工具调用和模型冒烟测试。
        "requires_bridge_probe": not bool(result["responsive"]),
        "requires_read_only_tool_probe": True,
    }


def main(confirmed: bool = False, repair: bool = False) -> int:
    """运行 MCP 设置并显示每一步是否执行或跳过。"""

    setup_result = setup_mcp(confirmed=confirmed, repair=repair)
    for message in setup_result["messages"]:
        print("- {0}".format(message))
    print("最终状态：{0}".format(setup_result["result"]["message"]))
    if setup_result["requires_bridge_probe"]:
        print(
            "下一步：启动 Abaqus 插件或运行 mcp-headless start，等待桥接心跳。"
        )
    print("兼容性确认：心跳通过后，再执行一次只读模型信息探测。")
    return 0
