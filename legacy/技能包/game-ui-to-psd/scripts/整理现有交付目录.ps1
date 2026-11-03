$ErrorActionPreference='Stop'
$workspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$deliveryBase=Join-Path $workspace '交付包'
function Check-Target([string]$target){
 $full=[IO.Path]::GetFullPath($target)
 if(-not $full.StartsWith($deliveryBase+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw "目标不在交付包: $full"}
 return $full
}
$projects=@(
 @('欢乐斗地主_2022春节主题曲','欢乐斗地主_2022春节主题曲'),
 @('开局迎好运_海报拆分_PSD_20261010','开局迎好运'),
 @('太白诗仙_UI拆分_PSD_20261010','太白诗仙')
)
$records=@()
foreach($pair in $projects){
 $src=Check-Target (Join-Path $deliveryBase $pair[0]);$dst=Check-Target (Join-Path $deliveryBase $pair[1])
 if($src -ne $dst){if(Test-Path -LiteralPath $dst){throw "新名称已存在: $dst"};Move-Item -LiteralPath $src -Destination $dst}
 if(Test-Path -LiteralPath (Join-Path $dst '过程')){
  foreach($p in @(@('输入','1_输入'),@('过程','2_过程'),@('输出','3_输出'))){$from=Check-Target (Join-Path $dst $p[0]);$to=Check-Target (Join-Path $dst $p[1]);if(Test-Path -LiteralPath $to){throw '编号目录已存在'};Move-Item -LiteralPath $from -Destination $to}
 }elseif(Test-Path -LiteralPath (Join-Path $dst '03_结构/项目.json')){
  $job=Get-Content -LiteralPath (Join-Path $dst '03_结构/项目.json') -Raw -Encoding utf8 | ConvertFrom-Json
  foreach($name in @('1_输入','2_过程','3_输出')){New-Item -ItemType Directory -Path (Check-Target (Join-Path $dst $name)) | Out-Null}
  $source=Check-Target (Join-Path $dst $job.source);$psd=Check-Target (Join-Path $dst ('04_输出/'+$job.outputName))
  foreach($p in @(@($source,(Join-Path $dst ('1_输入/'+[IO.Path]::GetFileName($source)))),@($source,(Join-Path $dst ('3_输出/'+[IO.Path]::GetFileName($source)))),@($psd,(Join-Path $dst ('3_输出/'+$job.outputName))))){$to=Check-Target $p[1];Copy-Item -LiteralPath $p[0] -Destination $to;if((Get-FileHash -LiteralPath $p[0]).Hash -ne (Get-FileHash -LiteralPath $to).Hash){throw '复制核验失败'}}
  $work=Check-Target (Join-Path $dst '2_过程/工作区');New-Item -ItemType Directory -Path $work | Out-Null
  foreach($item in Get-ChildItem -LiteralPath $dst){if($item.Name -in @('1_输入','2_过程','3_输出')){continue};$to=Check-Target (Join-Path $work $item.Name);Move-Item -LiteralPath $item.FullName -Destination $to}
 }
 $children=@((Get-ChildItem -LiteralPath $dst).Name)
 if(($children | Sort-Object) -join ',' -ne '1_输入,2_过程,3_输出'){throw '目录未整理完成'}
 $records+=[pscustomobject]@{项目=$pair[1];原名=$pair[0];目录=$children;输出=@((Get-ChildItem -LiteralPath (Join-Path $dst '3_输出')).Name)}
}
$records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace '技能包/game-ui-to-psd/目录整理记录.json') -Encoding utf8
$records | ConvertTo-Json -Depth 5
