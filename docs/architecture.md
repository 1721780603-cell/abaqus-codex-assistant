# 项目架构

## 主流程

```text
中文需求（可选）
   │
   ▼
本机 Ollama/LM Studio 提取白名单参数
   │
   ▼
人工确认后的 JSON 配置
   │
   ▼
Python 3 参数校验
   │
   ▼
abqpy 启动 Abaqus/CAE noGUI
   │
   ▼
Abaqus Python 2.7 建模、网格、边界条件、求解
   │
   ▼
读取 ODB 最后一帧的 U 和 S
   │
   ▼
results.json
   │
   ▼
Python 3 生成中文 report.md
```

## 模块职责

- `environment.py`：Abaqus 与自带 Python；
- `abqpy_environment.py`：abqpy 版本匹配；
- `mcp_environment.py`：MCP 文件、Codex 注册、导入验证和 Abaqus 插件心跳检查；
- `mcp_guard.py`：工具调用前检查心跳与进程，桥接离线时快速返回；
- `mcp_headless.py`：隐藏启动、检查和优雅停止独立 Abaqus noGUI 桥接；
- `mcp_setup.py`：经明确确认后的固定版本安装和防卡注册修复；
- `abaqus_plugins/readonly_model_snapshot/`：Abaqus 2021 用户点击后只运行一次的 Kernel 名称快照；
- `abaqus_plugins/safe_material_action/`：GUI 事件循环轮询与 Kernel 单材料白名单执行器；
- `desktop_assistant/snapshot_source.py`：默认读取并严格验证静态快照，不向 Abaqus 发送命令；
- `desktop_assistant/bridge.py`：显式 MCP 兼容模式，只发送 `ping` 和 `get_model_info`；
- `desktop_assistant/snapshot.py`：裁剪模型概要、移除完整路径并计算只读指纹；
- `desktop_assistant/controller.py`：不依赖 Tk 的中文输入和连接状态逻辑；
- `desktop_assistant/material_flow.py`：固定中文句式、实时旧值和可审阅 Action Plan；
- `desktop_assistant/safe_action_bridge.py`：只发送材料读取或已批准材料计划；
- `desktop_assistant/app.py`：Python 3 Tkinter 伴随窗口，后台读取、主线程更新界面；
- `doctor.py`：综合体检；
- `configuration.py`：输入校验；
- `local_ai.py`：只通过本机回环地址读取模型并生成受约束的矩形板参数；
- `scenario.py`：最小化场景配置；
- `workflow.py`：创建独立运行目录并协调全流程；
- `abaqus_scripts/rectangle_tension.py`：Abaqus 2021/Python 2.7 端逻辑；
- `abaqus_scripts/plate_with_hole_tension.py`：中心圆孔板和孔边局部网格逻辑；
- `abaqus_scripts/cantilever_bending.py`：悬臂梁固定端和均布载荷逻辑；
- `abaqus_scripts/biaxial_tension.py`：方板两个方向的位移边界逻辑；
- `abaqus_scripts/moving_load_road.py`：三维路面、动力隐式步和全帧结果读取；
- `user_subroutine.py`：把校验后的移动轮载参数写入本次运行的 Fortran 文件；
- `user_subroutines/moving_pressure_dload.for.in`：受控的移动矩形压力 DLOAD 模板；
- `report.py`：中文 Markdown 报告；
- `cli.py`：统一命令行。

## 为什么分成两个 Python 环境

Abaqus 2021 自带 Python 2.7，现代开发工具通常使用 Python 3。主程序使用 Python 3 进行输入校验、命令编排和报告生成；真正的 Abaqus API 脚本保持 Python 2.7 兼容。这样既能获得现代开发体验，又不修改 Abaqus 安装目录。

桌面助手也遵循这一边界：Python 3 负责中文句式、计划和确认；Abaqus 2021 Kernel 只执行固定材料动作。GUI 插件在 FOX 主事件循环中领取请求，并用固定 `sendCommand` 调用 Kernel，不在后台线程中访问 `mdb`。MCP 仅保留为显式兼容模式；无界面后台桥接属于另一个 Abaqus 会话，不能修改用户当前 GUI 中打开的模型。

## 结果可追溯性

每次运行创建唯一时间戳目录。公开输出中保存校验后的配置、结构化结果和报告；大型 ODB、CAE、SIM 及日志保存在 `work`，默认被 Git 忽略。

## 本地 AI 安全边界

本地模型只负责把自然语言转换为固定白名单字段。程序拒绝外部或局域网模型地址、额外字段、脚本路径和不支持的单位；生成结果还要经过 `configuration.py` 的同一套校验。生成配置与运行 Abaqus 是两个独立命令，避免一次模型响应直接触发高权限求解流程。
