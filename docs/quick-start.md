# 快速开始

## 1. 创建隔离环境

不要把开发依赖安装进 Abaqus 2021 自带的 Python 2.7。现代 Python 负责运行主程序，Abaqus 自带 Python 只负责执行建模与后处理脚本。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install "abqpy==2021.*"
```

如果使用其他 Abaqus 年份，把 `2021` 改成相同的大版本号。

## 2. 检查环境

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex doctor
```

输出包含两种结论：

- 本地基础模式：Abaqus 与 abqpy 可用；
- Codex 智能模式：基础模式可用，并且 Abaqus MCP 已注册、可加载。

## 3. 配置 MCP（可选）

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup
```

不带 `--yes` 时程序只会拒绝并显示安全提醒。确认后才运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --yes
```

安装器固定源码 commit 和 Python 依赖版本，不覆盖已有 `abaqus_v6.env` 或 GUI 插件目录。

## 4. 选择场景

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex configure --scenario learning
```

可用值：`learning`、`paper`、`research`、`production`、`teaching`。

## 5. 使用本地 AI 生成配置（可选）

先启动 Ollama 或 LM Studio 的本机服务，再检查连接：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai doctor
```

Ollama 示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai generate `
  --provider ollama `
  --model "你的本机模型名称" `
  --prompt "建立长 200 mm、高 100 mm、厚 2 mm 的矩形板，右边拉伸 0.2 mm。"
```

程序会显示通过校验的完整 JSON，并列出哪些参数沿用了教学默认值。输入 `y` 后只保存 `configs/local_ai_rectangle.json`，不会自动运行 Abaqus。人工检查配置后，可单独运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\local_ai_rectangle.json
```

第一版只支持二维矩形板单向拉伸、mm 和 MPa。其他模型或单位应停止并提示，不应由 AI 猜测。完整说明见[本地 AI 入门](local-ai.md)。

## 6. 运行示例

运行矩形板：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\rectangle_tension.json
```

运行中心圆孔板：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\plate_with_hole_tension.json
```

运行悬臂梁均布载荷弯曲：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\cantilever_bending.json
```

运行方板双向拉伸：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\biaxial_tension.json
```

运行三维路面单轮移动载荷：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\moving_load_road.json
```

移动载荷示例还要求 Abaqus 能调用 Visual Studio 和 Intel Fortran Classic。它会在本次 `work/runs/<运行时间>/` 中生成并编译 `moving_pressure_dload.for`。

程序会显示结果 JSON 和中文报告的绝对路径。计算失败时先查看 `work/runs/<运行时间>/abaqus_console.log`、`.sta`、`.msg` 和 `abaqus.rpy`。

## 7. 修改参数

复制相应 JSON 示例后，可以修改：

- 长、宽、厚度；
- 弹性模量和泊松比；
- 单向拉伸的右边位移；
- 悬臂梁的上边界均布载荷；
- 双向拉伸的右边和上边位移；
- 移动轮载的压力、速度、接触区、横向位置和最大时间增量；
- 网格尺寸；
- 圆孔板的孔半径和孔边局部网格尺寸；
- CPU 数量；
- 长度和应力单位标签。

`model.type` 可使用 `rectangle`、`plate_with_hole`、`cantilever_bending`、`biaxial_tension` 或 `moving_load_road`。圆孔板还会检查孔直径小于板长和板高，并要求孔边网格不比全局网格更粗；悬臂梁载荷和双向拉伸的两个位移必须大于零；移动载荷会检查接触区没有越界，且时间增量足够描述移动过程。Abaqus 不自动换算单位，所有输入必须使用一致单位制。

建议按矩形板、圆孔板、悬臂梁、双向拉伸、移动载荷的顺序学习。每次只修改一个参数，并先预测结果变大还是变小，再运行 Abaqus 核对。
