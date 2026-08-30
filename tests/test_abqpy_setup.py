# -*- coding: utf-8 -*-
"""测试 abqpy 按检测年份安装时的确认门槛和禁止回退规则。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

from abaqus_codex.abqpy_setup import (
    AbqpySetupError,
    build_install_command,
    setup_abqpy,
)
from abaqus_codex.paths import project_python_executable


def usable_abaqus(version: str):
    """生成安装流程测试所需的最小 Abaqus 体检结果。"""

    return {
        "installed": True,
        "usable": True,
        "command": r"C:\SIMULIA\Commands\abq{0}.bat".format(version),
        "version": version,
        "python_version": "3.10.5" if version == "2026" else "2.7.15",
        "python_executable": "SMAPython.exe",
        "message": "测试用 Abaqus 可用。",
    }


def abqpy_result(abaqus_version: str, version=None, usable=False):
    """生成安装前后版本复检使用的最小结构。"""

    return {
        "installed": version is not None,
        "usable": usable,
        "version": version,
        "abaqus_version": abaqus_version,
        "compatible": usable,
        "python_executable": sys.executable,
        "message": "测试用 abqpy 状态。",
    }


class AbqpySetupSafetyTests(unittest.TestCase):
    """确认安装只能在明确授权和可靠年份检测后进行。"""

    def test_private_runtime_install_command_uses_explicit_user_target(self):
        """安装版可选依赖不得写进由 Setup 管理的 runtime。"""

        target = Path(
            r"C:\Users\tester\AppData\Local\AbaqusCodexAssistant\python-packages"
        )
        command = build_install_command("abqpy==2025.*", target=target)

        self.assertEqual(
            command[:4],
            [str(project_python_executable()), "-I", "-m", "pip"],
        )
        self.assertEqual(command[-3:], ["--target", str(target), "abqpy==2025.*"])

    def test_source_install_command_preserves_existing_python_environment(self):
        """源码安装不使用用户包目录，命令形式保持兼容。"""

        command = build_install_command("abqpy==2021.*")

        self.assertEqual(
            command[:4],
            [str(project_python_executable()), "-m", "pip", "install"],
        )
        self.assertNotIn("-I", command)
        self.assertNotIn("--target", command)

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_confirmation_is_required_before_any_inspection_or_install(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """没有 --yes 时连环境探测之后的安装流程也不应开始。"""

        with self.assertRaises(AbqpySetupError):
            setup_abqpy(confirmed=False)

        inspect_abaqus_mock.assert_not_called()
        inspect_abqpy_mock.assert_not_called()
        install_mock.assert_not_called()

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_unusable_abaqus_stops_before_abqpy_install(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """没有可用 Abaqus 和内置 Python 时不得尝试安装 abqpy。"""

        inspect_abaqus_mock.return_value = {
            "installed": False,
            "usable": False,
            "version": None,
            "message": "没有找到 Abaqus。",
        }

        with self.assertRaises(AbqpySetupError):
            setup_abqpy(confirmed=True)

        inspect_abqpy_mock.assert_not_called()
        install_mock.assert_not_called()

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_2022_and_2025_install_only_their_exact_year(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """每个检测年份只能形成一次同年份 pip 安装，不得使用其他版本。"""

        for abaqus_year, installed_version in (
            ("2022", "2022.10.1"),
            ("2025", "2025.4.0"),
        ):
            with self.subTest(abaqus_year=abaqus_year):
                inspect_abaqus_mock.reset_mock()
                inspect_abqpy_mock.reset_mock()
                install_mock.reset_mock()
                inspect_abaqus_mock.return_value = usable_abaqus(abaqus_year)
                inspect_abqpy_mock.side_effect = [
                    abqpy_result(abaqus_year),
                    abqpy_result(
                        abaqus_year, version=installed_version, usable=True
                    ),
                ]

                result = setup_abqpy(confirmed=True)

                expected_requirement = "abqpy=={0}.*".format(abaqus_year)
                self.assertTrue(result["changed"])
                self.assertEqual(result["requirement"], expected_requirement)
                install_mock.assert_called_once()
                command = install_mock.call_args.args[0]
                self.assertEqual(command[-1], expected_requirement)
                self.assertEqual(
                    command[:4],
                    [
                        str(project_python_executable()),
                        "-m",
                        "pip",
                        "install",
                    ],
                )
                self.assertEqual(
                    inspect_abqpy_mock.call_args_list,
                    [call(abaqus_year), call(abaqus_year)],
                )

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_known_incompatible_2026_stops_before_abqpy_inspection_or_install(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """检测到 2026 后应直接阻断，不能形成 pip 命令或尝试其他年份。"""

        inspect_abaqus_mock.return_value = usable_abaqus("2026")

        with self.assertRaises(AbqpySetupError):
            setup_abqpy(confirmed=True)

        inspect_abqpy_mock.assert_not_called()
        install_mock.assert_not_called()

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_matching_abqpy_is_not_reinstalled(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """已经匹配时应直接返回，避免无意义联网和环境变更。"""

        inspect_abaqus_mock.return_value = usable_abaqus("2022")
        before = abqpy_result("2022", version="2022.10.1", usable=True)
        inspect_abqpy_mock.return_value = before

        result = setup_abqpy(confirmed=True)

        self.assertFalse(result["changed"])
        self.assertIs(result["abqpy"], before)
        inspect_abqpy_mock.assert_called_once_with("2022")
        install_mock.assert_not_called()

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_install_failure_is_reported_without_year_fallback(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """2025 安装失败后必须停止，不能偷偷尝试 2024 或 2021。"""

        inspect_abaqus_mock.return_value = usable_abaqus("2025")
        inspect_abqpy_mock.return_value = abqpy_result("2025")
        install_mock.side_effect = AbqpySetupError("测试用 pip 失败")

        with self.assertRaisesRegex(AbqpySetupError, "测试用 pip 失败"):
            setup_abqpy(confirmed=True)

        install_mock.assert_called_once()
        self.assertEqual(install_mock.call_args.args[0][-1], "abqpy==2025.*")
        inspect_abqpy_mock.assert_called_once_with("2025")

    @patch("abaqus_codex.abqpy_setup._run_install")
    @patch("abaqus_codex.abqpy_setup.inspect_abqpy")
    @patch("abaqus_codex.abqpy_setup.inspect_abaqus")
    def test_post_install_mismatch_fails_without_second_install(
        self, inspect_abaqus_mock, inspect_abqpy_mock, install_mock
    ):
        """pip 成功但复检仍不匹配时应报错，不能再次安装其他年份。"""

        inspect_abaqus_mock.return_value = usable_abaqus("2025")
        inspect_abqpy_mock.side_effect = [
            abqpy_result("2025"),
            abqpy_result("2025", version="2024.9.0", usable=False),
        ]

        with self.assertRaisesRegex(AbqpySetupError, "仍未与 Abaqus 年份匹配"):
            setup_abqpy(confirmed=True)

        install_mock.assert_called_once()
        self.assertEqual(install_mock.call_args.args[0][-1], "abqpy==2025.*")


if __name__ == "__main__":
    unittest.main()
