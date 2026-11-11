$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
& $taskPython -X utf8 -B (Join-Path $PSScriptRoot 'lan_https.py') --check *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '正在启动局域网共享，请稍候……'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $taskRoot '启动局域网共享.ps1')
    if ($LASTEXITCODE -ne 0) { throw '共享服务启动失败，请将窗口中的错误信息发给维护人员。' }
}
& $taskPython -X utf8 -B (Join-Path $PSScriptRoot 'lan_https.py') --check
if ($LASTEXITCODE -ne 0) { throw '网页尚未就绪，请稍后再试。' }
if ($env:AI_SPLIT_LAUNCH_CHECK -ne '1') {
    Start-Process -FilePath (Join-Path $taskRoot '同事网页入口/打开AI拆图助手.cmd') -WindowStyle Hidden
}
Write-Host '局域网共享版已就绪。'
