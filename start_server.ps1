# HIDAKARAanalytics 社内サーバー起動スクリプト
# 使い方:
#   1. PowerShell で `.\start_server.ps1` を実行
#      または start_server.bat をダブルクリック
#   2. 同じLAN内の他のPCから http://<このPCのIP>:8501 でアクセス

$ErrorActionPreference = "Stop"

# $PSScriptRoot が空のときのフォールバック（dot-source や ISE 経由など）
if ($PSScriptRoot) {
    $projectRoot = $PSScriptRoot
} elseif ($MyInvocation.MyCommand.Path) {
    $projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    $projectRoot = (Get-Location).Path
}
if (-not $projectRoot) {
    Write-Host "ERROR: プロジェクトルートを特定できません。PowerShell で 'cd <project>' してから .\start_server.ps1 を実行してください。" -ForegroundColor Red
    exit 1
}
Set-Location -LiteralPath $projectRoot
Write-Host "Project root: $projectRoot" -ForegroundColor DarkGray

# 現在のPCのLAN IPアドレスを表示
Write-Host "=== このPCのLAN IPアドレス ===" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object IPAddress, InterfaceAlias |
    Format-Table -AutoSize

Write-Host ""
Write-Host "同じLAN内のPCからは以下のURLでアクセス可能:" -ForegroundColor Yellow
Write-Host "  http://<上のIPアドレス>:8501"
Write-Host ""

# 仮想環境の Streamlit パス（Join-Path を避け、文字列連結で安全に組み立て）
$streamlit = "$projectRoot\.venv\Scripts\streamlit.exe"
$appPy     = "$projectRoot\app.py"

if (-not (Test-Path -LiteralPath $streamlit)) {
    Write-Host "ERROR: 仮想環境が見つかりません: $streamlit" -ForegroundColor Red
    Write-Host "セットアップ手順:" -ForegroundColor Red
    Write-Host "  python -m venv .venv" -ForegroundColor Red
    Write-Host "  .venv\Scripts\pip install --upgrade pip" -ForegroundColor Red
    Write-Host "  .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $appPy)) {
    Write-Host "ERROR: app.py が見つかりません: $appPy" -ForegroundColor Red
    exit 1
}

Write-Host "HIDAKARAanalytics を起動します（停止するには Ctrl+C）..." -ForegroundColor Green
& $streamlit run $appPy `
    --server.address 0.0.0.0 `
    --server.port 8501 `
    --server.headless true `
    --browser.gatherUsageStats false
