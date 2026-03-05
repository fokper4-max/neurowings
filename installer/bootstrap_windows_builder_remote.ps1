# Lightweight wrapper for bootstrapping the Windows build server over a one-shot remote command.

param(
    [string]$BootstrapScriptUrl = "https://raw.githubusercontent.com/fokper4-max/neurowings/main/installer/setup_windows_builder.ps1",
    [string]$PublishServerPassword,
    [string]$TaskPassword,
    [int]$PollMinutes = 60,
    [string]$CallbackUrl = "https://193-124-117-175.nip.io/downloads/neurowings/update-feed.json",
    [string]$CallbackToken = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$stateDir = "C:\ProgramData\NeuroWingsBuilder"
$bootstrapPath = Join-Path $env:TEMP "setup_windows_builder.ps1"
$logPath = Join-Path $stateDir "bootstrap.log"

function Write-Utf8BomFile {
    param(
        [string]$Path,
        [string]$Content
    )
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8Bom)
}

function Send-Marker {
    param(
        [string]$Stage,
        [string]$Message = ""
    )

    if ([string]::IsNullOrWhiteSpace($CallbackToken)) {
        return
    }

    $uri = "$CallbackUrl?cb=$CallbackToken&stage=$Stage"
    if ($Message) {
        $compact = (($Message -replace "`r?`n", " ") -replace "\s+", " ").Trim()
        if ($compact.Length -gt 220) {
            $compact = $compact.Substring(0, 220)
        }
        $uri += "&msg=" + [uri]::EscapeDataString($compact)
    }

    try {
        Invoke-WebRequest -UseBasicParsing $uri | Out-Null
    }
    catch {
    }
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
Send-Marker -Stage "start"

try {
    $bootstrapContent = (Invoke-WebRequest -UseBasicParsing $BootstrapScriptUrl).Content
    Write-Utf8BomFile -Path $bootstrapPath -Content $bootstrapContent
    Send-Marker -Stage "downloaded"

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bootstrapPath `
        -PollMinutes $PollMinutes `
        -PublishServerPassword $PublishServerPassword `
        -TaskPassword $TaskPassword *>&1 | Tee-Object -FilePath $logPath

    if ($LASTEXITCODE -eq 0) {
        Send-Marker -Stage "success"
    }
    else {
        $tail = if (Test-Path $logPath) { Get-Content $logPath -Tail 12 | Out-String } else { "bootstrap log missing" }
        Send-Marker -Stage "fail" -Message ("exit=$LASTEXITCODE; " + $tail)
        exit $LASTEXITCODE
    }
}
catch {
    $detail = $_.Exception.Message
    if (Test-Path $logPath) {
        $detail += " | " + (Get-Content $logPath -Tail 12 | Out-String)
    }
    Send-Marker -Stage "exception" -Message $detail
    throw
}
