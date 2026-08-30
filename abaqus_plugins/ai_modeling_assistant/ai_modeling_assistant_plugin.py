# -*- coding: utf-8 -*-
"""在 Abaqus/CAE 2021 的 Plug-ins 菜单注册中文建模助手。"""

from abaqusConstants import ALL
from abaqusGui import AFXForm, getAFXApp


class ChineseModelingAssistantForm(AFXForm):
    """管理可重复打开的非模态助手窗口。"""

    def __init__(self, owner):
        """保存插件工具集；本阶段不创建任何 Abaqus Kernel 命令。"""

        AFXForm.__init__(self, owner)
        self.dialog = None

    def getFirstDialog(self):
        """首次打开时创建窗口，之后复用同一个窗口对象。"""

        if self.dialog is None:
            from ai_modeling_assistant_dialog import ChineseModelingAssistantDialog

            self.dialog = ChineseModelingAssistantDialog(self)
        return self.dialog


# Abaqus 会自动执行文件名以 _plugin.py 结尾的注册文件。
toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
toolset.registerGuiMenuButton(
    object=ChineseModelingAssistantForm(toolset),
    buttonText=u"AI 中文建模助手...",
    applicableModules=ALL,
    version="0.2.2",
    author="Abaqus Codex Assistant Contributors",
    description=(
        u"Abaqus 2021 中文建模助手界面预览。"
        u"当前版本只展示模拟摘要和修改计划，不会修改模型。"
    ),
)
