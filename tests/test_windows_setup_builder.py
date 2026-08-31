# -*- coding: utf-8 -*-
"""Offline checks for the self-contained Windows Setup build definition."""

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "installer" / "build_windows_setup.ps1"
INNO_SCRIPT = PROJECT_ROOT / "installer" / "windows_setup.iss"


class WindowsSetupBuilderTests(unittest.TestCase):
    """Keep the public Setup reproducible, offline at install time, and scoped."""

    def test_builder_is_powershell_51_ascii_and_accepts_local_tools(self):
        content = BUILD_SCRIPT.read_bytes()
        self.assertTrue(content)
        self.assertTrue(all(byte < 128 for byte in content))
        text = content.decode("ascii")
        self.assertIn("[string]$PythonArchive", text)
        self.assertIn("[string]$InnoCompiler", text)
        self.assertIn("Set-StrictMode -Version Latest", text)

    def test_builder_pins_and_verifies_official_python_runtime(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn("python-3.12.10-amd64.zip", text)
        self.assertIn("https://www.python.org/ftp/python/", text)
        self.assertIn(
            "8649692DE846C56A7189D6DAE5C322AB20DEB1B5908B6F39426B62A36F39415D",
            text,
        )
        self.assertIn("Get-FileHash", text)
        self.assertIn("SHA256 mismatch", text)

    def test_builder_pins_and_verifies_inno_compiler(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn(
            "0A8757031B33777E4C9CBFFEE40F11A5062B36D25CBE144C1DB73B6102B80AD7",
            text,
        )
        self.assertIn("Get-AuthenticodeSignature", text)
        self.assertIn("Pyrsys B.V.", text)
        self.assertIn("ISCC.exe SHA256 mismatch", text)

    def test_builder_derives_and_cross_checks_public_version(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn("$PackageVersion", text)
        self.assertIn("the expected PEP 440 alpha form", text)
        self.assertIn("does not match pyproject.toml", text)
        self.assertIn("CITATION.cff does not match", text)
        self.assertIn("/DReleaseSerial=$ReleaseSerial", text)

    def test_builder_stages_full_runtime_project_and_hash(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn('Join-Path $runtimeRoot "Lib\\site-packages"', text)
        self.assertIn('Join-Path $stagingRoot "AbaqusCodexAssistant.exe"', text)
        self.assertIn('installer\\windows_launcher.cs', text)
        self.assertIn("Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe", text)
        self.assertIn("/target:winexe", text)
        self.assertIn("expected valid Microsoft signature", text)
        self.assertNotIn(
            'Copy-Item -LiteralPath (Join-Path $runtimeRoot "pythonw.exe")',
            text,
        )
        self.assertIn('"configs", "skills", "abaqus_plugins", "docs"', text)
        self.assertIn('"LICENSE"', text)
        self.assertIn('Join-Path $runtimeRoot "Doc"', text)
        self.assertIn('Filter "*.exe"', text)
        self.assertIn('"$($setup.FullName).sha256"', text)

    def test_builder_exports_only_clean_git_tracked_release_files(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn("status --porcelain --untracked-files=normal", text)
        self.assertIn("the release worktree is not clean", text)
        self.assertIn("archive --format=zip", text)
        self.assertIn("forbidden private or Abaqus file", text)
        self.assertIn('"user_profile.json", "local_ai_rectangle.json"', text)
        self.assertNotIn('Join-Path $projectRoot "src\\abaqus_codex"', text)

    def test_builder_only_recursively_cleans_guarded_build_children(self):
        text = BUILD_SCRIPT.read_text(encoding="ascii")
        self.assertIn("function Assert-BuildChild", text)
        self.assertIn("function Reset-BuildDirectory", text)
        self.assertIn("refusing to modify a path outside", text)
        self.assertNotIn("Remove-Item -LiteralPath $projectRoot", text)
        self.assertNotIn("Remove-Item -LiteralPath $buildRoot", text)

    def test_inno_installs_per_user_and_launches_bundled_runtime(self):
        text = INNO_SCRIPT.read_text(encoding="ascii")
        self.assertIn(r"DefaultDirName={localappdata}\Programs\AbaqusCodexAssistant", text)
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn("ArchitecturesAllowed=x64compatible", text)
        self.assertIn(
            r'Filename: "{app}\AbaqusCodexAssistant.exe"', text
        )
        self.assertNotIn(
            r'Filename: "{app}\runtime\pythonw.exe"', text
        )
        self.assertNotIn(
            r'Parameters: "-I -m abaqus_codex assistant"', text
        )
        self.assertIn("function InitializeSetup", text)
        self.assertIn("A newer Abaqus Codex Assistant is already installed", text)
        self.assertNotIn("{userprofile}", text)
        self.assertIn("GetEnv('USERPROFILE')", text)

    def test_named_application_is_a_real_fixed_command_launcher(self):
        launcher = (
            PROJECT_ROOT / "installer" / "windows_launcher.cs"
        ).read_text(encoding="ascii")
        self.assertIn('"runtime",', launcher)
        self.assertIn('"pythonw.exe"', launcher)
        self.assertIn('start.Arguments = "-I -m abaqus_codex assistant"', launcher)
        self.assertIn("Process.Start(start)", launcher)

    def test_inno_runs_owned_integration_setup_and_removal(self):
        text = INNO_SCRIPT.read_text(encoding="ascii")
        self.assertIn("function RunIntegration", text)
        self.assertIn("'-I ' + Arguments", text)
        self.assertIn("integration-setup --yes", text)
        self.assertIn('--data-root "', text)
        self.assertIn(r"{localappdata}\AbaqusCodexAssistant", text)
        self.assertIn("RaiseException", text)
        self.assertIn("procedure CurUninstallStepChanged", text)
        self.assertIn("integration-remove --yes", text)
        self.assertIn("MB_ABORTRETRYIGNORE", text)
        self.assertIn("if UninstallSilent then", text)
        self.assertNotIn("[UninstallRun]", text)
        self.assertNotIn("Invoke-WebRequest", text)
        self.assertNotIn("DownloadTemporaryFile", text)

    def test_inno_rejects_application_and_user_integration_path_overlap(self):
        text = INNO_SCRIPT.read_text(encoding="ascii")
        self.assertIn("function PathsOverlap", text)
        self.assertIn("function NextButtonClick", text)
        self.assertIn("WizardDirValue", text)
        self.assertIn("skills\\abaqus-modeling-guide", text)
        self.assertIn("abaqus_plugins\\safe_material_action", text)


if __name__ == "__main__":
    unittest.main()
