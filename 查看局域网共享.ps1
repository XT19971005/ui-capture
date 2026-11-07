$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -X utf8 -B (Join-Path $PSScriptRoot 'tools/lan_server.py') --status
