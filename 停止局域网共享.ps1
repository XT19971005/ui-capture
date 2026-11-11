$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -X utf8 -B (Join-Path $PSScriptRoot 'tools/lan_https.py') --stop
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -X utf8 -B (Join-Path $PSScriptRoot 'tools/lan_server.py') --stop
