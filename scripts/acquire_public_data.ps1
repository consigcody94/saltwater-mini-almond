[CmdletBinding()]
param(
    [ValidateSet('references', 'phase2-small', 'rootstock-rnaseq')]
    [string]$Profile = 'references',
    [switch]$Execute,
    [string]$OutputRoot,
    [switch]$AcknowledgeMissingRunTreatmentKey,
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = switch ($Profile) {
        'references' { Join-Path $projectRoot 'data\raw\ncbi_references' }
        'phase2-small' { Join-Path $projectRoot 'data\raw\phase2_small' }
        'rootstock-rnaseq' { Join-Path $projectRoot 'data\raw\PRJNA732909' }
    }
}

if ($Profile -eq 'rootstock-rnaseq') {
    Write-Output 'PRJNA732909 contains 24 paired-end libraries and about 40.539 GiB of canonical compressed FASTQ files.'
    Write-Output 'Repository metadata lacks a verified run-to-treatment key; the audited manifest remains the source of run accessions and ENA MD5 metadata.'
    Write-Output 'The unsuffixed ENA FASTQs are alternate generated representations and must never be added to the canonical _1/_2 pairs.'

    if ($Execute) {
        if (-not $AcknowledgeMissingRunTreatmentKey) {
            throw 'PRJNA732909 acquisition is gated: the verified run-to-treatment key is missing.'
        }
        throw 'This repository intentionally does not implement FASTQ acquisition. Resolve and verify the run-to-treatment key before adding a separately reviewed RNA-seq downloader.'
    }

    Write-Warning 'DRY RUN ONLY: no RNA-seq downloader is implemented and no files or directories were created.'
    return
}

if ($Profile -eq 'phase2-small') {
    $phase2Script = Join-Path $PSScriptRoot 'public_data\phase2\Acquire-Phase2PublicData.ps1'
    $phase2Arguments = @{
        Profile = 'All'
        OutputRoot = $OutputRoot
        TimeoutSeconds = $TimeoutSeconds
    }
    if ($Execute) { $phase2Arguments.Execute = $true }
    & $phase2Script @phase2Arguments
    return
}

$referenceScript = Join-Path $PSScriptRoot 'public_data\Acquire-NcbiReferences.ps1'
$arguments = @{
    OutputRoot = $OutputRoot
    TimeoutSeconds = $TimeoutSeconds
}
if ($Execute) { $arguments.Execute = $true }
& $referenceScript @arguments
