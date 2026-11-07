$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $taskPython -X utf8 -B (Join-Path $PSScriptRoot 'tools/build_lan_launcher.py')
if ($LASTEXITCODE -ne 0) { throw '启动器更新未完成，请先配置本机局域网共享；旧文件不会被覆盖。' }
