from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path

import hypothesis
import pytest
import yaml

from almondlab.verification_policy import load_conservation_case_manifest


GENERATOR_SCHEMA = {
    "name": "hypothesis",
    "version": hypothesis.__version__,
    "phase": "generate_only",
    "shrinking": False,
    "strategy": "sampled_from_frozen_candidate_set",
    "properties": {
        "blend": {"seed": 20260814, "max_examples": 2},
        "flow": {"seed": 20260812, "max_examples": 2},
        "ro": {"seed": 20260813, "max_examples": 2},
    },
}


def test_manifest_generator_and_collective_schema_are_exact() -> None:
    manifest, digest = load_conservation_case_manifest()

    assert len(digest) == 64
    generator = manifest["generator"]
    assert generator["name"] == GENERATOR_SCHEMA["name"]
    assert generator["version"] == GENERATOR_SCHEMA["version"]
    assert generator["phase"] == "generate_only"
    assert generator["shrinking"] is False
    assert generator["strategy"] == "sampled_from_frozen_candidate_set"
    assert len(generator["candidate_set_sha256"]) == 64
    assert tuple(manifest["cases"]) == ("flow", "ro", "blend")
    assert tuple(case["id"] for case in manifest["cases"]["flow"]) == (
        "flow_seed_20260812_01",
        "flow_seed_20260812_02",
    )


def test_manifest_rejects_reordered_extrema_even_when_membership_is_unchanged(
    tmp_path: Path,
) -> None:
    contents = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_text()
    )
    payload = yaml.safe_load(contents)
    values = payload["extrema_schema"]["flow"]["global_relative_residual"]
    values[0], values[1] = values[1], values[0]
    source = tmp_path / "conservation_case_manifest.yaml"
    source.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match="exact canonical set"):
        load_conservation_case_manifest(source)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("drop_flow_entity", "keys mismatch"),
        ("drop_extrema_entity", "exact canonical set"),
        ("generator_name", "generator"),
        ("enable_shrinking", "shrinking"),
    ],
)
def test_manifest_rejects_collectively_corrupted_schema(
    tmp_path: Path, mutation: str, message: str
) -> None:
    contents = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_text()
    )
    payload = yaml.safe_load(contents)
    if mutation == "drop_flow_entity":
        del payload["cases"]["flow"][0]["source"]["stocks"]["cl"]
    elif mutation == "drop_extrema_entity":
        payload["extrema_schema"]["ro"]["conservation_absolute_residual"].remove(
            "water"
        )
    elif mutation == "generator_name":
        payload["generator"]["name"] = "corrupted"
    else:
        payload["generator"]["shrinking"] = True
    source = tmp_path / "conservation_case_manifest.yaml"
    source.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match=message):
        load_conservation_case_manifest(source)


@pytest.mark.parametrize("property_id", ("flow", "ro", "blend"))
@pytest.mark.parametrize("field", ("seed", "max_examples"))
@pytest.mark.parametrize("alias_kind", ("matching_float", "bool"))
def test_manifest_rejects_non_integer_generator_metadata_aliases(
    tmp_path: Path,
    property_id: str,
    field: str,
    alias_kind: str,
) -> None:
    contents = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_text()
    )
    payload = yaml.safe_load(contents)
    expected = payload["generator"]["properties"][property_id][field]
    alias: object = float(expected) if alias_kind == "matching_float" else True
    payload["generator"]["properties"][property_id][field] = alias
    source = tmp_path / "conservation_case_manifest.yaml"
    source.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match="positive integer"):
        load_conservation_case_manifest(source)


def test_strategy_digest_covers_exact_candidate_payload() -> None:
    manifest, _ = load_conservation_case_manifest()
    canonical_cases = resources.files("almondlab.resources").joinpath(
        "fixtures/conservation_case_manifest.candidates.json"
    ).read_bytes()

    assert manifest["generator"]["candidate_set_sha256"] == hashlib.sha256(
        canonical_cases
    ).hexdigest()


def test_manifest_rejects_case_not_present_in_frozen_candidate_set(
    tmp_path: Path,
) -> None:
    contents = (
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_text()
    )
    payload = yaml.safe_load(contents)
    flow = payload["cases"]["flow"][0]
    flow["source"]["volume_l"] = 13.0
    flow["source"]["water_mass_kg"] = 12.961
    source = tmp_path / "conservation_case_manifest.yaml"
    source.write_text(yaml.safe_dump(payload, sort_keys=False))

    with pytest.raises(ValueError, match="candidate"):
        load_conservation_case_manifest(source)
