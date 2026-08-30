# -*- coding: utf-8 -*-
"""测试模型类型与内置 Abaqus 脚本之间的安全映射。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from abaqus_codex.configuration import validate_config
from abaqus_codex.workflow import (
    _abaqus_script_for_config,
    _require_automation_abaqus,
    run_analysis,
)
from test_configuration import (
    valid_biaxial_config,
    valid_cantilever_config,
    valid_config,
    valid_hole_config,
    valid_moving_load_config,
)


class AbaqusScriptSelectionTests(unittest.TestCase):
    """确保配置只能选择项目内明确支持的脚本。"""

    def test_rectangle_uses_original_script(self):
        """旧矩形板配置应继续选择原始脚本。"""

        config = validate_config(valid_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name, "rectangle_tension.py"
        )

    def test_hole_plate_uses_new_script(self):
        """圆孔板配置应选择新的圆孔建模脚本。"""

        config = validate_config(valid_hole_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name,
            "plate_with_hole_tension.py",
        )

    def test_cantilever_uses_bending_script(self):
        """悬臂梁配置应选择均布载荷弯曲脚本。"""

        config = validate_config(valid_cantilever_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name,
            "cantilever_bending.py",
        )

    def test_biaxial_plate_uses_biaxial_script(self):
        """双向拉伸配置应选择方板双向加载脚本。"""

        config = validate_config(valid_biaxial_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name,
            "biaxial_tension.py",
        )

    def test_moving_load_uses_road_script(self):
        """三维移动轮载配置应选择需要 DLOAD 的路面脚本。"""

        config = validate_config(valid_moving_load_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name,
            "moving_load_road.py",
        )



class AutomationVersionGateTests(unittest.TestCase):
    """确认自动求解对检测失败和未获准年份一律关闭。"""

    @patch("abaqus_codex.workflow.inspect_abaqus")
    def test_unusable_unknown_release_is_rejected(self, inspect_abaqus_mock):
        """版本未知或内置 Python 不可用时不能继续寻找 abqpy。"""

        inspect_abaqus_mock.return_value = {
            "usable": False,
            "command": r"C:\SIMULIA\Commands\abaqus.bat",
            "version": None,
        }

        with self.assertRaisesRegex(RuntimeError, "没有可靠检测"):
            _require_automation_abaqus()

    @patch("abaqus_codex.workflow.inspect_abaqus")
    def test_2026_and_2027_are_rejected(self, inspect_abaqus_mock):
        """已知不兼容和超出自动化白名单的年份都必须失败关闭。"""

        for version, message in (
            ("2026", "已知不兼容"),
            ("2027", "尚未列入自动求解范围"),
        ):
            with self.subTest(version=version):
                inspect_abaqus_mock.return_value = {
                    "usable": True,
                    "command": r"C:\SIMULIA\Commands\abq{0}.bat".format(
                        version
                    ),
                    "version": version,
                }
                with self.assertRaisesRegex(RuntimeError, message):
                    _require_automation_abaqus()

    @patch("abaqus_codex.workflow.inspect_abaqus")
    def test_2025_returns_the_checked_command(self, inspect_abaqus_mock):
        """白名单中的 2025 应返回完整体检结果供后续绑定命令。"""

        inspected = {
            "usable": True,
            "command": r"C:\SIMULIA\Commands\abq2025.bat",
            "version": "2025",
        }
        inspect_abaqus_mock.return_value = inspected

        self.assertIs(_require_automation_abaqus(), inspected)

    def test_run_binds_abqpy_to_the_checked_abaqus_command(self):
        """abqpy 子进程必须通过环境变量使用门禁已经检查过的命令。"""

        config = validate_config(valid_config())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checked_command = str((root / "abq2025.bat").resolve())
            inspected = {
                "usable": True,
                "command": checked_command,
                "version": "2025",
            }
            completed = Mock(returncode=1, stdout=b"test failure")
            with (
                patch("abaqus_codex.workflow.load_config", return_value=config),
                patch(
                    "abaqus_codex.workflow._require_automation_abaqus",
                    return_value=inspected,
                ),
                patch(
                    "abaqus_codex.workflow.build_abqpy_command_prefix",
                    return_value=["abqpy"],
                ),
                patch(
                    "abaqus_codex.workflow.subprocess.run",
                    return_value=completed,
                ) as run_mock,
                patch(
                    "abaqus_codex.workflow.activate_user_python_packages",
                    return_value=root / "user-packages",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "Abaqus 返回退出码"):
                    run_analysis(
                        root / "config.json",
                        root / "work",
                        root / "output",
                    )

        child_environment = run_mock.call_args.kwargs["env"]
        self.assertEqual(
            child_environment["ABAQUS_BAT_PATH"], checked_command
        )
        self.assertTrue(
            child_environment["PYTHONPATH"].startswith(
                str(root / "user-packages")
            )
        )


if __name__ == "__main__":
    unittest.main()
