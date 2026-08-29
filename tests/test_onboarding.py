# -*- coding: utf-8 -*-
"""测试首次启动向导的只读检测、安全边界和初学者输出。"""

from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.request import ProxyHandler

from abaqus_codex.cli import main
from abaqus_codex.onboarding import (
    ZOTERO_BASE_URL,
    _probe_zotero_endpoint,
    inspect_github,
    inspect_onboarding,
    inspect_sciencedirect,
    inspect_zotero,
    print_onboarding_report,
)


def sample_onboarding_result():
    """返回 CLI 和文本报告测试共用的最小完整结果。"""

    return {
        "schema_version": 1,
        "project_python": {
            "usable": True,
            "version": "3.13.0",
            "executable": "python",
            "message": "项目 Python 可以运行当前体检。",
        },
        "environment": {
            "core_usable": True,
            "ai_configured": True,
            "ai_usable": False,
            "abaqus": {"message": "已检测到 Abaqus。"},
            "abqpy": {"message": "abqpy 版本匹配。"},
            "mcp": {"message": "MCP 已配置，但桥接尚未响应。"},
        },
        "github": {
            "installed": True,
            "logged_in": True,
            "command": "gh",
            "message": "GitHub CLI 已登录 github.com。",
        },
        "zotero": {
            "api_running": True,
            "connector_running": True,
            "read_ready": True,
            "connector_ready": True,
            "usable": True,
            "base_url": ZOTERO_BASE_URL,
            "message": "Zotero 本地 API 和 Connector 均可连接。",
        },
        "science_direct": {
            "automatic_check": False,
            "manual_confirmation_required": True,
            "login_mode": "manual_browser",
            "login_status": "not_checked",
            "entry_url": "https://www.sciencedirect.com/",
            "message": "机构访问需要用户本人在官方网页完成。",
        },
        "readiness": {
            "base_modeling": True,
            "codex_smart_modeling": False,
            "research_local_tools": True,
            "science_direct_requires_user": True,
        },
    }


class _SuccessfulResponse:
    """模拟一个支持 with 语句的本地 HTTP 成功响应。"""

    status = 200

    def __enter__(self):
        """进入模拟响应上下文。"""

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """离开模拟响应上下文，不屏蔽异常。"""

        return False


class GitHubInspectionTests(unittest.TestCase):
    """确认 GitHub 登录检测不会启动 shell 或泄露命令输出。"""

    @patch("abaqus_codex.onboarding.subprocess.run")
    @patch("abaqus_codex.onboarding.find_github_cli", return_value=None)
    def test_missing_github_cli_does_not_run_command(
        self, find_mock, run_mock
    ):
        """未找到 gh 时应直接返回，而不是尝试执行其他命令。"""

        result = inspect_github()

        self.assertFalse(result["installed"])
        self.assertFalse(result["logged_in"])
        find_mock.assert_called_once_with()
        run_mock.assert_not_called()

    @patch("abaqus_codex.onboarding.subprocess.run")
    @patch(
        "abaqus_codex.onboarding.find_github_cli",
        return_value=Path(r"C:\Program Files\GitHub CLI\gh.exe"),
    )
    def test_success_uses_fixed_arguments_and_discards_output(
        self, find_mock, run_mock
    ):
        """登录检查只能调用固定 argv，并把标准输出和错误输出丢弃。"""

        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"gho_SECRET_MUST_NOT_APPEAR"
        )

        result = inspect_github(timeout_seconds=9)

        self.assertTrue(result["logged_in"])
        self.assertNotIn("gho_SECRET", json.dumps(result, ensure_ascii=False))
        command = run_mock.call_args.args[0]
        self.assertEqual(
            command[1:],
            ["auth", "status", "--hostname", "github.com"],
        )
        self.assertEqual(run_mock.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run_mock.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(run_mock.call_args.kwargs["timeout"], 9)
        self.assertFalse(run_mock.call_args.kwargs["check"])
        find_mock.assert_called_once_with()

    @patch("abaqus_codex.onboarding.subprocess.run")
    @patch(
        "abaqus_codex.onboarding.find_github_cli",
        return_value=Path("gh"),
    )
    def test_nonzero_status_is_reported_as_not_logged_in(
        self, _find_mock, run_mock
    ):
        """gh 返回非零值时应保守地判断为尚未确认登录。"""

        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=1)

        result = inspect_github()

        self.assertTrue(result["installed"])
        self.assertFalse(result["logged_in"])
        self.assertIn("尚未确认登录", result["message"])

    @patch("abaqus_codex.onboarding.subprocess.run")
    @patch(
        "abaqus_codex.onboarding.find_github_cli",
        return_value=Path("gh"),
    )
    def test_timeout_is_a_normal_diagnostic_result(
        self, _find_mock, run_mock
    ):
        """登录检查超时应返回可读状态，而不是把异常抛给初学者。"""

        run_mock.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=15)

        result = inspect_github()

        self.assertFalse(result["logged_in"])
        self.assertIn("超时", result["message"])

    @patch("abaqus_codex.onboarding.subprocess.run", side_effect=OSError)
    @patch(
        "abaqus_codex.onboarding.find_github_cli",
        return_value=Path("gh"),
    )
    def test_launch_error_is_a_normal_diagnostic_result(
        self, _find_mock, _run_mock
    ):
        """gh 文件无法启动时应保留已安装状态并给出中文说明。"""

        result = inspect_github()

        self.assertTrue(result["installed"])
        self.assertFalse(result["logged_in"])
        self.assertIn("无法启动", result["message"])


class ZoteroInspectionTests(unittest.TestCase):
    """确认 Zotero 检测仅访问固定的本机端点。"""

    @patch("abaqus_codex.onboarding._probe_zotero_endpoint")
    def test_both_zotero_endpoints_are_checked(self, probe_mock):
        """本地 API 与 Connector 都响应时应报告完整连接。"""

        probe_mock.side_effect = [True, True]

        result = inspect_zotero(timeout_seconds=4)

        self.assertTrue(result["read_ready"])
        self.assertTrue(result["connector_ready"])
        self.assertTrue(result["usable"])
        self.assertEqual(
            probe_mock.call_args_list,
            [
                unittest.mock.call("/api/", 4),
                unittest.mock.call("/connector/ping", 4),
            ],
        )

    @patch("abaqus_codex.onboarding._probe_zotero_endpoint")
    def test_api_only_remains_useful_for_reading(self, probe_mock):
        """只有本地 API 时仍可读取，但不能声称 Connector 已就绪。"""

        probe_mock.side_effect = [True, False]

        result = inspect_zotero()

        self.assertTrue(result["read_ready"])
        self.assertFalse(result["connector_ready"])
        self.assertFalse(result["usable"])
        self.assertIn("Connector 尚未响应", result["message"])

    @patch("abaqus_codex.onboarding._probe_zotero_endpoint")
    def test_offline_zotero_is_a_normal_result(self, probe_mock):
        """Zotero 未启动时应返回未就绪，而不是连接外部替代地址。"""

        probe_mock.side_effect = [False, False]

        result = inspect_zotero()

        self.assertFalse(result["read_ready"])
        self.assertFalse(result["connector_ready"])
        self.assertFalse(result["usable"])
        self.assertEqual(result["base_url"], "http://127.0.0.1:23119")

    @patch("abaqus_codex.onboarding.build_opener")
    def test_probe_uses_loopback_and_disables_system_proxy(self, opener_mock):
        """端点探测必须固定在 127.0.0.1，并显式禁用系统代理。"""

        opener = Mock()
        opener.open.return_value = _SuccessfulResponse()
        opener_mock.return_value = opener

        self.assertTrue(_probe_zotero_endpoint("/api/", 3))

        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:23119/api/")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 3)
        proxy_handler = opener_mock.call_args.args[0]
        self.assertIsInstance(proxy_handler, ProxyHandler)
        self.assertEqual(proxy_handler.proxies, {})

    @patch("abaqus_codex.onboarding.build_opener")
    def test_local_connection_error_is_converted_to_false(self, opener_mock):
        """本机端口拒绝连接时应返回 False，确保离线测试稳定。"""

        opener = Mock()
        opener.open.side_effect = URLError("connection refused")
        opener_mock.return_value = opener

        self.assertFalse(_probe_zotero_endpoint("/connector/ping", 1))


class ScienceDirectInspectionTests(unittest.TestCase):
    """确认机构访问始终由用户本人在官方网页完成。"""

    @patch("abaqus_codex.onboarding.build_opener")
    @patch("abaqus_codex.onboarding.subprocess.run")
    def test_sciencedirect_is_manual_only_and_does_not_probe_sessions(
        self, run_mock, opener_mock
    ):
        """检查函数不能访问网络、读取浏览器会话或声称已经登录。"""

        result = inspect_sciencedirect()

        self.assertFalse(result["automatic_check"])
        self.assertTrue(result["manual_confirmation_required"])
        self.assertEqual(result["login_mode"], "manual_browser")
        self.assertEqual(result["login_status"], "not_checked")
        self.assertEqual(result["entry_url"], "https://www.sciencedirect.com/")
        self.assertTrue(
            set(result).isdisjoint({"password", "cookie", "token", "session"})
        )
        run_mock.assert_not_called()
        opener_mock.assert_not_called()


class OnboardingAggregateTests(unittest.TestCase):
    """确认聚合状态不会把人工登录误报为全自动就绪。"""

    @patch("abaqus_codex.onboarding.inspect_sciencedirect")
    @patch("abaqus_codex.onboarding.inspect_zotero")
    @patch("abaqus_codex.onboarding.inspect_github")
    @patch("abaqus_codex.onboarding.inspect_environment")
    def test_readiness_reuses_existing_environment_results(
        self, environment_mock, github_mock, zotero_mock, science_mock
    ):
        """基础、MCP 与科研本地工具应分别计算，不混淆就绪层级。"""

        environment_mock.return_value = {
            "core_usable": True,
            "ai_usable": False,
        }
        github_mock.return_value = {"logged_in": True}
        zotero_mock.return_value = {"read_ready": True}
        science_mock.return_value = {
            "automatic_check": False,
            "login_status": "not_checked",
        }

        result = inspect_onboarding()

        self.assertTrue(result["readiness"]["base_modeling"])
        self.assertFalse(result["readiness"]["codex_smart_modeling"])
        self.assertTrue(result["readiness"]["research_local_tools"])
        self.assertTrue(result["readiness"]["science_direct_requires_user"])
        environment_mock.assert_called_once_with()


class OnboardingOutputTests(unittest.TestCase):
    """确认向导为 Skill 和初学者提供稳定、清楚的两种输出。"""

    @patch("abaqus_codex.onboarding.inspect_onboarding")
    def test_cli_json_output_is_machine_readable(self, inspect_mock):
        """--json 应输出完整 JSON，并把缺项视为诊断结果而非命令失败。"""

        inspect_mock.return_value = sample_onboarding_result()
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["onboard", "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertFalse(payload["readiness"]["codex_smart_modeling"])
        inspect_mock.assert_called_once_with()

    def test_text_report_offers_four_non_destructive_choices(self):
        """文本报告应给出四种路线，并明确不会自动安装或登录。"""

        output = io.StringIO()
        with redirect_stdout(output):
            print_onboarding_report(sample_onboarding_result())

        report = output.getvalue()
        for option in ("[1]", "[2]", "[3]", "[4]"):
            with self.subTest(option=option):
                self.assertIn(option, report)
        self.assertIn("本命令不会自动安装或登录", report)
        self.assertIn("MCP 已配置，但桥接尚未响应", report)


if __name__ == "__main__":
    unittest.main()
