# -*- coding: utf-8 -*-
"""测试安全动作插件安装器的版本门禁、演练和备份规则。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.safe_action_setup import (
    SafeActionSetupError,
    default_plugin_target,
    setup_safe_action_plugin,
)


def abaqus_result(version: str = "2021", usable: bool = True):
    """生成安装测试使用的最小 Abaqus 体检结果。"""

    return {
        "installed": usable,
        "usable": usable,
        "command": r"C:\SIMULIA\Commands\abaqus.bat" if usable else None,
        "version": version if usable else None,
        "python_version": "2.7.15" if usable else None,
        "python_executable": "SMAPython.exe" if usable else None,
        "message": "测试用 Abaqus 状态。",
    }


def make_plugin(directory: Path, marker: str = "new") -> Path:
    """在临时目录中创建一份最小而完整的测试插件。"""

    directory.mkdir(parents=True)
    (directory / "safe_material_action_plugin.py").write_text(
        "# 插件 {0}\n".format(marker), encoding="utf-8"
    )
    (directory / "safe_material_action_kernel.py").write_text(
        "# 内核 {0}\n".format(marker), encoding="utf-8"
    )
    (directory / "README.md").write_text(
        "测试插件 {0}\n".format(marker), encoding="utf-8"
    )
    return directory


class SafeActionSetupTests(unittest.TestCase):
    """确认安装器不会联网、跨版本安装或覆盖旧插件。"""

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_confirmation_is_required_before_environment_probe(self, inspect_mock):
        """非演练安装没有明确确认时，不应开始环境探测。"""

        with self.assertRaisesRegex(SafeActionSetupError, "明确确认"):
            setup_safe_action_plugin(confirmed=False)

        inspect_mock.assert_not_called()

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_unusable_or_non_2021_abaqus_is_rejected(self, inspect_mock):
        """没有可用环境或版本不是 2021 时，不能形成安装写入。"""

        for result, expected in (
            (abaqus_result(usable=False), "没有检测到可用"),
            (abaqus_result("2022"), "只支持 Abaqus 2021"),
            (abaqus_result("2026"), "只支持 Abaqus 2021"),
        ):
            with self.subTest(version=result.get("version")):
                inspect_mock.return_value = result
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = make_plugin(root / "source")
                    target = root / "target" / "safe_material_action"
                    with self.assertRaisesRegex(SafeActionSetupError, expected):
                        setup_safe_action_plugin(
                            confirmed=True, source=source, target=target
                        )
                    self.assertFalse(target.exists())

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_dry_run_reports_new_install_without_writing(self, inspect_mock):
        """dry-run 可以不确认，但不能创建目标目录或备份。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source")
            target = root / "plugins" / "safe_material_action"

            result = setup_safe_action_plugin(
                confirmed=False,
                source=source,
                target=target,
                dry_run=True,
            )

            self.assertTrue(result["changed"])
            self.assertTrue(result["dry_run"])
            self.assertIsNone(result["backup"])
            self.assertFalse(target.exists())
            self.assertFalse(target.parent.exists())

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_first_install_copies_complete_plugin(self, inspect_mock):
        """首次安装应复制全部内容，并且不创建无意义备份。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source")
            nested = source / "assets"
            nested.mkdir()
            (nested / "notice.txt").write_text("中文资源", encoding="utf-8")
            target = root / "plugins" / "safe_material_action"

            result = setup_safe_action_plugin(
                confirmed=True,
                source=source,
                target=target,
                backup_root=root / "recovery" / "plugin",
            )

            self.assertTrue(result["changed"])
            self.assertFalse(result["dry_run"])
            self.assertIsNone(result["backup"])
            self.assertEqual(
                (target / "assets" / "notice.txt").read_text(encoding="utf-8"),
                "中文资源",
            )

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_existing_plain_file_target_is_preserved_and_rejected(
        self, inspect_mock
    ):
        """普通文件不能被当成插件目录备份，否则卸载无法原样恢复。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source")
            target = root / "plugins" / "safe_material_action"
            target.parent.mkdir()
            target.write_text("用户文件", encoding="utf-8")

            with self.assertRaisesRegex(SafeActionSetupError, "不是目录"):
                setup_safe_action_plugin(
                    confirmed=True,
                    source=source,
                    target=target,
                    backup_root=root / "recovery" / "plugin",
                )

            self.assertEqual(target.read_text(encoding="utf-8"), "用户文件")
            self.assertFalse((root / "recovery").exists())

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_identical_install_is_left_untouched(self, inspect_mock):
        """目标内容相同时应直接返回，不生成备份或临时目录。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source")
            target = make_plugin(root / "plugins" / "safe_material_action")

            result = setup_safe_action_plugin(
                confirmed=True,
                source=source,
                target=target,
                backup_root=root / "recovery" / "plugin",
            )

            self.assertFalse(result["changed"])
            self.assertIsNone(result["backup"])
            self.assertEqual(list(target.parent.glob("safe_material_action.backup-*")), [])
            self.assertEqual(list(target.parent.glob(".safe_material_action.installing-*")), [])

    @patch("abaqus_codex.safe_action_setup.shutil.rmtree")
    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_different_install_is_renamed_to_backup_without_recursive_delete(
        self, inspect_mock, rmtree_mock
    ):
        """旧插件必须完整改名备份，新版本换入，且不调用递归删除。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source", marker="new")
            target = make_plugin(root / "plugins" / "safe_material_action", marker="old")
            (target / "user-note.txt").write_text("用户文件", encoding="utf-8")

            result = setup_safe_action_plugin(
                confirmed=True,
                source=source,
                target=target,
                backup_root=root / "recovery" / "plugin",
            )

            backup = Path(str(result["backup"]))
            self.assertTrue(backup.is_dir())
            self.assertEqual(backup.parent, root / "recovery" / "plugin")
            self.assertNotEqual(backup.parent, target.parent)
            self.assertIn(".backup-", backup.name)
            self.assertEqual(
                (backup / "user-note.txt").read_text(encoding="utf-8"),
                "用户文件",
            )
            self.assertFalse((target / "user-note.txt").exists())
            self.assertIn(
                "new",
                (target / "safe_material_action_plugin.py").read_text(
                    encoding="utf-8"
                ),
            )
            rmtree_mock.assert_not_called()

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_dry_run_with_old_plugin_predicts_backup_only(self, inspect_mock):
        """旧插件存在时，dry-run 只报告备份路径，不移动任何文件。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source", marker="new")
            target = make_plugin(root / "safe_material_action", marker="old")

            result = setup_safe_action_plugin(
                confirmed=False, source=source, target=target, dry_run=True
            )

            self.assertTrue(result["changed"])
            self.assertIsNotNone(result["backup"])
            self.assertFalse(Path(str(result["backup"])).exists())
            self.assertIn(
                "old",
                (target / "safe_material_action_plugin.py").read_text(
                    encoding="utf-8"
                ),
            )

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_incomplete_source_is_rejected_before_target_write(self, inspect_mock):
        """缺少关键文件的源码不能被当作可安装插件。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "safe_material_action_plugin.py").write_text(
                "# 只有界面入口\n", encoding="utf-8"
            )
            target = root / "safe_material_action"

            with self.assertRaisesRegex(SafeActionSetupError, "源码不完整"):
                setup_safe_action_plugin(
                    confirmed=True, source=source, target=target
                )

            self.assertFalse(target.exists())

    @patch("abaqus_codex.safe_action_setup.inspect_abaqus")
    def test_source_and_target_ancestry_overlap_is_rejected(self, inspect_mock):
        """插件安装不得把目标放入资源内部，也不得反过来。"""

        inspect_mock.return_value = abaqus_result()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_plugin(root / "source")
            with self.assertRaisesRegex(SafeActionSetupError, "互为父目录"):
                setup_safe_action_plugin(
                    confirmed=True,
                    source=source,
                    target=source / "nested-target",
                    backup_root=root / "recovery" / "plugin",
                )
            self.assertFalse((source / "nested-target").exists())

    def test_default_target_uses_userprofile(self):
        """Windows 默认路径应明确落在当前用户的 abaqus_plugins 下。"""

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"USERPROFILE": directory}):
                target = default_plugin_target()

        self.assertEqual(
            target,
            Path(directory) / "abaqus_plugins" / "safe_material_action",
        )


if __name__ == "__main__":
    unittest.main()
