[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$modulePath = Join-Path $PSScriptRoot 'PublicDataDownloader.psm1'
$acquirePath = Join-Path $PSScriptRoot 'Acquire-NcbiReferences.ps1'
$wrapperPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'acquire_public_data.ps1'
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

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('almondlab-downloader-smoke-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $testRoot

try {
    Invoke-SmokeCase 'plan is exactly the four approved reference accessions' {
        $plan = @(Get-ReferenceAssemblyPlan)
        $expected = @('GCF_902201215.1', 'GCA_008632915.2', 'GCA_021292205.2', 'GCF_000346465.2')
        Assert-True ($plan.Count -eq 4) "Expected 4 entries, found $($plan.Count)."
        Assert-True ((@($plan.Accession | Sort-Object) -join ',') -eq (@($expected | Sort-Object) -join ',')) 'Accession allowlist differs.'
        foreach ($item in $plan) {
            Assert-True ($item.PackageUrl -match '^https://api\.ncbi\.nlm\.nih\.gov/datasets/') 'Non-NCBI URL in plan.'
            Assert-True ($item.PackageUrl -notmatch '(?i)fastq|sra|ena') 'Read-archive token found in package URL.'
        }
    }

    Invoke-SmokeCase 'dry-run creates no output directory' {
        $dryRoot = Join-Path $testRoot 'dry-run-output'
        $null = & $acquirePath -OutputRoot $dryRoot 6>&1
        Assert-True (-not (Test-Path -LiteralPath $dryRoot)) 'Dry-run created its output root.'
    }

    Invoke-SmokeCase 'default dry-run path resolves under the script directory' {
        $repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $defaultRoot = Join-Path $repositoryRoot 'data\raw\ncbi_references'
        $existedBefore = Test-Path -LiteralPath $defaultRoot
        $null = & $acquirePath 6>&1
        if (-not $existedBefore) {
            Assert-True (-not (Test-Path -LiteralPath $defaultRoot)) 'Default dry-run created the data directory.'
        }
    }

    Invoke-SmokeCase 'RNA-seq execute profile is blocked before any output write' {
        $blockedRoot = Join-Path $testRoot 'blocked-rnaseq'
        $didThrow = $false
        try {
            $null = & $wrapperPath -Profile rootstock-rnaseq -Execute -AcknowledgeMissingRunTreatmentKey -OutputRoot $blockedRoot 6>&1
        }
        catch {
            $didThrow = $true
            Assert-True ($_.Exception.Message -match 'does not implement FASTQ') 'Unexpected RNA-seq guard error.'
        }
        Assert-True $didThrow 'RNA-seq execute profile did not throw.'
        Assert-True (-not (Test-Path -LiteralPath $blockedRoot)) 'RNA-seq guard created an output directory.'
    }

    Invoke-SmokeCase 'hash sidecar must revalidate before skip' {
        $file = Join-Path $testRoot 'hash-test.bin'
        [IO.File]::WriteAllBytes($file, [byte[]](0, 1, 2, 3, 254, 255))
        $hash = Get-FileSha256 -LiteralPath $file
        $null = Write-ChecksumSidecar -LiteralPath $file -Hash $hash
        Assert-True (Test-VerifiedFile -LiteralPath $file) 'Fresh file did not verify.'
        [IO.File]::WriteAllBytes($file, [byte[]](9, 8, 7))
        Assert-True (-not (Test-VerifiedFile -LiteralPath $file)) 'Mutated file incorrectly verified.'
    }

    Invoke-SmokeCase 'text artifacts are idempotent only after content and hash check' {
        $file = Join-Path $testRoot 'request.url.txt'
        $first = Write-TextArtifact -LiteralPath $file -Content "https://example.invalid/request`r`n"
        $second = Write-TextArtifact -LiteralPath $file -Content "https://example.invalid/request`r`n"
        Assert-True ($first.Status -eq 'Written') 'First text write was not Written.'
        Assert-True ($second.Status -eq 'SkippedVerified') 'Verified identical text was not skipped.'
        Add-Content -LiteralPath $file -Value 'tamper'
        $third = Write-TextArtifact -LiteralPath $file -Content "https://example.invalid/request`r`n"
        Assert-True ($third.Status -eq 'Written') 'Tampered text was not rewritten.'
        Assert-True (Test-VerifiedFile -LiteralPath $file) 'Rewritten text did not verify.'
    }

    Invoke-SmokeCase 'catalog extraction requires a verified package and hashes output' {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $package = Join-Path $testRoot 'fixture.zip'
        $sourceDir = Join-Path $testRoot 'zip-source'
        $catalogDir = Join-Path $sourceDir 'ncbi_dataset\data'
        $null = New-Item -ItemType Directory -Path $catalogDir -Force
        [IO.File]::WriteAllText((Join-Path $catalogDir 'dataset_catalog.json'), '{"assemblies":["fixture"]}', (New-Object Text.UTF8Encoding($false)))
        [IO.Compression.ZipFile]::CreateFromDirectory($sourceDir, $package)
        $packageHash = Get-FileSha256 -LiteralPath $package
        $null = Write-ChecksumSidecar -LiteralPath $package -Hash $packageHash
        $destination = Join-Path $testRoot 'metadata\dataset_catalog.json'
        $result = Export-DatasetCatalog -PackagePath $package -DestinationPath $destination
        Assert-True ($result.Status -eq 'Extracted') 'Catalog was not extracted.'
        Assert-True (Test-VerifiedFile -LiteralPath $destination) 'Catalog output did not verify.'
        Assert-True (Test-JsonDocument -LiteralPath $destination) 'Catalog output is invalid JSON.'
    }

    Invoke-SmokeCase '.partial files are never accepted as complete' {
        $final = Join-Path $testRoot 'package.zip'
        [IO.File]::WriteAllBytes("$final.partial", [byte[]](1, 2, 3, 4))
        Assert-True (-not (Test-VerifiedFile -LiteralPath $final)) 'Partial was mistaken for final.'
        Assert-True (-not (Test-Path -LiteralPath $final)) 'Final file unexpectedly exists.'
    }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolved = [IO.Path]::GetFullPath($testRoot)
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove smoke-test path outside temp: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

Write-Host "Smoke tests: $passed passed, $failed failed"
if ($failed -gt 0) { exit 1 }
exit 0
