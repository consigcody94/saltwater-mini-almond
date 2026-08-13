[CmdletBinding()]
param(
    [ValidateSet('All', 'GeoProcessed', 'NcbiRecords')]
    [string]$Profile = 'All',
    [switch]$Execute,
    [string]$OutputRoot,
    [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800,
    [switch]$AllowTestTransport,
    [scriptblock]$RequestInvoker,
    [scriptblock]$RetrySleepAction,
    [scriptblock]$PacingAction
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $PSScriptRoot 'data'
}
Import-Module (Join-Path $PSScriptRoot 'Phase2PublicData.psm1') -Force

if (($RequestInvoker -or $RetrySleepAction -or $PacingAction) -and -not $AllowTestTransport) {
    throw 'Injected transport/pacing callbacks require -AllowTestTransport and are for offline tests only.'
}

function Invoke-PacingDelay {
    param([Parameter(Mandatory)][int]$Milliseconds)
    if ($PacingAction) { $null = & $PacingAction $Milliseconds }
    else { Start-Sleep -Milliseconds $Milliseconds }
}

$geoPlan = Get-Phase2GeoPlan
$ncbiPlan = @(Get-Phase2NcbiRecordPlan)
$includeGeo = $Profile -in @('All', 'GeoProcessed')
$includeNcbi = $Profile -in @('All', 'NcbiRecords')

Write-Host 'AlmondLab Phase 2 small public-data acquisition'
Write-Host ('Mode: {0}' -f $(if ($Execute) { 'EXECUTE' } else { 'DRY RUN (no writes and no network requests)' }))
Write-Host ('Profile: {0}' -f $Profile)
Write-Host ('Output root: {0}' -f [IO.Path]::GetFullPath($OutputRoot))
Write-Host 'Scope exclusions: no SRA/ENA FASTQs, no article scraping, no unverified donor sequence, and no Ectocarpus identifier crosswalk.'

if ($includeGeo) {
    Write-Host ('GEO listing: {0}' -f $geoPlan.ListingUrl)
    Write-Host ('GEO caps: {0} files, {1:N1} MB per file, {2:N1} MB total.' -f $geoPlan.MaximumFileCount, ($geoPlan.MaximumFileBytes / 1000000), ($geoPlan.MaximumTotalBytes / 1000000))
    Write-Warning 'GEO filenames and exact remote sizes are discovered only from the preserved official directory listing during -Execute.'
}
if ($includeNcbi) {
    Write-Host ('NCBI EFetch allowlist: {0} accession.version records.' -f $ncbiPlan.Count)
    foreach ($record in $ncbiPlan) {
        Write-Host ('  {0} | {1} | {2}' -f $record.Accession, $record.Db, $record.Url)
    }
}

if (-not $Execute) {
    if ($includeGeo) { $geoPlan }
    if ($includeNcbi) { $ncbiPlan }
    return
}

$null = New-Item -ItemType Directory -Path $OutputRoot -Force
$geoReceipt = New-Object Collections.Generic.List[object]
$ncbiReceipt = New-Object Collections.Generic.List[object]
$listingReceipt = $null

if ($includeGeo) {
    $geoRoot = Join-Path $OutputRoot 'geo\GSE254853'
    $listingRoot = Join-Path $geoRoot 'listing'
    $filesRoot = Join-Path $geoRoot 'files'
    $requestsRoot = Join-Path $geoRoot 'requests'
    $metadataRoot = Join-Path $geoRoot 'metadata'
    $listingPath = Join-Path $listingRoot 'directory_listing.html'
    $listingResponsePath = Join-Path $listingRoot 'directory_listing.response.json'
    $listingRequestPath = Join-Path $listingRoot 'directory_listing.request.url.txt'
    $parsedListingPath = Join-Path $listingRoot 'parsed_listing.json'

    $null = Write-TextArtifact -LiteralPath $listingRequestPath -Content ($geoPlan.ListingUrl + [Environment]::NewLine)
    Write-Host '[GSE254853] Fetching and preserving the official supplementary directory listing...'
    $listingPolicy = New-GeoTransferPolicy -Listing
    $listingResult = Invoke-AuditedStreamDownload -Uri $geoPlan.ListingUrl -DestinationPath $listingPath -ResponseMetadataPath $listingResponsePath -MaximumBytes $geoPlan.MaximumListingBytes -TimeoutSeconds $TimeoutSeconds -Force -RequestInvoker $RequestInvoker -SleepAction $RetrySleepAction -ResponsePolicyValidator $listingPolicy.ResponseValidator -StoredMetadataValidator $listingPolicy.StoredMetadataValidator -Validator {
        param($path) Test-GeoListingDocument -LiteralPath $path
    }

    $listingHtml = Get-Content -LiteralPath $listingPath -Raw
    $entries = @(ConvertFrom-GeoDirectoryListing -Html $listingHtml -BaseUri $geoPlan.ListingUrl -RequiredPrefix $geoPlan.FilePrefix -MaximumFileCount $geoPlan.MaximumFileCount)
    $knownRemoteTotal = [int64]0
    foreach ($entry in $entries) {
        if ($null -ne $entry.RemoteSizeBytes) { $knownRemoteTotal += [int64]$entry.RemoteSizeBytes }
    }
    if ($knownRemoteTotal -gt $geoPlan.MaximumTotalBytes) {
        throw "Known GEO listing total $knownRemoteTotal exceeds the $($geoPlan.MaximumTotalBytes)-byte safety cap."
    }

    $parsedListing = [pscustomobject][ordered]@{
        accession = $geoPlan.Accession
        listing_url = $geoPlan.ListingUrl
        listing_local_sha256 = $listingResult.Sha256
        parsed_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        file_count = $entries.Count
        known_remote_size_total_bytes = $knownRemoteTotal
        files = @($entries)
    }
    $parsedResult = Write-JsonArtifact -LiteralPath $parsedListingPath -Value $parsedListing
    $listingReceipt = [pscustomobject][ordered]@{
        url = $geoPlan.ListingUrl
        path = $listingPath
        status = $listingResult.Status
        bytes = $listingResult.Bytes
        sha256 = $listingResult.Sha256
        response_metadata_path = $listingResponsePath
        parsed_listing_path = $parsedListingPath
        parsed_listing_sha256 = $parsedResult.Sha256
    }

    [int64]$geoObservedTotal = 0
    foreach ($entry in $entries) {
        $remaining = [int64]($geoPlan.MaximumTotalBytes - $geoObservedTotal)
        if ($remaining -le 0) { throw 'GEO total-byte safety budget is exhausted.' }
        $fileCap = [int64][Math]::Min([double]$geoPlan.MaximumFileBytes, [double]$remaining)
        if ($null -ne $entry.RemoteSizeBytes -and [int64]$entry.RemoteSizeBytes -gt $fileCap) {
            throw "GEO file $($entry.Name) exceeds the remaining safety budget."
        }

        $destination = Join-Path $filesRoot $entry.Name
        $requestPath = Join-Path $requestsRoot ($entry.Name + '.url.txt')
        $responsePath = Join-Path $metadataRoot ($entry.Name + '.response.json')
        $null = Write-TextArtifact -LiteralPath $requestPath -Content ($entry.Url + [Environment]::NewLine)
        Write-Host ('[GSE254853] Acquiring {0}...' -f $entry.Name)
        $geoFileName = $entry.Name
        $geoFilePolicy = New-GeoTransferPolicy -ExpectedFileName $geoFileName
        $downloadArgs = @{
            Uri = $entry.Url
            DestinationPath = $destination
            ResponseMetadataPath = $responsePath
            MaximumBytes = $fileCap
            TimeoutSeconds = $TimeoutSeconds
            RequestInvoker = $RequestInvoker
            SleepAction = $RetrySleepAction
            ResponsePolicyValidator = $geoFilePolicy.ResponseValidator
            StoredMetadataValidator = $geoFilePolicy.StoredMetadataValidator
            Validator = { param($path) Test-GeoProcessedPayload -LiteralPath $path -Name $geoFileName }.GetNewClosure()
        }
        if ($null -ne $entry.RemoteSizeBytes) { $downloadArgs.ExpectedBytes = [int64]$entry.RemoteSizeBytes }
        $result = Invoke-AuditedStreamDownload @downloadArgs
        $geoObservedTotal += [int64]$result.Bytes
        if ($geoObservedTotal -gt $geoPlan.MaximumTotalBytes) { throw 'GEO observed bytes exceed the total safety cap.' }
        $geoReceipt.Add([pscustomobject][ordered]@{
            name = $entry.Name
            url = $entry.Url
            remote_listing_size_bytes = $entry.RemoteSizeBytes
            remote_content_length_bytes = $result.RemoteContentLengthBytes
            status = $result.Status
            path = $result.Path
            bytes = $result.Bytes
            sha256 = $result.Sha256
            request_path = $requestPath
            response_metadata_path = $responsePath
            remote_checksum = $null
        })
        if ($result.Status -eq 'Downloaded') { Invoke-PacingDelay -Milliseconds 250 }
    }
}

if ($includeNcbi) {
    $ncbiRoot = Join-Path $OutputRoot 'ncbi\records'
    [int64]$ncbiObservedTotal = 0
    [int64]$ncbiTotalCap = 50000000
    [int64]$ncbiPerRecordCap = 10000000
    foreach ($record in $ncbiPlan) {
        $recordRoot = Join-Path $ncbiRoot $record.Accession
        $destination = Join-Path $recordRoot $record.FileName
        $requestPath = Join-Path $recordRoot 'request.url.txt'
        $responsePath = Join-Path $recordRoot 'response.json'
        $null = Write-TextArtifact -LiteralPath $requestPath -Content ($record.Url + [Environment]::NewLine)
        $expectedAccession = $record.Accession
        $validator = { param($path) Test-FastaRecord -LiteralPath $path -ExpectedAccession $expectedAccession }.GetNewClosure()
        $recordPolicy = New-NcbiEfetchTransferPolicy -Accession $record.Accession -Database $record.Db
        Write-Host ('[NCBI EFetch] Acquiring {0} ({1})...' -f $record.Accession, $record.Db)
        $result = Invoke-AuditedStreamDownload -Uri $record.Url -DestinationPath $destination -ResponseMetadataPath $responsePath -MaximumBytes $ncbiPerRecordCap -TimeoutSeconds $TimeoutSeconds -RequestInvoker $RequestInvoker -SleepAction $RetrySleepAction -ResponsePolicyValidator $recordPolicy.ResponseValidator -StoredMetadataValidator $recordPolicy.StoredMetadataValidator -Validator $validator
        $ncbiObservedTotal += [int64]$result.Bytes
        if ($ncbiObservedTotal -gt $ncbiTotalCap) { throw 'NCBI record payloads exceed the 50 MB total safety cap.' }
        $ncbiReceipt.Add([pscustomobject][ordered]@{
            group = $record.Group
            label = $record.Label
            accession = $record.Accession
            database = $record.Db
            molecule = $record.Molecule
            url = $record.Url
            status = $result.Status
            path = $result.Path
            bytes = $result.Bytes
            sha256 = $result.Sha256
            request_path = $requestPath
            response_metadata_path = $responsePath
            remote_checksum = $null
        })
        if ($result.Status -eq 'Downloaded') { Invoke-PacingDelay -Milliseconds 350 }
    }
}

$receipt = [pscustomobject][ordered]@{
    schema_version = '1.0.0'
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    profile = $Profile
    test_transport_injected = [bool]($RequestInvoker -or $RetrySleepAction -or $PacingAction)
    output_root = [IO.Path]::GetFullPath($OutputRoot)
    sources = [pscustomobject][ordered]@{
        geo_gse254853 = $listingReceipt
        geo_processed_files = $geoReceipt.ToArray()
        ncbi_fasta_records = $ncbiReceipt.ToArray()
    }
    exclusions = @(
        'No SRA or ENA raw reads and no FASTQ/FQ/SRA payloads.',
        'No publisher article scraping.',
        'No PyAPX sequence because no exact accession.version is verified.',
        'No Ectocarpus gene-model crosswalk or sequence claim.'
    )
    checksum_policy = 'SHA-256 values are calculated locally after streamed download and validation; no remote checksum is invented.'
}
$receiptRoot = Join-Path $OutputRoot 'receipts'
$receiptPath = Join-Path $receiptRoot 'phase2_acquisition_receipt.json'
$receiptResult = Write-JsonArtifact -LiteralPath $receiptPath -Value $receipt -Depth 20

Write-Host ('Receipt: {0}' -f $receiptPath)
return [pscustomobject]@{
    Status = 'Complete'
    ReceiptPath = $receiptPath
    ReceiptSha256 = $receiptResult.Sha256
    GeoFileCount = $geoReceipt.Count
    NcbiRecordCount = $ncbiReceipt.Count
}
