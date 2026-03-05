# PowerShell script to build NeuroWings on Windows and publish the release.

param(
    [switch]$SkipDownload,
    [switch]$SkipPyInstaller,
    [switch]$SkipNSIS,
    [switch]$Clean,
    [switch]$SkipBuild,
    [string]$PythonExe = "python",
    [string]$Headline,
    [string[]]$Note,
    [string]$ServerHost = "193.124.117.175",
    [int]$ServerPort = 22,
    [string]$ServerUser = "root",
    [string]$ServerPassword,
    [string]$RemoteDir = "/opt/max-control/public/downloads/neurowings",
    [string]$PublicBaseUrl = "https://193-124-117-175.nip.io/downloads/neurowings"
)

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "====================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "====================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Get-AppVersion {
    $constantsPath = Join-Path $ProjectRoot "neurowings\core\constants.py"
    $content = Get-Content $constantsPath -Raw -Encoding UTF8
    $match = [regex]::Match($content, 'APP_VERSION\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "APP_VERSION не найден в $constantsPath"
    }
    return $match.Groups[1].Value
}

function Resolve-PythonExe {
    param([string]$Candidate)
    if (Test-Path $Candidate) {
        return (Resolve-Path $Candidate).Path
    }
    $command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python не найден: $Candidate"
}

function Ensure-PythonModule {
    param(
        [string]$ModuleName,
        [string]$PythonExePath
    )
    $cmd = "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
    & $PythonExePath -c $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Info "Устанавливаю Python пакет $ModuleName..."
        & $PythonExePath -m pip install $ModuleName
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось установить модуль $ModuleName"
        }
    }
}

$PythonExe = Resolve-PythonExe -Candidate $PythonExe

if (-not $SkipBuild) {
    Write-Step "Сборка релиза"
    $buildArgs = @()
    if ($SkipDownload) { $buildArgs += "-SkipDownload" }
    if ($SkipPyInstaller) { $buildArgs += "-SkipPyInstaller" }
    if ($SkipNSIS) { $buildArgs += "-SkipNSIS" }
    if ($Clean) { $buildArgs += "-Clean" }

    $buildArgs += @("-PythonExe", $PythonExe)

    & (Join-Path $PSScriptRoot "build_installer.ps1") @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Сборка завершилась ошибкой."
    }
}

Write-Step "Подготовка публикации"
Ensure-PythonModule -ModuleName "paramiko" -PythonExePath $PythonExe

$version = Get-AppVersion
$exePath = Join-Path $ProjectRoot "dist\НейроКрылья.exe"
if (-not (Test-Path $exePath)) {
    throw "EXE не найден: $exePath"
}

$setupPath = $null
$setupCandidates = Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "*-Setup.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
if ($setupCandidates) {
    $setupPath = $setupCandidates[0].FullName
}

$publishArgs = @(
    (Join-Path $PSScriptRoot "publish_release.py"),
    "--exe", $exePath,
    "--version", $version,
    "--server-host", $ServerHost,
    "--server-port", "$ServerPort",
    "--server-user", $ServerUser,
    "--remote-dir", $RemoteDir,
    "--public-base-url", $PublicBaseUrl
)

if ($setupPath) {
    $publishArgs += @("--setup", $setupPath)
}
if ($Headline) {
    $publishArgs += @("--headline", $Headline)
}
if ($ServerPassword) {
    $publishArgs += @("--server-password", $ServerPassword)
}
foreach ($line in $Note) {
    if ($line) {
        $publishArgs += @("--note", $line)
    }
}

Write-Step "Публикация на сервер"
& $PythonExe @publishArgs
if ($LASTEXITCODE -ne 0) {
    throw "Публикация завершилась ошибкой."
}

Write-Success "Релиз $version собран и опубликован."
