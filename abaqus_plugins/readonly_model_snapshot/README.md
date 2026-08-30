# Abaqus 2021 一次性只读快照插件

这个插件只解决一个问题：用户在 Abaqus/CAE 2021 中点击一次菜单后，生成一份有限模型名称快照，供 Python 3 桌面助手读取。

## 安全边界

- 不启动线程、计时器或 MCP；
- 不访问网络，也不读取 API Key；
- 不执行任意 Python；
- 不修改、保存或另存 CAE；
- 不创建或提交 Job；
- 只读取模型、零件、材料、分析步、实例、载荷、边界条件和接触名称；
- 不记录 CAE 路径、工作目录、用户名、材料数值、节点或网格。

## 手动安装

项目不会静默改动 Abaqus 插件目录。用户确认安装后，把整个 `readonly_model_snapshot` 文件夹复制到当前用户的 `abaqus_plugins` 目录，然后重启 Abaqus/CAE 2021。菜单注册本身不依赖 GUI 版本元组；点击菜单后，Kernel 端通过 Abaqus 2021 可用的 `uti.getVersion()` 严格检查发行年份。

当前插件版本为 `0.2.3`。如果快照失败，消息区会显示固定阶段码，例如 `VERSION_CHECK_FAILED` 或 `WRITE_FAILED`；阶段码不会包含模型名称、文件路径或异常原文。

安装成功后，菜单位置为：

```text
Plug-ins → Abaqus Codex Assistant → Refresh Read-Only Snapshot
```

每次改变模型后都要重新点击一次。插件不会在后台监视模型变化。
