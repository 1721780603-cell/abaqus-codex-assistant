# -*- coding: utf-8 -*-
"""为插件窗口提供无需 Abaqus 的模拟文本。"""

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


MAX_COMMAND_LENGTH = 500

MOCK_MODEL_SUMMARY = (
    u"Abaqus 版本：2021\n"
    u"模型：Model-1（模拟）\n"
    u"零件：Plate（模拟）\n"
    u"材料：钢材，E=200000 MPa，ν=0.30（模拟）\n"
    u"提示：这些内容不是从当前 CAE 读取的。"
)

INITIAL_PLAN = (
    u"尚未生成计划。\n"
    u"输入中文命令并点击“发送”，这里只会显示模拟预览。"
)

INITIAL_LOG = (
    u"[就绪] Abaqus 2021 插件窗口已打开。\n"
    u"[安全] AI、MCP 和模型写操作均未连接。"
)


def _to_text(value):
    """把 GUI 返回值安全转换为 Unicode 文本。"""

    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        return value.decode("utf-8", "replace")
    return text_type(value)


def normalize_command(value):
    """移除控制字符并限制预览长度，绝不把输入当作代码。"""

    text = _to_text(value)
    cleaned = []
    for character in text:
        code = ord(character)
        if code < 32 or code == 127:
            cleaned.append(u" ")
        else:
            cleaned.append(character)
    return u"".join(cleaned).strip()[:MAX_COMMAND_LENGTH]


def build_mock_plan(command):
    """根据用户输入生成明确标注为模拟的只读预览。"""

    safe_command = normalize_command(command)
    return (
        u"【模拟计划，不会执行】\n"
        u"用户命令：{0}\n"
        u"涉及对象：等待后续安全模型摘要确认\n"
        u"旧值：尚未读取\n"
        u"新值：尚未解析\n"
        u"风险：当前版本没有写操作\n"
        u"状态：“应用修改”按钮保持禁用"
    ).format(safe_command)


def build_mock_log():
    """返回不包含用户命令和本机路径的模拟日志。"""

    return (
        u"[模拟] 已接收中文命令。\n"
        u"[模拟] 已生成界面预览，没有调用 AI 或 MCP。\n"
        u"[安全] 未读取、保存、修改或提交任何 Abaqus 对象。"
    )
