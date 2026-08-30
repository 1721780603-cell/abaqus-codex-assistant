# Product

<!-- impeccable:product-schema 1 -->

<!-- 本文件根据用户在本项目中的明确需求整理；尚未决定的内容单独标注。 -->

## Platform

adaptive

## Stack

delegated：沿用现有 Python 3.10+ 项目；当前伴随应用使用标准库 Tkinter，Abaqus 2021 端继续保持 Python 2.7 兼容。当前交付仅面向 Windows 桌面环境。

## Users

主要用户是有一定 Abaqus 基础、但编程经验较少的本科生、研究生及其他仿真初学者。他们在 Abaqus/CAE 中建模时，需要中文解释、环境排查和可审阅的修改帮助。

## Product Purpose

把中文意图转换成“读取当前模型—解释或给出方案—用户确认—受控执行—读回验证”的安全流程。成功不只是执行命令，而是让初学者知道发生了什么、模型是否改变以及下一步该做什么。

## Positioning

产品不是任意 Abaqus Python 生成器，而是一个带模型上下文、白名单动作、修改预览、备份和验证边界的中文协作助手。

## Operating Context

- 用户同时打开 Abaqus/CAE 2021 和独立中文助手；
- Python 3 应用负责界面、AI 与联网能力，Abaqus 内仅保留轻量桥接；
- 当前第一小目标只读取模型概要；默认由用户在 Abaqus 2021 中点击一次生成静态快照，不接入 AI，不修改模型；
- Abaqus 没有内置单位制，单位约定未知时不得生成数值修改计划；
- Codex 后续通过独立 App Server 会话接入，不抓取或复用桌面聊天凭据。

## Capabilities and Constraints

- 第一阶段仅支持 Abaqus 2021；其他年份后续单独适配；Abaqus 2026 当前排除；
- 所有修改必须先展示对象、旧值、新值、单位、影响和风险；
- 用户点击“应用修改”前不得写模型；
- 不允许 AI 生成并直接执行任意 Abaqus Python；
- 联网资料只能产生带来源的建议，建议需再次转换成白名单计划；
- 现有 MCP 的 GUI 后台线程可能导致 CAE 转圈；普通桌面刷新已切断该链路，但一次性 Kernel 菜单仍需 Abaqus 2021 真机验证；
- 开放决定：安全的 Abaqus 2021 主线程自动派发方式和多 CAE 会话选择协议。

## Evidence on Hand

- 已有五个可运行教学示例和离线测试；
- 本机已安装 Abaqus 2021、第三方 Abaqus MCP 及其文件通信桥接；
- `abaqus_plugins/ai_modeling_assistant/` 中已有不修改模型的插件界面外壳；
- 暂无可公开宣称的用户规模、性能指标或工程生产验证，不得编造。

## Product Principles

- 默认只读，修改需要明确确认；
- 一次完成一个可验证的小目标；
- 错误说明“发生了什么、是否改变模型、下一步是什么”；
- AI 负责理解和建议，可信执行器负责有限动作；
- 对版本、单位、对象和工程适用性不作未经验证的猜测。

## Accessibility & Inclusion

界面和文档使用初学者可理解的中文，状态不只依赖颜色表达；主要操作支持键盘焦点和快捷键。
