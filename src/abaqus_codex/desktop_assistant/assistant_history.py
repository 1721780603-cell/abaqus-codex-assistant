# -*- coding: utf-8 -*-
"""保存不含完整路径和凭据的桌面助手操作记录。"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional


HISTORY_SCHEMA = "abaqus-codex-assistant-history/1"
MAX_HISTORY_RECORDS = 120
MAX_HISTORY_TEXT = 12000
ALLOWED_STATUSES = frozenset(
    ("计划待确认", "计划失败", "执行成功", "执行失败", "检查完成")
)
WINDOWS_PATH_PATTERN = re.compile(r"(?i)(?:[A-Z]:\\|\\\\)[^\r\n]*")
POSIX_PATH_PATTERN = re.compile(r"(?m)(?<!\w)/(?:[^\s/]+/)+[^\s]*")


def default_history_path() -> Path:
    """把历史放在用户本地应用目录，不写入项目或 CAE 目录。"""

    local_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_data) if local_data else Path.home()
    return (base / "AbaqusCodexAssistant" / "assistant_history.json").resolve()


def sanitize_history_text(value: object) -> str:
    """隐藏可能意外进入说明文字的完整路径并限制记录长度。"""

    text = str(value).replace("\x00", "").strip()
    text = WINDOWS_PATH_PATTERN.sub("[本机路径已隐藏]", text)
    text = POSIX_PATH_PATTERN.sub("[本机路径已隐藏]", text)
    return text[:MAX_HISTORY_TEXT]


class AssistantHistoryStore:
    """使用原子替换维护有限条本地审计记录。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = (path or default_history_path()).resolve()

    def read(self) -> list[dict[str, str]]:
        """读取可信字段；损坏或未知版本记录按空历史处理。"""

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return []
        if not isinstance(data, dict) or data.get("schema") != HISTORY_SCHEMA:
            return []
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            return []
        records: list[dict[str, str]] = []
        required = {"record_id", "created_at", "title", "status", "details"}
        for item in raw_records[-MAX_HISTORY_RECORDS:]:
            if (
                isinstance(item, dict)
                and set(item) == required
                and all(isinstance(item[field], str) for field in required)
                and item["status"] in ALLOWED_STATUSES
            ):
                records.append(dict(item))
        return records

    def append(self, *, title: str, status: str, details: str) -> dict[str, str]:
        """追加一条界面已展示的信息，不保存原始命令或模型路径。"""

        if status not in ALLOWED_STATUSES:
            raise ValueError("操作记录状态不在白名单中。")
        record = {
            "record_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": sanitize_history_text(title)[:160],
            "status": status,
            "details": sanitize_history_text(details),
        }
        records = (self.read() + [record])[-MAX_HISTORY_RECORDS:]
        payload = {"schema": HISTORY_SCHEMA, "records": records}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(temporary), str(self.path))
        return record


def format_history(records: list[Mapping[str, str]]) -> str:
    """按最新优先格式化历史，便于初学者扫描计划和结果。"""

    if not records:
        return (
            "还没有操作记录。\n\n"
            "生成修改计划后，这里会保存计划内容；应用后会追加成功或失败结果。"
        )
    lines = ["操作记录（最新在前）", "完整路径、凭据和模型文件不会写入这里。", ""]
    for record in reversed(records):
        timestamp = record["created_at"].replace("T", " ")[:19]
        lines.extend(
            [
                "{0}｜{1}｜{2}".format(timestamp, record["status"], record["title"]),
                record["details"],
                "",
                "=" * 54,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


__all__ = [
    "AssistantHistoryStore",
    "default_history_path",
    "format_history",
    "sanitize_history_text",
]
