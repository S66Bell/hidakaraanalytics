# HIDAKARAanalytics 社内サーバー起動スクリプト
# 使い方:
#   1. PowerShell を開く
#   2. このスクリプトのあるフォルダで:
#        .\start_server.ps1
#   3. 同じLAN内の他のPCから http://<このPCのIP>:8501 でアクセス

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Set-Location $projectRoot

# 現在のPCのLAN IPアドレスを表示
Write-Host "=== このPCのLAN IPアドレス ===" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object IPAddress, InterfaceAlias |
    Format-Table -AutoSize

Write-Host ""
Write-Host "同じLAN内のPCからは以下のようなURLでアクセス可能:" -ForegroundColor Yellow
Write-Host "  http://<上のIPアドレス>:8501"
Write-Host ""

# 仮想環境のStreamlitを起動
$streamlit = Join-Path $projectRoot ".venv\Scripts\streamlit.exe"
if (-not (Test-Path $streamlit)) {
    Write-Host "ERROR: 仮想環境が見つかりません: $streamlit" -ForegroundColor Red
    Write-Host "セットアップ: python -m venv .venv; .venv\Scripts\pip.exe install -r requirements.txt" -ForegroundColor Red
    exit 1
}

Write-Host "HIDAKARAanalytics を起動します（停止するには Ctrl+C）..." -ForegroundColor Green
& $streamlit run "$projectRoot\app.py" `
    --server.address 0.0.0.0 `
    --server.port 8501 `
    --server.headless true `
    --browser.gatherUsageStats false
