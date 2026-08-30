# -*- coding: utf-8 -*-
"""Abaqus 中文建模助手的 Python 3 桌面入口。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, MutableMapping, Optional


def _configure_windows_dpi_awareness(
    *,
    platform_name: Optional[str] = None,
    user32: object = None,
    shcore: object = None,
) -> str:
    """在导入 Tk 前启用当前进程的 Windows 高 DPI 感知。"""

    selected_platform = os.name if platform_name is None else platform_name
    if selected_platform != "nt":
        return "not-windows"

    # 依赖延后导入，避免非 Windows 环境在加载命令行模块时失败。
    import ctypes

    if user32 is None:
        user32 = ctypes.windll.user32
    if shcore is None:
        shcore = getattr(ctypes.windll, "shcore", None)

    # Windows 10 的 Per-Monitor V2 能避免 125%/150% 缩放时整窗位图放大。
    try:
        setter = getattr(user32, "SetProcessDpiAwarenessContext")
        try:
            setter.argtypes = [ctypes.c_void_p]
            setter.restype = ctypes.c_bool
        except AttributeError:
            # 单元测试使用普通 Python 函数模拟系统接口。
            pass
        if setter(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    # Windows 8.1 回退到第一代按显示器感知。
    try:
        if shcore is not None:
            setter = shcore.SetProcessDpiAwareness
            try:
                setter.argtypes = [ctypes.c_int]
                setter.restype = ctypes.c_long
            except AttributeError:
                pass
            if setter(2) == 0:
                return "per-monitor"
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    # 更旧系统至少启用系统 DPI 感知，避免完全由系统拉伸。
    try:
        setter = user32.SetProcessDPIAware
        try:
            setter.argtypes = []
            setter.restype = ctypes.c_bool
        except AttributeError:
            pass
        if setter():
            return "system"
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return "unchanged"


def _default_tcl_roots() -> list[Path]:
    """列出当前 Python 可能保存 Tcl/Tk 数据文件的位置。"""

    prefixes = (
        Path(sys.base_prefix),
        Path(sys.prefix),
        Path(sys.executable).resolve().parent.parent,
    )
    roots = []
    for prefix in prefixes:
        root = prefix / "tcl"
        if root not in roots:
            roots.append(root)
    return roots


def _configure_tk_runtime(
    *,
    candidate_roots: Optional[Iterable[Path]] = None,
    environment: Optional[MutableMapping[str, str]] = None,
) -> bool:
    """在 Windows Python 未自动定位 Tcl/Tk 时补充当前进程环境。"""

    target_environment = os.environ if environment is None else environment
    if target_environment.get("TCL_LIBRARY") and target_environment.get(
        "TK_LIBRARY"
    ):
        return True

    # 非 Windows 平台沿用系统 Tk 配置；显式候选目录仅供离线测试。
    if os.name != "nt" and candidate_roots is None:
        return False

    roots = _default_tcl_roots() if candidate_roots is None else candidate_roots
    for root_value in roots:
        root = Path(root_value)
        for tcl_directory in sorted(root.glob("tcl*"), reverse=True):
            if not (tcl_directory / "init.tcl").is_file():
                continue
            version = tcl_directory.name[3:]
            tk_directory = root / ("tk" + version)
            if not (tk_directory / "tk.tcl").is_file():
                continue
            target_environment.setdefault("TCL_LIBRARY", str(tcl_directory))
            target_environment.setdefault("TK_LIBRARY", str(tk_directory))
            return True
    return False


def launch(
    *,
    mock: bool = False,
    source: str = "snapshot",
    mcp_home: Optional[Path] = None,
) -> int:
    """延后加载 Tkinter，避免普通命令和无图形 CI 受影响。"""

    _configure_windows_dpi_awareness()
    _configure_tk_runtime()
    from abaqus_codex.desktop_assistant.app import launch as launch_app

    return launch_app(mock=mock, source=source, mcp_home=mcp_home)


def main() -> int:
    """供 Windows 无控制台快捷入口调用。"""

    return launch()


__all__ = ["launch", "main"]
