# Safe NCBI reference downloader

This workflow acquires exactly four allowlisted NCBI reference-assembly packages:

- `GCF_902201215.1` — almond Texas, ALMONDv2
- `GCA_008632915.2` — almond Lauranne
- `GCA_021292205.2` — almond Nonpareil, OSU_Pdul_2.5
- `GCF_000346465.2` — peach Lovell, Prunus_persica_NCBIv2

It never calls SRA or ENA and does not download FASTQ files. `RNA_FASTA` in the NCBI package means reference-annotation transcript sequences, not RNA-seq reads.

The request contract is pinned to NCBI Datasets v2 `GET
/datasets/v2/genome/accession/{accession}/download`, with the supported enums
`GENOME_FASTA`, `GENOME_GFF`, `GENOME_GTF`, `GENOME_GBFF`, `RNA_FASTA`,
`CDS_FASTA`, `PROT_FASTA`, and `SEQUENCE_REPORT`. The retired `v2alpha` route
and rejected `PROTEIN_FASTA` enum are guarded by offline tests.

## Use

Dry-run is the default and writes nothing:

```powershell
.\scripts\public_data\Acquire-NcbiReferences.ps1
```

Choose a destination while still dry-running:

```powershell
.\scripts\public_data\Acquire-NcbiReferences.ps1 -OutputRoot D:\AlmondLab\references
```

Perform the downloads only with the explicit switch:

```powershell
.\scripts\public_data\Acquire-NcbiReferences.ps1 -Execute -OutputRoot D:\AlmondLab\references
```

The service does not expose complete package sizes for all four assemblies. The script prints the only verified size component—72.7 MB for the compressed Nonpareil genomic FASTA—as a lower bound and clearly marks total disk demand unknown.

## Output layout

Each accession receives a deterministic directory:

```text
<output-root>/
  GCF_902201215.1/
    requests/
      package.url.txt
      package.url.txt.sha256
      dataset_report.url.txt
      dataset_report.url.txt.sha256
    metadata/
      dataset_report.json
      dataset_report.json.sha256
      dataset_catalog.json
      dataset_catalog.json.sha256
    package/
      ncbi_dataset.zip
      ncbi_dataset.zip.sha256
```

The catalog is extracted only if NCBI includes `dataset_catalog.json`. If absent, the script warns and does not invent one.

Downloads stream to `<final-name>.partial`. Only a completed, format-validated file is promoted to its final name and assigned a locally computed SHA-256 sidecar. Existing final files are skipped only after the sidecar hash is recomputed and matches. A failed transfer leaves `.partial`, which is never considered complete.

Each successful or verified-skip call emits exactly one structured result with
`Status`, `Path`, `Sha256`, and `Bytes`. Internal .NET response objects are
suppressed so the result can be used directly to decide whether the package
catalog needs forced re-extraction.

Requests are serial. HTTP 429 and 5xx responses receive at most four attempts
with bounded exponential backoff; a valid `Retry-After` delay is honored up to
the configured 120-second safety cap. There is no parallel NCBI request fanout.
Available disk space is reported from `.NET DriveInfo`; total package demand
remains unknown because NCBI does not expose complete sizes for every package.

## Tests

No Pester installation is required. Tests use local temporary fixtures and
in-memory HTTP responses; they exercise the real streaming, validation,
promotion, hashing, result, and catalog-extraction paths without contacting
NCBI:

```powershell
.\scripts\public_data\Test-PublicDataDownloader.ps1
```

If the local execution policy blocks scripts, use the process-scoped invocation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\public_data\Test-PublicDataDownloader.ps1
```
