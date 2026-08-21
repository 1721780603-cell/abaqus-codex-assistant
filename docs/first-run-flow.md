# 首次启动流程

## 1. 环境体检

运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex doctor
```

程序依次检查 Abaqus 命令与版本、Abaqus 自带 Python、abqpy 版本、MCP 文件、Codex 注册、MCP 本地导入、插件心跳和 Abaqus 进程。

没有 Abaqus 时程序停止建模，并提示从正规渠道安装和配置许可证。项目不分发 Abaqus。

## 2. 可选 MCP 配置

本地基础模式不需要 MCP。智能模式缺少 MCP 时，用户阅读将发生的下载、文件复制和 Codex 配置变更后，运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --yes
```

没有 `--yes` 时安装器不会修改电脑。已有用户文件不会被覆盖，安装后必须再次导入服务器验证。

已有 MCP 调用一直转圈时，使用明确修复参数切换到防卡启动器：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --repair --yes
```

修复后需要重新打开 Codex，再启动 Abaqus/CAE 中的 MCP 插件。

## 3. 使用场景

第一版场景为：Abaqus 入门学习、单篇论文复现、科研参数分析、实际工程项目、课程与教学演示。场景决定解释和检查方式，不用于判断身份或论文权限。

## 4. 第一阶段限制

当前计算模板实现二维矩形板拉伸、中心圆孔板拉伸、悬臂梁均布载荷弯曲、方板双向拉伸，以及三维单层路面单轮移动载荷教学模型。分层道路、双轮双轴、路面不平度、车辆—路面耦合、论文参数证据表、参数化批处理、网格收敛自动化和复杂工程审核属于后续阶段。
