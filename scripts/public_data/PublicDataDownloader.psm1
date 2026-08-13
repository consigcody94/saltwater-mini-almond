Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ReferenceAssemblyPlan {
    [CmdletBinding()]
    param()

    $annotationTypes = 'GENOME_FASTA,GENOME_GFF,GENOME_GTF,GENOME_GBFF,RNA_FASTA,CDS_FASTA,PROT_FASTA,SEQUENCE_REPORT'
    $baseAccession = 'https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession'

    @(
        [pscustomobject]@{
            Accession = 'GCF_902201215.1'
            Organism = 'Prunus dulcis'
            Cultivar = 'Texas'
            Assembly = 'ALMONDv2'
            KnownComponentBytes = $null
        }
        [pscustomobject]@{
            Accession = 'GCA_008632915.2'
            Organism = 'Prunus dulcis'
            Cultivar = 'Lauranne'
            Assembly = 'Lauranne_v1.0'
            KnownComponentBytes = $null
        }
        [pscustomobject]@{
            Accession = 'GCA_021292205.2'
            Organism = 'Prunus dulcis'
            Cultivar = 'Nonpareil'
            Assembly = 'OSU_Pdul_2.5'
            # NCBI WGS exposes 72.7 MB for the compressed genomic FASTA.
            # This is a lower-bound component, not an estimate of the full package.
            KnownComponentBytes = [int64]72700000
        }
        [pscustomobject]@{
            Accession = 'GCF_000346465.2'
            Organism = 'Prunus persica'
            Cultivar = 'Lovell'
            Assembly = 'Prunus_persica_NCBIv2'
            KnownComponentBytes = $null
        }
    ) | ForEach-Object {
        $encodedTypes = [uri]::EscapeDataString($annotationTypes)
        $_ | Add-Member -NotePropertyName PackageUrl -NotePropertyValue (
            '{0}/{1}/download?include_annotation_type={2}' -f $baseAccession, $_.Accession, $encodedTypes
        )
        $_ | Add-Member -NotePropertyName ReportUrl -NotePropertyValue (
            '{0}/{1}/dataset_report' -f $baseAccession, $_.Accession
        )
        $_
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
        [Parameter(Mandatory)][string]$Hash
    )

    $sidecar = "$LiteralPath.sha256"
    $partial = "$sidecar.partial"
    $fileName = [IO.Path]::GetFileName($LiteralPath)
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($partial, ('{0}  {1}{2}' -f $Hash.ToLowerInvariant(), $fileName, [Environment]::NewLine), $encoding)
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
    $actual = Get-FileSha256 -LiteralPath $LiteralPath
    return $actual -eq $expected
}

function Get-BytesSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory)][byte[]]$Bytes)

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        -join ($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha.Dispose()
    }
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
        return [pscustomobject]@{ Path = $LiteralPath; Status = 'SkippedVerified'; Sha256 = $intendedHash }
    }

    $partial = "$LiteralPath.partial"
    [IO.File]::WriteAllBytes($partial, $bytes)
    $actualHash = Get-FileSha256 -LiteralPath $partial
    if ($actualHash -ne $intendedHash) { throw "In-memory and on-disk hashes differ for $partial" }
    Move-Item -LiteralPath $partial -Destination $LiteralPath -Force
    $null = Write-ChecksumSidecar -LiteralPath $LiteralPath -Hash $actualHash
    [pscustomobject]@{ Path = $LiteralPath; Status = 'Written'; Sha256 = $actualHash }
}

function Test-ZipArchive {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$LiteralPath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        $zip = [IO.Compression.ZipFile]::OpenRead($LiteralPath)
        try { return $zip.Entries.Count -gt 0 }
        finally { $zip.Dispose() }
    }
    catch { return $false }
}

function Test-JsonDocument {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$LiteralPath)

    try {
        $null = Get-Content -LiteralPath $LiteralPath -Raw | ConvertFrom-Json
        return $true
    }
    catch { return $false }
}

function Test-RetriableHttpStatus {
    [CmdletBinding()]
    param([Parameter(Mandatory)][int]$StatusCode)

    return ($StatusCode -eq 429) -or ($StatusCode -ge 500 -and $StatusCode -le 599)
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
        if ($null -ne $retryAfter.Delta) {
            $delay = [Math]::Ceiling($retryAfter.Delta.TotalSeconds)
        }
        elseif ($null -ne $retryAfter.Date) {
            $delay = [Math]::Ceiling(($retryAfter.Date - $UtcNow).TotalSeconds)
        }
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
        [ValidateRange(0.1, 300)][double]$BaseDelaySeconds = 2,
        [ValidateRange(1, 600)][double]$MaximumDelaySeconds = 120,
        [scriptblock]$RequestInvoker,
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
            $response = & $RequestInvoker $Client $Uri
            if ($null -eq $response) { throw "HTTP request invoker returned no response for $Uri" }
            $statusCode = [int]$response.StatusCode
            $retryable = Test-RetriableHttpStatus -StatusCode $statusCode
            if (-not $retryable -or $attempt -eq $MaximumAttempts) {
                return $response
            }

            $delay = Get-RetryDelaySeconds -Response $response -Attempt $attempt -BaseDelaySeconds $BaseDelaySeconds -MaximumDelaySeconds $MaximumDelaySeconds
            $response.Dispose()
            $response = $null
            Write-Warning ('HTTP {0} from {1}; retrying attempt {2}/{3} after {4:N0} second(s).' -f $statusCode, $Uri.Host, ($attempt + 1), $MaximumAttempts, $delay)
            & $SleepAction $delay
        }
    }
    catch {
        if ($null -ne $response) { $response.Dispose() }
        throw
    }
    finally {
        if ($ownsClient -and $null -ne $Client) { $Client.Dispose() }
    }
}

function Get-DestinationDriveInfo {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if ([string]::IsNullOrWhiteSpace($root)) {
        throw "Cannot resolve destination volume for: $Path"
    }
    return New-Object IO.DriveInfo($root)
}

function Invoke-StreamDownload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$DestinationPath,
        [ValidateRange(30, 86400)][int]$TimeoutSeconds = 1800,
        [ValidateRange(1, 10)][int]$MaximumAttempts = 4,
        [scriptblock]$Validator
    )

    $parent = Split-Path -Parent $DestinationPath
    if ($parent) { $null = New-Item -ItemType Directory -Path $parent -Force }

    if (Test-VerifiedFile -LiteralPath $DestinationPath) {
        if ((-not $Validator) -or (& $Validator $DestinationPath)) {
            return [pscustomobject]@{
                Path = $DestinationPath
                Status = 'SkippedVerified'
                Sha256 = Get-FileSha256 -LiteralPath $DestinationPath
                Bytes = (Get-Item -LiteralPath $DestinationPath).Length
            }
        }
    }

    $partial = "$DestinationPath.partial"
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object Net.Http.HttpClientHandler
    $client = New-Object Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
    $null = $client.DefaultRequestHeaders.UserAgent.ParseAdd('AlmondLab-PublicDataDownloader/1.0')
    $response = $null
    $inputStream = $null
    $outputStream = $null
    try {
        $response = Invoke-HttpGetWithRetry -Uri $Uri -Client $client -MaximumAttempts $MaximumAttempts
        $response.EnsureSuccessStatusCode()
        $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $outputStream = New-Object IO.FileStream($partial, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None, 1048576, [IO.FileOptions]::SequentialScan)
        $inputStream.CopyTo($outputStream, 1048576)
        $outputStream.Flush($true)
        $outputStream.Dispose()
        $outputStream = $null
        $inputStream.Dispose()
        $inputStream = $null

        if ($Validator -and -not (& $Validator $partial)) {
            throw "Downloaded file failed validation: $partial"
        }

        $hash = Get-FileSha256 -LiteralPath $partial
        $bytes = (Get-Item -LiteralPath $partial).Length
        Move-Item -LiteralPath $partial -Destination $DestinationPath -Force
        $null = Write-ChecksumSidecar -LiteralPath $DestinationPath -Hash $hash
        return [pscustomobject]@{ Path = $DestinationPath; Status = 'Downloaded'; Sha256 = $hash; Bytes = $bytes }
    }
    finally {
        if ($outputStream) { $outputStream.Dispose() }
        if ($inputStream) { $inputStream.Dispose() }
        if ($response) { $response.Dispose() }
        $client.Dispose()
        $handler.Dispose()
        # On failure the .partial is intentionally retained and can never satisfy
        # Test-VerifiedFile for the final path.
    }
}

function Export-DatasetCatalog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$PackagePath,
        [Parameter(Mandatory)][string]$DestinationPath,
        [switch]$Force
    )

    if (-not (Test-VerifiedFile -LiteralPath $PackagePath)) {
        throw "Refusing to read an unverified package: $PackagePath"
    }
    if (-not $Force -and (Test-VerifiedFile -LiteralPath $DestinationPath)) {
        return [pscustomobject]@{ Path = $DestinationPath; Status = 'SkippedVerified'; Sha256 = Get-FileSha256 -LiteralPath $DestinationPath }
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $parent = Split-Path -Parent $DestinationPath
    if ($parent) { $null = New-Item -ItemType Directory -Path $parent -Force }
    $partial = "$DestinationPath.partial"
    $zip = [IO.Compression.ZipFile]::OpenRead($PackagePath)
    try {
        $entry = $zip.Entries | Where-Object { $_.FullName -match '(^|[\\/])dataset_catalog\.json$' } | Select-Object -First 1
        if (-not $entry) { return $null }
        $inputStream = $entry.Open()
        $outputStream = New-Object IO.FileStream($partial, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $inputStream.CopyTo($outputStream) }
        finally {
            $outputStream.Dispose()
            $inputStream.Dispose()
        }
    }
    finally { $zip.Dispose() }

    if (-not (Test-JsonDocument -LiteralPath $partial)) {
        throw "Extracted dataset catalog is not valid JSON: $partial"
    }
    $hash = Get-FileSha256 -LiteralPath $partial
    Move-Item -LiteralPath $partial -Destination $DestinationPath -Force
    $null = Write-ChecksumSidecar -LiteralPath $DestinationPath -Hash $hash
    [pscustomobject]@{ Path = $DestinationPath; Status = 'Extracted'; Sha256 = $hash }
}

Export-ModuleMember -Function @(
    'Get-ReferenceAssemblyPlan',
    'Get-FileSha256',
    'Get-ExpectedHashFromSidecar',
    'Write-ChecksumSidecar',
    'Test-VerifiedFile',
    'Write-TextArtifact',
    'Test-ZipArchive',
    'Test-JsonDocument',
    'Test-RetriableHttpStatus',
    'Get-RetryDelaySeconds',
    'Invoke-HttpGetWithRetry',
    'Get-DestinationDriveInfo',
    'Invoke-StreamDownload',
    'Export-DatasetCatalog'
)
