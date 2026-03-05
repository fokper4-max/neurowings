# PowerShell скрипт для загрузки необходимых redistributables
# Запускать от имени администратора

param(
    [switch]$Force  # Принудительная перезагрузка
)

# Требуем прав администратора
#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "НейроКрылья Redistributables Downloader" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Создаем папку для redistributables
$redistDir = Join-Path $PSScriptRoot "redistributables"
if (-not (Test-Path $redistDir)) {
    Write-Host "[+] Создание папки redistributables..." -ForegroundColor Green
    New-Item -ItemType Directory -Path $redistDir | Out-Null
} else {
    Write-Host "[*] Папка redistributables уже существует" -ForegroundColor Yellow
}

# Функция для загрузки файла с прогресс-баром
function Download-File {
    param(
        [string]$Url,
        [string]$OutputPath,
        [string]$Description
    )

    if ((Test-Path $OutputPath) -and -not $Force) {
        Write-Host "[*] $Description уже загружен, пропускаем" -ForegroundColor Yellow
        return
    }

    Write-Host "[+] Загрузка $Description..." -ForegroundColor Green
    Write-Host "    URL: $Url" -ForegroundColor Gray

    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
        Write-Host "    [OK] Сохранено: $OutputPath" -ForegroundColor Green
    }
    catch {
        Write-Host "    [ERROR] Не удалось загрузить: $_" -ForegroundColor Red
        throw
    }
}

# URL для загрузки (официальные ссылки)
$downloads = @{
    # Visual C++ Redistributables
    "vc_redist_2022_x64.exe" = @{
        Url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Description = "Visual C++ 2022 Redistributable (x64)"
    }
    "vc_redist_2019_x64.exe" = @{
        Url = "https://aka.ms/vs/16/release/vc_redist.x64.exe"
        Description = "Visual C++ 2019 Redistributable (x64)"
    }
    "vc_redist_2015_x64.exe" = @{
        Url = "https://aka.ms/vs/16/release/vc_redist.x64.exe"
        Description = "Visual C++ 2015 Redistributable (x64)"
    }

    # Python installers
    "python-3.11-amd64.exe" = @{
        Url = "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"
        Description = "Python 3.11.8 (64-bit)"
    }
    "python-3.10-amd64.exe" = @{
        Url = "https://www.python.org/ftp/python/3.10.13/python-3.10.13-amd64.exe"
        Description = "Python 3.10.13 (64-bit)"
    }
    "python-3.8-amd64.exe" = @{
        Url = "https://www.python.org/ftp/python/3.8.18/python-3.8.18-amd64.exe"
        Description = "Python 3.8.18 (64-bit)"
    }
}

# Загружаем все файлы
Write-Host ""
Write-Host "Начало загрузки файлов..." -ForegroundColor Cyan
Write-Host ""

$total = $downloads.Count
$current = 0

foreach ($filename in $downloads.Keys) {
    $current++
    $item = $downloads[$filename]
    $outputPath = Join-Path $redistDir $filename

    Write-Host "[$current/$total] " -NoNewline -ForegroundColor Cyan
    Download-File -Url $item.Url -OutputPath $outputPath -Description $item.Description
    Write-Host ""
}

Write-Host ""
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "Загрузка завершена!" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Показываем размеры файлов
Write-Host "Загруженные файлы:" -ForegroundColor Cyan
Get-ChildItem $redistDir | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 2)
    Write-Host "  - $($_.Name) ($size MB)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Готово! Файлы сохранены в: $redistDir" -ForegroundColor Green
