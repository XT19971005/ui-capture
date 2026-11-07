#Requires -RunAsAdministrator
param([string]$ConfigPath = (Join-Path $env:LOCALAPPDATA 'AI拆图助手/局域网共享/site.json'))
$ErrorActionPreference = 'Stop'
$taskConfig = $ConfigPath
if (-not (Test-Path -LiteralPath $taskConfig)) { throw '请先以共享电脑的使用者身份启动局域网共享。' }
$taskSite = Get-Content -Raw -Encoding utf8 -LiteralPath $taskConfig | ConvertFrom-Json
$taskAddress = [System.Net.IPAddress]::Parse($taskSite.host)
if ($taskAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or $taskSite.port -ne 19218) { throw '局域网地址或端口无效。' }
$taskRuleName = 'AIImageSplitter-OfficeLAN-19218'
if (Get-NetFirewallRule -Name $taskRuleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $taskRuleName -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort 19218 -LocalAddress $taskSite.host -RemoteAddress LocalSubnet -Profile Any | Out-Null
} else {
    New-NetFirewallRule -Name $taskRuleName -DisplayName 'AI拆图助手：办公局域网共享' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 19218 -LocalAddress $taskSite.host -RemoteAddress LocalSubnet -Profile Any | Out-Null
}
Write-Host '已仅允许本机19218端口接收同一局域网访问。'
