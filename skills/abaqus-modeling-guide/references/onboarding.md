# 首次启动与连接向导

本向导的目标是让初学者先看懂“哪些已就绪、哪些可以以后再配”，不是一次修改电脑上的所有设置。

## 第一步：只读体检

运行前说明：“下面命令只检查本机状态，不会安装软件、修改配置或登录账号。”

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex onboard --json
```

读取 JSON 后按下列层级解释：

- **基础建模**：Abaqus、Abaqus 内置 Python 与对应年份的 abqpy。这些是创建和求解支持模型的基础。
- **Codex 智能建模**：在基础环境上增加 Abaqus MCP。MCP 不是基础 CLI 建模的必需品。
- **科研工具**：GitHub CLI 登录、Zotero 本地 API / Connector 和 ScienceDirect 机构访问。它们都是可选项。

不要把“未检查”说成“未安装”，也不要把 ScienceDirect 的手动确认说成程序已验证登录。

## 第二步：只问一个路线问题

把下面四个互斥选项原样解释给用户，然后等待他选择：

1. **基础建模**：只补齐 Abaqus、内置 Python 和 abqpy，就绪后直接进入模型选择。
2. **Codex 智能建模**：先满足基础建模，再安装、注册或修复 Abaqus MCP。
3. **科研复现全套**：若用户尚未说明建模方式，下一轮只问他需要基础 CLI 还是 MCP 智能建模；满足所选建模层级后，再依次检查 GitHub、Zotero 和 ScienceDirect 机构访问。
4. **我已有明确问题（单项修复）**：只询问用户想修复哪一项，不顺带修改其他配置。

选定路线后仍然每次只问一个问题。一个缺项处理完并重新检查后，再进入下一个缺项。

用户完全不熟悉这些工具或不知道如何选择时，推荐“基础建模”，理由是它能最快完成并核对第一个模型；推荐不等于代选，仍要等待用户确认。

## 统一确认规则

下列操作不是只读检查，执行前必须分别说明用途、可能的改变和是否使用网络，并得到用户明确同意：

- 下载或安装软件；
- 注册或修复 MCP；
- 启用 Zotero 本地 API；
- 重启 Codex、Abaqus、Zotero 或浏览器；
- 打开 GitHub 或 ScienceDirect 登录页；
- 向 Zotero 导入条目或附件。

一次同意只覆盖当前说明的操作，不把它当成后续所有操作的长期授权。

## Abaqus、Python 与 abqpy

项目 Python 能运行首次向导，不等于 Abaqus 内置 Python 也已连通。体检要分开解释：

- 项目 Python：运行本项目 CLI；
- Abaqus 内置 Python：实际执行 Abaqus 建模脚本；
- abqpy：为编辑器、类型提示和开发体验提供对应年份的 Python 包。

没有 Abaqus 时，只引导用户从 Dassault Systèmes 官方渠道安装并使用合法许可证，不下载、破解或绕过许可。

## Abaqus MCP 与 Codex

Codex 本地客户端使用共享的 MCP 配置；可以用下列只读命令查看是否已注册：

```powershell
codex mcp list
```

“出现在列表中”只代表已注册，不代表 Abaqus 端心跳或桥接已就绪。请以 `onboard --json` 中的 MCP 综合状态为准。

只有用户选择智能建模并同意下载代码、修改用户级 MCP 配置后，才运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --yes
```

已注册但配置异常时，说明会替换现有注册，再单独征得同意：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-setup --repair --yes
```

修改 MCP 配置后可能需要重启 Codex 才能生效。重启前也要说明原因并请求同意。GUI 持续转圈时，可先只读检查：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-headless status
```

只有用户同意启动后台 Abaqus noGUI 桥接后，才运行：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex mcp-headless start
```

## GitHub 登录

只用下列命令检查 `github.com` 的 GitHub CLI 登录状态：

```powershell
gh auth status --hostname github.com
```

不回显、记录或复制任何 token。未登录时，先说明命令会打开 GitHub 官方网页并将登录信息保存给 GitHub CLI，得到用户同意后才执行：

```powershell
gh auth login --hostname github.com --git-protocol https --web
```

网页上的设备码由用户本人输入。登录后只再运行 `gh auth status --hostname github.com` 确认成功，不要显示或查询令牌内容。

## Zotero 连接

若当前 Codex 中可用 Zotero Skill 或其 helper，优先按该 Skill 的 `status --json` 流程检查，因为它能区分 Zotero 本地 API 和 Connector。不要猜测固定的插件版本路径。若没有可用 helper，`onboard --json` 只对 `127.0.0.1` 上的 Zotero 回环端点做连通性检查，不读取文献库内容。

没有 Zotero Skill/helper 且本地端点未响应时，只报告“缺少可用的 Zotero 连接工具”。可以把安装兼容 Zotero 连接工具作为下一个单独选项，但安装前必须说明来源、权限和网络影响并再次征得同意；不能猜测插件目录、运行未知脚本或直接修改 Zotero 配置。

当状态表明本地 API 未启用或需要重启 Zotero 时，先说明会修改 Zotero 本地设置或重启应用，得到同意后再按 Zotero Skill 的 `enable --restart` 流程处理。

检索或导出现有本地文献时遵守 Zotero Skill 的只读流程。向 Zotero 新增条目、导入 RIS / BibTeX 或附件前，必须再次得到用户确认。

## ScienceDirect 机构访问

ScienceDirect 机构访问不是 MCP 自动连接。打开官方 ScienceDirect 网页前先征得用户同意，然后由用户亲自在浏览器中选择机构并完成登录。

严格遵守以下边界：

- 不询问、不读取、不保存密码或验证码；
- 不读取、导出或传递 Cookie 和会话令牌；
- 不代替用户点击机构身份提供方的授权确认；
- 不绕过付费墙、机构权限、下载限制或网站条款。

登录后只根据页面上可见的机构名称、“通过机构访问”提示或目标文献的可见访问状态进行确认。如果无权访问，明确说明“当前会话没有显示有效权限”，可以建议查找合法的开放获取版本，但不得绕过访问限制。

## 完成标准

每处理一项就重新运行一次只读体检：

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex onboard --json
```

只对当前路线达到以下标准即可结束：

- 基础建模：`readiness.base_modeling` 为 `true`；
- Codex 智能建模：`readiness.codex_smart_modeling` 为 `true`；
- 科研复现全套：`readiness.research_local_tools` 为 `true`，并由用户根据页面可见信息确认 ScienceDirect 机构访问；
- 单项修复：只要被指定项目重新检查通过。

结束时简短报告“已就绪、未选择因此未处理、下一步”。不要把可选工具未就绪说成整个项目失败。
