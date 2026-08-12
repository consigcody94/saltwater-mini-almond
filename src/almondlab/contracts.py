"""Stable public vocabulary for AlmondLab artifacts and model gates."""

from enum import StrEnum


class EvidenceLabel(StrEnum):
    PHYSICS_CONSTRAINED = "physics_constrained"
    EMPIRICALLY_CALIBRATED = "empirically_calibrated"
    HYPOTHESIS_PRIOR = "hypothesis_prior"
    SYNTHETIC_ONLY = "synthetic_only"


class DataOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    EMPIRICAL = "empirical"
    LITERATURE_DERIVED = "literature_derived"
    MODEL_DERIVED = "model_derived"


class ECKind(StrEnum):
    ECW = "ECw"
    PORE_WATER = "pore_water_EC"
    ECE = "ECe"


class ConservedEntity(StrEnum):
    WATER = "water"
    NA = "na"
    CL = "cl"
    CA = "ca"
    MG = "mg"
    K = "k"
    TOTAL_B = "total_b"
    N = "n"
    P = "p"
    S = "s"
    DIC = "dissolved_inorganic_carbon"
    ALKALINITY = "alkalinity"


class GateState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
