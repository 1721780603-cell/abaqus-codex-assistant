# -*- coding: utf-8 -*-
"""区分随程序发布的只读资源与当前用户的可写数据。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional


RESOURCE_ROOT_ENV = "ABAQUS_CODEX_INSTALL_ROOT"
USER_DATA_ROOT_ENV = "ABAQUS_CODEX_USER_DATA_ROOT"
RESOURCE_MARKERS = ("configs", "skills", "abaqus_plugins")


def _absolute_path(value: object) -> Optional[Path]:
    """把非空路径转成绝对路径，不要求路径已经存在。"""

    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve(strict=False)


def _has_resource_markers(path: Path) -> bool:
    """只有同时包含三类发布资源时，才把目录当成安装根。"""

    try:
        return path.is_dir() and all((path / name).is_dir() for name in RESOURCE_MARKERS)
    except OSError:
        return False


def _candidate_ancestors(start: Path) -> Iterable[Path]:
    """从一个文件或目录向上枚举，并保持稳定顺序。"""

    current = start if start.is_dir() else start.parent
    yield current
    yield from current.parents


def resource_root() -> Path:
    """返回只读发布资源根目录。

    安装版的固定布局是 ``{app}\\runtime\\Lib\\site-packages`` 中安装
    Python 包，而 ``configs``、``skills`` 和 ``abaqus_plugins`` 位于
    ``{app}``。源码模式则从 ``repo/src/abaqus_codex`` 向上找到仓库根。
    显式环境变量便于安装器和离线测试指定资源；若指定了却
    不完整，立即报错，不再猜测另一份资源。
    """

    module_start = Path(__file__).resolve()
    executable = _absolute_path(sys.executable)

    def first_root(start: Optional[Path]) -> Optional[Path]:
        if start is None:
            return None
        for candidate in _candidate_ancestors(start):
            if _has_resource_markers(candidate):
                return candidate
        return None

    # 官方自包含布局中，包与解释器同时位于 {app}/runtime。
    # 此时必须优先使用自身完整资源，不允许残留环境变量劫持。
    module_root = first_root(module_start)
    executable_root = first_root(executable)
    if module_root is not None and executable_root == module_root and executable is not None:
        try:
            executable_relative = executable.relative_to(module_root)
        except ValueError:
            executable_relative = None
        if executable_relative is not None and executable_relative.parts:
            if executable_relative.parts[0].lower() == "runtime":
                return module_root

    explicit = _absolute_path(os.environ.get(RESOURCE_ROOT_ENV))
    if explicit is not None:
        if not _has_resource_markers(explicit):
            raise RuntimeError(
                "{0} 指向的资源根不完整：{1}".format(
                    RESOURCE_ROOT_ENV, explicit
                )
            )
        return explicit

    starts: list[Path] = [module_start]
    if executable is not None:
        starts.append(executable)
    frozen_root = _absolute_path(getattr(sys, "_MEIPASS", None))
    if frozen_root is not None:
        starts.insert(0, frozen_root)

    seen: set[Path] = set()
    for start in starts:
        for candidate in _candidate_ancestors(start):
            if candidate in seen:
                continue
            seen.add(candidate)
            if _has_resource_markers(candidate):
                return candidate

    raise RuntimeError(
        "未找到完整的 Abaqus Codex Assistant 资源；"
        "请修复安装或设置 {0}。".format(RESOURCE_ROOT_ENV)
    )


def user_data_root(*, create: bool = False) -> Path:
    """返回当前用户的可写数据根目录。

    默认为 ``%LOCALAPPDATA%\\AbaqusCodexAssistant``；测试或便携式部署
    可用 ``ABAQUS_CODEX_USER_DATA_ROOT`` 显式覆盖。本函数不会把
    发布目录当作可写目录。
    """

    root = _absolute_path(os.environ.get(USER_DATA_ROOT_ENV))
    if root is None:
        local_data = _absolute_path(os.environ.get("LOCALAPPDATA"))
        if local_data is None:
            # 非 Windows 的测试和开发环境仍有可预期的用户级回退。
            local_data = Path.home().resolve(strict=False) / ".local" / "share"
        root = local_data / "AbaqusCodexAssistant"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def is_private_runtime() -> bool:
    """当前进程是否由 Windows 安装版自带的 Python 启动。"""

    try:
        expected = (resource_root() / "runtime").resolve(strict=False)
        executable_parent = Path(sys.executable).resolve(strict=False).parent
    except (OSError, RuntimeError):
        return False
    return executable_parent == expected


def user_python_packages(*, create: bool = False) -> Path:
    """返回安装版可选 Python 包的用户级目录。"""

    target = user_data_root(create=create) / "python-packages"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def activate_user_python_packages(*, create: bool = False) -> Optional[Path]:
    """仅在私有运行时中启用用户级可选包，并返回其路径。"""

    if not is_private_runtime():
        return None
    target = user_python_packages(create=create)
    if not target.is_dir():
        return None
    text = str(target)
    if text not in sys.path:
        sys.path.insert(0, text)
    return target


def project_python_executable() -> Path:
    """返回适合 CLI、pip 和 MCP stdio 的项目 Python。"""

    current = Path(sys.executable).resolve(strict=False)
    if is_private_runtime():
        console_python = resource_root() / "runtime" / "python.exe"
        if console_python.is_file():
            return console_python.resolve(strict=False)
    return current


def codex_home(explicit: Optional[Path] = None) -> Path:
    """返回 Codex 用户目录，支持显式值和 ``CODEX_HOME``。"""

    selected = _absolute_path(explicit)
    if selected is None:
        selected = _absolute_path(os.environ.get("CODEX_HOME"))
    if selected is not None:
        return selected
    user_profile = _absolute_path(os.environ.get("USERPROFILE"))
    if user_profile is None:
        user_profile = Path.home().resolve(strict=False)
    return user_profile / ".codex"


__all__ = [
    "RESOURCE_ROOT_ENV",
    "USER_DATA_ROOT_ENV",
    "activate_user_python_packages",
    "codex_home",
    "is_private_runtime",
    "project_python_executable",
    "resource_root",
    "user_data_root",
    "user_python_packages",
]
