# Hacker News Submission Draft

**Submission Type:** Show HN  
**URL:** `https://consigcody94.github.io/saltwater-mini-almond/`  
**Alternative Repo URL:** `https://github.com/consigcody94/saltwater-mini-almond`  
**Title:** `Show HN: AlmondLab – Virtual lab & Stage 1 registered report for salt-tolerant crops`

---

## Submission Text / First Comment:

Hi HN,

California produces over 80% of the world's commercial almond supply, but increasing groundwater overdraft and root-zone salinization in the Central Valley are threatening the long-term viability of orchards. Almonds (*Prunus dulcis*) are notoriously salt-sensitive woody perennials—they suffer leaf necrosis, yield collapse, and tree mortality when root-zone electrical conductivity exceeds 1.5–2.0 dS/m.

Conventional tree breeding takes decades due to long juvenility periods, while simply dumping saline water onto farmland degrades soil structure and pollutes regional aquifers.

To explore a path forward without risking agricultural soils, we designed and pre-registered **AlmondLab**: an open-source computational virtual laboratory and Stage 1 Registered Report protocol for a high-density, closed-loop genetic tournament.

### What it does:

1. **Six-Mechanism Genetic Tournament (C1–C6):** Evaluates candidate physiological salt-tolerance modules engineered into compact composite-root rootstocks:
   - **C1:** Marine *SOS1* Na⁺/H⁺ antiporter for rhizospheric Na⁺ extrusion
   - **C2:** Halophytic *HKT1;5* transporter for xylem Na⁺ retrieval and shoot protection
   - **C3:** Tonoplast *NHX1* exchanger for vacuolar sequestration
   - **C4:** Polyol (*mtlD*) synthesis for cytoplasmic osmotic adjustment
   - **C5:** Enhanced ascorbate peroxidase (*APX*) for ROS detoxification
   - **C6:** Suberin synthase (*CYP86A1*) for Casparian strip apoplastic barrier reinforcement

2. **Zero-Discharge Contained Greenhouse Architecture:** Pairs high-density dwarf rootstocks with precision root lysimeters, selective reverse osmosis (RO) desalination, continuous nutrient remineralization, and solid salt crystallization to guarantee zero saline effluent discharge.

3. **Pre-Registered Bayesian Statistical Analysis Plan (SAP):**
   - We enforce strict falsification gates: H1 efficacy ($P(\delta_k \ge \ln(1.20)) \ge 0.90$), H2 non-saline guardrail ($P(\text{penalty}_k > 0.10) \le 0.10$), and H3 directional mechanism assay confirmation ($P \ge 0.90$).
   - Candidate ranking uses the conservative weakest-gate score: $A[k] = \min(P_{H1}[k], P_{H2,\text{good}}[k], P_{H3}[k])$ (marginal gate probabilities are never multiplied to avoid artificially deflating performance).
   - Ties within 0.02 of the leader advance as `co-leading`, with a hard cap of $\le 4$ finalist slots advancing to confirmatory evaluation.

4. **Reproducible Virtual Laboratory CLI (`almondlab`):**
   - The entire pipeline is verifiable locally via Typer CLI (`almondlab init`, `validate`, `design`, `simulate`, `analyze`, `rank`, `audit`, `report`).
   - 1,533 passing unit, property-based (Hypothesis), and acceptance tests.
   - Strict watermark enforcement: `SYNTHETIC — NOT BIOLOGICAL EVIDENCE`.

### Links & Artifacts:
- **Live Interactive Paper:** https://consigcody94.github.io/saltwater-mini-almond/
- **GitHub Repository:** https://github.com/consigcody94/saltwater-mini-almond
- **Release Assets (HTML, DOCX, MD, 7 high-res figures):** https://github.com/consigcody94/saltwater-mini-almond/releases/tag/v0.2.0-registered-report

We would love feedback and critique from the HN community on the biophysical model formulation, the Bayesian decision boundaries, and using Stage 1 Registered Reports for agricultural biotechnology!
