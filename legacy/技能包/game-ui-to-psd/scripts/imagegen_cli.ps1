# Explicit CLI/API fallback only. Uses the official imagegen script unchanged.
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ImageArguments)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtimeSettings=Get-GameUiRuntime
if(-not (Test-Path -LiteralPath $runtimeSettings.imagegenCLI)){throw '缺少已配置的官方 ImageGen CLI；请核对技能包路径。'}
& $runtimeSettings.python -X utf8 $runtimeSettings.imagegenCLI @ImageArguments
exit $LASTEXITCODE
