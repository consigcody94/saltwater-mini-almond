# Public biological-data acquisition

The audited acquisition manifest is [`public_bio_data_manifest.yaml`](public_bio_data_manifest.yaml),
with a human-readable [`public_bio_data_audit.md`](public_bio_data_audit.md).

The manifest verifies 20 public records: 16 machine-addressable resources and
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

Only `-Profile references -Execute` can perform downloads. It delegates to the
four-accession allowlisted workflow in `scripts/public_data/`, streams each NCBI
package to a `.partial` file, validates its format, and locally calculates
SHA-256 before promotion. Existing files are skipped only after rehashing.

The `rootstock-rnaseq` profile is informational and deliberately has no
downloader. Even with `-Execute`, it fails closed because the verified
PRJNA732909 run-to-treatment key is absent. No SRA/ENA FASTQ data are acquired
by repository code.

`local_snapshot.sha256` contains locally calculated hashes for the audited
manifest, audit, evidence seed, and acquisition code. These are repository
snapshot hashes, not publisher, NCBI, ENA, or other remote checksums.
