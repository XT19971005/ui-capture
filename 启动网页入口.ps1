$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$taskEntry = Join-Path $PSScriptRoot 'tools/lan_https.py'
$taskStatusPath = Join-Path $env:LOCALAPPDATA 'AI拆图助手/局域网共享/https-status.json'
& $taskPython -X utf8 -B $taskEntry --prepare
if ($LASTEXITCODE -ne 0) { throw '无法准备HTTPS网页入口。' }
if (Test-Path -LiteralPath $taskStatusPath) {
    $taskStatus = Get-Content -Raw -Encoding utf8 -LiteralPath $taskStatusPath | ConvertFrom-Json
    $taskNow = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    if ($taskStatus.running -and ($taskNow - $taskStatus.heartbeat) -lt 20) {
        & $taskPython -X utf8 -B $taskEntry --check
        if ($LASTEXITCODE -ne 0) { throw '网页地址或证书可能已变化；请先保存工程，再停止并重启局域网共享。' }
        Write-Host ('网页入口正在运行：' + $taskStatus.url)
        return
    }
}
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-X','utf8','-B',('"'+$taskEntry+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
$taskStarted = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
for ($taskAttempt=0; $taskAttempt -lt 30; $taskAttempt++) {
    Start-Sleep -Seconds 1
    if ($taskProcess.HasExited) { throw 'HTTPS入口未启动，请检查私有目录https-status.json中的错误类型。' }
    if (Test-Path -LiteralPath $taskStatusPath) {
        $taskStatus = Get-Content -Raw -Encoding utf8 -LiteralPath $taskStatusPath | ConvertFrom-Json
        if ($taskStatus.running -and $taskStatus.heartbeat -ge $taskStarted) {
            & $taskPython -X utf8 -B $taskEntry --check
            if ($LASTEXITCODE -ne 0) { throw 'HTTPS验证未通过，请检查入口地址和证书。' }
            Write-Host ('网页入口：' + $taskStatus.url)
            Write-Host '将“同事网页入口”文件夹发给同事；首次导入信任证书，以后直接打开网页快捷方式。'
            return
        }
    }
}
throw 'HTTPS入口尚未就绪，请检查https-status.json。'
