# -*- coding: utf-8 -*-
"""Abaqus 中文建模助手的安全计划、矩形几何和材料修改窗口。"""

from __future__ import annotations

import math
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk

from abaqus_codex.desktop_assistant.bridge import FileIpcReadOnlyBridge
from abaqus_codex.desktop_assistant.controller import (
    AssistantViewState,
    classify_command,
    refresh_read_only,
)
from abaqus_codex.desktop_assistant.mock_bridge import MockReadOnlyBridge
from abaqus_codex.desktop_assistant.assistant_history import (
    AssistantHistoryStore,
    format_history,
)
from abaqus_codex.desktop_assistant.beginner_guide import format_beginner_guide
from abaqus_codex.desktop_assistant.material_flow import (
    MaterialCommandError,
    MaterialEditRequest,
    build_material_plan,
    format_material_plan,
)
from abaqus_codex.desktop_assistant.rectangle_flow import (
    DEFAULT_RECTANGLE_COMMAND,
    RectangleCommandError,
    RectangleCreateRequest,
    build_rectangle_plan,
    format_rectangle_plan,
)
from abaqus_codex.desktop_assistant.guided_rectangle_flow import (
    DEFAULT_COMMANDS,
    GuidedCommandError,
    GuidedStageRequest,
    NEXT_STAGE,
    STAGE_INTERACTION,
    STAGE_JOB,
    STAGE_NUMBERS,
    STAGE_RESULTS,
    build_guided_plan,
    format_guided_plan,
)
from abaqus_codex.desktop_assistant.safe_action_bridge import (
    SafeActionBridgeError,
    SafeActionFileBridge,
    SafeActionTimeoutError,
)
from abaqus_codex.desktop_assistant.snapshot_source import SnapshotFileSource


# 界面采用克制的工程工作台语言：连接状态和确认边界始终比装饰更醒目。
COLOR_BACKGROUND = "#EDF2F5"
COLOR_PANEL = "#FFFFFF"
COLOR_HEADER = "#123247"
COLOR_HEADER_MUTED = "#C8D9E4"
COLOR_TEXT = "#16232C"
COLOR_MUTED = "#52636F"
COLOR_BORDER = "#C8D3DA"
COLOR_ACCENT = "#176B87"
COLOR_ACCENT_ACTIVE = "#11576F"
COLOR_SUCCESS = "#1F6F54"
COLOR_WARNING = "#946200"
COLOR_ERROR = "#A13C3C"
COLOR_DISABLED = "#D9E1E6"
PROJECT_OWNER = "1721780603-cell"
PROJECT_URL = "https://github.com/1721780603-cell/abaqus-codex-assistant"
COPYRIGHT_NOTICE = "© 2026 1721780603-cell · MIT"
BASE_DPI = 96.0
BASE_WINDOW_SIZE = (1120, 760)
BASE_MINIMUM_SIZE = (920, 720)
STATUS_FONT_SIZE = 10


def _ui_scale_from_dpi(dpi: float) -> float:
    """把可信的 Windows DPI 转为界面尺寸倍率。"""

    if not math.isfinite(dpi) or dpi < 72.0 or dpi > 384.0:
        return 1.0
    return dpi / BASE_DPI


def _window_metrics_for_dpi(dpi: float) -> tuple[int, int, int, int]:
    """返回按 DPI 同步后的默认宽高和最小宽高。"""

    scale = _ui_scale_from_dpi(dpi)
    values = BASE_WINDOW_SIZE + BASE_MINIMUM_SIZE
    return tuple(int(round(value * scale)) for value in values)


class DesktopAssistantApp:
    """保持 Abaqus 连接、模型摘要和中文输入在一个可扫描工作台中。"""

    def __init__(
        self,
        root: tk.Tk,
        bridge: object,
        action_bridge: Optional[object] = None,
        history_store: Optional[AssistantHistoryStore] = None,
    ) -> None:
        """创建窗口；耗时的模型读取会在后台线程中执行。"""

        self.root = root
        self.bridge = bridge
        self.action_bridge = action_bridge or bridge
        self.history_store = history_store or AssistantHistoryStore()
        try:
            current_dpi = float(self.root.winfo_fpixels("1i"))
        except (tk.TclError, TypeError, ValueError):
            current_dpi = BASE_DPI
        self.ui_scale = _ui_scale_from_dpi(current_dpi)
        self.font_family = "TkDefaultFont"
        self.result_queue: queue.Queue[AssistantViewState] = queue.Queue()
        self.action_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.refresh_running = False
        self.action_running = False
        self.pending_plan: Optional[dict[str, object]] = None
        # 计划类型单独保存，避免材料和几何误走同一个执行入口。
        self.pending_plan_type: Optional[str] = None
        self.current_guided_stage: Optional[str] = None
        self.current_step_number = 1
        self.latest_state: Optional[AssistantViewState] = None
        self.log_lines: list[str] = []
        self.guide_window: Optional[tk.Toplevel] = None
        self.history_window: Optional[tk.Toplevel] = None

        self.connection_var = tk.StringVar(value="正在检查")
        self.goal_var = tk.StringVar(
            value="当前小目标：第 1/10 步，用中文创建二维矩形板几何"
        )
        mode_name = getattr(bridge, "mode_name", "只读来源")
        self.mode_var = tk.StringVar(value="{0} · 待验证".format(mode_name))
        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self._bind_shortcuts()

        self._append_log("助手已启动；AI 未启用，几何和材料写操作等待明确确认。")
        self.root.after(150, self._start_refresh)
        self.root.after(100, self._drain_result_queue)
        # 初学者打开窗口后可以直接输入，不必先用鼠标寻找输入框。
        self.root.after(250, self.command_text.focus_set)

    def _configure_window(self) -> None:
        """设置适合与 Abaqus 并排使用的窗口大小。"""

        self.root.title("Abaqus 中文建模助手 · 初学者建模向导")
        width, height, minimum_width, minimum_height = _window_metrics_for_dpi(
            BASE_DPI * self.ui_scale
        )
        self.root.geometry("{0}x{1}".format(width, height))
        self.root.minsize(minimum_width, minimum_height)
        self.root.configure(background=COLOR_BACKGROUND)

        # 中文界面使用 Windows 常见字体；其他系统会自动回退。
        available = set(tkfont.families(self.root))
        try:
            fallback_family = tkfont.nametofont("TkDefaultFont").actual(
                "family"
            )
        except tk.TclError:
            fallback_family = "Segoe UI"
        self.font_family = (
            "Microsoft YaHei UI"
            if "Microsoft YaHei UI" in available
            else fallback_family
        )
        for named_font in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
        ):
            try:
                tkfont.nametofont(named_font).configure(
                    family=self.font_family, size=10
                )
            except tk.TclError:
                pass

    def _px(self, value: int) -> int:
        """把基础像素间距按当前显示器 DPI 缩放。"""

        return max(1, int(round(value * self.ui_scale)))

    def _font(self, size: int, weight: Optional[str] = None) -> tuple:
        """返回统一的中文字体角色，并保留系统回退。"""

        if weight is None:
            return (self.font_family, size)
        return (self.font_family, size, weight)

    def _configure_styles(self) -> None:
        """统一按钮、分组和键盘焦点的视觉状态。"""

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Assistant.TFrame", background=COLOR_BACKGROUND
        )
        style.configure(
            "Panel.TFrame", background=COLOR_PANEL
        )
        style.configure(
            "PanelTitle.TLabel",
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            font=self._font(12, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background=COLOR_PANEL,
            foreground=COLOR_MUTED,
            font=self._font(9),
            wraplength=self._px(480),
        )
        style.configure(
            "Accent.TButton",
            background=COLOR_ACCENT,
            foreground="#FFFFFF",
            padding=(self._px(14), self._px(8)),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLOR_ACCENT_ACTIVE), ("disabled", COLOR_DISABLED)],
            foreground=[("disabled", COLOR_MUTED)],
        )
        style.configure(
            "Secondary.TButton",
            background="#E7EEF2",
            foreground=COLOR_TEXT,
            padding=(self._px(12), self._px(8)),
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton", background=[("active", "#D9E5EB")]
        )
        style.configure(
            "Disabled.TButton",
            background=COLOR_DISABLED,
            foreground=COLOR_MUTED,
            padding=(self._px(14), self._px(8)),
            borderwidth=0,
        )

    def _build_layout(self) -> None:
        """创建顶部状态、模型摘要、中文输入和执行日志。"""

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self._build_header()

        workspace = ttk.Frame(
            self.root, style="Assistant.TFrame", padding=self._px(16)
        )
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=11, uniform="workspace")
        workspace.grid_columnconfigure(1, weight=10, uniform="workspace")

        self._build_model_panel(workspace)
        self._build_command_panel(workspace)
        self._build_footer()

    def _build_header(self) -> None:
        """显示产品名称、连接状态和当前唯一写能力。"""

        header = tk.Frame(
            self.root,
            background=COLOR_HEADER,
            padx=self._px(20),
            pady=self._px(16),
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Abaqus 中文建模助手",
            background=COLOR_HEADER,
            foreground="#FFFFFF",
            font=self._font(17, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.goal_label = tk.Label(
            header,
            textvariable=self.goal_var,
            background=COLOR_HEADER,
            foreground=COLOR_HEADER_MUTED,
            font=self._font(9),
        )
        self.goal_label.grid(
            row=1, column=0, sticky="w", pady=(self._px(3), 0)
        )

        self.connection_label = tk.Label(
            header,
            textvariable=self.connection_var,
            background=COLOR_WARNING,
            foreground="#FFFFFF",
            padx=self._px(13),
            pady=self._px(7),
            # 彩色底上的 9pt 粗体在 125% DPI 下笔画容易粘连；
            # 10pt 常规字重依靠状态底色表达层级，中文边缘更清楚。
            font=self._font(STATUS_FONT_SIZE),
        )
        self.connection_label.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(self._px(12), self._px(8)),
        )
        tk.Label(
            header,
            textvariable=self.mode_var,
            background="#244B61",
            foreground="#FFFFFF",
            padx=self._px(13),
            pady=self._px(7),
            font=self._font(STATUS_FONT_SIZE),
        ).grid(row=0, column=2, rowspan=2)

    def _panel(self, parent: tk.Widget, column: int) -> tk.Frame:
        """创建有明确边界但不过度装饰的主工作区。"""

        panel = tk.Frame(
            parent,
            background=COLOR_PANEL,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=self._px(16),
            pady=self._px(16),
        )
        panel.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0, self._px(8))
            if column == 0
            else (self._px(8), 0),
        )
        panel.grid_columnconfigure(0, weight=1)
        return panel

    def _build_model_panel(self, parent: tk.Widget) -> None:
        """构建当前模型摘要区域。"""

        panel = self._panel(parent, 0)
        panel.grid_rowconfigure(5, weight=1)
        ttk.Label(panel, text="当前模型", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text="只读取模型、零件、材料、分析步和接触等对象名称；完整路径不会显示。",
            style="Hint.TLabel",
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(self._px(4), self._px(12)),
        )

        ttk.Label(
            panel,
            text="初学者建模路线",
            style="PanelTitle.TLabel",
        ).grid(row=2, column=0, sticky="w")
        self.workflow_label = tk.Label(
            panel,
            text=(
                "① 几何 → ② 材料 → ③ 截面\n"
                "④ 装配 → ⑤ 分析步 → ⑥ 相互作用\n"
                "⑦ 边界与载荷 → ⑧ 网格 → ⑨ Job → ⑩ 结果与报告\n"
                "离线向导：本轮目标全部可用｜AI / 联网：尚未接入"
            ),
            background="#EAF4F7",
            foreground=COLOR_TEXT,
            justify="left",
            anchor="w",
            padx=self._px(10),
            pady=self._px(8),
            font=self._font(9),
        )
        self.workflow_label.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(self._px(5), self._px(10)),
        )

        route_actions = ttk.Frame(panel, style="Panel.TFrame")
        route_actions.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(0, self._px(10)),
        )
        ttk.Button(
            route_actions,
            text="查看十步指令",
            style="Secondary.TButton",
            command=self._show_beginner_guide,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            route_actions,
            text="操作记录",
            style="Secondary.TButton",
            command=self._show_history,
        ).grid(row=0, column=1, sticky="w", padx=(self._px(8), 0))

        self.summary_text = scrolledtext.ScrolledText(
            panel,
            wrap="word",
            height=24,
            padx=self._px(12),
            pady=self._px(12),
            relief="flat",
            borderwidth=0,
            background="#F7F9FA",
            foreground=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground="#BBD6E3",
            font=self._font(10),
            takefocus=False,
        )
        self.summary_text.grid(row=5, column=0, sticky="nsew")
        self._set_readonly_text(
            self.summary_text,
            (
                "正在检查最近一次只读快照，请稍候……"
                if getattr(self.bridge, "source_kind", "mcp") == "snapshot"
                else "正在检查 Abaqus MCP 状态，请稍候……"
            ),
        )

        self.refresh_button = ttk.Button(
            panel,
            text="刷新模型",
            style="Accent.TButton",
            command=self._start_refresh,
        )
        self.refresh_button.grid(
            row=6, column=0, sticky="w", pady=(self._px(12), 0)
        )

    def _show_text_window(
        self,
        *,
        attribute: str,
        title: str,
        content: str,
    ) -> None:
        """复用一个非模态只读窗口展示路线或历史。"""

        existing = getattr(self, attribute, None)
        if existing is not None and existing.winfo_exists():
            text_widget = getattr(existing, "content_text", None)
            if text_widget is not None:
                self._set_readonly_text(text_widget, content)
                text_widget.see("1.0")
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return

        window = tk.Toplevel(self.root)
        setattr(self, attribute, window)
        window.title(title)
        window.geometry(
            "{0}x{1}".format(self._px(760), self._px(680))
        )
        window.minsize(self._px(620), self._px(480))
        window.configure(background=COLOR_BACKGROUND)
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)
        text_widget = scrolledtext.ScrolledText(
            window,
            wrap="word",
            padx=self._px(16),
            pady=self._px(16),
            relief="flat",
            borderwidth=0,
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            selectbackground="#BBD6E3",
            font=self._font(10),
            takefocus=True,
        )
        text_widget.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=self._px(14),
            pady=(self._px(14), self._px(8)),
        )
        window.content_text = text_widget
        self._set_readonly_text(text_widget, content)
        ttk.Button(
            window,
            text="关闭",
            style="Secondary.TButton",
            command=window.destroy,
        ).grid(
            row=1,
            column=0,
            sticky="e",
            padx=self._px(14),
            pady=(0, self._px(14)),
        )
        window.bind("<Escape>", lambda _event: window.destroy())

    def _show_beginner_guide(self) -> None:
        """显示当前步骤和完整十步固定句式。"""

        self._show_text_window(
            attribute="guide_window",
            title="矩形板拉伸十步指令",
            content=format_beginner_guide(self.current_step_number),
        )

    def _show_history(self) -> None:
        """显示持久化操作记录；读取失败按空历史处理。"""

        self._show_text_window(
            attribute="history_window",
            title="Abaqus 中文建模助手操作记录",
            content=format_history(self.history_store.read()),
        )

    def _record_history(self, *, title: str, status: str, details: str) -> None:
        """保存界面已展示的安全摘要，失败时不影响 Abaqus 操作。"""

        try:
            self.history_store.append(
                title=title,
                status=status,
                details=details,
            )
        except (OSError, ValueError):
            self._append_log("操作记录暂时无法保存；模型操作结果不受影响。")
            return
        history_window = self.history_window
        if history_window is not None and history_window.winfo_exists():
            text_widget = getattr(history_window, "content_text", None)
            if text_widget is not None:
                self._set_readonly_text(
                    text_widget,
                    format_history(self.history_store.read()),
                )

    def _build_command_panel(self, parent: tk.Widget) -> None:
        """构建中文输入、修改计划和安全执行日志区域。"""

        panel = self._panel(parent, 1)
        panel.grid_rowconfigure(6, weight=1)
        panel.grid_rowconfigure(9, weight=1)
        ttk.Label(panel, text="中文建模命令", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text=(
                "本阶段只做本地固定句式识别。未联网、未调用 AI、输入未上传；"
                "发送只生成计划，明确应用后才修改工作副本。"
            ),
            style="Hint.TLabel",
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(self._px(4), self._px(10)),
        )

        self.command_text = tk.Text(
            panel,
            height=5,
            wrap="word",
            padx=self._px(10),
            pady=self._px(10),
            relief="solid",
            borderwidth=1,
            background="#FFFFFF",
            foreground=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground="#BBD6E3",
            font=self._font(10),
            takefocus=True,
        )
        self.command_text.grid(row=2, column=0, sticky="ew")
        self.command_text.insert(
            "1.0",
            DEFAULT_RECTANGLE_COMMAND,
        )
        self.command_text.edit_modified(False)

        ttk.Label(
            panel,
            text="快捷键：Ctrl+Enter 生成计划；F5 刷新模型摘要。",
            style="Hint.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(self._px(5), 0))

        button_row = ttk.Frame(panel, style="Panel.TFrame")
        button_row.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(self._px(10), self._px(12)),
        )
        button_row.grid_columnconfigure(3, weight=1)
        self.send_button = ttk.Button(
            button_row,
            text="生成计划",
            style="Accent.TButton",
            command=self._handle_send,
        )
        self.send_button.grid(row=0, column=0, sticky="w")
        ttk.Button(
            button_row,
            text="清空",
            style="Secondary.TButton",
            command=self._clear_command,
        ).grid(row=0, column=1, sticky="w", padx=(self._px(8), 0))
        self.apply_button = ttk.Button(
            button_row,
            text="应用修改",
            style="Disabled.TButton",
            command=self._confirm_apply,
            state="disabled",
        )
        self.apply_button.grid(
            row=0, column=2, sticky="w", padx=(self._px(8), 0)
        )
        self.safety_label = tk.Label(
            button_row,
            text="尚无可应用计划｜不会自动修改模型",
            background=COLOR_PANEL,
            foreground=COLOR_ERROR,
            font=self._font(9, "bold"),
        )
        self.safety_label.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(self._px(8), 0),
        )

        ttk.Label(
            panel,
            text="修改计划（应用前不会修改模型）",
            style="PanelTitle.TLabel",
        ).grid(row=5, column=0, sticky="w")

        self.response_text = scrolledtext.ScrolledText(
            panel,
            wrap="word",
            height=10,
            padx=self._px(12),
            pady=self._px(12),
            relief="flat",
            borderwidth=0,
            background="#F7F9FA",
            foreground=COLOR_TEXT,
            selectbackground="#BBD6E3",
            font=self._font(10),
            takefocus=False,
        )
        self.response_text.grid(
            row=6, column=0, sticky="nsew", pady=(self._px(6), 0)
        )
        self._set_readonly_text(
            self.response_text,
            "尚未生成修改计划。应用按钮保持锁定。",
        )

        ttk.Label(panel, text="高级本地日志", style="PanelTitle.TLabel").grid(
            row=7, column=0, sticky="w", pady=(self._px(14), 0)
        )
        ttk.Label(
            panel,
            text="日志不记录完整命令、模型路径或凭据。",
            style="Hint.TLabel",
        ).grid(
            row=8,
            column=0,
            sticky="w",
            pady=(self._px(3), self._px(6)),
        )
        self.log_text = scrolledtext.ScrolledText(
            panel,
            wrap="word",
            height=7,
            padx=self._px(10),
            pady=self._px(10),
            relief="flat",
            borderwidth=0,
            background="#EEF3F5",
            foreground=COLOR_MUTED,
            selectbackground="#BBD6E3",
            font=self._font(9),
            takefocus=False,
        )
        self.log_text.grid(row=9, column=0, sticky="nsew")
        self._set_readonly_text(self.log_text, "")

    def _build_footer(self) -> None:
        """持续显示安全边界、原始作者和规范仓库来源。"""

        footer = tk.Frame(
            self.root,
            background="#DDE7EC",
            padx=self._px(18),
            pady=self._px(8),
        )
        footer.grid(row=2, column=0, sticky="ew")
        tk.Label(
            footer,
            text=(
                "安全原型：只支持固定矩形几何和已有单行各向同性弹性；"
                "应用时另存工作副本，不代表模型设置或结果合理。"
            ),
            background="#DDE7EC",
            foreground=COLOR_MUTED,
            anchor="w",
            font=self._font(9),
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            footer,
            text=COPYRIGHT_NOTICE + " · 官方仓库",
            background="#DDE7EC",
            foreground=COLOR_TEXT,
            anchor="e",
            font=self._font(9, "bold"),
        ).pack(side="right", padx=(self._px(12), 0))

    def _bind_shortcuts(self) -> None:
        """提供常见键盘操作，并避免回车意外触发未来写操作。"""

        self.root.bind("<F5>", self._on_refresh_shortcut)
        self.root.bind("<Control-Return>", self._on_send_shortcut)
        self.command_text.bind("<<Modified>>", self._on_command_modified)

    def _on_refresh_shortcut(self, event: object) -> str:
        """用 F5 刷新，并阻止按键继续传递给输入框。"""

        self._start_refresh()
        return "break"

    def _on_send_shortcut(self, event: object) -> str:
        """用 Ctrl+Enter 读取，并阻止输入框额外插入换行。"""

        self._handle_send()
        return "break"

    def _on_command_modified(self, event: object) -> None:
        """输入内容变化后立即废止旧计划，避免命令与计划错位。"""

        if not self.command_text.edit_modified():
            return
        self.command_text.edit_modified(False)
        if self.pending_plan is not None and not self.action_running:
            self._clear_pending_plan()
            self._set_readonly_text(
                self.response_text,
                "输入内容已经变化，旧修改计划已作废。请重新生成计划。",
            )
            self._append_log("输入发生变化，旧计划已作废。")

    @staticmethod
    def _set_readonly_text(widget: tk.Text, value: str) -> None:
        """更新只读文本，同时保留复制和选择能力。"""

        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _start_refresh(self) -> None:
        """在后台执行一次短超时查询，防止 Tk 主线程转圈。"""

        if self.refresh_running or self.action_running:
            return
        self._clear_pending_plan()
        self.refresh_running = True
        self.refresh_button.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.connection_var.set("正在读取")
        self.connection_label.configure(background=COLOR_WARNING)
        mode_name = getattr(self.bridge, "mode_name", "只读来源")
        self.mode_var.set("{0} · 正在验证".format(mode_name))
        self._append_log("正在执行固定只读查询。")
        worker = threading.Thread(target=self._refresh_worker, daemon=True)
        worker.start()

    def _refresh_worker(self) -> None:
        """后台线程只调用有限桥接接口，不触碰 Tk 控件。"""

        try:
            if getattr(self.bridge, "source_kind", "mcp") == "snapshot":
                self.action_bridge.refresh_readonly_snapshot(
                    timeout_seconds=5.0
                )
            state = refresh_read_only(self.bridge)
        except Exception:
            # 最后一层兜底确保按钮恢复；详细异常不进入界面或日志。
            state = AssistantViewState(
                tone="error",
                connection_text="读取失败",
                summary_text=(
                    "模型概要没有读取完成。\n\n"
                    "发生了什么：桌面助手遇到未预期的本地错误。\n"
                    "模型是否改变：没有。\n"
                    "下一步：关闭助手后重试；若重复出现，请提交不含模型文件的问题报告。"
                ),
                log_text="只读后台任务异常结束，模型未改变。",
                snapshot=None,
            )
        self.result_queue.put(state)

    def _drain_result_queue(self) -> None:
        """在 Tk 事件循环中接收模型刷新和材料动作结果。"""

        try:
            while True:
                state = self.result_queue.get_nowait()
                self._apply_state(state)
        except queue.Empty:
            pass
        try:
            while True:
                event_name, payload = self.action_queue.get_nowait()
                self._apply_action_event(event_name, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_result_queue)

    def _apply_state(self, state: AssistantViewState) -> None:
        """根据连接结果更新状态色、摘要和安全日志。"""

        colors = {
            "online": COLOR_SUCCESS,
            "mock": COLOR_WARNING,
            "offline": COLOR_ERROR,
            "error": COLOR_ERROR,
        }
        self.connection_var.set(state.connection_text)
        self.connection_label.configure(background=colors.get(state.tone, COLOR_WARNING))
        mode_name = getattr(self.bridge, "mode_name", "只读来源")
        if state.tone == "online":
            suffix = (
                "已读取"
                if getattr(self.bridge, "source_kind", "mcp") == "snapshot"
                else "已连接"
            )
            self.mode_var.set("{0} · {1}".format(mode_name, suffix))
        elif state.tone == "mock":
            self.mode_var.set("显式模拟 · 已载入")
        else:
            self.mode_var.set("{0} · 未就绪".format(mode_name))
        self._set_readonly_text(self.summary_text, state.summary_text)
        self._append_log(state.log_text)
        self.latest_state = state
        self.refresh_running = False
        self.refresh_button.configure(state="normal")
        self.send_button.configure(state="normal")

    def _handle_send(self) -> None:
        """本地识别查看或材料计划请求，不把规则匹配伪装成 AI。"""

        if self.refresh_running or self.action_running:
            return

        command = self.command_text.get("1.0", "end-1c")
        decision = classify_command(command)
        self._clear_pending_plan()
        self._set_readonly_text(self.response_text, decision.response)
        if decision.action == "refresh":
            self._append_log("中文输入已识别为只读刷新请求。")
            self._start_refresh()
        elif decision.action == "rectangle_plan" and decision.rectangle_request:
            self._prepare_rectangle_plan(decision.rectangle_request)
        elif decision.action == "guided_stage" and decision.guided_request:
            self._prepare_guided_stage(decision.guided_request)
        elif decision.action == "material_plan" and decision.material_request:
            if not self._snapshot_contains_target(decision.material_request):
                self._set_readonly_text(
                    self.response_text,
                    (
                        "当前模型摘要中没有同时找到指定模型和材料。\n\n"
                        "请先在 Abaqus 中打开目标 CAE，再刷新模型摘要；"
                        "对象名称必须与命令完全一致。模型没有改变。"
                    ),
                )
                self._append_log("材料目标未通过当前摘要核对，模型未改变。")
                return
            self._start_plan(decision.material_request)
        elif decision.action == "invalid_rectangle":
            self._append_log("矩形板命令格式未通过校验，模型未改变。")
        elif decision.action == "invalid_guided":
            self._append_log("向导命令格式未通过校验，模型未改变。")
        elif decision.action == "invalid_material":
            self._append_log("材料命令格式未通过校验，模型未改变。")
        elif decision.action == "empty":
            self._append_log("输入为空，没有执行任何操作。")
        else:
            self._append_log("当前命令不在首版白名单中，模型未改变。")

    def _prepare_rectangle_plan(self, request: RectangleCreateRequest) -> None:
        """只用最近快照生成几何计划，本步骤不修改 Abaqus。"""

        state = self.latest_state
        if state is None or state.snapshot is None:
            self._set_readonly_text(
                self.response_text,
                "尚未读取模型摘要。请先点击“刷新模型”，再生成几何计划。",
            )
            self._append_log("缺少模型摘要，未生成几何计划。")
            return

        model_exists = False
        part_exists = False
        for model in state.snapshot.models:
            if model.name == request.model_name:
                model_exists = True
                part_exists = request.part_name in model.parts
                break
        try:
            plan = build_rectangle_plan(
                request,
                snapshot_fingerprint=state.snapshot.fingerprint,
                model_exists=model_exists,
                part_exists=part_exists,
            )
        except RectangleCommandError as error:
            self._set_readonly_text(self.response_text, str(error))
            self._append_log("几何目标未通过当前摘要核对，模型未改变。")
            return
        self._apply_action_event("rectangle_plan_ready", plan)

    def _prepare_guided_stage(self, request: GuidedStageRequest) -> None:
        """生成一个离线向导步骤计划；相互作用检查点不写模型。"""

        if request.stage == STAGE_INTERACTION:
            response = (
                "【第 6/10 步完成：相互作用检查】\n\n"
                "当前教学模型只有一个连续矩形板零件，没有两个独立表面之间的"
                "接触、绑定或连接关系，因此本步骤不创建 Interaction。\n\n"
                "这不是忽略接触：只有模型包含多个可能相互接触的部件时，"
                "才需要定义接触属性和相互作用。\n\n"
                "下一步：第 7/10 步，边界条件与拉伸位移。"
            )
            self._set_readonly_text(
                self.response_text,
                response,
            )
            self._record_history(
                title="第 6/10 步｜相互作用检查",
                status="检查完成",
                details=response,
            )
            self._append_log("相互作用检查完成；单一连续体无需创建 Interaction。")
            self._set_next_guided_command(NEXT_STAGE[request.stage])
            return

        state = self.latest_state
        if state is None or state.snapshot is None:
            self._set_readonly_text(
                self.response_text,
                "尚未读取模型摘要。请先点击“刷新模型”，再生成向导计划。",
            )
            self._append_log("缺少模型摘要，未生成向导计划。")
            return
        if not any(
            model.name == request.model_name for model in state.snapshot.models
        ):
            self._set_readonly_text(
                self.response_text,
                "当前摘要中没有指定模型，请检查模型名并刷新。模型没有改变。",
            )
            self._append_log("向导模型名未通过当前摘要核对。")
            return
        try:
            plan = build_guided_plan(
                request,
                snapshot_fingerprint=state.snapshot.fingerprint,
            )
        except GuidedCommandError as error:
            self._set_readonly_text(self.response_text, str(error))
            self._append_log("向导计划未通过可信校验，模型未改变。")
            return
        self._apply_action_event(
            "guided_plan_ready", {"plan": plan, "stage": request.stage}
        )

    def _set_next_guided_command(self, stage: str) -> None:
        """成功后填入下一步示例，并清楚标出当前离线目标。"""

        self.current_guided_stage = stage
        self.current_step_number = STAGE_NUMBERS[stage]
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", DEFAULT_COMMANDS[stage])
        self.command_text.edit_modified(False)
        self.goal_var.set(
            "当前小目标：第 {0}/10 步，离线矩形板拉伸向导".format(
                STAGE_NUMBERS[stage]
            )
        )

    def _snapshot_contains_target(self, request: MaterialEditRequest) -> bool:
        """先用最近摘要检查对象名，减少给初学者的往返错误。"""

        state = self.latest_state
        if state is None or state.snapshot is None:
            return False
        for model in state.snapshot.models:
            if model.name == request.model_name:
                return request.material_name in model.materials
        return False

    def _start_plan(self, request: MaterialEditRequest) -> None:
        """在后台读取实时旧值并构造计划；本步骤没有写操作。"""

        self.action_running = True
        self.command_text.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.safety_label.configure(
            text="正在读取实时旧值｜尚未修改模型", foreground=COLOR_WARNING
        )
        self._append_log("正在读取一个材料的实时弹性旧值。")
        threading.Thread(
            target=self._plan_worker,
            args=(request,),
            daemon=True,
        ).start()

    def _plan_worker(self, request: MaterialEditRequest) -> None:
        """后台调用固定材料读取接口，并把安全结果送回 Tk 主线程。"""

        try:
            current = self.action_bridge.inspect_material_elastic(
                request.model_name,
                request.material_name,
                timeout_seconds=5.0,
            )
            plan = build_material_plan(request, current)
        except (SafeActionBridgeError, MaterialCommandError, OSError) as error:
            self.action_queue.put(("plan_error", str(error)))
        except Exception:
            self.action_queue.put(
                ("plan_error", "生成计划时遇到未预期的本地错误。")
            )
        else:
            self.action_queue.put(("plan_ready", plan))

    def _apply_action_event(self, event_name: str, payload: object) -> None:
        """只在 Tk 主线程中改变按钮、计划和可见文字。"""

        self.action_running = False
        self.command_text.configure(state="normal")
        self.command_text.edit_modified(False)
        self.refresh_button.configure(state="normal")
        self.send_button.configure(state="normal")
        if event_name == "plan_ready" and isinstance(payload, dict):
            self.pending_plan = payload
            self.pending_plan_type = "material"
            formatted_plan = format_material_plan(payload)
            self._set_readonly_text(
                self.response_text, formatted_plan
            )
            self._record_history(
                title="独立材料修改计划",
                status="计划待确认",
                details=formatted_plan,
            )
            self.apply_button.configure(state="normal", style="Accent.TButton")
            self.safety_label.configure(
                text="计划已就绪｜只有点击“应用修改”才会写入",
                foreground=COLOR_SUCCESS,
            )
            self._append_log("材料修改计划已生成，尚未修改模型。")
        elif event_name == "rectangle_plan_ready" and isinstance(payload, dict):
            self.pending_plan = payload
            self.pending_plan_type = "rectangle"
            formatted_plan = format_rectangle_plan(payload)
            self._set_readonly_text(
                self.response_text, formatted_plan
            )
            self._record_history(
                title="第 1/10 步｜几何修改计划",
                status="计划待确认",
                details=formatted_plan,
            )
            self.apply_button.configure(state="normal", style="Accent.TButton")
            self.safety_label.configure(
                text="几何计划已就绪｜点击“应用修改”才会创建零件",
                foreground=COLOR_SUCCESS,
            )
            self._append_log("矩形板几何计划已生成，尚未修改模型。")
        elif event_name == "guided_plan_ready" and isinstance(payload, dict):
            plan = payload.get("plan")
            stage = payload.get("stage")
            if not isinstance(plan, dict) or not isinstance(stage, str):
                self._set_readonly_text(
                    self.response_text, "向导计划格式无效，模型没有改变。"
                )
                return
            self.pending_plan = plan
            self.pending_plan_type = "guided:" + stage
            formatted_plan = format_guided_plan(plan, stage)
            self._set_readonly_text(
                self.response_text, formatted_plan
            )
            self._record_history(
                title="第 {0}/10 步｜修改计划".format(STAGE_NUMBERS[stage]),
                status="计划待确认",
                details=formatted_plan,
            )
            self.apply_button.configure(state="normal", style="Accent.TButton")
            self.safety_label.configure(
                text=(
                    "结果计划已就绪｜点击“应用修改”才读取并生成报告"
                    if stage == STAGE_RESULTS
                    else "向导计划已就绪｜点击“应用修改”才执行"
                ),
                foreground=COLOR_SUCCESS,
            )
            self._append_log(
                "第 {0}/10 步计划已生成，尚未执行。".format(
                    STAGE_NUMBERS[stage]
                )
            )
        elif event_name == "apply_success" and isinstance(payload, dict):
            after = payload["after"]
            success_text = (
                "【应用成功】\n"
                "模型：{0}\n材料：{1}\n"
                "新弹性模量：{2:g} MPa\n新泊松比：{3:g}\n\n"
                "Abaqus 当前会话已切换到受保护工作副本：{4}\n"
                "原 CAE 文件没有被覆盖。请回到 Abaqus 检查材料并保存后续工作。"
            ).format(
                payload["model"],
                payload["material"],
                after["youngs_modulus"],
                after["poisson_ratio"],
                payload["working_copy_name"],
            )
            self._set_readonly_text(
                self.response_text,
                success_text,
            )
            self._record_history(
                title="独立材料修改结果",
                status="执行成功",
                details=success_text,
            )
            self.safety_label.configure(
                text="修改已写入受保护工作副本｜原文件未覆盖",
                foreground=COLOR_SUCCESS,
            )
            self._append_log("材料修改成功，原 CAE 文件未覆盖。")
        elif event_name == "rectangle_apply_success" and isinstance(payload, dict):
            success_text = (
                "【第 1/10 步完成：几何已创建】\n"
                "模型：{0}\n零件：{1}\n"
                "尺寸：{2:g} mm × {3:g} mm\n\n"
                "Abaqus 当前会话已切换到受保护工作副本：{4}\n"
                "原 CAE 文件没有被覆盖。请回到 Abaqus 检查矩形板。\n\n"
                "下一步：第 2/10 步，定义材料。"
            ).format(
                payload["model"],
                payload["part"],
                payload["length"],
                payload["width"],
                payload["working_copy_name"],
            )
            self._set_readonly_text(
                self.response_text,
                success_text,
            )
            self._record_history(
                title="第 1/10 步｜几何执行结果",
                status="执行成功",
                details=success_text,
            )
            self.safety_label.configure(
                text="几何已写入受保护工作副本｜下一步定义材料",
                foreground=COLOR_SUCCESS,
            )
            self._append_log("矩形板几何创建成功，原 CAE 文件未覆盖。")
            self._set_next_guided_command("material")
            self.root.after(300, self._start_refresh)
        elif event_name == "guided_apply_success" and isinstance(payload, dict):
            stage = str(payload.get("stage", ""))
            success_text = self._format_guided_success(payload)
            self._set_readonly_text(
                self.response_text, success_text
            )
            self._record_history(
                title="第 {0}/10 步｜执行结果".format(
                    STAGE_NUMBERS.get(stage, 0)
                ),
                status="执行成功",
                details=success_text,
            )
            if stage == STAGE_RESULTS:
                self.safety_label.configure(
                    text="离线十步向导已完成｜CAE 未修改",
                    foreground=COLOR_SUCCESS,
                )
                self.goal_var.set("离线十步向导已完成｜联网 / AI 尚未接入")
            else:
                self.safety_label.configure(
                    text="本步骤已写入新工作副本｜原文件未覆盖",
                    foreground=COLOR_SUCCESS,
                )
                next_stage = NEXT_STAGE.get(stage)
                if next_stage:
                    self._set_next_guided_command(next_stage)
                self.root.after(300, self._start_refresh)
            self._append_log(
                "第 {0}/10 步成功；未记录本机路径。".format(
                    STAGE_NUMBERS.get(stage, 0)
                )
            )
        else:
            message = str(payload)
            failure_text = (
                "操作没有明确成功。\n\n{0}\n\n模型原文件不会被覆盖。"
            ).format(message)
            self._set_readonly_text(
                self.response_text,
                failure_text,
            )
            self._record_history(
                title="计划生成失败" if event_name == "plan_error" else "执行未成功",
                status="计划失败" if event_name == "plan_error" else "执行失败",
                details=failure_text,
            )
            self.safety_label.configure(
                text="没有可应用计划｜请检查提示后重新生成",
                foreground=COLOR_ERROR,
            )
            self._append_log("向导操作没有明确成功；未记录本机路径。")

    def _format_guided_success(self, payload: dict[str, object]) -> str:
        """把严格回执转换为简洁的步骤完成说明。"""

        stage = str(payload["stage"])
        number = STAGE_NUMBERS[stage]
        if stage == STAGE_RESULTS:
            return (
                "【第 10/10 步完成：结果与报告】\n"
                "Job：{0}\n最大位移模：{1:.8g} mm\n"
                "最大 Mises 应力：{2:.8g} MPa\n"
                "中文报告：{3}\n\n"
                "CAE 模型没有修改。离线确定性向导已经完成；"
                "联网和 AI 咨询仍未接入。"
            ).format(
                payload["job"],
                payload["maximum_displacement"],
                payload["maximum_mises_stress"],
                payload["report_name"],
            )
        details = payload["details"]
        stage_titles = {
            "material": "材料已创建",
            "section": "截面已创建并赋予",
            "assembly": "实例已装配",
            "step": "静力分析步已创建",
            "bcs": "边界条件与拉伸位移已创建",
            "mesh": "网格已划分",
            "job": "Job 已创建并提交",
        }
        # 用小函数延迟读取字段：每种回执只包含当前步骤的数据，
        # 不能在材料步骤提前访问截面、网格或 Job 字段。
        detail_builders = {
            "material": lambda: [
                "材料：{0}".format(details["material"]),
                "E = {0:g} MPa，ν = {1:g}".format(
                    details["youngs_modulus"], details["poisson_ratio"]
                ),
            ],
            "section": lambda: [
                "截面：{0}，零件：{1}".format(
                    details["section"], details["part"]
                ),
                "材料：{0}，厚度：{1:g} mm".format(
                    details["material"], details["thickness"]
                ),
            ],
            "assembly": lambda: [
                "零件：{0}，实例：{1}".format(
                    details["part"], details["instance"]
                )
            ],
            "step": lambda: [
                "分析步：{0}，前一步：{1}".format(
                    details["step"], details["previous_step"]
                ),
                "场输出：S、U",
            ],
            "bcs": lambda: [
                "实例：{0}，分析步：{1}".format(
                    details["instance"], details["step"]
                ),
                "右边水平位移：{0:g} mm".format(
                    details["right_displacement"]
                ),
            ],
            "mesh": lambda: [
                "零件：{0}，网格尺寸：{1:g} mm".format(
                    details["part"], details["size"]
                ),
                "节点：{0}，单元：{1}".format(
                    details["node_count"], details["element_count"]
                ),
            ],
            "job": lambda: [
                "Job：{0}，CPU：{1}".format(
                    details["job"], details["num_cpus"]
                ),
                "状态：{0}；本步骤不阻塞等待。".format(details["status"]),
            ],
        }
        detail_lines = detail_builders[stage]()
        next_stage = NEXT_STAGE.get(stage)
        lines = [
            "【第 {0}/10 步完成：{1}】".format(number, stage_titles[stage]),
        ] + detail_lines + [
            "",
            "Abaqus 已切换到受保护工作副本：{0}".format(
                payload["working_copy_name"]
            ),
            "原 CAE 文件没有被覆盖。",
        ]
        if next_stage:
            lines.extend([
                "",
                "下一步：第 {0}/10 步。".format(STAGE_NUMBERS[next_stage]),
            ])
        return "\n".join(lines)

    def _confirm_apply(self) -> None:
        """只有按钮点击和二次确认同时发生时才发布写请求。"""

        if self.action_running or self.pending_plan is None:
            return
        plan_type = self.pending_plan_type
        is_rectangle = plan_type == "rectangle"
        guided_stage = (
            plan_type.split(":", 1)[1]
            if isinstance(plan_type, str) and plan_type.startswith("guided:")
            else None
        )
        is_results = guided_stage == STAGE_RESULTS
        is_job = guided_stage == STAGE_JOB
        if is_results:
            title = "确认读取结果并生成报告"
            confirmation_text = (
                "将从当前 CAE 同目录读取计划中指定 Job 的 ODB，"
                "计算最大位移模和最大 Mises 应力，并新建一份中文 Markdown 报告。\n\n"
                "不会修改 CAE，也不会覆盖已有报告。是否继续？"
            )
        elif guided_stage is not None:
            title = (
                "确认创建并提交 Job"
                if is_job
                else "确认执行第 {0}/10 步".format(STAGE_NUMBERS[guided_stage])
            )
            confirmation_text = (
                "Abaqus 将先在原文件同目录创建一个新的 CAE 工作副本，"
                "再执行计划中显示的单个白名单步骤。原 CAE 文件不会被覆盖。\n\n"
                + (
                    "提交 Job 会占用 Abaqus 许可证和本机计算资源；"
                    "本步骤只提交，不阻塞等待或自动重试。\n\n"
                    if is_job
                    else ""
                )
                + "请确认当前模型采用 mm-N-s-MPa 单位约定。是否继续？"
            )
        else:
            title = "确认创建矩形板" if is_rectangle else "确认应用材料修改"
            confirmation_text = (
                "Abaqus 将先在原文件同目录创建一个新的 CAE 工作副本，"
                + ("再在副本中创建二维矩形板几何。" if is_rectangle else "再在副本中修改材料。")
                + "原 CAE 文件不会被覆盖。\n\n"
                + (
                    "本次只创建几何，不会自动创建材料、载荷或网格。\n"
                    if is_rectangle
                    else ""
                )
                + "请确认当前模型采用 mm-N-s-MPa 单位约定。是否继续？"
            )
        accepted = messagebox.askyesno(
            title,
            confirmation_text,
            parent=self.root,
            icon="warning",
        )
        if not accepted:
            self._append_log("用户取消应用，模型未改变。")
            return

        # 计划在发布前即从界面消费，避免双击或超时后盲目重试。
        plan = self.pending_plan
        self._clear_pending_plan()
        self.action_running = True
        self.command_text.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.safety_label.configure(
            text=(
                "正在读取 ODB 并生成报告｜请勿重复点击"
                if is_results
                else (
                    "正在创建并提交 Job｜请勿重复点击"
                    if is_job
                    else "正在创建工作副本并应用｜请勿重复点击"
                )
            ),
            foreground=COLOR_WARNING,
        )
        if guided_stage is not None:
            self._append_log(
                "用户已确认第 {0}/10 步白名单动作。".format(
                    STAGE_NUMBERS[guided_stage]
                )
            )
        else:
            self._append_log(
                "用户已确认，正在提交一个白名单几何动作。"
                if is_rectangle
                else "用户已确认，正在提交一个白名单材料动作。"
            )
        threading.Thread(
            target=self._apply_worker,
            args=(plan, plan_type),
            daemon=True,
        ).start()

    def _apply_worker(
        self, plan: dict[str, object], plan_type: Optional[str]
    ) -> None:
        """后台应用一次性计划，绝不向桥接发送任意 Python。"""

        try:
            if plan_type == "rectangle":
                receipt = self.action_bridge.apply_rectangle_plan(
                    plan, timeout_seconds=30.0
                )
            elif isinstance(plan_type, str) and plan_type.startswith("guided:"):
                receipt = self.action_bridge.apply_guided_plan(
                    plan, timeout_seconds=30.0
                )
            else:
                receipt = self.action_bridge.apply_material_plan(
                    plan, timeout_seconds=30.0
                )
        except SafeActionTimeoutError as error:
            if error.outcome_unknown:
                message = (
                    "Abaqus 已领取请求但尚未返回结果。不要重复应用；"
                    "请先回到 Abaqus 检查材料和工作副本。"
                )
            else:
                message = str(error)
            self.action_queue.put(("apply_error", message))
        except (SafeActionBridgeError, MaterialCommandError, OSError) as error:
            self.action_queue.put(("apply_error", str(error)))
        except Exception:
            self.action_queue.put(
                ("apply_error", "应用时遇到未预期的本地错误。")
            )
        else:
            self.action_queue.put(
                (
                    "rectangle_apply_success"
                    if plan_type == "rectangle"
                    else (
                        "guided_apply_success"
                        if isinstance(plan_type, str)
                        and plan_type.startswith("guided:")
                        else "apply_success"
                    ),
                    receipt,
                )
            )

    def _clear_pending_plan(self) -> None:
        """撤销界面中的待应用计划，并立即重新锁定按钮。"""

        self.pending_plan = None
        self.pending_plan_type = None
        if hasattr(self, "apply_button"):
            self.apply_button.configure(state="disabled", style="Disabled.TButton")
        if hasattr(self, "safety_label"):
            self.safety_label.configure(
                text="尚无可应用计划｜不会自动修改模型",
                foreground=COLOR_ERROR,
            )

    def _clear_command(self) -> None:
        """清空中文输入和答复，不影响已读取的模型摘要。"""

        if self.action_running:
            return
        self._clear_pending_plan()
        self.command_text.delete("1.0", "end")
        self._set_readonly_text(
            self.response_text,
            "已清空输入和待应用计划。模型摘要仍为最近一次只读结果。",
        )
        self._append_log("中文输入区域已清空。")

    def _append_log(self, message: str) -> None:
        """只记录动作类型和结果，不复制用户命令或本机路径。"""

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append("[{0}] {1}".format(timestamp, message))
        self.log_lines = self.log_lines[-80:]
        if hasattr(self, "log_text"):
            self._set_readonly_text(self.log_text, "\n".join(self.log_lines))
            self.log_text.see("end")


def launch(
    *,
    mock: bool = False,
    source: str = "snapshot",
    mcp_home: Optional[Path] = None,
) -> int:
    """创建模型概要来源，并接入独立的白名单材料动作桥。"""

    selected_source = "mock" if mock else source
    if selected_source == "mock":
        bridge = MockReadOnlyBridge()
        action_bridge = bridge
    elif selected_source == "snapshot":
        if mcp_home is not None:
            raise ValueError("一次性快照模式不能使用 --mcp-home。")
        bridge = SnapshotFileSource()
        action_bridge = SafeActionFileBridge()
    elif selected_source == "mcp":
        bridge = FileIpcReadOnlyBridge(home=mcp_home)
        action_bridge = SafeActionFileBridge()
    else:
        raise ValueError("未知桌面助手数据源：{0}".format(selected_source))
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError("无法创建桌面窗口：{0}".format(error)) from error
    DesktopAssistantApp(root, bridge, action_bridge=action_bridge)
    root.mainloop()
    return 0


__all__ = ["DesktopAssistantApp", "launch"]
