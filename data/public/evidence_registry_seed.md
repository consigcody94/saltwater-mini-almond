# Saltwater Mini-Almond — evidence-registry seed

**Registry status:** curated seed, not a completed systematic review  
**Prepared:** 2026-08-13  
**Scope:** the six primary Paper 1 candidate modules, plus the highest-leverage almond/rootstock, containment, and desalination sources.  
**Evidence-tier convention:** E1 = native *Prunus* gene with stable functional complementation; E2 = stable heterologous land-plant phenotype plus functional evidence; E3 = stable phenotype with incomplete identity/mechanism/localization; E4 = association/expression/anatomy only; E5 = algal/microbial evidence only. Context, policy, and method records are marked `N/A — non-candidate`, never forced into a biological tier.

## Data-quality rules applied

- `NR` means the source did not state the value in the accessible primary text, or it could not be transcribed without guessing. It is not zero.
- “Salt treatment” is retained as the actual ions and concentrations used. EC is never converted to a salt concentration.
- `sequence_status` is intentionally conservative. An identifier in a paper does not by itself verify the construct sequence, allelic origin, coding sequence, or target-site preservation.
- Correction/retraction status is a publisher/DOI-page check on 2026-08-12, not a claim that no database anywhere could later report an issue.

## Candidate-support records

### EV-C1-PYKPA1-2013

- **Candidate / tier:** C1 `PyKPA1`; **E2**.
- **Exact title:** *Functional expression of an animal type-Na+\u2011ATPase gene from a marine red seaweed Porphyra yezoensis increases salinity tolerance in rice plants*.
- **Primary source:** Kishimoto M, Shimajiri Y, Oshima A, Hase A, Mikami K, Akama K. *Plant Biotechnology* 30 (2013), 417–422. DOI: [10.5511/plantbiotechnology.13.0517a](https://doi.org/10.5511/plantbiotechnology.13.0517a); publisher full text: [J-STAGE](https://www.jstage.jst.go.jp/article/plantbiotechnology/30/4/30_13.0517a/_article).
- **Donor organism:** *Porphyra yezoensis* (current name *Neopyropia yezoensis*); donor lifecycle stage in the cited characterization: sporophyte-preferential expression is reported in antecedent work.
- **Chassis / life stage:** stable nuclear transformants of *Oryza sativa* cv. Nipponbare, T2, third-leaf stage; two lines (#28 and #115).
- **Salinity chemistry / duration:** MS medium + 50 mM NaCl, 12 days; no seawater, chloride, boron, calcium, or magnesium chemistry was tested.
- **Sample size:** n=12 for fresh-weight comparison, as reported for the salinity assay.
- **Endpoint:** total and root fresh biomass; transgene transcript; transient PyKPA1::GFP localization in onion epidermis; plasma-membrane ATPase activity.
- **Effect as reported:** under 50 mM NaCl, the null transformant lost about 20% total biomass, while lines #28 and #115 showed about +8% and −10%, respectively, neither reported as significantly changed from their unsalted condition. The authors also reported vanadate-sensitive Na+-ATPase activity in the transformed-rice membrane fraction.
- **Accession IDs:** GenBank nucleotide `AJ972674.1`; protein `CAI99405.1`; rice actin control `AK100267` is not candidate sequence evidence.
- **Sequence status:** `accession_verified; source allele, targeting/topology, transport coupling, and final construct remain unverified`.
- **Key limitation:** two rice events and an acute, single-salt tissue-culture assay; the “animal-type Na+/K+-ATPase” functional annotation is inference rather than a direct transport-stoichiometry measurement in almond roots. The study does not measure effluent fate, xylem Na, Cl, B, or a woody rootstock outcome.
- **Metadata / correction check:** publisher metadata matches DOI, volume, pages, and authors. No correction or retraction notice was located on the publisher record on 2026-08-12. **Conflict flag:** title says “Na+-ATPase,” while the text describes KPA as a putative animal-type Na+/K+-ATPase; retain the uncertainty in all construct claims.
- **Access date:** 2026-08-12.

### EV-C2-PYAPX-2026

- **Candidate / tier:** C2 `PyAPX`; **E2 only provisionally for phenotype**. The accession record is verified, but the candidate is not construct-ready.
- **Exact title:** *Physiological, biochemical, and transcriptomic analyses revealed enhanced salt tolerance in rice via heterologous expression of Pyropia yezoensis APX gene*.
- **Primary source:** Lu X, Gillani SW, Meng C, Li Y, Wang K, Xu Z. *Plant Physiology and Biochemistry* 230 (2026), 110839. DOI: [10.1016/j.plaphy.2025.110839](https://doi.org/10.1016/j.plaphy.2025.110839); indexed record: [PubMed PMID 41353893](https://pubmed.ncbi.nlm.nih.gov/41353893/).
- **Donor organism:** *Pyropia yezoensis* (red alga), with a *P. yezoensis* PyMnSOD comparator and a *Kappaphycus alvarezii* `KaNa+/H+` comparator; donor life stages were not material to the rice assay extraction.
- **Chassis / life stage:** stable transgenic rice cultivar ZH11; the full text reports 12 PyAPX, 11 PyMnSOD, and 9 `KaNa+/H+` homozygous T1 lines.
- **Salinity chemistry / duration:** 250 mM NaCl applied every 3 days; germination was read on day 10. This is a single-salt challenge, not a complete multi-ion seawater recipe.
- **Sample size:** 12/11/9 homozygous T1 lines for PyAPX/PyMnSOD/`KaNa+/H+`; the germination assay used 30 seeds per dish and three replicate dishes.
- **Endpoint:** germination, growth, ROS/oxidative-damage and ion-homeostasis measures, transcriptomics/WGCNA.
- **Effect as reported:** the authors report stronger salt-stress phenotypes for PyAPX-overexpressing rice than for the PyMnSOD and `KaNa+/H+` comparators, including germination, growth, oxidative-damage/ROS, and ion-homeostasis readouts. This is a source-reported rice comparison, not almond efficacy or a program winner claim.
- **Accession IDs:** the paper reports PyAPX `AY282755.1`, PyMnSOD `DQ146477.2`, and `KaNa+/H+` `MT473962.1`. Guarded NCBI EFetch independently retrieved `AY282755.1` (complete CDS), `DQ146477.2` (complete CDS), and `MT473962.1` (partial CDS), with locally calculated SHA-256 hashes in the Phase 2 acquisition receipt.
- **Sequence status:** `accession_verified_construct_map_unresolved`; these repository identities are **not construct-ready**.
- **Key limitation:** the paper-reported accessions and independently verified records do not establish the exact targeting sequences, construct maps, or event-to-construct mappings. `MT473962.1` is partial. The study also lacks complete multi-ion chemistry and almond Na/Cl/B fate evidence; antioxidant improvement cannot substitute for those outcomes.
- **Metadata / correction check:** DOI, title, authors, journal, volume and article number agree between publisher indexing and PubMed. Full-text design fields were independently reviewed on 2026-08-13. No correction or retraction notice was located on the DOI/index record. **Conflict flag:** publication carries a 2025 DOI and 2026 issue date; cite the version-of-record date/journal year, not a guessed online-publication year.
- **Access date:** 2026-08-13.

### EV-C3-ESMANNITOL-2020

- **Candidate / tier:** C3 `EsM1PDH1` + `EsM1Pase2`; **E2**.
- **Exact title:** *Low Mannitol Concentrations in Arabidopsis thaliana Expressing Ectocarpus Genes Improve Salt Tolerance*.
- **Primary source:** Ghasemi S, et al. *Plants* 9 (2020), 1508. DOI: [10.3390/plants9111508](https://doi.org/10.3390/plants9111508); full text: [PMC7695032](https://pmc.ncbi.nlm.nih.gov/articles/PMC7695032/).
- **Donor organism:** *Ectocarpus* sp. Ec32 (brown alga); source life stage not applicable to the recipient-plant assay.
- **Chassis / life stage:** three independent fifth-generation stable *Arabidopsis thaliana* Col-0 double-transgenic lines (`EsM1`, `EsM2`, `EsM3`), seedlings/plants as specified per assay.
- **Salinity chemistry / duration:** NaCl-based plate/plant assays are used; exact concentration and duration are assay-specific in the article and must be copied into a machine-readable extraction before using as a numerical prior. This seed deliberately does not collapse them to a single “salinity” value.
- **Sample size:** three independent stable lines; per-endpoint biological n must be transcribed from the figure legends/methods before quantitative reuse.
- **Endpoint:** transgene expression, LC–MS mannitol, salt and heat phenotypes, and transcriptomics (SRA `PRJNA674912`, submission `SUB8462528`).
- **Effect as reported:** the double-transgenic lines produced low but detectable mannitol (reported elsewhere in the article as low concentrations) and showed improved salinity and temperature tolerance versus wild type; the transcriptome response included stress, ABA, ROS, photosynthesis and K+-homeostasis pathways.
- **Accession IDs:** `Esi0017_0062` / `EsM1PDH1`; `Esi0100_0020` / `EsM1Pase2`.
- **Sequence status:** `locus_identifiers_supported; retrieve deposited coding sequences and confirm current Ectocarpus annotation before construct design`.
- **Key limitation:** constitutive double-gene expression in Arabidopsis does not isolate each enzyme, establish carbon-cost safety in woody roots, or prove enough mannitol for osmotic protection. **Metadata flag:** the paper text contains the spelling `EsM1PHD1` in places; canonical candidate symbol is `EsM1PDH1`.
- **Correction/retraction check:** no notice located on the publisher/PMC record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-C4-SBSOS1-2012

- **Candidate / tier:** C4 `SbSOS1`; **E2, conditional on non-xylem-loading localization**.
- **Exact title:** *The SbSOS1 gene from the extreme halophyte Salicornia brachiata enhances Na+ loading in xylem and confers salt tolerance in transgenic tobacco*.
- **Primary source:** Yadav NS, Shukla PS, Jha A, Agarwal PK, Jha B. *BMC Plant Biology* 12 (2012), 188. DOI: [10.1186/1471-2229-12-188](https://doi.org/10.1186/1471-2229-12-188); full text: [PMC3548769](https://pmc.ncbi.nlm.nih.gov/articles/PMC3548769/).
- **Donor organism:** extreme halophyte *Salicornia brachiata* Roxb.; one-month seedlings were also assayed for donor expression after hydroponic salt exposure.
- **Chassis / life stage:** stable T0/T1 *Nicotiana tabacum* transformants, 35S-driven construct; 70 individual events screened by GUS, with selected lines evaluated.
- **Salinity chemistry / duration:** donor plants: 0.10–2.0 M NaCl for 48 h. Tobacco: germination on 0–300 mM NaCl, scored at 15 d; T1 seedlings transferred at 8 d to 0/100/200 mM NaCl and measured after 30 d; hydroponic plants received 0/100/200 mM NaCl with tissues collected 45 d after treatment; ROS arm used 0/100/200/300 mM and 60 d. No seawater mult-ion chemistry.
- **Sample size:** 70 independent T0 events were initially screened; selected-line endpoint n varies by assay and should be transcribed from each figure before numerical meta-analysis.
- **Endpoint:** germination, root/shoot growth, biomass, RWC, chlorophyll, Na/K/Ca, xylem-sap Na, ROS/MDA, electrolyte leakage, osmolytes, and donor expression.
- **Effect as reported:** selected transgenics had higher salt-stress growth and K/Na ratio and lower root/leaf Na, ROS and electrolyte leakage than wild type. Crucially, they had **higher stem and xylem-sap Na**, consistent with enhanced xylem loading.
- **Accession IDs:** GenBank nucleotide `EU879059.1`; protein `ACJ63441.1`; 3,774-bp cDNA / 3,480-bp ORF / 1,159-aa protein reported in the primary paper.
- **Sequence status:** `accession_verified; independently validate the target-chassis topology/localization and resequence the final construct`.
- **Key limitation:** the claimed tolerance includes a mechanism that can raise xylem/scion Na—directly hazardous for a rootstock-first almond strategy. This is why C4 cannot progress without cortex-facing/exodermal expression, xylem-sap and whole-system ion-balance gates.
- **Correction/retraction check:** no notice located on the BMC/PMC record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-C5-PPHKT1-2019

- **Candidate / tier:** C5 `PpHKT1`; **E1**.
- **Exact title:** *Expression of the high-affinity K+ transporter 1 (PpHKT1) gene from almond rootstock ‘Nemaguard’ improved salt tolerance of transgenic Arabidopsis*.
- **Primary source:** Kaundal A, Sandhu D, Duenas M, Ferreira JFS. *PLOS ONE* 14 (2019), e0214473. DOI: [10.1371/journal.pone.0214473](https://doi.org/10.1371/journal.pone.0214473); full text: [PMC6435114](https://pmc.ncbi.nlm.nih.gov/articles/PMC6435114/).
- **Donor organism:** *Prunus persica* rootstock ‘Nemaguard’ (often described in almond-production context, but taxonomically peach, not *P. dulcis*).
- **Chassis / life stage:** stable *Arabidopsis thaliana* `athkt1` mutant complementation and overexpression lines; one-week-old seedlings.
- **Salinity chemistry / duration:** 1/8 MS with or without 90 mM NaCl; detailed exposure duration and per-assay n must be transcribed from the paper before numeric reuse.
- **Sample size:** independent stable lines are reported; exact biological n is assay-specific and not copied here without figure-level extraction.
- **Endpoint:** germination, survival, root architecture, biomass, Na/K, gene expression and complementation.
- **Effect as reported:** PpHKT1 expression improved salt response in the `athkt1` background; the study reports restored salt tolerance and differences in root/shoot ion outcomes, supporting a functional HKT1-like role.
- **Accession IDs:** peach reference locus `Prupe.1G067100` used to amplify the gene; no claim is made here that this reference identifier sequence-verifies a particular Nemaguard allele.
- **Sequence status:** `reference_locus_supported; Nemaguard donor amplicon/haplotype and final construct sequence require verification`.
- **Key limitation:** Arabidopsis mutant complementation is valuable functional evidence but does not establish woody-root xylem retrieval, root-stele injury limits, or almond scion/kernal salt protection.
- **Correction/retraction check:** no notice located on PLOS/PMC record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-C6-PPSOS2-2022

- **Candidate / tier:** C6 `PpSOS2` / `PpCIPK24`; **E1**.
- **Exact title:** *Transgenic Expression of Prunus persica Salt Overly Sensitive 2 (PpSOS2) in the atsos2 Mutant Imparts Salt Tolerance in Arabidopsis*.
- **Primary source:** Kaundal A, Sandhu D, Singh V, Duenas M, Acharya BR, Nelson B, Ferreira JFS, Litt A. *ACS Agricultural Science & Technology* 2 (2022), 153–164. DOI: [10.1021/acsagscitech.1c00276](https://doi.org/10.1021/acsagscitech.1c00276); official USDA copy: [P2719.pdf](https://www.ars.usda.gov/arsuserfiles/20361500/pdf_pubs/P2719.pdf).
- **Donor organism:** *Prunus persica* rootstock ‘Nemaguard’.
- **Chassis / life stage:** stable `atsos2` *Arabidopsis thaliana* complementation lines, including constitutive `PpSOS2.OE3.5` and native-promoter `PpSOS2NP.2.7` lines.
- **Salinity chemistry / duration:** 90 mM NaCl for germination/survival/dry-weight assays; 50 mM NaCl for root-growth and electrolyte-leakage assays; a 24-h 50 mM sampling time is reported for K+-channel/ROS-related expression.
- **Sample size:** two named transgenic lines; per-endpoint biological n requires figure-level extraction before numerical reuse.
- **Endpoint:** germination, survival, dry weight, primary/lateral root growth, electrolyte leakage, transgene expression and K+-channel/ROS-response expression.
- **Effect as reported:** both lines had better germination, survival and dry weight than `atsos2` at 90 mM NaCl; 50 mM root inhibition was restored and electrolyte leakage was lower. The paper supports functional SOS2 complementation, not a complete almond SOS-module deployment.
- **Accession IDs:** peach reference locus `Prupe.7G244500.1`; P. persica protein `XP_020424233.1` is reported in supporting material.
- **Sequence status:** `reference_gene_and_protein_supported; verify Nemaguard allele, PpSOS2/PpCIPK24 synonymy, CBL partner compatibility, and final construct sequence`.
- **Key limitation:** SOS2 is a kinase with broad network effects; the study does not establish compatible PpCBL4/PpCBL10 and PpSOS1 activation in almond, nor ion destination/food-safety outcomes.
- **Correction/retraction check:** no notice located on ACS/USDA record on 2026-08-12.
- **Access date:** 2026-08-12.

## Almond, rootstock, and implementation-context records

### EV-ALMOND-ROOTSTOCK-2020

- **Candidate / tier:** rootstock comparative anchor; `N/A — non-candidate` (supports E4-level associations only for individual loci).
- **Exact title:** *Linking diverse salinity responses of 14 almond rootstocks with physiological, biochemical, and genetic determinants*.
- **Primary source:** Sandhu D, Kaundal A, Acharya BR, Forest T, Pudussery MV, Liu X, Ferreira JFS, Suarez DL. *Scientific Reports* 10 (2020), 21087. DOI: [10.1038/s41598-020-78036-4](https://doi.org/10.1038/s41598-020-78036-4); full text: [PMC7712888](https://pmc.ncbi.nlm.nih.gov/articles/PMC7712888/).
- **Donor organism:** 14 commercial Prunus/almond rootstocks; no transgene donor.
- **Chassis / life stage:** non-grafted pot-grown rootstocks, 1.5-gallon sand:sandy-loam pots.
- **Salinity chemistry / duration:** municipal-water + nutrient control ECiw 1.36 dS m−1; four different ionic recipes, each ECiw 3.0 dS m−1: Na–sulfate, Na–chloride, Na–chloride/sulfate, and Ca/Mg–chloride/sulfate; pH 7.3–7.6; 600 mL every other day for 10 months. Leaf ion/physiology at 8 weeks.
- **Sample size:** 14 genotypes × 5 water treatments × 3 replications × 3 one-plant pots = 630 trees; gas exchange n=6 leaves per rootstock × water cell.
- **Endpoint:** survival, trunk diameter, leaf Na/Cl and other ions, gas exchange, chlorophyll, proline/ORAC/phenolics, and expression of 23 salt-response genes.
- **Effect as reported:** Na–chloride water caused the greatest survival and trunk-diameter reduction; Empyrean 1 and several peach–almond hybrids were relatively tolerant, and performance strongly related to leaf Na and Cl exclusion.
- **Accession IDs:** none is a construct sequence; locus-level expression calls must not be recast as functional proof.
- **Sequence status:** `not_applicable`.
- **Key limitation:** rootstock comparisons are associations at moderate ECiw, not seawater, not fruiting/grafted kernel yield, and not evidence that any reported locus is causal.
- **Correction/retraction check:** no notice located on Nature/PMC record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-ALMOND-ROOTGRADIENT-2021

- **Candidate / tier:** Empyrean-1 mechanism anchor; `E4 — anatomy/expression association only`.
- **Exact title:** *Investigation of Salt Tolerance Mechanisms Across a Root Developmental Gradient in Almond Rootstocks*.
- **Primary source:** Shao Y, Cheng Y, Pang H, et al. *Frontiers in Plant Science* 11 (2021), 595055. DOI: [10.3389/fpls.2020.595055](https://doi.org/10.3389/fpls.2020.595055); full text: [Frontiers](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2020.595055/full).
- **Donor organism:** Empyrean-1, Controller-5 and Krymsk-86 almond-production rootstocks; no transgene donor.
- **Chassis / life stage:** young rootstocks, root developmental zones Z0–Z2.
- **Salinity chemistry / duration:** 0, 50 or 150 mM NaCl. Phenotype at 13 d; Na imaging/suberin/lignin at 3 d; cell viability at 3 and 13 d; candidate-gene expression at 150 mM for 3 d.
- **Sample size:** growth n=5; imaging/viability representative/quantified n=15; gene-expression analysis used at least three biological replicates.
- **Endpoint:** root/leaf weight and length, Na localization, FDA viability, suberin/lignin, and salt-related gene expression.
- **Effect as reported:** Empyrean-1 had lower cortical Na signal, higher early suberin/lignin at apoplastic barriers and higher viability than the comparators under the NaCl challenges.
- **Accession IDs:** none sequence-verified as a candidate construct in this study.
- **Sequence status:** `not_applicable_for_construct; any KCS1-like or transporter locus requires independent identification`.
- **Key limitation:** acute NaCl-only juvenile assay with imaging proxies; it supports barrier/ion-exclusion hypotheses but does not prove a particular gene, mult-ion tolerance, yield, or food safety.
- **Correction/retraction check:** no notice located on Frontiers record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-ALMOND-ROOTPAC40-2022

- **Candidate / tier:** Rootpac 40 chassis anchor; `E4 — comparative phenotype/transcript association`.
- **Exact title:** *Morphological, physiological, biochemical, and transcriptome studies reveal the importance of transporters and stress signaling pathways during salinity stress in Prunus*.
- **Primary source:** Acharya BR, et al. *Scientific Reports* 12 (2022), 1274. DOI: [10.1038/s41598-022-05202-1](https://doi.org/10.1038/s41598-022-05202-1); official full text: [USDA PDF](https://www.ars.usda.gov/ARSUserFiles/51100/Publications/068.pdf).
- **Donor organism:** Rootpac 40 and Nemaguard rootstocks; no transgene donor.
- **Chassis / life stage:** approximately one-year-old rootstocks.
- **Salinity chemistry / duration:** sodium/chloride-dominant high-saline irrigation water; exact multi-ion recipe is in Supplementary Table S12 and must be imported before simulation calibration. Whole-plant treatment 10 months; RNA-seq roots/leaves harvested 48 h after treatment; physiological measurements 8 weeks.
- **Sample size:** three biological replicates (one plant per replicate) for reported physiological/ion and RNA-seq comparisons.
- **Endpoint:** survival, trunk diameter, leaf ions, proline, photosynthesis/gas exchange, and RNA-seq (BioProject `PRJNA732909`).
- **Effect as reported:** Rootpac 40 survival was 90.6% versus 38.9% for Nemaguard in the study’s saline treatment and accumulated less leaf Na and Cl, with differential transporter/signaling expression.
- **Accession IDs:** `PRJNA732909` is data provenance; peach-reference locus IDs are annotation aids, not Rootpac 40 allele validation.
- **Sequence status:** `not_applicable_for_construct; Rootpac 40 alleles must be sequenced before editing or promoter claims`.
- **Key limitation:** water composition cannot be reduced to EC; only two rootstocks, three biological replicates, and no grafted fruiting outcome.
- **Correction/retraction check:** no notice located on Nature/USDA record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-ALMOND-HAIRYROOT-2024

- **Candidate / tier:** Paper 1 experimental-method anchor; `N/A — method feasibility`.
- **Exact title:** *Genome editing in almond using hairy root transformation system*.
- **Primary source:** Jedličková V, Štefková M, Sánchez López JF, Grimplet J, Rubio Cabetas MJ, Robert HS. *Plant Cell, Tissue and Organ Culture* 159 (2024), 74. DOI: [10.1007/s11240-024-02935-x](https://doi.org/10.1007/s11240-024-02935-x); publisher record: [Springer](https://link.springer.com/article/10.1007/s11240-024-02935-x).
- **Donor organism:** not applicable; this is a transformation method.
- **Chassis / life stage:** almond seedlings and almond × peach hybrids; composite plants with wild-type shoots and transformed hairy roots.
- **Salinity chemistry / duration:** no salinity challenge; roots were subcultured every 4–5 weeks, and composite plants were moved to soil after about one month.
- **Sample size:** limited replication explicitly acknowledged; exact transformant counts are assay-specific and must be extracted if used for planning rates.
- **Endpoint:** hairy-root induction, VENUS signal, and CRISPR knockout screening for `ERF74` and `GAI`.
- **Effect as reported:** the authors produced composite plants and recovered edited hairy roots, supporting a rapid root-function assay but not stable whole-tree transformation.
- **Accession IDs:** target-gene accession list is method-specific; no Paper 1 candidate sequence is validated by this source.
- **Sequence status:** `not_applicable`.
- **Key limitation:** composite roots are not stable engineered rootstocks or fruiting trees; transformation rate, event independence and phenotype must be re-estimated in the chosen Vairo protocol.
- **Correction/retraction check:** no notice located on Springer record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-ALMOND-STABLETRANSFORM-1999

- **Candidate / tier:** stable-transformation feasibility anchor; `N/A — method feasibility`.
- **Exact title:** *Transgenic almond (Prunus dulcis Mill.) plants obtained by Agrobacterium-mediated transformation of leaf explants*.
- **Primary source:** Miguel CM, Oliveira MM. *Plant Cell Reports* 18 (1999), 387–393. DOI: [10.1007/s002990050591](https://doi.org/10.1007/s002990050591); institutional record: [University of Lisbon](https://researchportal.ulisboa.pt/en/publications/transgenic-almond-prunus-dulcis-mill-plants-obtained-by-agrobacte/).
- **Donor organism:** not applicable; leaf-explant transformation method in *Prunus dulcis*.
- **Chassis / life stage:** regenerated micropropagated almond shoots derived from leaf explants.
- **Salinity chemistry / duration:** no salinity treatment.
- **Sample size:** four regenerated shoots (A–D) reached molecular assessment; only clone D consistently tested GUS/PCR positive and had Southern evidence of stable integration.
- **Endpoint:** GUS, PCR, Southern blot and chimerism assessment.
- **Effect as reported:** one clone provided evidence compatible with stable transgene integration; three others appeared chimeric.
- **Accession IDs:** no primary-candidate accession.
- **Sequence status:** `not_applicable`.
- **Key limitation:** old, low-throughput evidence with chimerism; it is proof that stable transformation has been reported, not a current reproducible regeneration protocol or a salinity phenotype.
- **Correction/retraction check:** no notice located on the DOI/institutional record on 2026-08-12.
- **Access date:** 2026-08-12.

### EV-CA-ALMOND-SALINITY-GUIDE-2024

- **Candidate / tier:** greenhouse water-management context; `N/A — official grower guidance`.
- **Exact title:** *Salinity Management Guide for Almond Growers*.
- **Official source:** Almond Board of California, February 2024. [Official PDF](https://www.almonds.org/sites/default/files/2024-02/Salinity%20Management%20Guide%20for%20Almond%20Growers.pdf).
- **Donor organism / chassis / life stage:** N/A; California almond production guidance.
- **Salinity chemistry / duration / sample size:** N/A as a guide; it summarizes management practice and does not supply a single primary experimental sample for a construct effect.
- **Endpoint / effect as reported:** guidance emphasizes measurement and management of irrigation-water and soil salinity, Na/Cl/SAR and leaching/drainage decisions; it is not evidence that raw seawater can be used in almonds.
- **Accession IDs / sequence status:** N/A.
- **Key limitation:** stakeholder guidance, not a primary causal test; it cannot be used to define a seawater recipe or validate contained-system performance.
- **Correction/retraction check:** official PDF currently served by Almond Board; version/date must be captured in the final archive.
- **Access date:** 2026-08-12.

### EV-CA-OCEAN-DESALINATION

- **Candidate / tier:** discharge/permit context; `N/A — official regulatory source`.
- **Exact title:** *Ocean Desalination* (California Water Boards program page).
- **Official source:** State Water Resources Control Board. [Official program page](https://www.waterboards.ca.gov/water_issues/programs/ocean/desalination/).
- **Donor organism / chassis / life stage:** N/A.
- **Salinity chemistry / duration / sample size:** N/A; regulatory and environmental-review context, not a plant experiment.
- **Endpoint / effect as reported:** the page describes California’s permitting/environmental framework for ocean-desalination facilities and related requirements; it is not permission for an individual greenhouse to discharge concentrate.
- **Accession IDs / sequence status:** N/A.
- **Key limitation:** facility-specific permits, waste classification, local sewer/disposal agreements and institutional containment requirements remain fact-specific; this source cannot replace counsel or agency consultation.
- **Correction/retraction check:** official live webpage; archive/print to a dated project record before a registered-report submission.
- **Access date:** 2026-08-12.

### EV-USDA-APHIS-SECURE

- **Candidate / tier:** biotechnology-regulatory context; `N/A — official regulatory source`.
- **Exact title:** *SECURE Rule* (Sustainable, Ecological, Consistent, Uniform, Responsible, Efficient).
- **Official source:** USDA APHIS Biotechnology Regulatory Services. [Official page](https://www.aphis.usda.gov/biotechnology/regulations/secure-rule).
- **Donor organism / chassis / life stage / chemistry / duration / sample size:** N/A.
- **Endpoint / effect as reported:** official framework information for regulated movement, importation and environmental release of organisms developed using genetic engineering; it is not a biosafety approval or a salinity result.
- **Accession IDs / sequence status:** N/A.
- **Key limitation:** the actual construct, recipient, facility, movement and intended use require institution-specific IBC and regulatory review; do not infer exemption/permit status from this general page.
- **Correction/retraction check:** official live webpage; retain a dated archive before reliance.
- **Access date:** 2026-08-12.

## Critical unresolved items before a construct or numerical prior is admitted

1. **PyAPX is accession-verified but not construct-ready.** The paper reports `AY282755.1`, and guarded repository retrieval verifies that complete-CDS record identity. The targeting sequence, exact construct map, and event mapping remain unresolved, so sequence build stays blocked.
2. **All donor sequences require retrieval and identity checks.** Even accession-backed C1/C4 and reference-locus-backed C5/C6 need source-allele/ORF, translation, topology/targeting, and final-plasmid sequencing. Peach reference loci are not a Rootpac 40 or Nemaguard allele certificate.
3. **C4 has a known adverse route.** Its primary paper reports higher xylem Na. It cannot be treated as a root-exclusion gene without the registered cell-layer, xylem-sap and whole-system balance gates.
4. **C1 functional label is not transport stoichiometry proof.** Keep its pump direction, coupling and energy burden as hypotheses.
5. **No candidate record is evidence for raw seawater irrigation.** All primary candidate evidence uses simplified NaCl/MS treatments, not an ion-complete seawater, brackish-water, or concentrate treatment.
6. **Quantitative reuse needs figure-level extraction.** C2's 250 mM NaCl schedule, day-10 germination read, dish replication, and T1 line counts are transcribed, but endpoint-specific effect sizes still require figure-level extraction; C3/C5/C6 likewise require per-assay n/duration details from full methods/figures.
7. **Rootstock results do not make a locus causal.** The R40/E1 records support chassis and mechanism priors only; they cannot promote associated genes beyond E4.
8. **Compliance sources are context, not authorizations.** A contained greenhouse still needs IBC, waste/concentrate disposition and any applicable permit review.
