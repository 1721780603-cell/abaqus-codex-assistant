# -*- coding: utf-8 -*-
"""只读检查本机 Codex 程序和登录方式。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence


@dataclass(frozen=True)
class CodexStatus:
    """供桌面界面显示的最小 Codex 状态，不包含任何凭据。"""

    installed: bool
    authenticated: bool
    auth_method: str
    label: str
    tone: str
    guidance: str


class CodexLoginError(RuntimeError):
    """Codex 官方登录流程无法安全启动。"""


def _default_runner(
    command: Sequence[str], *, timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    """执行官方只读状态命令，并在 Windows 隐藏临时控制台。"""

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        creationflags=creation_flags,
    )


def _find_codex_executable(
    *,
    finder: Callable[[str], Optional[str]] = shutil.which,
    candidate_roots: Optional[Iterable[Path]] = None,
) -> Optional[str]:
    """先查 PATH，再查 Codex Windows 桌面版的版本化安装目录。"""

    path_match = finder("codex")
    if path_match:
        return path_match

    if candidate_roots is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        candidate_roots = (
            [Path(local_app_data) / "OpenAI" / "Codex" / "bin"]
            if local_app_data
            else []
        )

    matches = []
    for root_value in candidate_roots:
        root = Path(root_value)
        # 桌面版可能把可执行文件放在哈希版本子目录中。
        matches.extend(root.glob("*/codex.exe"))
        matches.extend(root.glob("codex.exe"))
    existing = [path for path in matches if path.is_file()]
    if not existing:
        return None
    try:
        selected = max(existing, key=lambda path: path.stat().st_mtime)
    except OSError:
        selected = sorted(existing, key=lambda path: str(path))[-1]
    return str(selected)


def inspect_codex_status(
    *,
    executable: Optional[str] = None,
    finder: Callable[[str], Optional[str]] = shutil.which,
    candidate_roots: Optional[Iterable[Path]] = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
    timeout_seconds: float = 5.0,
) -> CodexStatus:
    """调用 ``codex login status``；不读取登录缓存或令牌文件。"""

    codex_executable = executable or _find_codex_executable(
        finder=finder,
        candidate_roots=candidate_roots,
    )
    if not codex_executable:
        return CodexStatus(
            installed=False,
            authenticated=False,
            auth_method="none",
            label="Codex 未安装",
            tone="error",
            guidance="未找到 Codex；请先安装 Codex，再使用自己的 ChatGPT 账号登录。",
        )

    try:
        result = runner(
            [codex_executable, "login", "status"],
            timeout_seconds=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return CodexStatus(
            installed=True,
            authenticated=False,
            auth_method="unknown",
            label="Codex 待检查",
            tone="warning",
            guidance="Codex 已安装，但登录状态暂时无法确认；没有读取任何凭据。",
        )

    # 只在内存中判断官方命令的简短状态文字，原始输出不进入日志。
    output = "{0}\n{1}".format(result.stdout or "", result.stderr or "").lower()
    if "not logged in" in output or "未登录" in output:
        return CodexStatus(
            installed=True,
            authenticated=False,
            auth_method="none",
            label="Codex 未登录",
            tone="offline",
            guidance="Codex 已安装；请执行 codex login，并在官方浏览器页面使用自己的 ChatGPT 账号登录。",
        )

    if "logged in" in output and "api key" in output:
        return CodexStatus(
            installed=True,
            authenticated=True,
            auth_method="api_key",
            label="Codex API 登录",
            tone="warning",
            guidance="当前使用 API Key，费用由该用户的 OpenAI Platform 账户另行承担。",
        )

    if "logged in" in output and "chatgpt" in output:
        return CodexStatus(
            installed=True,
            authenticated=True,
            auth_method="chatgpt",
            label="Codex 已登录",
            tone="online",
            guidance="已通过 ChatGPT 登录；实际套餐、模型和额度由 OpenAI 账号决定。",
        )

    if result.returncode == 0 and "logged in" in output:
        return CodexStatus(
            installed=True,
            authenticated=True,
            auth_method="unknown",
            label="Codex 已登录",
            tone="online",
            guidance="Codex 报告已登录，但当前版本没有返回可识别的登录方式。",
        )

    return CodexStatus(
        installed=True,
        authenticated=False,
        auth_method="unknown",
        label="Codex 待检查",
        tone="warning",
        guidance="Codex 已安装，但没有得到可识别的登录状态；不会自动使用 API Key。",
    )


def start_codex_login(
    *,
    executable: Optional[str] = None,
    finder: Callable[[str], Optional[str]] = shutil.which,
    candidate_roots: Optional[Iterable[Path]] = None,
    process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> subprocess.Popen:
    """后台启动官方 ``codex login``，密码和令牌均由 Codex 自己处理。"""

    codex_executable = executable or _find_codex_executable(
        finder=finder,
        candidate_roots=candidate_roots,
    )
    if not codex_executable:
        raise CodexLoginError("未找到 Codex，请先安装后再登录。")

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return process_factory(
            [codex_executable, "login"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise CodexLoginError(
            "无法启动 Codex 官方登录，请稍后重试。"
        ) from error


__all__ = [
    "CodexLoginError",
    "CodexStatus",
    "inspect_codex_status",
    "start_codex_login",
]
