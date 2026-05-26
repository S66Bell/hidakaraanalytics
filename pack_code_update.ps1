$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$packageName = "HIDAKARAanalytics_codeupdate_$timestamp"
$desktop = [Environment]::GetFolderPath("Desktop")
$stage = Join-Path $env:TEMP $packageName

Write-Host "=== Code-only update package ===" -ForegroundColor Cyan
Write-Host "Includes: source code / scripts / docs / fonts (NO data/)"
Write-Host "Use this to update an already-running server without touching its DB."
Write-Host ""
Write-Host "Project root: $projectRoot"
Write-Host "Staging dir : $stage"
Write-Host ""

if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

Write-Host "Copying files..." -ForegroundColor Cyan

# /XD: Exclude directories (incl. data/ to protect server DB)
# /XF: Exclude files
$robocopyArgs = @(
    $projectRoot, $stage,
    "/E",
    "/XD", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", "data", ".git", ".claude",
    "/XF", "*.pyc", "*.pyo", "HIDAKARAanalytics_*.zip",
    "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
)
& robocopy @robocopyArgs | Out-Null

# Re-create empty data/ subfolders with .gitkeep so they exist after extraction
New-Item -ItemType Directory -Path "$stage\data\raw" -Force | Out-Null
New-Item -ItemType Directory -Path "$stage\data\reports" -Force | Out-Null
"" | Out-File -FilePath "$stage\data\raw\.gitkeep" -Encoding utf8 -NoNewline
"" | Out-File -FilePath "$stage\data\reports\.gitkeep" -Encoding utf8 -NoNewline

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
Write-Host "=== Server PC update instructions ===" -ForegroundColor Cyan
Write-Host "1. Transfer this ZIP to the server PC."
Write-Host "2. On the server PC, stop Streamlit (close the black window or stop the Python process)."
Write-Host "3. Open the ZIP. Select all top-level files/folders inside it and"
Write-Host "   COPY them into C:\HIDAKARAanalytics\ (the existing project folder)"
Write-Host "   - When asked, choose 'Replace files in the destination'."
Write-Host "   - The data/ folder in ZIP is EMPTY so the server's existing DB"
Write-Host "     will NOT be overwritten."
Write-Host "4. Restart Streamlit (run start_server.bat)."
Write-Host ""
Write-Host "Server's data/warehouse.duckdb is safe (not included in this ZIP)."

Remove-Item $stage -Recurse -Force
