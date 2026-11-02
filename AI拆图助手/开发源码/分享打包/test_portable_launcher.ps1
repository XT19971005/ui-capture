$ErrorActionPreference='Stop'
$plugin=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../AI拆图助手'))
$launcher=Join-Path $plugin '启动AI拆图助手.ps1'
if(-not (Test-Path -LiteralPath $launcher)){throw '便携启动入口尚未实现'}
$oldPath=$env:PATH
try {
 $env:PATH="$env:SystemRoot/System32;$env:SystemRoot"
 & $launcher -CheckOnly
 if($LASTEXITCODE -ne 0){throw '隔离PATH启动自检失败'}
} finally {$env:PATH=$oldPath}
