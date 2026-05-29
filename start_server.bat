@echo off
REM HIDAKARAanalytics startup launcher (double-click)
chcp 65001 >nul
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0start_server.ps1"
