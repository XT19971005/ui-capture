[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$icon=Join-Path $root '插件程序/edge/favicon.ico'
$launcher=Join-Path $PSScriptRoot '启动AI拆图助手.ps1'
foreach($file in @($icon,$launcher)){
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)){throw "缺少随包文件：$file"}
}
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut((Join-Path $PSScriptRoot 'AI拆图助手.lnk'))
$shortcut.TargetPath=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$shortcut.Arguments='-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$launcher+'"'
$shortcut.WorkingDirectory=$root
$shortcut.IconLocation=$icon+',0'
$shortcut.Description='AI拆图助手 · 网页编辑与图片拆分'
$shortcut.WindowStyle=7
$shortcut.Save()
Write-Host '已创建紫色AI拆图助手图标的启动快捷方式。'
