# -*- coding: utf-8 -*-
"""离线验证安装版路径、Skill 恢复和 Abaqus 2021 插件门禁。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.distribution_integration import (
    DistributionIntegrationError,
    MANIFEST_FILENAME,
    _install_directory,
    _next_recovery_path,
    integration_remove,
    integration_setup,
)
from abaqus_codex.paths import (
    activate_user_python_packages,
    is_private_runtime,
    project_python_executable,
    resource_root,
    user_data_root,
)


def make_resources(root: Path) -> Path:
    """创建最小但完整的离线发布资源。"""

    (root / "configs").mkdir(parents=True)
    skill = root / "skills" / "abaqus-modeling-guide"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# 新 Skill\n", encoding="utf-8")
    plugin = root / "abaqus_plugins" / "safe_material_action"
    plugin.mkdir(parents=True)
    (plugin / "safe_material_action_plugin.py").write_text(
        "# plugin\n", encoding="utf-8"
    )
    (plugin / "safe_material_action_kernel.py").write_text(
        "# kernel\n", encoding="utf-8"
    )
    return root


def abaqus_result(version: str = "2021", usable: bool = True) -> dict[str, object]:
    return {
        "installed": usable,
        "usable": usable,
        "version": version if usable else None,
        "python_version": "2.7.15" if usable else None,
        "command": "abaqus.bat" if usable else None,
    }


class RuntimePathTests(unittest.TestCase):
    """资源只读根与用户可写根不得混用。"""

    def test_private_runtime_finds_application_resource_root(self):
        """从 app/runtime/Lib/site-packages 向上能找到发布资源。"""

        with tempfile.TemporaryDirectory() as directory:
            app_root = make_resources(Path(directory) / "app")
            module_path = app_root / "runtime" / "Lib" / "site-packages" / "abaqus_codex" / "paths.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# probe\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch(
                "abaqus_codex.paths.__file__", str(module_path)
            ), patch("abaqus_codex.paths.sys.executable", str(app_root / "runtime" / "python.exe")):
                self.assertEqual(resource_root(), app_root.resolve())

    def test_named_gui_executable_maps_to_private_console_python(self):
        """派生 pip/MCP 时必须使用可承载 stdio 的 python.exe。"""

        with tempfile.TemporaryDirectory() as directory:
            app_root = make_resources(Path(directory) / "app")
            runtime = app_root / "runtime"
            runtime.mkdir()
            gui_executable = runtime / "AbaqusCodexAssistant.exe"
            console_python = runtime / "python.exe"
            gui_executable.touch()
            console_python.touch()
            module_path = (
                runtime
                / "Lib"
                / "site-packages"
                / "abaqus_codex"
                / "paths.py"
            )
            module_path.parent.mkdir(parents=True)
            module_path.touch()
            with patch.dict(os.environ, {}, clear=True), patch(
                "abaqus_codex.paths.__file__", str(module_path)
            ), patch(
                "abaqus_codex.paths.sys.executable", str(gui_executable)
            ):
                self.assertEqual(
                    project_python_executable(), console_python.resolve()
                )

    def test_private_runtime_ignores_stale_install_root_environment(self):
        """官方 runtime 的完整自身资源不得被残留环境变量劫持。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_root = make_resources(root / "app")
            stale_root = make_resources(root / "stale")
            module_path = app_root / "runtime" / "Lib" / "site-packages" / "abaqus_codex" / "paths.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# runtime\n", encoding="utf-8")
            executable = app_root / "runtime" / "python.exe"
            executable.write_bytes(b"")
            with patch.dict(
                os.environ,
                {"ABAQUS_CODEX_INSTALL_ROOT": str(stale_root)},
                clear=False,
            ), patch("abaqus_codex.paths.__file__", str(module_path)), patch(
                "abaqus_codex.paths.sys.executable", str(executable)
            ):
                self.assertEqual(resource_root(), app_root.resolve())

    def test_user_data_defaults_to_local_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": directory, "ABAQUS_CODEX_USER_DATA_ROOT": ""},
                clear=False,
            ):
                self.assertEqual(
                    user_data_root(),
                    Path(directory).resolve() / "AbaqusCodexAssistant",
                )

    def test_private_runtime_activates_only_its_user_package_directory(self):
        """安装版使用私有解释器时才激活可写依赖目录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_root = make_resources(root / "app")
            module_path = (
                app_root
                / "runtime"
                / "Lib"
                / "site-packages"
                / "abaqus_codex"
                / "paths.py"
            )
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# probe\n", encoding="utf-8")
            private_path = app_root / "runtime" / "python.exe"
            local_data = root / "local-data"
            isolated_sys_path = ["runtime-site-packages"]
            with patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(local_data),
                    "ABAQUS_CODEX_USER_DATA_ROOT": "",
                },
                clear=False,
            ), patch(
                "abaqus_codex.paths.__file__", str(module_path)
            ), patch(
                "abaqus_codex.paths.sys.executable", str(private_path)
            ), patch(
                "abaqus_codex.paths.sys.path", isolated_sys_path
            ):
                self.assertTrue(is_private_runtime())
                activated = activate_user_python_packages(create=True)

            expected = (
                local_data / "AbaqusCodexAssistant" / "python-packages"
            ).resolve()
            self.assertEqual(activated, expected)
            self.assertEqual(isolated_sys_path[0], str(expected))
            self.assertTrue(expected.is_dir())

    def test_source_runtime_does_not_create_or_activate_user_packages(self):
        """源码模式不修改 sys.path，也不创建安装版数据目录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = make_resources(root / "source")
            module_path = source_root / "src" / "abaqus_codex" / "paths.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("# probe\n", encoding="utf-8")
            local_data = root / "local-data"
            isolated_sys_path = ["source-tree"]
            with patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(local_data),
                    "ABAQUS_CODEX_USER_DATA_ROOT": "",
                },
                clear=False,
            ), patch(
                "abaqus_codex.paths.__file__", str(module_path)
            ), patch(
                "abaqus_codex.paths.sys.executable",
                str(root / "system-python" / "python.exe"),
            ), patch(
                "abaqus_codex.paths.sys.path", isolated_sys_path
            ):
                self.assertFalse(is_private_runtime())
                activated = activate_user_python_packages(create=True)

            self.assertIsNone(activated)
            self.assertEqual(isolated_sys_path, ["source-tree"])
            self.assertFalse(
                (
                    local_data
                    / "AbaqusCodexAssistant"
                    / "python-packages"
                ).exists()
            )


class DistributionIntegrationTests(unittest.TestCase):
    """集成只操作当前用户目录，并且所有移除都可恢复。"""

    def setUp(self):
        self.headless_patcher = patch(
            "abaqus_codex.mcp_setup.stop_managed_headless_bridge_for_uninstall",
            return_value={"status": "not_running", "stopped": True},
        )
        self.registration_patcher = patch(
            "abaqus_codex.mcp_setup.remove_managed_codex_registration",
            return_value={"status": "not_registered", "removed": False},
        )
        self.headless_patcher.start()
        self.registration_patcher.start()
        self.addCleanup(self.headless_patcher.stop)
        self.addCleanup(self.registration_patcher.stop)

    def test_skill_install_manifest_and_recoverable_remove(self):
        """新 Skill 安装后清单位于用户数据根，卸载只改名。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "custom-codex"
            data = root / "data"
            profile = root / "profile"
            with patch.dict(os.environ, {"USERPROFILE": str(profile)}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                installed = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                target = codex / "skills" / "abaqus-modeling-guide"
                self.assertTrue((target / "SKILL.md").is_file())
                self.assertFalse((profile / "abaqus_plugins").exists())
                manifest = data / MANIFEST_FILENAME
                self.assertTrue(manifest.is_file())
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertTrue(Path(payload["user_data_root"]).samefile(data))
                self.assertTrue(Path(payload["codex_home"]).samefile(codex))
                self.assertFalse(installed["plugin"]["eligible"])

                removed = integration_remove(confirmed=True, data_root=data)

            self.assertFalse(target.exists())
            self.assertEqual(removed["skill"]["status"], "moved_to_recovery")
            self.assertTrue(Path(removed["skill"]["recovery_copy"]).is_dir())
            self.assertFalse((data / MANIFEST_FILENAME).exists())
            self.assertTrue(Path(removed["archived_manifest"]).is_file())
            self.assertEqual(removed["headless_bridge"]["status"], "not_running")
            self.assertEqual(removed["mcp_registration"]["status"], "not_registered")

    def test_existing_skill_is_backed_up_and_restored(self):
        """替换旧 Skill 前先完整备份，移除时恢复旧内容。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            target = codex / "skills" / "abaqus-modeling-guide"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("# 用户旧 Skill\n", encoding="utf-8")
            data = root / "data"
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                installed = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                backup = Path(str(installed["skill"]["backup"]))
                self.assertEqual(backup.parent, data / "recovery" / "skill")
                self.assertNotEqual(backup.parent, target.parent)
                self.assertIn("用户旧", (backup / "SKILL.md").read_text(encoding="utf-8"))
                removed = integration_remove(confirmed=True, data_root=data)

            self.assertEqual(removed["skill"]["status"], "restored_backup")
            self.assertIn("用户旧", (target / "SKILL.md").read_text(encoding="utf-8"))

    def test_two_upgrades_keep_first_user_backup_for_uninstall(self):
        """v1→v2 只生成升级恢复副本，卸载仍恢复安装前的用户 Skill。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            target = codex / "skills" / "abaqus-modeling-guide"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("# 用户原版\n", encoding="utf-8")
            data = root / "data"
            patches = (
                patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}),
                patch(
                    "abaqus_codex.distribution_integration.resource_root",
                    return_value=resources,
                ),
                patch(
                    "abaqus_codex.distribution_integration.inspect_abaqus",
                    return_value=abaqus_result(usable=False),
                ),
            )
            with patches[0], patches[1], patches[2]:
                first = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                first_backup = Path(str(first["skill"]["backup"]))
                (resources / "skills" / "abaqus-modeling-guide" / "SKILL.md").write_text(
                    "# 程序 v2\n", encoding="utf-8"
                )
                second = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                self.assertEqual(Path(str(second["skill"]["backup"])), first_backup)
                upgrades = [
                    Path(value) for value in second["skill"]["upgrade_recoveries"]
                ]
                self.assertEqual(len(upgrades), 1)
                self.assertTrue(upgrades[0].is_dir())
                self.assertEqual(upgrades[0].parent, data / "recovery" / "skill")
                self.assertNotEqual(upgrades[0].parent, target.parent)
                removed = integration_remove(confirmed=True, data_root=data)

            self.assertEqual(removed["skill"]["status"], "restored_backup")
            self.assertIn("用户原版", (target / "SKILL.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "Windows 路径大小写语义回归")
    def test_upgrade_keeps_ownership_when_manifest_path_case_differs(self):
        """清单仅改变路径大小写时仍须保留最初用户备份。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            target = codex / "skills" / "abaqus-modeling-guide"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("# 用户原版\n", encoding="utf-8")
            data = root / "data"
            with patch.dict(
                os.environ, {"USERPROFILE": str(root / "profile")}
            ), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                first = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                first_backup = Path(str(first["skill"]["backup"]))
                manifest_path = data / MANIFEST_FILENAME
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload["skill"]["target"] = str(payload["skill"]["target"]).swapcase()
                manifest_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                (resources / "skills" / "abaqus-modeling-guide" / "SKILL.md").write_text(
                    "# 程序 v2\n", encoding="utf-8"
                )

                second = integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                self.assertEqual(Path(str(second["skill"]["backup"])), first_backup)
                self.assertEqual(len(second["skill"]["upgrade_recoveries"]), 1)
                removed = integration_remove(confirmed=True, data_root=data)

            self.assertEqual(removed["skill"]["status"], "restored_backup")
            self.assertIn(
                "用户原版", (target / "SKILL.md").read_text(encoding="utf-8")
            )

    def test_existing_manifest_rejects_changed_codex_home(self):
        """旧集成未移除时不能换 CODEX_HOME 后覆盖清单。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            data = root / "data"
            codex_one = root / "codex-one"
            codex_two = root / "codex-two"
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(
                    confirmed=True, codex_home_path=codex_one, data_root=data
                )
                original_manifest = (data / MANIFEST_FILENAME).read_text(encoding="utf-8")
                with self.assertRaisesRegex(
                    DistributionIntegrationError, "先.*integration-remove"
                ):
                    integration_setup(
                        confirmed=True, codex_home_path=codex_two, data_root=data
                    )

            self.assertEqual(
                (data / MANIFEST_FILENAME).read_text(encoding="utf-8"),
                original_manifest,
            )
            self.assertFalse((codex_two / "skills").exists())

    def test_legacy_sibling_backup_manifest_is_not_auto_migrated(self):
        """旧清单没有隔离恢复区时，不自动移动历史备份。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            data = root / "data"
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                payload = json.loads((data / MANIFEST_FILENAME).read_text(encoding="utf-8"))
                payload["skill"].pop("recovery_root", None)
                legacy_backup = codex / "skills" / "abaqus-modeling-guide.backup-old"
                payload["skill"]["backup"] = str(legacy_backup)
                (data / MANIFEST_FILENAME).write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                with self.assertRaisesRegex(
                    DistributionIntegrationError, "不会自动迁移"
                ):
                    integration_setup(
                        confirmed=True, codex_home_path=codex, data_root=data
                    )

            self.assertFalse(legacy_backup.exists())

    def test_symlink_target_is_rejected_without_following(self):
        """安装不得把 Skill 换入链接指向的外部目录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            target = codex / "skills" / "abaqus-modeling-guide"
            target.parent.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "sentinel.txt").write_text("不能改", encoding="utf-8")
            try:
                target.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest("当前系统不允许创建目录 symlink：{0}".format(error))
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                with self.assertRaisesRegex(
                    DistributionIntegrationError, "符号链接|Windows 联接点"
                ):
                    integration_setup(
                        confirmed=True,
                        codex_home_path=codex,
                        data_root=root / "data",
                    )

            self.assertEqual(
                (outside / "sentinel.txt").read_text(encoding="utf-8"), "不能改"
            )
            self.assertFalse((root / "data" / MANIFEST_FILENAME).exists())

    def test_remove_rejects_target_replaced_by_symlink(self):
        """卸载前若目标被替换为链接，应整体失败关闭。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            data = root / "data"
            outside = root / "outside"
            outside.mkdir()
            (outside / "sentinel.txt").write_text("保留", encoding="utf-8")
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                target = codex / "skills" / "abaqus-modeling-guide"
                target.replace(root / "parked-managed-skill")
                try:
                    target.symlink_to(outside, target_is_directory=True)
                except OSError as error:
                    self.skipTest("当前系统不允许创建目录 symlink：{0}".format(error))
                with self.assertRaisesRegex(
                    DistributionIntegrationError, "符号链接|Windows 联接点"
                ):
                    integration_remove(confirmed=True, data_root=data)

            self.assertTrue((data / MANIFEST_FILENAME).is_file())
            self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"), "保留")

    @unittest.skipUnless(
        os.name == "nt" and callable(getattr(Path("."), "is_junction", None)),
        "当前平台不提供 Windows junction 检测",
    )
    def test_junction_parent_is_rejected_when_available(self):
        """Windows junction 不是 is_symlink，也必须在写入前被拦截。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            real_codex = root / "real-codex"
            real_codex.mkdir()
            junction = root / "codex-junction"
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(real_codex)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed.returncode != 0 or not junction.is_junction():
                self.skipTest("当前 Windows 环境无法创建 junction")
            try:
                with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                    "abaqus_codex.distribution_integration.resource_root",
                    return_value=resources,
                ), patch(
                    "abaqus_codex.distribution_integration.inspect_abaqus",
                    return_value=abaqus_result(usable=False),
                ):
                    with self.assertRaisesRegex(
                        DistributionIntegrationError, "Windows 联接点"
                    ):
                        integration_setup(
                            confirmed=True,
                            codex_home_path=junction,
                            data_root=root / "data",
                        )
            finally:
                if junction.exists() or junction.is_junction():
                    os.rmdir(junction)

    @unittest.skipUnless(
        os.name == "nt" and callable(getattr(Path("."), "is_junction", None)),
        "当前平台不提供 Windows junction 检测",
    )
    def test_nested_junction_in_source_manifest_is_rejected(self):
        """指纹遍历在进入资源内部 junction 前就必须停止。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            outside = root / "outside"
            outside.mkdir()
            (outside / "sentinel.txt").write_text("不读取", encoding="utf-8")
            junction = resources / "skills" / "abaqus-modeling-guide" / "linked-data"
            completed = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed.returncode != 0 or not junction.is_junction():
                self.skipTest("当前 Windows 环境无法创建 junction")
            try:
                with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                    "abaqus_codex.distribution_integration.resource_root",
                    return_value=resources,
                ), patch(
                    "abaqus_codex.distribution_integration.inspect_abaqus",
                    return_value=abaqus_result(usable=False),
                ):
                    with self.assertRaisesRegex(
                        DistributionIntegrationError, "目录中含有.*Windows 联接点"
                    ):
                        integration_setup(
                            confirmed=True,
                            codex_home_path=root / "codex",
                            data_root=root / "data",
                        )
            finally:
                if junction.exists() or junction.is_junction():
                    os.rmdir(junction)

    def test_modified_managed_skill_is_preserved(self):
        """用户改过的已安装 Skill 不能在卸载时被移走或覆盖。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            data = root / "data"
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(confirmed=True, codex_home_path=codex, data_root=data)
                target = codex / "skills" / "abaqus-modeling-guide"
                (target / "user-note.txt").write_text("保留我", encoding="utf-8")
                removed = integration_remove(confirmed=True, data_root=data)

            self.assertEqual(removed["skill"]["status"], "preserved_modified")
            self.assertEqual((target / "user-note.txt").read_text(encoding="utf-8"), "保留我")

    def test_managed_mcp_cleanup_failure_keeps_manifest_and_integration(self):
        """已证明所有权的 MCP 清理失败时必须让卸载器收到非零结果。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            data = root / "data"
            profile = root / "profile"
            with patch.dict(os.environ, {"USERPROFILE": str(profile)}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                skill = codex / "skills" / "abaqus-modeling-guide"
                with patch(
                    "abaqus_codex.mcp_setup.stop_managed_headless_bridge_for_uninstall",
                    return_value={"status": "not_running", "stopped": True},
                ), patch(
                    "abaqus_codex.mcp_setup.remove_managed_codex_registration",
                    return_value={"status": "remove_failed", "removed": False},
                ):
                    with self.assertRaisesRegex(
                        DistributionIntegrationError, "MCP 注册未能移除"
                    ):
                        integration_remove(confirmed=True, data_root=data)

            self.assertTrue((data / MANIFEST_FILENAME).is_file())
            self.assertTrue(skill.is_dir())

    def test_headless_stop_failure_does_not_remove_mcp_registration(self):
        """后台停止失败时不能先造成 Codex 注册的半清理。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            data = root / "data"
            with patch.dict(
                os.environ, {"USERPROFILE": str(root / "profile")}
            ), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ):
                integration_setup(
                    confirmed=True, codex_home_path=codex, data_root=data
                )
                with patch(
                    "abaqus_codex.mcp_setup.stop_managed_headless_bridge_for_uninstall",
                    return_value={
                        "status": "stop_not_confirmed",
                        "stopped": False,
                    },
                ), patch(
                    "abaqus_codex.mcp_setup.remove_managed_codex_registration"
                ) as remove_mock:
                    with self.assertRaisesRegex(
                        DistributionIntegrationError, "尚未确认停止"
                    ):
                        integration_remove(confirmed=True, data_root=data)

            remove_mock.assert_not_called()
            self.assertTrue((data / MANIFEST_FILENAME).is_file())

    def test_manifest_failure_restores_previous_skill(self):
        """清单无法落盘时，不能留下无法管理的替换结果。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            codex = root / "codex"
            target = codex / "skills" / "abaqus-modeling-guide"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("# 原 Skill\n", encoding="utf-8")
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result(usable=False),
            ), patch(
                "abaqus_codex.distribution_integration._write_manifest",
                side_effect=DistributionIntegrationError("测试写入失败"),
            ):
                with self.assertRaises(DistributionIntegrationError):
                    integration_setup(
                        confirmed=True,
                        codex_home_path=codex,
                        data_root=root / "data",
                    )

            self.assertIn("原 Skill", (target / "SKILL.md").read_text(encoding="utf-8"))

    def test_safe_plugin_is_installed_only_for_verified_2021(self):
        """2021 通过两次实时门禁才能写入安全插件。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            profile = root / "profile"
            with patch.dict(os.environ, {"USERPROFILE": str(profile)}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result("2021"),
            ), patch(
                "abaqus_codex.safe_action_setup.inspect_abaqus",
                return_value=abaqus_result("2021"),
            ):
                result = integration_setup(
                    confirmed=True,
                    codex_home_path=root / "codex",
                    data_root=root / "data",
                )

            plugin = profile / "abaqus_plugins" / "safe_material_action"
            self.assertTrue((plugin / "safe_material_action_kernel.py").is_file())
            self.assertTrue(result["plugin"]["eligible"])
            self.assertTrue(result["plugin"]["managed"])

    def test_2022_never_calls_safe_plugin_installer(self):
        """即使 Abaqus 2022 可用，也不写入仅验证过 2021 的插件。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = make_resources(root / "resources")
            with patch.dict(os.environ, {"USERPROFILE": str(root / "profile")}), patch(
                "abaqus_codex.distribution_integration.resource_root",
                return_value=resources,
            ), patch(
                "abaqus_codex.distribution_integration.inspect_abaqus",
                return_value=abaqus_result("2022"),
            ), patch(
                "abaqus_codex.distribution_integration.setup_safe_action_plugin"
            ) as setup_mock:
                result = integration_setup(
                    confirmed=True,
                    codex_home_path=root / "codex",
                    data_root=root / "data",
                )

            setup_mock.assert_not_called()
            self.assertFalse(result["plugin"]["eligible"])
            self.assertFalse((root / "profile" / "abaqus_plugins").exists())

    def test_source_target_overlap_is_rejected(self):
        """资源和目标互为祖先/子孙时，必须在复制前停止。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "file.txt").write_text("data", encoding="utf-8")
            with self.assertRaisesRegex(DistributionIntegrationError, "重叠"):
                _install_directory(
                    source,
                    source / "nested-target",
                    recovery_root=root / "recovery" / "skill",
                    dry_run=False,
                )
            self.assertFalse((source / "nested-target").exists())

    def test_cross_volume_stops_before_copy(self):
        """无法原子移入恢复区时，不得先生成 .installing 副本。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "file.txt").write_text("data", encoding="utf-8")
            target = root / "active" / "managed"
            with patch(
                "abaqus_codex.distribution_integration._same_storage_volume",
                return_value=False,
            ), patch(
                "abaqus_codex.distribution_integration.shutil.copytree"
            ) as copy_mock:
                with self.assertRaisesRegex(DistributionIntegrationError, "同一磁盘"):
                    _install_directory(
                        source,
                        target,
                        recovery_root=root / "data" / "recovery" / "skill",
                        dry_run=False,
                    )
            copy_mock.assert_not_called()
            self.assertEqual(list(target.parent.glob(".managed.installing-*")), [])

    def test_recovery_name_collision_stays_in_recovery_root(self):
        """同一秒的恢复名冲突也不能回落到活跃扫描目录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovery = root / "data" / "recovery" / "skill"
            recovery.mkdir(parents=True)
            target = root / "codex" / "skills" / "guide"
            with patch(
                "abaqus_codex.distribution_integration._timestamp",
                return_value="20260101-000000",
            ):
                first = _next_recovery_path(recovery, target, "backup")
                first.mkdir()
                second = _next_recovery_path(recovery, target, "backup")
            self.assertEqual(second.parent, recovery)
            self.assertNotEqual(second.parent, target.parent)
            self.assertTrue(second.name.endswith("-001"))


if __name__ == "__main__":
    unittest.main()
