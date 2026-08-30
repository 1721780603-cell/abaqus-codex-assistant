# -*- coding: utf-8 -*-
"""Abaqus Codex Assistant 的统一命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from abaqus_codex.configuration import ConfigurationError, load_config
from abaqus_codex.doctor import main as doctor_main
from abaqus_codex.local_ai import LocalAIError, SUPPORTED_PROVIDERS
from abaqus_codex.scenario import SCENARIOS, prompt_scenario, save_profile


def _configure_utf8_output() -> None:
    """让 Windows 命令入口稳定显示中文，而不依赖当前控制台代码页。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def project_root() -> Path:
    """返回源码所在项目根目录。"""

    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    root = project_root()
    parser = argparse.ArgumentParser(
        prog="abaqus-codex",
        description="面向初学者的 Abaqus 环境体检、建模和结果报告工具。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="检查 Abaqus、abqpy 和 Abaqus MCP。")

    assistant_parser = subparsers.add_parser(
        "assistant", help="启动 Abaqus 2021 中文材料计划与安全修改助手。"
    )
    assistant_parser.add_argument(
        "--mock",
        action="store_true",
        help="显式使用模拟模型，不连接或冒充真实 Abaqus。",
    )
    assistant_parser.add_argument(
        "--source",
        choices=("snapshot", "mcp", "mock"),
        default=None,
        help="模型概要来源；默认读取一次性快照，MCP 仅为显式兼容模式。",
    )
    assistant_parser.add_argument(
        "--mcp-home",
        type=Path,
        help="高级选项：指定已有 Abaqus MCP 工作目录。",
    )

    assistant_setup_parser = subparsers.add_parser(
        "assistant-setup",
        help="检查或安装 Abaqus 2021 安全材料动作插件。",
    )
    assistant_setup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只做版本和文件预检，不写入用户插件目录。",
    )
    assistant_setup_parser.add_argument(
        "--yes",
        action="store_true",
        help="确认安装到当前用户的 abaqus_plugins；不同旧版会先备份。",
    )

    install_preflight_parser = subparsers.add_parser(
        "install-preflight",
        help="检测任意 Abaqus，并报告当前安全插件是否适配。",
    )
    install_preflight_parser.add_argument(
        "--json",
        action="store_true",
        help="输出供统一安装器读取的 ASCII JSON。",
    )

    onboard_parser = subparsers.add_parser(
        "onboard", help="首次启动时检查建模、GitHub、Zotero 和科研访问。"
    )
    onboard_parser.add_argument(
        "--json",
        action="store_true",
        help="输出便于 Codex Skill 读取的 JSON，不执行安装或登录。",
    )

    abqpy_parser = subparsers.add_parser(
        "abqpy-setup", help="按检测到的 Abaqus 年份安装匹配的 abqpy。"
    )
    abqpy_parser.add_argument(
        "--yes",
        action="store_true",
        help="确认联网并修改当前项目 Python；不提供时只显示安全提示。",
    )

    mcp_parser = subparsers.add_parser(
        "mcp-setup", help="安装或注册固定版本的 Abaqus MCP。"
    )
    mcp_parser.add_argument(
        "--yes",
        action="store_true",
        help="确认下载代码并修改用户级 MCP/插件配置。",
    )
    mcp_parser.add_argument(
        "--repair",
        action="store_true",
        help="将已有 Abaqus MCP 注册替换为防卡启动器；必须同时使用 --yes。",
    )

    headless_parser = subparsers.add_parser(
        "mcp-headless", help="在隐藏的 Abaqus noGUI 进程中运行 MCP 桥接。"
    )
    headless_subparsers = headless_parser.add_subparsers(
        dest="headless_command", required=True
    )
    headless_start = headless_subparsers.add_parser(
        "start", help="启动无界面后台桥接。"
    )
    headless_start.add_argument(
        "--timeout", type=int, default=60, help="等待插件心跳的秒数。"
    )
    headless_stop = headless_subparsers.add_parser(
        "stop", help="优雅停止无界面后台桥接。"
    )
    headless_stop.add_argument(
        "--timeout", type=int, default=20, help="等待后台进程退出的秒数。"
    )
    headless_subparsers.add_parser("status", help="查看无界面后台桥接状态。")

    configure_parser = subparsers.add_parser(
        "configure", help="选择使用场景并保存本地配置。"
    )
    configure_parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        help="不提供时显示交互式场景菜单。",
    )
    configure_parser.add_argument(
        "--output",
        type=Path,
        default=root / "configs" / "user_profile.json",
        help="场景配置保存位置。",
    )

    local_ai_parser = subparsers.add_parser(
        "local-ai", help="使用本机 Ollama 或 LM Studio 生成受约束的模型配置。"
    )
    local_ai_subparsers = local_ai_parser.add_subparsers(
        dest="local_ai_command", required=True
    )
    local_ai_doctor = local_ai_subparsers.add_parser(
        "doctor", help="检查本机模型服务并列出可用模型。"
    )
    local_ai_doctor.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        help="不提供时依次检查 Ollama 和 LM Studio。",
    )
    local_ai_doctor.add_argument(
        "--base-url",
        help="仅在指定 provider 时使用；只允许本机回环 HTTP 地址。",
    )

    local_ai_generate = local_ai_subparsers.add_parser(
        "generate", help="把中文需求转换为矩形板 JSON 配置。"
    )
    local_ai_generate.add_argument(
        "--provider", choices=SUPPORTED_PROVIDERS, required=True
    )
    local_ai_generate.add_argument("--model", required=True, help="本机模型名称。")
    local_ai_generate.add_argument(
        "--prompt", required=True, help="只描述二维矩形板拉伸参数。"
    )
    local_ai_generate.add_argument(
        "--base-url", help="只允许本机回环 HTTP 地址。"
    )
    local_ai_generate.add_argument(
        "--output",
        type=Path,
        default=root / "configs" / "local_ai_rectangle.json",
        help="确认后保存的 JSON 路径。",
    )
    local_ai_generate.add_argument(
        "--timeout", type=int, default=120, help="本地模型响应超时秒数。"
    )
    local_ai_generate.add_argument(
        "--yes", action="store_true", help="跳过交互确认，只保存经过校验的 JSON。"
    )

    validate_parser = subparsers.add_parser(
        "validate", help="检查模型 JSON，不启动 Abaqus。"
    )
    validate_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="需要检查的模型 JSON 配置文件。",
    )

    run_parser = subparsers.add_parser(
        "run", help="运行内置 Abaqus 示例并生成中文报告。"
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        default=root / "configs" / "rectangle_tension.json",
        help="内置 Abaqus 模型的 JSON 配置文件。",
    )
    run_parser.add_argument(
        "--work-root",
        type=Path,
        default=root / "work" / "runs",
        help="Abaqus 临时作业根目录。",
    )
    run_parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "outputs",
        help="结果和报告输出根目录。",
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Abaqus 整体运行超时秒数，默认 1800 秒。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """解析命令并返回适合脚本调用的退出码。"""

    _configure_utf8_output()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "doctor":
            return doctor_main()

        if args.command == "assistant":
            # 延后导入 Tkinter，普通命令和无图形 CI 不会加载桌面界面。
            from abaqus_codex.desktop_assistant import launch

            source = "mock" if args.mock else (args.source or "snapshot")
            if args.mock and args.source is not None:
                parser.error("--mock 不能与显式 --source 同时使用。")
            if args.mcp_home is not None and source != "mcp":
                parser.error("--mcp-home 只能与 --source mcp 一起使用。")
            return launch(
                mock=(source == "mock"),
                source=source,
                mcp_home=args.mcp_home,
            )

        if args.command == "assistant-setup":
            from abaqus_codex.safe_action_setup import setup_safe_action_plugin

            result = setup_safe_action_plugin(
                confirmed=args.yes,
                dry_run=args.dry_run,
            )
            print(result["message"])
            print("目标目录：{0}".format(result["target"]))
            if result["backup"]:
                print("旧版备份：{0}".format(result["backup"]))
            if not result["dry_run"] and result["changed"]:
                print("请关闭并重新打开 Abaqus/CAE 2021 后再使用助手。")
            return 0

        if args.command == "install-preflight":
            from abaqus_codex.install_preflight import main as preflight_main

            return preflight_main(json_output=args.json)

        if args.command == "onboard":
            from abaqus_codex.onboarding import (
                inspect_onboarding,
                print_onboarding_report,
            )

            # 首次启动体检只读状态；缺项是正常结果，不把它当成命令失败。
            result = inspect_onboarding()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print_onboarding_report(result)
            return 0

        if args.command == "abqpy-setup":
            from abaqus_codex.abqpy_setup import main as abqpy_setup_main

            return abqpy_setup_main(confirmed=args.yes)

        if args.command == "mcp-setup":
            from abaqus_codex.mcp_setup import main as mcp_setup_main

            return mcp_setup_main(confirmed=args.yes, repair=args.repair)

        if args.command == "mcp-headless":
            from abaqus_codex.mcp_headless import (
                inspect_headless_bridge,
                print_headless_status,
                start_headless_bridge,
                stop_headless_bridge,
            )

            if args.headless_command == "start":
                result = start_headless_bridge(timeout_seconds=args.timeout)
            elif args.headless_command == "stop":
                result = stop_headless_bridge(timeout_seconds=args.timeout)
            else:
                result = inspect_headless_bridge()
            print_headless_status(result)
            return 0 if result["running"] or args.headless_command == "stop" else 1

        if args.command == "configure":
            scenario = args.scenario or prompt_scenario()
            profile = save_profile(args.output.resolve(), scenario)
            print("场景配置已保存：{0}".format(args.output.resolve()))
            print("当前场景：{0}".format(profile["scenario_name"]))
            return 0

        if args.command == "local-ai":
            # 延后导入，普通建模流程不会加载或连接本地模型服务。
            from abaqus_codex.local_ai import (
                DEFAULT_BASE_URLS,
                generate_rectangle_config,
                list_models,
                save_generated_config,
            )

            if args.local_ai_command == "doctor":
                if args.base_url and not args.provider:
                    raise LocalAIError("使用 --base-url 时必须同时指定 --provider。")
                providers = (args.provider,) if args.provider else SUPPORTED_PROVIDERS
                available = False
                for provider in providers:
                    try:
                        models = list_models(provider, args.base_url)
                        available = True
                        print("{0}：已连接 {1}".format(provider, args.base_url or DEFAULT_BASE_URLS[provider]))
                        print("  可用模型：{0}".format("、".join(models) or "无"))
                    except LocalAIError as error:
                        print("{0}：不可用（{1}）".format(provider, error))
                return 0 if available else 1

            config, defaulted_fields = generate_rectangle_config(
                provider=args.provider,
                model=args.model,
                prompt=args.prompt,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
            )
            print("本地 AI 生成并通过校验的矩形板配置：")
            print(json.dumps(config, ensure_ascii=False, indent=2))
            if defaulted_fields:
                print(
                    "以下参数未在需求中明确给出，沿用教学默认值：{0}".format(
                        "、".join(defaulted_fields)
                    )
                )
            confirmed = args.yes
            if not confirmed:
                answer = input("确认保存该配置吗？输入 y 保存，其他输入取消：").strip()
                confirmed = answer.lower() in ("y", "yes")
            if not confirmed:
                print("已取消，配置未保存，也没有运行 Abaqus。")
                return 0
            output_path = args.output.resolve()
            save_generated_config(output_path, config)
            print("配置已保存：{0}".format(output_path))
            print("本命令不会自动运行 Abaqus；请先人工检查 JSON。")
            return 0

        if args.command == "validate":
            # 校验命令只读取 JSON，给初学者提供启动 Abaqus 前的检查点。
            config_path = args.config.resolve()
            config = load_config(config_path)
            print("配置检查通过：{0}".format(config_path))
            print(json.dumps(config, ensure_ascii=False, indent=2))
            print("Abaqus 尚未启动；确认参数后再运行 run 命令。")
            return 0

        if args.command == "run":
            # 延后导入，保证仅使用 doctor/configure 时不加载求解流程。
            from abaqus_codex.workflow import run_analysis

            result = run_analysis(
                config_path=args.config.resolve(),
                work_root=args.work_root.resolve(),
                output_root=args.output_root.resolve(),
                timeout_seconds=args.timeout,
            )
            print("分析完成。")
            print("结果文件：{0}".format(result["results_path"]))
            print("中文报告：{0}".format(result["report_path"]))
            print(
                "最大位移模：{0:.8g} {1}".format(
                    result["maximum_displacement"], result["length_unit"]
                )
            )
            print(
                "最大 Mises 应力：{0:.8g} {1}".format(
                    result["maximum_mises_stress"], result["stress_unit"]
                )
            )
            return 0
    except (ConfigurationError, LocalAIError, RuntimeError) as error:
        print("执行失败：{0}".format(error), file=sys.stderr)
        return 1

    parser.error("没有识别出命令。")
    return 2
