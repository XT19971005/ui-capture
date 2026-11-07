$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$taskEntry = Join-Path $PSScriptRoot 'tools/lan_server.py'
& $taskPython -X utf8 -B $taskEntry --prepare
if ($LASTEXITCODE -ne 0) { throw '无法准备共享服务；已运行时请使用“查看局域网共享.ps1”。' }
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-X','utf8','-B',('"'+$taskEntry+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
$taskState = Join-Path $env:LOCALAPPDATA 'AI拆图助手/局域网共享/status.json'
for ($taskAttempt=0; $taskAttempt -lt 45; $taskAttempt++) {
    Start-Sleep -Seconds 2
    if ($taskProcess.HasExited) { throw '共享服务未启动。请查看私有目录中的 status.json 错误类型并检查 Codex 登录、依赖和端口。' }
    if (Test-Path -LiteralPath $taskState) {
        $taskStatus = Get-Content -Raw -Encoding utf8 -LiteralPath $taskState | ConvertFrom-Json
        if ($taskStatus.running -and $taskStatus.pid -eq $taskProcess.Id) { & $taskPython -X utf8 -B $taskEntry --status; exit }
    }
}
Write-Host '启动仍在检查连接，请稍后运行“查看局域网共享.ps1”。'
