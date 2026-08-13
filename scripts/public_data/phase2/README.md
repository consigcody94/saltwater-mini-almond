# Phase 2 small public-data acquisition

Repository-integrated implementation. Offline verification uses injected local
fixtures; an explicitly authorized live run is separately recorded in the
sanitized Phase 2 receipt. Every future live acquisition still requires
explicit `-Execute`.

## Scope

The workflow has two allowlisted profiles:

1. `GeoProcessed` fetches the official directory listing at
   `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE254nnn/GSE254853/suppl/`,
   preserves the listing and its response metadata, parses only safe
   `GSE254853_` supplementary filenames, and streams every approved listed
   processed file. Any prefixed filename with an unknown format fails closed
   for review. Exact integer byte sizes are preserved when the listing exposes
   them; HTTP `Content-Length` is preserved separately. The expected current
   payload is about 16.8 MB, but the live directory remains authoritative.
2. `NcbiRecords` fetches exactly fifteen accession-version FASTA records from
   official NCBI EFetch. Nucleotide records use `db=nuccore`; protein records
   use `db=protein`.

The default `All` profile performs both. Dry-run is the default and performs no
writes or requests. `-Execute` is mandatory for network access.

## Exact NCBI allowlist

| Module | Nucleotide | Protein |
|---|---|---|
| PyKPA1 | `AJ972674.1` | `CAI99405.1` |
| PyAPX | `AY282755.1` | not requested |
| PyMnSOD | `DQ146477.2` | not requested |
| Kappaphycus Na+/H+ antiporter | `MT473962.1` (partial CDS) | not requested |
| SbSOS1 | `EU879059.1` | `ACJ63441.1` |
| PpHKT1 isoform 1 | `XM_020565174.1` | `XP_020420763.1` |
| PpHKT1 isoform 2 | `XM_020564808.1` | `XP_020420397.1` |
| PpSOS2 isoform 1 | `XM_020568644.1` | `XP_020424233.1` |
| PpSOS2 isoform 2 | `XM_007201987.2` | `XP_007202049.1` |

The endpoint template is:

```text
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db={nuccore|protein}&id={accession.version}&rettype=fasta&retmode=text&tool=AlmondLabPhase2
```

The 2025 paper reports `AY282755.1`, `DQ146477.2`, and unversioned `MT473962`;
the guarded workflow independently verifies the first two repository records
and resolves the last to `MT473962.1`. They are **not construct-ready**: the
records do not independently validate targeting, exact construct maps, or
event-to-construct mappings. The paper calls the KaNa+/H+ cloned material a
full-length coding sequence, while the resolved repository record is a partial
CDS; this identity/completeness conflict remains open. No Ectocarpus crosswalk
is asserted. The code does not call SRA or ENA and does not scrape article
pages.

The GEO filename policy is a positive allowlist. It accepts uncompressed
`.csv`, `.tsv`, `.txt`, `.fasta`, `.fa`, `.gff`, `.gff3`, `.gtf`, `.xlsx`, and
`.xls`; a single `.gz` layer is allowed only for the listed text, tabular,
FASTA, GFF, and GTF formats. It rejects ZIP, 7z, TAR, XZ, BZ2, RAR, FASTQ, FQ,
SRA, BAM, CRAM, hidden leaves, traversal, percent-encoded names, duplicate
names, double gzip suffixes, and delimited `RAW` payloads. Gzip payloads must
have gzip magic and decompress to nonempty content. Unexpected prefixed files
cause a reviewable failure rather than a silent skip.

## Safety and audit behavior

- Sequential requests only; bounded retry/backoff for HTTP 429 and 5xx, with
  `Retry-After` honored. Clearly classified timeouts and transient socket/web
  transport failures receive the same bounded exponential retry. Validation
  failures, ordinary exceptions, and non-429 4xx responses are never retried.
- Redirects are checked before the response stream is opened. GEO listing and
  file responses must finish on HTTPS `ftp.ncbi.nlm.nih.gov` within the exact
  GSE254853 supplementary path, and a file path must end in its exact parsed
  filename. EFetch responses must finish on the exact HTTPS EFetch endpoint
  with exactly the allowlisted accession-version/database plus
  `rettype=fasta`, `retmode=text`, and `tool=AlmondLabPhase2`; host, path, query,
  or extra-field drift is rejected. This final-URL check runs on every response
  before any 429/5xx retry decision, so an off-policy redirect is not retried.
- Response media types are source- and format-checked. HTML is accepted only
  for the GEO listing, gzip types only for approved `.gz` files, spreadsheet
  types only for spreadsheet suffixes, compatible text/tabular types for plain
  processed files, and compatible FASTA/text types for EFetch.
- GEO caps: 50 files, 100 MB per file, 250 MB total, and a 5 MB listing.
- NCBI caps: 10 MB per record and 50 MB total.
- Streaming uses `.partial`; failed or oversized transfers are retained with
  that suffix and never treated as complete.
- GEO files must be nonempty, pass the format-specific payload check, and match
  exact listing bytes when available.
- FASTA responses must contain one record whose header contains the exact
  requested accession-version and a nonempty valid sequence.
- Every payload, URL record, response-metadata document, parsed listing, and
  final receipt receives a locally calculated SHA-256 sidecar. Response
  metadata records both the requested and final URL, status, content type,
  observed bytes, remote content length when supplied, and local payload hash.
- An idempotent skip occurs only after rehashing both payload and metadata and
  semantically rechecking the exact requested/final URL policy, successful
  status, compatible content type, observed byte count, optional remote content
  length, payload hash, size caps, and payload content. A merely rehashed but
  forged metadata document is rejected.
- No remote checksum is fabricated. A receipt field remains `null` unless an
  official remote checksum is explicitly acquired in a future reviewed change.

The output layout is deterministic beneath the selected root:

```text
geo/GSE254853/{listing,files,requests,metadata}/...
ncbi/records/<accession.version>/{request.url.txt,response.json,<accession>.fasta}
receipts/phase2_acquisition_receipt.json
```

## Commands

Dry-run only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Acquire-Phase2PublicData.ps1
```

Explicit network execution:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Acquire-Phase2PublicData.ps1 -Execute -Profile All -OutputRoot <approved-path>
```

Offline tests:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-Phase2PublicData.ps1
```

Tests use local fixtures and in-memory HTTP responses only.
The acquisition script accepts guarded callback parameters only when
`-AllowTestTransport` is supplied; the receipt records this condition. These
callbacks exist solely so the complete execute/receipt path can be tested
without network traffic and are not part of a real acquisition command.
