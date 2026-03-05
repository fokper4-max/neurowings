# Automated release agent for a Windows build server.

param(
    [string]$ConfigPath = "$env:ProgramData\NeuroWingsBuilder\builder-config.json"
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $configDir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }

    $logPath = Join-Path $configDir "builder.log"
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -Path $logPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Load-JsonOrDefault {
    param(
        [string]$Path,
        $DefaultValue
    )
    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }
    return Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Save-Json {
    param(
        [string]$Path,
        $Value
    )
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $Value | ConvertTo-Json -Depth 10 | Set-Content -Path $Path -Encoding UTF8
}

function Get-PlainTextFromEncryptedFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Файл с зашифрованным паролем не найден: $Path"
    }
    $encrypted = Get-Content $Path -Raw -Encoding UTF8
    $secure = ConvertTo-SecureString $encrypted
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Get-AppVersion {
    param([string]$RepositoryPath)
    $constantsPath = Join-Path $RepositoryPath "neurowings\core\constants.py"
    $content = Get-Content $constantsPath -Raw -Encoding UTF8
    $match = [regex]::Match($content, 'APP_VERSION\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "APP_VERSION не найден в $constantsPath"
    }
    return $match.Groups[1].Value
}

function Resolve-Executable {
    param(
        [string]$ConfiguredPath,
        [string]$FallbackName,
        [string]$ErrorMessage
    )
    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPath)) {
        if (Test-Path $ConfiguredPath) {
            return (Resolve-Path $ConfiguredPath).Path
        }
        $configuredCommand = Get-Command $ConfiguredPath -ErrorAction SilentlyContinue
        if ($configuredCommand) {
            return $configuredCommand.Source
        }
        throw $ErrorMessage
    }
    $fallbackCommand = Get-Command $FallbackName -ErrorAction SilentlyContinue
    if ($fallbackCommand) {
        return $fallbackCommand.Source
    }
    throw $ErrorMessage
}

function Add-ToolDirectoriesToPath {
    param($Config)
    $dirs = @()
    foreach ($path in @($Config.GitExe, $Config.PythonExe)) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }
        $parent = Split-Path $path -Parent
        if (-not [string]::IsNullOrWhiteSpace($parent) -and (Test-Path $parent)) {
            $dirs += $parent
        }
        if ($path -like "*\\python.exe") {
            $scriptsDir = Join-Path $parent "Scripts"
            if (Test-Path $scriptsDir) {
                $dirs += $scriptsDir
            }
        }
        elseif ($path -like "*\\git.exe") {
            $cmdDir = Join-Path (Split-Path $parent -Parent) "cmd"
            if (Test-Path $cmdDir) {
                $dirs += $cmdDir
            }
        }
    }
    if ($dirs.Count -gt 0) {
        $uniqueDirs = $dirs | Select-Object -Unique
        $env:PATH = ($uniqueDirs -join ";") + ";" + $env:PATH
    }
}

function Sync-Models {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )
    if ([string]::IsNullOrWhiteSpace($SourceDir)) {
        return
    }
    if (-not (Test-Path $SourceDir)) {
        throw "Папка моделей не найдена: $SourceDir"
    }

    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    & robocopy $SourceDir $TargetDir /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy завершился с ошибкой ($LASTEXITCODE)"
    }
}

function Run-Agent {
    $config = Load-JsonOrDefault -Path $ConfigPath -DefaultValue $null
    if ($null -eq $config) {
        throw "Конфигурация агента не найдена: $ConfigPath"
    }

    Add-ToolDirectoriesToPath -Config $config

    $statePath = $config.StatePath
    $state = Load-JsonOrDefault -Path $statePath -DefaultValue ([pscustomobject]@{
        last_seen_commit = ""
        last_built_commit = ""
        last_built_version = ""
    })

    $gitExe = Resolve-Executable -ConfiguredPath $config.GitExe -FallbackName "git" -ErrorMessage "Git не найден."
    $pythonExe = Resolve-Executable -ConfiguredPath $config.PythonExe -FallbackName "python" -ErrorMessage "Python не найден."

    if (-not (Test-Path $config.RepositoryPath)) {
        Write-Log "Клонирую репозиторий в $($config.RepositoryPath)"
        & $gitExe clone $config.RepositoryUrl $config.RepositoryPath
        if ($LASTEXITCODE -ne 0) {
            throw "git clone завершился с ошибкой."
        }
    }

    & $gitExe -C $config.RepositoryPath config core.longpaths true | Out-Null
    & $gitExe -C $config.RepositoryPath fetch origin $config.Branch
    if ($LASTEXITCODE -ne 0) {
        throw "git fetch завершился с ошибкой."
    }

    $remoteHead = (& $gitExe -C $config.RepositoryPath rev-parse "origin/$($config.Branch)").Trim()
    if ([string]::IsNullOrWhiteSpace($remoteHead)) {
        throw "Не удалось определить origin/$($config.Branch)."
    }

    if ($state.last_seen_commit -eq $remoteHead) {
        Write-Log "Новых коммитов в GitHub нет. Текущий HEAD: $remoteHead"
        return
    }

    Write-Log "Обнаружен новый коммит GitHub: $remoteHead"

    & $gitExe -C $config.RepositoryPath checkout $config.Branch | Out-Null
    & $gitExe -C $config.RepositoryPath pull --ff-only origin $config.Branch
    if ($LASTEXITCODE -ne 0) {
        throw "git pull завершился с ошибкой."
    }

    if (-not [string]::IsNullOrWhiteSpace($config.ModelsSourceDir)) {
        Write-Log "Синхронизирую модели из $($config.ModelsSourceDir)"
        Sync-Models -SourceDir $config.ModelsSourceDir -TargetDir (Join-Path $config.RepositoryPath "models")
    }

    $appVersion = Get-AppVersion -RepositoryPath $config.RepositoryPath
    if ($state.last_built_version -eq $appVersion) {
        Write-Log "APP_VERSION не изменилась ($appVersion). Публикацию пропускаю."
        $state.last_seen_commit = $remoteHead
        Save-Json -Path $statePath -Value $state
        return
    }

    $serverPassword = Get-PlainTextFromEncryptedFile -Path $config.PublishPasswordFile
    $buildScript = Join-Path $config.RepositoryPath "installer\build_and_publish.ps1"
    $buildArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $buildScript,
        "-Clean",
        "-SkipDownload",
        "-PythonExe", $pythonExe,
        "-ServerHost", $config.PublishServerHost,
        "-ServerPort", "$($config.PublishServerPort)",
        "-ServerUser", $config.PublishServerUser,
        "-ServerPassword", $serverPassword,
        "-RemoteDir", $config.PublishRemoteDir,
        "-PublicBaseUrl", $config.PublishBaseUrl
    )
    if (-not $config.BuildSetup) {
        $buildArgs += "-SkipNSIS"
    }

    Write-Log "Запускаю сборку и публикацию версии $appVersion"
    & powershell.exe @buildArgs 2>&1 | ForEach-Object {
        Write-Log $_
    }
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -ne 0) {
        throw "Сборка или публикация завершились с ошибкой ($buildExitCode)."
    }

    $state.last_seen_commit = $remoteHead
    $state.last_built_commit = $remoteHead
    $state.last_built_version = $appVersion
    Save-Json -Path $statePath -Value $state

    Write-Log "Версия $appVersion успешно собрана и опубликована."
}

try {
    Run-Agent
}
catch {
    Write-Log $_.Exception.Message "ERROR"
    exit 1
}
