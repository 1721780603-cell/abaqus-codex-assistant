# 首次安装与环境准备

只有项目不存在或环境体检发现缺项时才读取本文件。每次只处理一个缺项，并在联网、安装软件或修改用户配置前征得同意。

## 定位已有项目

项目根目录应同时包含：

- `pyproject.toml`；
- `configs/rectangle_tension.json`；
- `src/abaqus_codex/`。

不要根据其他用户的电脑猜测路径。优先检查当前目录和用户明确提供的目录。

## 项目尚未下载

先确认 Git 可用，再询问用户希望把项目放在哪个父目录。得到同意后才执行：

```powershell
git clone https://github.com/1721780603-cell/abaqus-codex-assistant.git
```

不要克隆到系统目录，也不要覆盖同名非空文件夹。

## 创建项目环境

以下命令均在项目根目录执行。运行前逐条说明其作用：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m abaqus_codex doctor
```

第一条只创建项目虚拟环境，第二条以可编辑方式安装本项目，第三条只做环境检查。若安装需要访问网络，先说明并请求同意。

## 处理体检结果

- **没有 Abaqus**：停止自动操作，引导用户从 Dassault Systèmes 官方渠道安装并配置合法许可证。不要替用户下载非官方安装包。
- **Abaqus 可用、abqpy 缺失或版本不匹配**：根据体检得到的 Abaqus 年份建议对应的 `abqpy==<年份>.*`。展示命令并在安装前征得同意。
- **MCP 缺失**：基础建模仍可继续。只有用户选择 Codex 智能模式时才介绍 `mcp-setup`。
- **MCP 已配置但离线**：普通建模继续使用 CLI；用户需要 MCP 时再检查 `mcp-headless status`。
- **Fortran 缺失**：前四个二维模型仍可继续；只阻止三维移动荷载模型。

体检完成不等于结果可信。正式工程仍需核对单位、材料、边界条件、网格收敛性和适用规范。
