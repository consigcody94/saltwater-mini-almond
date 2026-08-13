from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd
import pytest
import yaml

from almondlab.errors import AlmondLabError
from almondlab.registries import (
    CANDIDATE_COLUMNS,
    EVIDENCE_COLUMNS,
    REFERENCE_CHEMISTRY_COLUMNS,
    load_candidate_registry,
    load_evidence_registry,
    load_reference_chemistry,
    validate_reference_chemistry_frame,
    validate_registry_links,
)


REPO = Path(__file__).parents[1]
EVIDENCE = REPO / "data" / "evidence_registry.csv"
CANDIDATES = REPO / "data" / "candidate_registry.csv"
CHEMISTRY = REPO / "data" / "reference_chemistry.csv"
FROZEN_CANDIDATES = REPO / "configs" / "candidates.yaml"

SECTION_16_DOIS = {
    "10.1038/s41598-020-78036-4",
    "10.3389/fpls.2020.595055",
    "10.1038/s41598-022-05202-1",
    "10.1002/tpg2.20371",
    "10.1007/s11240-024-02935-x",
    "10.1007/s002990050591",
    "10.3390/plants9111508",
    "10.3390/ijms22041971",
    "10.5511/plantbiotechnology.13.0517a",
    "10.1016/j.plaphy.2025.110839",
    "10.1186/1471-2229-12-188",
    "10.1371/journal.pone.0214473",
    "10.1021/acsagscitech.1c00276",
    "10.1007/s11033-022-07213-7",
    "10.1186/s12870-026-09156-8",
    "10.1111/pce.13865",
    "10.21273/HORTSCI18021-24",
    "10.3390/agronomy10020277",
    "10.1016/j.stress.2026.101307",
}

SECTION_16_URL_ONLY_IDENTITIES = {
    "url:https://www.almonds.org/sites/default/files/2024-02/Salinity%20Management%20Guide%20for%20Almond%20Growers.pdf",
    "url:https://www.waterboards.ca.gov/water_issues/programs/ocean/desalination/",
    "url:https://www.aphis.usda.gov/biotechnology/regulations/secure-rule",
    "url:https://www.nature.com/srep/journal-policies/registered-reports",
    "url:https://royalsociety.org/journals/open-access/open-science/",
}

PRIMARY_IDS = ("C1", "C2", "C3", "C4", "C5", "C6")
PREQUALIFICATION_IDS = {
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


def _write_csv(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _raw_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return header, list(reader)


def test_registry_files_use_exact_publication_schemas_and_lf_utf8() -> None:
    expected = {
        EVIDENCE: EVIDENCE_COLUMNS,
        CANDIDATES: CANDIDATE_COLUMNS,
        CHEMISTRY: REFERENCE_CHEMISTRY_COLUMNS,
    }
    for path, columns in expected.items():
        payload = path.read_bytes()
        assert payload.decode("utf-8").encode("utf-8") == payload
        assert b"\r" not in payload
        header, _ = _raw_rows(path)
        assert tuple(header) == columns


def test_hash_sealed_registry_bytes_are_pinned_to_lf_on_checkout() -> None:
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert {
        "/data/candidate_registry.csv text eol=lf",
        "/data/evidence_registry.csv text eol=lf",
        "/data/reference_chemistry.csv text eol=lf",
    } <= set(attributes)


def test_all_section_16_sources_have_unique_stable_records() -> None:
    table = load_evidence_registry(EVIDENCE)

    assert len(table) == 24
    assert table["evidence_id"].is_unique
    assert set(table.loc[table["doi"] != "not_applicable", "doi"]) == SECTION_16_DOIS
    assert set(
        table.loc[table["doi"] == "not_applicable", "source_reference_identity"]
    ) == SECTION_16_URL_ONLY_IDENTITIES
    assert table.loc[table["doi"] != "not_applicable", "doi"].is_unique
    assert table["primary_url"].is_unique


def test_evidence_loader_rejects_an_incomplete_section_16_source_set(
    tmp_path: Path,
) -> None:
    header, rows = _raw_rows(EVIDENCE)
    path = tmp_path / "incomplete-evidence.csv"
    _write_csv(path, tuple(header), rows[:-1])

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == "EVIDENCE_REGISTRY_INCOMPLETE"


def test_evidence_loader_rejects_identity_drift_for_a_stable_source_id(
    tmp_path: Path,
) -> None:
    header, rows = _raw_rows(EVIDENCE)
    doi = "10.9999/plausible.but.wrong"
    rows[0][header.index("doi")] = doi
    rows[0][header.index("primary_url")] = f"https://doi.org/{doi}"
    rows[0][header.index("source_reference_identity")] = f"doi:{doi}"
    path = tmp_path / "drifted-evidence.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == "EVIDENCE_REGISTRY_INCOMPLETE"


def test_evidence_metadata_is_explicit_and_never_uses_blank_unknowns() -> None:
    table = load_evidence_registry(EVIDENCE)

    required_metadata = (
        "title",
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
        "source_reference_identity",
        "metadata_basis",
        "program_assumptions",
    )
    assert not table.loc[:, required_metadata].eq("").any().any()
    assert set(table["metadata_basis"]).issubset(
        {
            "source_reported",
            "official_source",
            "mixed_source_reported_and_program_assumption",
        }
    )
    assert set(table["source_sha256_status"]).issubset(
        {"verified_local_payload", "primary_source_not_archived"}
    )


def test_primary_candidate_accessions_and_h3_contract_are_exact() -> None:
    table = load_candidate_registry(CANDIDATES).set_index("candidate_id")

    assert table.loc["C1", "sequence_id"] == "AJ972674.1"
    assert table.loc["C1", "sequence_accessions"] == "AJ972674.1|CAI99405.1"
    assert table.loc["C2", "sequence_id"] == "AY282755.1"
    assert table.loc["C2", "sequence_status"] == "accession_verified"
    assert table.loc["C2", "sequence_readiness"] == (
        "accession_verified_construct_map_unresolved"
    )
    assert table.loc["C2", "target_tissue"] == (
        "prospective root-preferred cortex/vascular parenchyma class; exact "
        "construct targeting unresolved"
    )
    assert table.loc["C2", "registered_expression_class"] == (
        "Prospective salt-inducible root-preferred cortex/vascular parenchyma "
        "class; exact construct targeting unresolved"
    )
    assert table.loc["C3", "sequence_id"] == "Esi0017_0062|Esi0100_0020"
    assert table.loc["C3", "sequence_status"] == "crosswalk_pending"
    assert table.loc["C4", "sequence_id"] == "EU879059.1"
    assert table.loc["C4", "sequence_accessions"] == "EU879059.1|ACJ63441.1"
    assert table.loc["C5", "sequence_id"] == "Prupe.1G067100"
    assert table.loc["C6", "sequence_id"] == "Prupe.7G244500.1"
    assert tuple(table.loc[list(PRIMARY_IDS), "registry_class"]) == ("primary",) * 6
    assert table.loc["C3", "h3_endpoint"] == (
        "root_mannitol_concentration_above_empty_vector"
    )
    assert table.loc["C5", "h3_direction"] == "le"
    assert float(table.loc["C5", "h3_margin"]) == pytest.approx(-0.2231435513142097)


def test_candidate_registry_has_every_prequalification_candidate_and_no_winner() -> None:
    table = load_candidate_registry(CANDIDATES)

    assert len(table) == 20
    assert tuple(table.iloc[:6]["candidate_id"]) == PRIMARY_IDS
    assert set(table.loc[table["registry_class"] == "prequalification", "candidate_id"]) == (
        PREQUALIFICATION_IDS
    )
    forbidden = {"winner", "best_candidate", "biological_efficacy_claim"}
    assert forbidden.isdisjoint(table.columns)
    assert set(table["evidence_label"]) == {"hypothesis_prior"}


def test_required_sequence_gaps_remain_explicitly_unresolved() -> None:
    table = load_candidate_registry(CANDIDATES).set_index("candidate_id")

    for candidate_id in ("PQ_KCS1_LIKE", "PQ_NHX1_2", "PQ_PAVNHX37"):
        assert table.loc[candidate_id, "sequence_id"] == "unresolved"
        assert table.loc[candidate_id, "sequence_status"] in {
            "pending_audit",
            "unresolved",
        }
        assert "unresolved" in table.loc[candidate_id, "sequence_unresolved_reason"].lower()


@pytest.mark.parametrize(
    ("candidate_id", "field"),
    [
        (candidate_id, field)
        for candidate_id in ("PQ_KCS1_LIKE", "PQ_NHX1_2", "PQ_PAVNHX37")
        for field in ("sequence_id", "sequence_accessions", "reference_sequence_ids")
    ],
)
def test_known_sequence_gaps_reject_invented_identifiers(
    tmp_path: Path, candidate_id: str, field: str
) -> None:
    header, rows = _raw_rows(CANDIDATES)
    candidate_index = header.index("candidate_id")
    target = next(row for row in rows if row[candidate_index] == candidate_id)
    target[header.index(field)] = "INVENTED_12345"
    path = tmp_path / "candidate-registry.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_registry(path)

    assert exc_info.value.code == "CANDIDATE_UNRESOLVED_IDENTITY_REQUIRED"


def test_primary_sequence_id_itself_is_part_of_frozen_identity(tmp_path: Path) -> None:
    header, rows = _raw_rows(CANDIDATES)
    rows[0][header.index("sequence_id")] = "AB686252"
    path = tmp_path / "candidate-registry.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_registry(path)

    assert exc_info.value.code == "CANDIDATE_IDENTITY_MISMATCH"


def test_recent_rice_accessions_are_verified_without_construct_readiness() -> None:
    table = load_candidate_registry(CANDIDATES).set_index("candidate_id")

    assert table.loc["PQ_PYMNSOD", "sequence_accessions"] == "DQ146477.2"
    assert table.loc["PQ_PYMNSOD", "sequence_status"] == "accession_verified"
    assert table.loc["PQ_KANAH", "sequence_accessions"] == "MT473962.1"
    assert table.loc["PQ_KANAH", "sequence_status"] == (
        "accession_verified_partial_cds"
    )
    for candidate_id in ("C2", "PQ_PYMNSOD", "PQ_KANAH"):
        assert "construct_map_unresolved" in table.loc[
            candidate_id, "sequence_readiness"
        ]
        assert "construct" in table.loc[
            candidate_id, "sequence_unresolved_reason"
        ].lower()
    assert table.loc["C2", "program_status"] == "primary_tournament_hypothesis"
    assert "sequence_build=blocked" in table.loc["C2", "gates"]


def test_recent_rice_evidence_retains_full_text_design_and_claim_boundaries() -> None:
    row = load_evidence_registry(EVIDENCE).set_index("evidence_id").loc[
        "EV_PYAPX_2026"
    ]

    assert row["salinity_concentration"] == "250 mM NaCl"
    assert "every 3 days" in row["exposure_duration"]
    assert "day 10" in row["exposure_duration"]
    assert "30 seeds per dish x 3 replicate dishes" in row["sample_size"]
    assert "endpoint-specific independent-line n not_reported" in row["sample_size"]
    assert "12 PyAPX" not in row["sample_size"]
    assert "11 PyMnSOD" not in row["sample_size"]
    assert "9 KaNa+/H+" not in row["sample_size"]
    assert "recovered homozygous T1 inventory" in row["life_stage"]
    assert "12 PyAPX" in row["life_stage"]
    assert "11 PyMnSOD" in row["life_stage"]
    assert "9 KaNa+/H+" in row["life_stage"]
    assert "AY282755.1" in row["program_assumptions"]
    assert "DQ146477.2" in row["program_assumptions"]
    assert "KaNa+/H+ MT473962 (unversioned)" in row["program_assumptions"]
    assert "resolves MT473962.1 as a partial CDS" in row["program_assumptions"]
    assert "MT473962.1" in row["program_assumptions"]
    assert "construct" in row["limitation"].lower()
    assert "event" in row["limitation"].lower()


def test_kana_evidence_records_paper_repository_completeness_conflict() -> None:
    row = load_evidence_registry(EVIDENCE).set_index("evidence_id").loc[
        "EV_KANAH_2022"
    ]

    assert "MT473962 (unversioned)" in row["program_assumptions"]
    assert "full-length coding sequence" in row["program_assumptions"]
    assert "MT473962.1" in row["program_assumptions"]
    assert "partial CDS" in row["program_assumptions"]
    assert "identity/completeness conflict" in row["limitation"]
    assert "No securely pinned public accession" not in row["limitation"]


def test_public_manifest_separates_rice_inventory_and_kana_identity_states() -> None:
    payload = yaml.safe_load(
        (REPO / "data" / "public" / "public_bio_data_manifest.yaml").read_text(
            encoding="utf-8"
        )
    )
    datasets = {item["id"]: item for item in payload["datasets"]}
    article = datasets["PYAPX_RICE_2026_ARTICLE"]
    kana = datasets["KANAH_MT473962"]

    assert article["sample_count"] == {
        "germination": "30 seeds per dish x 3 replicate dishes",
        "other_endpoint_independent_line_n": "not_reported",
    }
    assert article["source_reported_inventory"]["recovered_homozygous_t1_lines"] == {
        "PyAPX": 12,
        "PyMnSOD": 11,
        "KaNa+/H+": 9,
    }
    assert article["paper_reported_accessions"]["KaNa+/H+"] == "MT473962"
    assert article["repository_verification"]["resolved_accession_versions"][
        "KaNa+/H+"
    ] == "MT473962.1"
    assert kana["paper_reported_accession"] == "MT473962"
    assert kana["accession"] == "MT473962.1"
    assert any(
        "full-length coding sequence" in conflict and "partial CDS" in conflict
        for conflict in kana["identity_conflicts"]
    )


@pytest.mark.parametrize(
    ("registry_path", "header_name", "row_number", "field_name", "replacement", "loader", "code"),
    [
        (
            EVIDENCE,
            "evidence_id",
            0,
            "title",
            "Plausible but unaudited replacement title",
            load_evidence_registry,
            "EVIDENCE_REGISTRY_CONTENT_MISMATCH",
        ),
        (
            EVIDENCE,
            "evidence_id",
            9,
            "sample_size",
            "30 seeds per dish x 2 replicate dishes",
            load_evidence_registry,
            "EVIDENCE_REGISTRY_CONTENT_MISMATCH",
        ),
        (
            EVIDENCE,
            "evidence_id",
            9,
            "reported_effect",
            "plausible changed source report",
            load_evidence_registry,
            "EVIDENCE_REGISTRY_CONTENT_MISMATCH",
        ),
        (
            CANDIDATES,
            "candidate_id",
            0,
            "evidence_ids",
            "EV_PYKPA1_2013|EV_PYAPX_2026",
            load_candidate_registry,
            "CANDIDATE_REGISTRY_CONTENT_MISMATCH",
        ),
        (
            CHEMISTRY,
            "chemistry_id",
            1,
            "cl_meq_l",
            "4.5",
            load_reference_chemistry,
            "REFERENCE_CHEMISTRY_CONTENT_MISMATCH",
        ),
        (
            CHEMISTRY,
            "chemistry_id",
            1,
            "limitation",
            "plausible but different limitation",
            load_reference_chemistry,
            "REFERENCE_CHEMISTRY_CONTENT_MISMATCH",
        ),
    ],
)
def test_audited_registry_semantics_are_fully_frozen(
    tmp_path: Path,
    registry_path: Path,
    header_name: str,
    row_number: int,
    field_name: str,
    replacement: str,
    loader: object,
    code: str,
) -> None:
    header, rows = _raw_rows(registry_path)
    assert header_name in header
    rows[row_number][header.index(field_name)] = replacement
    path = tmp_path / registry_path.name
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        loader(path)  # type: ignore[operator]

    assert exc_info.value.code == code


def test_doi_and_primary_url_are_frozen_as_one_association(tmp_path: Path) -> None:
    header, rows = _raw_rows(EVIDENCE)
    rows[0][header.index("primary_url")] = (
        "https://example.org/plausible-primary-source"
    )
    path = tmp_path / "drifted-doi-url-pair.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == "EVIDENCE_REGISTRY_CONTENT_MISMATCH"


def test_prequalification_sequence_identity_is_fail_closed(tmp_path: Path) -> None:
    header, rows = _raw_rows(CANDIDATES)
    candidate_index = header.index("candidate_id")
    target = next(row for row in rows if row[candidate_index] == "PQ_PPKUP8_LIKE")
    target[header.index("sequence_id")] = "Prupe.5G236501"
    target[header.index("sequence_accessions")] = "Prupe.5G236501"
    path = tmp_path / "candidate-registry.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_registry(path)

    assert exc_info.value.code == "CANDIDATE_IDENTITY_MISMATCH"


def test_candidate_registry_cross_checks_the_frozen_identity_config(tmp_path: Path) -> None:
    text = FROZEN_CANDIDATES.read_text(encoding="utf-8")
    altered = tmp_path / "candidates.yaml"
    altered.write_text(text.replace("AJ972674", "AB686252", 1), encoding="utf-8")

    with pytest.raises((AlmondLabError, ValueError), match="CANDIDATE_IDENTITY_MISMATCH|frozen"):
        load_candidate_registry(CANDIDATES, candidate_config_path=altered)


def test_every_candidate_evidence_link_resolves_exactly() -> None:
    evidence = load_evidence_registry(EVIDENCE)
    candidates = load_candidate_registry(CANDIDATES)

    assert validate_registry_links(evidence, candidates) is None
    assert candidates["evidence_ids"].str.len().gt(0).all()


def test_evidence_lists_reject_unknown_duplicate_or_noncanonical_tokens() -> None:
    evidence = load_evidence_registry(EVIDENCE)
    candidates = load_candidate_registry(CANDIDATES)

    for value in (
        "EV_PYKPA1_2013|EV_DOES_NOT_EXIST",
        "EV_PYKPA1_2013|EV_PYKPA1_2013",
        "EV_PYKPA1_2013 |EV_PYAPX_2026",
        "EV_PYKPA1_2013||EV_PYAPX_2026",
    ):
        malformed = candidates.copy(deep=True)
        malformed.loc[0, "evidence_ids"] = value
        with pytest.raises(AlmondLabError, match="REGISTRY_EVIDENCE_LINK_INVALID"):
            validate_registry_links(evidence, malformed)


@pytest.mark.parametrize("bad_id", [True, "EV_UNSAFE/ID", "not_reported"])
def test_registry_link_validation_rejects_noncanonical_evidence_ids(
    bad_id: object,
) -> None:
    evidence = load_evidence_registry(EVIDENCE).astype(object)
    candidates = load_candidate_registry(CANDIDATES)
    evidence.at[0, "evidence_id"] = bad_id

    with pytest.raises(AlmondLabError) as exc_info:
        validate_registry_links(evidence, candidates)

    assert exc_info.value.code == "REGISTRY_EVIDENCE_LINK_INVALID"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("duplicate_header", "CSV_HEADER_DUPLICATE"),
        ("duplicate_row", "CSV_ROW_DUPLICATE"),
        ("duplicate_doi", "REGISTRY_DOI_DUPLICATE"),
        ("duplicate_url", "REGISTRY_URL_DUPLICATE"),
        ("blank_limitation", "REGISTRY_LIMITATION_REQUIRED"),
        ("unsafe_identifier", "REGISTRY_ID_INVALID"),
        ("extra_column", "CSV_SCHEMA_MISMATCH"),
    ],
)
def test_evidence_loader_rejects_malformed_or_ambiguous_csv(
    tmp_path: Path, mutation: str, code: str
) -> None:
    header, rows = _raw_rows(EVIDENCE)
    if mutation == "duplicate_header":
        header[-1] = header[0]
    elif mutation == "duplicate_row":
        rows.append(rows[0].copy())
    elif mutation == "duplicate_doi":
        doi_index = header.index("doi")
        rows[1][doi_index] = rows[0][doi_index]
    elif mutation == "duplicate_url":
        url_index = header.index("primary_url")
        rows[1][url_index] = rows[0][url_index]
    elif mutation == "blank_limitation":
        rows[0][header.index("limitation")] = ""
    elif mutation == "unsafe_identifier":
        rows[0][header.index("evidence_id")] = "../../paper"
    elif mutation == "extra_column":
        header.append("winner")
        for row in rows:
            row.append("C1")
    path = tmp_path / "evidence.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == code


def test_loader_rejects_non_utf8_crlf_and_inconsistent_rows(tmp_path: Path) -> None:
    invalid_utf8 = tmp_path / "invalid.csv"
    invalid_utf8.write_bytes(b"evidence_id,title\nEV_ONE,\xff\n")
    with pytest.raises(AlmondLabError) as utf8:
        load_evidence_registry(invalid_utf8)
    assert utf8.value.code == "CSV_ENCODING_INVALID"

    crlf = tmp_path / "crlf.csv"
    crlf.write_bytes(EVIDENCE.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(AlmondLabError) as line_endings:
        load_evidence_registry(crlf)
    assert line_endings.value.code == "CSV_LINE_ENDING_INVALID"

    header, rows = _raw_rows(EVIDENCE)
    rows[0].pop()
    inconsistent = tmp_path / "inconsistent.csv"
    _write_csv(inconsistent, tuple(header), rows)
    with pytest.raises(AlmondLabError) as width:
        load_evidence_registry(inconsistent)
    assert width.value.code == "CSV_ROW_WIDTH_INVALID"


def test_missing_source_link_or_explicit_unknown_is_rejected(tmp_path: Path) -> None:
    header, rows = _raw_rows(EVIDENCE)
    rows[0][header.index("primary_url")] = "not_reported"
    rows[0][header.index("doi")] = "not_applicable"
    path = tmp_path / "missing-link.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == "REGISTRY_SOURCE_LINK_REQUIRED"


@pytest.mark.parametrize("bad_date", ["20260813", "2026-8-13", "+2026-08-13"])
def test_retrieval_date_requires_exact_iso_lexical_form(
    tmp_path: Path, bad_date: str
) -> None:
    header, rows = _raw_rows(EVIDENCE)
    rows[0][header.index("retrieval_date")] = bad_date
    path = tmp_path / "bad-date.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_evidence_registry(path)

    assert exc_info.value.code == "REGISTRY_DATE_INVALID"


def test_reference_chemistry_keeps_reported_recipe_distinct_from_ec() -> None:
    table = load_reference_chemistry(CHEMISTRY).set_index("chemistry_id")

    assert len(table) == 5
    assert set(table["composition_basis"]) == {
        "source_reported_recipe_not_ec_derived"
    }
    saline = table.loc[["ROOTSTOCK_T2_NA_SO4", "ROOTSTOCK_T3_NA_CL"]]
    assert tuple(saline["ec_ds_m"]) == pytest.approx((3.0, 3.0))
    assert tuple(saline["cl_meq_l"]) == pytest.approx((4.4, 19.0))
    assert tuple(saline["sulfate_meq_l"]) == pytest.approx((22.0, 3.8))
    assert set(table["source_type"]) == {"literature_derived"}
    assert set(table["evidence_label"]) == {"empirically_calibrated"}


def test_reference_chemistry_evidence_and_missing_fields_are_closed() -> None:
    table = load_reference_chemistry(CHEMISTRY)

    assert set(table["evidence_id"]) == {"EV_ROOTSTOCK_SCREEN_2020"}
    for _, row in table.iterrows():
        missing = set(row["reported_missing_fields"].split("|"))
        for column in ("temperature_c", "ca_meq_l"):
            assert (column in missing) is bool(pd.isna(row[column]))


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("evidence_id", "EV_DOES_NOT_EXIST", "REFERENCE_CHEMISTRY_EVIDENCE_INVALID"),
        (
            "reported_missing_fields",
            "boron|alkalinity|bicarbonate|ph",
            "REFERENCE_CHEMISTRY_MISSING_FIELDS_INVALID",
        ),
        ("limitation", True, "REGISTRY_LIMITATION_REQUIRED"),
    ],
)
def test_reference_chemistry_frame_rejects_untrusted_metadata_objects(
    field: str, value: object, code: str
) -> None:
    table = load_reference_chemistry(CHEMISTRY).astype(object)
    table.at[0, field] = value

    with pytest.raises(AlmondLabError) as exc_info:
        validate_reference_chemistry_frame(table)

    assert exc_info.value.code == code


@pytest.mark.parametrize("bad_value", [True, False, "3.0", object()])
def test_reference_chemistry_object_validation_does_not_coerce_numeric_values(
    bad_value: object,
) -> None:
    table = load_reference_chemistry(CHEMISTRY)
    malformed = table.copy(deep=True)
    malformed["ec_ds_m"] = malformed["ec_ds_m"].astype(object)
    malformed.at[0, "ec_ds_m"] = bad_value

    with pytest.raises(AlmondLabError, match="REFERENCE_CHEMISTRY_NUMBER_INVALID"):
        validate_reference_chemistry_frame(malformed)


@pytest.mark.parametrize(
    "bad_number", ["3e0", "+3.0", "03.0", ".5", "1.360", "1.3600"]
)
def test_reference_chemistry_requires_canonical_decimal_text(
    tmp_path: Path, bad_number: str
) -> None:
    header, rows = _raw_rows(CHEMISTRY)
    rows[0][header.index("ec_ds_m")] = bad_number
    path = tmp_path / "bad-chemistry-number.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_reference_chemistry(path)

    assert exc_info.value.code == "REFERENCE_CHEMISTRY_NUMBER_INVALID"


@pytest.mark.parametrize("bad_number", ["0.90", "0.900", "10.0", "010"])
def test_candidate_h3_numbers_have_one_canonical_decimal_spelling(
    tmp_path: Path, bad_number: str
) -> None:
    header, rows = _raw_rows(CANDIDATES)
    field = "h3_min_probability" if bad_number.startswith("0") else "h3_margin"
    rows[2][header.index(field)] = bad_number
    path = tmp_path / "candidate-decimal-alias.csv"
    _write_csv(path, tuple(header), rows)

    with pytest.raises(AlmondLabError) as exc_info:
        load_candidate_registry(path)

    assert exc_info.value.code == "CANDIDATE_H3_INVALID"


def test_public_evidence_surfaces_do_not_repeat_false_pyapx_absence_claims() -> None:
    paths = (
        REPO / "data" / "public" / "public_bio_data_audit.md",
        REPO / "data" / "public" / "public_bio_data_manifest.yaml",
        REPO / "data" / "public" / "evidence_registry_seed.md",
        REPO / "data" / "public" / "README.md",
        REPO / "scripts" / "public_data" / "phase2" / "README.md",
    )
    forbidden = (
        "no exact pyapx nucleotide/protein accession was verified",
        "no pyapx sequence is included because no exact public accession-version was verified",
        "article_verified_sequence_accession_absent",
        "the exact pyapx sequence/accession used in the recent rice paper was not verified",
    )
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)

    assert all(statement not in combined for statement in forbidden)
    for accession in ("AY282755.1", "DQ146477.2", "MT473962.1"):
        assert accession.lower() in combined
    assert "not construct-ready" in combined


def test_public_snapshot_sidecars_hash_current_files_and_describe_mixed_history(
) -> None:
    public_readme = (REPO / "data" / "public" / "README.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(public_readme.split())

    assert "mixed repository snapshot" in normalized
    assert "per-file content hashes, not a single commit identity" in normalized
    assert "byte-identical to downloader integration commit `0c61054`" in normalized
    assert "byte-identical to accession-extension commit `f739404`" in normalized
    assert (
        "acquisition code at downloader integration commit `0c61054`"
        not in normalized
    )
    assert (
        "documentation at the accession-extension review committed as `f739404`"
        not in normalized
    )

    snapshots = (
        (REPO / "data" / "public" / "local_snapshot.sha256", REPO),
        (
            REPO / "scripts" / "public_data" / "phase2" / "local_snapshot.sha256",
            REPO / "scripts" / "public_data" / "phase2",
        ),
    )
    checked = 0
    for sidecar, base in snapshots:
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            digest, separator, relative_path = line.partition("  ")
            assert separator == "  ", f"malformed snapshot line in {sidecar}: {line}"
            assert len(digest) == 64 and all(
                character in "0123456789abcdef" for character in digest
            )
            actual = hashlib.sha256((base / relative_path).read_bytes()).hexdigest()
            assert actual == digest
            checked += 1

    assert checked == 13


def test_registry_loads_are_defensive_against_caller_mutation() -> None:
    first = load_candidate_registry(CANDIDATES)
    first.loc[0, "sequence_id"] = "invented"
    first.attrs["trusted"] = True

    second = load_candidate_registry(CANDIDATES)

    assert second.loc[0, "sequence_id"] == "AJ972674.1"
    assert "trusted" not in second.attrs
