[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$OutputRoot,
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $OutputRoot = Join-Path $repositoryRoot 'data\raw\ncbi_references'
}
Import-Module (Join-Path $PSScriptRoot 'PublicDataDownloader.psm1') -Force

$plan = @(Get-ReferenceAssemblyPlan)
$knownComponentBytes = [int64](($plan | Where-Object { $null -ne $_.KnownComponentBytes } | Measure-Object -Property KnownComponentBytes -Sum).Sum)

Write-Host 'AlmondLab NCBI reference acquisition plan'
Write-Host ('Mode: {0}' -f $(if ($Execute) { 'EXECUTE' } else { 'DRY RUN (no files or directories will be created)' }))
Write-Host ('Output root: {0}' -f [IO.Path]::GetFullPath($OutputRoot))
Write-Host 'Scope: exactly four NCBI reference assembly packages; no SRA/ENA/FASTQ downloads.'
Write-Host ('Known-size lower-bound component: {0:N1} MB ({1:N1} MiB; Nonpareil compressed genomic FASTA only).' -f ($knownComponentBytes / 1000000), ($knownComponentBytes / 1MB))
Write-Warning 'Full NCBI package sizes are not exposed for all four accessions. Total required disk space is UNKNOWN; the 72.7 MB figure is not a package-total estimate.'

foreach ($item in $plan) {
    Write-Host ('  {0} | {1} {2} | {3}' -f $item.Accession, $item.Organism, $item.Cultivar, $item.Assembly)
    Write-Host ('    {0}' -f $item.PackageUrl)
}

if (-not $Execute) {
    $plan | Select-Object Accession, Organism, Cultivar, Assembly, PackageUrl, ReportUrl
    return
}

$null = New-Item -ItemType Directory -Path $OutputRoot -Force
try {
    $drive = Get-DestinationDriveInfo -Path $OutputRoot
    if ($drive.IsReady) {
        Write-Host ('Destination volume {0}: {1:N2} GiB available of {2:N2} GiB total.' -f $drive.Name, ($drive.AvailableFreeSpace / 1GB), ($drive.TotalSize / 1GB))
        Write-Warning 'Because three complete package sizes are unknown, free-space sufficiency cannot be proven in advance.'
    }
    else {
        Write-Warning "Destination volume $($drive.Name) is not ready; available disk space cannot be reported."
    }
}
catch {
    Write-Warning "Available disk space could not be determined with DriveInfo: $($_.Exception.Message)"
}

$results = New-Object Collections.Generic.List[object]
$failures = New-Object Collections.Generic.List[string]

foreach ($item in $plan) {
    $assemblyRoot = Join-Path $OutputRoot $item.Accession
    $requestRoot = Join-Path $assemblyRoot 'requests'
    $metadataRoot = Join-Path $assemblyRoot 'metadata'
    $packageRoot = Join-Path $assemblyRoot 'package'
    $packagePath = Join-Path $packageRoot 'ncbi_dataset.zip'
    $reportPath = Join-Path $metadataRoot 'dataset_report.json'
    $catalogPath = Join-Path $metadataRoot 'dataset_catalog.json'

    try {
        $null = New-Item -ItemType Directory -Path $requestRoot, $metadataRoot, $packageRoot -Force
        $results.Add((Write-TextArtifact -LiteralPath (Join-Path $requestRoot 'package.url.txt') -Content ($item.PackageUrl + [Environment]::NewLine)))
        $results.Add((Write-TextArtifact -LiteralPath (Join-Path $requestRoot 'dataset_report.url.txt') -Content ($item.ReportUrl + [Environment]::NewLine)))

        Write-Host ('[{0}] Fetching dataset report...' -f $item.Accession)
        $reportResult = Invoke-StreamDownload -Uri $item.ReportUrl -DestinationPath $reportPath -TimeoutSeconds $TimeoutSeconds -Validator {
            param($path) Test-JsonDocument -LiteralPath $path
        }
        $results.Add($reportResult)

        Write-Host ('[{0}] Fetching assembly package...' -f $item.Accession)
        $packageResult = Invoke-StreamDownload -Uri $item.PackageUrl -DestinationPath $packagePath -TimeoutSeconds $TimeoutSeconds -Validator {
            param($path) Test-ZipArchive -LiteralPath $path
        }
        $results.Add($packageResult)

        $catalogResult = Export-DatasetCatalog -PackagePath $packagePath -DestinationPath $catalogPath -Force:($packageResult.Status -eq 'Downloaded')
        if ($catalogResult) {
            $results.Add($catalogResult)
        }
        else {
            Write-Warning "[$($item.Accession)] NCBI package did not contain dataset_catalog.json; no catalog was fabricated."
        }
    }
    catch {
        $message = '[{0}] {1}' -f $item.Accession, $_.Exception.Message
        $failures.Add($message)
        Write-Error $message -ErrorAction Continue
    }
}

Write-Host ''
Write-Host 'Acquisition results:'
$results | Select-Object Status, Bytes, Sha256, Path | Format-Table -AutoSize

if ($failures.Count -gt 0) {
    throw ('Acquisition failed for {0} accession(s). Partial files, if any, retain the .partial suffix. {1}' -f $failures.Count, ($failures -join ' | '))
}

Write-Host 'All four reference packages completed or were skipped only after SHA-256 sidecar revalidation.'
