# -*- coding: utf-8 -*-
"""测试 Codex 安装和登录检测，不调用真实账号。"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from abaqus_codex.desktop_assistant.codex_status import (
    CodexLoginError,
    inspect_codex_status,
    start_codex_login,
)


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """构造不包含任何真实凭据的模拟命令结果。"""

    return subprocess.CompletedProcess(
        args=["codex", "login", "status"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


class CodexStatusTests(unittest.TestCase):
    """覆盖面向初学者的五种状态。"""

    def test_missing_codex_is_reported(self):
        """找不到程序时提示安装，不能尝试登录。"""

        status = inspect_codex_status(
            finder=lambda _name: None,
            candidate_roots=[],
        )
        self.assertFalse(status.installed)
        self.assertEqual(status.label, "Codex 未安装")

    def test_windows_desktop_bundle_is_discovered_without_path(self):
        """双击启动器时也能发现版本化目录里的 Codex。"""

        with tempfile.TemporaryDirectory() as directory:
            bin_root = Path(directory) / "bin"
            executable = bin_root / "version-id" / "codex.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"test")
            seen = {}

            def runner(command, **_kwargs):
                seen["command"] = command
                return completed("Not logged in", 1)

            status = inspect_codex_status(
                finder=lambda _name: None,
                candidate_roots=[bin_root],
                runner=runner,
            )

        self.assertTrue(status.installed)
        self.assertEqual(seen["command"][0], str(executable))

    def test_not_logged_in_is_reported(self):
        """已安装但未登录时应引导官方 ChatGPT 登录。"""

        status = inspect_codex_status(
            executable="codex",
            runner=lambda *_args, **_kwargs: completed("Not logged in", 1),
        )
        self.assertTrue(status.installed)
        self.assertFalse(status.authenticated)
        self.assertIn("codex login", status.guidance)

    def test_chatgpt_login_uses_subscription_label(self):
        """ChatGPT 登录只确认身份，不擅自判断 Plus 或 Pro。"""

        status = inspect_codex_status(
            executable="codex",
            runner=lambda *_args, **_kwargs: completed(
                "Logged in using ChatGPT"
            ),
        )
        self.assertTrue(status.authenticated)
        self.assertEqual(status.auth_method, "chatgpt")
        self.assertIn("额度由 OpenAI 账号决定", status.guidance)

    def test_api_key_login_warns_about_separate_billing(self):
        """API Key 登录必须明确提示单独计费。"""

        status = inspect_codex_status(
            executable="codex",
            runner=lambda *_args, **_kwargs: completed(
                "Logged in using an API key"
            ),
        )
        self.assertTrue(status.authenticated)
        self.assertEqual(status.auth_method, "api_key")
        self.assertIn("另行承担", status.guidance)

    def test_unexpected_failure_does_not_expose_raw_output(self):
        """无法识别时只返回固定提示，不回显第三方文本。"""

        status = inspect_codex_status(
            executable="codex",
            runner=lambda *_args, **_kwargs: completed(
                r"failure at C:\Users\Alice\secret", 2
            ),
        )
        self.assertEqual(status.auth_method, "unknown")
        self.assertNotIn("Alice", status.guidance)
        self.assertNotIn("secret", status.guidance)

    def test_login_starts_official_codex_without_shell(self):
        """登录只能启动已定位的 Codex，不能拼接 shell 命令。"""

        seen = {}
        expected_process = object()

        def process_factory(command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            return expected_process

        process = start_codex_login(
            executable=r"C:\safe\codex.exe",
            process_factory=process_factory,
        )

        self.assertIs(process, expected_process)
        self.assertEqual(
            seen["command"], [r"C:\safe\codex.exe", "login"]
        )
        self.assertFalse(seen["kwargs"]["shell"])
        self.assertEqual(seen["kwargs"]["stdout"], subprocess.DEVNULL)
        self.assertEqual(seen["kwargs"]["stderr"], subprocess.DEVNULL)

    def test_login_refuses_when_codex_is_missing(self):
        """找不到 Codex 时必须停止，不能尝试其他命令。"""

        with self.assertRaises(CodexLoginError):
            start_codex_login(
                finder=lambda _name: None,
                candidate_roots=[],
            )


if __name__ == "__main__":
    unittest.main()
