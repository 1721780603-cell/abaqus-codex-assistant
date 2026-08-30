# Abaqus Codex Assistant

一个面向 Abaqus 初学者的开源项目：先检查本机环境，再用清晰、可追溯的步骤完成建模、求解、ODB 结果读取和中文报告生成。

当前已经实现五个由浅入深的模型：矩形板拉伸、中心圆孔板拉伸、悬臂梁均布载荷弯曲、方板双向拉伸，以及使用 Fortran DLOAD 的三维路面单轮移动载荷，并在 Abaqus 2021 上完成真实验证。

> 本项目是非官方社区项目，与 Dassault Systèmes 不存在隶属、授权或赞助关系。

> 原始项目与规范仓库：[`1721780603-cell/abaqus-codex-assistant`](https://github.com/1721780603-cell/abaqus-codex-assistant)。Copyright © 2026 `1721780603-cell` and contributors。使用或改编时请保留 [MIT License](LICENSE)、[版权与来源声明](NOTICE.md)，学术或教学使用请按 [CITATION.cff](CITATION.cff) 引用。

## 已实现功能

- 检测 Abaqus 安装位置、版本及自带 Python；
- 检测 `abqpy` 安装状态和版本兼容性；
- 检测 Abaqus MCP 文件、Codex 注册和本地启动状态；
- 提供首次启动体检，分层检查项目 Python、GitHub 登录、Zotero 本地连接和 ScienceDirect 人工机构访问；
- 检测 MCP 心跳和 Abaqus 进程，并在桥接离线时快速返回，避免工具持续转圈；
- 支持在隐藏的 `Abaqus cae noGUI` 进程中运行 MCP，避免 CAE 图形界面被轮询占用；
- 提供独立 Python 3 只读中文助手，默认读取 Abaqus 2021 一次性快照，不启动 MCP 后台轮询；
- 在用户明确确认后安装或注册固定版本的 Abaqus MCP；
- 选择入门、论文复现、科研、生产或教学场景；
- 检测本机 Ollama 或 LM Studio，并把中文需求转换为受约束的矩形板 JSON；
- 提供可安装的 Codex Skill，一次一个问题引导新手完成模型；
- 启动 Abaqus 前单独校验个人模型 JSON；
- 生成二维平面应力矩形板拉伸模型；
- 生成带孔边局部网格细化的二维中心圆孔板拉伸模型；
- 生成左端固定、上边界承受向下均布载荷的二维悬臂梁模型；
- 生成水平和竖直方向同时受控位移的二维方板双向拉伸模型；
- 生成三维单层路面，并用 Fortran DLOAD 控制矩形轮载区匀速移动；
- 自动运行 Abaqus/Standard；
- 读取 ODB 最后分析帧；
- 输出全模型最大位移模和最大 Mises 应力；
- 生成 UTF-8 中文 Markdown 报告；
- 每次运行使用独立目录，不覆盖历史计算。

## 三种运行模式

| 模式 | 包含功能 | 是否需要 Codex 用量 |
|---|---|---:|
| 本地基础模式 | 环境检测、固定模型、求解、ODB 读取、模板报告 | 否 |
| 本地 AI 模式 | Ollama/LM Studio 中文需求转矩形板 JSON，人工确认后保存 | 否 |
| Codex 智能模式 | 自然语言辅助、脚本修改、错误分析、后续论文复现 | 是 |

项目不会内置或共享公共 API Key。本地 AI 模式只允许连接当前电脑的回环地址；Codex 智能模式应由每个用户使用自己的 Codex 登录或 API Key。

## 运行要求

- Windows 10/11；
- 已合法安装并配置许可证的 Abaqus；
- Python 3.10 或更高版本；
- Git；
- Abaqus 2021–2025 使用与年份严格匹配的 `abqpy==<年份>.*`，例如 Abaqus 2024 使用 `abqpy==2024.*`；Abaqus 2026 自动流程当前禁用；
- Codex 和 Abaqus MCP 仅为智能模式所需。
- 三维移动载荷示例还需要与 Abaqus 匹配的 Visual Studio 和 Intel Fortran Classic。

项目不分发 Abaqus，也不绕过许可证。

## Codex Skill 新手向导

在 Codex 中调用 `$skill-installer`，要求从下面的 GitHub 目录安装 Skill：

<https://github.com/1721780603-cell/abaqus-codex-assistant/tree/main/skills/abaqus-modeling-guide>

安装完成后可以这样开始：

```text
使用 $abaqus-modeling-guide 带我一步步建立并运行第一个 Abaqus 模型。
```

向导会先运行只读首次体检，再让用户选择“基础建模”“Codex 智能建模”“科研复现全套”或“单项修复”。它一次只处理一个缺项；安装、注册、启用、重启和登录均不会静默执行。ScienceDirect 机构登录必须由用户本人在官方网页完成，Skill 不读取密码、验证码、Cookie 或会话令牌。

体检完成后，向导会一次只询问一组建模参数。它把个人配置保存在 `configs/user_models/`，先运行离线校验，并在得到明确确认后才启动 Abaqus。Skill 不包含 Abaqus，也不会绕过许可证或自动上传模型文件。

## 快速开始

以下命令在 PowerShell 的项目根目录运行。先安装项目并进行只读体检，不要在尚未确认 Abaqus 年份时直接安装最新版 abqpy：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m abaqus_codex onboard
```

先在不连接 Abaqus 的情况下打开中文助手模拟界面：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant --mock
```

真实使用前，先演练并安装安全材料动作插件：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --dry-run
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --yes
```

关闭并重新打开 Abaqus/CAE 2021，打开一个已经保存过的 CAE；如需刷新完整对象名称摘要，再点击：

```text
Plug-ins → Abaqus Codex Assistant → Refresh Read-Only Snapshot
```

再启动桌面助手：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant
```

Windows 用户也可以直接双击项目根目录中的 `启动中文建模助手.cmd`。该启动器只使用项目自己的虚拟环境；如果环境尚未安装，会显示中文提示而不会改用未知的系统 Python。可以为这个文件创建桌面快捷方式，移动项目后需要重新创建快捷方式。

中文助手现已支持固定句式驱动的二维矩形板拉伸十步闭环：几何、材料、截面、装配、静力步、相互作用检查、位移边界、网格、Job、ODB 极值与中文报告。发送只生成计划；点击“应用修改”并二次确认后才执行。每个 CAE 写步骤先建立唯一工作副本，报告也只新建不覆盖。默认模式不调用旧 MCP、不联网、不调用 AI；它不是开放式自然语言助手。详细命令和边界见[中文建模助手](docs/desktop-assistant.md)。

体检显示的 Abaqus 命令路径符合预期、且年份为当前允许继续的 2021–2025 后，再让项目安装同年份的 abqpy。下面的命令会联网修改当前项目 Python，因此只在核对安装计划并同意后使用 `--yes`：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex abqpy-setup --yes
.\.venv\Scripts\python.exe -m abaqus_codex onboard
```

安装器始终生成严格年份规格：Abaqus 2021 对应 `abqpy==2021.*`，Abaqus 2024 对应 `abqpy==2024.*`，不会安装不带年份限制的最新版。

当前体检只解析 PATH 或常见目录中找到的第一个可用 Abaqus 命令，并不会枚举所有安装。如果你知道电脑装了多个版本、显示路径与预期不符或检测结果不确定，请不要运行 `abqpy-setup --yes`、配置 MCP 或启动求解；先人工明确本次目标版本和启动命令/安装路径。多版本自动枚举和选择器是后续功能。

实际求解会把这条已检查命令通过 `ABAQUS_BAT_PATH` 交给 abqpy，避免检查和启动落到不同版本。版本、内置 Python 或命令路径任一项无法可靠确认时，求解和后台 MCP 都会停止，不采用猜测值继续。

维护者当前只在 Abaqus 2021 上完成真机全流程验证，Abaqus 2022–2025 属于可检测的候选兼容版本。Abaqus 2026 已在用户/项目实测中出现兼容失败，当前自动流程仅检测版本并给出提示；不得继续运行 `abqpy-setup --yes`、安装或启动 MCP、提交求解。项目修复并重新完成真机验证后，才会重新评估这一限制。详见[版本支持表](docs/version-support.md)。

运行首次启动体检；普通输出适合人阅读，JSON 输出适合 Skill 判断下一步：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex onboard
.\.venv\Scripts\python.exe -m abaqus_codex onboard --json
```

这两个命令只读取状态，不会安装软件、修改配置或替用户登录。ScienceDirect 状态会保持为“需要用户确认”，不会根据浏览器 Cookie 猜测登录成功。

只检查 Abaqus、abqpy 和 MCP 核心环境：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex doctor
```

如需智能模式，在阅读安全说明后安装或注册 MCP：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --yes
```

已有 MCP 点击后一直转圈时，安装防卡启动器并更新注册：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --repair --yes
```

详细原因和排查步骤见 [Abaqus MCP 一直转圈排查](docs/mcp-troubleshooting.md)。

如果 GUI 模式仍导致进度条和鼠标转圈，使用无界面后台桥接：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-headless start
.\.venv\Scripts\python.exe -m abaqus_codex mcp-headless status
.\.venv\Scripts\python.exe -m abaqus_codex mcp-headless stop
```

该模式使用独立 Abaqus/CAE 许可证会话，不显示操作界面，也不会预先打开任何私人模型。

保存使用场景：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex configure --scenario learning
```

检查本地 AI（可选）：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai doctor
```

用 Ollama 生成一份矩形板配置；程序会先显示完整 JSON，确认后才保存：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai generate `
  --provider ollama `
  --model "你的本机模型名称" `
  --prompt "建立长 200 mm、高 100 mm、厚 2 mm 的矩形板，右边拉伸 0.2 mm。"
```

这个命令不会运行 Abaqus。第一版只支持矩形板、mm 和 MPa，详细边界见[本地 AI 入门](docs/local-ai.md)。

在启动 Abaqus 前单独检查任意受支持的配置：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex validate --config .\configs\rectangle_tension.json
```

命令只读取并规范化 JSON，不占用 Abaqus 许可证。

运行二维矩形板拉伸示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run
```

运行二维中心圆孔板拉伸示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\plate_with_hole_tension.json
```

运行二维悬臂梁均布载荷弯曲示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\cantilever_bending.json
```

运行二维方板双向拉伸示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\biaxial_tension.json
```

运行三维路面单轮移动载荷示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\moving_load_road.json
```

移动载荷会编译项目生成的 Fortran DLOAD。首次使用前请阅读[移动载荷入门说明](docs/moving-load-dload.md)。

结果保存在 `outputs/<运行时间>/`：

- `input_config.json`：本次实际使用的参数；
- `results.json`：结构化最大位移和最大 Mises 应力；
- `report.md`：简单中文报告。

Abaqus 的 CAE、ODB、状态和日志文件保存在 `work/runs/<运行时间>/`，默认不提交到 GitHub。

## 示例结果

![Abaqus Codex Assistant 真实验证结果](docs/images/verified-run.svg)

默认配置采用 mm–MPa 单位制：板长 100 mm、板高 20 mm、厚度 1 mm、弹性模量 210000 MPa、泊松比 0.3、右边位移 0.1 mm。

在 Abaqus 2021 的真实验证结果为：

- 最大位移模：约 0.10017984 mm；
- 最大 Mises 应力：210 MPa；
- `.sta` 状态：`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

210 MPa 与线弹性理论值 `E × u / L = 210000 × 0.1 / 100` 一致。

圆孔板默认配置采用板长 100 mm、板高 50 mm、中心孔半径 5 mm、全局网格 2 mm、孔边网格 0.5 mm。在同一台 Abaqus 2021 电脑上的真实验证结果为：

- 最大位移模：约 0.10093824 mm；
- 最大 Mises 应力：约 562.55554 MPa；
- `.sta` 状态：`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

圆孔附近存在应力集中，因此最大应力高于无孔板。该数值依赖孔径、板宽和孔边网格，正式使用前必须进行网格收敛性分析，不能把本示例结果直接当作工程许用值。

悬臂梁默认配置采用长 100 mm、高 20 mm、厚 1 mm、上边界向下均布载荷 1 MPa、网格 2 mm。真实验证结果为：

- 最大位移模：约 0.094622037 mm；
- 最大 Mises 应力：约 71.0299 MPa；
- 读取 561 个节点位移值和 500 个应力值；
- `.sta` 状态：`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

方板双向拉伸默认配置采用 100 mm × 100 mm 方板，右边和上边各拉伸 0.1 mm，网格 5 mm。真实验证结果为：

- 最大位移模：约 0.14142136 mm；
- 最大 Mises 应力：300 MPa；
- 读取 441 个节点位移值和 400 个应力值；
- `.sta` 状态：`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

最大位移与理论值 `√(0.1² + 0.1²)` 一致；等双向平面应力的理论 Mises 应力为 `E × 0.001 / (1 - ν) = 300 MPa`。

三维移动载荷默认配置采用单层 `4000 × 2000 × 600 mm` 弹性路面、`200 × 200 mm` 矩形接触区、`0.7 MPa` 接触压力和 `36 km/h` 速度。Abaqus 2021 真实编译 DLOAD 并完成 211 个动力输出帧，结果为：

- 全程最大位移模：约 0.18379377 mm；
- 全程最大竖向位移绝对值：约 0.18264329 mm；
- 全程最大 Mises 应力：约 0.47442088 MPa；
- `.sta` 状态：`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

最大响应接近模型入口和出口，反映了有限路面端部效应。本示例只验证子程序和流程，不能作为三级公路正式设计结果。

## 推荐入门顺序

1. 矩形板单向拉伸：学习材料、位移边界、网格和理论值核对；
2. 中心圆孔板拉伸：观察应力集中和局部网格敏感性；
3. 悬臂梁均布载荷弯曲：学习固定端、分布载荷和弯曲变形；
4. 方板双向拉伸：学习两个方向的边界条件和双向应力状态。
5. 三维路面移动载荷：学习密度、动力时间、Fortran DLOAD 和全时间帧极值。

## 项目结构

```text
abaqus-codex-assistant/
├─ .github/workflows/       GitHub 自动测试
├─ abaqus_plugins/          Abaqus 2021 快照与安全材料动作插件
├─ configs/                 示例模型配置
├─ docs/                    快速开始、架构和边界说明
├─ examples/                面向初学者的示例说明
├─ skills/                  可安装的 Codex 新手建模向导
├─ src/abaqus_codex/        主程序、桌面助手与 Abaqus 脚本
├─ tests/                   不需要 Abaqus 的离线测试
├─ work/                    本机计算文件，不提交
└─ outputs/                 本机结果与报告，不提交
```

## 开发与测试

开发环境应安装测试依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions 只运行不依赖 Abaqus 许可证的测试。真实求解必须在已安装 Abaqus 的电脑上运行。

CI 同时覆盖 Linux、Windows、Python 3.10 和 Python 3.13。当前真实 Abaqus 支持范围见 [版本支持表](docs/version-support.md)。

## 维护方式

- 缺陷和功能建议使用仓库内置 Issue 表单；
- 所有改动通过分支和 Pull Request 提交；
- GitHub Actions 自动运行语法检查和离线测试；
- Dependabot 每月检查 Python 与 GitHub Actions 依赖；
- 版本变化记录在 [CHANGELOG](CHANGELOG.md)；
- 发布前按照 [发布清单](RELEASING.md) 完成真实 Abaqus 验证；
- 支持范围和响应边界见 [SUPPORT](SUPPORT.md)。

## 安全与论文访问

Abaqus MCP 可以执行 Abaqus Python 脚本，属于高权限本地能力。不要让不可信内容直接进入任意脚本执行工具。详细规则见 [SECURITY.md](SECURITY.md)。

论文复现功能第一阶段只检查 GitHub 与 Zotero 本地状态，并引导用户使用合法的机构访问或开放获取来源，尚未自动下载论文。项目不得保存机构账号、密码、Cookie、验证码或会话令牌，也不得绕过付费墙。详见 [论文复现边界](docs/paper-reproduction-boundaries.md)。

## 文档

- [快速开始](docs/quick-start.md)
- [首次启动流程](docs/first-run-flow.md)
- [项目架构](docs/architecture.md)
- [版本支持表](docs/version-support.md)
- [移动载荷与 DLOAD 入门](docs/moving-load-dload.md)
- [本地 AI 入门](docs/local-ai.md)
- [中文材料修改助手](docs/desktop-assistant.md)
- [Abaqus MCP 一直转圈排查](docs/mcp-troubleshooting.md)
- [日常维护方式](docs/maintenance.md)
- [GitHub 仓库设置](docs/github-settings.md)
- [论文复现边界](docs/paper-reproduction-boundaries.md)
- [贡献指南](CONTRIBUTING.md)
- [变更日志](CHANGELOG.md)
- [支持政策](SUPPORT.md)

## 许可证

本项目使用 [MIT License](LICENSE)。Abaqus 是 Dassault Systèmes 的商业软件，不包含在本项目许可证中。第三方 Abaqus MCP 和 `abqpy` 分别遵循其自身许可证。详见 [第三方与商标声明](NOTICE.md)。
