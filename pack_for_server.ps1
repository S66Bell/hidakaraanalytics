$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$packageName = "HIDAKARAanalytics_$timestamp"
$desktop = [Environment]::GetFolderPath("Desktop")
$stage = Join-Path $env:TEMP $packageName

Write-Host "=== Packaging start ===" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"
Write-Host "Staging dir : $stage"
Write-Host ""

$running = Get-Process | Where-Object { $_.ProcessName -eq 'python' -and ($_.Path -like "*motosuanalytics*" -or $_.Path -like "*HIDAKARAanalytics*") }
if ($running) {
    Write-Host "WARNING: Streamlit appears to be running. Stop it first." -ForegroundColor Yellow
    $resp = Read-Host "Continue anyway? (y/N)"
    if ($resp -ne "y") { exit 1 }
}

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

Write-Host "Copying files..." -ForegroundColor Cyan

$robocopyArgs = @(
    $projectRoot, $stage,
    "/E",
    "/XD", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    "/XF", "*.pyc", "*.pyo", "*.duckdb.wal", "test_smoke.duckdb", "test_reports.duckdb",
    "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
)
& robocopy @robocopyArgs | Out-Null

$reportsDir = Join-Path $stage "data\reports"
if (Test-Path $reportsDir) {
    Get-ChildItem $reportsDir -File -Include "*.xlsx", "*.pdf" -Recurse | Remove-Item -Force
}

$totalSize = (Get-ChildItem $stage -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Copy complete: {0:N1} MB" -f ($totalSize / 1MB)) -ForegroundColor Green

$zipPath = Join-Path $desktop "$packageName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Write-Host ""
Write-Host "Compressing to ZIP..." -ForegroundColor Cyan
Compress-Archive -Path "$stage\*" -DestinationPath $zipPath -CompressionLevel Optimal

$zipSize = (Get-Item $zipPath).Length
Write-Host "Done!" -ForegroundColor Green
Write-Host ""
Write-Host "ZIP file : $zipPath" -ForegroundColor Yellow
Write-Host ("ZIP size : {0:N1} MB" -f ($zipSize / 1MB)) -ForegroundColor Yellow
Write-Host ""
Write-Host "Transfer this ZIP to the new server PC via USB / shared folder / OneDrive." -ForegroundColor Cyan
Write-Host "Then follow DEPLOYMENT.md (Phase 2 onwards) on the new PC." -ForegroundColor Cyan

Remove-Item $stage -Recurse -Force
