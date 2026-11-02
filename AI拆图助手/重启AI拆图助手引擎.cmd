@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0重启AI拆图助手引擎.ps1"
if errorlevel 1 pause
