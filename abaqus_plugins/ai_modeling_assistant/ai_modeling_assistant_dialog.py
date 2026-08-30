# -*- coding: utf-8 -*-
"""Abaqus 2021 中文建模助手的非模态窗口外壳。"""

from abaqusGui import *

from mock_preview import (
    INITIAL_LOG,
    INITIAL_PLAN,
    MOCK_MODEL_SUMMARY,
    build_mock_log,
    build_mock_plan,
    normalize_command,
)


class ChineseModelingAssistantDialog(AFXDataDialog):
    """靠右显示的可缩放窗口；当前阶段只执行本地模拟交互。"""

    [ID_SEND, ID_CLEAR, ID_APPLY] = range(
        AFXDataDialog.ID_LAST, AFXDataDialog.ID_LAST + 3
    )

    def __init__(self, form):
        """创建输入、摘要、计划和日志区域。"""

        self.form = form
        AFXDataDialog.__init__(
            self,
            form,
            u"AI 中文建模助手（Abaqus 2021）",
            0,
            DECOR_RESIZE,
        )

        # 使用官方 Alias Map 保存用户调整后的窗口几何信息。
        getAFXAliasMap().setPrefix(self, "AbaqusCodexChineseAssistant")

        # 所有按钮都由当前 GUI 对象处理，不向 Kernel 发送字符串命令。
        self.send_button = self.appendActionButton(u"发送", self, self.ID_SEND)
        self.clear_button = self.appendActionButton(u"清空", self, self.ID_CLEAR)
        self.apply_button = self.appendActionButton(
            u"应用修改（尚未启用）", self, self.ID_APPLY
        )
        self.appendActionButton(self.DISMISS)
        self.apply_button.disable()

        FXMAPFUNC(self, SEL_COMMAND, self.ID_SEND, self.onCmdSend)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_CLEAR, self.onCmdClear)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_APPLY, self.onCmdApplyBlocked)

        root = FXVerticalFrame(
            self,
            LAYOUT_FILL_X | LAYOUT_FILL_Y,
            0,
            0,
            0,
            0,
            8,
            8,
            8,
            8,
        )

        FXLabel(
            root,
            u"界面演示模式：不连接 AI/MCP，不读取或修改当前模型。",
            None,
            JUSTIFY_LEFT | LAYOUT_FILL_X,
        )

        input_group = FXGroupBox(
            root, u"中文命令", FRAME_GROOVE | LAYOUT_FILL_X
        )
        self.command_text = self._make_text_area(input_group, 92, False)
        self.command_text.setText(
            u"例如：把 Model-1 中钢材弹性模量改为 2.1e5 MPa"
        )

        summary_group = FXGroupBox(
            root, u"模型摘要（模拟数据）", FRAME_GROOVE | LAYOUT_FILL_X
        )
        self.summary_text = self._make_text_area(summary_group, 98, True)
        self.summary_text.setText(MOCK_MODEL_SUMMARY)

        plan_group = FXGroupBox(
            root, u"修改计划（仅预览）", FRAME_GROOVE | LAYOUT_FILL_X
        )
        self.plan_text = self._make_text_area(plan_group, 145, True)
        self.plan_text.setText(INITIAL_PLAN)

        log_group = FXGroupBox(
            root,
            u"执行日志",
            FRAME_GROOVE | LAYOUT_FILL_X | LAYOUT_FILL_Y,
        )
        self.log_text = self._make_text_area(log_group, 110, True, True)
        self.log_text.setText(INITIAL_LOG)

    def _make_text_area(self, parent, height, read_only, fill_y=False):
        """创建统一样式的多行文本区域。"""

        options = LAYOUT_FILL_X | TEXT_WORDWRAP | FRAME_SUNKEN | FRAME_THICK
        if fill_y:
            options = options | LAYOUT_FILL_Y
        widget = FXText(parent, None, 0, options, 0, 0, 0, height)
        if read_only:
            widget.disable()
            # 禁用编辑后保持普通背景色，方便阅读中文内容。
            widget.setBackColor(self.getBackColor())
        return widget

    def show(self):
        """以非模态方式显示，并尽量移动到 Abaqus 主窗口右侧。"""

        AFXDataDialog.show(self)
        try:
            main_window = getAFXApp().getAFXMainWindow()
            right_x = (
                main_window.getX()
                + main_window.getWidth()
                - self.getWidth()
                - 24
            )
            top_y = main_window.getY() + 72
            self.move(max(main_window.getX(), right_x), top_y)
        except Exception:
            # 多屏或特殊主题下定位失败不影响窗口正常使用。
            pass

    def onCmdSend(self, sender, selector, data):
        """读取中文输入并生成不会执行的模拟计划。"""

        command = normalize_command(self.command_text.getText())
        if not command:
            showAFXErrorDialog(self, u"请先输入一条中文建模命令。")
            return 1

        self.plan_text.setText(build_mock_plan(command))
        self.log_text.setText(build_mock_log())
        self.apply_button.disable()
        return 1

    def onCmdClear(self, sender, selector, data):
        """清空输入和模拟结果，不访问 Abaqus 模型。"""

        self.command_text.setText(u"")
        self.plan_text.setText(INITIAL_PLAN)
        self.log_text.setText(INITIAL_LOG)
        self.apply_button.disable()
        return 1

    def onCmdApplyBlocked(self, sender, selector, data):
        """即使事件被程序触发，也拒绝修改模型。"""

        showAFXErrorDialog(
            self,
            u"当前只是界面演示版，尚未接入安全执行器，不能修改模型。",
        )
        return 1
