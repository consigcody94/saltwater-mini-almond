"""Conservative water blending and charge-based chemistry diagnostics."""

from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence

from pydantic import Field

from almondlab.contracts import DataOrigin, ECKind, EvidenceLabel
from almondlab.errors import fail
from almondlab.schemas import StrictScientificModel, WaterBatch, WaterChemistry


BLENDED_CONCENTRATION_FIELDS = (
    "alkalinity_mmol_c_l",
    "na_mmol_l",
    "cl_mmol_l",
    "ca_mmol_l",
    "mg_mmol_l",
    "k_mmol_l",
    "total_b_mmol_l",
    "sulfate_mmol_l",
    "bicarbonate_mmol_l",
    "nitrate_mmol_l",
    "phosphate_mmol_l",
)

_EVIDENCE_RANK = {
    EvidenceLabel.SYNTHETIC_ONLY: 0,
    EvidenceLabel.HYPOTHESIS_PRIOR: 1,
    EvidenceLabel.PHYSICS_CONSTRAINED: 2,
    EvidenceLabel.EMPIRICALLY_CALIBRATED: 3,
}


class BlendMeasurement(StrictScientificModel):
    """Validated observation/calibration contract for nonconservative fields."""

    measurement_id: str = Field(min_length=1)
    ec_kind: ECKind
    ec_ds_m: float = Field(ge=0)
    temperature_k: float = Field(ge=0)
    measured_osmolality_osmol_kg: float = Field(ge=0)
    ph: float
    data_origin: DataOrigin
    evidence_label: EvidenceLabel


@dataclass(frozen=True)
class BlendResult:
    """A blended chemistry record with retained input provenance."""

    chemistry: WaterChemistry
    total_volume_l: float
    data_origin: DataOrigin
    evidence_label: EvidenceLabel
    source_data_origins: tuple[DataOrigin, ...]
    source_evidence_labels: tuple[EvidenceLabel, ...]
    measurement_id: str
    measurement_data_origin: DataOrigin


def _finite_nonnegative(value: float, code: str, field_path: str) -> float:
    converted = float(value)
    if not isfinite(converted) or converted < 0.0:
        fail(code, "value must be finite and nonnegative", field_path)
    return converted


def blend_by_volume(
    sources: Sequence[WaterBatch],
    volumes_l: Sequence[float],
    *,
    measurement: BlendMeasurement | None = None,
) -> BlendResult:
    """Blend registered analytes mass-first without deriving or averaging EC.

    Every source is a ``WaterBatch`` so origin and evidence cannot be discarded.
    EC, pH, osmolality, and temperature enter through an explicit validated
    observation/calibration record rather than through an averaging shortcut.
    """
    if not sources:
        fail("BLEND_EMPTY", "at least one source is required", "sources")
    if len(sources) != len(volumes_l):
        fail(
            "BLEND_LENGTH_MISMATCH",
            "sources and volumes_l must have equal lengths",
            "volumes_l",
        )
    if any(not isinstance(source, WaterBatch) for source in sources):
        fail(
            "BLEND_PROVENANCE_REQUIRED",
            "each source must be a provenance-bearing WaterBatch",
            "sources",
        )

    volumes = tuple(
        _finite_nonnegative(volume, "BLEND_INVALID_VOLUME", f"volumes_l.{index}")
        for index, volume in enumerate(volumes_l)
    )
    total_volume = sum(volumes)
    if total_volume <= 0.0:
        fail(
            "BLEND_ZERO_VOLUME",
            "total blend volume must be positive",
            "volumes_l",
        )

    ec_kinds = {source.chemistry.ec_kind for source in sources}
    if len(ec_kinds) != 1:
        fail(
            "EC_TYPE_MISMATCH",
            "all blend sources must use one EC kind",
            "sources.chemistry.ec_kind",
        )
    source_ec_kind = next(iter(ec_kinds))
    if measurement is None:
        fail(
            "EC_MEASUREMENT_REQUIRED",
            "blend EC requires a validated measurement or calibration record",
            "measurement",
        )
    if measurement.ec_kind is not source_ec_kind:
        fail(
            "EC_TYPE_MISMATCH",
            "blend measurement EC kind must match every source",
            "measurement.ec_kind",
        )

    concentrations = {
        field: sum(
            volume * getattr(source.chemistry, field)
            for source, volume in zip(sources, volumes, strict=True)
        )
        / total_volume
        for field in BLENDED_CONCENTRATION_FIELDS
    }
    chemistry = WaterChemistry(
        ec_kind=measurement.ec_kind,
        ec_ds_m=measurement.ec_ds_m,
        temperature_k=measurement.temperature_k,
        measured_osmolality_osmol_kg=measurement.measured_osmolality_osmol_kg,
        ph=measurement.ph,
        **concentrations,
    )

    source_origins = tuple(source.data_origin for source in sources)
    source_labels = tuple(source.evidence_label for source in sources)
    weakest_label = min(
        (*source_labels, measurement.evidence_label),
        key=_EVIDENCE_RANK.__getitem__,
    )
    return BlendResult(
        chemistry=chemistry,
        total_volume_l=total_volume,
        data_origin=DataOrigin.MODEL_DERIVED,
        evidence_label=weakest_label,
        source_data_origins=source_origins,
        source_evidence_labels=source_labels,
        measurement_id=measurement.measurement_id,
        measurement_data_origin=measurement.data_origin,
    )


def sodium_adsorption_ratio(
    na_mmol_c_l: float,
    ca_mmol_c_l: float,
    mg_mmol_c_l: float,
) -> float:
    """Return SAR from charge concentrations, all expressed in mmol_c/L."""
    values = (na_mmol_c_l, ca_mmol_c_l, mg_mmol_c_l)
    if any(not isfinite(float(value)) or value < 0.0 for value in values):
        fail(
            "SAR_INVALID_CONCENTRATION",
            "SAR inputs must be finite nonnegative charge concentrations",
            "water.sar_inputs_mmol_c_l",
        )
    denominator = ((ca_mmol_c_l + mg_mmol_c_l) / 2.0) ** 0.5
    if denominator <= 0.0:
        fail(
            "SAR_ZERO_DENOMINATOR",
            "Ca + Mg must be positive",
            "water.ca_mg",
        )
    return na_mmol_c_l / denominator


def sodium_adsorption_ratio_for_water(water: WaterChemistry) -> float:
    """Return SAR after explicitly converting molar Ca/Mg to charge units."""
    return sodium_adsorption_ratio(
        na_mmol_c_l=water.na_mmol_l,
        ca_mmol_c_l=2.0 * water.ca_mmol_l,
        mg_mmol_c_l=2.0 * water.mg_mmol_l,
    )


def charge_balance_error(water: WaterChemistry) -> float:
    """Return signed charge-balance error in percent using explicit valences."""
    cations_mmol_c_l = (
        water.na_mmol_l
        + water.k_mmol_l
        + 2.0 * water.ca_mmol_l
        + 2.0 * water.mg_mmol_l
    )
    anions_mmol_c_l = (
        water.cl_mmol_l
        + 2.0 * water.sulfate_mmol_l
        + water.alkalinity_mmol_c_l
        + water.nitrate_mmol_l
    )
    total_charge = cations_mmol_c_l + anions_mmol_c_l
    if total_charge <= 0.0:
        fail(
            "CHARGE_BALANCE_ZERO_TOTAL",
            "total ionic charge must be positive",
            "water.ionic_charge",
        )
    return 100.0 * (cations_mmol_c_l - anions_mmol_c_l) / total_charge
