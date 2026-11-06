$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$taskEntry = Join-Path $PSScriptRoot 'tools/desktop_worker.py'
if (-not (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'AI拆图助手/共享服务/connection.dat'))) { throw '请先运行“配置本机共享服务.ps1”。' }
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @(('"' + $taskEntry + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
if ($taskProcess.HasExited) { throw '本机服务未启动，可能已经运行；请运行“查看本机共享服务.ps1”检查。' }
Write-Host '本机接单程序已启动，正在检查连接；请在网页“共享服务”页面查看在线状态。'
