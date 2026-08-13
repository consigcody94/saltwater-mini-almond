# AlmondLab public biological data audit

Verified: 2026-08-12

## Outcome

Public data can support a serious *in silico* AlmondLab program, but it cannot currently validate the claim that an almond tree can thrive on seawater. The audit verified 16 machine-addressable reference, sequence, expression, or water/model resources and four additional article/supplement-only evidence packages. One externally cited repository record is deleted.

The largest immediately relevant dataset is [BioProject PRJNA732909](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA732909): 24 paired-end RNA-seq runs from Rootpac40 and Nemaguard roots/leaves. The primary paper reports **233 Gb of clean reads across the 24 libraries**; that is biological sequence yield, not download size. ENA exposes file-level MD5 values and 43,527,962,230 bytes (40.539 GiB) for the canonical compressed `_1`/`_2` FASTQ pairs. The same ENA response also offers unsuffixed generated FASTQs; those are alternate representations and must not be downloaded or counted as additional samples.

Across resources with exposed, nonduplicated sizes, the known lower bound is about **40.62 GiB**. This includes the canonical PRJNA732909 pairs, the 72.7 MB Nonpareil genome FASTA, and approximately 16.8 MB of processed GEO files. Most NCBI assembly packages, article supplements, and dynamic water queries do not expose stable totals, so this is not an estimate of the complete acquisition.

The machine-oriented record is in `public_bio_data_manifest.yaml`. It deliberately distinguishes raw repositories, reference sequences, processed supplements, dynamic public services, and article-only evidence.

## What is strong enough to use now

### Almond and peach references

- **Texas almond ALMONDv2**: NCBI RefSeq `GCF_902201215.1`, paired with GenBank `GCA_902201215.1`; chromosome-level, 227,599,157 bp, RefSeq annotation release 100. RefSeq added plastid `NC_034696.1`, so RefSeq and the submitter GenBank assembly are not byte-identical.
- **Nonpareil almond OSU_Pdul_2.5**: GenBank `GCA_021292205.2`, WGS `JAJFAZ02`; chromosome-level, 257,071,663 bp. Version `.1` is superseded. The WGS page exposes a 72.7 MB compressed genomic FASTA.
- **Lauranne almond**: GenBank `GCA_008632915.2`; scaffold-level, 246,116,696 bp. It is useful as an independent almond haplotype but is considerably more fragmented and has submitter rather than RefSeq annotation.
- **Lovell peach**: RefSeq `GCF_000346465.2`; the coordinate/protein reference for the verified Prupe candidates.

These should be acquired first as small NCBI data packages with genome, annotation, CDS, protein, and sequence-report files. Preserve the package catalog/MD5 records and calculate SHA-256 locally.

### Rootstock salinity RNA-seq

The 24 runs in `PRJNA732909` match the published factorial design of two genotypes × two tissues × two treatments × three biological replicates. However, the verified ENA run/sample metadata do **not** assign control versus salt treatment to each run. The paper describes control Riverside city water at EC 1.36 dS/m and Na/Cl-dominant saline water at EC 3.0 dS/m, sampled after 48 hours. A publisher or author sample key must be recovered and independently checked before differential expression.

There is also a taxonomy caveat: the repository calls all samples *Prunus persica*. Rootpac40 is commercially described as a peach × almond hybrid, but deposited taxonomy must be retained as-is and supplemented with a separate curated chassis field.

### Phenotype and ion-calibration evidence

The [14-rootstock Scientific Reports study](https://pmc.ncbi.nlm.nih.gov/articles/PMC7712888/) is the best public multi-genotype calibration source. It tested 630 trees in a 14-genotype × five-treatment × three-block × three-plant design. Its exact Na, Cl, sulfate, Ca, Mg, K, phosphate, and nitrate recipes are encoded in the manifest. The phenotype, ion, physiological, and targeted-expression evidence is available only through the article and supplementary PDF—not as raw instrument files or a machine-readable phenotype repository.

The [root developmental-gradient Frontiers study](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2020.595055/full) provides useful mechanistic evidence for Empyrean-1, Controller-5, and Krymsk-86 at 0, 50, and 150 mM NaCl. It supports hypotheses about sodium distribution, root barriers, and HKT/SOS/NHX responses. Its data-availability statement points only to the article/supplement; no raw repository accession was verified.

Neither study is a seawater trial. Full-strength seawater is a high-ionic-strength, multi-ion solution and is far more saline than EC 3 dS/m irrigation. Their results can calibrate low-to-moderate stress behavior, not justify extrapolation to seawater survival or yield.

## Candidate-sequence audit

| Candidate | Verified public identity | Readiness | Main warning |
|---|---|---|---|
| PpHKT1 | `Prupe.1G067100`; NCBI Gene `18791946`; `XM_020565174.1`/`XP_020420763.1` and `XM_020564808.1`/`XP_020420397.1` | Reference models available | The functional paper used Nemaguard material, but no exact experimental clone/promoter accession was verified; two Lovell RefSeq isoforms differ in length. |
| PpSOS2/PpCIPK24 | `Prupe.7G244500.1`; NCBI Gene `18770930`; `XM_020568644.1`/`XP_020424233.1` and `XM_007201987.2`/`XP_007202049.1` | Reference models available | The same locus is called PprCIPK17 in a 2022 family study and PpCIPK24/PpSOS2 in the 2024 functional study. Anchor identity to accession.version. |
| PyKPA1 | `AJ972674.1`; protein `CAI99405.1` | Sequence-ready for computational evaluation | Current taxonomy is *Pyropia yezoensis*; older literature may use *Porphyra yezoensis*. Heterologous rice evidence does not establish almond function. |
| SbSOS1 | `EU879059.1`; protein `ACJ63441.1` | Sequence-ready for computational evaluation | Large membrane protein; target-chassis localization and energetic burden remain unknown. |
| PyAPX | No verified accession in the 2026 rice paper | **Not construct-ready** | The article says its datasets are in the paper/additional files; no exact donor sequence or raw RNA-seq accession was verified. |
| Ectocarpus mannitol candidates | Reference `GCA_000310025.1`; legacy Esi identifiers and EST range `FP245546–FP312611` | Crosswalk required | `Esi0020_0181` is a second M1PDH-like model; it is not `Esi0100_0020`, the later M1Pase2 candidate. Sequence-map all Esi IDs before scoring. |

The primary safety rule for the virtual screen is simple: no candidate enters sequence-level design unless its exact accession-version or a newly verified experimental sequence is frozen and hashed.

## Transformation-data failure

The 2024 [almond hairy-root CRISPR paper](https://link.springer.com/article/10.1007/s11240-024-02935-x) is a useful feasibility study in cv. Vairo, reporting a 41 ± 7% transformation rate and six screened composite plants. Its Springer supplement is public. However, the paper cites Zenodo DOI `10.5281/zenodo.10945763` for sequences/chromatograms, and the official Zenodo API returned **HTTP 410 Gone** on 2026-08-12. The underlying record is deleted and must be treated as unavailable, not merely hard to find.

This blocks full independent verification of the reported edit calls. A publication-ready project should request the deleted files from the authors and archive any response in a durable repository with checksums.

## California water and seawater chemistry

Three official observation services are acquisition-ready:

- [California DWR/CNRA Water Quality Data](https://data.cnra.ca.gov/dataset/water-quality-data), including the discrete-grab station service. This is the best California-specific starting point for irrigation-source chemistry.
- [GeoTracker GAMA groundwater results](https://data.ca.gov/dataset/ground-water-water-quality-results), which aggregates state, federal, and local groundwater programs.
- [USGS/EPA Water Quality Portal](https://www.waterqualitydata.us/), using **WQX3**, not legacy WQX 2.2. Separate, spatially/date-bounded queries should be run for conductivity, Na, Cl, sulfate, Ca, Mg, K, boron, alkalinity, pH, and TDS.

These are dynamic services: extraction URL, timestamp, provider identifiers, units, methods, detection limits, and the SHA-256 of each response must be stored. Results need deduplication and unit/fraction harmonization before modeling.

For full-strength or concentrated saline recipes, use the official [USGS PHREEQC](https://www.usgs.gov/software/phreeqc-version-3) Pitzer database. It provides high-ionic-strength activity modeling, precipitation risk, and osmotic/speciation calculations. It is thermodynamic reference data, not biological evidence, and the exact PHREEQC release plus `pitzer.dat` hash must be pinned.

## Critical gaps before a publishable claim

1. **No direct seawater-almond outcome data.** No verified public dataset demonstrates almond survival, growth, flowering, yield, kernel quality, or rootstock/scion compatibility under undiluted seawater.
2. **No per-run condition key for `PRJNA732909`.** This blocks defensible differential-expression analysis until resolved.
3. **Missing experimental sequences.** PyAPX and the Nemaguard PpHKT1 clone are not publicly accessioned in a verified sequence repository.
4. **Deleted editing evidence.** The hairy-root paper's Zenodo record is gone.
5. **Sparse raw phenotypes.** Major almond salinity studies expose article tables, not raw machine-readable observations or instrument files.
6. **No engineered-almond validation.** Cross-species donor evidence cannot establish expression, localization, pleiotropy, food safety, pollen containment, or perennial performance in almond.
7. **No greenhouse mass-balance dataset.** A contained system still needs empirical Na/Cl accumulation, evapoconcentration, membrane/brine recovery, leachate volume, substrate exchange, and disposal measurements.

## Safe acquisition sequence

1. Download and hash the small almond/peach reference packages and candidate sequence records.
2. Download article OA/supplement packages and extract phenotype/ion tables using scripted schemas plus independent value checking.
3. Snapshot bounded California water queries and normalize units/methods.
4. Obtain the missing `PRJNA732909` run-condition key.
5. Only then stage the 40.539 GiB canonical paired FASTQs and verify every ENA MD5.

No multi-GB raw reads were downloaded during this audit.
