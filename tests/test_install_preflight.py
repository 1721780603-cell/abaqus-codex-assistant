# -*- coding: utf-8 -*-
"""测试统一安装只检测 Abaqus，而不把年份当成整包门槛。"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from abaqus_codex.install_preflight import inspect_installation_target, main


def abaqus_result(version, *, installed=True, usable=True):
    """构造不启动真实 Abaqus 的检查结果。"""

    return {
        "installed": installed,
        "usable": usable,
        "command": r"C:\SIMULIA\Commands\abaqus.bat" if installed else None,
        "version": version,
        "python_version": "2.7.18" if usable else None,
        "python_executable": "ABQLauncher.exe" if usable else None,
        "message": "mock",
    }


class InstallationPreflightTests(unittest.TestCase):
    """核心安装与安全修改插件必须使用两个独立判断。"""

    @patch("abaqus_codex.install_preflight.inspect_abaqus")
    def test_2021_installs_core_and_verified_plugin(self, inspect_mock):
        inspect_mock.return_value = abaqus_result("2021")

        result = inspect_installation_target()

        self.assertTrue(result["detected"])
        self.assertTrue(result["safe_plugin_supported"])

    @patch("abaqus_codex.install_preflight.inspect_abaqus")
    def test_other_years_are_accepted_for_core_install(self, inspect_mock):
        for version in ("2022", "2026", "2030"):
            with self.subTest(version=version):
                inspect_mock.return_value = abaqus_result(version)
                result = inspect_installation_target()
                self.assertTrue(result["detected"])
                self.assertFalse(result["safe_plugin_supported"])

    @patch("abaqus_codex.install_preflight.inspect_abaqus")
    def test_detected_command_with_unknown_version_still_allows_core(self, inspect_mock):
        inspect_mock.return_value = abaqus_result(None, usable=False)

        result = inspect_installation_target()

        self.assertTrue(result["detected"])
        self.assertFalse(result["usable"])
        self.assertFalse(result["safe_plugin_supported"])

    @patch("abaqus_codex.install_preflight.inspect_abaqus")
    def test_missing_abaqus_returns_diagnostic_without_claiming_detection(self, inspect_mock):
        inspect_mock.return_value = abaqus_result(None, installed=False, usable=False)

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(json_output=True)

        self.assertEqual(exit_code, 1)
        self.assertFalse(json.loads(output.getvalue())["detected"])

    @patch("abaqus_codex.install_preflight.inspect_abaqus")
    def test_json_output_is_ascii_for_powershell_51(self, inspect_mock):
        inspect_mock.return_value = abaqus_result("2022")

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(json_output=True)

        self.assertEqual(exit_code, 0)
        output.getvalue().encode("ascii")
        self.assertEqual(json.loads(output.getvalue())["year"], 2022)


if __name__ == "__main__":
    unittest.main()
