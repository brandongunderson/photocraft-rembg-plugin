param([switch]$Offline, [switch]$DebugWorker, [switch]$SkipBuild, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$pluginRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot))
$pluginDist = Join-Path $pluginRoot 'dist'
$pluginStage = Join-Path $pluginDist ('stage-' + [Guid]::NewGuid().ToString('N'))
$pluginArchive = Join-Path $pluginDist 'PhotoCraft-Rembg.pcplugin'
$pluginProfile = if ($DebugWorker) { 'debug' } else { 'release' }
Push-Location $pluginRoot
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT') { throw 'This package targets Windows x86_64.' }
    & (Join-Path $PSScriptRoot 'fetch-assets.ps1') -Offline:$Offline -Python $Python
    & $Python (Join-Path $PSScriptRoot 'sync-panel-models.py') --check
    if ($LASTEXITCODE -ne 0) { throw 'Panel choices do not match the pinned model catalog.' }
    if (-not $SkipBuild) {
        $buildArgs = @('build', '--locked', '--bin', 'photocraft-rembg-worker', '--target-dir', 'target')
        if (-not $DebugWorker) { $buildArgs += '--release' }
        if ($Offline) { $buildArgs += '--offline' }
        & cargo @buildArgs
        if ($LASTEXITCODE -ne 0) { throw 'Plugin processing supervisor build failed.' }
        Push-Location (Join-Path $pluginRoot 'extension')
        try {
            $buildArgs = @('build', '--locked', '--release', '--target', 'wasm32-unknown-unknown', '--target-dir', 'target')
            if ($Offline) { $buildArgs += '--offline' }
            & cargo @buildArgs
            if ($LASTEXITCODE -ne 0) { throw 'Plugin panel build failed.' }
        } finally { Pop-Location }
    }
    $worker = Join-Path $pluginRoot "target/$pluginProfile/photocraft-rembg-worker.exe"
    $panel = Join-Path $pluginRoot 'extension/target/wasm32-unknown-unknown/release/photocraft_plugin_rembg.wasm'
    foreach ($builtFile in @($worker, $panel)) {
        if (-not (Test-Path -LiteralPath $builtFile -PathType Leaf)) { throw "Missing built plugin file: $builtFile" }
    }
    $workerBytes = [IO.File]::ReadAllBytes($worker)
    if ($workerBytes.Length -lt 64 -or $workerBytes[0] -ne 77 -or $workerBytes[1] -ne 90) { throw 'The processing supervisor is not a Windows executable.' }
    $peOffset = [BitConverter]::ToInt32($workerBytes, 60)
    if ($peOffset -lt 0 -or $peOffset -gt $workerBytes.Length - 6 -or
        [BitConverter]::ToUInt32($workerBytes, $peOffset) -ne 17744 -or
        [BitConverter]::ToUInt16($workerBytes, $peOffset + 4) -ne 34404) { throw 'The processing supervisor must target Windows x86_64.' }
    & $Python (Join-Path $PSScriptRoot 'collect-licenses.py')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency license collection failed.' }
    New-Item -ItemType Directory -Path $pluginStage -Force | Out-Null
    # The same authoring source generates the embedded panel descriptor and archive metadata.
    $pluginAuthoring = Get-Content -LiteralPath (Join-Path $pluginRoot 'authoring.json') -Raw | ConvertFrom-Json
    $pluginPackage = $pluginAuthoring.package | ConvertTo-Json -Depth 32
    [IO.File]::WriteAllText((Join-Path $pluginStage 'package.json'), $pluginPackage, [Text.UTF8Encoding]::new($false))
    New-Item -ItemType Directory -Path (Join-Path $pluginStage 'licenses/photocraft-sdk') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $pluginRoot 'extension/vendor/plugin-sdk/LICENSE-MIT') -Destination (Join-Path $pluginStage 'licenses/photocraft-sdk/LICENSE-MIT')
    Copy-Item -LiteralPath (Join-Path $pluginRoot 'extension/vendor/plugin-sdk/LICENSE-APACHE') -Destination (Join-Path $pluginStage 'licenses/photocraft-sdk/LICENSE-APACHE')
    Copy-Item -LiteralPath (Join-Path $pluginRoot 'extension/vendor/SDK-RELEASE.json') -Destination (Join-Path $pluginStage 'licenses/photocraft-sdk/SDK-RELEASE.json')
    foreach ($name in @('LICENSE', 'THIRD-PARTY-NOTICES.md', 'README.md', 'requirements.lock')) {
        Copy-Item -LiteralPath (Join-Path $pluginRoot $name) -Destination $pluginStage
    }
    Copy-Item -Path (Join-Path $pluginRoot 'licenses/*') -Destination (Join-Path $pluginStage 'licenses') -Recurse -Force
    Copy-Item -LiteralPath $worker -Destination $pluginStage
    Copy-Item -LiteralPath $panel -Destination (Join-Path $pluginStage 'plugin.pcext')
    New-Item -ItemType Directory -Path (Join-Path $pluginStage 'python'),(Join-Path $pluginStage 'runtime') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $pluginRoot 'python/worker.py') -Destination (Join-Path $pluginStage 'python/worker.py')
    Copy-Item -LiteralPath (Join-Path $pluginRoot 'python/model_manager.py') -Destination (Join-Path $pluginStage 'python/model_manager.py')
    foreach ($name in @('python-runtime.zip', 'runtime.json', 'models.json', 'model-catalog.json', 'model-catalog-provenance.json', 'assets.json', 'downloads.json', 'vc-runtime.json', 'python-packages.json', 'models', 'licenses')) {
        Copy-Item -LiteralPath (Join-Path $pluginRoot ('runtime/' + $name)) -Destination (Join-Path $pluginStage 'runtime') -Recurse
    }
    # Only the bounded runtime ZIP is shipped, never its build cache or a global Python install.
    & $Python (Join-Path $PSScriptRoot 'package-plugin.py') --root $pluginStage --output $pluginArchive
    if ($LASTEXITCODE -ne 0) { throw 'Plugin package validation failed.' }
    Write-Output "Installable plugin: $pluginArchive"
} finally {
    Pop-Location
    $stageResolved = [IO.Path]::GetFullPath($pluginStage)
    $distPrefix = [IO.Path]::GetFullPath($pluginDist).TrimEnd('\') + '\'
    if ($stageResolved.StartsWith($distPrefix, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $stageResolved)) {
        Remove-Item -LiteralPath $stageResolved -Recurse -Force
    }
}
