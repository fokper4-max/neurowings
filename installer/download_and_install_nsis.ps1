$ErrorActionPreference = "Stop"

$url = "https://sourceforge.net/projects/nsis/files/NSIS%203/3.10/nsis-3.10-setup.exe/download"
$installer = "$env:TEMP\nsis-setup.exe"

Write-Host "Downloading NSIS 3.10..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    Write-Host "[OK] Downloaded" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Download failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Installing NSIS (silent mode)..." -ForegroundColor Cyan
try {
    Start-Process -FilePath $installer -ArgumentList "/S" -Wait -NoNewWindow
    Write-Host "[OK] Installation complete" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Installation failed: $_" -ForegroundColor Red
    exit 1
}

Start-Sleep -Seconds 2

if (Test-Path "C:\Program Files (x86)\NSIS\makensis.exe") {
    Write-Host "[OK] NSIS verified!" -ForegroundColor Green
} else {
    Write-Host "[WARNING] NSIS not found at expected location" -ForegroundColor Yellow
}
