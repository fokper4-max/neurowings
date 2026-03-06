# PowerShell script to publish NeuroWings documentation to the update server.

param(
    [string]$PythonExe = "python",
    [string]$ServerHost = "193.124.117.175",
    [int]$ServerPort = 22,
    [string]$ServerUser = "root",
    [string]$ServerPassword,
    [string]$RemoteDir = "/opt/max-control/public/downloads/neurowings",
    [string]$PublicBaseUrl = "https://193-124-117-175.nip.io/downloads/neurowings"
)

$ErrorActionPreference = "Stop"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

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
        & $PythonExePath -m pip install --no-warn-script-location $ModuleName
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось установить модуль $ModuleName"
        }
    }
}

$PythonExe = Resolve-PythonExe -Candidate $PythonExe
Ensure-PythonModule -ModuleName "paramiko" -PythonExePath $PythonExe

$publishArgs = @(
    (Join-Path $PSScriptRoot "publish_release.py"),
    "--docs-only",
    "--server-host", $ServerHost,
    "--server-port", "$ServerPort",
    "--server-user", $ServerUser,
    "--remote-dir", $RemoteDir,
    "--public-base-url", $PublicBaseUrl
)

if ($ServerPassword) {
    $publishArgs += @("--server-password", $ServerPassword)
}

& $PythonExe @publishArgs
if ($LASTEXITCODE -ne 0) {
    throw "Синхронизация документации завершилась ошибкой."
}
