# -*- coding: utf-8 -*-
"""检查对外分发脚本的关键安全和完整性约束。"""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "installer" / "install.ps1"
UNINSTALLER = PROJECT_ROOT / "installer" / "uninstall.ps1"


class DistributionInstallerTests(unittest.TestCase):
    """防止发布脚本退化为本机路径、静默联网或宽泛删除。"""

    def test_installer_has_no_maintainer_specific_absolute_path(self):
        """安装器必须从 Release 自身定位资源，不能依赖维护者电脑。"""

        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn(r"C:\Users\zzj", text)
        self.assertIn("$PSScriptRoot", text)
        self.assertIn("LOCALAPPDATA", text)
        self.assertIn(r"Programs\AbaqusCodexAssistant", text)

    def test_program_files_do_not_replace_runtime_data_directory(self):
        """程序目录必须与历史、快照和动作队列的数据目录分离。"""

        installer = INSTALLER.read_text(encoding="utf-8")
        uninstaller = UNINSTALLER.read_text(encoding="utf-8")
        direct_data_target = 'Join-Path $env:LOCALAPPDATA "AbaqusCodexAssistant"'
        self.assertNotIn(direct_data_target, installer)
        self.assertNotIn(direct_data_target, uninstaller)
        self.assertIn(r'"Programs\AbaqusCodexAssistant"', installer)
        self.assertIn(r'"Programs\AbaqusCodexAssistant"', uninstaller)

    def test_powershell_entrypoints_are_ascii_for_windows_51(self):
        """避免 Windows PowerShell 5.1 把无 BOM 中文脚本解析成乱码。"""

        for path in (INSTALLER, UNINSTALLER):
            with self.subTest(path=path.name):
                content = path.read_bytes()
                self.assertTrue(content)
                self.assertTrue(all(byte < 128 for byte in content))

    def test_network_components_require_explicit_switches(self):
        """abqpy 和 MCP 只有用户主动选择时才允许安装。"""

        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("[switch]$InstallAbqpy", text)
        self.assertIn("[switch]$InstallMcp", text)
        self.assertIn("if ($InstallAbqpy)", text)
        self.assertIn("if ($InstallMcp)", text)
        self.assertIn('Read-Host "Type INSTALL to continue"', text)
        self.assertNotIn('"pip", "install"', text)

    def test_shortcut_uses_stable_system_command_target(self):
        """快捷方式目标不能被沙箱或用户目录路径映射改写。"""

        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("$shortcut.TargetPath = $env:ComSpec", text)
        self.assertIn("$shortcut.Arguments", text)
        self.assertNotIn(
            '$shortcut.TargetPath = Join-Path $InstallRoot',
            text,
        )

    def test_installer_separates_core_install_from_safe_plugin(self):
        """先装核心组件，随后才检测 Abaqus 并决定是否安装安全插件。"""

        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(r".codex\skills\abaqus-modeling-guide", text)
        self.assertIn("install-preflight", text)
        self.assertIn("$installSafePlugin", text)
        self.assertIn("if ($installSafePlugin)", text)
        self.assertIn("assistant-setup", text)
        self.assertIn("--yes", text)
        self.assertNotIn('"assistant-setup", "--dry-run"', text)
        self.assertIn("plugin_installed = $pluginInstalled", text)
        self.assertIn("Abaqus detection: after core installation", text)
        self.assertLess(
            text.index('$installedPython = Join-Path $InstallRoot'),
            text.index("install-preflight --json"),
        )
        self.assertNotIn("Abaqus was not detected. Install Abaqus", text)

    def test_uninstaller_skips_plugin_not_owned_by_install(self):
        """核心模式未安装插件时，卸载器不得移动用户原有插件。"""

        text = UNINSTALLER.read_text(encoding="utf-8")
        self.assertIn('Properties["plugin_installed"]', text)
        self.assertIn("if ($pluginInstalled)", text)

    def test_credentials_are_not_embedded_or_copied(self):
        """发布脚本不能尝试搬运 Codex 或论文数据库会话。"""

        text = INSTALLER.read_text(encoding="utf-8").lower()
        forbidden = (
            "openai_api_key=",
            "authorization: bearer",
            "cookie.sqlite",
            "cookies.json",
            "credentials.json",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)
        self.assertIn("credentials_copied = $false", text)

    def test_uninstaller_requires_owned_manifest(self):
        """卸载器只能处理带本项目身份清单的精确目录。"""

        text = UNINSTALLER.read_text(encoding="utf-8")
        self.assertIn("install-manifest.json", text)
        self.assertIn('product -ne "abaqus-codex-assistant"', text)
        self.assertIn('Read-Host "Type UNINSTALL to continue"', text)
        self.assertNotIn("Remove-Item $env:USERPROFILE", text)


if __name__ == "__main__":
    unittest.main()
