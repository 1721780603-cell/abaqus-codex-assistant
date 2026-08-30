[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Yes,
    [switch]$KeepRecoveryCopy,
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is not available."
    }
    $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\AbaqusCodexAssistant"
}

$manifestPath = Join-Path $InstallRoot "install-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Managed installation manifest was not found. No files were removed."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.product -ne "abaqus-codex-assistant") {
    throw "Installation manifest is not recognized. No files were removed."
}
$recordedRoot = [System.IO.Path]::GetFullPath([string]$manifest.install_root)
$actualRoot = [System.IO.Path]::GetFullPath($InstallRoot)
if ($recordedRoot -ne $actualRoot) {
    throw "Installation root does not match its manifest. No files were removed."
}
$userProfileRoot = [System.IO.Path]::GetFullPath([string]$manifest.user_profile_root)
$codexHome = Join-Path $userProfileRoot ".codex"
if ($null -ne $manifest.PSObject.Properties["codex_home"] -and -not [string]::IsNullOrWhiteSpace([string]$manifest.codex_home)) {
    $codexHome = [System.IO.Path]::GetFullPath([string]$manifest.codex_home)
}
$expectedSkillTarget = Join-Path $codexHome "skills\abaqus-modeling-guide"
$expectedPluginTarget = Join-Path $userProfileRoot "abaqus_plugins\safe_material_action"
if ([string]$manifest.skill_target -ne $expectedSkillTarget -or [string]$manifest.plugin_target -ne $expectedPluginTarget) {
    throw "Managed component paths do not match the manifest owner. No files were removed."
}
$pluginInstalled = $true
if ($null -ne $manifest.PSObject.Properties["plugin_installed"]) {
    $pluginInstalled = [bool]$manifest.plugin_installed
}

Write-Host "Uninstall plan"
Write-Host "  Application: $InstallRoot"
Write-Host "  Codex skill: $($manifest.skill_target)"
Write-Host "  Abaqus plugin installed by setup: $pluginInstalled"
Write-Host "Abaqus, Codex, user models, CAE files, ODB files, credentials, and old backups are outside this removal scope."

if (-not $Yes) {
    $answer = Read-Host "Type UNINSTALL to continue"
    if ($answer -cne "UNINSTALL") {
        throw "Uninstall cancelled by user."
    }
}

if (-not $PSCmdlet.ShouldProcess($InstallRoot, "Uninstall Abaqus Codex Assistant")) {
    return
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$skillTarget = $expectedSkillTarget
$pluginTarget = $expectedPluginTarget
$managedTargets = @($skillTarget)
if ($pluginInstalled) {
    $managedTargets += $pluginTarget
}
foreach ($target in $managedTargets) {
    if (-not [string]::IsNullOrWhiteSpace($target) -and (Test-Path -LiteralPath $target)) {
        Move-Item -LiteralPath $target -Destination "$target.uninstalled-$stamp"
    }
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Abaqus Codex Assistant.lnk"
if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
    Remove-Item -LiteralPath $shortcutPath -Force
}

Set-Location $env:TEMP
if ($KeepRecoveryCopy) {
    Move-Item -LiteralPath $InstallRoot -Destination "$InstallRoot.uninstalled-$stamp"
    Write-Host "Uninstall completed. A recoverable application copy was retained."
}
else {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
    Write-Host "Uninstall completed. Skill and Abaqus plugin were renamed as recoverable copies."
}
