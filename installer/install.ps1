[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Install", "Repair")]
    [string]$Mode = "Install",
    [switch]$InstallAbqpy,
    [switch]$InstallMcp,
    [switch]$NoDesktopShortcut,
    [switch]$Yes,
    [string]$InstallRoot,
    [string]$UserProfileRoot,
    [string]$CodexHome
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Stop-Setup([string]$Message) {
    throw "Abaqus Codex Assistant setup: $Message"
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "command failed with exit code ${LASTEXITCODE}: $FilePath"
    }
}

function Find-Python {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & $py.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
        if ($LASTEXITCODE -eq 0) {
            return @{ File = $py.Source; Prefix = @("-3") }
        }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
        if ($LASTEXITCODE -eq 0) {
            return @{ File = $python.Source; Prefix = @() }
        }
    }
    Stop-Setup "Python 3.10 or newer was not found. Install Python, then run setup again."
}

function Copy-Payload([string]$SourceRoot, [string]$DestinationRoot) {
    $directories = @("src", "configs", "skills", "abaqus_plugins", "docs")
    $files = @(
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "NOTICE.md",
        "AUTHORS.md",
        "SECURITY.md",
        "CHANGELOG.md"
    )

    foreach ($name in $directories) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot $name) -Destination $DestinationRoot -Recurse
    }
    foreach ($name in $files) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot $name) -Destination $DestinationRoot
    }
    Copy-Item -LiteralPath (Join-Path $SourceRoot "installer") -Destination $DestinationRoot -Recurse
}

function Backup-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$Path.backup-$stamp"
    $index = 0
    while (Test-Path -LiteralPath $backup) {
        $index += 1
        $backup = "$Path.backup-$stamp-$index"
    }
    Move-Item -LiteralPath $Path -Destination $backup
    return $backup
}

if ($env:OS -ne "Windows_NT") {
    Stop-Setup "this installer supports Windows only."
}

$sourceRoot = Split-Path -Parent $PSScriptRoot
foreach ($required in @("pyproject.toml", "src\abaqus_codex", "skills\abaqus-modeling-guide", "abaqus_plugins\safe_material_action")) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $required))) {
        Stop-Setup "release payload is incomplete: $required"
    }
}

if ([string]::IsNullOrWhiteSpace($UserProfileRoot)) {
    $UserProfileRoot = $env:USERPROFILE
}
if ([string]::IsNullOrWhiteSpace($UserProfileRoot)) {
    Stop-Setup "USERPROFILE is not available."
}
$env:USERPROFILE = $UserProfileRoot
if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        $CodexHome = $env:CODEX_HOME
    }
    else {
        $CodexHome = Join-Path $UserProfileRoot ".codex"
    }
}
$CodexHome = [System.IO.Path]::GetFullPath($CodexHome)
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        Stop-Setup "LOCALAPPDATA is not available."
    }
    $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\AbaqusCodexAssistant"
}

$python = Find-Python
$pythonArgs = @($python.Prefix)
$pythonArgs += @("-c", "import sys; print(sys.version.split()[0])")
Invoke-Checked $python.File $pythonArgs

if ((Test-Path -LiteralPath $InstallRoot) -and $Mode -eq "Install") {
    if (-not $WhatIfPreference) {
        Stop-Setup "the target already exists. Run again with -Mode Repair."
    }
    Write-Warning "The target already exists; an actual update requires -Mode Repair."
}

Write-Host ""
Write-Host "Install plan"
Write-Host "  Application: $InstallRoot"
Write-Host "  Codex skill: $(Join-Path $CodexHome 'skills\abaqus-modeling-guide')"
Write-Host "  Abaqus detection: after core installation"
Write-Host "  abqpy download: $([bool]$InstallAbqpy)"
Write-Host "  MCP download and registration: $([bool]$InstallMcp)"
Write-Host "No Abaqus files, passwords, cookies, API keys, or Codex credentials will be copied."

if (-not $Yes -and -not $WhatIfPreference) {
    $answer = Read-Host "Type INSTALL to continue"
    if ($answer -cne "INSTALL") {
        Stop-Setup "cancelled by user."
    }
}

if (-not $PSCmdlet.ShouldProcess($InstallRoot, "$Mode Abaqus Codex Assistant")) {
    return
}

$installParent = Split-Path -Parent $InstallRoot
New-Item -ItemType Directory -Path $installParent -Force | Out-Null
$staging = Join-Path $installParent (".AbaqusCodexAssistant.installing-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null

$applicationBackup = $null
$applicationActivated = $false
try {
    Copy-Payload $sourceRoot $staging

    $launcher = @"
@echo off
setlocal
set "APP_DIR=%~dp0"
"%APP_DIR%.venv\Scripts\python.exe" -m abaqus_codex assistant
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" pause
endlocal & exit /b %APP_EXIT_CODE%
"@
    [System.IO.File]::WriteAllText((Join-Path $staging "Start-Abaqus-Codex-Assistant.cmd"), $launcher.Replace("`n", "`r`n"), [System.Text.Encoding]::ASCII)

    if (Test-Path -LiteralPath $InstallRoot) {
        $applicationBackup = Backup-Directory $InstallRoot
    }
    Move-Item -LiteralPath $staging -Destination $InstallRoot
    $applicationActivated = $true

    # Create the environment at its final path so editable metadata stays valid.
    $venvRoot = Join-Path $InstallRoot ".venv"
    $venvArgs = @($python.Prefix)
    $venvArgs += @("-m", "venv", $venvRoot)
    Invoke-Checked $python.File $venvArgs

    $venvPython = Join-Path $venvRoot "Scripts\python.exe"
    $sitePackages = Join-Path $venvRoot "Lib\site-packages"
    if (-not (Test-Path -LiteralPath $sitePackages -PathType Container)) {
        Stop-Setup "the private Python site-packages directory was not created."
    }
    $pthPath = Join-Path $sitePackages "abaqus_codex_assistant.pth"
    $sourcePath = Join-Path $InstallRoot "src"
    [System.IO.File]::WriteAllText(
        $pthPath,
        $sourcePath + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
}
catch {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
    if ($applicationActivated -and (Test-Path -LiteralPath $InstallRoot)) {
        $failedPath = "$InstallRoot.failed-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -LiteralPath $InstallRoot -Destination $failedPath
    }
    if ($null -ne $applicationBackup -and -not (Test-Path -LiteralPath $InstallRoot)) {
        Move-Item -LiteralPath $applicationBackup -Destination $InstallRoot
    }
    throw
}

$installedPython = Join-Path $InstallRoot ".venv\Scripts\python.exe"

# Keep the Skill replaceable so it can be upgraded independently.
$skillSource = Join-Path $InstallRoot "skills\abaqus-modeling-guide"
$skillTarget = Join-Path $CodexHome "skills\abaqus-modeling-guide"
New-Item -ItemType Directory -Path (Split-Path -Parent $skillTarget) -Force | Out-Null
$skillBackup = Backup-Directory $skillTarget
Copy-Item -LiteralPath $skillSource -Destination $skillTarget -Recurse

# Detect Abaqus only after the core app and Skill are installed.
$abaqusCheck = $null
$preflightOutput = & $installedPython -m abaqus_codex install-preflight --json
try {
    $abaqusCheck = ($preflightOutput -join "`n") | ConvertFrom-Json
}
catch {
    Write-Warning "Abaqus detection could not be read. The core installation will be kept."
    $abaqusCheck = [pscustomobject]@{
        detected = $false
        usable = $false
        version = $null
        safe_plugin_supported = $false
    }
}
$abaqusDetected = [bool]$abaqusCheck.detected
$installSafePlugin = [bool]$abaqusCheck.safe_plugin_supported
$detectedAbaqusVersion = [string]$abaqusCheck.version
if ([string]::IsNullOrWhiteSpace($detectedAbaqusVersion)) {
    $detectedAbaqusVersion = "not-detected"
}

# Install the model-changing plugin only for its verified Abaqus version.
$pluginInstalled = $false
$pluginSetupStatus = "not-supported"
if ($installSafePlugin) {
    try {
        Invoke-Checked $installedPython @("-m", "abaqus_codex", "assistant-setup", "--yes")
        $pluginInstalled = $true
        $pluginSetupStatus = "completed"
    }
    catch {
        $pluginSetupStatus = "failed"
        Write-Warning "The core app and Skill were installed, but the Abaqus safe plugin failed: $($_.Exception.Message)"
    }
}

$abqpySetupStatus = "not-requested"
if ($InstallAbqpy) {
    try {
        Invoke-Checked $installedPython @("-m", "abaqus_codex", "abqpy-setup", "--yes")
        $abqpySetupStatus = "completed"
    }
    catch {
        $abqpySetupStatus = "failed"
        Write-Warning "The core app and Skill were installed, but abqpy setup failed: $($_.Exception.Message)"
    }
}
$mcpSetupStatus = "not-requested"
if ($InstallMcp) {
    try {
        Invoke-Checked $installedPython @("-m", "abaqus_codex", "mcp-setup", "--yes")
        $mcpSetupStatus = "completed"
    }
    catch {
        $mcpSetupStatus = "failed"
        Write-Warning "The core app and Skill were installed, but MCP setup failed: $($_.Exception.Message)"
    }
}

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $NoDesktopShortcut -and -not [string]::IsNullOrWhiteSpace($desktop)) {
    $shortcutPath = Join-Path $desktop "Abaqus Codex Assistant.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $launcherPath = Join-Path $InstallRoot "Start-Abaqus-Codex-Assistant.cmd"
    $shortcut.TargetPath = $env:ComSpec
    $shortcut.Arguments = '/d /c ""{0}""' -f $launcherPath
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Description = "Abaqus Chinese modeling assistant"
    $shortcut.Save()
}

$manifest = @{
    product = "abaqus-codex-assistant"
    installed_at = (Get-Date).ToString("o")
    install_root = $InstallRoot
    user_profile_root = $UserProfileRoot
    codex_home = $CodexHome
    skill_target = $skillTarget
    plugin_target = (Join-Path $UserProfileRoot "abaqus_plugins\safe_material_action")
    plugin_installed = $pluginInstalled
    plugin_setup = $pluginSetupStatus
    abqpy_setup = $abqpySetupStatus
    mcp_setup = $mcpSetupStatus
    skill_backup = $skillBackup
    application_backup = $applicationBackup
    detected_abaqus_version = $detectedAbaqusVersion
    abaqus_detected = $abaqusDetected
    abaqus_support = $(if ($pluginInstalled) { "2021-verified" } else { "core-only" })
    credentials_copied = $false
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $InstallRoot "install-manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "Installation completed."
if ($pluginInstalled) {
    Write-Host "Restart Abaqus/CAE and Codex before the first real-model test."
}
else {
    if ($abaqusDetected) {
        Write-Host "Abaqus $detectedAbaqusVersion was detected after installation. The version-specific model modification plugin was skipped."
    }
    else {
        Write-Host "The core app and Skill are installed. Abaqus was not detected; run Environment Check after Abaqus is installed or configured."
    }
}
if ($pluginSetupStatus -eq "failed" -or $abqpySetupStatus -eq "failed" -or $mcpSetupStatus -eq "failed") {
    Write-Host "One or more optional components failed. The managed core installation was kept."
    Write-Host "Correct the reported issue, then run this release again with -Mode Repair and the required optional switches."
}
Write-Host "Run the desktop shortcut, then open Environment Check."
Invoke-Checked $installedPython @("-m", "abaqus_codex", "onboard")
