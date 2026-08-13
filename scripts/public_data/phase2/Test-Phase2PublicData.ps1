[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$modulePath = Join-Path $PSScriptRoot 'Phase2PublicData.psm1'
$acquirePath = Join-Path $PSScriptRoot 'Acquire-Phase2PublicData.ps1'
Import-Module $modulePath -Force

$passed = 0
$failed = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-SmokeCase {
    param([string]$Name, [scriptblock]$Test)
    try {
        & $Test
        $script:passed++
        Write-Host "PASS $Name"
    }
    catch {
        $script:failed++
        Write-Host "FAIL $Name :: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function New-FakeResponse {
    param(
        [Parameter(Mandatory)][byte[]]$Bytes,
        [int]$StatusCode = 200,
        [switch]$WithoutContentLength,
        [string]$FinalUri = 'https://example.invalid/fixture',
        [string]$ContentType = 'application/octet-stream'
    )
    Add-Type -AssemblyName System.Net.Http
    $status = [Enum]::ToObject([Net.HttpStatusCode], $StatusCode)
    $response = New-Object Net.Http.HttpResponseMessage -ArgumentList $status
    $response.Content = New-Object Net.Http.ByteArrayContent -ArgumentList (,$Bytes)
    $response.Content.Headers.ContentType = New-Object Net.Http.Headers.MediaTypeHeaderValue($ContentType)
    $response.RequestMessage = New-Object Net.Http.HttpRequestMessage([Net.Http.HttpMethod]::Get, [uri]$FinalUri)
    if ($WithoutContentLength) { $response.Content.Headers.ContentLength = $null }
    return $response
}

function Compress-GzipBytes {
    param([Parameter(Mandatory)][byte[]]$Bytes)
    Add-Type -AssemblyName System.IO.Compression
    $memory = New-Object IO.MemoryStream
    $gzip = New-Object IO.Compression.GZipStream($memory, [IO.Compression.CompressionMode]::Compress, $true)
    try { $gzip.Write($Bytes, 0, $Bytes.Length) }
    finally { $gzip.Dispose() }
    try { return $memory.ToArray() }
    finally { $memory.Dispose() }
}

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('almondlab-phase2-smoke-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $testRoot

try {
    Invoke-SmokeCase 'NCBI allowlist is exactly the twelve approved accession versions' {
        $plan = @(Get-Phase2NcbiRecordPlan)
        $expected = @(
            'AJ972674.1', 'CAI99405.1', 'EU879059.1', 'ACJ63441.1',
            'XM_020565174.1', 'XP_020420763.1', 'XM_020564808.1', 'XP_020420397.1',
            'XM_020568644.1', 'XP_020424233.1', 'XM_007201987.2', 'XP_007202049.1'
        )
        $expectedDb = @{
            'AJ972674.1' = 'nuccore'; 'CAI99405.1' = 'protein'
            'EU879059.1' = 'nuccore'; 'ACJ63441.1' = 'protein'
            'XM_020565174.1' = 'nuccore'; 'XP_020420763.1' = 'protein'
            'XM_020564808.1' = 'nuccore'; 'XP_020420397.1' = 'protein'
            'XM_020568644.1' = 'nuccore'; 'XP_020424233.1' = 'protein'
            'XM_007201987.2' = 'nuccore'; 'XP_007202049.1' = 'protein'
        }
        Assert-True ($plan.Count -eq 12) "Expected 12 records, found $($plan.Count)."
        Assert-True ((@($plan.Accession | Sort-Object) -join ',') -eq (@($expected | Sort-Object) -join ',')) 'NCBI accession allowlist differs.'
        Assert-True ((@($plan | Where-Object Db -eq 'nuccore').Count) -eq 6) 'Expected six nucleotide records.'
        Assert-True ((@($plan | Where-Object Db -eq 'protein').Count) -eq 6) 'Expected six protein records.'
        foreach ($record in $plan) {
            Assert-True ($record.Db -eq $expectedDb[$record.Accession]) "Wrong database for $($record.Accession)."
            Assert-True ($record.Url -match '^https://eutils\.ncbi\.nlm\.nih\.gov/entrez/eutils/efetch\.fcgi\?') 'Non-EFetch URL in NCBI plan.'
            Assert-True ($record.Url -match ('id=' + [regex]::Escape($record.Accession))) 'URL does not contain exact accession.version.'
            Assert-True ($record.Url -match ('db=' + $record.Db)) 'URL database differs from allowlist.'
            Assert-True ($record.Url -notmatch '(?i)fastq|/sra/|/ena/|doi\.org|pubmed') 'Forbidden raw-read/article URL in plan.'
        }
    }

    Invoke-SmokeCase 'GEO scope is pinned to the official GSE254853 supplementary directory' {
        $plan = Get-Phase2GeoPlan
        Assert-True ($plan.ListingUrl -eq 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/') 'Unexpected GEO listing URL.'
        Assert-True ($plan.FilePrefix -eq 'GSE254853_') 'Unexpected GEO filename prefix.'
        Assert-True ($plan.MaximumTotalBytes -eq 250000000) 'Unexpected GEO total safety cap.'
    }

    Invoke-SmokeCase 'GEO listing parser preserves files URLs and exact exposed byte sizes' {
        $html = @'
<html><body><pre>
<a href="../">Parent Directory</a>
<a href="GSE254853_Texas_F0_transcripts.fasta.gz">GSE254853_Texas_F0_transcripts.fasta.gz</a> 2024-03-18 12:00 13700000
<a href="GSE254853_rawdata_general.csv.gz">GSE254853_rawdata_general.csv.gz</a> 2024-03-18 12:00 423100
<a href="GSE254853_rawmatrix_ASE.csv.gz">GSE254853_rawmatrix_ASE.csv.gz</a> 2024-03-18 12:00 178400
<a href="GSE254853_rlogmatrix_ASE.csv.gz">GSE254853_rlogmatrix_ASE.csv.gz</a> 2024-03-18 12:00 781900
<a href="GSE254853_rlogmatrix_general.csv.gz">GSE254853_rlogmatrix_general.csv.gz</a> 2024-03-18 12:00 1700000
<a href="md5sum.txt">md5sum.txt</a> 2024-03-18 12:00 500
</pre></body></html>
'@
        $entries = @(ConvertFrom-GeoDirectoryListing -Html $html -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/')
        Assert-True ($entries.Count -eq 5) "Expected five processed files, found $($entries.Count)."
        Assert-True (($entries.Name -join ',') -eq (($entries.Name | Sort-Object) -join ',')) 'GEO entries are not deterministically sorted.'
        $transcripts = $entries | Where-Object Name -eq 'GSE254853_Texas_F0_transcripts.fasta.gz'
        Assert-True ($transcripts.RemoteSizeBytes -eq 13700000) 'Exact listing byte size was not preserved.'
        Assert-True ($transcripts.Url -eq 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/GSE254853_Texas_F0_transcripts.fasta.gz') 'Resolved GEO URL differs.'
    }

    Invoke-SmokeCase 'GEO parser fails closed on raw-read payloads and unsafe paths' {
        $rawHtml = '<a href="GSE254853_reads.fastq.gz">GSE254853_reads.fastq.gz</a> 2024-03-18 12:00 10'
        $rawRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $rawHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $rawRejected = $_.Exception.Message -match 'Raw-data payload is forbidden' }
        Assert-True $rawRejected 'Raw FASTQ listing entry was not rejected.'

        $rawTarHtml = '<a href="GSE254853_RAW.tar">GSE254853_RAW.tar</a> 2024-03-18 12:00 10'
        $rawTarRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $rawTarHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $rawTarRejected = $_.Exception.Message -match 'Raw-data payload is forbidden' }
        Assert-True $rawTarRejected 'GEO RAW archive was not rejected.'

        $archiveHtml = '<a href="GSE254853_reads.tar.gz">GSE254853_reads.tar.gz</a> 2024-03-18 12:00 10'
        $archiveRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $archiveHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $archiveRejected = $_.Exception.Message -match 'Raw-data payload is forbidden' }
        Assert-True $archiveRejected 'Unreviewed GEO archive was not rejected.'

        $pathHtml = '<a href="GSE254853_../escape.txt">GSE254853_../escape.txt</a> 2024-03-18 12:00 10'
        $pathRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $pathHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $pathRejected = $_.Exception.Message -match 'Unsafe GEO supplementary filename' }
        Assert-True $pathRejected 'Unsafe GEO path was not rejected.'

        $duplicateHtml = @'
<a href="GSE254853_counts.csv">GSE254853_counts.csv</a> 2024-03-18 12:00 10
<a href="GSE254853_COUNTS.CSV">GSE254853_COUNTS.CSV</a> 2024-03-18 12:00 10
'@
        $duplicateRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $duplicateHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $duplicateRejected = $_.Exception.Message -match 'Duplicate GEO' }
        Assert-True $duplicateRejected 'Case-variant duplicate GEO entry was not rejected.'

        $encodedPathHtml = '<a href="GSE254853_%252fescape.csv">GSE254853_%252fescape.csv</a> 2024-03-18 12:00 10'
        $encodedPathRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $encodedPathHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $encodedPathRejected = $_.Exception.Message -match 'Unsafe GEO' }
        Assert-True $encodedPathRejected 'Double-encoded GEO separator was not rejected.'

        $encodedPrefixHtml = '<a href="GSE254853%5fcounts.csv">GSE254853%5fcounts.csv</a> 2024-03-18 12:00 10'
        $encodedPrefixRejected = $false
        try { $null = ConvertFrom-GeoDirectoryListing -Html $encodedPrefixHtml -BaseUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/' }
        catch { $encodedPrefixRejected = $_.Exception.Message -match 'Unsafe GEO' }
        Assert-True $encodedPrefixRejected 'Encoded GEO prefix separator was silently skipped.'
    }

    Invoke-SmokeCase 'GEO processed filename policy is a positive format allowlist' {
        $safe = @(
            'GSE254853_counts.csv', 'GSE254853_counts.csv.gz',
            'GSE254853_matrix.tsv.gz', 'GSE254853_notes.txt.gz',
            'GSE254853_transcripts.fasta.gz', 'GSE254853_annotations.gff3.gz',
            'GSE254853_table.xlsx', 'GSE254853_legacy.xls'
        )
        $unsafe = @(
            'GSE254853_reads.tar.xz', 'GSE254853_bundle.7z', 'GSE254853_bundle.zip',
            'GSE254853_.hidden.csv', 'GSE254853_data..csv', 'GSE254853_RAW.csv.gz',
            'GSE254853_counts.csv.gz.gz', 'GSE254853_payload.bin',
            'GSE254853_%2fescape.csv', 'GSE254853_%252fescape.csv'
        )
        foreach ($name in $safe) { Assert-True (Test-GeoProcessedFileName -Name $name) "Safe filename rejected: $name" }
        foreach ($name in $unsafe) { Assert-True (-not (Test-GeoProcessedFileName -Name $name)) "Unsafe filename accepted: $name" }
    }

    Invoke-SmokeCase 'GEO payload validation requires nonempty plain files and genuine single gzip streams' {
        $plainPath = Join-Path $testRoot 'payload-validation\GSE254853_counts.csv'
        $gzipPath = Join-Path $testRoot 'payload-validation\GSE254853_counts.csv.gz'
        $fakeGzipPath = Join-Path $testRoot 'payload-validation\GSE254853_fake.csv.gz'
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $plainPath) -Force
        $plainBytes = (New-Object Text.UTF8Encoding($false)).GetBytes("sample,count`nA,1`n")
        [IO.File]::WriteAllBytes($plainPath, $plainBytes)
        [IO.File]::WriteAllBytes($gzipPath, (Compress-GzipBytes -Bytes $plainBytes))
        [IO.File]::WriteAllBytes($fakeGzipPath, $plainBytes)
        Assert-True (Test-GeoProcessedPayload -LiteralPath $plainPath -Name ([IO.Path]::GetFileName($plainPath))) 'Valid plain processed payload was rejected.'
        Assert-True (Test-GeoProcessedPayload -LiteralPath $gzipPath -Name ([IO.Path]::GetFileName($gzipPath))) 'Valid gzip processed payload was rejected.'
        Assert-True (-not (Test-GeoProcessedPayload -LiteralPath $fakeGzipPath -Name ([IO.Path]::GetFileName($fakeGzipPath)))) 'A non-gzip payload with .gz suffix was accepted.'
    }

    Invoke-SmokeCase 'source response policies reject final URL and content-type drift' {
        $geoName = 'GSE254853_counts.csv.gz'
        $geoRequested = [uri]"https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/$geoName"
        $geoPolicy = New-GeoTransferPolicy -ExpectedFileName $geoName
        $gzipBytes = Compress-GzipBytes -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes('a,b'))
        $badGeo = New-FakeResponse -Bytes $gzipBytes -FinalUri 'https://evil.example/GSE254853_counts.csv.gz' -ContentType 'application/gzip'
        try {
            $rejected = $false
            try { $null = & $geoPolicy.ResponseValidator $geoRequested $badGeo }
            catch { $rejected = $_.Exception.Message -match 'GEO.*URL|official GEO' }
            Assert-True $rejected 'GEO cross-host redirect was accepted.'
        }
        finally { $badGeo.Dispose() }

        $record = @(Get-Phase2NcbiRecordPlan | Where-Object Accession -eq 'AJ972674.1')[0]
        $efetchPolicy = New-NcbiEfetchTransferPolicy -Accession $record.Accession -Database $record.Db
        $drifted = $record.Url -replace 'id=AJ972674\.1', 'id=EU879059.1'
        $badEfetch = New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes(">AJ972674.1 x`nATGC`n")) -FinalUri $drifted -ContentType 'text/plain'
        try {
            $rejected = $false
            try { $null = & $efetchPolicy.ResponseValidator ([uri]$record.Url) $badEfetch }
            catch { $rejected = $_.Exception.Message -match 'EFetch.*URL|query' }
            Assert-True $rejected 'EFetch accession redirect drift was accepted.'
        }
        finally { $badEfetch.Dispose() }

        $wrongType = New-FakeResponse -Bytes $gzipBytes -FinalUri $geoRequested.AbsoluteUri -ContentType 'text/html'
        try {
            $rejected = $false
            try { $null = & $geoPolicy.ResponseValidator $geoRequested $wrongType }
            catch { $rejected = $_.Exception.Message -match 'content type' }
            Assert-True $rejected 'Incompatible GEO content type was accepted.'
        }
        finally { $wrongType.Dispose() }

        $goodGeo = New-FakeResponse -Bytes $gzipBytes -FinalUri $geoRequested.AbsoluteUri -ContentType 'application/x-gzip'
        try { Assert-True (& $geoPolicy.ResponseValidator $geoRequested $goodGeo) 'Compatible GEO response was rejected.' }
        finally { $goodGeo.Dispose() }

        $goodEfetch = New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes(">AJ972674.1 x`nATGC`n")) -FinalUri $record.Url -ContentType 'text/plain'
        try { Assert-True (& $efetchPolicy.ResponseValidator ([uri]$record.Url) $goodEfetch) 'Compatible EFetch response was rejected.' }
        finally { $goodEfetch.Dispose() }

        $wrongEfetchType = New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes('<html>error</html>')) -FinalUri $record.Url -ContentType 'text/html'
        try {
            $rejected = $false
            try { $null = & $efetchPolicy.ResponseValidator ([uri]$record.Url) $wrongEfetchType }
            catch { $rejected = $_.Exception.Message -match 'content type' }
            Assert-True $rejected 'Incompatible EFetch content type was accepted.'
        }
        finally { $wrongEfetchType.Dispose() }

        $extraQuery = $record.Url + '&email=unexpected%40example.org'
        $extraResponse = New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes(">AJ972674.1 x`nATGC`n")) -FinalUri $extraQuery -ContentType 'text/plain'
        try {
            $rejected = $false
            try { $null = & $efetchPolicy.ResponseValidator ([uri]$record.Url) $extraResponse }
            catch { $rejected = $_.Exception.Message -match 'query' }
            Assert-True $rejected 'EFetch response with an extra query field was accepted.'
        }
        finally { $extraResponse.Dispose() }

        $listingPolicy = New-GeoTransferPolicy -Listing
        $listingUri = [uri](Get-Phase2GeoPlan).ListingUrl
        $badListing = New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes('<html></html>')) -FinalUri 'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/' -ContentType 'text/html'
        try {
            $rejected = $false
            try { $null = & $listingPolicy.ResponseValidator $listingUri $badListing }
            catch { $rejected = $_.Exception.Message -match 'GEO.*URL|official GEO' }
            Assert-True $rejected 'GEO listing redirect outside the exact supplementary directory was accepted.'
        }
        finally { $badListing.Dispose() }
    }

    Invoke-SmokeCase 'redirect policy is enforced before any response body is accepted' {
        $geoName = 'GSE254853_counts.csv'
        $geoUri = [uri]"https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/$geoName"
        $geoPolicy = New-GeoTransferPolicy -ExpectedFileName $geoName
        $geoDestination = Join-Path $testRoot 'redirect-guard\GSE254853_counts.csv'
        $geoMetadata = Join-Path $testRoot 'redirect-guard\geo.response.json'
        $script:geoRequests = 0
        $geoRejected = $false
        try {
            $null = Invoke-AuditedStreamDownload -Uri $geoUri -DestinationPath $geoDestination -ResponseMetadataPath $geoMetadata -MaximumBytes 1000 -MaximumAttempts 3 -RequestInvoker {
                param($client, $uri)
                $script:geoRequests++
                New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes('a,b')) -StatusCode 503 -FinalUri 'https://evil.example/GSE254853_counts.csv' -ContentType 'text/csv'
            } -SleepAction { throw 'Redirect validation must not retry.' } -ResponsePolicyValidator $geoPolicy.ResponseValidator -StoredMetadataValidator $geoPolicy.StoredMetadataValidator -Validator { param($path) Test-NonEmptyFile -LiteralPath $path }
        }
        catch { $geoRejected = $_.Exception.Message -match 'GEO.*URL|official GEO' }
        Assert-True $geoRejected 'Malicious GEO final URL was not rejected by the downloader.'
        Assert-True ($script:geoRequests -eq 1) 'GEO redirect validation was retried before its final URL was checked.'
        Assert-True (-not (Test-Path -LiteralPath "$geoDestination.partial")) 'GEO redirect body was written before final-URL validation.'

        $record = @(Get-Phase2NcbiRecordPlan | Where-Object Accession -eq 'AJ972674.1')[0]
        $efetchPolicy = New-NcbiEfetchTransferPolicy -Accession $record.Accession -Database $record.Db
        $efetchDestination = Join-Path $testRoot 'redirect-guard\AJ972674.1.fasta'
        $efetchMetadata = Join-Path $testRoot 'redirect-guard\efetch.response.json'
        $script:efetchRequests = 0
        $efetchRejected = $false
        try {
            $null = Invoke-AuditedStreamDownload -Uri $record.Url -DestinationPath $efetchDestination -ResponseMetadataPath $efetchMetadata -MaximumBytes 1000 -MaximumAttempts 3 -RequestInvoker {
                param($client, $uri)
                $script:efetchRequests++
                New-FakeResponse -Bytes ((New-Object Text.UTF8Encoding($false)).GetBytes(">AJ972674.1 x`nATGC`n")) -FinalUri 'https://evil.example/entrez/eutils/efetch.fcgi?db=nuccore&id=AJ972674.1&rettype=fasta&retmode=text&tool=AlmondLabPhase2' -ContentType 'text/plain'
            } -SleepAction { throw 'Redirect validation must not retry.' } -ResponsePolicyValidator $efetchPolicy.ResponseValidator -StoredMetadataValidator $efetchPolicy.StoredMetadataValidator -Validator { param($path) Test-FastaRecord -LiteralPath $path -ExpectedAccession 'AJ972674.1' }
        }
        catch { $efetchRejected = $_.Exception.Message -match 'EFetch.*URL|official NCBI' }
        Assert-True $efetchRejected 'Malicious EFetch final URL was not rejected by the downloader.'
        Assert-True ($script:efetchRequests -eq 1) 'EFetch redirect validation was retried.'
        Assert-True (-not (Test-Path -LiteralPath "$efetchDestination.partial")) 'EFetch redirect body was written before final-URL validation.'
    }

    Invoke-SmokeCase 'FASTA validation requires one exact accession-version header' {
        $nucleotide = Join-Path $testRoot 'AJ972674.1.fasta'
        $protein = Join-Path $testRoot 'CAI99405.1.fasta'
        $wrong = Join-Path $testRoot 'wrong.fasta'
        $multi = Join-Path $testRoot 'multi.fasta'
        [IO.File]::WriteAllText($nucleotide, ">AJ972674.1 fixture nucleotide`nATGCNNATGC`n")
        [IO.File]::WriteAllText($protein, ">CAI99405.1 fixture protein`nMSTXK*`n")
        [IO.File]::WriteAllText($wrong, ">AJ972674.2 wrong version`nATGC`n")
        [IO.File]::WriteAllText($multi, ">AJ972674.1 one`nATGC`n>OTHER.1 two`nATGC`n")
        Assert-True (Test-FastaRecord -LiteralPath $nucleotide -ExpectedAccession 'AJ972674.1') 'Valid nucleotide FASTA failed.'
        Assert-True (Test-FastaRecord -LiteralPath $protein -ExpectedAccession 'CAI99405.1') 'Valid protein FASTA failed.'
        Assert-True (-not (Test-FastaRecord -LiteralPath $wrong -ExpectedAccession 'AJ972674.1')) 'Wrong accession version passed.'
        Assert-True (-not (Test-FastaRecord -LiteralPath $multi -ExpectedAccession 'AJ972674.1')) 'Multi-record response passed.'
    }

    Invoke-SmokeCase 'HTTP retry honors Retry-After without real requests' {
        Add-Type -AssemblyName System.Net.Http
        $script:retryCalls = 0
        $delays = New-Object Collections.Generic.List[double]
        $request = {
            param($client, $uri)
            $script:retryCalls++
            if ($script:retryCalls -eq 1) {
                $response = New-FakeResponse -Bytes ([byte[]](1)) -StatusCode 429
                $response.Headers.RetryAfter = New-Object Net.Http.Headers.RetryConditionHeaderValue([TimeSpan]::FromSeconds(6))
                return $response
            }
            return New-FakeResponse -Bytes ([byte[]](1))
        }
        $response = Invoke-HttpGetWithRetry -Uri 'https://eutils.ncbi.nlm.nih.gov/fixture' -MaximumAttempts 3 -RequestInvoker $request -SleepAction { param($seconds) $delays.Add([double]$seconds) }
        try {
            Assert-True ($script:retryCalls -eq 2) 'Retry attempt count differs.'
            Assert-True ($delays.Count -eq 1 -and $delays[0] -eq 6) 'Retry-After was not honored.'
            Assert-True ([int]$response.StatusCode -eq 200) 'Retry did not return success.'
        }
        finally { $response.Dispose() }
    }

    Invoke-SmokeCase 'only clearly transient transport exceptions are retried' {
        Add-Type -AssemblyName System.Net.Http
        $script:transportCalls = 0
        $delays = New-Object Collections.Generic.List[double]
        $transient = {
            param($client, $uri)
            $script:transportCalls++
            if ($script:transportCalls -eq 1) { throw (New-Object Threading.Tasks.TaskCanceledException('fixture timeout')) }
            return New-FakeResponse -Bytes ([byte[]](1)) -FinalUri $uri.AbsoluteUri
        }
        $response = Invoke-HttpGetWithRetry -Uri 'https://eutils.ncbi.nlm.nih.gov/fixture' -MaximumAttempts 3 -RequestInvoker $transient -SleepAction { param($seconds) $delays.Add([double]$seconds) }
        try {
            Assert-True ($script:transportCalls -eq 2) 'Transient timeout was not retried once.'
            Assert-True ($delays.Count -eq 1 -and $delays[0] -eq 2) 'Transient retry delay differs.'
        }
        finally { $response.Dispose() }

        $script:transportCalls = 0
        $permanent = { param($client, $uri) $script:transportCalls++; throw (New-Object IO.InvalidDataException('validation fixture')) }
        $didThrow = $false
        try { $null = Invoke-HttpGetWithRetry -Uri 'https://eutils.ncbi.nlm.nih.gov/fixture' -MaximumAttempts 3 -RequestInvoker $permanent -SleepAction { throw 'Must not sleep.' } }
        catch { $didThrow = $_.Exception -is [IO.InvalidDataException] }
        Assert-True $didThrow 'Nontransport exception was not propagated.'
        Assert-True ($script:transportCalls -eq 1) 'Nontransport exception was retried.'

        $script:transportCalls = 0
        $badRequest = {
            param($client, $uri)
            $script:transportCalls++
            New-FakeResponse -Bytes ([byte[]](1)) -StatusCode 400 -FinalUri $uri.AbsoluteUri
        }
        $response = Invoke-HttpGetWithRetry -Uri 'https://eutils.ncbi.nlm.nih.gov/fixture' -MaximumAttempts 3 -RequestInvoker $badRequest -SleepAction { throw 'HTTP 400 must not sleep.' }
        try {
            Assert-True ([int]$response.StatusCode -eq 400) 'HTTP 400 response was not returned to the caller.'
            Assert-True ($script:transportCalls -eq 1) 'HTTP 400 was retried.'
        }
        finally { $response.Dispose() }
    }

    Invoke-SmokeCase 'audited stream emits one result and preserves response metadata' {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes(">XM_020565174.1 fixture`nATGCNN`n")
        $record = @(Get-Phase2NcbiRecordPlan | Where-Object Accession -eq 'XM_020565174.1')[0]
        $policy = New-NcbiEfetchTransferPolicy -Accession $record.Accession -Database $record.Db
        $request = { param($client, $uri) New-FakeResponse -Bytes $bytes -FinalUri $uri.AbsoluteUri -ContentType 'text/plain' }
        $destination = Join-Path $testRoot 'stream\XM_020565174.1.fasta'
        $metadata = Join-Path $testRoot 'stream\response.json'
        $results = @(Invoke-AuditedStreamDownload -Uri $record.Url -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 10000 -ExpectedBytes $bytes.Length -RequestInvoker $request -SleepAction { throw 'Unexpected sleep.' } -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator -Validator {
            param($path) Test-FastaRecord -LiteralPath $path -ExpectedAccession 'XM_020565174.1'
        })
        Assert-True ($results.Count -eq 1) "Expected one result, found $($results.Count)."
        $result = $results[0]
        Assert-True ($result.GetType().FullName -eq 'System.Management.Automation.PSCustomObject') 'Result is not PSCustomObject.'
        Assert-True ($result.Status -eq 'Downloaded') 'Unexpected stream status.'
        Assert-True ($result.Bytes -eq $bytes.Length) 'Observed byte count differs.'
        Assert-True (Test-VerifiedFile -LiteralPath $destination) 'Payload SHA-256 sidecar failed.'
        Assert-True (Test-VerifiedFile -LiteralPath $metadata) 'Response metadata SHA-256 sidecar failed.'
        $responseMetadata = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
        Assert-True ($responseMetadata.request_url -eq $record.Url) 'Request URL not preserved in response metadata.'
        Assert-True ($responseMetadata.final_url -eq $record.Url) 'Final URL not preserved in response metadata.'
        Assert-True ($responseMetadata.content_type -eq 'text/plain') 'Content type not preserved in response metadata.'
        Assert-True ($responseMetadata.observed_bytes -eq $bytes.Length) 'Response metadata byte count differs.'
        Assert-True ($responseMetadata.local_sha256 -eq $result.Sha256) 'Response metadata hash differs.'
    }

    Invoke-SmokeCase 'verified payload and metadata skip without invoking HTTP' {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes('processed-data')
        $uri = [uri]'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/GSE254853_processed.csv'
        $policy = New-GeoTransferPolicy -ExpectedFileName 'GSE254853_processed.csv'
        $firstRequest = { param($client, $requestUri) New-FakeResponse -Bytes $bytes -FinalUri $requestUri.AbsoluteUri -ContentType 'text/csv' }
        $destination = Join-Path $testRoot 'skip\GSE254853_processed.csv'
        $metadata = Join-Path $testRoot 'skip\response.json'
        $first = Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 1000 -RequestInvoker $firstRequest -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator -Validator { param($path) Test-NonEmptyFile -LiteralPath $path }
        Assert-True ($first.Status -eq 'Downloaded') 'Initial fixture was not downloaded.'
        $neverRequest = { throw 'HTTP invoker must not run for a verified skip.' }
        $results = @(Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 1000 -RequestInvoker $neverRequest -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator -Validator { param($path) Test-NonEmptyFile -LiteralPath $path })
        Assert-True ($results.Count -eq 1 -and $results[0].Status -eq 'SkippedVerified') 'Verified file did not return one skip result.'
    }

    Invoke-SmokeCase 'correctly hashed but semantically forged skip metadata is rejected' {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes('processed-data')
        $uri = [uri]'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/GSE254853_counts.csv'
        $policy = New-GeoTransferPolicy -ExpectedFileName 'GSE254853_counts.csv'
        $request = { param($client, $requestUri) New-FakeResponse -Bytes $bytes -FinalUri $requestUri.AbsoluteUri -ContentType 'text/csv' }
        $destination = Join-Path $testRoot 'forged\GSE254853_counts.csv'
        $metadata = Join-Path $testRoot 'forged\response.json'
        $null = Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 1000 -RequestInvoker $request -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator -Validator { param($path) Test-NonEmptyFile -LiteralPath $path }
        $validJson = Get-Content -LiteralPath $metadata -Raw
        $forgeries = @(
            [pscustomobject]@{ Field = 'status_code'; Value = 302 }
            [pscustomobject]@{ Field = 'observed_bytes'; Value = 999 }
            [pscustomobject]@{ Field = 'remote_content_length_bytes'; Value = 999 }
            [pscustomobject]@{ Field = 'content_type'; Value = 'text/html' }
            [pscustomobject]@{ Field = 'final_url'; Value = 'https://evil.example/payload' }
            [pscustomobject]@{ Field = 'request_url'; Value = 'https://evil.example/request' }
        )
        foreach ($case in $forgeries) {
            $forged = $validJson | ConvertFrom-Json
            $forged.($case.Field) = $case.Value
            $null = Write-JsonArtifact -LiteralPath $metadata -Value $forged
            $didThrow = $false
            try {
                $null = Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 1000 -RequestInvoker { throw 'HTTP must not run.' } -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator -Validator { param($path) Test-NonEmptyFile -LiteralPath $path }
            }
            catch { $didThrow = $_.Exception.Message -match 'metadata|status|observed|length|URL|content type' }
            Assert-True $didThrow "Semantically forged metadata field passed verified skip: $($case.Field)"
        }
    }

    Invoke-SmokeCase 'stream safety cap leaves partial and never promotes final' {
        $bytes = New-Object byte[] 64
        for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [byte]($i + 1) }
        $uri = [uri]'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/GSE254853_too-large.csv'
        $policy = New-GeoTransferPolicy -ExpectedFileName 'GSE254853_too-large.csv'
        $request = { param($client, $requestUri) New-FakeResponse -Bytes $bytes -WithoutContentLength -FinalUri $requestUri.AbsoluteUri -ContentType 'text/csv' }
        $destination = Join-Path $testRoot 'cap\GSE254853_too-large.csv'
        $metadata = Join-Path $testRoot 'cap\response.json'
        $didThrow = $false
        try {
            $null = Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 10 -RequestInvoker $request -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator
        }
        catch { $didThrow = $_.Exception.Message -match 'safety cap' }
        Assert-True $didThrow 'Oversized stream did not fail its safety cap.'
        Assert-True (Test-Path -LiteralPath "$destination.partial") 'Failed stream did not retain .partial.'
        Assert-True (-not (Test-Path -LiteralPath $destination)) 'Failed stream was promoted.'
        Assert-True (-not (Test-Path -LiteralPath "$destination.sha256")) 'Failed stream received a checksum sidecar.'
    }

    Invoke-SmokeCase 'official listing size mismatch fails before promotion' {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes('abc')
        $uri = [uri]'https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/GSE254853_size-mismatch.csv'
        $policy = New-GeoTransferPolicy -ExpectedFileName 'GSE254853_size-mismatch.csv'
        $request = { param($client, $requestUri) New-FakeResponse -Bytes $bytes -FinalUri $requestUri.AbsoluteUri -ContentType 'text/csv' }
        $destination = Join-Path $testRoot 'size-mismatch\GSE254853_size-mismatch.csv'
        $metadata = Join-Path $testRoot 'size-mismatch\response.json'
        $didThrow = $false
        try {
            $null = Invoke-AuditedStreamDownload -Uri $uri -DestinationPath $destination -ResponseMetadataPath $metadata -MaximumBytes 100 -ExpectedBytes 4 -RequestInvoker $request -ResponsePolicyValidator $policy.ResponseValidator -StoredMetadataValidator $policy.StoredMetadataValidator
        }
        catch { $didThrow = $_.Exception.Message -match 'official GEO listing reported 4' }
        Assert-True $didThrow 'Listing-size mismatch did not fail.'
        Assert-True (Test-Path -LiteralPath "$destination.partial") 'Mismatch did not retain .partial.'
        Assert-True (-not (Test-Path -LiteralPath $destination)) 'Mismatched file was promoted.'
    }

    Invoke-SmokeCase 'JSON receipt artifact is hashed and tamper-detecting' {
        $receiptPath = Join-Path $testRoot 'receipt\receipt.json'
        $result = Write-JsonArtifact -LiteralPath $receiptPath -Value ([pscustomobject]@{ status = 'fixture'; count = 12 })
        Assert-True ($result.Status -eq 'Written') 'Receipt was not written.'
        Assert-True (Test-VerifiedFile -LiteralPath $receiptPath) 'Receipt did not verify.'
        Add-Content -LiteralPath $receiptPath -Value 'tamper'
        Assert-True (-not (Test-VerifiedFile -LiteralPath $receiptPath)) 'Tampered receipt incorrectly verified.'
    }

    Invoke-SmokeCase 'generic receipt lists serialize as explicit arrays' {
        $items = New-Object Collections.Generic.List[object]
        $items.Add([pscustomobject]@{ accession = 'AJ972674.1' })
        $value = [pscustomobject]@{ records = $items.ToArray() }
        $jsonPath = Join-Path $testRoot 'receipt\array-receipt.json'
        $null = Write-JsonArtifact -LiteralPath $jsonPath -Value $value
        $parsed = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
        Assert-True (@($parsed.records).Count -eq 1) 'Receipt list did not serialize as a JSON array.'
        Assert-True ($parsed.records[0].accession -eq 'AJ972674.1') 'Receipt array content differs.'
    }

    Invoke-SmokeCase 'full execute orchestration works with explicitly injected offline transport' {
        $encoding = New-Object Text.UTF8Encoding($false)
        $geoPayloads = @{
            'GSE254853_fixture_counts.csv.gz' = (Compress-GzipBytes -Bytes ($encoding.GetBytes("sample,count`nA,1`n")))
            'GSE254853_fixture_transcripts.fasta.gz' = (Compress-GzipBytes -Bytes ($encoding.GetBytes(">fixture`nATGC`n")))
        }
        $listingHtml = @"
<html><body><pre>
<a href="GSE254853_fixture_counts.csv.gz">GSE254853_fixture_counts.csv.gz</a> 2026-08-12 12:00 $($geoPayloads['GSE254853_fixture_counts.csv.gz'].Length)
<a href="GSE254853_fixture_transcripts.fasta.gz">GSE254853_fixture_transcripts.fasta.gz</a> 2026-08-12 12:00 $($geoPayloads['GSE254853_fixture_transcripts.fasta.gz'].Length)
</pre></body></html>
"@
        $listingBytes = $encoding.GetBytes($listingHtml)
        $recordLookup = @{}
        foreach ($record in @(Get-Phase2NcbiRecordPlan)) { $recordLookup[$record.Accession] = $record }
        $request = {
            param($client, $uri)
            if ($uri.AbsoluteUri -eq (Get-Phase2GeoPlan).ListingUrl) {
                return New-FakeResponse -Bytes $listingBytes -FinalUri $uri.AbsoluteUri -ContentType 'text/html'
            }
            if ($uri.Host -eq 'ftp.ncbi.nlm.nih.gov') {
                $name = [uri]::UnescapeDataString([IO.Path]::GetFileName($uri.AbsolutePath))
                if (-not $geoPayloads.ContainsKey($name)) { throw "Unexpected GEO fixture URL: $uri" }
                return New-FakeResponse -Bytes $geoPayloads[$name] -FinalUri $uri.AbsoluteUri -ContentType 'application/x-gzip'
            }
            if ($uri.Host -eq 'eutils.ncbi.nlm.nih.gov' -and $uri.Query -match '(?:\?|&)id=(?<id>[^&]+)') {
                $accession = [uri]::UnescapeDataString($Matches['id'])
                if (-not $recordLookup.ContainsKey($accession)) { throw "Unexpected NCBI fixture accession: $accession" }
                $sequence = if ($recordLookup[$accession].Molecule -eq 'protein') { 'MSTXK' } else { 'ATGCNN' }
                return New-FakeResponse -Bytes $encoding.GetBytes(">$accession fixture`n$sequence`n") -FinalUri $uri.AbsoluteUri -ContentType 'text/plain'
            }
            throw "Unexpected offline fixture URL: $uri"
        }.GetNewClosure()
        $outputRoot = Join-Path $testRoot 'full-execute'
        $results = @(& $acquirePath -Profile All -Execute -OutputRoot $outputRoot -AllowTestTransport -RequestInvoker $request -RetrySleepAction { throw 'Unexpected retry sleep.' } -PacingAction { param($milliseconds) })
        Assert-True ($results.Count -eq 1 -and $results[0].Status -eq 'Complete') 'Full orchestration did not emit one completion result.'
        Assert-True ($results[0].GeoFileCount -eq 2) 'Full receipt GEO count differs.'
        Assert-True ($results[0].NcbiRecordCount -eq 12) 'Full receipt NCBI count differs.'
        Assert-True (Test-VerifiedFile -LiteralPath $results[0].ReceiptPath) 'Full acquisition receipt did not verify.'
        $receipt = Get-Content -LiteralPath $results[0].ReceiptPath -Raw | ConvertFrom-Json
        Assert-True ($receipt.test_transport_injected -eq $true) 'Injected transport was not disclosed in receipt.'
        Assert-True (@($receipt.sources.geo_processed_files).Count -eq 2) 'Serialized GEO receipt array differs.'
        Assert-True (@($receipt.sources.ncbi_fasta_records).Count -eq 12) 'Serialized NCBI receipt array differs.'
        foreach ($entry in @($receipt.sources.geo_processed_files) + @($receipt.sources.ncbi_fasta_records)) {
            Assert-True (Test-VerifiedFile -LiteralPath $entry.path) "Receipt payload failed hash check: $($entry.path)"
            Assert-True (Test-VerifiedFile -LiteralPath $entry.response_metadata_path) "Receipt response metadata failed hash check: $($entry.response_metadata_path)"
        }
    }

    Invoke-SmokeCase 'default dry-run performs no writes' {
        $dryRoot = Join-Path $testRoot 'dry-run-output'
        $null = & $acquirePath -Profile All -OutputRoot $dryRoot 6>&1
        Assert-True (-not (Test-Path -LiteralPath $dryRoot)) 'Dry-run created an output directory.'
    }

    Invoke-SmokeCase 'injected transport is rejected without the explicit test gate' {
        $guardRoot = Join-Path $testRoot 'unguarded-transport'
        $didThrow = $false
        try { $null = & $acquirePath -Profile All -OutputRoot $guardRoot -RequestInvoker { throw 'must not run' } 6>&1 }
        catch { $didThrow = $_.Exception.Message -match 'require -AllowTestTransport' }
        Assert-True $didThrow 'Unguarded injected transport was accepted.'
        Assert-True (-not (Test-Path -LiteralPath $guardRoot)) 'Transport guard created an output directory.'
    }

    Invoke-SmokeCase 'dry-run never invokes an explicitly gated request callback' {
        $dryRoot = Join-Path $testRoot 'gated-dry-run'
        $null = & $acquirePath -Profile All -OutputRoot $dryRoot -AllowTestTransport -RequestInvoker { throw 'Dry-run invoked HTTP callback.' } 6>&1
        Assert-True (-not (Test-Path -LiteralPath $dryRoot)) 'Gated dry-run created an output directory.'
    }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolved = [IO.Path]::GetFullPath($testRoot)
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove test path outside temp: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

Write-Host "Smoke tests: $passed passed, $failed failed"
if ($failed -gt 0) { exit 1 }
exit 0
