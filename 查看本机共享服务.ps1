$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'tools/desktop_worker.py') --status
