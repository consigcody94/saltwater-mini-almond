# Public biological-data acquisition

The audited acquisition manifest is [`public_bio_data_manifest.yaml`](public_bio_data_manifest.yaml),
with a human-readable [`public_bio_data_audit.md`](public_bio_data_audit.md).

The manifest verifies 23 public records: 19 machine-addressable resources and
four article/supplement-only packages. No multi-gigabyte read archive is stored
in this repository. Raw downloads belong under `data/raw/`, are immutable, and
must be accompanied by repository MD5 values where provided plus locally
calculated SHA-256 hashes.

The largest immediate acquisition is BioProject `PRJNA732909`: 24 paired-end
Rootpac 40/Nemaguard RNA-seq libraries. Canonical compressed FASTQ pairs total
43,527,962,230 bytes (40.539 GiB). The paper reports 233 Gb of clean sequence;
that is biological read yield, not download size. Acquisition remains gated
until the missing run-to-treatment key is independently recovered.

Public data can inform references, priors, and validation. It cannot establish
that any proposed construct works in almond or that almonds tolerate seawater.

## Acquisition workflow

The repository wrapper defaults to a no-write reference dry-run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/acquire_public_data.ps1
```

The wrapper exposes three profiles:

- `references` delegates to the four-accession NCBI reference workflow. With
  `-Execute`, it streams each package to `.partial`, validates the ZIP, and
  calculates SHA-256 before promotion. Existing files are skipped only after
  rehashing. The downloader pins the current NCBI Datasets v2 accession routes
  and supported `PROT_FASTA` enum and performs serial bounded retries.
- `phase2-small` delegates to Phase 2 `All` and defaults to
  `data/raw/phase2_small`. It admits only the official GSE254853 processed
  supplementary directory plus these exact EFetch accession versions:
  `AJ972674.1`, `CAI99405.1`, `EU879059.1`, `ACJ63441.1`,
  `AY282755.1`, `DQ146477.2`, `MT473962.1`,
  `XM_020565174.1`, `XP_020420763.1`, `XM_020564808.1`,
  `XP_020420397.1`, `XM_020568644.1`, `XP_020424233.1`,
  `XM_007201987.2`, and `XP_007202049.1`. GEO files must pass a positive
  processed-format allowlist; EFetch nucleotide/protein database mappings,
  redirect destinations, query semantics, response types, accession headers,
  byte counts, and local hashes are checked.
- `rootstock-rnaseq` remains informational and blocked. Even with `-Execute`,
  it fails closed because the verified PRJNA732909 run-to-treatment key is
  absent.

Phase 2 dry-run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/acquire_public_data.ps1 -Profile phase2-small
```

Phase 2 explicit acquisition command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/acquire_public_data.ps1 -Profile phase2-small -Execute
```

`-Execute` is the only switch that permits requests or output creation. The
completed live snapshot below was explicitly authorized and is disclosed in a
sanitized receipt.

The guarded workflow includes paper-reported `AY282755.1`, `DQ146477.2`, and
unversioned `MT473962`; NCBI independently verifies the first two accession
versions and resolves the last to `MT473962.1`. Those records are **not
construct-ready**: targeting, exact construct maps, and event mapping remain
unresolved. The paper calls the KaNa+/H+ cloned material a full-length coding
sequence, while the resolved NCBI record is a partial CDS; this explicit
identity/completeness conflict remains open. No Ectocarpus
identifier crosswalk or sequence claim is made. Phase 2 does not request SRA,
ENA, FASTQ, FQ, BAM, CRAM, or any other raw-read payload; the repository still
has no RNA-seq downloader.

The two `local_snapshot.sha256` files are mixed repository snapshots, not
whole-tree or single-commit manifests. The public-data sidecar hashes the
current reviewed manifest, audit, evidence seed, and this README; its five
unchanged acquisition implementation/documentation entries are byte-identical
to downloader integration commit `0c61054`. The independent
`scripts/public_data/phase2/local_snapshot.sha256` hashes the current reviewed
Phase 2 README; its three unchanged module, entry-point, and offline-test
entries are byte-identical to accession-extension commit `f739404`. Each
sidecar records per-file content hashes, not a single commit identity. The Git
commit references in this explanation describe independently verified file
history; they are not encoded by the SHA-256 sidecar lines. These are local
repository hashes, not publisher, NCBI, ENA, or other remote checksums.

## Completed Phase 2 small snapshot

An explicitly authorized live acquisition completed at
`2026-08-13T07:46:16.3675604+00:00` using downloader commit `f739404` and no
injected test transport. The sanitized tracked
[`phase2_acquisition_receipt.json`](phase2_acquisition_receipt.json) records:

- five GSE254853 processed supplementary gzip files totaling 17,602,426 bytes;
- fifteen exact NCBI EFetch FASTA records totaling 23,684 bytes; and
- source URLs, response Content-Length values, locally calculated SHA-256
  hashes, listing and parsed-listing hashes, exclusions, and the original raw
  receipt SHA-256.

The tracked receipt contains no absolute local paths. Before it was recorded,
all 20 payloads were independently rehashed against the live raw receipt and
their sidecars; request and response URL policy was rechecked; all GEO gzip
streams decompressed to nonempty content; and every NCBI FASTA contained exactly
one record with the requested accession-version header. This snapshot includes
no SRA/ENA raw reads and no Ectocarpus crosswalk claim. Inclusion of the three
recent rice-paper sequence records verifies repository identity only and makes
no construct-ready, efficacy, or winner claim.

## Completed reference snapshot

The four approved reference packages were acquired on 2026-08-12 after the
live NCBI Datasets v2 API contract was verified. The packages total
911,023,329 bytes (0.8485 GiB). All four passed ZIP integrity and local SHA-256
sidecar revalidation, and every included `dataset_catalog.json` was extracted
and hashed. Exact sizes, hashes, accession identities, request URLs, and the
downloader Git commit are frozen in `reference_acquisition_receipt.json`.

The package files remain ignored under `data/raw/ncbi_references/`; they are
local reproducibility inputs, not source-controlled artifacts. This completed
snapshot still contains no SRA, ENA, or FASTQ reads.
