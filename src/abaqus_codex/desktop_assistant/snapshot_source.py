# -*- coding: utf-8 -*-
"""安全读取 Abaqus 2021 一次性只读模型快照。"""

from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from abaqus_codex.desktop_assistant.bridge import (
    BridgeOfflineError,
    BridgeProtocolError,
)
from abaqus_codex.mcp_guard import process_is_running


SCHEMA_NAME = "abaqus-codex-readonly-snapshot"
SCHEMA_VERSION = 1
TARGET_RELEASE = "2021"
MAX_SNAPSHOT_BYTES = 256 * 1024
MAX_MODELS = 50
MAX_NAMES_PER_FIELD = 200
MAX_NAME_LENGTH = 160
MAX_FUTURE_SECONDS = 30.0
DEFAULT_MAX_AGE_SECONDS = 300.0

SNAPSHOT_NAME_PATTERN = re.compile(
    r"^snapshot_(?P<snapshot_id>(?P<stamp>\d{8}T\d{12}Z)_"
    r"(?P<pid>[1-9]\d*)_(?P<random>[0-9a-f]{32}))\.json$"
)
MODEL_FIELDS = frozenset(
    (
        "name",
        "parts",
        "materials",
        "steps",
        "instances",
        "loads",
        "boundary_conditions",
        "interactions",
    )
)
LIST_FIELDS = (
    "parts",
    "materials",
    "steps",
    "instances",
    "loads",
    "boundary_conditions",
    "interactions",
)
ROOT_FIELDS = frozenset(
    (
        "schema",
        "schema_version",
        "target_release",
        "complete",
        "snapshot_id",
        "generated_at_utc",
        "producer_pid",
        "truncated",
        "warnings",
        "models",
    )
)
WARNING_CODES = frozenset(
    (
        "MODELS_UNREADABLE",
        "MODEL_UNREADABLE",
        "PARTS_UNREADABLE",
        "MATERIALS_UNREADABLE",
        "STEPS_UNREADABLE",
        "INSTANCES_UNREADABLE",
        "LOADS_UNREADABLE",
        "BCS_UNREADABLE",
        "INTERACTIONS_UNREADABLE",
    )
)


class SnapshotMissingError(BridgeOfflineError):
    """表示固定目录中没有一次性快照。"""


class SnapshotProtocolError(BridgeProtocolError):
    """表示最新快照不符合固定只读协议。"""


def default_snapshot_directory() -> Path:
    """返回与 Abaqus 2021 插件一致的当前用户固定目录。"""

    local_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_data) if local_data else Path.home()
    return (base / "AbaqusCodexAssistant" / "readonly_snapshots").resolve()


def _reject_constant(value: str) -> object:
    """拒绝 JSON 标准之外的 NaN 和 Infinity。"""

    raise SnapshotProtocolError("快照包含非标准数值。")


def _unique_object(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    """拒绝重复键，避免同一字段有两种解释。"""

    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotProtocolError("快照包含重复字段。")
        result[key] = value
    return result


def _parse_utc(value: object) -> float:
    """解析固定 UTC 时间格式，并返回 Unix 秒数。"""

    if not isinstance(value, str):
        raise SnapshotProtocolError("快照时间格式不正确。")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise SnapshotProtocolError("快照时间格式不正确。") from error
    return parsed.replace(tzinfo=timezone.utc).timestamp()


def _validate_name(value: object) -> str:
    """只接受有限、非空且不含控制字符的对象名称。"""

    if not isinstance(value, str) or not value or len(value) > MAX_NAME_LENGTH:
        raise SnapshotProtocolError("快照中的对象名称不符合限制。")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SnapshotProtocolError("快照中的对象名称包含控制字符。")
    if re.search(r"(?:[A-Za-z]:[\\/]|\\\\)", value):
        raise SnapshotProtocolError("快照中的对象名称不能是本机路径。")
    return value


def _validate_name_list(value: object) -> List[str]:
    """验证并复制一个对象名称列表。"""

    if not isinstance(value, list) or len(value) > MAX_NAMES_PER_FIELD:
        raise SnapshotProtocolError("快照中的对象名称列表不符合限制。")
    return [_validate_name(item) for item in value]


def _validate_models(value: object) -> List[Dict[str, object]]:
    """验证模型列表，并转换成现有桌面摘要使用的字段名。"""

    if not isinstance(value, list) or len(value) > MAX_MODELS:
        raise SnapshotProtocolError("快照中的模型列表不符合限制。")
    models = []
    for raw_model in value:
        if not isinstance(raw_model, Mapping):
            raise SnapshotProtocolError("快照中的模型不是 JSON 对象。")
        if frozenset(raw_model) != MODEL_FIELDS:
            raise SnapshotProtocolError("快照中的模型字段不完整。")
        model = {
            "name": _validate_name(raw_model["name"]),
            "parts": _validate_name_list(raw_model["parts"]),
            "materials": _validate_name_list(raw_model["materials"]),
            "steps": _validate_name_list(raw_model["steps"]),
            "assemblies": _validate_name_list(raw_model["instances"]),
            "loads": _validate_name_list(raw_model["loads"]),
            "bcs": _validate_name_list(raw_model["boundary_conditions"]),
            "interactions": _validate_name_list(raw_model["interactions"]),
        }
        models.append(model)
    return models


class SnapshotFileSource:
    """读取用户主动生成的静态快照；不创建目录或发送任何命令。"""

    is_mock = False
    source_kind = "snapshot"
    mode_name = "一次性快照"

    def __init__(
        self,
        directory: Optional[Path] = None,
        *,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        process_checker: Callable[[int], bool] = process_is_running,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        """保存固定读取目录和可替换检查函数，便于离线测试。"""

        if max_age_seconds <= 0:
            raise ValueError("快照有效时间必须大于零。")
        self.directory = (directory or default_snapshot_directory()).resolve()
        self.max_age_seconds = float(max_age_seconds)
        self.process_checker = process_checker
        self.wall_clock = wall_clock

    def _latest_path(self) -> Tuple[Path, re.Match[str]]:
        """只选择严格匹配名称的最新最终 JSON，完全忽略临时文件。"""

        if not self.directory.is_dir():
            raise SnapshotMissingError("尚未生成 Abaqus 只读快照。")
        candidates = []
        try:
            for path in self.directory.iterdir():
                match = SNAPSHOT_NAME_PATTERN.fullmatch(path.name)
                if match is None or path.is_symlink() or not path.is_file():
                    continue
                candidates.append((match.group("stamp"), path.name, path, match))
        except OSError as error:
            raise SnapshotProtocolError("无法读取本地快照目录。") from error
        if not candidates:
            raise SnapshotMissingError("尚未生成 Abaqus 只读快照。")
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, path, match = candidates[0]
        return path, match

    def _read_latest(self) -> Tuple[Dict[str, object], float, int]:
        """从同一文件句柄限量读取，并验证整个协议外壳。"""

        path, filename_match = self._latest_path()
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        except OSError as error:
            raise SnapshotProtocolError("最新快照暂时无法读取。") from error
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise SnapshotProtocolError("最新快照超过安全大小上限。")
        try:
            payload = json.loads(
                raw.decode("utf-8-sig"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except SnapshotProtocolError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise SnapshotProtocolError("最新快照不是完整的 UTF-8 JSON。") from error
        if not isinstance(payload, dict) or frozenset(payload) != ROOT_FIELDS:
            raise SnapshotProtocolError("最新快照的根字段不完整。")
        if payload["schema"] != SCHEMA_NAME:
            raise SnapshotProtocolError("最新快照的协议名称不受支持。")
        if (
            isinstance(payload["schema_version"], bool)
            or payload["schema_version"] != SCHEMA_VERSION
        ):
            raise SnapshotProtocolError("最新快照的协议版本不受支持。")
        if payload["target_release"] != TARGET_RELEASE:
            raise SnapshotProtocolError("当前版本只接受 Abaqus 2021 快照。")
        if payload["complete"] is not True:
            raise SnapshotProtocolError("最新快照尚未完整写入。")

        snapshot_id = payload["snapshot_id"]
        if snapshot_id != filename_match.group("snapshot_id"):
            raise SnapshotProtocolError("快照 ID 与文件名不一致。")
        generated_at = _parse_utc(payload["generated_at_utc"])
        filename_time = datetime.strptime(
            filename_match.group("stamp"), "%Y%m%dT%H%M%S%fZ"
        ).replace(tzinfo=timezone.utc).timestamp()
        if generated_at != filename_time or not math.isfinite(generated_at):
            raise SnapshotProtocolError("快照时间与文件名不一致。")

        producer_pid = payload["producer_pid"]
        if (
            isinstance(producer_pid, bool)
            or not isinstance(producer_pid, int)
            or producer_pid <= 0
            or producer_pid > 0xFFFFFFFF
            or str(producer_pid) != filename_match.group("pid")
        ):
            raise SnapshotProtocolError("快照进程标识不正确。")
        if not isinstance(payload["truncated"], bool):
            raise SnapshotProtocolError("快照截断标记不正确。")
        warnings = payload["warnings"]
        if (
            not isinstance(warnings, list)
            or len(warnings) > 100
            or any(code not in WARNING_CODES for code in warnings)
        ):
            raise SnapshotProtocolError("快照警告代码不受支持。")

        models = _validate_models(payload["models"])
        result = {
            "models": models,
            "snapshot_generated_at": generated_at,
            "partial": bool(warnings or payload["truncated"]),
        }
        return result, generated_at, producer_pid

    def _inspect(self) -> Tuple[Dict[str, object], Optional[Dict[str, object]]]:
        """把缺失、过期和无效快照映射成不泄露路径的状态。"""

        try:
            data, generated_at, producer_pid = self._read_latest()
        except SnapshotMissingError:
            return {
                "responsive": False,
                "status": "missing",
                "message": "尚未生成一次性只读快照。",
            }, None
        except (SnapshotProtocolError, OSError, ValueError):
            return {
                "responsive": False,
                "status": "invalid",
                "message": "最新快照未通过安全校验。",
            }, None

        age = self.wall_clock() - generated_at
        if age < -MAX_FUTURE_SECONDS:
            return {
                "responsive": False,
                "status": "future",
                "message": "快照时间位于未来。",
            }, None
        if age > self.max_age_seconds:
            return {
                "responsive": False,
                "status": "stale",
                "message": "一次性快照已经过期。",
            }, None
        if not self.process_checker(producer_pid):
            return {
                "responsive": False,
                "status": "dead-process",
                "message": "生成快照的 Abaqus 会话已经关闭。",
            }, None
        return {
            "responsive": True,
            "status": "fresh",
            "message": "一次性只读快照可用。",
            "pid": producer_pid,
        }, data

    def inspect_status(self) -> Dict[str, object]:
        """只检查静态文件，不创建目录、不等待，也不发送 MCP 命令。"""

        status, _ = self._inspect()
        return status

    def get_model_info(self, timeout_seconds: float = 5.0) -> Dict[str, object]:
        """返回已验证的白名单字段；参数仅用于保持统一只读接口。"""

        if not 0.1 <= float(timeout_seconds) <= 10.0:
            raise ValueError("只读命令超时必须位于 0.1～10 秒之间。")
        status, data = self._inspect()
        if not status.get("responsive") or data is None:
            raise BridgeOfflineError("一次性只读快照当前不可用。")
        return data


__all__ = [
    "MAX_SNAPSHOT_BYTES",
    "SNAPSHOT_NAME_PATTERN",
    "SnapshotFileSource",
    "SnapshotMissingError",
    "SnapshotProtocolError",
    "default_snapshot_directory",
]
