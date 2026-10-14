[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Position=0,Mandatory=$true)][ValidateSet('doctor','init','status','build','verify','run','register','import','trace','smooth','review-init','review-check','selftest','finalize')][string]$Command,[string]$Project,[Parameter(ValueFromRemainingArguments=$true)][string[]]$ExtraArguments)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$settings=Get-GameUiRuntime
if($Command -eq 'doctor'){& $settings.node (Join-Path $PSScriptRoot 'doctor.cjs');exit $LASTEXITCODE}
if($Command -eq 'selftest'){& $settings.node (Join-Path $PSScriptRoot 'selftest.cjs') @ExtraArguments;exit $LASTEXITCODE}
if(-not $Project){throw '必须传入 -Project'}
$delivery=[IO.Path]::GetFullPath($Project);$work=Join-Path $delivery '1_过程'
if($Command -eq 'finalize'){& $settings.python -X utf8 (Join-Path $PSScriptRoot 'finalize_delivery.py') --project $delivery;exit $LASTEXITCODE}
if($Command -eq 'init'){foreach($dir in @('1_过程/01_素材','1_过程/02_结构','1_过程/03_检查','2_输出')){New-Item -ItemType Directory -Path (Join-Path $delivery $dir) -Force | Out-Null}}
elseif(-not (Test-Path -LiteralPath (Join-Path $work '02_结构/项目.json'))){throw '缺少两目录项目清单；旧项目先迁移'}
switch($Command){
 'register' {& $settings.node (Join-Path $PSScriptRoot 'register_asset.cjs') --project $work @ExtraArguments}
 'import' {& $settings.node (Join-Path $PSScriptRoot 'import_psd.cjs') --project $work @ExtraArguments}
 'trace' {& $settings.python -X utf8 (Join-Path $PSScriptRoot 'trace_shapes.py') --project $work @ExtraArguments}
 'smooth' {& $settings.python -X utf8 (Join-Path $PSScriptRoot 'smooth_paths.py') --project $work @ExtraArguments}
 'review-init' {& $settings.node (Join-Path $PSScriptRoot 'review.cjs') init --project $work}
 'review-check' {& $settings.node (Join-Path $PSScriptRoot 'review.cjs') check --project $work}
 default {& $settings.node (Join-Path $PSScriptRoot 'pipeline.cjs') $Command --project $work @ExtraArguments}
}
$result=$LASTEXITCODE
if($result -eq 0 -and $Command -eq 'init'){
 $file=Join-Path $work '02_结构/项目.json';$job=Get-Content -LiteralPath $file -Raw -Encoding utf8 | ConvertFrom-Json
 $temporary=[IO.Path]::GetFullPath((Join-Path $work $job.source));$out=[IO.Path]::GetFullPath((Join-Path $delivery '2_输出'))
 if(-not $temporary.StartsWith($out+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw '临时来源不在输出目录'}
 $name=[IO.Path]::GetFileName($delivery.TrimEnd([IO.Path]::DirectorySeparatorChar))
 $original=$name+'_原图'+[IO.Path]::GetExtension($temporary);$canonical=Join-Path $out $original
 if($temporary -ne $canonical){if(Test-Path -LiteralPath $canonical){if((Get-FileHash -LiteralPath $temporary).Hash -ne (Get-FileHash -LiteralPath $canonical).Hash){throw '原图名称冲突'};Remove-Item -LiteralPath $temporary}else{Move-Item -LiteralPath $temporary -Destination $canonical}}
 $job.source='../2_输出/'+$original;$job.outputName=$name+'_可编辑分层.psd'
 $job | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $file -Encoding utf8
}
if($result -eq 0 -and $Command -eq 'run'){& $settings.node (Join-Path $PSScriptRoot 'review.cjs') init --project $work;$result=$LASTEXITCODE}
if($result -eq 0 -and $Command -eq 'review-check'){& $settings.python -X utf8 (Join-Path $PSScriptRoot 'finalize_delivery.py') --project $delivery;$result=$LASTEXITCODE}
exit $result
