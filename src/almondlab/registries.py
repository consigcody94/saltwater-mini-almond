"""Strict evidence, candidate, and reference-chemistry registries.

Registry files are publication inputs, not permissive spreadsheets.  This
module therefore reads them with an exact schema, rejects ambiguous CSV, keeps
unknown values explicit, and cross-checks the six primary candidate identities
against the independently frozen Paper 1 configuration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from math import isclose
from numbers import Real
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit, urlunsplit
import csv
import hashlib
import re

import pandas as pd

from almondlab.errors import AlmondLabError, fail, finite_float


EVIDENCE_COLUMNS: Final[tuple[str, ...]] = (
    "evidence_id",
    "title",
    "doi",
    "primary_url",
    "donor_or_organism",
    "life_stage",
    "salinity_chemistry",
    "salinity_concentration",
    "ec_context",
    "exposure_duration",
    "experimental_unit",
    "sample_size",
    "endpoint",
    "reported_effect",
    "effect_units_context",
    "limitation",
    "evidence_tier",
    "retrieval_date",
    "source_sha256",
    "source_sha256_status",
    "source_reference_identity",
    "metadata_basis",
    "program_assumptions",
)

CANDIDATE_COLUMNS: Final[tuple[str, ...]] = (
    "candidate_id",
    "registry_class",
    "construct_name",
    "donor_species",
    "sequence_id",
    "sequence_accessions",
    "reference_sequence_ids",
    "sequence_status",
    "sequence_readiness",
    "sequence_unresolved_reason",
    "target_tissue",
    "target_tissue_basis",
    "mechanism",
    "evidence_tier",
    "registered_expression_class",
    "primary_parameter_id",
    "h3_endpoint",
    "h3_unit",
    "h3_scale",
    "h3_direction",
    "h3_margin",
    "h3_min_probability",
    "gates",
    "principal_failure_mode",
    "prequalification_requirement",
    "evidence_ids",
    "evidence_label",
    "program_status",
)

REFERENCE_CHEMISTRY_COLUMNS: Final[tuple[str, ...]] = (
    "chemistry_id",
    "evidence_id",
    "source_type",
    "evidence_label",
    "metadata_basis",
    "ec_kind",
    "ec_ds_m",
    "temperature_c",
    "ion_unit",
    "na_meq_l",
    "k_meq_l",
    "phosphate_meq_l",
    "mg_meq_l",
    "ca_meq_l",
    "sulfate_meq_l",
    "cl_meq_l",
    "nitrate_meq_l",
    "reported_missing_fields",
    "composition_basis",
    "limitation",
)

_PRIMARY_CANDIDATE_IDS: Final[tuple[str, ...]] = tuple(
    f"C{number}" for number in range(1, 7)
)
_PREQUALIFICATION_CANDIDATE_IDS: Final[frozenset[str]] = frozenset(
    {
        "PQ_PYMNSOD",
        "PQ_KANAH",
        "PQ_ESI0017_0056",
        "PQ_PPSOS1",
        "PQ_PPSOS3",
        "PQ_PPCBL10",
        "PQ_PPAKT1",
        "PQ_PPKUP8_LIKE",
        "PQ_ANO10_LIKE",
        "PQ_MSL10_LIKE",
        "PQ_KCS1_LIKE",
        "PQ_NHX1_2",
        "PQ_PPPIP1_2",
        "PQ_PAVNHX37",
    }
)
_REQUIRED_UNRESOLVED: Final[frozenset[str]] = frozenset(
    {"PQ_KCS1_LIKE", "PQ_NHX1_2", "PQ_PAVNHX37"}
)
_PRIMARY_SEQUENCE_IDS: Final[dict[str, str]] = {
    "C1": "AJ972674.1",
    "C2": "AY282755.1",
    "C3": "Esi0017_0062|Esi0100_0020",
    "C4": "EU879059.1",
    "C5": "Prupe.1G067100",
    "C6": "Prupe.7G244500.1",
}
_SECTION_16_IDENTITIES: Final[tuple[tuple[str, str], ...]] = (
    ("EV_ROOTSTOCK_SCREEN_2020", "doi:10.1038/s41598-020-78036-4"),
    ("EV_ROOT_GRADIENT_2021", "doi:10.3389/fpls.2020.595055"),
    ("EV_ROOTPAC40_TRANSCRIPTOME_2022", "doi:10.1038/s41598-022-05202-1"),
    ("EV_PRUNUS_SOS_MAP_2024", "doi:10.1002/tpg2.20371"),
    ("EV_ALMOND_HAIRY_ROOT_2024", "doi:10.1007/s11240-024-02935-x"),
    ("EV_ALMOND_STABLE_TRANSFORM_1999", "doi:10.1007/s002990050591"),
    ("EV_ECTOCARPUS_MANNITOL_2020", "doi:10.3390/plants9111508"),
    ("EV_ECTOCARPUS_ESI0056_2021", "doi:10.3390/ijms22041971"),
    ("EV_PYKPA1_2013", "doi:10.5511/plantbiotechnology.13.0517a"),
    ("EV_PYAPX_2026", "doi:10.1016/j.plaphy.2025.110839"),
    ("EV_SBSOS1_2012", "doi:10.1186/1471-2229-12-188"),
    ("EV_PPHKT1_2019", "doi:10.1371/journal.pone.0214473"),
    ("EV_PPSOS2_2022", "doi:10.1021/acsagscitech.1c00276"),
    ("EV_KANAH_2022", "doi:10.1007/s11033-022-07213-7"),
    ("EV_PAVNHX37_2026", "doi:10.1186/s12870-026-09156-8"),
    ("EV_CROP_NA_TRANSPORT_REVIEW_2020", "doi:10.1111/pce.13865"),
    ("EV_INTENSIA_2024", "doi:10.21273/HORTSCI18021-24"),
    ("EV_ALMOND_CHILLING_2020", "doi:10.3390/agronomy10020277"),
    ("EV_ALMOND_SEAWEED_2026", "doi:10.1016/j.stress.2026.101307"),
    (
        "EV_ALMOND_SALINITY_GUIDE_2024",
        "url:https://www.almonds.org/sites/default/files/2024-02/"
        "Salinity%20Management%20Guide%20for%20Almond%20Growers.pdf",
    ),
    (
        "EV_CA_OCEAN_DESALINATION",
        "url:https://www.waterboards.ca.gov/water_issues/programs/ocean/"
        "desalination/",
    ),
    (
        "EV_USDA_APHIS_SECURE",
        "url:https://www.aphis.usda.gov/biotechnology/regulations/secure-rule",
    ),
    (
        "EV_SCIENTIFIC_REPORTS_RR_POLICY",
        "url:https://www.nature.com/srep/journal-policies/registered-reports",
    ),
    (
        "EV_ROYAL_SOCIETY_OPEN_SCIENCE_POLICY",
        "url:https://royalsociety.org/journals/open-access/open-science/",
    ),
)
_CANDIDATE_SEQUENCE_IDENTITIES: Final[
    dict[str, tuple[str, str, str, str, str, str]]
] = {
    "C1": (
        "AJ972674.1",
        "AJ972674.1|CAI99405.1",
        "AJ972674.1|CAI99405.1",
        "accession_verified",
        "accession_verified_final_construct_unverified",
        "E2",
    ),
    "C2": (
        "AY282755.1",
        "AY282755.1",
        "AY282755.1",
        "accession_verified",
        "accession_verified_construct_map_unresolved",
        "E2",
    ),
    "C3": (
        "Esi0017_0062|Esi0100_0020",
        "Esi0017_0062|Esi0100_0020",
        "GCA_000310025.1",
        "crosswalk_pending",
        "crosswalk_required",
        "E2",
    ),
    "C4": (
        "EU879059.1",
        "EU879059.1|ACJ63441.1",
        "EU879059.1|ACJ63441.1",
        "accession_verified",
        "accession_verified_final_construct_unverified",
        "E2",
    ),
    "C5": (
        "Prupe.1G067100",
        "Prupe.1G067100",
        "XM_020565174.1|XP_020420763.1|XM_020564808.1|XP_020420397.1",
        "verified",
        "reference_locus_not_experimental_clone",
        "E1",
    ),
    "C6": (
        "Prupe.7G244500.1",
        "Prupe.7G244500.1|XP_020424233.1",
        "XM_020568644.1|XP_020424233.1|XM_007201987.2|XP_007202049.1",
        "verified",
        "reference_locus_not_experimental_clone",
        "E1",
    ),
    "PQ_PYMNSOD": (
        "DQ146477.2",
        "DQ146477.2",
        "DQ146477.2",
        "accession_verified",
        "accession_verified_construct_map_unresolved",
        "E5/E3",
    ),
    "PQ_KANAH": (
        "MT473962.1",
        "MT473962.1",
        "MT473962.1",
        "accession_verified_partial_cds",
        "partial_accession_construct_map_unresolved",
        "E3",
    ),
    "PQ_ESI0017_0056": (
        "Esi0017_0056",
        "Esi0017_0056",
        "GCA_000310025.1",
        "reference_locus_only",
        "crosswalk_and_mechanism_required",
        "E3",
    ),
    "PQ_PPSOS1": (
        "Prupe.1G339200.1",
        "Prupe.1G339200.1",
        "not_applicable",
        "reference_locus_only",
        "functional_direction_unresolved",
        "E4",
    ),
    "PQ_PPSOS3": (
        "Prupe.2G310300.1",
        "Prupe.2G310300.1",
        "not_applicable",
        "reference_locus_only",
        "functional_complex_unresolved",
        "E4",
    ),
    "PQ_PPCBL10": (
        "Prupe.1G412900",
        "Prupe.1G412900",
        "not_applicable",
        "reference_locus_only",
        "interaction_and_function_unresolved",
        "E4",
    ),
    "PQ_PPAKT1": (
        "Prupe.1G472600",
        "Prupe.1G472600",
        "not_applicable",
        "reference_locus_only",
        "transport_function_unresolved",
        "E4",
    ),
    "PQ_PPKUP8_LIKE": (
        "Prupe.5G236500",
        "Prupe.5G236500",
        "not_applicable",
        "reference_locus_only",
        "transport_function_unresolved",
        "E4",
    ),
    "PQ_ANO10_LIKE": (
        "Prupe.3G053200",
        "Prupe.3G053200",
        "not_applicable",
        "reference_locus_only",
        "transport_function_unresolved",
        "E4",
    ),
    "PQ_MSL10_LIKE": (
        "Prupe.7G202700",
        "Prupe.7G202700",
        "not_applicable",
        "reference_locus_only",
        "transport_function_unresolved",
        "E4",
    ),
    "PQ_KCS1_LIKE": (
        "unresolved",
        "unresolved",
        "unresolved",
        "unresolved",
        "blocked_unresolved",
        "E4",
    ),
    "PQ_NHX1_2": (
        "unresolved",
        "unresolved",
        "unresolved",
        "unresolved",
        "paralog_and_compartment_unresolved",
        "E4",
    ),
    "PQ_PPPIP1_2": (
        "Prupe.5G101400",
        "Prupe.5G101400",
        "not_applicable",
        "reference_locus_only",
        "hydraulic_function_unresolved",
        "E4",
    ),
    "PQ_PAVNHX37": (
        "unresolved",
        "unresolved",
        "unresolved",
        "unresolved",
        "blocked_unresolved",
        "E3",
    ),
}
_SEQUENCE_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "accession_verified",
        "accession_verified_partial_cds",
        "crosswalk_pending",
        "verified",
        "pending_audit",
        "reference_locus_only",
        "unresolved",
    }
)
_SEQUENCE_READINESS: Final[frozenset[str]] = frozenset(
    {
        "accession_verified_final_construct_unverified",
        "accession_verified_construct_map_unresolved",
        "blocked_unresolved",
        "crosswalk_and_mechanism_required",
        "crosswalk_required",
        "functional_complex_unresolved",
        "functional_direction_unresolved",
        "hydraulic_function_unresolved",
        "interaction_and_function_unresolved",
        "paralog_and_compartment_unresolved",
        "partial_accession_construct_map_unresolved",
        "reference_locus_not_experimental_clone",
        "transport_function_unresolved",
    }
)
_REFERENCE_CHEMISTRY_IDS: Final[tuple[str, ...]] = (
    "ROOTSTOCK_T1_CONTROL",
    "ROOTSTOCK_T2_NA_SO4",
    "ROOTSTOCK_T3_NA_CL",
    "ROOTSTOCK_T4_NA_CL_SO4",
    "ROOTSTOCK_T5_CA_MG_CL_SO4",
)
_EVIDENCE_ID = re.compile(r"^EV_[A-Z0-9]+(?:_[A-Z0-9]+)*$")
_CANDIDATE_ID = re.compile(r"^(?:C[1-6]|PQ_[A-Z0-9]+(?:_[A-Z0-9]+)*)$")
_CHEMISTRY_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
_PORTABLE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/-]*$")
_DOI = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPLICIT_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "not_applicable",
        "not_reported",
        "unresolved",
        "not_evaluable",
        "none",
    }
)
_EVIDENCE_TIERS: Final[frozenset[str]] = frozenset(
    {"E1", "E2", "E3", "E4", "E5", "E5/E3", "NA_NON_CANDIDATE"}
)
_NUMERIC_CHEMISTRY_COLUMNS: Final[tuple[str, ...]] = (
    "ec_ds_m",
    "temperature_c",
    "na_meq_l",
    "k_meq_l",
    "phosphate_meq_l",
    "mg_meq_l",
    "ca_meq_l",
    "sulfate_meq_l",
    "cl_meq_l",
    "nitrate_meq_l",
)
_REFERENCE_CHEMISTRY_EVIDENCE_ID: Final[str] = "EV_ROOTSTOCK_SCREEN_2020"
_REFERENCE_MISSING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "temperature_c",
        "ca_meq_l",
        "boron",
        "alkalinity",
        "bicarbonate",
        "ph",
    }
)
_DEFAULT_CANDIDATE_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "candidates.yaml"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSIGNED_DECIMAL = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_SIGNED_DECIMAL = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")

# These are independent, code-owned seals for the three separately reviewed
# publication inputs.  They are intentionally literal rather than derived at
# import time: a syntactically valid edit must not authorize itself.
_AUDITED_EVIDENCE_REGISTRY_SHA256: Final[str] = (
    "3296138c408220c9b5919cc5f1126bc18e1def9c5dd72ff0188d1c5ce8159bb8"
)
_AUDITED_CANDIDATE_REGISTRY_SHA256: Final[str] = (
    "8e95c90ee9d85180a0b2dee7ef71ae8471b9784da1bafd52bf4d0d9aa044d0ae"
)
_AUDITED_REFERENCE_CHEMISTRY_SHA256: Final[str] = (
    "262a3b3210181d73bac416a6c0e09151de397fc8cc3752692a88d296a75f430a"
)


def _coerce_path(value: str | Path, field_path: str) -> Path:
    if isinstance(value, bool) or not isinstance(value, (str, Path)):
        fail("CSV_PATH_INVALID", "path must be a string or Path", field_path)
    path = Path(value)
    if not path.is_file():
        fail("CSV_FILE_UNREADABLE", "registry CSV does not exist", field_path)
    return path


def _read_strict_csv(
    value: str | Path, expected_columns: tuple[str, ...], registry_name: str
) -> tuple[list[dict[str, str]], str]:
    path = _coerce_path(value, registry_name)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AlmondLabError(
            "CSV_FILE_UNREADABLE", "registry CSV could not be read", registry_name
        ) from exc
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AlmondLabError(
            "CSV_ENCODING_INVALID", "registry CSV must be strict UTF-8", registry_name
        ) from exc
    if text.startswith("\ufeff"):
        fail(
            "CSV_ENCODING_INVALID",
            "registry CSV must not contain a UTF-8 BOM",
            registry_name,
        )
    if "\r" in text:
        fail(
            "CSV_LINE_ENDING_INVALID",
            "registry CSV must use LF line endings",
            registry_name,
        )
    if not text or not text.endswith("\n"):
        fail(
            "CSV_LINE_ENDING_INVALID",
            "registry CSV must be nonempty and end with LF",
            registry_name,
        )
    try:
        parsed = list(csv.reader(StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise AlmondLabError(
            "CSV_MALFORMED", "registry CSV is syntactically malformed", registry_name
        ) from exc
    if not parsed:
        fail("CSV_EMPTY", "registry CSV is empty", registry_name)
    header = parsed[0]
    if len(header) != len(set(header)):
        fail(
            "CSV_HEADER_DUPLICATE",
            "registry CSV contains a duplicate header",
            f"{registry_name}.header",
        )
    if tuple(header) != expected_columns:
        fail(
            "CSV_SCHEMA_MISMATCH",
            "registry CSV header does not match the exact schema",
            f"{registry_name}.header",
            {"expected": list(expected_columns), "received": header},
        )
    rows: list[dict[str, str]] = []
    raw_rows: set[tuple[str, ...]] = set()
    for line_number, raw_row in enumerate(parsed[1:], start=2):
        if len(raw_row) != len(expected_columns):
            fail(
                "CSV_ROW_WIDTH_INVALID",
                "registry CSV row width differs from its header",
                f"{registry_name}.line[{line_number}]",
            )
        if not raw_row or all(value == "" for value in raw_row):
            fail(
                "CSV_BLANK_ROW_INVALID",
                "registry CSV cannot contain blank rows",
                f"{registry_name}.line[{line_number}]",
            )
        frozen = tuple(raw_row)
        if frozen in raw_rows:
            fail(
                "CSV_ROW_DUPLICATE",
                "registry CSV contains a duplicate row",
                f"{registry_name}.line[{line_number}]",
            )
        raw_rows.add(frozen)
        for column, cell in zip(expected_columns, raw_row):
            if cell != cell.strip() or any(ord(char) < 32 for char in cell):
                fail(
                    "CSV_CELL_INVALID",
                    "registry cells cannot contain surrounding whitespace or control characters",
                    f"{registry_name}.line[{line_number}].{column}",
                )
        rows.append(dict(zip(expected_columns, raw_row)))
    if not rows:
        fail("CSV_EMPTY", "registry CSV has no data rows", registry_name)
    return rows, hashlib.sha256(payload).hexdigest()


def _require_audited_registry_hash(
    actual: str,
    expected: str,
    *,
    code: str,
    registry_name: str,
) -> None:
    if actual != expected:
        fail(
            code,
            "registry content differs from the independently reviewed publication input",
            registry_name,
            {"expected_sha256": expected, "received_sha256": actual},
        )


def _require_explicit_text(row: Mapping[str, str], columns: Sequence[str], row_path: str) -> None:
    for column in columns:
        value = row[column]
        if not isinstance(value, str) or not value:
            code = (
                "REGISTRY_LIMITATION_REQUIRED"
                if column == "limitation"
                else "REGISTRY_FIELD_REQUIRED"
            )
            fail(code, f"{column} must be explicit and nonblank", f"{row_path}.{column}")


def _normal_url(value: str, field_path: str) -> str:
    if not isinstance(value, str):
        fail("REGISTRY_URL_INVALID", "URL must be a string", field_path)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        fail(
            "REGISTRY_URL_INVALID",
            "primary URL must be an absolute HTTPS URL without credentials",
            field_path,
        )
    if parsed.fragment:
        fail("REGISTRY_URL_INVALID", "primary URL cannot contain a fragment", field_path)
    path = parsed.path or "/"
    normalized_path = path if path == "/" else path.rstrip("/")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), normalized_path, parsed.query, "")
    )


def _parse_pipe_list(
    value: object,
    *,
    field_path: str,
    item_pattern: re.Pattern[str],
    marker_allowed: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        fail(
            "REGISTRY_EVIDENCE_LINK_INVALID",
            "list fields must be nonempty strings",
            field_path,
        )
    if marker_allowed and value in _EXPLICIT_MARKERS:
        return ()
    tokens = value.split("|")
    if (
        any(not token or token != token.strip() for token in tokens)
        or len(tokens) != len(set(tokens))
        or any(item_pattern.fullmatch(token) is None for token in tokens)
        or "|".join(tokens) != value
    ):
        fail(
            "REGISTRY_EVIDENCE_LINK_INVALID",
            "list fields must use unique canonical pipe-delimited tokens",
            field_path,
        )
    return tuple(tokens)


def _strict_csv_float(value: str, field_path: str) -> float:
    if (
        not isinstance(value, str)
        or not value
        or _UNSIGNED_DECIMAL.fullmatch(value) is None
    ):
        fail(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "numeric CSV value must be an explicit finite decimal",
            field_path,
        )
    try:
        decimal = Decimal(value)
    except InvalidOperation as exc:
        raise AlmondLabError(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "numeric CSV value must be an explicit finite decimal",
            field_path,
        ) from exc
    if not decimal.is_finite():
        fail(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "numeric CSV value must be finite",
            field_path,
        )
    if value != _canonical_decimal_text(decimal):
        fail(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "numeric CSV value must have one canonical decimal spelling",
            field_path,
        )
    try:
        converted = float(decimal)
    except (OverflowError, ValueError) as exc:
        raise AlmondLabError(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "numeric CSV value is outside the supported finite range",
            field_path,
        ) from exc
    if converted < 0.0:
        fail(
            "REFERENCE_CHEMISTRY_NUMBER_INVALID",
            "chemistry values must be nonnegative",
            field_path,
        )
    return converted


def _canonical_decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def load_evidence_registry(path: str | Path) -> pd.DataFrame:
    """Load and validate the complete §16 evidence registry."""
    rows, payload_sha256 = _read_strict_csv(
        path, EVIDENCE_COLUMNS, "evidence_registry"
    )
    evidence_ids: set[str] = set()
    dois: set[str] = set()
    urls: set[str] = set()
    for index, row in enumerate(rows):
        row_path = f"evidence_registry[{index}]"
        _require_explicit_text(row, EVIDENCE_COLUMNS, row_path)
        evidence_id = row["evidence_id"]
        if _EVIDENCE_ID.fullmatch(evidence_id) is None:
            fail(
                "REGISTRY_ID_INVALID",
                "evidence_id must be a safe portable EV_ identifier",
                f"{row_path}.evidence_id",
            )
        if evidence_id in evidence_ids:
            fail(
                "REGISTRY_ID_DUPLICATE",
                "evidence_id values must be unique",
                f"{row_path}.evidence_id",
            )
        evidence_ids.add(evidence_id)

        doi = row["doi"]
        if doi != "not_applicable":
            if _DOI.fullmatch(doi) is None:
                fail("REGISTRY_DOI_INVALID", "DOI is not canonical", f"{row_path}.doi")
            normalized_doi = doi.casefold()
            if normalized_doi in dois:
                fail(
                    "REGISTRY_DOI_DUPLICATE",
                    "DOI values must be unique",
                    f"{row_path}.doi",
                )
            dois.add(normalized_doi)
        if doi == "not_applicable" and row["primary_url"] in _EXPLICIT_MARKERS:
            fail(
                "REGISTRY_SOURCE_LINK_REQUIRED",
                "every evidence row requires a DOI or primary HTTPS URL",
                row_path,
            )
        normalized_url = _normal_url(row["primary_url"], f"{row_path}.primary_url")
        if normalized_url in urls:
            fail(
                "REGISTRY_URL_DUPLICATE",
                "primary source URLs must be unique",
                f"{row_path}.primary_url",
            )
        urls.add(normalized_url)
        expected_identity = (
            f"doi:{doi}" if doi != "not_applicable" else f"url:{row['primary_url']}"
        )
        if row["source_reference_identity"] != expected_identity:
            fail(
                "REGISTRY_SOURCE_IDENTITY_INVALID",
                "source_reference_identity must exactly anchor the DOI or primary URL",
                f"{row_path}.source_reference_identity",
            )
        if row["evidence_tier"] not in _EVIDENCE_TIERS:
            fail(
                "REGISTRY_EVIDENCE_TIER_INVALID",
                "evidence tier is not registered",
                f"{row_path}.evidence_tier",
            )
        try:
            if _ISO_DATE.fullmatch(row["retrieval_date"]) is None:
                raise ValueError("noncanonical ISO date")
            date.fromisoformat(row["retrieval_date"])
        except ValueError as exc:
            raise AlmondLabError(
                "REGISTRY_DATE_INVALID",
                "retrieval_date must be ISO YYYY-MM-DD",
                f"{row_path}.retrieval_date",
            ) from exc
        hash_status = row["source_sha256_status"]
        if hash_status not in {"verified_local_payload", "primary_source_not_archived"}:
            fail(
                "REGISTRY_SOURCE_HASH_INVALID",
                "source SHA status is not registered",
                f"{row_path}.source_sha256_status",
            )
        if hash_status == "verified_local_payload":
            valid_hash = _SHA256.fullmatch(row["source_sha256"]) is not None
        else:
            valid_hash = row["source_sha256"] == "not_available"
        if not valid_hash:
            fail(
                "REGISTRY_SOURCE_HASH_INVALID",
                "source SHA and status are inconsistent",
                f"{row_path}.source_sha256",
            )
        if row["metadata_basis"] not in {
            "source_reported",
            "official_source",
            "mixed_source_reported_and_program_assumption",
        }:
            fail(
                "REGISTRY_METADATA_BASIS_INVALID",
                "metadata_basis is not registered",
                f"{row_path}.metadata_basis",
            )
    received_identities = tuple(
        (row["evidence_id"], row["source_reference_identity"]) for row in rows
    )
    if received_identities != _SECTION_16_IDENTITIES:
        fail(
            "EVIDENCE_REGISTRY_INCOMPLETE",
            "evidence registry must retain every audited Section 16 source identity in order",
            "evidence_registry.source_reference_identity",
            {
                "expected": [list(item) for item in _SECTION_16_IDENTITIES],
                "received": [list(item) for item in received_identities],
            },
        )
    _require_audited_registry_hash(
        payload_sha256,
        _AUDITED_EVIDENCE_REGISTRY_SHA256,
        code="EVIDENCE_REGISTRY_CONTENT_MISMATCH",
        registry_name="evidence_registry",
    )
    table = pd.DataFrame.from_records(rows, columns=EVIDENCE_COLUMNS).astype("string")
    table.attrs.clear()
    return table


def _default_candidate_config_path() -> Path:
    if not _DEFAULT_CANDIDATE_CONFIG.is_file():
        fail(
            "CANDIDATE_CONFIG_MISSING",
            "frozen candidate identity configuration is unavailable",
            "candidate_config_path",
        )
    return _DEFAULT_CANDIDATE_CONFIG


def _cross_check_frozen_candidates(
    table: pd.DataFrame, candidate_config_path: str | Path | None
) -> None:
    if candidate_config_path is None:
        config_path = _default_candidate_config_path()
    else:
        config_path = _coerce_path(candidate_config_path, "candidate_config_path")
    # Imported lazily to avoid making registry parsing depend on the biological
    # simulator at module import time.
    from almondlab.paper1_contracts import load_candidate_specs

    frozen = load_candidate_specs(config_path)
    primary = table.loc[table["registry_class"] == "primary"].set_index("candidate_id")
    if tuple(primary.index) != _PRIMARY_CANDIDATE_IDS:
        fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "primary candidate rows must be C1 through C6 in order",
            "candidate_registry.candidate_id",
        )
    frozen_ids = tuple(candidate.candidate_id for candidate in frozen.candidates)
    if frozen_ids != _PRIMARY_CANDIDATE_IDS:
        fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "frozen candidate configuration must contain C1 through C6 in order",
            "candidate_config.candidate_id",
            {"received": list(frozen_ids)},
        )
    for candidate in frozen.candidates:
        row = primary.loc[candidate.candidate_id]
        configured_sequences = _parse_pipe_list(
            row["sequence_accessions"],
            field_path=f"candidate_registry.{candidate.candidate_id}.sequence_accessions",
            item_pattern=_PORTABLE_TOKEN,
            marker_allowed=True,
        )
        gates = tuple(
            f"{name}={state}" for name, state in sorted(candidate.gates.items())
        )
        expected = {
            "sequence_id": _PRIMARY_SEQUENCE_IDS[candidate.candidate_id],
            "construct_name": candidate.construct_name,
            "donor_species": candidate.donor_species,
            "sequence_accessions": candidate.sequence_accessions,
            "sequence_status": candidate.sequence_status,
            "evidence_tier": candidate.evidence_tier,
            "evidence_label": candidate.evidence_label.value,
            "primary_parameter_id": candidate.primary_parameter_id,
            "h3_endpoint": candidate.h3_rule.endpoint,
            "h3_unit": candidate.h3_rule.unit,
            "h3_scale": candidate.h3_rule.scale,
            "h3_direction": candidate.h3_rule.direction,
            "gates": gates,
            "principal_failure_mode": candidate.risk_warning,
        }
        actual = {
            "sequence_id": row["sequence_id"],
            "construct_name": row["construct_name"],
            "donor_species": row["donor_species"],
            "sequence_accessions": configured_sequences,
            "sequence_status": row["sequence_status"],
            "evidence_tier": row["evidence_tier"],
            "evidence_label": row["evidence_label"],
            "primary_parameter_id": row["primary_parameter_id"],
            "h3_endpoint": row["h3_endpoint"],
            "h3_unit": row["h3_unit"],
            "h3_scale": row["h3_scale"],
            "h3_direction": row["h3_direction"],
            "gates": tuple(row["gates"].split("|")),
            "principal_failure_mode": row["principal_failure_mode"],
        }
        mismatches = [name for name, value in actual.items() if value != expected[name]]
        try:
            h3_margin = float(Decimal(row["h3_margin"]))
            h3_probability = float(Decimal(row["h3_min_probability"]))
        except (InvalidOperation, ValueError, OverflowError):
            mismatches.extend(["h3_margin", "h3_min_probability"])
        else:
            if not isclose(
                h3_margin, candidate.h3_rule.margin, rel_tol=0.0, abs_tol=1e-12
            ):
                mismatches.append("h3_margin")
            if not isclose(
                h3_probability,
                candidate.h3_rule.min_probability,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                mismatches.append("h3_min_probability")
        if mismatches:
            fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "candidate registry differs from the frozen Paper 1 identity",
                f"candidate_registry.{candidate.candidate_id}",
                {"fields": sorted(set(mismatches))},
            )


def load_candidate_registry(
    path: str | Path,
    *,
    candidate_config_path: str | Path | None = None,
) -> pd.DataFrame:
    """Load all primary/prequalification candidates and fail on identity drift."""
    rows, payload_sha256 = _read_strict_csv(
        path, CANDIDATE_COLUMNS, "candidate_registry"
    )
    ids: list[str] = []
    for index, row in enumerate(rows):
        row_path = f"candidate_registry[{index}]"
        _require_explicit_text(row, CANDIDATE_COLUMNS, row_path)
        candidate_id = row["candidate_id"]
        if _CANDIDATE_ID.fullmatch(candidate_id) is None:
            fail(
                "REGISTRY_ID_INVALID",
                "candidate_id must be a safe C1-C6 or PQ_ identifier",
                f"{row_path}.candidate_id",
            )
        if candidate_id in ids:
            fail(
                "REGISTRY_ID_DUPLICATE",
                "candidate_id values must be unique",
                f"{row_path}.candidate_id",
            )
        ids.append(candidate_id)
        expected_class = "primary" if candidate_id in _PRIMARY_CANDIDATE_IDS else "prequalification"
        if row["registry_class"] != expected_class:
            fail(
                "CANDIDATE_CLASS_INVALID",
                "candidate registry class does not match its ID namespace",
                f"{row_path}.registry_class",
            )
        _parse_pipe_list(
            row["sequence_id"],
            field_path=f"{row_path}.sequence_id",
            item_pattern=_PORTABLE_TOKEN,
            marker_allowed=True,
        )
        _parse_pipe_list(
            row["sequence_accessions"],
            field_path=f"{row_path}.sequence_accessions",
            item_pattern=_PORTABLE_TOKEN,
            marker_allowed=True,
        )
        _parse_pipe_list(
            row["reference_sequence_ids"],
            field_path=f"{row_path}.reference_sequence_ids",
            item_pattern=_PORTABLE_TOKEN,
            marker_allowed=True,
        )
        _parse_pipe_list(
            row["evidence_ids"],
            field_path=f"{row_path}.evidence_ids",
            item_pattern=_EVIDENCE_ID,
        )
        if row["sequence_status"] not in _SEQUENCE_STATUSES:
            fail(
                "CANDIDATE_SEQUENCE_STATUS_INVALID",
                "sequence_status is not registered",
                f"{row_path}.sequence_status",
            )
        if row["sequence_readiness"] not in _SEQUENCE_READINESS:
            fail(
                "CANDIDATE_SEQUENCE_STATUS_INVALID",
                "sequence_readiness is not registered",
                f"{row_path}.sequence_readiness",
            )
        if row["target_tissue_basis"] not in {"program_assumption", "unresolved"}:
            fail(
                "CANDIDATE_TARGET_TISSUE_INVALID",
                "target_tissue_basis must distinguish assumptions from unresolved targeting",
                f"{row_path}.target_tissue_basis",
            )
        if row["evidence_tier"] not in _EVIDENCE_TIERS - {"NA_NON_CANDIDATE"}:
            fail(
                "REGISTRY_EVIDENCE_TIER_INVALID",
                "candidate evidence tier is not registered",
                f"{row_path}.evidence_tier",
            )
        if row["evidence_label"] != "hypothesis_prior":
            fail(
                "CANDIDATE_EVIDENCE_LABEL_INVALID",
                "all untested candidate records must remain hypothesis_prior",
                f"{row_path}.evidence_label",
            )
        if candidate_id in _REQUIRED_UNRESOLVED:
            if (
                any(
                    row[field] != "unresolved"
                    for field in (
                        "sequence_id",
                        "sequence_accessions",
                        "reference_sequence_ids",
                    )
                )
                or row["sequence_status"] not in {"pending_audit", "unresolved"}
                or "unresolved" not in row["sequence_readiness"]
                or "unresolved" not in row["sequence_unresolved_reason"].casefold()
            ):
                fail(
                    "CANDIDATE_UNRESOLVED_IDENTITY_REQUIRED",
                    "known sequence gaps must remain explicitly unresolved",
                    f"{row_path}.sequence_id",
                )
        if row["sequence_id"] == "unresolved" and (
            row["sequence_accessions"] != "unresolved"
            or row["reference_sequence_ids"] != "unresolved"
            or row["sequence_status"] not in {"pending_audit", "unresolved"}
        ):
            fail(
                "CANDIDATE_UNRESOLVED_IDENTITY_REQUIRED",
                "unresolved sequence identities cannot carry invented accessions or references",
                f"{row_path}.sequence_id",
            )
        identity_fields = (
            "sequence_id",
            "sequence_accessions",
            "reference_sequence_ids",
            "sequence_status",
            "sequence_readiness",
            "evidence_tier",
        )
        expected_identity = _CANDIDATE_SEQUENCE_IDENTITIES.get(candidate_id)
        actual_identity = tuple(row[field] for field in identity_fields)
        if expected_identity is None or actual_identity != expected_identity:
            fail(
                "CANDIDATE_IDENTITY_MISMATCH",
                "candidate sequence identity differs from the audited registry",
                f"{row_path}.sequence_id",
                {
                    "candidate_id": candidate_id,
                    "fields": [
                        field
                        for field, actual, expected in zip(
                            identity_fields, actual_identity, expected_identity or ()
                        )
                        if actual != expected
                    ],
                },
            )
        if expected_class == "primary":
            if row["program_status"] != "primary_tournament_hypothesis":
                fail(
                    "CANDIDATE_STATUS_INVALID",
                    "primary records must remain tournament hypotheses",
                    f"{row_path}.program_status",
                )
            for field in ("h3_margin", "h3_min_probability"):
                if _SIGNED_DECIMAL.fullmatch(row[field]) is None:
                    fail(
                        "CANDIDATE_H3_INVALID",
                        "primary H3 numeric fields must use canonical decimal text",
                        f"{row_path}.{field}",
                    )
                try:
                    number = Decimal(row[field])
                except InvalidOperation as exc:
                    raise AlmondLabError(
                        "CANDIDATE_H3_INVALID",
                        "primary H3 numeric fields must be finite decimals",
                        f"{row_path}.{field}",
                    ) from exc
                if not number.is_finite():
                    fail(
                        "CANDIDATE_H3_INVALID",
                        "primary H3 numeric fields must be finite",
                        f"{row_path}.{field}",
                    )
                if row[field] != _canonical_decimal_text(number):
                    fail(
                        "CANDIDATE_H3_INVALID",
                        "primary H3 numeric fields must have one canonical decimal spelling",
                        f"{row_path}.{field}",
                    )
        else:
            if row["program_status"] != "held_for_prequalification":
                fail(
                    "CANDIDATE_STATUS_INVALID",
                    "prequalification candidates cannot enter the tournament",
                    f"{row_path}.program_status",
                )
            expected_na = {
                "primary_parameter_id": "not_applicable_prequalification",
                "h3_endpoint": "not_applicable_prequalification",
                "h3_unit": "not_applicable_prequalification",
                "h3_scale": "not_applicable_prequalification",
                "h3_direction": "not_applicable_prequalification",
                "h3_margin": "not_applicable_prequalification",
                "h3_min_probability": "not_applicable_prequalification",
                "gates": "not_applicable_prequalification",
            }
            if any(row[field] != expected for field, expected in expected_na.items()):
                fail(
                    "CANDIDATE_PREQUALIFICATION_H3_INVALID",
                    "held candidates cannot carry a registered tournament H3 rule",
                    row_path,
                )

    expected_ids = list(_PRIMARY_CANDIDATE_IDS) + sorted(_PREQUALIFICATION_CANDIDATE_IDS)
    if ids[:6] != list(_PRIMARY_CANDIDATE_IDS) or set(ids[6:]) != set(
        _PREQUALIFICATION_CANDIDATE_IDS
    ) or len(ids) != len(expected_ids):
        fail(
            "CANDIDATE_REGISTRY_INCOMPLETE",
            "registry must contain C1-C6 followed by every prequalification candidate",
            "candidate_registry.candidate_id",
        )
    table = pd.DataFrame.from_records(rows, columns=CANDIDATE_COLUMNS).astype("string")
    table.attrs.clear()
    _cross_check_frozen_candidates(table, candidate_config_path)
    _require_audited_registry_hash(
        payload_sha256,
        _AUDITED_CANDIDATE_REGISTRY_SHA256,
        code="CANDIDATE_REGISTRY_CONTENT_MISMATCH",
        registry_name="candidate_registry",
    )
    return table


def validate_registry_links(
    evidence: pd.DataFrame, candidates: pd.DataFrame
) -> None:
    """Require canonical candidate evidence lists that resolve exactly once."""
    if not isinstance(evidence, pd.DataFrame) or not isinstance(candidates, pd.DataFrame):
        fail(
            "REGISTRY_FRAME_INVALID",
            "registry link validation requires pandas DataFrames",
            "registries",
        )
    if "evidence_id" not in evidence.columns or "evidence_ids" not in candidates.columns:
        fail(
            "REGISTRY_FRAME_INVALID",
            "registry frames lack required evidence link columns",
            "registries.columns",
        )
    evidence_ids = evidence["evidence_id"].tolist()
    if (
        any(
            not isinstance(value, str) or _EVIDENCE_ID.fullmatch(value) is None
            for value in evidence_ids
        )
        or len(evidence_ids) != len(set(evidence_ids))
    ):
        fail(
            "REGISTRY_EVIDENCE_LINK_INVALID",
            "evidence IDs must be unique strings",
            "evidence.evidence_id",
        )
    available = set(evidence_ids)
    for position, value in enumerate(candidates["evidence_ids"].tolist()):
        links = _parse_pipe_list(
            value,
            field_path=f"candidates.evidence_ids[{position}]",
            item_pattern=_EVIDENCE_ID,
        )
        unresolved = sorted(set(links) - available)
        if unresolved:
            fail(
                "REGISTRY_EVIDENCE_LINK_INVALID",
                "candidate evidence link does not resolve",
                f"candidates.evidence_ids[{position}]",
                {"unresolved": unresolved},
            )


def _is_missing_number(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False
    return False


def validate_reference_chemistry_frame(frame: pd.DataFrame) -> None:
    """Validate already-materialized reference chemistry without coercion."""
    if not isinstance(frame, pd.DataFrame):
        fail(
            "REFERENCE_CHEMISTRY_FRAME_INVALID",
            "reference chemistry must be a pandas DataFrame",
            "reference_chemistry",
        )
    if tuple(frame.columns) != REFERENCE_CHEMISTRY_COLUMNS:
        fail(
            "CSV_SCHEMA_MISMATCH",
            "reference chemistry frame must retain the exact schema",
            "reference_chemistry.columns",
        )
    if frame.empty:
        fail(
            "REFERENCE_CHEMISTRY_FRAME_INVALID",
            "reference chemistry frame cannot be empty",
            "reference_chemistry",
        )
    ids = frame["chemistry_id"].tolist()
    if any(not isinstance(value, str) or _CHEMISTRY_ID.fullmatch(value) is None for value in ids):
        fail(
            "REGISTRY_ID_INVALID",
            "chemistry IDs must be safe portable identifiers",
            "reference_chemistry.chemistry_id",
        )
    if len(ids) != len(set(ids)):
        fail(
            "REGISTRY_ID_DUPLICATE",
            "chemistry IDs must be unique",
            "reference_chemistry.chemistry_id",
        )
    text_columns = tuple(
        column
        for column in REFERENCE_CHEMISTRY_COLUMNS
        if column not in _NUMERIC_CHEMISTRY_COLUMNS
    )
    for position, row in frame.iterrows():
        row_path = f"reference_chemistry[{position}]"
        for column in text_columns:
            if not isinstance(row[column], str) or not row[column]:
                code = (
                    "REGISTRY_LIMITATION_REQUIRED"
                    if column == "limitation"
                    else "REFERENCE_CHEMISTRY_FRAME_INVALID"
                )
                fail(code, f"{column} must be an explicit nonblank string", f"{row_path}.{column}")
        if row["evidence_id"] != _REFERENCE_CHEMISTRY_EVIDENCE_ID:
            fail(
                "REFERENCE_CHEMISTRY_EVIDENCE_INVALID",
                "all reference recipes must link to the audited rootstock screen",
                f"{row_path}.evidence_id",
            )
        if row["source_type"] != "literature_derived":
            fail(
                "REFERENCE_CHEMISTRY_SOURCE_INVALID",
                "reference recipes must retain literature-derived source type",
                f"{row_path}.source_type",
            )
        if row["evidence_label"] != "empirically_calibrated":
            fail(
                "REFERENCE_CHEMISTRY_LABEL_INVALID",
                "source-reported reference recipes require their explicit evidence label",
                f"{row_path}.evidence_label",
            )
        if row["metadata_basis"] != "source_reported":
            fail(
                "REFERENCE_CHEMISTRY_BASIS_INVALID",
                "reference recipe metadata must remain source reported",
                f"{row_path}.metadata_basis",
            )
        if row["ec_kind"] != "ECw" or row["ion_unit"] != "meq/L":
            fail(
                "REFERENCE_CHEMISTRY_UNIT_INVALID",
                "reference EC and ion units must remain explicit",
                row_path,
            )
        if row["composition_basis"] != "source_reported_recipe_not_ec_derived":
            fail(
                "REFERENCE_CHEMISTRY_BASIS_INVALID",
                "ion composition must never be represented as derived from EC",
                f"{row_path}.composition_basis",
            )
        if not isinstance(row["limitation"], str) or not row["limitation"]:
            fail(
                "REGISTRY_LIMITATION_REQUIRED",
                "reference chemistry limitation must be nonblank",
                f"{row_path}.limitation",
            )
        missing_value = row["reported_missing_fields"]
        missing_fields = missing_value.split("|")
        if (
            any(
                not field
                or field != field.strip()
                or field not in _REFERENCE_MISSING_FIELDS
                for field in missing_fields
            )
            or len(missing_fields) != len(set(missing_fields))
            or "|".join(missing_fields) != missing_value
        ):
            fail(
                "REFERENCE_CHEMISTRY_MISSING_FIELDS_INVALID",
                "reported_missing_fields must be a unique canonical list of registered fields",
                f"{row_path}.reported_missing_fields",
            )
        missing_set = set(missing_fields)
        for column in _NUMERIC_CHEMISTRY_COLUMNS:
            is_missing = _is_missing_number(row[column])
            if (column in missing_set) != is_missing:
                fail(
                    "REFERENCE_CHEMISTRY_MISSING_FIELDS_INVALID",
                    "reported numeric omissions must exactly match missing numeric values",
                    f"{row_path}.reported_missing_fields",
                    {"column": column},
                )
        for column in _NUMERIC_CHEMISTRY_COLUMNS:
            value = row[column]
            if column != "ec_ds_m" and _is_missing_number(value):
                continue
            try:
                finite_float(
                    value,
                    code="REFERENCE_CHEMISTRY_NUMBER_INVALID",
                    field_path=f"{row_path}.{column}",
                    nonnegative=True,
                )
            except AlmondLabError:
                raise


def load_reference_chemistry(path: str | Path) -> pd.DataFrame:
    """Load exact source-reported recipes without deriving ions from EC."""
    rows, payload_sha256 = _read_strict_csv(
        path, REFERENCE_CHEMISTRY_COLUMNS, "reference_chemistry"
    )
    converted: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        row_path = f"reference_chemistry[{index}]"
        _require_explicit_text(row, REFERENCE_CHEMISTRY_COLUMNS, row_path)
        output: dict[str, object] = dict(row)
        for column in _NUMERIC_CHEMISTRY_COLUMNS:
            value = row[column]
            if column != "ec_ds_m" and value == "not_reported":
                output[column] = pd.NA
            else:
                output[column] = _strict_csv_float(value, f"{row_path}.{column}")
        converted.append(output)
    table = pd.DataFrame.from_records(converted, columns=REFERENCE_CHEMISTRY_COLUMNS)
    for column in _NUMERIC_CHEMISTRY_COLUMNS:
        table[column] = pd.array(table[column], dtype="Float64")
    table.attrs.clear()
    validate_reference_chemistry_frame(table)
    if tuple(table["chemistry_id"].tolist()) != _REFERENCE_CHEMISTRY_IDS:
        fail(
            "REFERENCE_CHEMISTRY_INCOMPLETE",
            "reference chemistry must contain all five audited source recipes in order",
            "reference_chemistry.chemistry_id",
        )
    _require_audited_registry_hash(
        payload_sha256,
        _AUDITED_REFERENCE_CHEMISTRY_SHA256,
        code="REFERENCE_CHEMISTRY_CONTENT_MISMATCH",
        registry_name="reference_chemistry",
    )
    return table


__all__ = [
    "CANDIDATE_COLUMNS",
    "EVIDENCE_COLUMNS",
    "REFERENCE_CHEMISTRY_COLUMNS",
    "load_candidate_registry",
    "load_evidence_registry",
    "load_reference_chemistry",
    "validate_reference_chemistry_frame",
    "validate_registry_links",
]
