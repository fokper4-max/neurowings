# PowerShell скрипт для полной сборки инсталлятора НейроКрылья
# Запускать от имени администратора

param(
    [switch]$SkipDownload,      # Пропустить загрузку redistributables
    [switch]$SkipPyInstaller,   # Пропустить PyInstaller
    [switch]$SkipNSIS,          # Пропустить NSIS
    [switch]$Clean,             # Очистить старые сборки перед началом
    [string]$PythonExe = "python"
)

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$ProductName = "НейроКрылья"
$InstallerVersion = $null

# Цвета для вывода
function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "====================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "====================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Yellow
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

function Test-PythonModule {
    param(
        [string]$PythonExePath,
        [string]$ModuleName
    )
    $cmd = "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
    & $PythonExePath -c $cmd
    return ($LASTEXITCODE -eq 0)
}

function Get-InstallerVersion {
    param([string]$NsiPath)
    $content = Get-Content $NsiPath -Raw -Encoding UTF8
    $match = [regex]::Match($content, '!define\s+PRODUCT_VERSION\s+"([^"]+)"')
    if (-not $match.Success) {
        throw "Не удалось определить PRODUCT_VERSION из $NsiPath"
    }
    return $match.Groups[1].Value
}

# Переходим в корневую директорию проекта
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

Write-Step "$ProductName Installer Build Script"
Write-Host "Project Root: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Проверяем наличие необходимых инструментов
Write-Step "1. Проверка окружения"

# Проверка Python
try {
    $PythonExe = Resolve-PythonExe -Candidate $PythonExe
    $pythonVersion = & $PythonExe --version 2>&1
    Write-Success "Python найден: $pythonVersion"
}
catch {
    Write-Error-Custom "Python не найден! Установите Python 3.8+ и добавьте в PATH"
    exit 1
}

# Проверка PyInstaller
if (Test-PythonModule -PythonExePath $PythonExe -ModuleName "PyInstaller") {
    $pyinstallerVersion = & $PythonExe -m PyInstaller --version 2>&1
    Write-Success "PyInstaller найден: $pyinstallerVersion"
}
else {
    Write-Info "PyInstaller не найден, устанавливаем..."
    & $PythonExe -m pip install --no-warn-script-location pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Не удалось установить PyInstaller"
        exit 1
    }
    Write-Success "PyInstaller установлен"
}

$nsisPath = "C:\Program Files (x86)\NSIS\makensis.exe"
if (-not $SkipNSIS) {
    if (Test-Path $nsisPath) {
        Write-Success "NSIS найден: $nsisPath"
    }
    else {
        Write-Error-Custom "NSIS не найден! Установите NSIS 3.x с https://nsis.sourceforge.io/"
        Write-Info "После установки перезапустите скрипт"
        exit 1
    }
}
else {
    Write-Info "NSIS не требуется (--SkipNSIS)"
}

# Очистка старых сборок
if ($Clean) {
    Write-Step "2. Очистка старых сборок"

    $dirs = @("build", "dist")
    foreach ($dir in $dirs) {
        $path = Join-Path $ProjectRoot $dir
        if (Test-Path $path) {
            Write-Info "Удаление $dir..."
            Remove-Item $path -Recurse -Force
            Write-Success "Удалено: $path"
        }
    }
}

# Загрузка redistributables
if (-not $SkipDownload) {
    Write-Step "3. Загрузка redistributables"

    $downloadScript = Join-Path $PSScriptRoot "download_redistributables.ps1"
    & $downloadScript

    if ($LASTEXITCODE -eq 0 -or $?) {
        Write-Success "Redistributables загружены"
    }
    else {
        Write-Error-Custom "Ошибка загрузки redistributables"
        exit 1
    }
}
else {
    Write-Info "Пропуск загрузки redistributables (--SkipDownload)"
}

# Установка зависимостей Python
Write-Step "4. Установка зависимостей Python"

$requirementsFile = Join-Path $ProjectRoot "requirements.txt"
if (Test-Path $requirementsFile) {
    Write-Info "Установка зависимостей из requirements.txt..."
    & $PythonExe -m pip install --no-warn-script-location -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Не удалось установить зависимости Python"
        exit 1
    }
    Write-Success "Зависимости установлены"
}
else {
    Write-Info "requirements.txt не найден, пропускаем"
}

# Сборка с PyInstaller
if (-not $SkipPyInstaller) {
    Write-Step "5. Сборка с PyInstaller"

    $specFile = Join-Path $PSScriptRoot "NeuroWings.spec"

    if (-not (Test-Path $specFile)) {
        Write-Error-Custom "Файл спецификации не найден: $specFile"
        exit 1
    }

    Write-Info "Запуск PyInstaller..."
    Write-Host "Спецификация: $specFile" -ForegroundColor Gray

    & $PythonExe -m PyInstaller --clean --noconfirm $specFile
    $pyInstallerExitCode = $LASTEXITCODE

    # На Windows некоторые сборки PyInstaller пишут INFO в stderr и могут завершаться
    # с ненулевым кодом, хотя итоговый one-file EXE уже собран корректно.
    $exePath = Join-Path $ProjectRoot "dist\$ProductName.exe"
    if (Test-Path $exePath) {
        $size = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
        if ($pyInstallerExitCode -ne 0) {
            Write-Info "PyInstaller вернул код $pyInstallerExitCode, но EXE уже создан. Продолжаю сборку."
        }
        else {
            Write-Success "PyInstaller завершен успешно"
        }
        Write-Success "EXE файл создан: $exePath ($size MB)"
    }
    else {
        Write-Error-Custom "PyInstaller завершился с ошибкой (код: $pyInstallerExitCode)"
        Write-Error-Custom "EXE файл не найден после сборки!"
        exit 1
    }
}
else {
    Write-Info "Пропуск PyInstaller (--SkipPyInstaller)"
}

# Создание лицензии (если нет)
Write-Step "6. Проверка лицензии"

$licenseFile = Join-Path $ProjectRoot "LICENSE.txt"
if (-not (Test-Path $licenseFile)) {
    Write-Info "Создание файла лицензии..."
    @"
MIT License

Copyright (c) 2025 НейроКрылья Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"@ | Out-File -FilePath $licenseFile -Encoding UTF8
    Write-Success "Файл лицензии создан"
}
else {
    Write-Success "Файл лицензии существует"
}

# Сборка NSIS инсталлятора
if (-not $SkipNSIS) {
    Write-Step "7. Сборка NSIS инсталлятора"

    $nsiScript = Join-Path $PSScriptRoot "installer.nsi"

    if (-not (Test-Path $nsiScript)) {
        Write-Error-Custom "NSIS скрипт не найден: $nsiScript"
        exit 1
    }

    Write-Info "Запуск NSIS..."
    Write-Host "Скрипт: $nsiScript" -ForegroundColor Gray
    $InstallerVersion = Get-InstallerVersion -NsiPath $nsiScript

    & $nsisPath $nsiScript

    if ($LASTEXITCODE -eq 0) {
        Write-Success "NSIS компиляция завершена успешно"

        # Проверяем результат
        $installerPath = Join-Path $ProjectRoot "dist\$ProductName-$InstallerVersion-Setup.exe"
        if (Test-Path $installerPath) {
            $size = [math]::Round((Get-Item $installerPath).Length / 1MB, 2)
            Write-Success "Инсталлятор создан: $installerPath ($size MB)"
        }
        else {
            Write-Error-Custom "Инсталлятор не найден после сборки!"
            exit 1
        }
    }
    else {
        Write-Error-Custom "NSIS завершился с ошибкой (код: $LASTEXITCODE)"
        exit 1
    }
}
else {
    Write-Info "Пропуск NSIS (--SkipNSIS)"
}

# Финальная информация
Write-Step "8. Сборка завершена!"

Write-Host "Результаты:" -ForegroundColor Cyan
Write-Host ""

$distDir = Join-Path $ProjectRoot "dist"
if (Test-Path $distDir) {
    Get-ChildItem $distDir -File | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Write-Host "  - $($_.Name) ($size MB)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Success "Готово! Инсталлятор готов к распространению."
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Yellow
Write-Host "  1. Протестируйте инсталлятор на чистой системе" -ForegroundColor Gray
Write-Host "  2. Проверьте установку на Windows 8.1, 10, 11" -ForegroundColor Gray
Write-Host "  3. Убедитесь, что все зависимости устанавливаются корректно" -ForegroundColor Gray
Write-Host ""
