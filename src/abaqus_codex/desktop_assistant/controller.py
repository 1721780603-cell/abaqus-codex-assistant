# -*- coding: utf-8 -*-
"""桌面助手的纯 Python 状态逻辑，不创建 Tk 窗口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from abaqus_codex.desktop_assistant.bridge import (
    BridgeOfflineError,
    BridgeProtocolError,
    BridgeTimeoutError,
    ReadOnlyBridgeError,
)
from abaqus_codex.desktop_assistant.snapshot import (
    ModelSnapshot,
    format_snapshot,
    normalize_model_info,
)
from abaqus_codex.desktop_assistant.material_flow import (
    MaterialCommandError,
    MaterialEditRequest,
    parse_material_command,
)
from abaqus_codex.desktop_assistant.rectangle_flow import (
    RectangleCommandError,
    RectangleCreateRequest,
    parse_rectangle_command,
)
from abaqus_codex.desktop_assistant.guided_rectangle_flow import (
    GuidedCommandError,
    GuidedStageRequest,
    parse_guided_command,
)


MAX_COMMAND_LENGTH = 500


class ReadOnlyBridge(Protocol):
    """真实桥接和模拟桥接共同实现的最小接口。"""

    is_mock: bool
    source_kind: str
    mode_name: str

    def inspect_status(self) -> dict[str, object]:
        """返回桥接健康状态。"""

    def get_model_info(self, timeout_seconds: float = 5.0) -> dict[str, object]:
        """返回当前模型的有限概要。"""


@dataclass(frozen=True)
class AssistantViewState:
    """一次刷新后界面需要展示的完整只读状态。"""

    tone: str
    connection_text: str
    summary_text: str
    log_text: str
    snapshot: Optional[ModelSnapshot]
    model_changed: bool = False


@dataclass(frozen=True)
class CommandDecision:
    """中文输入的第一阶段本地判断结果。"""

    action: str
    response: str
    material_request: Optional[MaterialEditRequest] = None
    rectangle_request: Optional[RectangleCreateRequest] = None
    guided_request: Optional[GuidedStageRequest] = None


def normalize_command(value: object) -> str:
    """限制用户输入长度，并确保控制字符不会进入界面日志。"""

    if not isinstance(value, str):
        value = str(value)
    cleaned = "".join(
        character if ord(character) >= 32 and ord(character) != 127 else " "
        for character in value
    )
    return " ".join(cleaned.split())[:MAX_COMMAND_LENGTH]


def classify_command(value: object) -> CommandDecision:
    """识别只读刷新、矩形和材料固定命令，不进行开放式 AI 推断。"""

    command = normalize_command(value)
    if not command:
        return CommandDecision("empty", "请先输入一条中文问题或查看命令。")

    try:
        rectangle_request = parse_rectangle_command(command)
    except RectangleCommandError as error:
        return CommandDecision("invalid_rectangle", str(error))
    if rectangle_request is not None:
        return CommandDecision(
            "rectangle_plan",
            (
                "已识别二维矩形板几何命令。接下来只生成第一步几何计划；"
                "材料、分析步和网格仍需在后续教学步骤中完成。"
            ),
            rectangle_request=rectangle_request,
        )

    try:
        guided_request = parse_guided_command(command)
    except GuidedCommandError as error:
        return CommandDecision("invalid_guided", str(error))
    if guided_request is not None:
        return CommandDecision(
            "guided_stage",
            (
                "已识别矩形板离线向导第 {0}/10 步。"
                "本地固定规则不会联网，也不会调用 AI。"
            ).format(
                {
                    "material": 2,
                    "section": 3,
                    "assembly": 4,
                    "step": 5,
                    "interaction": 6,
                    "bcs": 7,
                    "mesh": 8,
                    "job": 9,
                    "results": 10,
                }[guided_request.stage]
            ),
            guided_request=guided_request,
        )

    try:
        material_request = parse_material_command(command)
    except MaterialCommandError as error:
        return CommandDecision("invalid_material", str(error))
    if material_request is not None:
        return CommandDecision(
            "material_plan",
            (
                "已识别材料弹性参数命令。接下来只读取实时旧值并生成计划；"
                "在你点击“应用修改”前不会改变模型。"
            ),
            material_request=material_request,
        )

    refresh_phrases = (
        "查看模型",
        "刷新模型",
        "读取模型",
        "模型信息",
        "当前模型",
        "检查模型",
    )
    if any(phrase in command for phrase in refresh_phrases):
        return CommandDecision(
            "refresh",
            "将执行一次固定的只读模型概要查询；不会修改模型。",
        )

    return CommandDecision(
        "not_available",
        (
            "这条命令尚不在第一版白名单中。\n\n"
            "目前支持二维矩形板拉伸的十步离线向导，以及修改已有简单材料。"
            "请使用界面自动填入的当前步骤句式。AI 咨询和联网搜索尚未接入，"
            "因此这条命令没有改变模型。"
        ),
    )


def refresh_read_only(bridge: ReadOnlyBridge) -> AssistantViewState:
    """检查心跳并读取快照；任何失败都明确说明模型未改变。"""

    source_kind = getattr(bridge, "source_kind", "mcp")
    try:
        health = bridge.inspect_status()
        if not health.get("responsive"):
            status = str(health.get("status", "offline"))
            if source_kind == "snapshot":
                if status == "missing":
                    problem = "还没有生成一次性只读快照。"
                elif status == "stale":
                    problem = "最近的只读快照已经超过五分钟。"
                elif status == "dead-process":
                    problem = "生成快照的 Abaqus 会话已经关闭。"
                elif status in ("invalid", "future"):
                    problem = "最新快照没有通过安全校验。"
                else:
                    problem = "一次性只读快照当前不可用。"
                next_steps = (
                    "1. 打开 Abaqus/CAE 2021 和目标模型；\n"
                    "2. 点击 Plug-ins → Abaqus Codex Assistant → "
                    "Refresh Read-Only Snapshot；\n"
                    "3. 回到本窗口点击“刷新模型”。"
                )
            else:
                if status == "missing":
                    problem = "没有发现 Abaqus MCP 连接组件。"
                elif status == "stale":
                    problem = "Abaqus MCP 连接信息已经过期。"
                elif status == "dead-process":
                    problem = "上次连接的 Abaqus 已经关闭。"
                else:
                    problem = "Abaqus MCP 连接组件当前没有响应。"
                next_steps = (
                    "1. 打开 Abaqus/CAE 2021 和目标模型；\n"
                    "2. 在 Abaqus 的 Plug-ins 菜单启动 MCP；\n"
                    "3. 回到本窗口点击“刷新模型”。"
                )
            return AssistantViewState(
                tone="offline",
                connection_text=(
                    "快照未就绪" if source_kind == "snapshot" else "未连接"
                ),
                summary_text=(
                    "尚未读取模型。\n\n发生了什么：{0}\n"
                    "模型是否改变：没有。\n下一步：\n{1}"
                ).format(problem, next_steps),
                log_text=(
                    "快照检查未通过，模型未改变。"
                    if source_kind == "snapshot"
                    else "连接检查未通过，模型未改变。"
                ),
                snapshot=None,
            )

        payload = bridge.get_model_info(timeout_seconds=5.0)
        if bridge.is_mock:
            source = "内置模拟数据"
        elif source_kind == "snapshot":
            source = "Abaqus 2021 手动一次性快照"
        else:
            source = "Abaqus 2021 MCP 当前会话"
        snapshot = normalize_model_info(
            payload, source=source, is_mock=bridge.is_mock
        )
    except (ReadOnlyBridgeError, OSError, ValueError) as error:
        if isinstance(error, BridgeTimeoutError):
            problem = "Abaqus 连接组件在五秒内没有返回。"
        elif isinstance(error, BridgeOfflineError):
            problem = (
                "读取过程中一次性快照变得不可用。"
                if source_kind == "snapshot"
                else "读取过程中 Abaqus 连接已断开。"
            )
        elif isinstance(error, BridgeProtocolError):
            problem = "返回的模型概要不完整或超过安全上限。"
        elif isinstance(error, OSError):
            problem = "当前用户无法访问本地连接目录。"
        else:
            problem = "本地只读查询没有完成。"
        return AssistantViewState(
            tone="error",
            connection_text="读取失败",
            summary_text=(
                "模型概要没有读取完成。\n\n发生了什么：{0}\n"
                "模型是否改变：没有。\n"
                "下一步：确认 Abaqus 仍可操作，然后重新生成一次快照或只重试一次。"
            ).format(problem),
            log_text="只读查询失败，模型未改变。",
            snapshot=None,
        )

    return AssistantViewState(
        tone="mock" if bridge.is_mock else "online",
        connection_text=(
            "模拟模式"
            if bridge.is_mock
            else ("快照已读取" if source_kind == "snapshot" else "已连接")
        ),
        summary_text=format_snapshot(snapshot),
        log_text=(
            "模拟模型概要已载入。"
            if bridge.is_mock
            else "已读取当前模型概要，模型未改变。"
        ),
        snapshot=snapshot,
    )


__all__ = [
    "AssistantViewState",
    "CommandDecision",
    "classify_command",
    "normalize_command",
    "refresh_read_only",
]
