# -*- coding: utf-8 -*-
"""在 Abaqus/CAE 2021 的 Plug-ins 菜单注册一次性只读快照。"""

from abaqusConstants import ALL
from abaqusGui import getAFXApp


# 菜单注册阶段不读取版本号，避免不同 Abaqus GUI 构建返回不同格式时
# 把入口静默隐藏。真正执行快照时，Kernel 端仍会严格校验 2021。
application = getAFXApp()
# 官方 Kernel 菜单机制只会调用下面写死的无参数函数。
toolset = application.getAFXMainWindow().getPluginToolset()
toolset.registerKernelMenuButton(
    # Abaqus 2021 的旧式 GUI 绑定按 C 字符串接收这些字段。
    # 注册层先使用纯 ASCII，中文说明由桌面助手和文档提供。
    buttonText="Abaqus Codex Assistant|Refresh Read-Only Snapshot",
    moduleName="readonly_model_snapshot_kernel",
    functionName="write_readonly_snapshot()",
    icon=None,
    applicableModules=ALL,
    version="0.2.3",
    author="Abaqus Codex Assistant Contributors",
    description=(
        "Create one read-only Abaqus 2021 model-name snapshot. "
        "No polling, model changes, or model saves."
    ),
    helpUrl="",
)
