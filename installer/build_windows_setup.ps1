[CmdletBinding()]
param(
    [string]$PythonArchive,
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PythonVersion = "3.12.10"
$PythonArchiveName = "python-3.12.10-amd64.zip"
$PythonArchiveUri = "https://www.python.org/ftp/python/$PythonVersion/$PythonArchiveName"
$PythonArchiveSha256 = "8649692DE846C56A7189D6DAE5C322AB20DEB1B5908B6F39426B62A36F39415D"
$InnoCompilerSha256 = "0A8757031B33777E4C9CBFFEE40F11A5062B36D25CBE144C1DB73B6102B80AD7"
$InnoSignerSubjectNeedle = "Pyrsys B.V."

function Stop-Build([string]$Message) {
    throw "Windows setup build: $Message"
}

function Get-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path)
}

$projectRoot = Get-FullPath (Split-Path -Parent $PSScriptRoot)
$buildRoot = Get-FullPath (Join-Path $projectRoot "build\windows-setup")
$downloadRoot = Get-FullPath (Join-Path $buildRoot "downloads")
$sourceRoot = Get-FullPath (Join-Path $buildRoot "source")
$sourceArchive = Get-FullPath (Join-Path $buildRoot "source.zip")
$stagingRoot = Get-FullPath (Join-Path $buildRoot "staging")
$runtimeRoot = Get-FullPath (Join-Path $stagingRoot "runtime")
$outputRoot = Get-FullPath (Join-Path $buildRoot "output")
$innoScript = Get-FullPath (Join-Path $PSScriptRoot "windows_setup.iss")

$pyprojectText = [System.IO.File]::ReadAllText((Join-Path $projectRoot "pyproject.toml"))
$packageMatch = [regex]::Match(
    $pyprojectText,
    '(?m)^version\s*=\s*"(?<version>[^"]+)"\s*$'
)
if (-not $packageMatch.Success) {
    Stop-Build "pyproject.toml does not contain one package version."
}
$PackageVersion = $packageMatch.Groups["version"].Value
$pep440Match = [regex]::Match(
    $PackageVersion,
    '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)a(?<alpha>\d+)$'
)
if (-not $pep440Match.Success) {
    Stop-Build "the package version is not the expected PEP 440 alpha form: $PackageVersion"
}
$AppVersion = "{0}.{1}.{2}-alpha" -f @(
    $pep440Match.Groups["major"].Value,
    $pep440Match.Groups["minor"].Value,
    $pep440Match.Groups["patch"].Value
)
$ReleaseSerial = "{0:D4}{1:D4}{2:D4}1{3:D4}" -f @(
    [int]$pep440Match.Groups["major"].Value,
    [int]$pep440Match.Groups["minor"].Value,
    [int]$pep440Match.Groups["patch"].Value,
    [int]$pep440Match.Groups["alpha"].Value
)
$packageInitText = [System.IO.File]::ReadAllText(
    (Join-Path $projectRoot "src\abaqus_codex\__init__.py")
)
$citationText = [System.IO.File]::ReadAllText((Join-Path $projectRoot "CITATION.cff"))
if ($packageInitText -notmatch ('__version__\s*=\s*"' + [regex]::Escape($PackageVersion) + '"')) {
    Stop-Build "src/abaqus_codex/__init__.py does not match pyproject.toml."
}
if ($citationText -notmatch ('(?m)^version:\s*"' + [regex]::Escape($AppVersion) + '"\s*$')) {
    Stop-Build "CITATION.cff does not match the normalized public version $AppVersion."
}
$SetupBaseName = "AbaqusCodexAssistant-Setup-$AppVersion-x64"

function Assert-BuildChild([string]$Path) {
    $full = Get-FullPath $Path
    $prefix = $buildRoot.TrimEnd("\") + "\"
    if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Build "refusing to modify a path outside the dedicated build directory: $full"
    }
    return $full
}

function Reset-BuildDirectory([string]$Path) {
    $safePath = Assert-BuildChild $Path
    if (Test-Path -LiteralPath $safePath) {
        Remove-Item -LiteralPath $safePath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $safePath -Force | Out-Null
}

function Copy-RequiredDirectory([string]$Name) {
    $source = Join-Path $sourceRoot $Name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        Stop-Build "release payload is missing directory: $Name"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stagingRoot $Name) -Recurse
}

function Copy-RequiredFile([string]$Name) {
    $source = Join-Path $sourceRoot $Name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        Stop-Build "release payload is missing file: $Name"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $stagingRoot $Name)
}

if ($env:OS -ne "Windows_NT") {
    Stop-Build "this build script supports Windows only."
}
if (-not (Test-Path -LiteralPath $innoScript -PathType Leaf)) {
    Stop-Build "Inno Setup source was not found: $innoScript"
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($PythonArchive)) {
    $PythonArchive = Join-Path $downloadRoot $PythonArchiveName
    if (-not (Test-Path -LiteralPath $PythonArchive -PathType Leaf)) {
        Write-Host "Downloading the official Python $PythonVersion x64 runtime for the maintainer build..."
        Invoke-WebRequest -Uri $PythonArchiveUri -OutFile $PythonArchive -UseBasicParsing
    }
}
elseif (-not (Test-Path -LiteralPath $PythonArchive -PathType Leaf)) {
    Stop-Build "Python archive was not found: $PythonArchive"
}
$PythonArchive = Get-FullPath (Resolve-Path -LiteralPath $PythonArchive).Path
$actualPythonHash = (Get-FileHash -LiteralPath $PythonArchive -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualPythonHash -ne $PythonArchiveSha256) {
    Stop-Build "Python archive SHA256 mismatch. Expected $PythonArchiveSha256 but received $actualPythonHash."
}

if ([string]::IsNullOrWhiteSpace($InnoCompiler)) {
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:INNO_ISCC)) {
        $candidates += $env:INNO_ISCC
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $InnoCompiler = $candidate
            break
        }
    }
}
if ([string]::IsNullOrWhiteSpace($InnoCompiler) -or -not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
    Stop-Build "ISCC.exe was not found. Install Inno Setup 6 or pass -InnoCompiler."
}
$InnoCompiler = Get-FullPath (Resolve-Path -LiteralPath $InnoCompiler).Path
$actualInnoHash = (Get-FileHash -LiteralPath $InnoCompiler -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualInnoHash -ne $InnoCompilerSha256) {
    Stop-Build "ISCC.exe SHA256 mismatch. Expected $InnoCompilerSha256 but received $actualInnoHash."
}
$innoSignature = Get-AuthenticodeSignature -LiteralPath $InnoCompiler
$innoSigner = ""
if ($null -ne $innoSignature.SignerCertificate) {
    $innoSigner = $innoSignature.SignerCertificate.Subject
}
if (
    $innoSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
    $innoSigner.IndexOf($InnoSignerSubjectNeedle, [System.StringComparison]::OrdinalIgnoreCase) -lt 0
) {
    Stop-Build "ISCC.exe does not have the expected valid Pyrsys B.V. signature."
}

Reset-BuildDirectory $stagingRoot
Reset-BuildDirectory $outputRoot
Reset-BuildDirectory $sourceRoot

$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $gitCommand) {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
}
if ($null -eq $gitCommand) {
    Stop-Build "Git is required on the maintainer build machine to export tracked release files."
}
$gitStatus = @(& $gitCommand.Source -C $projectRoot status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) {
    Stop-Build "Git could not inspect the release worktree."
}
if ($gitStatus.Count -ne 0) {
    Stop-Build "the release worktree is not clean; commit or remove local files before packaging."
}
$safeSourceArchive = Assert-BuildChild $sourceArchive
if (Test-Path -LiteralPath $safeSourceArchive) {
    Remove-Item -LiteralPath $safeSourceArchive -Force
}
& $gitCommand.Source -C $projectRoot archive --format=zip --output=$safeSourceArchive HEAD
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $safeSourceArchive -PathType Leaf)) {
    Stop-Build "Git could not create the tracked source archive."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($safeSourceArchive, $sourceRoot)
[System.IO.Compression.ZipFile]::ExtractToDirectory($PythonArchive, $runtimeRoot)

foreach ($requiredRuntimePath in @("python.exe", "pythonw.exe", "Lib", "DLLs")) {
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot $requiredRuntimePath))) {
        Stop-Build "Python archive is not the required full x64 distribution: $requiredRuntimePath"
    }
}

# Build a real desktop launcher. Directly double-clicking this EXE always
# starts the fixed private runtime command; it is not a renamed pythonw.exe.
$launcherSource = Join-Path $sourceRoot "installer\windows_launcher.cs"
if (-not (Test-Path -LiteralPath $launcherSource -PathType Leaf)) {
    Stop-Build "release payload is missing installer/windows_launcher.cs."
}
$appExecutable = Join-Path $stagingRoot "AbaqusCodexAssistant.exe"
$csharpCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$csharpCompiler = $null
foreach ($candidate in $csharpCandidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $csharpCompiler = $candidate
        break
    }
}
if ($null -eq $csharpCompiler) {
    Stop-Build "the signed Microsoft .NET Framework C# compiler was not found."
}
$csharpSignature = Get-AuthenticodeSignature -LiteralPath $csharpCompiler
$csharpSigner = ""
if ($null -ne $csharpSignature.SignerCertificate) {
    $csharpSigner = $csharpSignature.SignerCertificate.Subject
}
if (
    $csharpSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
    $csharpSigner.IndexOf("Microsoft", [System.StringComparison]::OrdinalIgnoreCase) -lt 0
) {
    Stop-Build "the C# compiler does not have the expected valid Microsoft signature."
}
& $csharpCompiler `
    /nologo `
    /target:winexe `
    /optimize+ `
    "/out:$appExecutable" `
    /reference:System.dll `
    /reference:System.Windows.Forms.dll `
    $launcherSource
if ($LASTEXITCODE -ne 0) {
    Stop-Build "the desktop launcher failed to compile."
}
if (-not (Test-Path -LiteralPath $appExecutable -PathType Leaf)) {
    Stop-Build "the desktop launcher executable was not created."
}

$pythonDocs = Join-Path $runtimeRoot "Doc"
if (Test-Path -LiteralPath $pythonDocs) {
    $safePythonDocs = Assert-BuildChild $pythonDocs
    Remove-Item -LiteralPath $safePythonDocs -Recurse -Force
}

$sitePackages = Join-Path $runtimeRoot "Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null
$packageSource = Join-Path $sourceRoot "src\abaqus_codex"
if (-not (Test-Path -LiteralPath $packageSource -PathType Container)) {
    Stop-Build "release payload is missing src\abaqus_codex."
}
Copy-Item -LiteralPath $packageSource -Destination (Join-Path $sitePackages "abaqus_codex") -Recurse

foreach ($directory in @("configs", "skills", "abaqus_plugins", "docs")) {
    Copy-RequiredDirectory $directory
}
foreach ($file in @(
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "AUTHORS.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "CITATION.cff"
)) {
    Copy-RequiredFile $file
}

$forbiddenExtensions = @(
    ".cae", ".odb", ".lck", ".sta", ".msg", ".dat", ".sim", ".res", ".rpy"
)
$forbiddenNames = @(
    ".env", "auth.json", "cookies.json", "credentials.json",
    "user_profile.json", "local_ai_rectangle.json"
)
$payloadRoots = @(
    (Join-Path $stagingRoot "configs"),
    (Join-Path $stagingRoot "skills"),
    (Join-Path $stagingRoot "abaqus_plugins"),
    (Join-Path $stagingRoot "docs"),
    (Join-Path $sitePackages "abaqus_codex")
)
foreach ($payloadRoot in $payloadRoots) {
    foreach ($payloadFile in Get-ChildItem -LiteralPath $payloadRoot -Recurse -File) {
        $lowerName = $payloadFile.Name.ToLowerInvariant()
        $lowerExtension = $payloadFile.Extension.ToLowerInvariant()
        if (
            $forbiddenExtensions -contains $lowerExtension -or
            $forbiddenNames -contains $lowerName -or
            $lowerName.StartsWith(".env.")
        ) {
            Stop-Build "forbidden private or Abaqus file in release payload: $($payloadFile.FullName)"
        }
    }
}

# Do not ship local bytecode accidentally copied from a maintainer checkout.
$safeStagingRoot = Assert-BuildChild $stagingRoot
Get-ChildItem -LiteralPath $safeStagingRoot -Directory -Filter "__pycache__" -Recurse |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $safeStagingRoot -File -Filter "*.pyc" -Recurse |
    Remove-Item -Force

$runtimePython = Join-Path $runtimeRoot "python.exe"
& $runtimePython -I -c "import abaqus_codex, tkinter; print('runtime-ok')"
if ($LASTEXITCODE -ne 0) {
    Stop-Build "the staged runtime could not import abaqus_codex and tkinter."
}

$innoArguments = @(
    "/DStageDir=$stagingRoot",
    "/DOutputDir=$outputRoot",
    "/DAppVersion=$AppVersion",
    "/DReleaseSerial=$ReleaseSerial",
    "/DSetupBaseName=$SetupBaseName",
    $innoScript
)
& $InnoCompiler @innoArguments
if ($LASTEXITCODE -ne 0) {
    Stop-Build "Inno Setup failed with exit code $LASTEXITCODE."
}

$setups = @(Get-ChildItem -LiteralPath $outputRoot -Filter "*.exe" -File)
if ($setups.Count -ne 1) {
    Stop-Build "expected one Setup executable but found $($setups.Count)."
}
$setup = $setups[0]
$setupHash = (Get-FileHash -LiteralPath $setup.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
$hashPath = "$($setup.FullName).sha256"
"$setupHash  $($setup.Name)" | Set-Content -LiteralPath $hashPath -Encoding Ascii

Write-Host "Windows setup build completed."
Write-Host "  Setup:  $($setup.FullName)"
Write-Host "  SHA256: $hashPath"
