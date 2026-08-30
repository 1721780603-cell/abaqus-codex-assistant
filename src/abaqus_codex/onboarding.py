# -*- coding: utf-8 -*-
"""为首次启动向导汇总本机建模与科研连接状态。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from abaqus_codex.abqpy_environment import (
    abaqus_verification_level,
    parse_release_year,
    recommended_abqpy_requirement,
)
from abaqus_codex.doctor import inspect_environment


ZOTERO_BASE_URL = "http://127.0.0.1:23119"
SCIENCEDIRECT_URL = "https://www.sciencedirect.com/"


def find_github_cli() -> Optional[Path]:
    """从 PATH 和 Windows 常见安装目录寻找 GitHub CLI。"""

    path_command = shutil.which("gh")
    if path_command:
        return Path(path_command)

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = Path(program_files) / "GitHub CLI" / "gh.exe"
        if candidate.is_file():
            return candidate
    return None


def inspect_github(timeout_seconds: int = 15) -> Dict[str, object]:
    """只检查 GitHub CLI 登录状态，不返回令牌或原始命令输出。"""

    command = find_github_cli()
    if command is None:
        return {
            "installed": False,
            "logged_in": False,
            "command": None,
            "message": "没有找到 GitHub CLI（gh）。",
        }

    try:
        completed = subprocess.run(
            [
                str(command),
                "auth",
                "status",
                "--hostname",
                "github.com",
            ],
            # 输出可能包含账户或认证提示，体检只关心退出码，直接丢弃更安全。
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "logged_in": False,
            "command": str(command),
            "message": "GitHub CLI 登录检查超时。",
        }
    except OSError:
        return {
            "installed": True,
            "logged_in": False,
            "command": str(command),
            "message": "GitHub CLI 已找到，但无法启动登录检查。",
        }

    # 安全边界：不解析、保存或回显 gh 的输出，避免意外泄露令牌信息。
    logged_in = completed.returncode == 0
    message = (
        "GitHub CLI 已登录 github.com。"
        if logged_in
        else "GitHub CLI 已安装，但尚未确认登录 github.com。"
    )
    return {
        "installed": True,
        "logged_in": logged_in,
        "command": str(command),
        "message": message,
    }


def _probe_zotero_endpoint(path: str, timeout_seconds: int) -> bool:
    """只访问固定的 Zotero 回环端点，不使用代理或外部地址。"""

    request = Request(
        url=ZOTERO_BASE_URL + path,
        headers={"Accept": "application/json, text/plain, */*"},
        method="GET",
    )
    try:
        # 禁用系统代理，确保探测流量只发往本机 Zotero。
        with build_opener(ProxyHandler({})).open(
            request, timeout=timeout_seconds
        ) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def inspect_zotero(timeout_seconds: int = 2) -> Dict[str, object]:
    """检查 Zotero 本地 API 和 Connector，不读取任何文献内容。"""

    api_running = _probe_zotero_endpoint("/api/", timeout_seconds)
    connector_running = _probe_zotero_endpoint(
        "/connector/ping", timeout_seconds
    )
    if api_running and connector_running:
        message = "Zotero 本地 API 和 Connector 均可连接。"
    elif api_running:
        message = "Zotero 本地 API 可连接，但 Connector 尚未响应。"
    elif connector_running:
        message = "Zotero Connector 可连接，但本地 API 尚未响应。"
    else:
        message = "没有连接到 Zotero 本地 API 或 Connector。"

    return {
        "api_running": api_running,
        "connector_running": connector_running,
        "read_ready": api_running,
        # ping 只表示 Connector 端点响应，不代表用户已经批准任何导入。
        "connector_ready": connector_running,
        "usable": api_running and connector_running,
        "base_url": ZOTERO_BASE_URL,
        "message": message,
    }


def inspect_sciencedirect() -> Dict[str, object]:
    """声明 ScienceDirect 必须手动登录，不尝试读取浏览器会话。"""

    return {
        "automatic_check": False,
        "manual_confirmation_required": True,
        "login_status": "not_checked",
        "login_mode": "manual_browser",
        "entry_url": SCIENCEDIRECT_URL,
        "message": (
            "机构访问需要用户本人在官方网页完成；程序不会读取密码、"
            "验证码、Cookie 或会话令牌。"
        ),
    }


def build_version_plan(environment: Dict[str, object]) -> Dict[str, object]:
    """把环境体检转换为按年份执行的 abqpy 和 MCP 下一步计划。"""

    # 使用 get 保持向导能读取较旧的体检结果，而不是因为缺少新字段直接崩溃。
    abaqus = environment.get("abaqus", {})
    abqpy = environment.get("abqpy", {})
    mcp = environment.get("mcp", {})
    abaqus_version = abaqus.get("version")
    release_year = parse_release_year(abaqus_version)
    requirement = abqpy.get("recommended_requirement")
    if not requirement:
        requirement = recommended_abqpy_requirement(abaqus_version)
    verification_level = abqpy.get("abaqus_verification_level")
    if not verification_level:
        verification_level = abaqus_verification_level(abaqus_version)

    if verification_level == "known_incompatible":
        abqpy_action = "unsupported"
    elif verification_level == "detected_unsupported":
        abqpy_action = "manual_review"
    elif not abaqus.get("usable"):
        abqpy_action = "wait_for_abaqus"
    elif requirement is None:
        abqpy_action = "manual_review"
    elif abqpy.get("usable"):
        abqpy_action = "ready"
    elif not abqpy.get("installed"):
        abqpy_action = "install_matching"
    else:
        abqpy_action = "replace_mismatched"

    base_ready = bool(abaqus.get("usable") and abqpy.get("usable"))
    if verification_level == "known_incompatible":
        mcp_action = "blocked_incompatible"
    elif verification_level == "detected_unsupported":
        mcp_action = "blocked_unsupported"
    elif not base_ready:
        mcp_action = "wait_for_base"
    elif mcp.get("responsive"):
        mcp_action = "ready"
    elif not mcp.get("files_installed"):
        mcp_action = "install"
    elif not mcp.get("usable"):
        mcp_action = "setup_or_repair"
    else:
        # 注册和导入成功并不等于 Abaqus 插件已经响应，仍需启动后做心跳探测。
        mcp_action = "start_and_probe"

    return {
        "detected_abaqus_version": abaqus_version,
        "detected_abaqus_python": abaqus.get("python_version"),
        "selected_abaqus_command": abaqus.get("command"),
        "release_year": release_year,
        "verification_level": verification_level,
        "recommended_abqpy_requirement": requirement,
        "abqpy_action": abqpy_action,
        "mcp_action": mcp_action,
        "mcp_requires_heartbeat_probe": verification_level
        in ("maintainer_verified", "detected_unverified")
        and not bool(mcp.get("responsive")),
        "model_execution_allowed": verification_level
        in ("maintainer_verified", "detected_unverified"),
        "model_smoke_test_required": verification_level
        == "detected_unverified",
    }


def inspect_onboarding() -> Dict[str, object]:
    """汇总一次首次启动体检，供 CLI 和 Codex Skill 使用。"""

    environment = inspect_environment()
    github = inspect_github()
    zotero = inspect_zotero()
    science_direct = inspect_sciencedirect()
    project_python = {
        "usable": True,
        "version": platform.python_version(),
        "executable": sys.executable,
        "message": "项目 Python 可以运行当前体检。",
    }

    return {
        "schema_version": 1,
        "project_python": project_python,
        "environment": environment,
        "version_plan": build_version_plan(environment),
        "github": github,
        "zotero": zotero,
        "science_direct": science_direct,
        "readiness": {
            "base_modeling": bool(environment["core_usable"]),
            "codex_smart_modeling": bool(environment["ai_usable"]),
            # ScienceDirect 登录只能由用户在浏览器中确认，因此不伪造全自动就绪。
            "research_local_tools": bool(
                github["logged_in"] and zotero["read_ready"]
            ),
            "science_direct_requires_user": True,
        },
    }


def _state(value: bool) -> str:
    """把布尔状态转换为适合初学者阅读的中文。"""

    return "可用" if value else "未就绪"


def print_onboarding_report(result: Dict[str, object]) -> None:
    """输出分层状态和四个下一步选项，不自动修改任何配置。"""

    environment = result["environment"]
    project_python = result["project_python"]
    github = result["github"]
    zotero = result["zotero"]
    science_direct = result["science_direct"]
    readiness = result["readiness"]
    version_plan = result.get("version_plan") or build_version_plan(environment)

    print("Abaqus Codex Assistant 首次启动向导")
    print("====================================")
    print("1. 基础建模")
    print("   项目 Python：{0}".format(project_python["message"]))
    print("   Abaqus：{0}".format(environment["abaqus"]["message"]))
    if version_plan["detected_abaqus_version"]:
        print(
            "   检测版本：Abaqus {0}".format(
                version_plan["detected_abaqus_version"]
            )
        )
    if version_plan["detected_abaqus_python"]:
        print(
            "   内置 Python：{0}".format(
                version_plan["detected_abaqus_python"]
            )
        )
    if version_plan["recommended_abqpy_requirement"]:
        print(
            "   推荐 abqpy：{0}".format(
                version_plan["recommended_abqpy_requirement"]
            )
        )
    if version_plan["verification_level"] == "maintainer_verified":
        print("   支持状态：该年份已完成维护者真机求解验证。")
    elif version_plan["verification_level"] == "known_incompatible":
        print("   支持状态：该年份已知不兼容，自动安装和运行已停止。")
    elif version_plan["verification_level"] == "detected_unsupported":
        print("   支持状态：已识别年份，但尚未列入自动流程，需要人工评估。")
    elif version_plan["verification_level"] == "detected_unverified":
        print("   支持状态：可自动检测，但尚未完成维护者真机求解验证。")
    else:
        print("   支持状态：无法按年份自动判断，需要人工检查。")
    print("   Abaqus Python / abqpy：{0}".format(environment["abqpy"]["message"]))
    print("   结果：{0}".format(_state(readiness["base_modeling"])))
    print("2. Codex 智能建模")
    print("   Abaqus MCP：{0}".format(environment["mcp"]["message"]))
    print("   结果：{0}".format(_state(readiness["codex_smart_modeling"])))
    print("3. GitHub 与 Zotero")
    print("   GitHub：{0}".format(github["message"]))
    print("   Zotero：{0}".format(zotero["message"]))
    print("4. ScienceDirect 机构访问")
    print("   {0}".format(science_direct["message"]))
    print()
    print("请选择下一步（本命令不会自动安装或登录）：")
    print("[1] 基础建模：只补齐 Abaqus、Python 和 abqpy")
    print("[2] Codex 智能建模：在基础环境上再连接 Abaqus MCP")
    print("[3] 科研复现全套：再检查 GitHub、Zotero 和机构访问")
    print("[4] 我已有明确问题（单项修复）：只处理你指定的一项")
