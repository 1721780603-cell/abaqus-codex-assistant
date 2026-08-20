# 本地 AI 入门

## 第一版能做什么

本地 AI 模式把一段中文需求转换为二维矩形板单向拉伸 JSON。它支持：

- Ollama，默认地址 `http://127.0.0.1:11434`；
- LM Studio，默认地址 `http://127.0.0.1:1234`；
- 长、板高、厚度、材料名、弹性模量、泊松比、右边位移、网格和 CPU 数量；
- 生成后预览、教学默认值提示、现有配置校验和人工确认。

它不会下载模型，不会调用 Codex 或 OpenAI API，不会生成或执行任意 Python/Fortran，也不会自动启动 Abaqus。

## 1. 启动本机模型服务

### Ollama

安装并启动 Ollama，确保至少已经下载一个本机模型。项目通过官方接口 `/api/tags` 列出模型，通过 `/api/chat` 请求结构化输出。

官方文档：

- <https://docs.ollama.com/api/introduction>
- <https://docs.ollama.com/capabilities/structured-outputs>

### LM Studio

在 LM Studio 的 Developer 页面启动本地服务器，或者运行：

```powershell
lms server start
```

项目使用 OpenAI 兼容的 `/v1/models` 和 `/v1/chat/completions`。如果你在 LM Studio 中启用了认证，请只在当前终端设置令牌，不要写入仓库：

```powershell
$env:LM_API_TOKEN = "你的本机 LM Studio 令牌"
```

官方文档：

- <https://lmstudio.ai/docs/developer/core/server>
- <https://lmstudio.ai/docs/developer/openai-compat>
- <https://lmstudio.ai/docs/developer/openai-compat/structured-output>

## 2. 检查连接

同时检查两个默认服务：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai doctor
```

只检查一个服务：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai doctor --provider ollama
.\.venv\Scripts\python.exe -m abaqus_codex local-ai doctor --provider lm-studio
```

输出会列出本机服务返回的模型名称。程序不会自动下载或启动模型。

## 3. 生成矩形板配置

Ollama 示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai generate `
  --provider ollama `
  --model "本机模型列表中的名称" `
  --prompt "建立长 200 mm、高 100 mm、厚 2 mm 的矩形板，弹性模量 210000 MPa，泊松比 0.3，右边拉伸 0.2 mm，网格 5 mm。"
```

LM Studio 示例：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex local-ai generate `
  --provider lm-studio `
  --model "本机模型列表中的名称" `
  --prompt "建立长 200 mm、高 100 mm、厚 2 mm 的矩形板，右边拉伸 0.2 mm。"
```

程序先显示完整 JSON。没有在需求中明确给出的参数会沿用已经真实验证过的矩形板教学默认值，并逐项列出。输入 `y` 后才保存到：

```text
configs/local_ai_rectangle.json
```

该文件包含本机生成的参数，默认被 Git 忽略。

## 4. 人工检查后运行

至少检查尺寸、单位、材料参数、载荷和网格。确认无误后再单独运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\local_ai_rectangle.json
```

## 安全边界

- 只允许 `localhost`、`127.0.0.1` 或 `::1` 的 HTTP 地址；
- 不允许局域网、公网、带凭据或带路径的自定义地址；
- 第一版只接受二维矩形板、mm 和 MPa；
- 常见的 cm、m、inch、Pa、kPa 和 GPa 会在请求模型前被拒绝，不做隐式单位换算；
- 材料名称、弹性模量和泊松比必须一起给出，避免材料参数混搭；
- AI 只能填写九个白名单参数，不能指定作业脚本、命令或文件路径；
- 模型输出必须符合 JSON Schema，并再次通过项目已有参数校验；
- 请求文本最长 10000 字符，响应最大 2 MB；
- 生成和求解分开执行，避免模型响应直接调用 Abaqus；
- 本地部署减少外发数据，但仍要遵守模型许可证和单位的工程数据政策。

本地 AI 生成的内容只是输入草稿，不是工程审查或设计结论。正式项目仍需人工确认材料、载荷、边界条件、网格收敛和适用规范。
