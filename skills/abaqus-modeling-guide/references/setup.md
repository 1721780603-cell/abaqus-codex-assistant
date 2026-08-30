# 首次安装与环境准备

只有项目不存在或环境体检发现缺项时才读取本文件。每次只处理一个缺项，并在联网、安装软件或修改用户配置前征得同意。

## 优先定位 EXE 安装版

普通用户首选 EXE 安装版。默认安装目录是 `%LOCALAPPDATA%\Programs\AbaqusCodexAssistant`，项目 Python 固定放在：

```text
%LOCALAPPDATA%\Programs\AbaqusCodexAssistant\runtime\python.exe
```

先展开环境变量并解析为当前电脑上的绝对路径，再确认该文件真实存在。EXE 安装版自带项目 Python，普通用户无需另装 Python 或 Git。Abaqus 本体、合法许可证以及用户本人的 Codex 安装和登录不包含在应用中，仍需用户自行准备。

## 定位源码项目

源码项目根目录应同时包含：

- `pyproject.toml`；
- `configs/rectangle_tension.json`；
- `src/abaqus_codex/`；
- `.venv\Scripts\python.exe`。

按以下顺序只读检查：

1. EXE 安装版的默认完整应用目录 `%LOCALAPPDATA%\Programs\AbaqusCodexAssistant`；
2. 当前目录及其父目录；
3. 用户明确提供的目录。

每次都先确定并显示检测到的项目 Python 绝对路径：EXE 安装版使用 `runtime\python.exe`，源码版使用项目 `.venv\Scripts\python.exe`。不要无边界扫描用户目录，不要根据其他用户的电脑猜测路径，也不要退回系统 Python。只安装到 `CODEX_HOME` 的本 Skill 不包含桌面应用或项目运行环境。

## 项目尚未下载

普通用户优先从项目的 [GitHub Releases](https://github.com/1721780603-cell/abaqus-codex-assistant/releases) 下载 `AbaqusCodexAssistant-Setup-<版本>-x64.exe` 并双击安装。EXE 会安装自带的项目 Python、桌面助手和 Codex Skill，并创建启动入口；用户不需要下载源码、解压项目、运行 PowerShell，也不需要预装 Python 或 Git。

EXE 不包含 Abaqus、许可证或 Codex 账号。安装核心应用不要求电脑已经安装 Abaqus，但真实建模仍需要用户自己的合法 Abaqus；Codex 智能模式仍使用用户本人安装并登录的 Codex。安装完成后先运行只读环境体检，再根据检测到的 Abaqus 年份逐项询问是否安装严格匹配的 abqpy，以及是否为 Codex 智能模式配置 MCP。abqpy 和 MCP 都可能联网或修改用户级配置，没有明确确认时不得安装。

若 EXE 暂时无法使用，或用户明确参与开发，才使用同一 Release 的完整源码包或 Git 仓库。完整源码包必须整体解压，不能只下载一个 `install.ps1`。源码备用安装说明见项目根目录 `installer/README.md`。

若 Codex 使用自定义 `CODEX_HOME`，统一安装器会优先把 Skill 放到该活动主目录；安装前先核对计划中显示的 Skill 目标。不要复制 Codex 凭据或会话文件。

需要参与开发且选择 Git 克隆时，才确认 Git 可用，再询问用户希望把项目放在哪个父目录。得到同意后才执行：

```powershell
git clone https://github.com/1721780603-cell/abaqus-codex-assistant.git
```

不要克隆到系统目录，也不要覆盖同名非空文件夹。

## 使用 EXE 安装版的内置运行时

若应用位于默认安装目录，先把项目 Python 解析为绝对路径并确认存在，再运行：

```powershell
$ProjectPython = [System.IO.Path]::GetFullPath("$env:LOCALAPPDATA\Programs\AbaqusCodexAssistant\runtime\python.exe")
& $ProjectPython -m abaqus_codex onboard --json
```

该运行时由 EXE 安装器维护，不要在安装目录中手工替换 Python 或包文件。升级应用时使用新的 EXE 安装包；不要从其他电脑复制运行时、Codex 凭据或会话文件。

## 创建源码开发环境

只有从源码参与开发时才执行以下命令。它们均在源码项目根目录运行；运行前逐条说明其作用：

```powershell
py -m venv .venv
$ProjectPython = (Resolve-Path ".\.venv\Scripts\python.exe").Path
& $ProjectPython -m pip install -e .
& $ProjectPython -m abaqus_codex onboard --json
```

第一条只创建项目虚拟环境，第二条以可编辑方式安装本项目，第三条只做首次启动检查，不会自动安装或登录。若安装需要访问网络，先说明并请求同意。体检完成后按 [onboarding.md](onboarding.md) 只让用户选择一条下一步路线。

## 处理体检结果

- **没有 Abaqus**：停止自动操作，引导用户从 Dassault Systèmes 官方渠道安装并配置合法许可证。不要替用户下载非官方安装包。
- **检测到 Abaqus 2026**：只报告用户/项目实测兼容未通过，当前自动流程禁用。不要运行 `abqpy-setup --yes`、`mcp-setup`、`mcp-headless start` 或求解；不要猜测故障原因，等待项目修复和重新验证。
- **Abaqus 2021–2025 可用、abqpy 缺失或版本不匹配**：先展示体检给出的 `abqpy==<年份>.*` 计划。得到同意后使用检测到的项目 Python 绝对路径运行 `-m abaqus_codex abqpy-setup --yes`；该命令只安装检测年份，不会失败后改装其他年份。
- **MCP 缺失**：基础建模仍可继续。只有用户选择 Codex 智能模式时才介绍 `mcp-setup`；说明该命令会下载代码并修改用户级 MCP 配置，获得同意后才能带 `--yes` 执行。
- **MCP 已配置但离线**：普通建模继续使用 CLI；用户需要 MCP 时再检查 `mcp-headless status`。
- **GitHub、Zotero 或 ScienceDirect 未就绪**：不影响基础建模。只在用户选择“科研复现全套”或指定单项修复时处理，并遵守 [onboarding.md](onboarding.md) 中的凭据和付费墙安全边界。
- **Fortran 缺失**：前四个二维模型仍可继续；只阻止三维移动荷载模型。

体检完成不等于结果可信。正式工程仍需核对单位、材料、边界条件、网格收敛性和适用规范。
