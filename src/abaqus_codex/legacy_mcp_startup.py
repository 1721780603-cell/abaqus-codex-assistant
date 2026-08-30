# -*- coding: utf-8 -*-
"""可回退地关闭旧 Abaqus MCP 的 CAE 启动时自动轮询。"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict


AUTO_START_BLOCK = (
    "        if 'mcp_start' in __main__.__dict__:\n"
    "            __main__.__dict__['mcp_start']()\n"
)
DISABLED_BLOCK = (
    "        # Abaqus Codex Assistant: legacy MCP auto-start is disabled.\n"
    "        # Start the legacy MCP only through an explicit project command.\n"
)


class LegacyMcpStartupError(RuntimeError):
    """表示环境文件与已知安全修复目标不一致。"""


def disable_legacy_mcp_autostart(
    env_path: Path,
    *,
    confirmed: bool,
) -> Dict[str, object]:
    """备份后只移除已知自动调用块，不删除或改写 MCP 插件。"""

    if not confirmed:
        raise LegacyMcpStartupError("修改启动配置前必须明确确认。")
    path = Path(env_path).resolve(strict=True)
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise LegacyMcpStartupError("abaqus_v6.env 不是可识别的 UTF-8 文件。") from error
    normalized = text.replace("\r\n", "\n")
    if AUTO_START_BLOCK not in normalized:
        if "legacy MCP auto-start is disabled" in normalized:
            return {"changed": False, "backup": None, "path": str(path)}
        raise LegacyMcpStartupError("没有找到已知的旧 MCP 自动启动代码，未修改文件。")
    if normalized.count(AUTO_START_BLOCK) != 1:
        raise LegacyMcpStartupError("旧 MCP 自动启动代码数量异常，未修改文件。")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + ".backup-mcp-autostart-" + timestamp)
    index = 1
    while backup.exists():
        backup = path.with_name(
            path.name
            + ".backup-mcp-autostart-"
            + timestamp
            + "-{0:03d}".format(index)
        )
        index += 1
    shutil.copy2(path, backup)

    newline = "\r\n" if "\r\n" in text else "\n"
    updated = normalized.replace(AUTO_START_BLOCK, DISABLED_BLOCK).replace(
        "\n", newline
    )
    encoded = updated.encode("utf-8")
    if has_bom:
        encoded = b"\xef\xbb\xbf" + encoded
    temporary = path.with_name("." + path.name + ".mcp-autostart.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    return {"changed": True, "backup": str(backup), "path": str(path)}


__all__ = ["LegacyMcpStartupError", "disable_legacy_mcp_autostart"]
