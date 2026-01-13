# PowerShell script для автоматической загрузки готового .exe из GitHub Actions
# Использование: .\download_build.ps1

# GitHub токен (опционально - можно скачивать без токена публичные артефакты)
# Если репозиторий приватный, установите токен:
# $env:GITHUB_TOKEN = "your_token_here"

$token = $env:GITHUB_TOKEN
$repo = "fokper4-max/neurowings"
$outputDir = ".\build_output"
$isPublicRepo = $true  # Установите $false если репозиторий приватный

# Создаём папку для скачанных файлов
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  GitHub Actions Auto Downloader" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Отслеживаю сборку: $repo" -ForegroundColor Yellow
Write-Host "Папка для загрузки: $outputDir" -ForegroundColor Yellow
Write-Host ""

$headers = @{
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

# Добавляем токен если он установлен
if ($token) {
    $headers["Authorization"] = "Bearer $token"
}

$checkInterval = 30  # Проверять каждые 30 секунд
$maxWaitTime = 1800  # Максимум ждать 30 минут
$elapsed = 0

while ($elapsed -lt $maxWaitTime) {
    try {
        # Получаем последнюю сборку
        $runsUrl = "https://api.github.com/repos/$repo/actions/runs?per_page=1"
        $response = Invoke-RestMethod -Uri $runsUrl -Headers $headers

        if ($response.workflow_runs.Count -eq 0) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Нет активных сборок" -ForegroundColor Red
            break
        }

        $run = $response.workflow_runs[0]
        $status = $run.status
        $conclusion = $run.conclusion
        $runId = $run.id

        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Статус: $status | Результат: $conclusion" -ForegroundColor Cyan

        if ($status -eq "completed") {
            if ($conclusion -eq "success") {
                Write-Host ""
                Write-Host "✓ Сборка завершена успешно!" -ForegroundColor Green
                Write-Host "Скачиваю артефакты..." -ForegroundColor Yellow

                # Получаем список артефактов
                $artifactsUrl = "https://api.github.com/repos/$repo/actions/runs/$runId/artifacts"
                $artifacts = Invoke-RestMethod -Uri $artifactsUrl -Headers $headers

                if ($artifacts.artifacts.Count -eq 0) {
                    Write-Host "✗ Артефакты не найдены" -ForegroundColor Red
                    break
                }

                # Скачиваем каждый артефакт
                foreach ($artifact in $artifacts.artifacts) {
                    $artifactName = $artifact.name
                    $downloadUrl = $artifact.archive_download_url
                    $outputFile = Join-Path $outputDir "$artifactName.zip"

                    Write-Host "  → Скачиваю: $artifactName..." -ForegroundColor Cyan

                    Invoke-WebRequest -Uri $downloadUrl -Headers $headers -OutFile $outputFile

                    Write-Host "  ✓ Сохранено: $outputFile" -ForegroundColor Green

                    # Распаковываем
                    $extractPath = Join-Path $outputDir $artifactName
                    if (Test-Path $extractPath) {
                        Remove-Item $extractPath -Recurse -Force
                    }

                    Write-Host "  → Распаковываю..." -ForegroundColor Cyan
                    Expand-Archive -Path $outputFile -DestinationPath $extractPath -Force
                    Write-Host "  ✓ Распаковано в: $extractPath" -ForegroundColor Green
                }

                Write-Host ""
                Write-Host "=====================================" -ForegroundColor Green
                Write-Host "  ГОТОВО!" -ForegroundColor Green
                Write-Host "=====================================" -ForegroundColor Green
                Write-Host "Файлы сохранены в: $outputDir" -ForegroundColor Yellow
                Write-Host ""

                # Показываем содержимое
                Get-ChildItem -Path $outputDir -Recurse -Include "*.exe" | ForEach-Object {
                    Write-Host "→ .exe файл: $($_.FullName)" -ForegroundColor Cyan
                }

                break
            }
            else {
                Write-Host ""
                Write-Host "✗ Сборка завершилась с ошибкой: $conclusion" -ForegroundColor Red
                Write-Host "Откройте страницу для деталей: $($run.html_url)" -ForegroundColor Yellow
                break
            }
        }
        elseif ($status -eq "in_progress" -or $status -eq "queued") {
            Write-Host "  → Ожидание... (прошло $elapsed сек)" -ForegroundColor Gray
        }

        Start-Sleep -Seconds $checkInterval
        $elapsed += $checkInterval

    }
    catch {
        Write-Host ""
        Write-Host "✗ Ошибка: $($_.Exception.Message)" -ForegroundColor Red
        break
    }
}

if ($elapsed -ge $maxWaitTime) {
    Write-Host ""
    Write-Host "✗ Превышено время ожидания (30 минут)" -ForegroundColor Red
    Write-Host "Проверьте статус вручную: https://github.com/$repo/actions" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Нажмите любую клавишу для выхода..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
