param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$pluginRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot))
$runtimeRoot = Join-Path $pluginRoot 'runtime'
$runtimePrefix = $runtimeRoot.TrimEnd('\') + '\'
$cacheRoot = Join-Path $runtimeRoot 'cache'
$manifest = Get-Content -LiteralPath (Join-Path $runtimeRoot 'vc-runtime.json') -Raw | ConvertFrom-Json
function Test-PinnedFile($Path, $Sha256, $Bytes) {
    (Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-Item -LiteralPath $Path).Length -eq $Bytes -and
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256
}
function Runtime-Path($Relative) {
    $resolved = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $Relative))
    if (-not $resolved.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime path escapes package.' }
    return $resolved
}
$missing = @($manifest.files | Where-Object { -not (Test-PinnedFile (Runtime-Path $_.path) $_.sha256 $_.size) })
if ($missing.Count -eq 0) { Write-Output "Verified app-local Microsoft VC runtime $($manifest.version)."; return }
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
$archive = Join-Path $cacheRoot 'vc-redist-x64-14.51.36247.exe'
if (-not (Test-PinnedFile $archive $manifest.archiveSha256 $manifest.archiveBytes)) {
    if ($Offline) { throw 'Pinned VC runtime archive is not cached. Run fetch-assets.ps1 online first.' }
    $download = $archive + '.part'
    Invoke-WebRequest -Uri $manifest.url -OutFile $download -UserAgent 'Photocraft-plugin-dev'
    if (-not (Test-PinnedFile $download $manifest.archiveSha256 $manifest.archiveBytes)) { throw 'VC runtime archive checksum/size mismatch.' }
    Move-Item -LiteralPath $download -Destination $archive -Force
}
$cabTar = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)) 'System32/tar.exe'
if (-not (Test-Path -LiteralPath $cabTar -PathType Leaf)) { throw 'Windows system tar.exe is required for cabinet extraction.' }
$extractRoot = Join-Path $cacheRoot ('vc-extract-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
try {
    # Read pinned cabinet data; never execute the redistributable or install system files.
    $bytes = [IO.File]::ReadAllBytes($archive)
    $offset = [int]$manifest.payloadOffset
    $length = [int]$manifest.payloadSize
    if ($offset -lt 0 -or $length -lt 36 -or $offset -gt $bytes.Length - $length) { throw 'Invalid pinned cabinet range.' }
    $cabinet = [byte[]]::new($length)
    [Array]::Copy($bytes, $offset, $cabinet, 0, $length)
    $cabinetPath = Join-Path $extractRoot 'payload.cab'
    [IO.File]::WriteAllBytes($cabinetPath, $cabinet)
    & $cabTar -xf $cabinetPath -C $extractRoot $manifest.minimumMember
    if ($LASTEXITCODE -ne 0) { throw 'VC runtime cabinet extraction failed.' }
    $members = @($manifest.files | Where-Object { $_.member } | ForEach-Object { $_.member })
    & $cabTar -xf (Join-Path $extractRoot $manifest.minimumMember) -C $extractRoot @members
    if ($LASTEXITCODE -ne 0) { throw 'VC runtime DLL extraction failed.' }
    foreach ($asset in $manifest.files) {
        $destination = Runtime-Path $asset.path
        New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
        if ($asset.member) {
            $source = Join-Path $extractRoot $asset.member
            if (-not (Test-PinnedFile $source $asset.sha256 $asset.size)) { throw "VC DLL checksum mismatch: $($asset.path)" }
            Copy-Item -LiteralPath $source -Destination $destination -Force
        } elseif (-not (Test-PinnedFile $destination $asset.sha256 $asset.size)) {
            if ($Offline) { throw "Pinned license is missing: $($asset.path)" }
            $download = $destination + '.part'
            Invoke-WebRequest -Uri $asset.url -OutFile $download -UserAgent 'Photocraft-plugin-dev'
            if (-not (Test-PinnedFile $download $asset.sha256 $asset.size)) { throw 'The official VC license changed; review and update its pin deliberately.' }
            Move-Item -LiteralPath $download -Destination $destination -Force
        }
    }
} finally {
    $extractResolved = [IO.Path]::GetFullPath($extractRoot)
    $cachePrefix = [IO.Path]::GetFullPath($cacheRoot).TrimEnd('\') + '\'
    if ($extractResolved.StartsWith($cachePrefix, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $extractResolved)) {
        Remove-Item -LiteralPath $extractResolved -Recurse -Force
    }
}
