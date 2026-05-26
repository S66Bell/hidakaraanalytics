@echo off
REM HIDAKARAanalytics 社内サーバー起動（ダブルクリック起動用）
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0start_server.ps1"
