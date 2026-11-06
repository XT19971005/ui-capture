$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '请先安装服务器源码的 Python 运行依赖。' }
& $taskPython (Join-Path $PSScriptRoot 'tools/desktop_worker.py') --configure
if ($LASTEXITCODE -ne 0) { throw '共享服务未配置成功，请检查上方提示。' }
