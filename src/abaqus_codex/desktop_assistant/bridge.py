# -*- coding: utf-8 -*-
"""通过现有 Abaqus MCP 文件协议执行固定的只读请求。"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, Optional

from abaqus_codex.mcp_guard import inspect_bridge_status, process_is_running


# 第一阶段只允许这两个命令，调用方不能把任意 MCP 类型传进来。
READ_ONLY_COMMANDS = frozenset(("ping", "get_model_info"))
MAX_RESULT_BYTES = 2 * 1024 * 1024
DEFAULT_POLL_INTERVAL_SECONDS = 0.05


class ReadOnlyBridgeError(RuntimeError):
    """表示只读桥接没有安全完成。"""


class BridgeOfflineError(ReadOnlyBridgeError):
    """表示 Abaqus MCP 心跳或进程不在线。"""


class BridgeTimeoutError(ReadOnlyBridgeError):
    """表示只读命令在固定时间内没有返回。"""


class BridgeProtocolError(ReadOnlyBridgeError):
    """表示结果文件超过限制或结构不符合约定。"""


class _ResultNotReady(ReadOnlyBridgeError):
    """表示第三方插件已经创建响应文件，但内容仍在写入。"""


def default_mcp_home() -> Path:
    """返回项目约定的 MCP 工作目录。"""

    configured = os.environ.get("ABAQUS_MCP_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".abaqus-mcp").resolve()


class FileIpcReadOnlyBridge:
    """只向已有 GUI 桥接发送固定查询，不导入第三方 MCP 服务器。"""

    is_mock = False
    source_kind = "mcp"
    mode_name = "MCP 兼容"

    def __init__(
        self,
        home: Optional[Path] = None,
        *,
        status_max_age_seconds: float = 10.0,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        process_checker: Callable[[int], bool] = process_is_running,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """保存固定目录和可替换时钟，便于做完全离线的测试。"""

        if status_max_age_seconds <= 0:
            raise ValueError("心跳最大允许时间必须大于零。")
        if poll_interval_seconds <= 0:
            raise ValueError("结果轮询间隔必须大于零。")
        self.home = (home or default_mcp_home()).expanduser().resolve()
        self.status_file = self.home / "status.json"
        self.commands_dir = self.home / "commands"
        self.results_dir = self.home / "results"
        self.status_max_age_seconds = status_max_age_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.process_checker = process_checker
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self.sleeper = sleeper

    def inspect_status(self) -> Dict[str, object]:
        """只读检查心跳；离线时不会创建命令目录或等待结果。"""

        return inspect_bridge_status(
            self.status_file,
            now=self.wall_clock(),
            max_age_seconds=self.status_max_age_seconds,
            process_checker=self.process_checker,
        )

    def ping(self, timeout_seconds: float = 2.0) -> Dict[str, object]:
        """发送固定 ping，验证插件是否真正处理命令。"""

        return self._request("ping", timeout_seconds=timeout_seconds)

    def get_model_info(self, timeout_seconds: float = 5.0) -> Dict[str, object]:
        """读取当前 MDB 的对象名称概要，不读取 ODB 或完整工程路径。"""

        result = self._request(
            "get_model_info", timeout_seconds=timeout_seconds
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise BridgeProtocolError("Abaqus 返回的模型概要不是 JSON 对象。")
        return data

    def _request(
        self, command_type: str, *, timeout_seconds: float
    ) -> Dict[str, object]:
        """原子发布一个白名单命令，并在短超时后清理自己的文件。"""

        if command_type not in READ_ONLY_COMMANDS:
            raise BridgeProtocolError(
                "只读助手拒绝非白名单命令：{0}".format(command_type)
            )
        if not 0.1 <= float(timeout_seconds) <= 10.0:
            raise ValueError("只读命令超时必须位于 0.1～10 秒之间。")

        health = self.inspect_status()
        if not health.get("responsive"):
            raise BridgeOfflineError(str(health.get("message", "桥接离线。")))

        try:
            self.commands_dir.mkdir(parents=True, exist_ok=True)
            self.results_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ReadOnlyBridgeError(
                "无法访问 MCP 命令目录；请检查当前用户的目录权限。"
            ) from error

        # 使用较长随机 ID，减少与第三方客户端并发时发生碰撞的概率。
        request_id = "aca_" + uuid.uuid4().hex[:16]
        command_path = self.commands_dir / ("cmd_{0}.json".format(request_id))
        temporary_path = self.commands_dir / ("cmd_{0}.tmp".format(request_id))
        result_path = self.results_dir / ("{0}.json".format(request_id))
        created_at = self.wall_clock()
        command = {
            "id": request_id,
            "type": command_type,
            "timestamp": created_at,
            "protocol": "abaqus-codex-readonly/1",
            "expires_at": created_at + float(timeout_seconds),
        }

        try:
            try:
                with temporary_path.open("x", encoding="utf-8") as stream:
                    json.dump(command, stream, ensure_ascii=False)
                # 临时文件没有 .json 后缀，插件不会提前读取半写入内容。
                os.replace(str(temporary_path), str(command_path))
            except OSError as error:
                raise ReadOnlyBridgeError(
                    "无法发布只读 MCP 请求；请检查目录权限后重试。"
                ) from error

            deadline = self.monotonic_clock() + float(timeout_seconds)
            while self.monotonic_clock() < deadline:
                if result_path.is_file():
                    try:
                        return self._read_result(result_path, request_id)
                    except _ResultNotReady:
                        # 第三方插件直接写最终文件，极短时间内可能只有半段 JSON。
                        pass
                self.sleeper(self.poll_interval_seconds)
            raise BridgeTimeoutError(
                "Abaqus 在 {0:.1f} 秒内没有返回模型概要；模型未改变。".format(
                    timeout_seconds
                )
            )
        finally:
            # 这里只删除本次随机 ID 对应的文件，不清理其他客户端的命令。
            for path in (temporary_path, command_path, result_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    # 清理失败不应掩盖更有帮助的连接或协议错误。
                    pass

    def _read_result(
        self, result_path: Path, request_id: str
    ) -> Dict[str, object]:
        """读取并校验本次响应，拒绝过大或错配的数据。"""

        try:
            # 从同一个句柄最多读取上限加一字节，避免 stat 后文件继续增长。
            with result_path.open("rb") as stream:
                raw_result = stream.read(MAX_RESULT_BYTES + 1)
        except OSError as error:
            raise _ResultNotReady("Abaqus 响应暂时无法读取。") from error
        if len(raw_result) > MAX_RESULT_BYTES:
            raise BridgeProtocolError("Abaqus 响应超过 2 MiB 安全上限。")

        try:
            result = json.loads(raw_result.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _ResultNotReady("Abaqus 响应仍在写入。") from error
        if not isinstance(result, dict):
            raise BridgeProtocolError("Abaqus 响应必须是 JSON 对象。")
        if result.get("id") != request_id:
            raise BridgeProtocolError("Abaqus 响应 ID 与本次请求不一致。")
        if not result.get("success"):
            # 第三方错误可能包含工程路径或用户名，界面只显示安全摘要。
            raise ReadOnlyBridgeError(
                "Abaqus 只读查询返回失败；请在本机检查 MCP 日志。"
            )
        return result


__all__ = [
    "BridgeOfflineError",
    "BridgeProtocolError",
    "BridgeTimeoutError",
    "FileIpcReadOnlyBridge",
    "ReadOnlyBridgeError",
    "READ_ONLY_COMMANDS",
    "default_mcp_home",
]
