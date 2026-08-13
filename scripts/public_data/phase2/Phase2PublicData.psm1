Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Phase2NcbiRecordPlan {
    [CmdletBinding()]
    param()

    $records = @(
        [pscustomobject]@{ Group = 'PyKPA1'; Label = 'PyKPA1 nucleotide'; Accession = 'AJ972674.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PyKPA1'; Label = 'PyKPA1 protein'; Accession = 'CAI99405.1'; Db = 'protein'; Molecule = 'protein' }
        [pscustomobject]@{ Group = 'PyAPX'; Label = 'PyAPX complete CDS'; Accession = 'AY282755.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PyMnSOD'; Label = 'PyMnSOD complete CDS'; Accession = 'DQ146477.2'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'KaNaH'; Label = 'Kappaphycus Na+/H+ antiporter partial CDS'; Accession = 'MT473962.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'SbSOS1'; Label = 'SbSOS1 nucleotide'; Accession = 'EU879059.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'SbSOS1'; Label = 'SbSOS1 protein'; Accession = 'ACJ63441.1'; Db = 'protein'; Molecule = 'protein' }
        [pscustomobject]@{ Group = 'PpHKT1'; Label = 'PpHKT1 isoform 1 transcript'; Accession = 'XM_020565174.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PpHKT1'; Label = 'PpHKT1 isoform 1 protein'; Accession = 'XP_020420763.1'; Db = 'protein'; Molecule = 'protein' }
        [pscustomobject]@{ Group = 'PpHKT1'; Label = 'PpHKT1 isoform 2 transcript'; Accession = 'XM_020564808.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PpHKT1'; Label = 'PpHKT1 isoform 2 protein'; Accession = 'XP_020420397.1'; Db = 'protein'; Molecule = 'protein' }
        [pscustomobject]@{ Group = 'PpSOS2'; Label = 'PpSOS2 isoform 1 transcript'; Accession = 'XM_020568644.1'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PpSOS2'; Label = 'PpSOS2 isoform 1 protein'; Accession = 'XP_020424233.1'; Db = 'protein'; Molecule = 'protein' }
        [pscustomobject]@{ Group = 'PpSOS2'; Label = 'PpSOS2 isoform 2 transcript'; Accession = 'XM_007201987.2'; Db = 'nuccore'; Molecule = 'nucleotide' }
        [pscustomobject]@{ Group = 'PpSOS2'; Label = 'PpSOS2 isoform 2 protein'; Accession = 'XP_007202049.1'; Db = 'protein'; Molecule = 'protein' }
    )

    foreach ($record in $records) {
        $url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db={0}&id={1}&rettype=fasta&retmode=text&tool=AlmondLabPhase2' -f (
            [uri]::EscapeDataString($record.Db), [uri]::EscapeDataString($record.Accession)
        )
        $record | Add-Member -NotePropertyName Url -NotePropertyValue $url
        $record | Add-Member -NotePropertyName FileName -NotePropertyValue ($record.Accession + '.fasta')
        $record
    }
}

function Get-Phase2GeoPlan {
    [CmdletBinding()]
    param()

    [pscustomobject]@{
        Accession = 'GSE254853'
        ListingUrl = 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/'
        FilePrefix = 'GSE254853_'
        MaximumFileCount = 50
        MaximumFileBytes = [int64]100000000
        MaximumTotalBytes = [int64]250000000
        MaximumListingBytes = [int64]5000000
    }
}

function Get-FileSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$LiteralPath)

    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        throw "Cannot hash missing file: $LiteralPath"
    }
    (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ExpectedHashFromSidecar {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$SidecarPath)

    if (-not (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) { return $null }
    $text = Get-Content -LiteralPath $SidecarPath -Raw
    if ($text -match '(?im)^\s*([0-9a-f]{64})\s+') {
        return $Matches[1].ToLowerInvariant()
    }
    return $null
}

function Write-ChecksumSidecar {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$Hash
    )

    $sidecar = "$LiteralPath.sha256"
    $partial = "$sidecar.partial"
    $fileName = [IO.Path]::GetFileName($LiteralPath)
    $encoding = New-Object Text.UTF8Encoding($false)
    $null = [IO.File]::WriteAllText($partial, ('{0}  {1}{2}' -f $Hash.ToLowerInvariant(), $fileName, [Environment]::NewLine), $encoding)
    Move-Item -LiteralPath $partial -Destination $sidecar -Force
    return $sidecar
}

function Test-VerifiedFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [string]$SidecarPath = "$LiteralPath.sha256"
    )

    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { return $false }
    $expected = Get-ExpectedHashFromSidecar -SidecarPath $SidecarPath
    if (-not $expected) { return $false }
    return (Get-FileSha256 -LiteralPath $LiteralPath) -eq $expected
}

function Get-BytesSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory)][byte[]]$Bytes)

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        -join ($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') })
    }
    finally { $null = $sha.Dispose() }
}

function Write-TextArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content
    )

    $parent = Split-Path -Parent $LiteralPath
    if ($parent) { $null = New-Item -ItemType Directory -Path $parent -Force }
    $encoding = New-Object Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($Content)
    $intendedHash = Get-BytesSha256 -Bytes $bytes

    if ((Test-VerifiedFile -LiteralPath $LiteralPath) -and ((Get-FileSha256 -LiteralPath $LiteralPath) -eq $intendedHash)) {
        return [pscustomobject]@{ Status = 'SkippedVerified'; Path = $LiteralPath; Sha256 = $intendedHash; Bytes = [int64]$bytes.Length }
    }

    $partial = "$LiteralPath.partial"
    $null = [IO.File]::WriteAllBytes($partial, $bytes)
    $actualHash = Get-FileSha256 -LiteralPath $partial
    if ($actualHash -ne $intendedHash) { throw "Text artifact hash mismatch: $partial" }
    Move-Item -LiteralPath $partial -Destination $LiteralPath -Force
    $null = Write-ChecksumSidecar -LiteralPath $LiteralPath -Hash $actualHash
    return [pscustomobject]@{ Status = 'Written'; Path = $LiteralPath; Sha256 = $actualHash; Bytes = [int64]$bytes.Length }
}

function Write-JsonArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)]$Value,
        [ValidateRange(2, 30)][int]$Depth = 12
    )

    $json = ($Value | ConvertTo-Json -Depth $Depth) + [Environment]::NewLine
    Write-TextArtifact -LiteralPath $LiteralPath -Content $json
}

function Test-NonEmptyFile {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$LiteralPath)

    return (Test-Path -LiteralPath $LiteralPath -PathType Leaf) -and ((Get-Item -LiteralPath $LiteralPath).Length -gt 0)
}

function Test-GeoListingDocument {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$LiteralPath)

    if (-not (Test-NonEmptyFile -LiteralPath $LiteralPath)) { return $false }
    $text = Get-Content -LiteralPath $LiteralPath -Raw
    return $text -match 'GSE254853_'
}

function Test-GeoProcessedFileName {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name)

    if ([string]::IsNullOrWhiteSpace($Name) -or $Name.Length -gt 255) { return $false }
    if (-not $Name.StartsWith('GSE254853_', [StringComparison]::Ordinal)) { return $false }
    if ($Name.IndexOfAny([char[]]"/\?/#%") -ge 0 -or $Name.Contains('..')) { return $false }
    if ($Name -match '[\x00-\x1f\x7f]' -or $Name.EndsWith('.', [StringComparison]::Ordinal) -or $Name.EndsWith(' ', [StringComparison]::Ordinal)) { return $false }
    if ($Name -notmatch '^GSE254853_[A-Za-z0-9][A-Za-z0-9._+()-]*$') { return $false }

    $leaf = $Name.Substring('GSE254853_'.Length)
    if ($leaf.StartsWith('.', [StringComparison]::Ordinal)) { return $false }
    if ($leaf -match '(?i)(?:^|[_.()+-])RAW(?:[_.()+-]|$)') { return $false }
    if ($leaf -match '(?i)\.(?:fastq|fq|sra|bam|cram|tar|zip|7z|xz|bz2|rar)(?:\.|$)') { return $false }

    $lower = $Name.ToLowerInvariant()
    $allowedSuffixes = @(
        '.csv', '.tsv', '.txt', '.fasta', '.fa', '.gff', '.gff3', '.gtf', '.xlsx', '.xls',
        '.csv.gz', '.tsv.gz', '.txt.gz', '.fasta.gz', '.fa.gz', '.gff.gz', '.gff3.gz', '.gtf.gz'
    )
    foreach ($suffix in $allowedSuffixes) {
        if ($lower.EndsWith($suffix, [StringComparison]::Ordinal)) { return $true }
    }
    return $false
}

function Test-GeoProcessedPayload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)][string]$Name,
        [ValidateRange(1, 2000000000)][int64]$MaximumExpandedBytes = 1000000000
    )

    if (-not (Test-GeoProcessedFileName -Name $Name)) { return $false }
    if (-not (Test-NonEmptyFile -LiteralPath $LiteralPath)) { return $false }
    if (-not $Name.EndsWith('.gz', [StringComparison]::OrdinalIgnoreCase)) { return $true }

    Add-Type -AssemblyName System.IO.Compression
    $fileStream = $null
    $gzipStream = $null
    try {
        $fileStream = New-Object IO.FileStream($LiteralPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($fileStream.Length -lt 2) { return $false }
        $first = $fileStream.ReadByte()
        $second = $fileStream.ReadByte()
        if ($first -ne 0x1f -or $second -ne 0x8b) { return $false }
        $fileStream.Position = 0
        $gzipStream = New-Object IO.Compression.GZipStream($fileStream, [IO.Compression.CompressionMode]::Decompress, $true)
        $buffer = New-Object byte[] 65536
        [int64]$expanded = 0
        while (($read = $gzipStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $expanded += $read
            if ($expanded -gt $MaximumExpandedBytes) { return $false }
        }
        return $expanded -gt 0
    }
    catch { return $false }
    finally {
        if ($null -ne $gzipStream) { $null = $gzipStream.Dispose() }
        if ($null -ne $fileStream) { $null = $fileStream.Dispose() }
    }
}

function ConvertFrom-StrictQueryString {
    [CmdletBinding()]
    param([Parameter(Mandatory)][uri]$Uri)

    if ([string]::IsNullOrEmpty($Uri.Query) -or $Uri.Query -eq '?') { throw "Required query string is missing: $Uri" }
    $rawQuery = $Uri.Query.Substring(1)
    $result = @{}
    foreach ($segment in $rawQuery.Split('&')) {
        if ([string]::IsNullOrEmpty($segment)) { throw "Empty query segment is forbidden: $Uri" }
        $separator = $segment.IndexOf('=')
        if ($separator -le 0) { throw "Malformed query segment is forbidden: $segment" }
        $rawKey = $segment.Substring(0, $separator)
        $rawValue = $segment.Substring($separator + 1)
        if ($rawKey -match '%(?![0-9A-Fa-f]{2})' -or $rawValue -match '%(?![0-9A-Fa-f]{2})') {
            throw "Malformed percent encoding in query: $Uri"
        }
        $key = [uri]::UnescapeDataString($rawKey.Replace('+', ' '))
        $value = [uri]::UnescapeDataString($rawValue.Replace('+', ' '))
        if ($key -notmatch '^[a-z]+$') { throw "Unexpected query key syntax: $key" }
        if ($result.ContainsKey($key)) { throw "Duplicate query key is forbidden: $key" }
        $result[$key] = $value
    }
    return $result
}

function Assert-ExactHttpsEndpoint {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][string]$AbsolutePath,
        [Parameter(Mandatory)][string]$SourceLabel
    )

    if (-not $Uri.IsAbsoluteUri -or
        -not $Uri.Scheme.Equals('https', [StringComparison]::OrdinalIgnoreCase) -or
        -not $Uri.Host.Equals($HostName, [StringComparison]::OrdinalIgnoreCase) -or
        -not $Uri.IsDefaultPort -or
        -not [string]::IsNullOrEmpty($Uri.UserInfo) -or
        -not $Uri.AbsolutePath.Equals($AbsolutePath, [StringComparison]::Ordinal) -or
        -not [string]::IsNullOrEmpty($Uri.Fragment)) {
        throw "$SourceLabel URL is outside its exact official HTTPS endpoint policy: $Uri"
    }
}

function Assert-GeoUriPolicy {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [switch]$Listing,
        [string]$ExpectedFileName
    )

    $basePath = '/geo/series/GSE254nnn/GSE254853/suppl/'
    $hasFileName = -not [string]::IsNullOrEmpty($ExpectedFileName)
    if ([bool]$Listing -eq $hasFileName) {
        throw 'Exactly one GEO URI policy mode must be selected.'
    }
    $path = $basePath
    if (-not $Listing) {
        if (-not (Test-GeoProcessedFileName -Name $ExpectedFileName)) { throw "Unsafe or unapproved GEO filename: $ExpectedFileName" }
        $path += $ExpectedFileName
    }
    Assert-ExactHttpsEndpoint -Uri $Uri -HostName 'ftp.ncbi.nlm.nih.gov' -AbsolutePath $path -SourceLabel 'GEO'
    if (-not [string]::IsNullOrEmpty($Uri.Query)) { throw "GEO URL query is forbidden: $Uri" }
    return $true
}

function Assert-NcbiEfetchUriPolicy {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$Accession,
        [Parameter(Mandatory)][ValidateSet('nuccore', 'protein')][string]$Database
    )

    $matches = @(Get-Phase2NcbiRecordPlan | Where-Object { $_.Accession -ceq $Accession -and $_.Db -ceq $Database })
    if ($matches.Count -ne 1) { throw "Accession/database pair is outside the exact EFetch allowlist: $Accession / $Database" }
    Assert-ExactHttpsEndpoint -Uri $Uri -HostName 'eutils.ncbi.nlm.nih.gov' -AbsolutePath '/entrez/eutils/efetch.fcgi' -SourceLabel 'EFetch'
    $query = ConvertFrom-StrictQueryString -Uri $Uri
    $expected = [ordered]@{
        db = $Database
        id = $Accession
        rettype = 'fasta'
        retmode = 'text'
        tool = 'AlmondLabPhase2'
    }
    if ($query.Count -ne $expected.Count) { throw "EFetch query has unexpected or missing fields: $Uri" }
    foreach ($key in $expected.Keys) {
        if (-not $query.ContainsKey($key) -or -not [string]::Equals([string]$query[$key], [string]$expected[$key], [StringComparison]::Ordinal)) {
            throw "EFetch query field differs from the allowlist: $key"
        }
    }
    return $true
}

function Test-AllowedMediaType {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$MediaType,
        [Parameter(Mandatory)][string[]]$Allowed
    )

    $normalized = ($MediaType.Split(';')[0]).Trim().ToLowerInvariant()
    return $normalized -in $Allowed
}

function Assert-GeoContentType {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$MediaType,
        [switch]$Listing,
        [string]$ExpectedFileName
    )

    $allowed = @()
    if ($Listing) { $allowed = @('text/html') }
    elseif ($ExpectedFileName.EndsWith('.gz', [StringComparison]::OrdinalIgnoreCase)) {
        $allowed = @('application/gzip', 'application/x-gzip', 'application/octet-stream')
    }
    elseif ($ExpectedFileName.EndsWith('.xlsx', [StringComparison]::OrdinalIgnoreCase)) {
        $allowed = @('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/octet-stream')
    }
    elseif ($ExpectedFileName.EndsWith('.xls', [StringComparison]::OrdinalIgnoreCase)) {
        $allowed = @('application/vnd.ms-excel', 'application/octet-stream')
    }
    elseif ($ExpectedFileName.EndsWith('.csv', [StringComparison]::OrdinalIgnoreCase)) {
        $allowed = @('text/csv', 'application/csv', 'text/plain', 'application/octet-stream')
    }
    elseif ($ExpectedFileName.EndsWith('.tsv', [StringComparison]::OrdinalIgnoreCase)) {
        $allowed = @('text/tab-separated-values', 'text/plain', 'application/octet-stream')
    }
    else { $allowed = @('text/plain', 'text/x-fasta', 'application/fasta', 'text/tab-separated-values', 'application/octet-stream') }

    if (-not (Test-AllowedMediaType -MediaType $MediaType -Allowed $allowed)) {
        throw "GEO response content type is incompatible with the approved payload: $MediaType"
    }
    return $true
}

function Assert-NcbiEfetchContentType {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$MediaType)

    if (-not (Test-AllowedMediaType -MediaType $MediaType -Allowed @('text/plain', 'text/x-fasta', 'application/fasta', 'application/octet-stream'))) {
        throw "EFetch response content type is incompatible with FASTA: $MediaType"
    }
    return $true
}

function Get-ResponseMediaType {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Response)

    if ($null -eq $Response.Content -or $null -eq $Response.Content.Headers.ContentType -or [string]::IsNullOrWhiteSpace($Response.Content.Headers.ContentType.MediaType)) {
        throw 'Response content type is missing.'
    }
    return $Response.Content.Headers.ContentType.MediaType
}

function New-GeoTransferPolicy {
    [CmdletBinding(DefaultParameterSetName = 'File')]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Listing')][switch]$Listing,
        [Parameter(Mandatory, ParameterSetName = 'File')][string]$ExpectedFileName
    )

    if ($PSCmdlet.ParameterSetName -eq 'File' -and -not (Test-GeoProcessedFileName -Name $ExpectedFileName)) {
        throw "Unsafe or unapproved GEO filename: $ExpectedFileName"
    }
    $isListing = $PSCmdlet.ParameterSetName -eq 'Listing'
    $fileName = $ExpectedFileName
    $responseValidator = {
        param([uri]$RequestedUri, $Response)
        $null = Assert-GeoUriPolicy -Uri $RequestedUri -Listing:$isListing -ExpectedFileName $fileName
        if ($null -eq $Response.RequestMessage -or $null -eq $Response.RequestMessage.RequestUri) { throw 'GEO response final URL is missing.' }
        $null = Assert-GeoUriPolicy -Uri $Response.RequestMessage.RequestUri -Listing:$isListing -ExpectedFileName $fileName
        $statusCode = [int]$Response.StatusCode
        if ($statusCode -ge 200 -and $statusCode -le 299) {
            $mediaType = Get-ResponseMediaType -Response $Response
            $null = Assert-GeoContentType -MediaType $mediaType -Listing:$isListing -ExpectedFileName $fileName
        }
        return $true
    }.GetNewClosure()
    $storedMetadataValidator = {
        param([uri]$RequestedUri, $Metadata)
        $null = Assert-GeoUriPolicy -Uri $RequestedUri -Listing:$isListing -ExpectedFileName $fileName
        if ($Metadata.PSObject.Properties.Name -notcontains 'final_url' -or [string]::IsNullOrWhiteSpace([string]$Metadata.final_url)) { throw 'Stored GEO metadata final URL is missing.' }
        $null = Assert-GeoUriPolicy -Uri ([uri]$Metadata.final_url) -Listing:$isListing -ExpectedFileName $fileName
        if ($Metadata.PSObject.Properties.Name -notcontains 'content_type' -or [string]::IsNullOrWhiteSpace([string]$Metadata.content_type)) { throw 'Stored GEO metadata content type is missing.' }
        $null = Assert-GeoContentType -MediaType ([string]$Metadata.content_type) -Listing:$isListing -ExpectedFileName $fileName
        return $true
    }.GetNewClosure()
    return [pscustomobject]@{ ResponseValidator = $responseValidator; StoredMetadataValidator = $storedMetadataValidator }
}

function New-NcbiEfetchTransferPolicy {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Accession,
        [Parameter(Mandatory)][ValidateSet('nuccore', 'protein')][string]$Database
    )

    $probe = @(Get-Phase2NcbiRecordPlan | Where-Object { $_.Accession -ceq $Accession -and $_.Db -ceq $Database })
    if ($probe.Count -ne 1) { throw "Accession/database pair is outside the exact EFetch allowlist: $Accession / $Database" }
    $expectedAccession = $Accession
    $expectedDb = $Database
    $responseValidator = {
        param([uri]$RequestedUri, $Response)
        $null = Assert-NcbiEfetchUriPolicy -Uri $RequestedUri -Accession $expectedAccession -Database $expectedDb
        if ($null -eq $Response.RequestMessage -or $null -eq $Response.RequestMessage.RequestUri) { throw 'EFetch response final URL is missing.' }
        $null = Assert-NcbiEfetchUriPolicy -Uri $Response.RequestMessage.RequestUri -Accession $expectedAccession -Database $expectedDb
        $statusCode = [int]$Response.StatusCode
        if ($statusCode -ge 200 -and $statusCode -le 299) {
            $mediaType = Get-ResponseMediaType -Response $Response
            $null = Assert-NcbiEfetchContentType -MediaType $mediaType
        }
        return $true
    }.GetNewClosure()
    $storedMetadataValidator = {
        param([uri]$RequestedUri, $Metadata)
        $null = Assert-NcbiEfetchUriPolicy -Uri $RequestedUri -Accession $expectedAccession -Database $expectedDb
        if ($Metadata.PSObject.Properties.Name -notcontains 'final_url' -or [string]::IsNullOrWhiteSpace([string]$Metadata.final_url)) { throw 'Stored EFetch metadata final URL is missing.' }
        $null = Assert-NcbiEfetchUriPolicy -Uri ([uri]$Metadata.final_url) -Accession $expectedAccession -Database $expectedDb
        if ($Metadata.PSObject.Properties.Name -notcontains 'content_type' -or [string]::IsNullOrWhiteSpace([string]$Metadata.content_type)) { throw 'Stored EFetch metadata content type is missing.' }
        $null = Assert-NcbiEfetchContentType -MediaType ([string]$Metadata.content_type)
        return $true
    }.GetNewClosure()
    return [pscustomobject]@{ ResponseValidator = $responseValidator; StoredMetadataValidator = $storedMetadataValidator }
}

function Test-FastaRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)][ValidatePattern('^[A-Z]{2}_[0-9]+\.[0-9]+$|^[A-Z]{2,4}[0-9]+\.[0-9]+$')][string]$ExpectedAccession
    )

    if (-not (Test-NonEmptyFile -LiteralPath $LiteralPath)) { return $false }
    $lines = @(Get-Content -LiteralPath $LiteralPath | Where-Object { $_ -ne '' })
    if ($lines.Count -lt 2) { return $false }
    $headers = @($lines | Where-Object { $_.StartsWith('>') })
    if ($headers.Count -ne 1) { return $false }
    if ($headers[0] -notmatch ('^>' + [regex]::Escape($ExpectedAccession) + '(?:\s|$)')) { return $false }
    $sequenceLines = @($lines | Where-Object { -not $_.StartsWith('>') })
    if ($sequenceLines.Count -eq 0) { return $false }
    $sequence = $sequenceLines -join ''
    if ($sequence.Length -eq 0) { return $false }
    return $sequence -match '^[A-Za-z*.-]+$'
}

function ConvertFrom-GeoDirectoryListing {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Html,
        [Parameter(Mandatory)][uri]$BaseUri,
        [string]$RequiredPrefix = 'GSE254853_',
        [ValidateRange(1, 100)][int]$MaximumFileCount = 50
    )

    if (-not [string]::Equals($RequiredPrefix, 'GSE254853_', [StringComparison]::Ordinal)) { throw "Unexpected GEO filename prefix policy: $RequiredPrefix" }
    $null = Assert-GeoUriPolicy -Uri $BaseUri -Listing

    $pattern = '(?im)<a\s+[^>]*href\s*=\s*["''](?<href>[^"'']+)["''][^>]*>.*?</a>(?<tail>[^\r\n]*)'
    $matches = [regex]::Matches($Html, $pattern)
    $seen = @{}
    $entries = New-Object Collections.Generic.List[object]

    foreach ($match in $matches) {
        $href = [Net.WebUtility]::HtmlDecode($match.Groups['href'].Value).Trim()
        try { $decoded = [uri]::UnescapeDataString($href) }
        catch { throw "Invalid URL encoding in GEO listing href: $href" }
        $rawCandidate = $href.StartsWith($RequiredPrefix, [StringComparison]::Ordinal)
        $decodedCandidate = $decoded.StartsWith($RequiredPrefix, [StringComparison]::Ordinal)
        if (-not $rawCandidate -and -not $decodedCandidate) { continue }
        if ($href.Contains('%')) { throw "Unsafe GEO supplementary filename encoding: $href" }

        if ($decoded.Contains('/') -or $decoded.Contains('\') -or $decoded.Contains('?') -or $decoded.Contains('#') -or $decoded.Contains('%') -or $decoded.Contains('..')) {
            throw "Unsafe GEO supplementary filename: $decoded"
        }
        if (-not (Test-GeoProcessedFileName -Name $decoded)) { throw "Raw-data payload is forbidden or the processed format is not approved: $decoded" }
        if ($seen.ContainsKey($decoded)) { throw "Duplicate GEO supplementary filename: $decoded" }

        $tail = [Net.WebUtility]::HtmlDecode(([regex]::Replace($match.Groups['tail'].Value, '<[^>]+>', ' ')))
        $remoteSize = $null
        if ($tail -match '(?:^|\s)(?<bytes>[0-9]+)\s*$') {
            $remoteSize = [int64]$Matches['bytes']
        }

        $fileUri = New-Object uri($BaseUri, $decoded)
        $null = Assert-GeoUriPolicy -Uri $fileUri -ExpectedFileName $decoded

        $seen[$decoded] = $true
        $entries.Add([pscustomobject]@{
            Name = $decoded
            Url = $fileUri.AbsoluteUri
            RemoteSizeBytes = $remoteSize
        })
        if ($entries.Count -gt $MaximumFileCount) {
            throw "GEO listing exceeds the $MaximumFileCount-file safety cap."
        }
    }

    if ($entries.Count -eq 0) { throw 'No processed GSE254853 supplementary files were found in the official listing.' }
    return @($entries | Sort-Object Name)
}

function Test-RetriableHttpStatus {
    [CmdletBinding()]
    param([Parameter(Mandatory)][int]$StatusCode)

    return ($StatusCode -eq 429) -or ($StatusCode -ge 500 -and $StatusCode -le 599)
}

function Test-TransientTransportException {
    [CmdletBinding()]
    param([Parameter(Mandatory)][Exception]$Exception)

    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [Threading.Tasks.TaskCanceledException] -or $current -is [TimeoutException]) { return $true }
        if ($current -is [Net.WebException]) {
            $transientWebStatuses = @(
                'Timeout', 'ConnectFailure', 'ConnectionClosed', 'KeepAliveFailure',
                'NameResolutionFailure', 'ReceiveFailure', 'SendFailure', 'PipelineFailure',
                'ProxyNameResolutionFailure'
            )
            if ($current.Status.ToString() -in $transientWebStatuses) { return $true }
        }
        if ($current -is [Net.Sockets.SocketException]) {
            $transientSocketErrors = @(
                'TimedOut', 'ConnectionReset', 'ConnectionAborted', 'NetworkDown',
                'NetworkUnreachable', 'HostDown', 'HostUnreachable', 'TryAgain', 'WouldBlock'
            )
            if ($current.SocketErrorCode.ToString() -in $transientSocketErrors) { return $true }
        }
        $current = $current.InnerException
    }
    return $false
}

function Get-RetryDelaySeconds {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Response,
        [Parameter(Mandatory)][ValidateRange(1, 10)][int]$Attempt,
        [ValidateRange(0.1, 300)][double]$BaseDelaySeconds = 2,
        [ValidateRange(1, 600)][double]$MaximumDelaySeconds = 120,
        [DateTimeOffset]$UtcNow = [DateTimeOffset]::UtcNow
    )

    $delay = [Math]::Min($MaximumDelaySeconds, $BaseDelaySeconds * [Math]::Pow(2, $Attempt - 1))
    $retryAfter = $Response.Headers.RetryAfter
    if ($null -ne $retryAfter) {
        if ($null -ne $retryAfter.Delta) { $delay = [Math]::Ceiling($retryAfter.Delta.TotalSeconds) }
        elseif ($null -ne $retryAfter.Date) { $delay = [Math]::Ceiling(($retryAfter.Date - $UtcNow).TotalSeconds) }
    }
    if ($delay -lt 0) { $delay = 0 }
    return [double][Math]::Min($MaximumDelaySeconds, $delay)
}

function Invoke-HttpGetWithRetry {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Net.Http.HttpClient]$Client,
        [ValidateRange(1, 10)][int]$MaximumAttempts = 4,
        [scriptblock]$RequestInvoker,
        [scriptblock]$ResponsePolicyValidator,
        [scriptblock]$SleepAction
    )

    Add-Type -AssemblyName System.Net.Http
    $ownsClient = $false
    if ($null -eq $Client) {
        $handler = New-Object Net.Http.HttpClientHandler
        $Client = New-Object Net.Http.HttpClient($handler)
        $ownsClient = $true
    }
    if (-not $RequestInvoker) {
        $RequestInvoker = {
            param($httpClient, $requestUri)
            $httpClient.GetAsync($requestUri, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        }
    }
    if (-not $SleepAction) {
        $SleepAction = { param($seconds) Start-Sleep -Milliseconds ([int][Math]::Ceiling($seconds * 1000)) }
    }

    $response = $null
    try {
        for ($attempt = 1; $attempt -le $MaximumAttempts; $attempt++) {
            try { $response = & $RequestInvoker $Client $Uri }
            catch {
                $transportException = $_.Exception
                if ($attempt -ge $MaximumAttempts -or -not (Test-TransientTransportException -Exception $transportException)) { throw }
                $delay = [double][Math]::Min(120, 2 * [Math]::Pow(2, $attempt - 1))
                Write-Warning ('Transient transport failure from {0}; retrying attempt {1}/{2} after {3:N0} second(s).' -f $Uri.Host, ($attempt + 1), $MaximumAttempts, $delay)
                $null = & $SleepAction $delay
                continue
            }
            if ($null -eq $response) { throw "HTTP request invoker returned no response for $Uri" }
            if ($ResponsePolicyValidator) { $null = & $ResponsePolicyValidator $Uri $response }
            $statusCode = [int]$response.StatusCode
            if (-not (Test-RetriableHttpStatus -StatusCode $statusCode) -or $attempt -eq $MaximumAttempts) {
                return $response
            }
            $delay = Get-RetryDelaySeconds -Response $response -Attempt $attempt
            $null = $response.Dispose()
            $response = $null
            Write-Warning ('HTTP {0} from {1}; retrying attempt {2}/{3} after {4:N0} second(s).' -f $statusCode, $Uri.Host, ($attempt + 1), $MaximumAttempts, $delay)
            $null = & $SleepAction $delay
        }
    }
    catch {
        if ($null -ne $response) { $null = $response.Dispose() }
        throw
    }
    finally {
        if ($ownsClient -and $null -ne $Client) { $null = $Client.Dispose() }
    }
}

function ConvertTo-HeaderObject {
    [CmdletBinding()]
    param($Headers)

    $result = [ordered]@{}
    if ($null -ne $Headers) {
        foreach ($header in $Headers) { $result[$header.Key] = @($header.Value) }
    }
    return [pscustomobject]$result
}

function New-ResponseMetadata {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$RequestUri,
        [Parameter(Mandatory)]$Response,
        [Parameter(Mandatory)][int64]$ObservedBytes,
        [Parameter(Mandatory)][string]$LocalSha256
    )

    $responseUri = $null
    if ($null -ne $Response.RequestMessage -and $null -ne $Response.RequestMessage.RequestUri) {
        $responseUri = $Response.RequestMessage.RequestUri.AbsoluteUri
    }
    $contentLength = $null
    if ($null -ne $Response.Content -and $null -ne $Response.Content.Headers.ContentLength) {
        $contentLength = [int64]$Response.Content.Headers.ContentLength
    }
    $contentType = $null
    if ($null -ne $Response.Content -and $null -ne $Response.Content.Headers.ContentType) {
        $contentType = $Response.Content.Headers.ContentType.MediaType
    }
    [pscustomobject][ordered]@{
        request_url = $RequestUri.AbsoluteUri
        response_url = $responseUri
        final_url = $responseUri
        status_code = [int]$Response.StatusCode
        content_type = $contentType
        received_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        response_headers = ConvertTo-HeaderObject -Headers $Response.Headers
        content_headers = ConvertTo-HeaderObject -Headers $(if ($null -ne $Response.Content) { $Response.Content.Headers } else { $null })
        remote_content_length_bytes = $contentLength
        observed_bytes = $ObservedBytes
        local_sha256 = $LocalSha256
    }
}

function Assert-StoredDownloadMetadata {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$RequestUri,
        [Parameter(Mandatory)]$Metadata,
        [Parameter(Mandatory)][int64]$PayloadBytes,
        [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$PayloadSha256,
        [Parameter(Mandatory)][scriptblock]$StoredMetadataValidator
    )

    $properties = @($Metadata.PSObject.Properties.Name)
    if ($properties -notcontains 'request_url' -or -not [string]::Equals([string]$Metadata.request_url, $RequestUri.AbsoluteUri, [StringComparison]::Ordinal)) {
        throw 'Verified response metadata does not match the requested URL.'
    }
    if ($properties -notcontains 'local_sha256' -or
        [string]$Metadata.local_sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        -not [string]::Equals([string]$Metadata.local_sha256, $PayloadSha256, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Verified response metadata does not match the payload SHA-256.'
    }
    if ($properties -notcontains 'status_code') { throw 'Verified response metadata status is missing.' }
    try { $statusCode = [int]$Metadata.status_code }
    catch { throw 'Verified response metadata status is invalid.' }
    if ($statusCode -lt 200 -or $statusCode -gt 299) { throw "Verified response metadata status is not successful: $statusCode" }
    if ($properties -notcontains 'observed_bytes') { throw 'Verified response metadata observed byte count is missing.' }
    try { $observedBytes = [int64]$Metadata.observed_bytes }
    catch { throw 'Verified response metadata observed byte count is invalid.' }
    if ($observedBytes -ne $PayloadBytes) { throw 'Verified response metadata observed bytes do not match the payload.' }
    if ($properties -notcontains 'final_url' -or [string]::IsNullOrWhiteSpace([string]$Metadata.final_url)) {
        throw 'Verified response metadata final URL is missing.'
    }
    if ($properties -contains 'response_url' -and $null -ne $Metadata.response_url -and
        -not [string]::Equals([string]$Metadata.response_url, [string]$Metadata.final_url, [StringComparison]::Ordinal)) {
        throw 'Verified response metadata response URL differs from the final URL.'
    }
    if ($properties -notcontains 'content_type' -or [string]::IsNullOrWhiteSpace([string]$Metadata.content_type)) {
        throw 'Verified response metadata content type is missing.'
    }

    $remoteLength = $null
    if ($properties -contains 'remote_content_length_bytes' -and $null -ne $Metadata.remote_content_length_bytes) {
        try { $remoteLength = [int64]$Metadata.remote_content_length_bytes }
        catch { throw 'Verified response metadata remote content length is invalid.' }
        if ($remoteLength -ne $PayloadBytes) { throw 'Verified response metadata remote content length does not match the payload.' }
    }
    $null = & $StoredMetadataValidator $RequestUri $Metadata
    return $remoteLength
}

function Invoke-AuditedStreamDownload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$DestinationPath,
        [Parameter(Mandatory)][string]$ResponseMetadataPath,
        [Parameter(Mandatory)][ValidateRange(1, 1000000000)][int64]$MaximumBytes,
        [Nullable[int64]]$ExpectedBytes,
        [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800,
        [ValidateRange(1, 10)][int]$MaximumAttempts = 4,
        [scriptblock]$Validator,
        [scriptblock]$ResponsePolicyValidator,
        [scriptblock]$StoredMetadataValidator,
        [scriptblock]$RequestInvoker,
        [scriptblock]$SleepAction,
        [switch]$Force
    )

    if (-not $ResponsePolicyValidator -or -not $StoredMetadataValidator) {
        throw 'Source-specific response and stored-metadata policy validators are required.'
    }

    $destinationParent = Split-Path -Parent $DestinationPath
    $metadataParent = Split-Path -Parent $ResponseMetadataPath
    if ($destinationParent) { $null = New-Item -ItemType Directory -Path $destinationParent -Force }
    if ($metadataParent) { $null = New-Item -ItemType Directory -Path $metadataParent -Force }

    if (-not $Force -and (Test-VerifiedFile -LiteralPath $DestinationPath) -and (Test-VerifiedFile -LiteralPath $ResponseMetadataPath)) {
        $bytes = [int64](Get-Item -LiteralPath $DestinationPath).Length
        $sha256 = Get-FileSha256 -LiteralPath $DestinationPath
        if ($bytes -gt $MaximumBytes) { throw "Verified file exceeds current safety cap: $DestinationPath" }
        if ($null -ne $ExpectedBytes -and $bytes -ne [int64]$ExpectedBytes) {
            throw "Verified file differs from the current official listing size: $DestinationPath"
        }
        if ($Validator -and -not (& $Validator $DestinationPath)) {
            throw "Verified file failed content validation: $DestinationPath"
        }
        $storedMetadata = Get-Content -LiteralPath $ResponseMetadataPath -Raw | ConvertFrom-Json
        $storedRemoteLength = Assert-StoredDownloadMetadata -RequestUri $Uri -Metadata $storedMetadata -PayloadBytes $bytes -PayloadSha256 $sha256 -StoredMetadataValidator $StoredMetadataValidator
        return [pscustomobject]@{
            Status = 'SkippedVerified'
            Path = $DestinationPath
            Sha256 = $sha256
            Bytes = $bytes
            RemoteContentLengthBytes = $storedRemoteLength
            ResponseMetadataPath = $ResponseMetadataPath
        }
    }

    $partial = "$DestinationPath.partial"
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object Net.Http.HttpClientHandler
    $client = New-Object Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
    $null = $client.DefaultRequestHeaders.UserAgent.ParseAdd('AlmondLab-Phase2-PublicData/1.0')
    $response = $null
    $inputStream = $null
    $outputStream = $null
    try {
        $response = Invoke-HttpGetWithRetry -Uri $Uri -Client $client -MaximumAttempts $MaximumAttempts -RequestInvoker $RequestInvoker -ResponsePolicyValidator $ResponsePolicyValidator -SleepAction $SleepAction
        $null = $response.EnsureSuccessStatusCode()
        if ($null -eq $response.Content) { throw "HTTP response contained no content: $Uri" }
        $null = & $ResponsePolicyValidator $Uri $response
        $remoteContentLength = $null
        if ($null -ne $response.Content.Headers.ContentLength) {
            $remoteContentLength = [int64]$response.Content.Headers.ContentLength
            if ($remoteContentLength -gt $MaximumBytes) {
                throw "Remote Content-Length $remoteContentLength exceeds the $MaximumBytes-byte safety cap for $Uri"
            }
        }

        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = New-Object IO.FileStream($partial, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None, 1048576, [IO.FileOptions]::SequentialScan)
        $buffer = New-Object byte[] 1048576
        [int64]$totalBytes = 0
        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if (($totalBytes + $read) -gt $MaximumBytes) {
                throw "Stream exceeded the $MaximumBytes-byte safety cap for $Uri"
            }
            $outputStream.Write($buffer, 0, $read)
            $totalBytes += $read
        }
        $null = $outputStream.Flush($true)
        $null = $outputStream.Dispose()
        $outputStream = $null
        $null = $inputStream.Dispose()
        $inputStream = $null

        if ($totalBytes -le 0) { throw "Downloaded file is empty: $Uri" }
        if ($null -ne $remoteContentLength -and $totalBytes -ne $remoteContentLength) {
            throw "Observed $totalBytes bytes but HTTP Content-Length was $remoteContentLength for $Uri"
        }
        if ($null -ne $ExpectedBytes -and $totalBytes -ne [int64]$ExpectedBytes) {
            throw "Observed $totalBytes bytes but official GEO listing reported $([int64]$ExpectedBytes) for $Uri"
        }
        if ($Validator -and -not (& $Validator $partial)) {
            throw "Downloaded file failed content validation: $partial"
        }

        $hash = Get-FileSha256 -LiteralPath $partial
        Move-Item -LiteralPath $partial -Destination $DestinationPath -Force
        $null = Write-ChecksumSidecar -LiteralPath $DestinationPath -Hash $hash
        $metadata = New-ResponseMetadata -RequestUri $Uri -Response $response -ObservedBytes $totalBytes -LocalSha256 $hash
        $null = Write-JsonArtifact -LiteralPath $ResponseMetadataPath -Value $metadata

        return [pscustomobject]@{
            Status = 'Downloaded'
            Path = $DestinationPath
            Sha256 = $hash
            Bytes = $totalBytes
            RemoteContentLengthBytes = $remoteContentLength
            ResponseMetadataPath = $ResponseMetadataPath
        }
    }
    finally {
        if ($null -ne $outputStream) { $null = $outputStream.Dispose() }
        if ($null -ne $inputStream) { $null = $inputStream.Dispose() }
        if ($null -ne $response) { $null = $response.Dispose() }
        $null = $client.Dispose()
        $null = $handler.Dispose()
        # Failures intentionally retain .partial; only a validated final file
        # with a matching SHA-256 sidecar is treated as complete.
    }
}

Export-ModuleMember -Function @(
    'Get-Phase2NcbiRecordPlan',
    'Get-Phase2GeoPlan',
    'Get-FileSha256',
    'Get-ExpectedHashFromSidecar',
    'Write-ChecksumSidecar',
    'Test-VerifiedFile',
    'Write-TextArtifact',
    'Write-JsonArtifact',
    'Test-NonEmptyFile',
    'Test-GeoListingDocument',
    'Test-GeoProcessedFileName',
    'Test-GeoProcessedPayload',
    'Test-FastaRecord',
    'ConvertFrom-GeoDirectoryListing',
    'Assert-GeoUriPolicy',
    'Assert-NcbiEfetchUriPolicy',
    'Assert-GeoContentType',
    'Assert-NcbiEfetchContentType',
    'Get-ResponseMediaType',
    'New-GeoTransferPolicy',
    'New-NcbiEfetchTransferPolicy',
    'Test-RetriableHttpStatus',
    'Test-TransientTransportException',
    'Get-RetryDelaySeconds',
    'Invoke-HttpGetWithRetry',
    'ConvertTo-HeaderObject',
    'New-ResponseMetadata',
    'Invoke-AuditedStreamDownload'
)
