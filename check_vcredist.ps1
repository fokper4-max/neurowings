# Проверка Visual C++ Redistributable

Write-Host "Checking Visual C++ Redistributable..." -ForegroundColor Cyan
Write-Host ""

$installed = @()
$missing = @()

# Проверяем основные версии
$versions = @(
    @{Name="Visual C++ 2015-2022 x64"; Key="HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"},
    @{Name="Visual C++ 2019 x64"; Key="HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"},
    @{Name="Visual C++ 2017 x64"; Key="HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"}
)

foreach ($ver in $versions) {
    if (Test-Path $ver.Key) {
        $version = (Get-ItemProperty -Path $ver.Key -ErrorAction SilentlyContinue).Version
        if ($version) {
            Write-Host "[OK] $($ver.Name): $version" -ForegroundColor Green
            $installed += $ver.Name
        }
    }
}

if ($installed.Count -eq 0) {
    Write-Host "[!] Visual C++ Redistributable NOT FOUND!" -ForegroundColor Red
    Write-Host ""
    Write-Host "This is likely the cause of the problem!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Download and install:" -ForegroundColor Cyan
    Write-Host "https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "[OK] Visual C++ Redistributable is installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
