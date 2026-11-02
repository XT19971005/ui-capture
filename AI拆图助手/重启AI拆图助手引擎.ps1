[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$taskServer=Join-Path $taskRoot '开发源码/自动拆图/server.py'
try {
    $taskConnection=Invoke-RestMethod 'http://127.0.0.1:19217/connection' -TimeoutSec 3
} catch {
    & (Join-Path $taskRoot '启动AI拆图助手.ps1') -NoBrowser
    return
}
if($taskConnection.url -ne 'http://127.0.0.1:19217' -or -not $taskConnection.token){throw '本机引擎连接无效，未停止任何程序。'}
$taskHeaders=@{'X-Shijie-Token'=$taskConnection.token}
$taskHealth=Invoke-RestMethod 'http://127.0.0.1:19217/health' -Headers $taskHeaders -TimeoutSec 4
if($taskHealth.service -ne 'shijie-engine' -or $taskHealth.activeJobs -ne 0){throw '当前有任务正在执行，未重启。请等待任务结束后再运行。'}
$taskListener=Get-NetTCPConnection -LocalPort 19217 -State Listen
$taskProcess=Get-CimInstance Win32_Process -Filter "ProcessId = $($taskListener.OwningProcess)"
if(-not $taskProcess.CommandLine -or -not $taskProcess.CommandLine.Contains($taskServer)){throw '监听程序不属于当前AI拆图助手目录，未停止任何程序。'}
$taskHealth=Invoke-RestMethod 'http://127.0.0.1:19217/health' -Headers $taskHeaders -TimeoutSec 4
if($taskHealth.activeJobs -ne 0){throw '当前刚开始执行任务，未重启。'}
$taskEngineProcesses=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and $_.CommandLine.Contains($taskServer)})
foreach($taskEngineProcess in $taskEngineProcesses){
    Stop-Process -Id $taskEngineProcess.ProcessId -ErrorAction SilentlyContinue
}
foreach($taskEngineProcess in $taskEngineProcesses){
    Wait-Process -Id $taskEngineProcess.ProcessId -Timeout 8 -ErrorAction SilentlyContinue
}
& (Join-Path $taskRoot '启动AI拆图助手.ps1') -NoBrowser
Write-Host '引擎已更新。网页未刷新，当前未保存内容仍在原页面。保存工程后刷新可加载新版侧栏。'
