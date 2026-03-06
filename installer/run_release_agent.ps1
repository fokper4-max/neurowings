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

function Get-ConfigIntOrDefault {
    param(
        $Value,
        [int]$DefaultValue
    )
    if ($null -eq $Value) {
        return $DefaultValue
    }
    $parsed = 0
    if ([int]::TryParse($Value.ToString(), [ref]$parsed)) {
        return $parsed
    }
    return $DefaultValue
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

function Reset-InstallerScriptWorkingTree {
    param(
        [string]$RepositoryRoot,
        [string]$GitExe
    )
    $installerDir = Join-Path $RepositoryRoot "installer"
    if (-not (Test-Path $installerDir)) {
        return
    }
    & $GitExe -C $RepositoryRoot checkout -- "installer/*.ps1" 2>$null | Out-Null
}

function Get-PlainTextFromEncryptedFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Файл с зашифрованным паролем не найден: $Path"
    }
    return (Get-Content $Path -Raw -Encoding UTF8).Trim()
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

function Resolve-ModelsSourceDir {
    param(
        [string]$SourceDir,
        [string]$RepositoryPath
    )
    if (-not [string]::IsNullOrWhiteSpace($SourceDir)) {
        if (-not (Test-Path $SourceDir)) {
            throw "Папка моделей не найдена: $SourceDir"
        }
        return (Resolve-Path $SourceDir).Path
    }
    $repoModelsDir = Join-Path $RepositoryPath "models"
    if (Test-Path $repoModelsDir) {
        return (Resolve-Path $repoModelsDir).Path
    }
    return $null
}

function Get-SystemLoadSnapshot {
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $processors = @(Get-CimInstance Win32_Processor)
        $cpuAverage = 0
        if ($processors.Count -gt 0) {
            $cpuAverage = [math]::Round((($processors | Measure-Object -Property LoadPercentage -Average).Average), 0)
        }

        $freeMemoryMB = [math]::Floor(([double]$os.FreePhysicalMemory) / 1024)
        $totalMemoryMB = [math]::Floor(([double]$os.TotalVisibleMemorySize) / 1024)
        $usedMemoryPercent = 0
        if ($totalMemoryMB -gt 0) {
            $usedMemoryPercent = [math]::Round((($totalMemoryMB - $freeMemoryMB) * 100.0) / $totalMemoryMB, 1)
        }

        $activeBuildProcesses = @(
            Get-CimInstance Win32_Process | Where-Object {
                $_.ProcessId -ne $PID -and
                $_.CommandLine -and
                (
                    $_.CommandLine -match 'run_release_agent\.ps1' -or
                    $_.CommandLine -match 'build_and_publish\.ps1' -or
                    $_.CommandLine -match 'PyInstaller' -or
                    $_.CommandLine -match 'publish_release\.py'
                )
            }
        ).Count

        return [pscustomobject]@{
            CpuLoadPercent = $cpuAverage
            FreeMemoryMB = $freeMemoryMB
            TotalMemoryMB = $totalMemoryMB
            UsedMemoryPercent = $usedMemoryPercent
            ActiveBuildProcesses = $activeBuildProcesses
        }
    }
    catch {
        throw "Не удалось определить текущую нагрузку сервера: $($_.Exception.Message)"
    }
}

function Test-BuildCapacity {
    param($Config)

    $maxCpuLoadPercent = Get-ConfigIntOrDefault -Value $Config.MaxCpuLoadPercent -DefaultValue 75
    $minAvailableMemoryMB = Get-ConfigIntOrDefault -Value $Config.MinAvailableMemoryMB -DefaultValue 350
    $maxActiveBuildProcesses = Get-ConfigIntOrDefault -Value $Config.MaxActiveBuildProcesses -DefaultValue 0
    $snapshot = Get-SystemLoadSnapshot
    $reasons = @()

    if ($snapshot.CpuLoadPercent -gt $maxCpuLoadPercent) {
        $reasons += "CPU=$($snapshot.CpuLoadPercent)% > $maxCpuLoadPercent%"
    }
    if ($snapshot.FreeMemoryMB -lt $minAvailableMemoryMB) {
        $reasons += "RAM free=$($snapshot.FreeMemoryMB)MB < ${minAvailableMemoryMB}MB"
    }
    if ($snapshot.ActiveBuildProcesses -gt $maxActiveBuildProcesses) {
        $reasons += "active_build_processes=$($snapshot.ActiveBuildProcesses) > $maxActiveBuildProcesses"
    }

    return [pscustomobject]@{
        Snapshot = $snapshot
        MaxCpuLoadPercent = $maxCpuLoadPercent
        MinAvailableMemoryMB = $minAvailableMemoryMB
        MaxActiveBuildProcesses = $maxActiveBuildProcesses
        CanBuild = ($reasons.Count -eq 0)
        Reasons = $reasons
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
        last_docs_sync_commit = ""
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

    Reset-InstallerScriptWorkingTree -RepositoryRoot $config.RepositoryPath -GitExe $gitExe
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
    Normalize-InstallerScriptEncoding -RepositoryRoot $config.RepositoryPath

    $loadSnapshot = Get-SystemLoadSnapshot
    Write-Log ("Нагрузка сервера: CPU={0}% RAM={1}/{2}MB free ({3}% used) activeBuilds={4}" -f `
        $loadSnapshot.CpuLoadPercent, `
        $loadSnapshot.FreeMemoryMB, `
        $loadSnapshot.TotalMemoryMB, `
        $loadSnapshot.UsedMemoryPercent, `
        $loadSnapshot.ActiveBuildProcesses)

    $appVersion = Get-AppVersion -RepositoryPath $config.RepositoryPath
    $serverPassword = Get-PlainTextFromEncryptedFile -Path $config.PublishPasswordFile
    if ($state.last_built_version -eq $appVersion) {
        $docsScript = Join-Path $config.RepositoryPath "installer\sync_docs.ps1"
        $docsArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $docsScript,
            "-PythonExe", $pythonExe,
            "-ServerHost", $config.PublishServerHost,
            "-ServerPort", "$($config.PublishServerPort)",
            "-ServerUser", $config.PublishServerUser,
            "-ServerPassword", $serverPassword,
            "-RemoteDir", $config.PublishRemoteDir,
            "-PublicBaseUrl", $config.PublishBaseUrl
        )

        Write-Log "APP_VERSION не изменилась ($appVersion). Синхронизирую документацию."
        $docsStdoutPath = Join-Path (Split-Path $ConfigPath -Parent) "docs-stdout.log"
        $docsStderrPath = Join-Path (Split-Path $ConfigPath -Parent) "docs-stderr.log"
        Remove-Item $docsStdoutPath, $docsStderrPath -Force -ErrorAction SilentlyContinue

        $docsProcess = Start-Process -FilePath "powershell.exe" `
            -ArgumentList $docsArgs `
            -RedirectStandardOutput $docsStdoutPath `
            -RedirectStandardError $docsStderrPath `
            -Wait `
            -PassThru `
            -NoNewWindow

        foreach ($streamPath in @($docsStdoutPath, $docsStderrPath)) {
            if (-not (Test-Path $streamPath)) {
                continue
            }
            Get-Content $streamPath | ForEach-Object {
                Write-Log $_
            }
        }

        if ($docsProcess.ExitCode -ne 0) {
            throw "Синхронизация документации завершилась с ошибкой ($($docsProcess.ExitCode))."
        }

        $state.last_seen_commit = $remoteHead
        $state.last_docs_sync_commit = $remoteHead
        Save-Json -Path $statePath -Value $state
        Write-Log "Документация успешно синхронизирована для коммита $remoteHead."
        return
    }

    $modelsDir = Resolve-ModelsSourceDir -SourceDir $config.ModelsSourceDir -RepositoryPath $config.RepositoryPath
    if (-not [string]::IsNullOrWhiteSpace($config.ModelsSourceDir)) {
        Write-Log "Использую внешнюю папку моделей: $modelsDir"
    }
    elseif ($modelsDir) {
        Write-Log "Использую models/ из репозитория: $modelsDir"
    }
    else {
        Write-Log "Папка моделей не найдена. Сборка завершится ошибкой, если потребуются обязательные модели." "WARN"
    }

    $capacity = Test-BuildCapacity -Config $config
    if (-not $capacity.CanBuild) {
        Write-Log ("Откладываю сборку из-за нагрузки. CPU={0}% (лимит {1}%), freeRAM={2}MB (минимум {3}MB), activeBuilds={4} (лимит {5}). Причины: {6}" -f `
            $capacity.Snapshot.CpuLoadPercent, `
            $capacity.MaxCpuLoadPercent, `
            $capacity.Snapshot.FreeMemoryMB, `
            $capacity.MinAvailableMemoryMB, `
            $capacity.Snapshot.ActiveBuildProcesses, `
            $capacity.MaxActiveBuildProcesses, `
            ($capacity.Reasons -join "; ")) "WARN"
        return
    }

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
    if ($modelsDir) {
        $buildArgs += @("-ModelsDir", $modelsDir)
    }

    Write-Log "Запускаю сборку и публикацию версии $appVersion"
    $buildStdoutPath = Join-Path (Split-Path $ConfigPath -Parent) "build-stdout.log"
    $buildStderrPath = Join-Path (Split-Path $ConfigPath -Parent) "build-stderr.log"
    Remove-Item $buildStdoutPath, $buildStderrPath -Force -ErrorAction SilentlyContinue

    $buildProcess = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $buildArgs `
        -RedirectStandardOutput $buildStdoutPath `
        -RedirectStandardError $buildStderrPath `
        -Wait `
        -PassThru `
        -NoNewWindow

    foreach ($streamPath in @($buildStdoutPath, $buildStderrPath)) {
        if (-not (Test-Path $streamPath)) {
            continue
        }
        Get-Content $streamPath | ForEach-Object {
            Write-Log $_
        }
    }

    $buildExitCode = $buildProcess.ExitCode
    if ($buildExitCode -ne 0) {
        throw "Сборка или публикация завершились с ошибкой ($buildExitCode)."
    }

    $state.last_seen_commit = $remoteHead
    $state.last_built_commit = $remoteHead
    $state.last_built_version = $appVersion
    $state.last_docs_sync_commit = $remoteHead
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
