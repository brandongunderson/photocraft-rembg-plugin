param([switch]$Offline, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'fetch-vc-runtime.ps1') -Offline:$Offline
$runtimeArgs = @((Join-Path $PSScriptRoot 'prepare-runtime.py'))
if ($Offline) { $runtimeArgs += '--offline' }
& $Python @runtimeArgs
if ($LASTEXITCODE -ne 0) { throw 'Pinned private runtime preparation failed.' }
