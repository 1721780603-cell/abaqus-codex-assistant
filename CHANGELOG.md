# 变更日志

本项目遵循语义化版本思想：不兼容变更提升主版本，新功能提升次版本，兼容修复提升修订版本。Alpha 阶段的接口仍可能调整。

## [Unreleased]

### 新增

- 首次启动 `onboard` / `onboard --json` 命令，分层检查 Abaqus 建模环境、Codex MCP、GitHub CLI 登录和 Zotero 本地连接；
- ScienceDirect 机构访问人工确认边界，以及基础建模、智能建模、科研复现和单项修复四条新手路线；
- 14 项不连接真实外部服务的首次启动向导与凭据保护测试，以及 1 项受限 MCP 依赖目录回归测试，离线测试总数增加到 98 项；
- 可安装的 `abaqus-modeling-guide` Skill，一次一个问题引导环境检查、建模、校验、求解和结果解读；
- 不启动 Abaqus 的 `validate --config` 配置检查命令；
- 2 项命令行校验测试和 2 项 Skill 同步测试，离线测试总数增加到 83 项；
- 隐藏运行的 `Abaqus cae noGUI` MCP 后台桥接及 start/status/stop 命令；
- Windows 使用只读进程句柄检查 PID，避免 Python 3.13 的 `os.kill` 兼容异常；
- 11 项后台桥接和 Windows 进程检查测试，离线测试总数增加到 79 项；
- MCP 插件心跳、状态新鲜度和 Abaqus 进程检测；
- MCP 防卡启动器与显式 `mcp-setup --repair --yes` 修复流程；
- 11 项不启动 Abaqus 的 MCP 防卡测试，离线测试总数增加到 68 项；
- Ollama 和 LM Studio 本机服务检测、模型列表和结构化 JSON 接口；
- 中文需求转换为经过白名单和现有校验器复核的矩形板配置；
- 生成配置预览、教学默认值提示和保存前确认；
- 13 项不联网的本地 AI 安全与兼容测试，离线测试总数增加到 57 项；
- 二维中心圆孔板拉伸模型与独立示例配置；
- 二维悬臂梁均布载荷弯曲模型与独立示例配置；
- 二维方板双向拉伸模型与独立示例配置；
- 三维单层路面单轮移动载荷模型、Fortran DLOAD 模板和独立示例配置；
- 可配置孔半径、全局网格和孔边局部网格；
- 可配置悬臂梁上边界均布载荷和方板两个方向的拉伸位移；
- 根据 `model.type` 安全选择内置 Abaqus 脚本；
- 五类模型各自的中文边界条件、结果说明和输入校验；
- 自动把已校验的轮载参数写入每次运行专用的 Fortran 文件；
- 动力报告遍历全部时间帧，并输出最大竖向位移和极值发生时间；
- 离线测试由 20 项增加到 44 项。

### 已验证

- Windows 11、Abaqus 2021、Abaqus Python 2.7.15；
- 默认圆孔板最大位移模 0.10093824 mm、最大 Mises 应力 562.55554 MPa；
- 默认悬臂梁最大位移模 0.094622037 mm、最大 Mises 应力 71.0299 MPa；
- 默认双向拉伸方板最大位移模 0.14142136 mm、最大 Mises 应力 300 MPa；
- Intel Fortran 19.1.3.311 完成 DLOAD 编译和链接；
- 默认移动轮载模型完成 211 个动力帧，最大位移模 0.18379377 mm、最大竖向位移绝对值 0.18264329 mm、最大 Mises 应力 0.47442088 MPa；
- `.sta` 显示 `THE ANALYSIS HAS COMPLETED SUCCESSFULLY`。

### 计划

- 参数化批量分析；
- 结果曲线和 PDF 报告；
- 论文复现参数证据表；
- 更多 Abaqus 版本验证。

## [0.1.0-alpha] - 2026-08-10

### 新增

- Abaqus、Abaqus Python、abqpy 和 MCP 综合体检；
- 经用户确认的固定版本 Abaqus MCP 安装与注册；
- 五种最小使用场景配置；
- 二维平面应力矩形板拉伸建模与 Abaqus/Standard 自动求解；
- ODB 最大位移模和最大 Mises 应力提取；
- 结构化 JSON 结果与中文 Markdown 报告；
- 输入校验、20 项离线测试和 GitHub Actions；
- Windows/Linux CI、Issue/PR 模板、Dependabot 和发布维护文档；
- README、快速开始、安全说明、贡献指南和论文访问边界。

### 已验证

- Windows 11；
- Abaqus 2021；
- Abaqus Python 2.7.15；
- abqpy 2021.7.3；
- 默认示例最大位移模 0.10017984 mm、最大 Mises 应力 210 MPa。
