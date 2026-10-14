[CmdletBinding()]
param([switch]$CheckOnly,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($PSScriptRoot)
$python=Join-Path $root '依赖/运行环境/python/python.exe'
$pythonPth=Join-Path $root '依赖/运行环境/python/python310._pth'
$pythonDll=Join-Path $root '依赖/运行环境/python/python310.dll'
$node=Join-Path $root '依赖/运行环境/node/node.exe'
$server=Join-Path $root '开发源码/自动拆图/server.py'
$shortcutScript=Join-Path $root '创建拾界快捷方式.ps1'
$icon=Join-Path $root '插件程序/edge/favicon.ico'
$sharedNode=Join-Path (Split-Path -Parent $root) '技能包/依赖/Node/node_modules'
$ag=Join-Path $sharedNode 'ag-psd'
$canvas=Join-Path $sharedNode '@napi-rs/canvas'
foreach($file in @($python,$pythonPth,$pythonDll,$node,$server,$shortcutScript,$icon)){
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)){throw "缺少随包文件：$file"}
}
foreach($directory in @($ag,$canvas)){
    if(-not (Test-Path -LiteralPath $directory -PathType Container)){throw "缺少随包依赖：$directory"}
}
& $python -B -c 'import flask, requests, PIL, numpy, cv2, scipy, psd_tools, vtracer'
if($LASTEXITCODE -ne 0){throw '随包 Python 依赖检查失败。'}
Write-Host 'Python portable OK'
& $node --version
if($LASTEXITCODE -ne 0){throw '随包 Node 检查失败。'}
& $node -e 'require(process.argv[1]);require(process.argv[2])' $ag $canvas
if($LASTEXITCODE -ne 0){throw '随包 Node PSD 依赖检查失败。'}
if($CheckOnly){Write-Host '拾界便携环境检查通过。';return}
& (Join-Path $root '创建拾界快捷方式.ps1')

$manifest=Join-Path $root '开发源码/自动拆图/native-host.json'
if(-not (Test-Path -LiteralPath $manifest)){
    $default=@{name='cn.xt.shijie.engine';description='拾界本机引擎';path='';type='stdio';allowed_origins=@()}
    [IO.File]::WriteAllText($manifest,($default|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
$state=Join-Path $root '依赖/自动拆图/运行'
$temporary=Join-Path $root '依赖/运行临时'
New-Item -ItemType Directory -Path $state,$temporary -Force | Out-Null
$url='http://127.0.0.1:19217/ping'
function Test-ShijieServer {
    try {
        $response=Invoke-RestMethod -Uri $url -TimeoutSec 2
        return ($response.service -eq 'shijie-engine' -and $response.version -eq '0.9.0')
    } catch {return $false}
}
if(-not (Test-ShijieServer)){
    $previousTemp=$env:TEMP;$previousTmp=$env:TMP
    $previousPath=$env:PATH;$previousPython=$env:SHIJIE_PYTHON
    try {
        $env:TEMP=$temporary;$env:TMP=$temporary
        $env:SHIJIE_PYTHON=$python
        $env:PATH="$(Split-Path -Parent $python);$(Split-Path -Parent $node);$previousPath"
        $log=Join-Path $state '启动.log'
        Start-Process -FilePath $python -ArgumentList @('-B',('"'+$server+'"')) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $state '标准输出.log') -RedirectStandardError $log | Out-Null
    } finally {$env:TEMP=$previousTemp;$env:TMP=$previousTmp;$env:PATH=$previousPath;$env:SHIJIE_PYTHON=$previousPython}
    $ready=$false
    for($attempt=0;$attempt -lt 60;$attempt++){
        Start-Sleep -Milliseconds 200
        if(Test-ShijieServer){$ready=$true;break}
    }
    if(-not $ready){throw "本机引擎启动失败，请查看 $log"}
}
if(-not $NoBrowser){Start-Process 'http://127.0.0.1:19217/image-editor.html' | Out-Null}
Write-Host '拾界本机引擎已就绪。'
