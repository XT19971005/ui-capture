[CmdletBinding()]
param([ValidatePattern('^[a-z0-9][a-z0-9-]{0,63}$')][string]$SkillName='game-ui-to-psd',[string]$CodexDirectory)
$ErrorActionPreference='Stop'
$bundleRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$workspaceRoot=Split-Path -Parent $bundleRoot
$skillRoot=Join-Path $bundleRoot $SkillName
if (-not (Test-Path -LiteralPath (Join-Path $skillRoot 'SKILL.md'))) { throw '完整技能包不存在。' }
if (-not $CodexDirectory) { $CodexDirectory=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'} }
$codexRoot=[IO.Path]::GetFullPath($CodexDirectory)
$skillsRoot=Join-Path $codexRoot 'skills'
$entryPath=[IO.Path]::GetFullPath((Join-Path $skillsRoot $SkillName))
if (-not $entryPath.StartsWith([IO.Path]::GetFullPath($skillsRoot)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '安装入口超出 skills 目录。' }
New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
if (Test-Path -LiteralPath $entryPath) {
    $entry=Get-Item -LiteralPath $entryPath -Force
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        if ([IO.Path]::GetFullPath([string]@($entry.Target)[0]) -ne $skillRoot) { throw '安装入口联接到另一个位置，请先核对其目标。' }
    } else {
        $archiveParent=[IO.Path]::GetFullPath((Join-Path $workspaceRoot ('归档/技能工具旧版/Codex同步前_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))))
        if (-not $archiveParent.StartsWith($workspaceRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '归档目标超出工作区。' }
        New-Item -ItemType Directory -Path $archiveParent -Force | Out-Null
        $archiveTarget=Join-Path $archiveParent $SkillName
        Move-Item -LiteralPath $entryPath -Destination $archiveTarget
        try { New-Item -ItemType Junction -Path $entryPath -Target $skillRoot -ErrorAction Stop | Out-Null } catch { Move-Item -LiteralPath $archiveTarget -Destination $entryPath; throw }
    }
} else { New-Item -ItemType Junction -Path $entryPath -Target $skillRoot -ErrorAction Stop | Out-Null }
$rule=Get-Content -LiteralPath (Join-Path $bundleRoot '维护约定.md') -Raw -Encoding UTF8
$rule=$rule.Replace('{{WORKSPACE_ROOT}}',$workspaceRoot.Replace('\','/'))
$start='<!-- ui-skill-storage:start -->';$end='<!-- ui-skill-storage:end -->'
foreach ($agentFile in @((Join-Path $codexRoot 'AGENTS.md'),(Join-Path $workspaceRoot 'AGENTS.md'))) {
    $content=if(Test-Path -LiteralPath $agentFile){Get-Content -LiteralPath $agentFile -Raw -Encoding UTF8}else{''}
    if ($content.Contains($start)) {
        $begin=$content.IndexOf($start);$finish=$content.IndexOf($end,$begin)
        if ($finish -lt 0) { throw '约定标记不完整，停止以保护已有指令。' }
        # Some older instruction files contain the storage block twice. Update
        # every complete block so a stale duplicate cannot contradict recovery.
        $blockPattern='(?s)'+[regex]::Escape($start)+'.*?'+[regex]::Escape($end)
        $content=[regex]::Replace($content,$blockPattern,[Text.RegularExpressions.MatchEvaluator]{param($match) $rule.TrimEnd()})
    } else { $content=$content.TrimEnd()+"`r`n`r`n"+$rule.TrimEnd()+"`r`n" }
    [IO.File]::WriteAllText($agentFile,$content,[Text.UTF8Encoding]::new($false))
}
$skillFile=Join-Path $skillRoot 'SKILL.md';$entryFile=Join-Path $entryPath 'SKILL.md'
if ((Get-FileHash -LiteralPath $skillFile -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $entryFile -Algorithm SHA256).Hash) { throw '入口内容不一致。' }
[pscustomobject]@{status='PASS';skill=$skillRoot;entry=$entryPath;sync='同一份文件';globalInstructions=(Join-Path $codexRoot 'AGENTS.md')} | ConvertTo-Json
