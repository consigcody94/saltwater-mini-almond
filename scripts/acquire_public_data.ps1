[CmdletBinding()]
param(
    [ValidateSet('references', 'rootstock-rnaseq')]
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
    $OutputRoot = if ($Profile -eq 'references') {
        Join-Path $projectRoot 'data\raw\ncbi_references'
    }
    else {
        Join-Path $projectRoot 'data\raw\PRJNA732909'
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

$referenceScript = Join-Path $PSScriptRoot 'public_data\Acquire-NcbiReferences.ps1'
$arguments = @{
    OutputRoot = $OutputRoot
    TimeoutSeconds = $TimeoutSeconds
}
if ($Execute) { $arguments.Execute = $true }
& $referenceScript @arguments
