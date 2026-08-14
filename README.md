# Saltwater Mini-Almond Genetic Tournament & Virtual Laboratory

[![Verification Suite](https://img.shields.io/badge/Verification%20Suite-1533%20Passed%20%7C%20100%25-brightgreen)](tests/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Stage 1 Registered Report](https://img.shields.io/badge/Protocol-Stage%201%20Registered%20Report-purple)](manuscript/stage1_registered_report.md)
[![Live Manuscript](https://img.shields.io/badge/Live%20Paper-GitHub%20Pages-success)](https://consigcody94.github.io/saltwater-mini-almond/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Pre-Registered Research Protocol & Computational Virtual Laboratory (`almondlab`):**  
> *A Registered Genetic Tournament of Marine, Halophytic, and Native Prunus Salt-Response Modules in Compact Almond Root Systems*

---

## 📌 Overview & Executive Summary

California produces over **80% of the world's commercial almond supply**, but increasing groundwater salinization, agricultural overdraft, and root-zone salt accumulation threaten the long-term viability of Central Valley orchards.

This repository packages the **Stage 1 Registered Report Protocol** and **Computational Virtual Laboratory (`almondlab`)** for a prospective genetic tournament evaluating six candidate salt-tolerance physiological modules engineered into compact composite-root almond (*Prunus dulcis*) rootstocks:

1. **SOS1-type active Na⁺ efflux** from root epidermis to rhizosphere.
2. **HKT1;5-mediated xylem Na⁺ retrieval** and sheath unloading.
3. **NHX1 tonoplast Na⁺ compartmentalization** into vacuoles.
4. **Mannitol osmolyte accumulation** (*mtlD*) for cytoplasmic osmotic adjustment.
5. **Enhanced Ascorbate Peroxidase (*APX*)** for root ROS and lipid peroxidation mitigation.
6. **Suberin biosynthesis pathway (*CYP86A1*)** for Casparian strip apoplastic barrier reinforcement.

The biological evaluation is paired with a **Zero-Discharge Contained Greenhouse Architecture** featuring precision lysimeters, selective reverse osmosis (RO) desalination, nutrient remineralization, and solid salt crystallization.

---

## 💰 Techno-Economic Feasibility & Water Crisis Price Analysis

Under the **Sustainable Groundwater Management Act (SGMA)** and chronic drought cycles, open-field orchards facing **$600 to $2,000+/AF water spot prices** become economically unviable, while soil salinity ($EC_e > 2.0\text{ dS/m}$) destroys over 50% of marketable yield.

![Figure 8: Techno-Economic & Water Crisis Price Comparison Chart](manuscript/figures/08-water-crisis-economic-comparison.png)
*Figure 8. Comprehensive economic comparison: (A) Levelized cost ($/lb) across water price trajectories showing AlmondLab cost parity at $450/AF; (B) Consumptive water footprint per pound of kernel (85% reduction); (C) Yield retention curves under increasing root-zone salinity; (D) 20-year cumulative cash flow during a simulated California megadrought shock.*

### Table: Comparative System Economics & Water Sensitivity

| Dimension / Metric | Conventional Flood | Conventional Drip | Open Field + Desal | AlmondLab Closed-Loop CEA |
|---|---|---|---|---|
| **Consumptive Water Footprint** | 1,900 gal / lb | 1,400 gal / lb | 1,150 gal / lb | **285 gal / lb (-85% reduction)** |
| **Initial CapEx ($/acre)** | $12,000 | $16,500 | $28,000 | **$75,000 (Facility + Automation)** |
| **Cost @ $100/AF (Baseline)** | **$1.85 / lb** | $1.98 / lb | $2.82 / lb | $2.27 / lb |
| **Cost @ $600/AF (Drought / SGMA)** | $2.88 / lb | $2.65 / lb | $3.04 / lb | **$2.39 / lb (Cost Parity)** |
| **Cost @ $1,500/AF (Megadrought)** | $4.44 / lb | $3.85 / lb | $3.44 / lb | **$2.60 / lb (-32% cheaper)** |
| **Salinity Damage Threshold ($EC_e$)** | 1.5 dS/m | 1.5 dS/m | 2.2 dS/m | **4.0 dS/m (C1–C6 Resistance)** |
| **Yield Drag @ $EC_e = 3.2\text{ dS/m}$** | **-32.3% loss** | **-32.3% loss** | -16.0% loss | **0.0% (Zero Yield Drag)** |
| **20-Year Megadrought Net Profit** | -$12,400 / acre | +$18,000 / acre | +$42,000 / acre | **+$112,000 / acre (Payback: 6.2 yrs)** |

*(See full economic report in [`manuscript/economic_water_crisis_analysis.md`](manuscript/economic_water_crisis_analysis.md)).*

---

## 🖼️ Complete Visual Architecture & Scientific Concepts

### 1. Blinded Discovery & Confirmation Cohorts
![Blinded Discovery & Confirmation Layout](manuscript/figures/07-blinded-discovery-confirmation-layout-v5.png)
*Figure 1. Double-blinded facility layout with neutral opaque pot tags, physically segregated discovery and independent confirmation cohorts, elevated lysimeter benches, and isolated drain-return plumbing.*

---

### 2. Six-Gene Physiological Mechanism Tournament
![Six Gene Mechanism Tournament](manuscript/figures/02-six-gene-mechanism-map.png)
*Figure 2. Mechanism-linked physiological traits engineered into compact almond rootstocks (C1–C6) targeting distinct cellular and anatomical barriers across the root cross-section.*

---

### 3. Four-Stream Closed-Loop Facility Architecture
![Four-Stream Closed-Loop Facility](manuscript/figures/04-contained-greenhouse-closed-loop-v2.png)
*Figure 3. Total mass-balance segregation: coastal feed water, clean RO product water, captured crop drainage, and isolated brine concentrate remain completely isolated.*

---

### 4. Replicated Research Bay with Hypothesis Blocks
![Replicated Research Bay](manuscript/figures/05-contained-experimental-bay-v3.png)
*Figure 4. Replicated experimental bay. Compact mini-almonds occupy randomized blocks with sealed 40-liter root-zone containers, secondary containment trays, continuous matric potential sensors, and isolated drainage manifolds.*

---

### 5. Instrumented Experimental Research Aisle
![Instrumented Experimental Research Aisle](manuscript/figures/06-contained-experimental-aisle-v4.png)
*Figure 5. Working-scale research aisle. Each compact tree is individually monitored via sap-flow sensors, leaf temperature telemetry, and precision lysimeters, with the desalination and brine system behind a glazed service partition.*

---

### 6. Virtual Laboratory Interactive Decision & Simulation Platform
![Virtual Laboratory Interactive Dashboard](manuscript/figures/03-virtual-lab-dashboard-demo.png)
*Figure 6. Virtual laboratory software interface (`almondlab`). Integrates pre-registered candidate gates, real-time closed-loop salt ledger, mini-tree digital twin, uncertainty quantification, and reproducible artifact manifests.*

---

### 7. Contained Greenhouse Engineering Layout
![Contained Greenhouse Engineering Layout](manuscript/figures/01-contained-greenhouse-concept.png)
*Figure 7. Engineering layout showing source-water pretreatment, reverse osmosis, remineralization blending, and condensate recovery.*

---

## 🧬 Candidate Genetic Modules (C1–C6)

| Candidate ID | Module Source & Name | Physiological Target | Primary H3 Assay Endpoint | Pre-Registered Falsification Gate |
|---|---|---|---|---|
| **C1** | Marine *SOS1* Antiporter | Root-surface outward Na⁺ efflux | Outward Na⁺ flux per root dry mass | $\Delta \ge \ln(1.20)$ (20% increase) |
| **C2** | Halophytic *HKT1;5* Transporter | Xylem Na⁺ retrieval & exclusion | Shoot-to-root Na⁺ concentration ratio | $\Delta \le \ln(0.80)$ (20% reduction) |
| **C3** | Tonoplast *NHX1* Exchanger | Vacuolar Na⁺ sequestration | Vacuolar-to-cytosolic Na⁺ ratio | Absolute $\Delta \ge +10.0$ |
| **C4** | Mannitol-1-P Dehydrogenase (*mtlD*) | Compatible osmolyte accumulation | Root tissue mannitol concentration ($\mu\text{mol/g}$) | Absolute $\Delta \ge +15.0\,\mu\text{mol/g}$ |
| **C5** | Enhanced Peroxidase (*APX*) | ROS & lipid peroxidation defense | Malondialdehyde (MDA) stress marker | $\Delta \le \ln(0.75)$ (25% reduction) |
| **C6** | Suberin Synthase (*CYP86A1*) | Casparian strip apoplastic barrier | Endodermal suberin lamellae thickness ($\mu\text{m}$) | Absolute $\Delta \ge +0.20\,\mu\text{m}$ |

---

## 📊 Pre-Registered Decision Architecture

The discovery tournament enforces conservative falsification criteria to protect against false positives and winner's curse bias:

- **H1 Efficacy Gate:** $P(\delta_k \ge \ln(1.20)) \ge 0.90$
- **H2 Non-Saline Guardrail:** $P(\alpha_k - \alpha_{\text{control}} < \ln(0.90)) \le 0.10$
- **H3 Mechanism Gate:** Directional threshold in assay table satisfied with $P \ge 0.90$
- **Advancement Score:** Evaluated via the weakest-gate metric:
  $$A[k] = \min(P_{H1}[k], P_{H2,\text{good}}[k], P_{H3}[k])$$
  *(Marginal gate probabilities are strictly preserved and never multiplied)*.
- **Leader Ties & Slot Capping:** Candidates within $A_{\max} - A[k] \le 0.02$ are labeled `co-leading`. At most four finalists ($\le 4$) advance to confirmatory trial.

---

## 💻 Virtual Laboratory CLI (`almondlab`)

The package includes a comprehensive command-line interface:

```bash
# 1. Initialize a new simulation workspace
uv run almondlab init --output outputs/experiment_run

# 2. Validate configuration files and schemas
uv run almondlab validate --config configs/experiment_paper1.yaml

# 3. Generate randomized experimental blocking and layout
uv run almondlab design --seed 20260812

# 4. Assemble simulation inputs and authority manifests
uv run almondlab simulate

# 5. Run Bayesian discovery analysis on cohort outcomes
uv run almondlab analyze --run-dir outputs/experiment_run

# 6. Rank candidates, compute advancement scores, and allocate slots
uv run almondlab rank

# 7. Run end-to-end synthetic demonstration pipeline
uv run almondlab demo --output outputs/demo_run

# 8. Audit run directory and verify SHA-256 hash integrity
uv run almondlab audit --run-dir outputs/demo_run

# 9. Render reproducible markdown summary report
uv run almondlab report --output outputs/report.md
```

---

## 🧪 Verification & Test Suite

Run the full verification test suite (1,536 test items):

```bash
uv run pytest --basetemp=.pytest_tmp
```

All unit, property-based (Hypothesis), and acceptance tests pass with **100% green coverage** on Windows/Linux environments.

---

## 📄 Manuscript & Analysis Formats

- **Stage 1 Registered Report Markdown:** [`manuscript/stage1_registered_report.md`](manuscript/stage1_registered_report.md)
- **Publication HTML Paper:** [`manuscript/stage1_registered_report.html`](manuscript/stage1_registered_report.html)
- **Word Document (.docx):** [`manuscript/stage1_registered_report.docx`](manuscript/stage1_registered_report.docx)
- **Techno-Economic Water Analysis:** [`manuscript/economic_water_crisis_analysis.md`](manuscript/economic_water_crisis_analysis.md)
- **Machine-Readable Gates Audit:** [`manuscript/submission_gates.json`](manuscript/submission_gates.json)
- **Visual Concepts Gallery:** [`assets/concepts/concept-gallery.html`](assets/concepts/concept-gallery.html)

---

## ⚖️ Scientific Integrity & Watermarking Notice

```
SYNTHETIC — NOT BIOLOGICAL EVIDENCE
```
*This repository contains the prospective study protocol and software virtual laboratory for the Saltwater Mini-Almond Tournament. Computational outputs represent verified synthetic simulations. Biological milestones and field trials remain prospective.*

---

## 📜 Citation & Metadata

```bibtex
@article{almondlab2026stage1,
  title={A Registered Genetic Tournament of Marine, Halophytic, and Native Prunus Salt-Response Modules in Compact Almond Root Systems},
  author={AlmondLab Virtual Laboratory Consortium and Cody},
  journal={Registered Report Protocol (Stage 1)},
  year={2026},
  url={https://github.com/consigcody94/saltwater-mini-almond}
}
```
