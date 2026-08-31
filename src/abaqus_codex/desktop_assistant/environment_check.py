# -*- coding: utf-8 -*-
"""把首次体检结果转换成适合桌面助手展示的有限状态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from abaqus_codex.desktop_assistant.codex_status import CodexStatus


@dataclass(frozen=True)
class EnvironmentCheckItem:
    """一个不包含路径或凭据的环境检查结果。"""

    group: str
    name: str
    status: str
    tone: str
    detail: str
    next_step: str
    codex_prompt: str = ""
    action_kind: str = "none"


def _mapping(value: object) -> Mapping[str, object]:
    """把不可信的嵌套值安全收窄为只读映射。"""

    return value if isinstance(value, Mapping) else {}


def build_environment_items(
    result: Mapping[str, object],
    codex_status: Optional[CodexStatus],
) -> list[EnvironmentCheckItem]:
    """生成固定顺序的状态列表，不暴露可执行文件和用户目录。"""

    project_python = _mapping(result.get("project_python"))
    environment = _mapping(result.get("environment"))
    abaqus = _mapping(environment.get("abaqus"))
    abqpy = _mapping(environment.get("abqpy"))
    mcp = _mapping(environment.get("mcp"))
    git = _mapping(result.get("git"))
    github = _mapping(result.get("github"))
    zotero = _mapping(result.get("zotero"))
    version_plan = _mapping(result.get("version_plan"))

    project_python_ready = bool(project_python.get("usable"))
    abaqus_installed = bool(abaqus.get("installed"))
    abaqus_ready = bool(abaqus.get("usable"))
    abqpy_ready = bool(abqpy.get("usable"))
    mcp_configured = bool(mcp.get("usable"))
    mcp_heartbeat_ready = bool(mcp.get("responsive"))
    mcp_probe_ready = bool(mcp.get("read_only_probe_passed"))
    mcp_action = str(version_plan.get("mcp_action") or "")
    mcp_blocked = mcp_action in (
        "blocked_incompatible",
        "blocked_unsupported",
    )
    mcp_waiting_for_base = mcp_action == "wait_for_base"
    mcp_ready = bool(
        not mcp_blocked
        and not mcp_waiting_for_base
        and mcp_configured
        and mcp_heartbeat_ready
        and mcp_probe_ready
    )
    git_ready = bool(git.get("usable"))
    github_ready = bool(github.get("logged_in"))
    zotero_ready = bool(zotero.get("read_ready"))

    abaqus_version = str(abaqus.get("version") or "未知")
    abaqus_python = str(abaqus.get("python_version") or "未知")
    abaqus_command = str(abaqus.get("command") or "未检测到")
    abaqus_release_ready = bool(
        abaqus_installed and abaqus_version != "未知"
    )
    abaqus_python_ready = bool(
        abaqus_ready and abaqus_python != "未知"
    )
    project_python_version = str(project_python.get("version") or "未知")
    abqpy_version = str(abqpy.get("version") or "未安装")
    abqpy_installed = bool(abqpy.get("installed"))
    abqpy_requirement = str(
        version_plan.get("recommended_abqpy_requirement")
        or abqpy.get("recommended_requirement")
        or ""
    ).strip()
    abqpy_action = str(version_plan.get("abqpy_action") or "")
    verification_level = str(version_plan.get("verification_level") or "")
    git_version = str(git.get("version") or "未知")
    release_year = version_plan.get("release_year")
    if isinstance(release_year, bool) or not isinstance(release_year, int):
        release_year = None

    if abqpy_ready:
        abqpy_status = "已就绪"
        abqpy_tone = "success"
        abqpy_next_step = "无需处理；Abaqus 与 abqpy 的年份已经匹配。"
        abqpy_codex_prompt = ""
    elif abqpy_action == "unsupported":
        abqpy_status = "版本不支持"
        abqpy_tone = "error"
        abqpy_next_step = (
            "当前版本已知不兼容，禁止自动安装 abqpy、MCP 或提交求解；"
            "等待项目完成适配和真机验证。"
        )
        abqpy_codex_prompt = ""
    elif abqpy_requirement and abaqus_ready:
        abqpy_status = (
            "版本不匹配" if abqpy_installed else "需安装 {0}".format(abqpy_requirement)
        )
        abqpy_tone = "warning"
        abqpy_next_step = (
            "先确认上面的 Abaqus {0} 正是本次要使用的版本。"
            "确认后点击下方按钮，把严格同年份安装请求复制给 Codex。"
            "安装完成后回到本窗口点击‘重新检查’，无需重启中文助手。"
        ).format(abaqus_version, abqpy_requirement)
        abqpy_codex_prompt = (
            "我确认本次使用 Abaqus {0}。请先只读复核检测结果，"
            "只安装严格匹配的 {1}；联网安装前向我展示变更并等待确认。"
            "安装后重新检查版本，不得回退或改装其他年份。"
        ).format(abaqus_version, abqpy_requirement)
        if verification_level == "detected_unverified":
            abqpy_next_step += (
                "该 Abaqus 年份尚未完成维护者真机验证；安装后先运行教学小模型，"
                "通过建模、求解和结果读取测试后再用于正式模型。"
            )
            abqpy_codex_prompt += (
                "该年份尚未完成维护者真机验证；安装完成后先运行教学小模型，"
                "验证建模、求解和结果读取。"
            )
    elif not abaqus_ready:
        abqpy_status = "等待 Abaqus"
        abqpy_tone = "warning"
        abqpy_next_step = "先让 Abaqus 及其内置 Python 通过检查，再决定 abqpy 年份。"
        abqpy_codex_prompt = ""
    else:
        abqpy_status = "需人工确认"
        abqpy_tone = "warning"
        abqpy_next_step = (
            "当前无法生成安全的同年份规格；请先确认 Abaqus 版本和启动命令。"
        )
        abqpy_codex_prompt = ""

    abqpy_requirement_text = abqpy_requirement or "尚未生成"

    codex_ready = bool(codex_status and codex_status.authenticated)
    codex_label = codex_status.label if codex_status else "Codex 尚未检查"
    codex_guidance = (
        codex_status.guidance
        if codex_status
        else "请重新检查；程序不会读取密码或令牌。"
    )

    if mcp_ready:
        mcp_status = "只读能力已验证"
        mcp_tone = "success"
        mcp_next_step = "无需处理。"
        mcp_codex_prompt = ""
    elif mcp_blocked:
        mcp_status = "当前版本已阻断"
        mcp_tone = "error"
        mcp_next_step = (
            "当前 Abaqus 年份不在可执行范围内；不要安装、注册或启动 MCP。"
        )
        mcp_codex_prompt = ""
    elif mcp_waiting_for_base:
        mcp_status = "等待基础环境"
        mcp_tone = "warning"
        mcp_next_step = "先完成 Abaqus 与严格同年份 abqpy，再检查 MCP。"
        mcp_codex_prompt = ""
    else:
        if mcp_configured and mcp_heartbeat_ready:
            mcp_status = "心跳正常，待能力验证"
        elif mcp_configured:
            mcp_status = "已配置，未连接"
        else:
            mcp_status = "未配置"
        mcp_tone = "warning"
        mcp_next_step = "把 MCP 检查请求复制给 Codex。"
        mcp_codex_prompt = (
            "我选择 Codex 智能建模。请先只读确认 Abaqus 与同年份 "
            "abqpy 已就绪，再检查 Abaqus MCP 的安装、注册、插件心跳"
            "和只读能力。任何下载、注册或修复前先展示计划并等待我确认；"
            "不得把‘已注册’或‘有心跳’误报为‘只读能力已连接’。"
            "若本次新建或修改了 Codex MCP 注册，只提示我重启 Codex 一次；"
            "之后启动 Abaqus 插件并执行 ping 与只读查询，不要反复要求重启助手。"
        )

    return [
        EnvironmentCheckItem(
            "必需环境",
            "项目 Python",
            "已就绪" if project_python_ready else "未就绪",
            "success" if project_python_ready else "error",
            "运行助手的 Python 版本：{0}。".format(project_python_version),
            "无需处理。" if project_python_ready else "请重新创建项目虚拟环境。",
        ),
        EnvironmentCheckItem(
            "必需环境",
            "Abaqus",
            (
                "已就绪"
                if abaqus_release_ready
                else ("已找到，需检查" if abaqus_installed else "未检测到")
            ),
            "success" if abaqus_release_ready else "error",
            "检测版本：Abaqus {0}。本次检测命令：{1}。{2}".format(
                abaqus_version,
                abaqus_command,
                str(abaqus.get("message") or ""),
            ),
            (
                "无需处理。"
                if abaqus_release_ready
                else (
                    "已经找到启动命令，不要直接重装；请先根据上面的失败原因检查启动环境。"
                    if abaqus_installed
                    else "请从 Dassault Systèmes 官方渠道安装并配置合法许可证。"
                )
            ),
        ),
        EnvironmentCheckItem(
            "必需环境",
            "Abaqus Python",
            "已就绪" if abaqus_python_ready else "未就绪",
            "success" if abaqus_python_ready else "error",
            "Abaqus 内置 Python：{0}。它与项目 Python 是两个环境。".format(
                abaqus_python
            ),
            "无需处理。" if abaqus_python_ready else "先修复 Abaqus 内置 Python 查询或启动环境，不要改装其他年份。",
        ),
        EnvironmentCheckItem(
            "必需环境",
            "abqpy",
            abqpy_status,
            abqpy_tone,
            "Abaqus 年份：{0}；当前 abqpy：{1}；严格匹配要求：{2}。{3}".format(
                abaqus_version,
                abqpy_version,
                abqpy_requirement_text,
                str(abqpy.get("message") or ""),
            ),
            abqpy_next_step,
            abqpy_codex_prompt,
            "copy_codex" if abqpy_codex_prompt else "none",
        ),
        EnvironmentCheckItem(
            "Codex 联动",
            "Codex 登录",
            "已就绪" if codex_ready else "待处理",
            "success" if codex_ready else "warning",
            codex_label + "。" + codex_guidance,
            "无需处理。" if codex_ready else "使用自己的 ChatGPT 账号完成官方 Codex 登录。",
            action_kind=(
                "codex_login"
                if codex_status
                and codex_status.installed
                and not codex_ready
                else "none"
            ),
        ),
        EnvironmentCheckItem(
            "Codex 联动",
            "Abaqus MCP",
            mcp_status,
            mcp_tone,
            "{0} {1}".format(
                str(mcp.get("message") or "尚未得到 MCP 状态。"),
                str(
                    mcp.get("read_only_probe_message")
                    or (
                        "尚未进行只读工具能力探测。"
                        if mcp_heartbeat_ready
                        else ""
                    )
                ),
            ).strip(),
            mcp_next_step,
            mcp_codex_prompt,
            "copy_codex" if mcp_codex_prompt else "none",
        ),
        _build_first_model_item(
            release_year=release_year,
            abaqus_version=abaqus_version,
            abqpy_requirement=abqpy_requirement,
            base_ready=bool(
                project_python_ready
                and abaqus_release_ready
                and abaqus_python_ready
                and abqpy_ready
            ),
            codex_ready=codex_ready,
            mcp_ready=mcp_ready,
        ),
        EnvironmentCheckItem(
            "代码工具",
            "Git",
            "已就绪" if git_ready else "可选缺项",
            "success" if git_ready else "optional",
            "Git 版本：{0}。{1}".format(
                git_version, str(git.get("message") or "")
            ),
            "无需处理。" if git_ready else "需要下载或更新项目时再安装 Git。",
        ),
        EnvironmentCheckItem(
            "代码工具",
            "GitHub 登录",
            "已登录" if github_ready else "尚未登录",
            "success" if github_ready else "optional",
            str(github.get("message") or "尚未得到 GitHub CLI 状态。"),
            "无需处理。" if github_ready else "科研或贡献代码时，再通过 GitHub 官方网页登录。",
        ),
        EnvironmentCheckItem(
            "科研可选",
            "Zotero",
            "已连接" if zotero_ready else "尚未连接",
            "success" if zotero_ready else "optional",
            str(zotero.get("message") or "尚未得到 Zotero 状态。"),
            "无需处理。" if zotero_ready else "论文复现需要文献库时再连接 Zotero。",
        ),
        EnvironmentCheckItem(
            "科研可选",
            "ScienceDirect",
            "需人工确认",
            "optional",
            "机构访问只能由用户在官方网页确认，程序不会读取浏览器会话。",
            "需要下载论文时，由用户本人完成机构登录。",
        ),
    ]


def format_environment_detail(item: EnvironmentCheckItem) -> str:
    """给初学者展示当前项的含义和唯一下一步。"""

    return (
        "{0}｜{1}\n\n"
        "检查结果：{2}\n\n"
        "下一步：{3}\n\n"
        "本窗口只做检查，不会安装软件、登录账号或修改 Abaqus 模型。"
        "本机路径只在这里显示，不会复制给 Codex。"
    ).format(item.name, item.status, item.detail, item.next_step)


def summarize_environment(items: Sequence[EnvironmentCheckItem]) -> str:
    """生成不把可选缺项误报为整体失败的顶部摘要。"""

    required = [item for item in items if item.group == "必需环境"]
    blockers = [item.name for item in required if item.tone == "error"]
    warnings = [item.name for item in required if item.tone == "warning"]
    if blockers:
        return "基础建模尚未就绪：请先处理 {0}。".format("、".join(blockers))
    if warnings:
        return "Abaqus 已找到；建议先处理 {0}，再开始第一个模型。".format(
            "、".join(warnings)
        )
    return "基础建模环境已就绪；Codex、GitHub 和科研工具按使用场景选配。"


def recommended_environment_index(
    items: Sequence[EnvironmentCheckItem],
) -> int:
    """优先选中当前主路径上的第一个未完成项目。"""

    priorities = (
        ("必需环境", "error"),
        ("必需环境", "warning"),
        ("Codex 联动", "error"),
        ("Codex 联动", "warning"),
        ("开始建模", "error"),
        ("开始建模", "warning"),
        ("开始建模", "success"),
    )
    for group, tone in priorities:
        for index, item in enumerate(items):
            if item.group == group and item.tone == tone:
                return index
    return 0


def format_environment_progress(
    items: Sequence[EnvironmentCheckItem],
) -> str:
    """用五个短步骤显示从安装到首次建模的当前位置。"""

    by_name = {item.name: item for item in items}

    def ready(*names: str) -> bool:
        return all(
            name in by_name and by_name[name].tone == "success"
            for name in names
        )

    first_model = by_name.get("第一个模型")
    if first_model is None:
        first_model_state = "待处理"
    elif first_model.tone == "success":
        first_model_state = "可开始"
    elif first_model.tone == "optional":
        first_model_state = "未到此步"
    else:
        first_model_state = "待处理"

    stages = [
        ("应用", ready("项目 Python")),
        ("Abaqus", ready("Abaqus", "Abaqus Python")),
        ("同年份 abqpy", ready("abqpy")),
        ("Codex/MCP", ready("Codex 登录", "Abaqus MCP")),
    ]
    labels = [
        "{0} {1}·{2}".format(
            index,
            name,
            "完成" if is_ready else "待处理",
        )
        for index, (name, is_ready) in enumerate(stages, start=1)
    ]
    return "配置路线：{0} → 5 第一个模型·{1}".format(
        " → ".join(labels),
        first_model_state,
    )


def environment_action_label(item: EnvironmentCheckItem) -> str:
    """让主按钮直接说明复制的处理请求类型。"""

    if item.action_kind == "codex_login":
        return "打开官方 Codex 登录"
    if item.action_kind == "start_model":
        return "返回建模并开始第 1/10 步"
    if item.action_kind != "copy_codex" or not item.codex_prompt:
        return "请按上方说明处理"
    if item.name == "abqpy":
        return "复制同年份 abqpy 请求"
    if item.name == "Abaqus MCP":
        return "复制 MCP 检查请求"
    return "复制下一步给 Codex"


def _build_first_model_item(
    *,
    release_year: Optional[int],
    abaqus_version: str,
    abqpy_requirement: str,
    base_ready: bool,
    codex_ready: bool,
    mcp_ready: bool,
) -> EnvironmentCheckItem:
    """根据真实支持边界生成版本感知的首次模型终点。"""

    prerequisites_ready = base_ready and codex_ready and mcp_ready
    if release_year == 2021 and prerequisites_ready:
        return EnvironmentCheckItem(
            "开始建模",
            "第一个模型",
            "可以开始",
            "success",
            "Abaqus 2021 主路径和 MCP 只读能力均已验证。",
            "返回主窗口，从第 1/10 步创建二维矩形板；每次应用修改前仍会再次确认。",
            action_kind="start_model",
        )

    if release_year in (2022, 2023, 2024, 2025) and prerequisites_ready:
        prompt = (
            "我已完成 Abaqus {0}、{1}、Codex 登录和 MCP 只读能力验证。"
            "请为这个严格同年份环境制定一个最小教学模型冒烟测试，验证建模、"
            "求解和结果读取；任何模型写入前先展示计划并等待我确认。"
            "不得调用只在 Abaqus 2021 上完成真机验证的桌面写动作插件。"
        ).format(abaqus_version, abqpy_requirement or "同年份 abqpy")
        return EnvironmentCheckItem(
            "开始建模",
            "第一个模型",
            "需候选版验证",
            "warning",
            "该年份可以进入候选测试，但尚未完成维护者真机验收。",
            "先把下方冒烟测试请求复制给 Codex；验证通过前不要用于正式模型。",
            prompt,
            "copy_codex",
        )

    if release_year == 2026:
        return EnvironmentCheckItem(
            "开始建模",
            "第一个模型",
            "版本暂不支持",
            "error",
            "Abaqus 2026 目前属于已知不兼容版本。",
            "等待项目完成适配和真机验证；不要生成安装、MCP 或求解请求。",
        )

    return EnvironmentCheckItem(
        "开始建模",
        "第一个模型",
        "等待配置",
        "optional",
        "首次模型入口将在前面的必需环境和 Codex/MCP 完成后开放。",
        "先处理列表自动选中的未完成项目。",
    )


__all__ = [
    "EnvironmentCheckItem",
    "build_environment_items",
    "format_environment_detail",
    "format_environment_progress",
    "environment_action_label",
    "recommended_environment_index",
    "summarize_environment",
]
