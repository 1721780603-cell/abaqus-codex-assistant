# 首次启动流程

## 1. 环境体检

运行：

```powershell
.\.venv\Scripts\abaqus-codex.exe doctor
```

程序依次检查 Abaqus 命令与版本、Abaqus 自带 Python、abqpy 版本、MCP 文件、Codex 注册和 MCP 本地导入。

没有 Abaqus 时程序停止建模，并提示从正规渠道安装和配置许可证。项目不分发 Abaqus。

## 2. 可选 MCP 配置

本地基础模式不需要 MCP。智能模式缺少 MCP 时，用户阅读将发生的下载、文件复制和 Codex 配置变更后，运行：

```powershell
.\.venv\Scripts\abaqus-codex.exe mcp-setup --yes
```

没有 `--yes` 时安装器不会修改电脑。已有用户文件不会被覆盖，安装后必须再次导入服务器验证。

## 3. 使用场景

第一版场景为：Abaqus 入门学习、单篇论文复现、科研参数分析、实际工程项目、课程与教学演示。场景决定解释和检查方式，不用于判断身份或论文权限。

## 4. 第一阶段限制

当前计算模板只实现二维矩形板拉伸。论文下载、论文参数证据表、参数化批处理和复杂工程审核属于后续阶段。
