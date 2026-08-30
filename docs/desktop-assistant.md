# 中文建模助手（Abaqus 2021）

这是“同时打开 Abaqus 和中文应用”的第一个真实闭环。它没有接入 AI，而是用确定性的中文句式完成可审阅、可确认、可追溯的二维矩形板拉伸十步流程。

## 第一版能做什么

- 读取当前模型中的对象名称快照；
- 展示几何、材料、截面、装配、分析步、相互作用、边界与载荷、网格、Job、结果与报告的十步路线；
- 识别 `创建一个长 100 mm、宽 20 mm 的二维矩形板，模型名 Model-1，零件名 Plate`；
- 先在受保护工作副本中创建二维可变形矩形板，拒绝覆盖同名零件；
- 依次创建 `Steel` 材料、`PlateSection` 截面和 `Plate-1` 实例；
- 创建 `TensionStep` 静力分析步，并解释单一连续板为何无需相互作用；
- 创建防刚体位移、左边约束和右边 0.1 mm 拉伸边界条件；
- 设置 2 mm 全局网格并划分零件；
- 创建并异步提交 `rectangle_tension_2d`，不在界面线程中阻塞等待；
- 读取成功完成的 ODB，输出最大位移模和最大 Mises 应力，并新建不覆盖的中文 Markdown 报告；
- 识别 `把 Model-1 中 Steel 的弹性模量改为 210000 MPa`；
- 从当前 Abaqus/CAE 会话读取材料的实时弹性模量和泊松比；
- 先显示模型、材料、旧值、新值、单位和风险提示，不直接执行；
- 只有点击“应用修改”并二次确认后才发布白名单动作；
- 应用前把已保存的原 CAE 另存为同目录唯一工作副本；
- 修改已有单行各向同性 `Elastic` 表，并保存工作副本；
- 旧值变化、计划过期或计划重复使用时拒绝执行。

## 第一版不能做什么

- 不理解开放式自然语言，不联网，也不调用 Codex、OpenAI API 或本地模型；
- 十步向导只支持内置的矩形板拉伸教学场景，不能自由组合零件、载荷或接触；
- 独立材料修改命令只支持已有简单弹性材料，不修改温度或场变量相关弹性表；
- 不创建接触；当前第 6 步只是对单一连续板执行“无需相互作用”的教学检查；
- 不接受任意 Abaqus Python、脚本路径或完整本机路径；
- 不支持 Abaqus 2022 或 2026，本阶段只适配 Abaqus 2021；
- 不判断模型单位是否真的为 mm-N-s-MPa，必须由用户确认。

## 安装

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --dry-run
.\.venv\Scripts\python.exe -m abaqus_codex assistant-setup --yes
```

安装器只接受检测到的 Abaqus 2021。目标为 `%USERPROFILE%\abaqus_plugins\safe_material_action`；已有不同版本会整体改名备份，不递归删除用户文件。

随后关闭并重新打开 Abaqus/CAE 2021。插件通过 GUI 主事件循环处理请求，不使用访问 `mdb` 的后台 Python 线程。

## 使用

1. 在 Abaqus/CAE 2021 打开目标 CAE，并先保存一次；未保存的新 MDB 会被拒绝。
2. 启动助手或点击“刷新模型”时，助手会自动请求 Abaqus 生成只读概要，不需要手动进入 Plug-ins 菜单。
3. 启动桌面助手：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant
```

4. 第一次使用先点击左侧“环境体检”。它会只读检查项目 Python、Abaqus、Abaqus Python、abqpy、Codex、Abaqus MCP、Git、GitHub、Zotero 和 ScienceDirect，不会安装软件、登录账号或修改模型。
5. 使用窗口自动填入的命令，从几何、材料、截面、装配、分析步、相互作用检查、边界条件、网格、Job 一直做到结果报告。
6. 每一步先点击“生成计划”，核对对象、旧值、新值、风险和 mm-N-s-MPa 约定。
7. 除相互作用教学检查外，点击“应用修改”并在确认框选择“是”后才会执行。
8. Job 提交后等待 Abaqus 完成，再生成第 10 步计划；未完成的 Job 会被明确拒绝。
9. 回到 Abaqus 检查当前工作副本，并打开同目录的新建 `*_report_zh_001.md` 报告。

环境体检把结果分成“必需环境”“Codex 联动”“代码工具”和“科研可选”四层。黄色或灰色的 Zotero、ScienceDirect 等可选项不会阻止基础建模；选择任一检查项即可在下方看到检查结果和下一步建议。安装、修复和登录仍需用户另行确认，体检按钮本身始终是只读的。

## 初学者如何知道下一步

不需要自己记住后续九条命令。每一步明确成功后，助手会自动把下一步固定句式填入“中文建模命令”输入框，并同步更新顶部的“第几/10 步”。左侧“初学者建模路线”下面还有两个入口：

- `查看十步指令`：显示每一步的目的、完整固定句式和当前所在步骤，可选择复制；
- `操作记录`：按最新优先显示已经生成的修改计划、执行成功、执行失败和无需写模型的检查结果。

操作记录保存在 `%LOCALAPPDATA%\AbaqusCodexAssistant\assistant_history.json`。它只记录界面已经展示的对象名、参数、安全说明、执行状态和工作副本文件名，不记录完整路径、凭据或模型文件；最多保留最近 120 条。清空输入不会清空历史。旧版本已经完成但当时没有记录的步骤无法事后凭空恢复，升级后的新操作才会持续保留。

应用成功后的 CAE 名称类似 `original__aca_edit_20260830-120000_001.cae`。原 CAE 不覆盖，回执只显示文件名，不显示完整路径。

当前进度保存在助手内存中。中途关闭助手后，CAE 中已经完成的对象不会丢失，但窗口会回到第 1 步示例；请直接输入要继续的固定步骤命令。自动恢复需要只读快照先增加不含路径的网格和 Job 状态，当前版本不会靠猜测重复划分网格或提交 Job。

## 模拟演示

没有 Abaqus 时可运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex assistant --mock
```

模拟模式会完整展示计划、确认和应用流程，但不会创建真实 CAE。窗口顶部和摘要始终标注“模拟”。

## 为什么不复用旧 MCP 自动线程

旧第三方 MCP 会在 Python 后台线程中轮询并访问 `mdb`，部分 Abaqus 2021 会话可能表现为进度条移动或鼠标转圈。安全动作插件改为 FOX GUI 主事件循环短轮询，GUI 只把程序生成的请求 ID 传给固定 Kernel 函数。

项目不会读取 Codex 桌面凭据，也不会把 API Key 写入插件。未来接入 AI 时，AI 只能生成同一白名单 Action JSON，仍必须人工点击应用。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_rectangle_creation_flow tests.test_material_edit_flow tests.test_safe_action_bridge tests.test_abaqus_2021_material_executor tests.test_guided_rectangle_flow tests.test_safe_action_setup -v
```

这些测试使用临时目录和假 Abaqus 对象，不需要许可证、不启动 Abaqus、不连接网络。

## 官方 API 依据

- [Abaqus Kernel 与 GUI 是独立进程](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECUSRefMap/simacus-c-comcommandskernelandgui.htm)
- [GUI 使用 `sendCommand` 向 Kernel 发命令](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECUSRefMap/simacus-c-comcommandsexecute.htm)
- [保存当前 MDB 与 Save As](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-dbsmdbsave.htm)
- [Elastic 对象及 `setValues`](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-elasticpyc.htm)
