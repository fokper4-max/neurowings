# One-time bootstrap for a Windows build server that watches GitHub and publishes NeuroWings.

param(
    [string]$RepositoryUrl = "https://github.com/fokper4-max/neurowings.git",
    [string]$Branch = "main",
    [string]$RepositoryPath = "C:\Build\NeuroWings",
    [string]$StateDir = "$env:ProgramData\NeuroWingsBuilder",
    [int]$PollMinutes = 60,
    [switch]$BuildSetup,
    [string]$PublishServerHost = "193.124.117.175",
    [int]$PublishServerPort = 22,
    [string]$PublishServerUser = "root",
    [string]$PublishServerPassword,
    [string]$PublishRemoteDir = "/opt/max-control/public/downloads/neurowings",
    [string]$PublishBaseUrl = "https://193-124-117-175.nip.io/downloads/neurowings",
    [string]$GitInstallDir = "$env:ProgramData\NeuroWingsBuilder\tools\git",
    [string]$PythonInstallDir = "C:\Python311",
    [string]$ModelsSourceDir = "",
    [string]$TaskName = "NeuroWings Release Agent",
    [string]$TaskUser = "Administrator",
    [string]$TaskPassword
)

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

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

function Ensure-Command {
    param(
        [string]$Name,
        [string]$Hint
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw $Hint
    }
}

function Resolve-Executable {
    param(
        [string]$ConfiguredPath,
        [string]$FallbackName
    )
    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPath) -and (Test-Path $ConfiguredPath)) {
        return (Resolve-Path $ConfiguredPath).Path
    }
    $command = Get-Command $FallbackName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Add-ToolDirectoriesToPath {
    param(
        [string]$GitExe,
        [string]$PythonExe
    )
    $dirs = @()
    if ($GitExe -and (Test-Path $GitExe)) {
        $gitParent = Split-Path $GitExe -Parent
        $dirs += $gitParent
        $gitCmdDir = Join-Path (Split-Path $gitParent -Parent) "cmd"
        if (Test-Path $gitCmdDir) {
            $dirs += $gitCmdDir
        }
    }
    if ($PythonExe -and (Test-Path $PythonExe)) {
        $pythonParent = Split-Path $PythonExe -Parent
        $dirs += $pythonParent
        $pythonScripts = Join-Path $pythonParent "Scripts"
        if (Test-Path $pythonScripts) {
            $dirs += $pythonScripts
        }
    }
    if ($dirs.Count -gt 0) {
        $env:PATH = (($dirs | Select-Object -Unique) -join ";") + ";" + $env:PATH
    }
}

function Invoke-DownloadFile {
    param(
        [string]$Url,
        [string]$DestinationPath
    )
    $parent = Split-Path $DestinationPath -Parent
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Invoke-WebRequest -Uri $Url -OutFile $DestinationPath -UseBasicParsing
}

function Write-Utf8BomFile {
    param(
        [string]$Path,
        [string]$Content
    )
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8Bom)
}

function Normalize-InstallerScriptEncoding {
    param([string]$RepositoryRoot)
    $installerDir = Join-Path $RepositoryRoot "installer"
    if (-not (Test-Path $installerDir)) {
        return
    }
    Get-ChildItem -Path $installerDir -Filter "*.ps1" -File | ForEach-Object {
        $content = Get-Content $_.FullName -Raw -Encoding UTF8
        Write-Utf8BomFile -Path $_.FullName -Content $content
    }
}

function Get-LatestGitAssetUrl {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -Headers @{ "User-Agent" = "NeuroWingsBuilder" }
    $asset = $release.assets | Where-Object {
        $_.name -match '^MinGit-.*-64-bit\.zip$' -and $_.name -notmatch 'busybox'
    } | Select-Object -First 1
    if ($null -eq $asset) {
        throw "Не удалось найти 64-bit MinGit архив в последнем релизе git-for-windows."
    }
    return $asset.browser_download_url
}

function Ensure-Git {
    param([string]$InstallDir)
    $portableGit = Join-Path $InstallDir "cmd\git.exe"
    $existing = Resolve-Executable -ConfiguredPath $portableGit -FallbackName "git"
    if ($existing) {
        return $existing
    }

    Write-Info "Git не найден, загружаю portable MinGit..."
    $zipPath = Join-Path $env:TEMP "MinGit-64-bit.zip"
    $extractRoot = Split-Path $InstallDir -Parent
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Invoke-DownloadFile -Url (Get-LatestGitAssetUrl) -DestinationPath $zipPath
    if (Test-Path $InstallDir) {
        Remove-Item $InstallDir -Recurse -Force
    }
    Expand-Archive -Path $zipPath -DestinationPath $InstallDir -Force
    if (-not (Test-Path $portableGit)) {
        throw "Не удалось подготовить portable Git: $portableGit"
    }
    return (Resolve-Path $portableGit).Path
}

function Ensure-Python {
    param([string]$InstallDir)
    $pythonExe = Join-Path $InstallDir "python.exe"
    $existing = Resolve-Executable -ConfiguredPath $pythonExe -FallbackName "python"
    if ($existing) {
        return $existing
    }

    Write-Info "Python не найден, устанавливаю Python 3.11..."
    $installerPath = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
    Invoke-DownloadFile -Url "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -DestinationPath $installerPath
    $arguments = @(
        "/quiet",
        "InstallAllUsers=1",
        "TargetDir=$InstallDir",
        "PrependPath=0",
        "Include_pip=1",
        "Include_test=0",
        "Include_launcher=0",
        "Shortcuts=0",
        "SimpleInstall=1"
    )
    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Установка Python завершилась с ошибкой ($($process.ExitCode))."
    }
    if (-not (Test-Path $pythonExe)) {
        throw "Python установлен, но исполняемый файл не найден: $pythonExe"
    }
    return (Resolve-Path $pythonExe).Path
}

function Convert-SecureToPlain {
    param([Security.SecureString]$SecureString)
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Save-EncryptedSecret {
    param(
        [string]$Path,
        [Security.SecureString]$SecureString
    )
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $plain = Convert-SecureToPlain -SecureString $SecureString
    Set-Content -Path $Path -Value $plain -Encoding UTF8
    & icacls.exe $Path /inheritance:r /grant:r "Administrators:F" "SYSTEM:F" | Out-Null
}

Write-Step "Проверка окружения"
$gitExe = Ensure-Git -InstallDir $GitInstallDir
$pythonExe = Ensure-Python -InstallDir $PythonInstallDir
Add-ToolDirectoriesToPath -GitExe $gitExe -PythonExe $pythonExe
if ($BuildSetup -and -not (Test-Path "C:\Program Files (x86)\NSIS\makensis.exe")) {
    throw "NSIS не найден. Установите NSIS 3.x."
}
Write-Success "Базовые инструменты найдены"

Write-Step "Подготовка каталогов"
New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $RepositoryPath -Parent) -Force | Out-Null
Write-Success "Каталоги готовы"

Write-Step "Синхронизация репозитория"
if (-not (Test-Path $RepositoryPath)) {
    & $gitExe clone $RepositoryUrl $RepositoryPath
    if ($LASTEXITCODE -ne 0) {
        throw "git clone завершился с ошибкой."
    }
}
elseif (-not (Test-Path (Join-Path $RepositoryPath ".git"))) {
    throw "Папка $RepositoryPath уже существует, но это не git-репозиторий."
}
else {
    & $gitExe -C $RepositoryPath remote set-url origin $RepositoryUrl
    & $gitExe -C $RepositoryPath fetch origin
    if ($LASTEXITCODE -ne 0) {
        throw "git fetch завершился с ошибкой."
    }
}

& $gitExe -C $RepositoryPath config core.longpaths true | Out-Null
& $gitExe -C $RepositoryPath checkout $Branch | Out-Null
& $gitExe -C $RepositoryPath pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) {
    throw "git pull завершился с ошибкой."
}
Normalize-InstallerScriptEncoding -RepositoryRoot $RepositoryPath
Write-Success "Репозиторий синхронизирован"

Write-Step "Сохранение конфигурации"
$publishSecretPath = Join-Path $StateDir "publish-server-password.txt"
$statePath = Join-Path $StateDir "builder-state.json"
$configPath = Join-Path $StateDir "builder-config.json"

if ($PublishServerPassword) {
    $publishSecure = ConvertTo-SecureString $PublishServerPassword -AsPlainText -Force
}
else {
    $publishSecure = Read-Host "Пароль Linux-сервера публикации" -AsSecureString
}
Save-EncryptedSecret -Path $publishSecretPath -SecureString $publishSecure

$config = [pscustomobject]@{
    RepositoryUrl = $RepositoryUrl
    Branch = $Branch
    RepositoryPath = $RepositoryPath
    BuildSetup = [bool]$BuildSetup
    GitExe = $gitExe
    PythonExe = $pythonExe
    ModelsSourceDir = $ModelsSourceDir
    PublishServerHost = $PublishServerHost
    PublishServerPort = $PublishServerPort
    PublishServerUser = $PublishServerUser
    PublishRemoteDir = $PublishRemoteDir
    PublishBaseUrl = $PublishBaseUrl
    PublishPasswordFile = $publishSecretPath
    StatePath = $statePath
}
$config | ConvertTo-Json -Depth 10 | Set-Content -Path $configPath -Encoding UTF8
Write-Success "Конфигурация сохранена"

Write-Step "Регистрация задачи"
if ($TaskPassword) {
    $taskPasswordPlain = $TaskPassword
}
else {
    $taskSecure = Read-Host "Пароль пользователя для Task Scheduler ($TaskUser)" -AsSecureString
    $taskPasswordPlain = Convert-SecureToPlain -SecureString $taskSecure
}

$agentPath = Join-Path $RepositoryPath "installer\run_release_agent.ps1"
$taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$agentPath`""

& schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
& schtasks.exe /Create /F /TN $TaskName /TR $taskCommand /SC MINUTE /MO $PollMinutes /RU $TaskUser /RP $taskPasswordPlain /RL HIGHEST
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось зарегистрировать Scheduled Task."
}
Write-Success "Задача $TaskName зарегистрирована"

Write-Step "Первый запуск агента"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $agentPath
if ($LASTEXITCODE -ne 0) {
    throw "Первый запуск агента завершился с ошибкой."
}

Write-Success "Windows build server настроен."
