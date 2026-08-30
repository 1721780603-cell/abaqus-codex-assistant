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
    abaqus_ready = bool(abaqus.get("usable"))
    abqpy_ready = bool(abqpy.get("usable"))
    mcp_ready = bool(mcp.get("responsive"))
    git_ready = bool(git.get("usable"))
    github_ready = bool(github.get("logged_in"))
    zotero_ready = bool(zotero.get("read_ready"))

    abaqus_version = str(abaqus.get("version") or "未知")
    abaqus_python = str(abaqus.get("python_version") or "未知")
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

    if abqpy_ready:
        abqpy_status = "已就绪"
        abqpy_tone = "success"
        abqpy_next_step = "无需处理；Abaqus 与 abqpy 的年份已经匹配。"
    elif abqpy_action == "unsupported":
        abqpy_status = "版本不支持"
        abqpy_tone = "error"
        abqpy_next_step = (
            "当前版本已知不兼容，禁止自动安装 abqpy、MCP 或提交求解；"
            "等待项目完成适配和真机验证。"
        )
    elif abqpy_requirement and abaqus_ready:
        abqpy_status = (
            "版本不匹配" if abqpy_installed else "需安装 {0}".format(abqpy_requirement)
        )
        abqpy_tone = "warning"
        abqpy_next_step = (
            "先确认上面的 Abaqus {0} 正是本次要使用的版本。"
            "确认后复制给 Codex：我确认当前使用 Abaqus {0}，"
            "请安装严格匹配的 {1}。安装会联网，请先向我确认。"
        ).format(abaqus_version, abqpy_requirement)
        if verification_level == "detected_unverified":
            abqpy_next_step += (
                "该 Abaqus 年份尚未完成维护者真机验证；安装后先运行教学小模型，"
                "通过建模、求解和结果读取测试后再用于正式模型。"
            )
    elif not abaqus_ready:
        abqpy_status = "等待 Abaqus"
        abqpy_tone = "warning"
        abqpy_next_step = "先让 Abaqus 及其内置 Python 通过检查，再决定 abqpy 年份。"
    else:
        abqpy_status = "需人工确认"
        abqpy_tone = "warning"
        abqpy_next_step = (
            "当前无法生成安全的同年份规格；请先确认 Abaqus 版本和启动命令。"
        )

    abqpy_requirement_text = abqpy_requirement or "尚未生成"

    codex_ready = bool(codex_status and codex_status.authenticated)
    codex_label = codex_status.label if codex_status else "Codex 尚未检查"
    codex_guidance = (
        codex_status.guidance
        if codex_status
        else "请重新检查；程序不会读取密码或令牌。"
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
            "已就绪" if abaqus_ready else "未就绪",
            "success" if abaqus_ready else "error",
            "检测版本：Abaqus {0}。{1}".format(
                abaqus_version, str(abaqus.get("message") or "")
            ),
            (
                "无需处理。"
                if abaqus_ready
                else "请从 Dassault Systèmes 官方渠道安装并配置合法许可证。"
            ),
        ),
        EnvironmentCheckItem(
            "必需环境",
            "Abaqus Python",
            "已就绪" if abaqus_ready and abaqus_python != "未知" else "未就绪",
            "success" if abaqus_ready and abaqus_python != "未知" else "error",
            "Abaqus 内置 Python：{0}。它与项目 Python 是两个环境。".format(
                abaqus_python
            ),
            "无需处理。" if abaqus_ready else "先修复 Abaqus 启动环境。",
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
        ),
        EnvironmentCheckItem(
            "Codex 联动",
            "Codex 登录",
            "已就绪" if codex_ready else "待处理",
            "success" if codex_ready else "warning",
            codex_label + "。" + codex_guidance,
            "无需处理。" if codex_ready else "使用自己的 ChatGPT 账号完成官方 Codex 登录。",
        ),
        EnvironmentCheckItem(
            "Codex 联动",
            "Abaqus MCP",
            "已连接" if mcp_ready else "未连接",
            "success" if mcp_ready else "warning",
            str(mcp.get("message") or "尚未得到 MCP 状态。"),
            (
                "无需处理。"
                if mcp_ready
                else "选择 Codex 智能建模后，再询问是否安装、注册或修复 MCP。"
            ),
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


__all__ = [
    "EnvironmentCheckItem",
    "build_environment_items",
    "format_environment_detail",
    "summarize_environment",
]
