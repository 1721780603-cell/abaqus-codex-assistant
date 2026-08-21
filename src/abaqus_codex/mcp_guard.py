# -*- coding: utf-8 -*-
"""在 Abaqus MCP 工具调用前执行快速健康检查，避免客户端长时间转圈。"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import ctypes
from pathlib import Path
from typing import Callable, Dict, Optional


# 此标记用于区分项目管理的启动器和用户自己的同名文件。
MANAGED_GUARD_MARKER = "ABAQUS_CODEX_ASSISTANT_MANAGED_MCP_GUARD_V1"
DEFAULT_STATUS_MAX_AGE_SECONDS = 10.0


def process_is_running(pid: int) -> bool:
    """用不发送真实信号的方式检查状态文件中的进程是否仍存在。"""

    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_is_running(pid)
    try:
        # 信号 0 只检查进程，不会结束 Abaqus。
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 无权查询通常意味着进程存在，但属于其他权限级别。
        return True
    except OSError:
        return False
    return True


def _windows_process_is_running(pid: int) -> bool:
    """在 Windows 上用只读进程句柄检查 PID，避免 os.kill 的兼容异常。"""

    process_query_limited_information = 0x1000
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        open_process.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        handle = open_process(process_query_limited_information, 0, pid)
        if handle:
            close_handle(handle)
            return True
        # ERROR_ACCESS_DENIED 表示进程存在，只是当前权限不能打开。
        return ctypes.get_last_error() == 5
    except (AttributeError, OSError, SystemError, ValueError):
        return False


def inspect_bridge_status(
    status_file: Path,
    *,
    now: Optional[float] = None,
    max_age_seconds: float = DEFAULT_STATUS_MAX_AGE_SECONDS,
    process_checker: Callable[[int], bool] = process_is_running,
) -> Dict[str, object]:
    """读取 Abaqus 插件心跳，并返回可供 doctor 和启动器复用的结果。"""

    if max_age_seconds <= 0:
        raise ValueError("MCP 状态最大允许时间必须大于零。")
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "responsive": False,
            "status": "missing",
            "age_seconds": None,
            "pid": None,
            "message": "没有找到 Abaqus 插件状态文件；请先启动 Abaqus/CAE。",
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "responsive": False,
            "status": "invalid",
            "age_seconds": None,
            "pid": None,
            "message": "Abaqus 插件状态文件无法读取；请重启 Abaqus/CAE 中的 MCP 插件。",
        }

    if not isinstance(status, dict):
        return {
            "responsive": False,
            "status": "invalid",
            "age_seconds": None,
            "pid": None,
            "message": "Abaqus 插件状态格式无效；请重启 MCP 插件。",
        }

    state = status.get("status", "unknown")
    pid = status.get("pid")
    timestamp = status.get("timestamp")
    if state != "running":
        return {
            "responsive": False,
            "status": state,
            "age_seconds": None,
            "pid": pid,
            "message": "Abaqus MCP 插件没有运行（状态：{0}）。".format(state),
        }
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(float(timestamp))
    ):
        return {
            "responsive": False,
            "status": "invalid",
            "age_seconds": None,
            "pid": pid,
            "message": "Abaqus MCP 心跳时间无效；请重启插件。",
        }

    current_time = time.time() if now is None else now
    age_seconds = max(0.0, float(current_time) - float(timestamp))
    if float(timestamp) > float(current_time) + 5.0:
        return {
            "responsive": False,
            "status": "future",
            "age_seconds": age_seconds,
            "pid": pid,
            "message": "Abaqus MCP 心跳时间位于未来；请检查系统时间并重启插件。",
        }
    if age_seconds > max_age_seconds:
        return {
            "responsive": False,
            "status": "stale",
            "age_seconds": age_seconds,
            "pid": pid,
            "message": "Abaqus MCP 心跳已过期 {0:.1f} 秒；CAE 可能已关闭或插件线程已停止。".format(
                age_seconds
            ),
        }
    if not process_checker(pid):
        return {
            "responsive": False,
            "status": "dead-process",
            "age_seconds": age_seconds,
            "pid": pid,
            "message": "Abaqus MCP 记录的进程不存在；请重新启动 Abaqus/CAE。",
        }
    return {
        "responsive": True,
        "status": "running",
        "age_seconds": age_seconds,
        "pid": pid,
        "message": "Abaqus MCP 插件心跳正常。",
    }


def guarded_sender(
    original_sender: Callable[..., dict],
    status_file: Path,
    *,
    max_age_seconds: float = DEFAULT_STATUS_MAX_AGE_SECONDS,
    process_checker: Callable[[int], bool] = process_is_running,
) -> Callable[..., dict]:
    """包装第三方命令发送器；桥接离线时立即返回，不创建待处理命令。"""

    def send(cmd_type: str, timeout: float = 30.0, **kwargs) -> dict:
        health = inspect_bridge_status(
            status_file,
            max_age_seconds=max_age_seconds,
            process_checker=process_checker,
        )
        if not health["responsive"]:
            return {
                "success": False,
                "error": "Abaqus MCP 防卡检查失败：{0}".format(health["message"]),
            }
        return original_sender(cmd_type, timeout=timeout, **kwargs)

    return send


def main() -> int:
    """加载固定的第三方 MCP，并只替换其命令发送前检查。"""

    mcp_home = Path(
        os.environ.get("ABAQUS_MCP_HOME", Path.home() / ".abaqus-mcp")
    ).resolve()
    sys.path.insert(0, str(mcp_home))
    try:
        import mcp_server  # type: ignore
    except Exception as error:
        # stdio MCP 的 stdout 属于协议通道，诊断只能写入 stderr。
        print("无法加载 Abaqus MCP：{0}".format(error), file=sys.stderr)
        return 1

    original_sender = mcp_server._send_command
    mcp_server._send_command = guarded_sender(
        original_sender, mcp_home / "status.json"
    )
    mcp_server.mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
