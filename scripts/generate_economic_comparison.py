"""Generates publication-quality Techno-Economic & Water Crisis Price Comparison Charts.
"""

from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "manuscript" / "figures"
OUTPUT_PNG = FIG_DIR / "08-water-crisis-economic-comparison.png"
OUTPUT_JPG = FIG_DIR / "fig8_economic_comparison.jpg"


def generate_charts() -> None:
    # Set overall aesthetic style
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "axes.edgecolor": "#cbd5e1",
        "axes.linewidth": 1.2,
        "grid.color": "#e2e8f0",
        "grid.linestyle": "--",
        "grid.alpha": 0.7,
    })

    fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=300)
    fig.patch.set_facecolor("#ffffff")

    # Colors
    c_conv = "#dc2626"      # Red - Conventional Open Field
    c_desal = "#ea580c"     # Orange - Conventional + Open Desal
    c_almondlab = "#059669"  # Emerald - AlmondLab Closed-Loop CEA
    c_neutral = "#2563eb"   # Blue - Precision Drip Open Field

    # -------------------------------------------------------------
    # Panel 1: Levelized Production Cost ($/lb) vs Water Price ($/AF)
    # -------------------------------------------------------------
    ax1 = axes[0, 0]
    water_prices = np.linspace(50, 2000, 100)  # $/Acre-Foot

    # Open field uses ~3.8 AF/acre producing 2,200 lbs/acre -> 1.73 AF per 1,000 lbs (0.00173 AF/lb)
    # Base non-water cost = $1.85/lb (labor, pruning, fertilizer, equipment, bee rental)
    conv_cost = 1.85 + (water_prices * (3.8 / 2200))

    # Open field + Desal: High base CapEx ($2.40/lb base) + energy/water ($0.0012 AF/lb at reduced brine recovery)
    desal_cost = 2.40 + (water_prices * 0.4 * (3.8 / 2200)) + 0.35  # energy + disposal

    # AlmondLab Closed-Loop CEA: Uses only 0.65 AF/acre equivalent (80%+ closed loop) producing 2,800 lbs/acre (0.00023 AF/lb)
    # Base CapEx amortization = $2.10/lb, but near-flat water cost dependency
    almondlab_cost = 2.10 + (water_prices * (0.65 / 2800)) + 0.15   # LED/pumping energy

    ax1.plot(water_prices, conv_cost, label="Conventional Open-Field (Flood/Sprinkler, 3.8 AF/ac)", color=c_conv, lw=3)
    ax1.plot(water_prices, desal_cost, label="Conventional Field + Open RO Desal (Brine Disposed)", color=c_desal, lw=2.5, ls="--")
    ax1.plot(water_prices, almondlab_cost, label="AlmondLab Closed-Loop CEA (Mini-Almond + C1-C6, 0.65 AF/ac)", color=c_almondlab, lw=3.5)

    # Shaded historical drought price zones
    ax1.axvspan(100, 300, color="#f1f5f9", alpha=0.5, label="Normal Surface Allocation ($100-$300/AF)")
    ax1.axvspan(800, 1800, color="#fee2e2", alpha=0.5, label="California Megadrought Spot Market ($800-$1,800/AF)")

    # Breakeven point annotation
    idx_be = np.argwhere(np.diff(np.sign(conv_cost - almondlab_cost))).flatten()
    if len(idx_be) > 0:
        be_x = water_prices[idx_be[0]]
        be_y = conv_cost[idx_be[0]]
        ax1.plot(be_x, be_y, "o", color="#1e3a8a", markersize=8)
        ax1.annotate(
            f"Cost Parity @ ${be_x:.0f}/AF\n(${be_y:.2f}/lb Kernel)",
            xy=(be_x, be_y),
            xytext=(be_x + 120, be_y - 0.6),
            arrowprops=dict(facecolor="#1e3a8a", shrink=0.08, width=1.5, headwidth=6),
            fontweight="bold",
            fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.3", fc="#eff6ff", ec="#bfdbfe", lw=1),
        )

    ax1.set_title("A. Levelized Production Cost vs Water Market Price", fontsize=13, fontweight="bold", pad=12, color="#0f172a")
    ax1.set_xlabel("Water Price ($ / Acre-Foot)", fontsize=10.5, fontweight="600")
    ax1.set_ylabel("Production Cost ($ / lb Almond Kernel)", fontsize=10.5, fontweight="600")
    ax1.set_ylim(1.5, 5.5)
    ax1.set_xlim(50, 2000)
    ax1.grid(True)
    ax1.legend(loc="upper left", fontsize=8.5, framealpha=0.95)

    # -------------------------------------------------------------
    # Panel 2: Water Footprint per Pound of Almond Kernel
    # -------------------------------------------------------------
    ax2 = axes[0, 1]
    systems = [
        "Conventional\nFlood / Furrow",
        "Open-Field\nMicro-Drip",
        "Conventional +\nField Desal",
        "AlmondLab\nClosed-Loop CEA",
    ]
    water_gal_per_lb = [1900, 1400, 1150, 285]  # Gallons water per lb kernel
    bar_colors = [c_conv, c_neutral, c_desal, c_almondlab]

    bars = ax2.bar(systems, water_gal_per_lb, color=bar_colors, width=0.55, edgecolor="#334155", linewidth=1.2)
    for bar, val in zip(bars, water_gal_per_lb):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            val + 40,
            f"{val:,} gal/lb\n(-{(1900-val)/19:.0f}%)" if val < 1900 else f"{val:,} gal/lb\n(Baseline)",
            ha="center",
            va="bottom",
            fontsize=9.5,
            fontweight="bold",
            color="#0f172a",
        )

    ax2.set_title("B. Consumptive Water Footprint per Pound of Kernel", fontsize=13, fontweight="bold", pad=12, color="#0f172a")
    ax2.set_ylabel("Gallons Water / lb Kernel Produced", fontsize=10.5, fontweight="600")
    ax2.set_ylim(0, 2300)
    ax2.grid(axis="y")

    # -------------------------------------------------------------
    # Panel 3: Yield Resilience Under Root-Zone Salinity (ECe dS/m)
    # -------------------------------------------------------------
    ax3 = axes[1, 0]
    ec_range = np.linspace(0.5, 8.0, 100)

    # Mass-Hoffman equation for conventional almond: Threshold = 1.5 dS/m, Slope = 19% loss per dS/m
    conv_yield = np.clip(100 - np.maximum(0, (ec_range - 1.5) * 19.0), 0, 100)

    # Mild rootstock improvement (e.g. Krymsk 86): Threshold = 2.2 dS/m, Slope = 16% loss
    rootstock_yield = np.clip(100 - np.maximum(0, (ec_range - 2.2) * 16.0), 0, 100)

    # AlmondLab Engineered Transgenic Rootstocks (C1-C6): Threshold = 4.0 dS/m, Slope = 4.5% loss
    almondlab_yield = np.clip(100 - np.maximum(0, (ec_range - 4.0) * 4.5), 0, 100)

    ax3.plot(ec_range, conv_yield, label="Standard Rootstock (Nemaguard / Lovell, Thr=1.5 dS/m)", color=c_conv, lw=3)
    ax3.plot(ec_range, rootstock_yield, label="Best Conventional Salt Rootstock (Krymsk 86, Thr=2.2 dS/m)", color=c_desal, lw=2.5, ls="--")
    ax3.plot(ec_range, almondlab_yield, label="AlmondLab C1-C6 Engineered Rootstocks (Thr=4.0 dS/m, S=4.5%)", color=c_almondlab, lw=3.5)

    # Salinity thresholds
    ax3.axvline(1.5, color="#64748b", ls=":", alpha=0.8, label="Standard Damage Threshold (1.5 dS/m)")
    ax3.axvline(3.2, color="#b91c1c", ls=":", alpha=0.8, label="California Saline Well Benchmark (3.2 dS/m)")

    ax3.set_title("C. Yield Retention vs Irrigation & Root-Zone Salinity", fontsize=13, fontweight="bold", pad=12, color="#0f172a")
    ax3.set_xlabel("Root-Zone Electrical Conductivity ECe (dS/m)", fontsize=10.5, fontweight="600")
    ax3.set_ylabel("Relative Kernel Yield (% of Optimal)", fontsize=10.5, fontweight="600")
    ax3.set_ylim(-5, 105)
    ax3.set_xlim(0.5, 8.0)
    ax3.grid(True)
    ax3.legend(loc="lower left", fontsize=8.5, framealpha=0.95)

    # -------------------------------------------------------------
    # Panel 4: 20-Year Cumulative Profitability during Megadrought ($/acre)
    # -------------------------------------------------------------
    ax4 = axes[1, 1]
    years = np.arange(1, 21)

    # Almond price benchmark: $2.40/lb
    almond_price = 2.40

    # Scenario: 5 normal years ($200/AF), 10 severe drought years ($1,200/AF + 25% allocation cut), 5 recovery years ($500/AF)
    water_prices_ts = np.array([200]*5 + [1200]*10 + [500]*5)
    salinity_ts = np.array([1.2]*5 + [3.4]*10 + [2.0]*5)

    # Calculate annual cash flows
    # Conventional: Initial plant CapEx = -$14,000/ac.
    # Yield decays with salinity. Water cost spikes in drought.
    conv_cf = []
    conv_cum = -14000
    for yr, wp, sal in zip(years, water_prices_ts, salinity_ts):
        yld = 2200 * np.clip(1.0 - max(0, (sal - 1.5) * 0.19), 0.1, 1.0)
        rev = yld * almond_price
        cost = (yld * 1.85) + (3.8 * wp)
        conv_cum += (rev - cost)
        conv_cf.append(conv_cum)

    # AlmondLab CEA: Initial CapEx = -$75,000/ac.
    # Yield remains constant 2,800 lbs/ac. Water usage 0.65 AF/ac.
    cea_cf = []
    cea_cum = -75000
    for yr, wp, sal in zip(years, water_prices_ts, salinity_ts):
        yld = 2800 * np.clip(1.0 - max(0, (sal - 4.0) * 0.045), 0.85, 1.0)
        rev = yld * almond_price
        cost = (yld * 1.25) + (0.65 * wp) + (yld * 0.15)  # low labor, controlled nutrients
        cea_cum += (rev - cost)
        cea_cf.append(cea_cum)

    ax4.plot(years, np.array(conv_cf)/1000, label="Conventional Open Field Orchard (Megadrought Shock)", color=c_conv, lw=3)
    ax4.plot(years, np.array(cea_cf)/1000, label="AlmondLab Closed-Loop CEA (Protected High Density)", color=c_almondlab, lw=3.5)
    ax4.axhline(0, color="#94a3b8", ls="-", lw=1)

    # Payback point annotation
    idx_pb = np.argwhere(np.diff(np.sign(np.array(cea_cf)))).flatten()
    if len(idx_pb) > 0:
        pb_yr = years[idx_pb[0]] + 1
        ax4.plot(pb_yr, 0, "o", color=c_almondlab, markersize=8)
        ax4.annotate(
            f"AlmondLab Payback: Year {pb_yr}",
            xy=(pb_yr, 0),
            xytext=(pb_yr - 3, 20),
            arrowprops=dict(facecolor=c_almondlab, shrink=0.08, width=1.5, headwidth=6),
            fontweight="bold",
            fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.3", fc="#ecfdf5", ec="#a7f3d0", lw=1),
        )

    ax4.set_title("D. 20-Year Cumulative Cash Flow under Prolonged Megadrought", fontsize=13, fontweight="bold", pad=12, color="#0f172a")
    ax4.set_xlabel("Orchard / Facility Operating Year", fontsize=10.5, fontweight="600")
    ax4.set_ylabel("Cumulative Net Cash Flow ($1,000 / Acre)", fontsize=10.5, fontweight="600")
    ax4.set_xticks(range(2, 21, 2))
    ax4.grid(True)
    ax4.legend(loc="upper left", fontsize=8.5, framealpha=0.95)

    plt.suptitle(
        "Techno-Economic & Water Crisis Price Comparison: Conventional Open-Field vs. AlmondLab Closed-Loop CEA",
        fontsize=15,
        fontweight="bold",
        y=0.995,
        color="#0f172a",
    )
    plt.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight")
    fig.savefig(OUTPUT_JPG, dpi=300, bbox_inches="tight")
    print(f"Generated economic charts:\n - {OUTPUT_PNG}\n - {OUTPUT_JPG}")


if __name__ == "__main__":
    generate_charts()
