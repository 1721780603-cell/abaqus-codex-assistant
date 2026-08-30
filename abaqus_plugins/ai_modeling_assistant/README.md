# Abaqus 2021 中文建模助手插件外壳

这是第一版界面演示，只用于确认窗口布局和中文输入是否正常。它不会连接 AI、MCP 或 Abaqus Kernel，也不会修改当前模型。

## 手动试用

1. 关闭 Abaqus/CAE 2021。
2. 在个人目录下创建 `abaqus_plugins/ai_modeling_assistant` 文件夹。
3. 把本目录中的三个 `.py` 文件复制进去。
4. 重新打开 Abaqus/CAE 2021。
5. 点击 `Plug-ins → AI 中文建模助手...`。

窗口可以移动和缩放，首次打开时会尽量靠近 Abaqus 主窗口右侧。

## 当前限制

- 模型摘要是明确标注的模拟数据；
- “发送”只生成模拟计划；
- “应用修改”按钮保持禁用；
- 不读取 API Key，不访问网络，不提交 Job；
- 仅针对 Abaqus 2021 的 Python 2.7 GUI 环境。

删除个人插件目录中的 `ai_modeling_assistant` 文件夹并重启 Abaqus，即可卸载这个界面演示版。
