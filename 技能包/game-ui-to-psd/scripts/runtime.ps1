function Get-GameUiRuntime {
    $skillRoot = Split-Path -Parent $PSScriptRoot
    $skillItem = Get-Item -LiteralPath $skillRoot -Force
    if ($skillItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        $skillRoot = [string]@($skillItem.Target)[0]
    }
    $bundleRoot = Split-Path -Parent $skillRoot
    $workspaceRoot = Split-Path -Parent $bundleRoot
    $runtimeFile = if ($env:GAME_UI_PSD_RUNTIME) { $env:GAME_UI_PSD_RUNTIME } else { Join-Path $PSScriptRoot 'runtime.json' }
    $settings = @{}
    foreach ($property in (Get-Content -LiteralPath $runtimeFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties) { $settings[$property.Name] = $property.Value }
    $localFile = Join-Path (Split-Path -Parent $runtimeFile) 'runtime.local.json'
    if (Test-Path -LiteralPath $localFile) {
        foreach ($property in (Get-Content -LiteralPath $localFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties) { $settings[$property.Name] = $property.Value }
    }
    $roots = @{'@bundle/'=$bundleRoot;'@workspace/'=$workspaceRoot;'@skill/'=$skillRoot}
    foreach ($key in @('workspaceRoot','agPsd','canvas','svgpath','psdTools','imagegenSkill','imagegenCLI')) {
        foreach ($prefix in $roots.Keys) {
            if ($settings[$key] -is [string] -and $settings[$key].StartsWith($prefix)) { $settings[$key] = [IO.Path]::GetFullPath((Join-Path $roots[$prefix] $settings[$key].Substring($prefix.Length))); break }
        }
    }
    foreach ($key in @('node','python')) {
        if (-not [IO.Path]::IsPathRooted($settings[$key])) { $settings[$key] = (Get-Command $settings[$key] -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source }
    }
    return [pscustomobject]$settings
}
