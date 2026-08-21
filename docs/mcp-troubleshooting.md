# Abaqus MCP 一直转圈排查

## 为什么会转圈

Abaqus MCP 包含两个独立部分：Codex 启动的 MCP 服务器，以及 Abaqus/CAE 中读取命令的插件。服务器能启动，不代表 CAE 插件正在响应。

如果 CAE 已关闭、插件轮询线程退出，或者旧的 `status.json` 仍写着 `running`，原服务器仍可能写入命令并等待 10～30 秒。客户端在等待期间通常表现为一直转圈。

## 先做环境体检

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex doctor
```

重点看三行：

- `防卡启动器`：是否安装；
- `Abaqus 桥接`：是否在线；
- `桥接说明`：心跳过期、进程消失或插件未启动的具体原因。

## 修复已有安装

修复会复制项目管理的 `mcp_guard.py`，并把 Codex 中已有的 `abaqus-mcp-server` 注册切换到该启动器。它会修改用户级 Codex MCP 配置，因此必须明确确认：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --repair --yes
```

完成后关闭并重新打开 Codex，使客户端重新启动 MCP 进程。

然后启动 Abaqus/CAE，并在插件菜单中启动 MCP。正常插件每约 2 秒更新一次心跳。再次运行 `doctor`，确认 `Abaqus 桥接：在线`。

## 防卡启动器做了什么

每次工具调用前，它会检查：

1. `status.json` 是否存在且格式正确；
2. 插件状态是否为 `running`；
3. 心跳是否在 10 秒内更新；
4. 状态文件记录的 Abaqus 进程是否仍存在。

任何一项失败都会立即返回可读错误，不再创建命令文件或等待 30 秒。桥接正常时，原 MCP 的参数和长作业超时保持不变。

## 仍然离线怎么办

- 确认启动的是 Abaqus/CAE，而不只是许可证服务；
- 在 Abaqus 插件菜单中停止后重新启动 MCP；
- 查看 `%USERPROFILE%\.abaqus-mcp\mcp.log` 和 `thread_error.log` 的末尾；
- 如果日志出现插件线程异常，关闭 CAE 后重新打开；
- 不要把 `commands` 目录里的 JSON 当作脚本手工执行。

防卡启动器解决的是“离线时长时间等待”，不会自动启动 Abaqus，也不会掩盖插件自身错误。
