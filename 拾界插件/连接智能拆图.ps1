[CmdletBinding()]
param([string]$Python,[ValidatePattern('^[a-p]{32}$')][string]$ExtensionId)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($PSScriptRoot)
$engine=Join-Path $root '开发源码/自动拆图'
if(-not $Python){
    $bundled=Join-Path $root '依赖/运行环境/python/python.exe'
    if(Test-Path -LiteralPath $bundled -PathType Leaf){$Python=$bundled}
}
if(-not $Python){
    $pythonCommand=Get-Command python -ErrorAction SilentlyContinue
    if($pythonCommand){$Python=$pythonCommand.Source}
    else{
        $launcher=Get-Command py -ErrorAction SilentlyContinue
        if($launcher){$Python=& $launcher.Source -3.10 -c 'import sys; print(sys.executable)'}
    }
}
if(-not $ExtensionId){
    $profileRoot=Join-Path $env:LOCALAPPDATA 'Microsoft/Edge/User Data'
    $extensionPath=[IO.Path]::GetFullPath((Join-Path $root '插件程序/edge')).TrimEnd('\')
    $matches=@()
    if(Test-Path -LiteralPath $profileRoot){
        foreach($preferences in Get-ChildItem -LiteralPath $profileRoot -Filter Preferences -File -Recurse -ErrorAction SilentlyContinue){
            try {
                $settings=(Get-Content -LiteralPath $preferences.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).extensions.settings
                foreach($entry in $settings.PSObject.Properties){
                    if($entry.Name -cmatch '^[a-p]{32}$' -and $entry.Value.path){
                        $installed=[IO.Path]::GetFullPath([string]$entry.Value.path).TrimEnd('\')
                        if($installed -ieq $extensionPath){$matches+= $entry.Name}
                    }
                }
            } catch {}
        }
    }
    $matches=@($matches | Sort-Object -Unique)
    if($matches.Count -eq 1){$ExtensionId=$matches[0]}
    else{throw '请在 edge://extensions 打开开发者模式，复制拾界扩展 ID，并用 -ExtensionId 指定。'}
}
if(-not $Python -or -not (Test-Path -LiteralPath $Python -PathType Leaf)){throw '请先安装 Python 3.10，或使用 -Python 指定自己的 Python 路径。'}
$Python=[IO.Path]::GetFullPath($Python)
$version=& $Python -c 'import sys; print(sys.version_info.major,sys.version_info.minor,sep=chr(46))'
if($LASTEXITCODE -ne 0 -or $version -ne '3.10'){throw '拾界随包原生依赖要求 Python 3.10。'}
$cmdFile=Join-Path $engine 'native-host.cmd'
$bundledNode=Join-Path $root '依赖/运行环境/node'
$pythonDirectory=Split-Path -Parent $Python
$cmd="@echo off`r`nset `"SHIJIE_PYTHON=$Python`"`r`nset `"PATH=$pythonDirectory;$bundledNode;%PATH%`"`r`n`"$Python`" -B `"%~dp0native_host.py`"`r`n"
[IO.File]::WriteAllText($cmdFile,$cmd,[Text.UTF8Encoding]::new($false))
$manifest=Join-Path $engine 'native-host.json'
$settings=@{name='cn.xt.shijie.engine';description='拾界本机 Codex 图片拆分';path=$cmdFile;type='stdio';allowed_origins=@("chrome-extension://$ExtensionId/")}
[IO.File]::WriteAllText($manifest,($settings|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$key='HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\cn.xt.shijie.engine'
New-Item -Path $key -Force | Out-Null
Set-Item -LiteralPath $key -Value $manifest
Write-Host '拾界本机连接已安装。重新加载 Edge 扩展后，连接、登录、上传和 PSD 导出均在网页操作。'
