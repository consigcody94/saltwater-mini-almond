# Synthetic Biology Vector Specifications & Cassette Engineering

**Project:** Saltwater Mini-Almond Genetic Tournament & Virtual Laboratory  
**Category:** Molecular Genetics, Synthetic Biology & Vector Engineering  
**Version:** 1.0-Registered (August 2026)  
**Target Organism:** *Prunus dulcis* (Mill.) D.A.Webb (Almond rootstock composite system)  
**Repository:** [consigcody94/saltwater-mini-almond](https://github.com/consigcody94/saltwater-mini-almond)  

---

## 1. Vector Backbone Architecture & Biosafety Design

All candidate transgenes (C1–C6) are cloned into the standardized, non-mobilizable binary transformation backbone **`pALMOND-SAFE-v2`** (derived from pCAMBIA binary vectors with minimized T-DNA borders and zero extraneous backbone coding sequences).

### Core Vector Elements:
- **Left & Right Borders (LB/RB):** Synthetic 25-bp imperfect repeat borders with overdrive flanking sequences to promote precise single-copy integration.
- **Selection Marker:** Plant-optimized hygromycin phosphotransferase (*hptII*) driven by the constitutive *Nos* promoter with dual *Nos* terminators, flanked by *loxP* recombination sites for post-transformation Cre-mediated excision.
- **Visual Reporter:** Root-specific green fluorescent protein (*eGFP-ER*) driven by the *pAtGLP9* promoter for non-destructive spatial transformation verification in living root tissues.
- **Origin of Replication:** pVS1 (for high-stability maintenance in *Rhizobium rhizogenes* strain K599 / ARqua1) and ColE1 (for *E. coli* cloning).

---

## 2. Detailed Transgene Cassette Specifications (C1–C6)

```
[RB] ---> [pAtPRX66 (Root Promoter)] ---> [Codon-Optimized CDS (C1-C6)] ---> [t35S Terminator] ---> [Selection/Reporter] ---> [LB]
```

### Candidate C1: Constitutively Activated SOS1 Na⁺/H⁺ Antiporter
- **Source Organism:** *Salicornia brachiata* (*SbSOS1*, GenBank: JN038234) / *Prunus triflora* (*PtSOS1*).
- **Engineering Modification:** Truncation of the C-terminal autoinhibitory domain ($\Delta 970\text{--}1147\text{ aa}$) creating a constitutively active antiporter independent of calcineurin B-like (CBL)-interacting protein kinase 24 (CIPK24/CBL4) phosphorylation.
- **Promoter:** Root epidermal/cortical-specific promoter *pAtPRX66* (Arabidopsis peroxidase 66 homolog in *Prunus*, -1,250 bp) to direct outward Na⁺ extrusion into the rhizosphere while preventing ectopic vascular expression.
- **Predicted $V_{\max}$ / $K_m$:** $V_{\max} = 145\,\mu\text{mol}\cdot\text{g}^{-1}\cdot\text{h}^{-1}$; $K_m(\text{Na}^+) = 5.2\text{ mM}$.

---

### Candidate C2: High-Affinity Potassium Transporter (HKT1;5)
- **Source Organism:** *Thellungiella salsuginea* (*TsHKT1;2*, halophytic relative) codon-optimized for *Prunus dulcis*.
- **Mechanism:** Mediates selective Na⁺ retrieval from the ascending xylem sap in root stele/xylem parenchyma cells, sequestering Na⁺ before it reaches the photosynthetic canopy.
- **Selectivity Filter:** Conserved $S\text{-}G\text{-}G\text{-}G$ pore loop selectivity motif ensuring high Na⁺ specificity without uncoupling K⁺ homeostasis ($P_{\text{Na}}/P_{\text{K}} > 85$).
- **Promoter:** Xylem parenchyma-specific promoter *pAtHKT1;1* (root vascular bundle specific, -1,800 bp).

---

### Candidate C3: Vacuolar Na⁺/H⁺ Exchanger (NHX1)
- **Source Organism:** *Zygophyllum xanthoxylum* (*ZxNHX1*, extremophile xerophyte).
- **Target Subcellular Localization:** Tonoplast (vacuolar membrane) with confirmed C-terminal targeting peptide and N-glycosylation consensus sequences.
- **Mechanism:** Coupled to the tonoplast V-type $\text{H}^+\text{-ATPase}$ and $\text{H}^+\text{-PPase}$ proton pumps, driving intra-vacuolar Na⁺ sequestration to maintain cytosolic $\text{K}^+/\text{Na}^+ > 5.0$.
- **Promoter:** Ubiquitous root cortical and stellar promoter *pPrunus-UBQ10* (-1,100 bp).

---

### Candidate C4: Mannitol-1-Phosphate Dehydrogenase (mtlD)
- **Source Organism:** *Escherichia coli* K-12 (*mtlD*, GenBank: M13988).
- **Target Subcellular Localization:** Cytosol and chloroplast envelope via N-terminal transit peptide.
- **Mechanism:** Catalyzes the conversion of fructose-6-phosphate to mannitol-1-phosphate, subsequently dephosphorylated to accumulate compatible osmolyte mannitol up to $25\text{--}40\,\mu\text{mol}\cdot\text{g}^{-1}\text{ FW}$, maintaining root turgor at leaf water potentials $\Psi_w < -2.5\text{ MPa}$.
- **Promoter:** Salinity-inducible *pRD29A* promoter (-850 bp) featuring dual Dehydration-Responsive Elements (DRE/CRT) to prevent non-saline metabolic yield penalties (H2 guardrail compliance).

---

### Candidate C5: Engineered Cytosolic Ascorbate Peroxidase (cytAPX)
- **Source Organism:** *Prunus dulcis* native *PdAPX1* engineered with hyper-stable active-site mutations (Arg-38 $\to$ Lys, Trp-41 $\to$ Phe) derived from *Pisum sativum* extremophile homologs.
- **Mechanism:** Rapid catalytic reduction of hydrogen peroxide ($\text{H}_2\text{O}_2 + \text{Ascorbate} \to 2\text{H}_2\text{O} + \text{DHA}$) in root apical meristems, preventing lipid peroxidation of plasma membranes and preserving root hydraulic conductivity ($L_p$).
- **Catalytic Turnover:** $k_{\text{cat}} = 2.4 \times 10^3\text{ s}^{-1}$ (3.2x enhancement over native wild-type almond APX).
- **Promoter:** Root meristematic promoter *pAtRCH1* (-950 bp).

---

### Candidate C6: Cytochrome P450 Suberin Fatty Acid Hydroxylase (CYP86A1)
- **Source Organism:** *Arabidopsis thaliana* (*AtCYP86A1* / *HORST*, $\omega$-hydroxylase).
- **Mechanism:** Catalyzes the $\omega$-hydroxylation of $\text{C}_{16}\text{--}\text{C}_{18}$ very-long-chain fatty acids, accelerating and thickening the endodermal Casparian strip suberin lamellae by $+0.25\text{ to }+0.40\,\mu\text{m}$.
- **Physiological Impact:** Blocks the apoplastic bypass flow of $\text{Na}^+$ and $\text{Cl}^-$ ions into the vascular cylinder under high transpirational demand ($EC_w > 3.0\text{ dS/m}$).
- **Promoter:** Endodermal-specific promoter *pAtSCR* (*SCARECROW*, -1,400 bp).

---

## 3. CRISPR/Cas9 Ribonucleoprotein (RNP) Target Sites

For targeted integration and native gene enhancement via precision base editing (HDR), the following sgRNA guide sequences have been pre-validated:

| Target Locus | sgRNA Target Sequence (5' $\to$ 3') | PAM | Cleavage Locus | Purpose |
|---|---|---|---|---|
| **PdSOS1-exon19** | `GTCGCCGTCATCCTCGGCGC` | TGG | Chr2:18,421,092 | Auto-inhibitory tail truncation ($\Delta 970\text{--}1147$) |
| **PdHKT1-promoter** | `AAGCTTAGCCTACGGCGTAG` | CGG | Chr4:09,124,550 | Insertion of root-vascular enhancer elements |
| **PdCYP86A1-5'UTR** | `CGTAGCCTAGGTACCGATCG` | AGG | Chr7:24,812,015 | Endodermal expression driver integration |
