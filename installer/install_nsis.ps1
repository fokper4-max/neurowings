# Автоматическая установка NSIS
$ErrorActionPreference = "Stop"

$nsisUrl = "https://sourceforge.net/projects/nsis/files/NSIS%203/3.10/nsis-3.10-setup.exe/download"
$nsisInstaller = "$env:TEMP\nsis-setup.exe"
$nsisPath = "C:\Program Files (x86)\NSIS\makensis.exe"

Write-Host "Checking NSIS installation..." -ForegroundColor Cyan

if (Test-Path $nsisPath) {
    Write-Host "[OK] NSIS already installed at: $nsisPath" -ForegroundColor Green
    exit 0
}

Write-Host "[*] Downloading NSIS installer..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $nsisUrl -OutFile $nsisInstaller -UseBasicParsing
    Write-Host "[OK] Downloaded to: $nsisInstaller" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to download NSIS: $_" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Installing NSIS..." -ForegroundColor Yellow
Write-Host "    This may take a minute..." -ForegroundColor Gray

try {
    Start-Process -FilePath $nsisInstaller -ArgumentList "/S" -Wait -NoNewWindow
    Write-Host "[OK] NSIS installed successfully" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to install NSIS: $_" -ForegroundColor Red
    exit 1
}

# Verify installation
if (Test-Path $nsisPath) {
    Write-Host "[OK] NSIS verified at: $nsisPath" -ForegroundColor Green
    exit 0
} else {
    Write-Host "[ERROR] NSIS installation verification failed" -ForegroundColor Red
    exit 1
}
