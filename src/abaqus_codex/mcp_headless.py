# -*- coding: utf-8 -*-
"""管理不显示 Abaqus/CAE 图形界面的 MCP 后台桥接。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from abaqus_codex.abqpy_environment import (
    is_automation_allowed,
    is_known_incompatible,
)
from abaqus_codex.environment import (
    find_abaqus_command,
    inspect_abaqus_command,
)
from abaqus_codex.mcp_guard import inspect_bridge_status, process_is_running


MANAGED_HEADLESS_MARKER = "ABAQUS_CODEX_ASSISTANT_MANAGED_HEADLESS_BRIDGE_V1"
HEADLESS_SCRIPT_NAME = "mcp_headless_bridge.py"
HEADLESS_PID_NAME = "headless_bridge_launcher.json"
HEADLESS_STDOUT_NAME = "headless_bridge_stdout.log"
HEADLESS_STDERR_NAME = "headless_bridge_stderr.log"


HEADLESS_BRIDGE_SCRIPT = '''# -*- coding: utf-8 -*-
"""由 Abaqus Codex Assistant 管理的无界面 MCP 桥接入口。"""

# ABAQUS_CODEX_ASSISTANT_MANAGED_HEADLESS_BRIDGE_V1
# Abaqus 启动钩子会先加载 MCP 插件。这里停止不稳定的后台线程，
# 再在独立 noGUI 进程中使用稳定的阻塞轮询；不会占用用户的 CAE 界面。
if 'mcp_stop' in globals():
    mcp_stop()

if 'mcp_loop' not in globals():
    raise RuntimeError('Abaqus MCP plugin was not loaded by abaqus_v6.env')

print('Starting managed headless Abaqus MCP bridge...')
mcp_loop(sleep_interval=0.1)
'''


class McpHeadlessError(RuntimeError):
    """表示后台 MCP 桥接无法安全启动或停止。"""


def mcp_home_path(home: Optional[Path] = None) -> Path:
    """返回 MCP 工作目录。"""

    return (home or (Path.home() / ".abaqus-mcp")).resolve()


def _write_managed_script(home: Path) -> Path:
    """写入通用 noGUI 脚本，不覆盖用户自己的同名文件。"""

    path = home / HEADLESS_SCRIPT_NAME
    if path.is_file():
        existing = path.read_text(encoding="utf-8", errors="replace")
        if MANAGED_HEADLESS_MARKER not in existing:
            raise McpHeadlessError(
                "发现非本项目管理的后台脚本，未覆盖：{0}".format(path)
            )
        if existing.replace("\r\n", "\n") == HEADLESS_BRIDGE_SCRIPT.replace(
            "\r\n", "\n"
        ):
            return path
    path.write_text(HEADLESS_BRIDGE_SCRIPT, encoding="utf-8")
    return path


def _abaqus_arguments(
    command: Path,
    script: Path,
    system_name: Optional[str] = None,
) -> list[str]:
    """构造固定参数命令；可传入平台名，方便跨平台测试。"""

    no_gui_argument = "noGUI={0}".format(script)
    current_system = os.name if system_name is None else system_name
    if current_system == "nt" and command.suffix.lower() in {".bat", ".cmd"}:
        return [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(command),
            "cae",
            no_gui_argument,
        ]
    return [str(command), "cae", no_gui_argument]


def _read_launcher(home: Path) -> Dict[str, object]:
    """读取本项目记录的后台启动器信息。"""

    try:
        data = json.loads((home / HEADLESS_PID_NAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def inspect_headless_bridge(home: Optional[Path] = None) -> Dict[str, object]:
    """同时检查启动器进程和 Abaqus 插件心跳。"""

    root = mcp_home_path(home)
    launcher = _read_launcher(root)
    launcher_pid = launcher.get("launcher_pid")
    launcher_running = process_is_running(launcher_pid)
    bridge = inspect_bridge_status(root / "status.json")
    bridge_pid = launcher.get("bridge_pid")
    bridge_process_running = bool(
        bridge_pid
        and bridge.get("pid") == bridge_pid
        and process_is_running(bridge_pid)
    )
    managed_process_running = bool(launcher_running or bridge_process_running)
    return {
        "running": bool(managed_process_running and bridge["responsive"]),
        "launcher_pid": launcher_pid,
        "launcher_running": launcher_running,
        "bridge_pid": bridge_pid,
        "bridge_process_running": bridge_process_running,
        "managed_process_running": managed_process_running,
        "bridge": bridge,
        "stdout_log": str(root / HEADLESS_STDOUT_NAME),
        "stderr_log": str(root / HEADLESS_STDERR_NAME),
    }


def start_headless_bridge(
    home: Optional[Path] = None,
    abaqus_command: Optional[Path] = None,
    timeout_seconds: int = 60,
) -> Dict[str, object]:
    """隐藏启动独立 noGUI 进程，并等待插件心跳真正可用。"""

    if timeout_seconds <= 0:
        raise McpHeadlessError("后台桥接启动超时必须大于零。")
    root = mcp_home_path(home)
    if not (root / "abaqus_mcp_plugin.py").is_file():
        raise McpHeadlessError("没有找到 Abaqus MCP 插件，请先运行 mcp-setup。")

    current = inspect_headless_bridge(root)
    if current["running"]:
        return current
    current_bridge = current["bridge"]
    if current_bridge["responsive"]:
        raise McpHeadlessError(
            "已有 Abaqus MCP 桥接在线；请先停止 CAE 中的 MCP，再启动后台模式。"
        )

    command = abaqus_command or find_abaqus_command()
    if command is None or not Path(command).is_file():
        raise McpHeadlessError("没有找到 Abaqus 启动命令。")
    command = Path(command).resolve()
    abaqus = inspect_abaqus_command(command)
    if is_known_incompatible(abaqus.get("version")):
        raise McpHeadlessError(
            "Abaqus {0} 已被项目列为已知不兼容，后台桥接未启动。".format(
                abaqus.get("version")
            )
        )
    if not abaqus.get("usable"):
        raise McpHeadlessError(
            "无法可靠读取该 Abaqus 的版本和内置 Python，后台桥接未启动。"
        )
    if not is_automation_allowed(abaqus.get("version")):
        raise McpHeadlessError(
            "Abaqus {0} 尚未列入自动 MCP 流程，后台桥接未启动。".format(
                abaqus.get("version")
            )
        )
    script = _write_managed_script(root)
    stop_file = root / "stop.flag"
    if stop_file.exists():
        stop_file.unlink()

    stdout_path = root / HEADLESS_STDOUT_NAME
    stderr_path = root / HEADLESS_STDERR_NAME
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        # BREAKAWAY 让后台 Abaqus 不随启动命令所在的宿主作业退出；
        # NO_WINDOW 确保不弹出额外控制台窗口。DETACHED_PROCESS 会让
        # 部分 Abaqus 批处理初始化停住，因此这里明确不使用它。
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_BREAKAWAY_FROM_JOB
        )

    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    try:
        process = subprocess.Popen(
            _abaqus_arguments(Path(command), script),
            cwd=str(root),
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except OSError as error:
        raise McpHeadlessError("无法启动 Abaqus noGUI：{0}".format(error)) from error
    finally:
        stdout_handle.close()
        stderr_handle.close()

    launcher = {
        "launcher_pid": process.pid,
        "started_at": time.time(),
        "abaqus_command": str(command),
        "script": str(script),
    }
    (root / HEADLESS_PID_NAME).write_text(
        json.dumps(launcher, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            raise McpHeadlessError(
                "Abaqus noGUI 提前退出，退出码 {0}。请检查日志：{1}".format(
                    process.returncode, stderr_path
                )
            )
        result = inspect_headless_bridge(root)
        if result["running"]:
            bridge_pid = result["bridge"].get("pid")
            launcher["bridge_pid"] = bridge_pid
            (root / HEADLESS_PID_NAME).write_text(
                json.dumps(launcher, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return inspect_headless_bridge(root)
        time.sleep(0.5)
    raise McpHeadlessError(
        "Abaqus noGUI 在 {0} 秒内没有建立心跳；进程可能仍在启动，请检查：{1}".format(
            timeout_seconds, stderr_path
        )
    )


def stop_headless_bridge(
    home: Optional[Path] = None, timeout_seconds: int = 20
) -> Dict[str, object]:
    """发送停止文件并等待后台进程自行退出，不强制终止 Abaqus。"""

    if timeout_seconds <= 0:
        raise McpHeadlessError("后台桥接停止超时必须大于零。")
    root = mcp_home_path(home)
    before = inspect_headless_bridge(root)
    if not before["managed_process_running"]:
        return before
    (root / "stop.flag").write_text("stop", encoding="ascii")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = inspect_headless_bridge(root)
        if not result["managed_process_running"]:
            try:
                (root / HEADLESS_PID_NAME).unlink()
            except FileNotFoundError:
                pass
            return result
        time.sleep(0.5)
    raise McpHeadlessError(
        "已发送停止信号，但后台进程未在 {0} 秒内退出；未强制结束进程。".format(
            timeout_seconds
        )
    )


def print_headless_status(result: Dict[str, object]) -> None:
    """输出适合初学者阅读的后台桥接状态。"""

    print("Abaqus MCP 无界面后台桥接")
    print("----------------------------")
    print("整体状态：{0}".format("在线" if result["running"] else "离线"))
    print(
        "启动器进程：{0}".format(
            "运行中" if result["launcher_running"] else "未运行"
        )
    )
    if result["launcher_pid"]:
        print("启动器 PID：{0}".format(result["launcher_pid"]))
    if result["bridge_pid"]:
        print("Abaqus 内核 PID：{0}".format(result["bridge_pid"]))
    print("插件心跳：{0}".format(result["bridge"]["message"]))
    print("标准输出日志：{0}".format(result["stdout_log"]))
    print("错误日志：{0}".format(result["stderr_log"]))
