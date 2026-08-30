# Abaqus 2021 安全材料动作插件

这个插件只服务于桌面助手第一版的一个闭环：读取已有单行各向同性弹性参数，以及在用户确认后修改该参数。

- GUI 端使用 FOX 主事件循环短轮询，不创建 Python 后台线程；
- 不接受任意 Python、脚本路径或网络请求；
- Kernel 端重新验证计划、旧值、状态指纹和有效期；
- 写入前先把当前已保存的 CAE 另存为同目录唯一工作副本；
- 原 CAE 文件永不覆盖；回执不公开完整路径；
- 当前仅适配并允许 Abaqus/CAE 2021。

推荐从项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --dry-run
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --yes
```

安装后关闭并重新打开 Abaqus/CAE 2021。
