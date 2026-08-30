# Windows 统一安装向导 v1

该向导先把同一个 GitHub Release 中的桌面助手安装到 `%LOCALAPPDATA%\Programs\AbaqusCodexAssistant`，并安装 Codex Skill，然后才检测 Abaqus。没有安装 Abaqus 也不会阻止核心程序安装；当前仅在检测到可用的 Abaqus 2021 后自动安装已验证的安全修改插件。历史、快照和动作队列继续保存在独立的数据目录 `%LOCALAPPDATA%\AbaqusCodexAssistant`。安装器不包含 Abaqus、Codex、许可证、账号、Cookie、API Key 或论文数据库会话。

## 前置条件

- Windows 10/11；
- Python 3.10 或更高版本，并能通过 `py -3` 或 `python` 启动；
- 从同一个 GitHub Release 下载并**完整解压**源码包。不能只下载 `installer/install.ps1`，安装器还需要同包内的 `pyproject.toml`、`src/`、`skills/` 和 `abaqus_plugins/`；
- 安装核心助手不要求先安装 Abaqus；真实建模仍需要合法安装、可用许可证和明确版本的 Abaqus；
- 安装或升级前关闭 Abaqus/CAE 和中文建模助手。

默认 Codex 主目录是 `%USERPROFILE%\.codex`。若环境变量 `CODEX_HOME` 已设置，统一安装器会优先把 Skill 安装到该活动主目录；高级或隔离安装也可以显式传入 `-CodexHome`。安装计划和最终清单都会显示实际目标。不要在两个 Codex 主目录之间手工复制凭据或会话文件。

## 安装

1. 在完整解压的 Release 根目录右键打开 PowerShell；
2. 先查看计划：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install.ps1 -WhatIf
```

3. 安装本地助手和 Skill；若检测到 Abaqus 2021，再同时安装安全插件：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install.ps1
```

安装器会要求输入 `INSTALL`，完成前不会写入用户目录。默认不下载 abqpy 或 MCP；需要时分别增加 `-InstallAbqpy`、`-InstallMcp`，这些选项会联网并修改当前用户环境。

核心应用和 Skill 会先完成安装，随后才处理可选的安全插件、abqpy 或 MCP。如果可选组件因网络、版本或注册问题失败，安装器会显示警告，把失败状态写入安装清单，并继续保留可启动、可修复的核心安装。先根据警告处理缺项，再从完整 Release 目录运行 `-Mode Repair` 并带上需要重试的可选开关。

已有安装需要升级时使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install.ps1 -Mode Repair
```

旧应用目录和旧 Skill 会先备份；只有本次确实安装安全插件时，插件才交给已有安全安装边界处理。不覆盖用户 CAE、ODB、个人模型和凭据。

## 卸载

关闭 Abaqus、Codex 和助手后，从解压的 Release 目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\uninstall.ps1
```

卸载器只接受带本项目清单的安装目录。Skill 和 Abaqus 插件会先改名保留为可恢复副本；Abaqus、Codex、模型文件、结果文件和历史备份不在删除范围内。增加 `-KeepRecoveryCopy` 可连应用程序本身也只改名保留。

## 当前限制

- 核心程序和 Skill 先安装，随后才只读检测 Abaqus；未检测到 Abaqus 时保留核心安装并给出配置提示；
- 维护者只在 Abaqus 2021 上完成安全修改插件的真机验证；其他版本先安装核心助手和 Skill，但不会自动启用模型修改；
- v1 不内置 Python 运行时；后续正式 EXE 再评估自包含运行时；
- MCP、abqpy 需要联网，所以必须由用户主动选择；
- Abaqus 2021 安装了安全插件后必须重启 Abaqus/CAE 和 Codex；
- 未购买代码签名证书前，Windows 可能显示未知发布者提示。
