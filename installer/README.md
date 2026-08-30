# Windows 统一安装向导 v1

该向导先把同一个 GitHub Release 中的桌面助手安装到 `%LOCALAPPDATA%\Programs\AbaqusCodexAssistant`，并安装 Codex Skill，然后才检测 Abaqus。没有安装 Abaqus 也不会阻止核心程序安装；当前仅在检测到可用的 Abaqus 2021 后自动安装已验证的安全修改插件。历史、快照和动作队列继续保存在独立的数据目录 `%LOCALAPPDATA%\AbaqusCodexAssistant`。安装器不包含 Abaqus、Codex、许可证、账号、Cookie、API Key 或论文数据库会话。

## 安装

1. 从 GitHub Releases 下载并完整解压源码包；
2. 关闭 Abaqus/CAE 和中文建模助手；
3. 在解压目录右键打开 PowerShell；
4. 先查看计划：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install.ps1 -WhatIf
```

5. 安装本地助手和 Skill；若检测到 Abaqus 2021，再同时安装安全插件：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install.ps1
```

安装器会要求输入 `INSTALL`，完成前不会写入用户目录。默认不下载 abqpy 或 MCP；需要时分别增加 `-InstallAbqpy`、`-InstallMcp`，这些选项会联网并修改当前用户环境。

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
- v1 仍要求电脑已有 Python 3.10 或更高版本；后续正式 EXE 可以内置独立 Python 运行时；
- MCP、abqpy 需要联网，所以必须由用户主动选择；
- Abaqus 2021 安装了安全插件后必须重启 Abaqus/CAE 和 Codex；
- 未购买代码签名证书前，Windows 可能显示未知发布者提示。
