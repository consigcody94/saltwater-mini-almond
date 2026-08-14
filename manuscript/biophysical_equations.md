# Continuum Biophysics & Mathematical Model Derivations

**Project:** Saltwater Mini-Almond Genetic Tournament & Virtual Laboratory  
**Category:** Theoretical Biophysics, Ion Transport & Continuum Plant Physiology  
**Version:** 1.0-Registered (August 2026)  
**Repository:** [consigcody94/saltwater-mini-almond](https://github.com/consigcody94/saltwater-mini-almond)  

---

## 1. Radial Root Electrodiffusion & Ion Transport

Radial movement of $\text{Na}^+$ and $\text{Cl}^-$ through the composite root cross-section ($r \in [r_{\text{rhizo}}, r_{\text{xylem}}]$) couples symplastic and apoplastic continuum transport via the **extended Nernst-Planck electrodiffusion equation**:

$$J_i(r) = -D_i \left( \frac{\partial c_i(r)}{\partial r} + \frac{z_i F}{R T} c_i(r) \frac{\partial \psi(r)}{\partial r} \right) + v_{\text{water}}(r) \cdot (1 - \sigma_i) c_i(r)$$

where:
- $J_i(r)$: Radial flux of ion species $i \in \{\text{Na}^+, \text{K}^+, \text{Cl}^-\}$ ($\text{mol}\cdot\text{m}^{-2}\cdot\text{s}^{-1}$).
- $D_i$: Effective radial diffusion coefficient in cell wall apoplast ($\approx 1.2 \times 10^{-9}\,\text{m}^2/\text{s}$).
- $z_i$: Valence charge ($+1$ for $\text{Na}^+, \text{K}^+$; $-1$ for $\text{Cl}^-$).
- $\psi(r)$: Trans-tissue electrical potential profile across root cell layers ($\text{V}$).
- $v_{\text{water}}(r)$: Radial advective water velocity ($v(r) = Q_{\text{transp}} / (2\pi r L_{\text{root}})$).
- $\sigma_i$: Reflection coefficient of the Casparian strip ($\sigma_{\text{wt}} \approx 0.72$; $\sigma_{\text{C6\_suberin}} \approx 0.94$).

---

## 2. Plasma Membrane & Tonoplast Transporter Kinetics

Membrane transporter fluxes are modeled via coupled **Michaelis-Menten electrogenic transport**:

### 2.1 SOS1 Rhizospheric Na⁺ Efflux (Candidate C1)
$$\Phi_{\text{SOS1}} = V_{\max,\text{SOS1}} \cdot \frac{[\text{Na}^+]_{\text{cyt}}}{K_{m,\text{SOS1}} + [\text{Na}^+]_{\text{cyt}}} \cdot \frac{[\text{H}^+]_{\text{apo}}}{K_{m,\text{H}} + [\text{H}^+]_{\text{apo}}} \cdot \exp\left( \frac{F(\psi_{\text{cyt}} - \psi_{\text{apo}})}{2 R T} \right)$$

### 2.2 HKT1;5 Stelar Xylem Retrieval (Candidate C2)
$$\Phi_{\text{HKT1}} = V_{\max,\text{HKT1}} \cdot \frac{[\text{Na}^+]_{\text{xylem}}}{K_{m,\text{HKT1}} + [\text{Na}^+]_{\text{xylem}}} \cdot \left[ 1 + \left( \frac{[\text{K}^+]_{\text{xylem}}}{K_{i,\text{K}}} \right) \right]^{-1}$$

### 2.3 NHX1 Tonoplast Sequestration (Candidate C3)
$$\Phi_{\text{NHX1}} = V_{\max,\text{NHX1}} \cdot \frac{[\text{Na}^+]_{\text{cyt}}}{K_{m,\text{NHX}} + [\text{Na}^+]_{\text{cyt}}} \cdot \left( \frac{[\text{H}^+]_{\text{vac}}}{[\text{H}^+]_{\text{cyt}}} \right) \cdot \left( 1 - \frac{[\text{Na}^+]_{\text{vac}} [\text{H}^+]_{\text{cyt}}}{[\text{Na}^+]_{\text{cyt}} [\text{H}^+]_{\text{vac}} K_{\text{eq}}} \right)$$

---

## 3. Coupled Root-Canopy Water Thermodynamics

The volume flux of water $J_v$ through the root cylinder into the xylem transpiration stream is driven by both hydraulic and osmotic potential gradients:

$$J_v = L_p \left( \Delta P - \sum_{i} \sigma_i R T \Delta c_i \right) = L_p (\Delta \Psi_p + \Delta \Psi_s)$$

where:
- $L_p$: Root hydraulic conductivity ($\approx 2.8 \times 10^{-7}\,\text{m}\cdot\text{s}^{-1}\cdot\text{MPa}^{-1}$).
- $\Delta P = P_{\text{rhizo}} - P_{\text{xylem}}$: Hydrostatic pressure gradient.
- $\Delta \Psi_s = -R T \sum (c_{i,\text{rhizo}} - c_{i,\text{symplast}})$: Osmotic potential gradient.

Under extreme salinity ($EC_w = 12.0\text{ dS/m}$, $\Psi_{s,\text{soil}} \approx -0.45\text{ MPa}$), turgor pressure $P_{\text{turgor}} = \Psi_w - \Psi_s$ is preserved in candidate C4 via active compatible polyol accumulation ($\Delta \Psi_{s,\text{mannitol}} = -c_{\text{mtlD}} R T \approx -0.62\text{ MPa}$).

---

## 4. Closed-Loop 4-Stream Desalination Mass-Balance System

The greenhouse dynamic mass-balance system couples continuous differential equations for all 4 fluid streams:

```
[Feed Seawater Stream F] ---> [RO Membrane Unit] ---> [Permeate Product Water P] ---> [Irrigation Loop I] ---> [Lysimeters]
                                    |                                                                               |
                                    v                                                                               v
                        [Brine Concentrate B]                                                           [Drainage Return D]
```

### Dynamic Balance Equations:
1. **Total Water Mass Closure:**
   $$\frac{d V_{\text{storage}}}{d t} = Q_{\text{feed}} + Q_{\text{condensate}} + Q_{\text{drainage}} - Q_{\text{irrigation}} - Q_{\text{brine}}$$
2. **Salt Mass Conservation:**
   $$\frac{d(V_{\text{system}} C_{\text{Na}})}{d t} = Q_{\text{feed}} C_{\text{feed}} - Q_{\text{brine}} C_{\text{brine}} - \sum_{k=1}^{N_{\text{plants}}} \dot{m}_{\text{uptake},k}$$
3. **Zero-Discharge Salt Recovery Constraint:**
   $$m_{\text{salt,recovered}} = \int_0^T Q_{\text{brine}}(t) \cdot C_{\text{brine}}(t) \cdot \eta_{\text{crystallizer}} \, dt \equiv m_{\text{salt,input}} - m_{\text{salt,tissue}}$$
