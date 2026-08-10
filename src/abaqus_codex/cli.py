# -*- coding: utf-8 -*-
"""Abaqus Codex Assistant 的统一命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from abaqus_codex.configuration import ConfigurationError
from abaqus_codex.doctor import main as doctor_main
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
        description="面向初学者的 Abaqus 环境体检与二维板拉伸工具。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="检查 Abaqus、abqpy 和 Abaqus MCP。")

    mcp_parser = subparsers.add_parser(
        "mcp-setup", help="安装或注册固定版本的 Abaqus MCP。"
    )
    mcp_parser.add_argument(
        "--yes",
        action="store_true",
        help="确认下载代码并修改用户级 MCP/插件配置。",
    )

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

    run_parser = subparsers.add_parser(
        "run", help="运行二维板拉伸分析并生成中文报告。"
    )
    run_parser.add_argument(
        "--config",
        type=Path,
        default=root / "configs" / "rectangle_tension.json",
        help="二维板 JSON 配置文件。",
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

        if args.command == "mcp-setup":
            from abaqus_codex.mcp_setup import main as mcp_setup_main

            return mcp_setup_main(confirmed=args.yes)

        if args.command == "configure":
            scenario = args.scenario or prompt_scenario()
            profile = save_profile(args.output.resolve(), scenario)
            print("场景配置已保存：{0}".format(args.output.resolve()))
            print("当前场景：{0}".format(profile["scenario_name"]))
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
    except (ConfigurationError, RuntimeError) as error:
        print("执行失败：{0}".format(error), file=sys.stderr)
        return 1

    parser.error("没有识别出命令。")
    return 2
