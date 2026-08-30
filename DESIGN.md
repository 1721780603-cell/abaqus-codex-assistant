---
name: Abaqus 中文建模助手
description: 面向 Abaqus 2021 初学者的只读中文桌面工作台
colors:
  canvas: "#EDF2F5"
  panel: "#FFFFFF"
  header: "#123247"
  header-muted: "#C8D9E4"
  text: "#16232C"
  text-muted: "#52636F"
  border: "#C8D3DA"
  accent: "#176B87"
  accent-active: "#11576F"
  success: "#1F6F54"
  warning: "#946200"
  error: "#A13C3C"
  disabled: "#D9E1E6"
  selection: "#BBD6E3"
typography:
  brand:
    fontFamily: "Microsoft YaHei UI, TkDefaultFont"
    fontSize: "17pt"
    fontWeight: 700
  title:
    fontFamily: "Microsoft YaHei UI, TkDefaultFont"
    fontSize: "12pt"
    fontWeight: 700
  body:
    fontFamily: "Microsoft YaHei UI, TkDefaultFont"
    fontSize: "10pt"
    fontWeight: 400
  meta:
    fontFamily: "Microsoft YaHei UI, TkDefaultFont"
    fontSize: "9pt"
    fontWeight: 400
  status:
    fontFamily: "Microsoft YaHei UI, TkDefaultFont"
    fontSize: "10pt"
    fontWeight: 400
spacing:
  control-gap: "8px"
  content-gap: "12px"
  panel-padding: "16px"
  header-horizontal: "20px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.panel}"
    typography: "{typography.body}"
    padding: "8px 14px"
  button-primary-active:
    backgroundColor: "{colors.accent-active}"
    textColor: "{colors.panel}"
  button-secondary:
    backgroundColor: "#E7EEF2"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    padding: "8px 12px"
  panel:
    backgroundColor: "{colors.panel}"
    padding: "16px"
---

# Design System: Abaqus 中文建模助手

## Overview

**Creative North Star: “克制的工程工作台”**

界面服务于“读取当前模型—解释结果—确认边界”的安全流程。视觉层级首先回答三件事：是否连接、是否为真实环境、模型是否可能被修改；装饰始终让位于可扫描性和风险说明。

当前版本是 Windows 桌面只读原型，面向有 Abaqus 基础但编程经验较少的中文用户。成功标准不是“命令执行了”，而是用户能理解发生了什么、模型是否改变及下一步怎么做。

**关键特征：** 深蓝标题栏、浅灰蓝画布、白色有边界面板；工程化而不冰冷；所有状态同时使用文字和颜色；危险边界在主操作附近重复出现。

## Colors

色彩以冷静的蓝灰中性色为底，只把绿、琥珀和红用于连接与安全语义。YAML token 为规范来源。

- **主操作蓝：** 用于刷新与读取等允许的只读动作；按下或悬停时转为更深的蓝。
- **成功绿：** 仅表示真实连接在线，不代表模型设置、收敛性或结果正确。
- **警示琥珀：** 表示正在检查、正在读取、显式模拟或未知状态。
- **错误红：** 表示离线、读取失败、异常，以及“写操作已锁定”的安全提醒。
- **中性层级：** 画布承载分区，白色面板承载任务，浅灰蓝填充只读结果、日志和页脚。

**状态不只靠颜色规则。** 任何绿、黄、红状态都必须同时显示明确中文文案，并在摘要或日志中说明模型是否改变。

## Typography

Windows 优先使用 Microsoft YaHei UI；不可用时回退到 TkDefaultFont。字号以 Tk point 为单位：品牌标题 17pt 粗体、面板标题 12pt 粗体、正文与输入 10pt、提示文字 9pt。右上角彩色状态块使用 10pt 常规字重，避免 125% DPI 下小号粗体笔画粘连；安全锁定标签仍使用 9pt 粗体。

文案使用初学者能理解的短句。错误信息遵循“发生了什么—模型是否改变—下一步”结构，不使用未经解释的内部异常或工程术语。

## Layout

默认窗口为 1120×760，最小尺寸为 920×620，适合与 Abaqus/CAE 并排使用。顶部是全宽状态栏，中间工作区采用 11:10 的双栏：左侧“当前模型”，右侧“只读命令测试、处理结果、高级本地日志”；底部是持续可见的安全说明。

基础节奏为 8px 控件间距、12px 内容间距和 16px 面板/工作区内边距，标题栏水平内边距为 20px。当前实现是 Windows 桌面双栏布局，没有小屏折叠规则。

## Elevation & Depth

系统保持扁平，不使用阴影。深度依靠背景明度、1px 面板边框和区域留白表达；状态的优先级由位置、清晰字号与语义色共同建立。

## Shapes

采用方正、克制的原生 Tk/ttk 轮廓，不定义额外圆角。主面板使用 1px 边框；摘要、答复和日志为无边框浅色填充区；输入框使用 1px 实线边框，以区别可编辑内容和只读输出。

## Components

### 顶部状态栏

- 左侧显示产品名及当前小目标；右侧同时显示连接状态和运行模式。
- 连接文案：启动为“正在检查”，刷新期间为“正在读取”，异常兜底为“读取失败”；完成后显示状态对象提供的连接文字。
- 默认模式文案使用“一次性快照 · 待验证/正在验证/已读取/未就绪”；显式兼容模式使用“MCP 兼容 · 待验证/正在验证/已连接/未就绪”；模拟模式使用“显式模拟 · 待验证/已载入”。
- 连接语义色：`online` 为成功绿，`mock` 为警示琥珀，`offline`/`error` 为错误红，未知状态回退为警示琥珀。

### 面板与文本区

- 模型摘要只显示模型、零件、材料、分析步和接触等对象名称，不显示完整路径。
- 摘要、处理结果和日志均为只读文本；更新时短暂解除禁用，写入后立即恢复禁用，并保留选择与复制能力。
- 日志只记录动作类型、时间和结果，不复制完整命令、模型路径或凭据；最多保留最近 80 行。

### 按钮与输入

- “刷新模型”“读取模型”是蓝色主按钮；读取期间两者同时禁用，避免并发请求。
- “清空”是浅灰蓝次按钮，只清空输入与答复，不影响最近一次模型摘要。
- 输入框默认填入“查看当前模型信息”，窗口打开后自动获得焦点。
- 主操作旁持续显示红色粗体文案“写操作已锁定｜本版本不能修改模型”。

### 安全页脚

页脚始终显示：“只读原型：读取成功仅表示数据源通过检查，不代表模型设置、收敛性或结果合理。”此说明不得因快照可用或在线状态而隐藏。

## Do's and Don'ts

### Do

- **Do** 在状态徽标、摘要和日志中同时用中文说明状态，不能只改变颜色。
- **Do** 保持“本地关键词匹配、未联网、未调用 AI、输入未上传、不能修改模型”的阶段性边界可见。
- **Do** 支持 F5 刷新、Ctrl+Enter 读取；处理后返回 `break`，避免按键继续传入文本框。
- **Do** 启动后把焦点放入命令输入框，并保持输入框与按钮可进入键盘焦点顺序。
- **Do** 对错误明确说明模型没有改变，并提供可执行的下一步。

### Don't

- **Don't** 把“连接在线”表达成“模型正确”或“工程结果可信”。
- **Don't** 暗示已经联网、调用 AI、上传输入或具备写模型能力。
- **Don't** 用普通 Enter 触发操作；它应继续用于输入换行，降低未来误触写操作的风险。
- **Don't** 声称当前只读输出具备完整键盘可访问性：这些控件设置了 `takefocus=False`，不进入 Tab 顺序；复制/选择主要依赖指针操作，后续若扩展需单独补齐。
