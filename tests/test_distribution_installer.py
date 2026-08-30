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

    def test_installer_distributes_skill_and_safe_plugin(self):
        """统一入口必须同时包含 Skill 和已验证的安全插件。"""

        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn(r".codex\skills\abaqus-modeling-guide", text)
        self.assertIn("assistant-setup", text)
        self.assertIn("--dry-run", text)
        self.assertIn("--yes", text)

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
