"""Adversarial tests for restricted Paper 1 randomization and unit audits."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from importlib import resources
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
from types import MappingProxyType

import numpy as np
import pytest
import almondlab.design as design_module

from almondlab.contracts import EvidenceLabel
from almondlab.design import (
    AllocationRecord,
    BaselinePlant,
    BaselineRoster,
    BlindingEscrowAuthority,
    BlindedAllocationRecord,
    BlindedProjection,
    CohortIdentitySet,
    ConfirmationDesignConfig,
    ExperimentalUnitSpec,
    ObservationIdentityRecord,
    PositionMap,
    PositionSlot,
    blinded_projection,
    blinding_escrow_crosswalk,
    generate_blinding_escrow_authority,
    cohort_identity_set,
    load_randomization_fixture,
    load_shared_reservoir_records,
    publish_design_acceptance,
    randomize,
    revalidate_baseline_roster,
    revalidate_blinded_projection,
    revalidate_experimental_unit_audit,
    revalidate_position_map,
    revalidate_randomization_manifest,
    validate_cohort_separation,
    validate_experimental_units,
)
from almondlab.errors import AlmondLabError
from almondlab.paper1_contracts import AnalysisPopulation, load_paper1_design
from almondlab.provenance import canonical_json_bytes, sha256_bytes, sha256_file


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs" / "experiment_paper1.yaml"
FIXTURE = ROOT / "tests" / "fixtures" / "paper1_small.yaml"
TRAP = ROOT / "tests" / "fixtures" / "shared_reservoir_trap.csv"
SEED = 20260812
BLINDING_KEY = bytes.fromhex(
    "4ddc4d7845c87157f211001e11dc4f859a98e3a27fd27b37c3bd1b3b498ac75a"
)
GROUPS = (
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "empty_vector",
    "sham_transformation",
    "unmodified_parent",
)
SEED_NAMES = (
    "run_block_ordering",
    "reservoir_identity",
    "transformation_batch",
    "plant_identity",
    "position",
    "blind_code",
    "movement_schedule",
)


@pytest.fixture(scope="module")
def design_inputs():
    return load_randomization_fixture(FIXTURE)


@pytest.fixture(scope="module")
def config():
    return load_paper1_design(CONFIG)


@pytest.fixture(scope="module")
def manifest(config, design_inputs):
    return randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )


@pytest.fixture(scope="module")
def escrow_authority():
    return BlindingEscrowAuthority(secret_key=BLINDING_KEY)


@pytest.fixture(scope="module")
def full_spec(config, design_inputs):
    return ExperimentalUnitSpec.from_design(
        config,
        position_map=design_inputs.position_map,
    )


def _cell(record: AllocationRecord) -> tuple[str, str, str, str]:
    return (record.group_id, record.water_id, record.run_id, record.reservoir_id)


def _replace_record(
    records: tuple[AllocationRecord, ...], index: int, **changes: object
) -> tuple[AllocationRecord, ...]:
    edited = list(records)
    edited[index] = replace(edited[index], **changes)
    return tuple(edited)


def _confirmation_inputs(
    *,
    selected_candidates: tuple[str, ...] = ("C1", "C2"),
    plants_per_cell: int = 5,
) -> tuple[ConfirmationDesignConfig, BaselineRoster, PositionMap]:
    groups = selected_candidates + ("empty_vector",)
    runs = ("confirmation_run_a", "confirmation_run_b")
    waters = (
        "nonsaline_nutrient_matched_control",
        "pilot_selected_full_ion_marine_challenge",
    )
    config = ConfirmationDesignConfig(
        schema_version="1.0",
        evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
        population=AnalysisPopulation.COMPOSITE_ROOT,
        selected_candidate_ids=selected_candidates,
        water_ids=waters,
        runs=runs,
        reservoirs_per_water=6,
        independent_plants_per_group_reservoir=plants_per_cell,
        balanced_transformation_batches=("batch_a", "batch_b"),
        construct_level_unit="independently_transformed_plant",
        water_treatment_unit="reservoir",
        discovery_max_run_sequence_ordinal=2,
    )
    plants: list[BaselinePlant] = []
    per_group = 12 * plants_per_cell
    for group in groups:
        for index in range(per_group):
            block = "batch_a" if index < per_group // 2 else "batch_b"
            stratum_index = index % (per_group // 2)
            stratum = "lower_canopy" if stratum_index < per_group // 4 else "upper_canopy"
            plants.append(
                BaselinePlant(
                    plant_id=f"confirm-{group}-{index + 1:03d}",
                    group_id=group,
                    pretreatment_canopy=20.0 + index / 1000,
                    baseline_canopy_stratum=stratum,
                    transformation_batch_block=block,
                    transformation_batch_id=f"confirm-{group}-physical-{block}",
                    transformation_event_id=f"confirm-{group}-event-{index + 1:03d}",
                    cohort_id="confirmation",
                )
            )
    slots: list[PositionSlot] = []
    slots_per_loop = len(groups) * plants_per_cell
    for water_index, water_id in enumerate(waters, start=1):
        for reservoir_number in range(1, 7):
            run_index = 0 if reservoir_number <= 3 else 1
            run_id = runs[run_index]
            run_ordinal = 3 + run_index
            for slot_number in range(1, slots_per_loop + 1):
                slots.append(
                    PositionSlot(
                        position_id=(
                            f"confirm-w{water_index}-res{reservoir_number:02d}"
                            f"-slot{slot_number:02d}"
                        ),
                        run_id=run_id,
                        run_sequence_ordinal=run_ordinal,
                        water_id=water_id,
                        reservoir_id=(
                            f"confirm-w{water_index}-reservoir-{reservoir_number:02d}"
                        ),
                        water_batch_id=f"confirm-w{water_index}-water-batch",
                        greenhouse_compartment_id=f"confirm-compartment-{run_index + 1}",
                        bench_id=f"confirm-w{water_index}-res{reservoir_number:02d}",
                        row=(slot_number - 1) // 9 + 1,
                        column=(slot_number - 1) % 9 + 1,
                        spatial_gradient_profile_id=(
                            f"confirm-gradient-w{water_index}-res{reservoir_number:02d}"
                        ),
                        permitted_movement_schedule_ids=("confirm-rotation",),
                        cohort_id="confirmation",
                    )
                )
    return config, BaselineRoster(tuple(plants)), PositionMap(tuple(slots))


def test_full_allocation_matches_independent_literal_count_oracle(manifest) -> None:
    """Catches omitted design arms or a generated count oracle."""
    assert len(manifest.records) == 720
    assert 9 * 2 * 2 * 4 * 5 == 720
    assert {record.group_id for record in manifest.records} == set(GROUPS)
    assert sum(record.transformation_batch_id is not None for record in manifest.records) == 560
    assert sum(record.transformation_batch_id is None for record in manifest.records) == 160


def test_discovery_physical_schedule_has_exact_run_ordinals(manifest) -> None:
    """Catches inferred or missing temporal ordering in physical allocations."""
    assert {
        (record.run_id, record.run_sequence_ordinal) for record in manifest.records
    } == {("discovery_run_1", 1), ("discovery_run_2", 2)}
    with pytest.raises(AlmondLabError) as exc_info:
        replace(manifest.records[0], run_sequence_ordinal=True)
    assert exc_info.value.code == "ALLOCATION_RECORD_INVALID"
    assert exc_info.value.field_path == "run_sequence_ordinal"


def test_manifest_is_canonical_for_repeat_and_permuted_input_order(
    config, design_inputs, manifest
) -> None:
    """Catches dependence on caller row order or nondeterministic serialization."""
    repeated = randomize(
        config,
        SEED,
        position_map=PositionMap(tuple(reversed(design_inputs.position_map.slots))),
        baseline_roster=BaselineRoster(
            tuple(reversed(design_inputs.baseline_roster.plants))
        ),
    )
    assert repeated.canonical_json_bytes() == manifest.canonical_json_bytes()
    assert repeated.allocation_sha256 == manifest.allocation_sha256


def test_different_seed_changes_assignment_not_registered_cells(
    config, design_inputs, manifest
) -> None:
    """Catches seed-dependent creation or deletion of experimental cells."""
    changed = randomize(
        config,
        SEED + 1,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    assert [_cell(record) for record in changed.records] == [
        _cell(record) for record in manifest.records
    ]
    assert [record.plant_id for record in changed.records] != [
        record.plant_id for record in manifest.records
    ]
    assert [record.position_id for record in changed.records] != [
        record.position_id for record in manifest.records
    ]
    assert [record.blinded_treatment_code for record in changed.records] != [
        record.blinded_treatment_code for record in manifest.records
    ]


def test_seed_tree_has_literal_order_spawn_keys_and_ignores_global_rng(
    config, design_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches alphabetic seed children or module-global RNG use."""
    expected = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("module-global random state was used")

    monkeypatch.setattr(np.random, "seed", refuse)
    monkeypatch.setattr(np.random, "shuffle", refuse)
    monkeypatch.setattr(np.random, "permutation", refuse)
    received = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    assert received.canonical_json_bytes() == expected.canonical_json_bytes()
    assert tuple(child.name for child in received.seed_tree.children) == SEED_NAMES
    assert tuple(child.spawn_key for child in received.seed_tree.children) == tuple(
        (index,) for index in range(7)
    )
    assert received.seed_tree.entropy == SEED
    assert received.seed_tree.spawn_key == ()
    assert received.seed_tree.pool_size == 4


def test_copy_bypassed_config_and_reused_physical_batches_fail_before_rng(
    config, design_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches model-copy bypass and cross-group reuse of a physical batch ID."""
    seed_calls = 0
    real_seed_sequence = np.random.SeedSequence

    def count_seed(*args: object, **kwargs: object):
        nonlocal seed_calls
        seed_calls += 1
        return real_seed_sequence(*args, **kwargs)

    monkeypatch.setattr(np.random, "SeedSequence", count_seed)
    bypassed = config.model_copy(update={"reservoirs_per_water_run": True})
    with pytest.raises(AlmondLabError) as config_error:
        randomize(
            bypassed,
            SEED,
            position_map=design_inputs.position_map,
            baseline_roster=design_inputs.baseline_roster,
        )
    assert config_error.value.code == "DESIGN_CONFIG_INVALID"
    assert seed_calls == 0

    c1_batch = next(
        plant.transformation_batch_id
        for plant in design_inputs.baseline_roster.plants
        if plant.group_id == "C1" and plant.transformation_batch_block == "batch_a"
    )
    reused = BaselineRoster(
        tuple(
            replace(plant, transformation_batch_id=c1_batch)
            if plant.group_id == "C2" and plant.transformation_batch_block == "batch_a"
            else plant
            for plant in design_inputs.baseline_roster.plants
        )
    )
    with pytest.raises(AlmondLabError) as roster_error:
        randomize(
            config,
            SEED,
            position_map=design_inputs.position_map,
            baseline_roster=reused,
        )
    assert roster_error.value.code == "ROSTER_INVALID"
    assert roster_error.value.field_path == "baseline_roster.plants.transformation_batch_id"
    assert seed_calls == 0


def test_every_registered_group_reservoir_cell_has_five_plants(manifest) -> None:
    """Catches an incomplete or overfilled allocation cell."""
    counts: dict[tuple[str, str, str, str], int] = {}
    for record in manifest.records:
        counts[_cell(record)] = counts.get(_cell(record), 0) + 1
    assert len(counts) == 9 * 2 * 2 * 4
    assert set(counts.values()) == {5}


def test_candidate_and_empty_vector_batches_cross_and_balance(manifest) -> None:
    """Catches manufactured, uncrossed, or globally imbalanced batch blocks."""
    requiring_batch = set(GROUPS[:7])
    for group in requiring_batch:
        group_records = [record for record in manifest.records if record.group_id == group]
        assert {record.transformation_batch_block for record in group_records} == {
            "batch_a",
            "batch_b",
        }
        assert {
            block: sum(record.transformation_batch_block == block for record in group_records)
            for block in ("batch_a", "batch_b")
        } == {"batch_a": 40, "batch_b": 40}
        for cell in {_cell(record) for record in group_records}:
            cell_records = [record for record in group_records if _cell(record) == cell]
            assert sorted(
                sum(record.transformation_batch_block == block for record in cell_records)
                for block in ("batch_a", "batch_b")
            ) == [2, 3]


def test_sham_and_unmodified_reject_fictional_transformation_identity() -> None:
    """Catches invented event or batch identities for nontransformed controls."""
    with pytest.raises(AlmondLabError) as exc_info:
        BaselinePlant(
            plant_id="sham-physical-001",
            group_id="sham_transformation",
            pretreatment_canopy=1.0,
            baseline_canopy_stratum="lower_canopy",
            transformation_batch_block=None,
            transformation_batch_id=None,
            transformation_event_id="fictional-event",
            cohort_id="discovery",
        )
    assert exc_info.value.code == "ROSTER_INVALID"
    assert exc_info.value.field_path == "transformation_event_id"


def test_allocation_identities_are_one_to_one_and_positions_have_capacity(
    manifest,
) -> None:
    """Catches reused plants, blinds, allocations, or physical slots."""
    assert len({record.allocation_id for record in manifest.records}) == 720
    assert len({record.plant_id for record in manifest.records}) == 720
    assert len({record.position_id for record in manifest.records}) == 720
    assert len({record.blinded_treatment_code for record in manifest.records}) == 720
    assert all(record.movement_schedule_id for record in manifest.records)


def test_water_n_uses_shared_reservoir_and_rejects_plant_alias_first() -> None:
    """Catches plant/pot counts being substituted for independent water loops."""
    records = load_shared_reservoir_records(TRAP)
    audit = validate_experimental_units(
        records,
        ExperimentalUnitSpec(population=AnalysisPopulation.COMPOSITE_ROOT),
    )
    assert audit.biological_n == 4
    assert audit.water_treatment_n == 1
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(
            (),
            ExperimentalUnitSpec(
                population=AnalysisPopulation.COMPOSITE_ROOT,
                requested_water_unit="plant_id",
            ),
        )
    assert exc_info.value.to_dict() == {
        "code": "PSEUDOREPLICATION",
        "message": "water treatment replication must use independent reservoirs",
        "field_path": "spec.requested_water_unit",
        "details": {
            "attempted_unit": "plant_id",
            "canonical_unit": "reservoir",
            "canonical_identity_fields": ["run_id", "water_id", "reservoir_id"],
        },
    }


def test_observations_never_inflate_biological_or_water_n(manifest, full_spec) -> None:
    """Catches leaves, wells, images, time points, or reads becoming replicates."""
    first = manifest.records[0]
    observations = tuple(
        ObservationIdentityRecord(
            observation_id=f"obs-{index}",
            plant_id=first.plant_id,
            subsample_id=f"leaf-{index % 2}",
            technical_read_id=f"well-{index}",
            timepoint_id=f"day-{index}",
        )
        for index in range(12)
    )
    plain = validate_experimental_units(manifest.records, full_spec)
    repeated = validate_experimental_units(
        manifest.records,
        full_spec,
        observations=observations,
    )
    assert (plain.biological_n, plain.water_treatment_n) == (720, 16)
    assert (repeated.biological_n, repeated.water_treatment_n) == (720, 16)
    assert repeated.observation_n == 12


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("missing", "EXPERIMENTAL_UNIT_INVALID"),
        ("duplicate_allocation", "EXPERIMENTAL_UNIT_INVALID"),
        ("reused_blind", "EXPERIMENTAL_UNIT_INVALID"),
        ("off_grid", "EXPERIMENTAL_UNIT_INVALID"),
        ("reused_plant", "EXPERIMENTAL_UNIT_INVALID"),
    ],
)
def test_audit_fails_closed_on_identity_and_grid_corruption(
    manifest, full_spec, mutation: str, code: str
) -> None:
    """Catches incomplete, duplicated, relabeled, blind-reused, or off-grid rows."""
    records = manifest.records
    if mutation == "missing":
        corrupted = records[:-1]
    elif mutation == "duplicate_allocation":
        corrupted = records + (records[0],)
    elif mutation == "reused_blind":
        corrupted = _replace_record(
            records, 1, blinded_treatment_code=records[0].blinded_treatment_code
        )
    elif mutation == "off_grid":
        corrupted = _replace_record(records, 0, position_id="not-a-physical-slot")
    else:
        corrupted = _replace_record(records, 1, plant_id=records[0].plant_id)
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == code


@pytest.mark.parametrize(
    ("namespace", "field_name"),
    [
        ("plant_ids", "plant_ids"),
        ("transformation_batch_ids", "transformation_batch_ids"),
        ("reservoir_ids", "reservoir_ids"),
        ("water_batch_ids", "water_batch_ids"),
        ("run_ids", "run_ids"),
    ],
)
def test_discovery_confirmation_reuse_fails_in_all_required_namespaces(
    namespace: str, field_name: str
) -> None:
    """Catches physical identity leakage from discovery into confirmation."""
    base = {
        "plant_ids": ("disc-plant",),
        "transformation_batch_ids": ("disc-batch",),
        "reservoir_ids": ("disc-reservoir",),
        "water_batch_ids": ("disc-water-batch",),
        "run_ids": ("disc-run",),
    }
    other = {
        "plant_ids": ("confirm-plant",),
        "transformation_batch_ids": ("confirm-batch",),
        "reservoir_ids": ("confirm-reservoir",),
        "water_batch_ids": ("confirm-water-batch",),
        "run_ids": ("confirm-run",),
    }
    other[field_name] = base[field_name]
    cohorts = (
        CohortIdentitySet(cohort_id="discovery", **base),
        CohortIdentitySet(
            cohort_id="confirmation", run_sequence_ordinals=(3,), **other
        ),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(
            load_shared_reservoir_records(TRAP),
            ExperimentalUnitSpec(population=AnalysisPopulation.COMPOSITE_ROOT),
            cohorts=cohorts,
        )
    assert exc_info.value.code == "COHORT_IDENTITY_REUSE"
    assert exc_info.value.details == {"namespace": namespace, "reused_ids": list(base[field_name])}


def test_row_count_preserving_imbalance_is_rejected(manifest, full_spec) -> None:
    """Catches an allocator that checks totals but not block-cell balance."""
    c1_cell = _cell(next(record for record in manifest.records if record.group_id == "C1"))
    cell_records = [record for record in manifest.records if _cell(record) == c1_cell]
    block_counts = {
        block: sum(record.transformation_batch_block == block for record in cell_records)
        for block in ("batch_a", "batch_b")
    }
    majority = max(block_counts, key=block_counts.get)
    minority = min(block_counts, key=block_counts.get)
    source_index = next(
        index for index, record in enumerate(manifest.records)
        if _cell(record) == c1_cell and record.transformation_batch_block == minority
    )
    corrupted = _replace_record(
        manifest.records,
        source_index,
        transformation_batch_block=majority,
        transformation_batch_id=next(
            record.transformation_batch_id
            for record in manifest.records
            if record.group_id == "C1"
            and record.transformation_batch_block == majority
        ),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.transformation_batch_block"


def test_cell_balanced_but_globally_imbalanced_batches_are_rejected(
    manifest, full_spec
) -> None:
    """Catches 3/2 cells whose excess never alternates to global 40/40."""
    c1_cells = sorted({_cell(record) for record in manifest.records if record.group_id == "C1"})
    source_cell = next(
        cell
        for cell in c1_cells
        if sum(
            record.transformation_batch_block == "batch_b"
            for record in manifest.records
            if _cell(record) == cell
        )
        == 3
    )
    source_index = next(
        index
        for index, record in enumerate(manifest.records)
        if _cell(record) == source_cell and record.transformation_batch_block == "batch_b"
    )
    target_batch_id = next(
        record.transformation_batch_id
        for record in manifest.records
        if record.group_id == "C1" and record.transformation_batch_block == "batch_a"
    )
    corrupted = _replace_record(
        manifest.records,
        source_index,
        transformation_batch_block="batch_a",
        transformation_batch_id=target_batch_id,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.transformation_batch_block"


def test_position_metadata_must_match_the_physical_position_map(
    manifest, full_spec
) -> None:
    """Catches a valid position ID relabeled to a fictional row or loop."""
    corrupted = _replace_record(manifest.records, 0, row=99)
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.position_id"


def test_wrong_population_model_fails_stably(manifest, full_spec) -> None:
    """Catches applying a stable-event unit model to composite-root records."""
    wrong = replace(full_spec, population=AnalysisPopulation.STABLE_EVENT)
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(manifest.records, wrong)
    assert exc_info.value.code == "MODEL_POPULATION_MISMATCH"
    assert exc_info.value.field_path == "spec.population"


@pytest.mark.parametrize(
    ("selected_candidates", "plants_per_cell"),
    [(("C1",), 5), (("C1", "C2", "C3", "C4"), 6)],
)
def test_separate_confirmation_config_allocates_later_six_loop_design(
    selected_candidates: tuple[str, ...],
    plants_per_cell: int,
) -> None:
    """Catches loosening discovery config or inventing confirmation material."""
    confirmation, roster, positions = _confirmation_inputs(
        selected_candidates=selected_candidates,
        plants_per_cell=plants_per_cell
    )
    manifest = randomize(
        confirmation,
        SEED + 10,
        position_map=positions,
        baseline_roster=roster,
    )
    spec = ExperimentalUnitSpec.from_confirmation_design(
        confirmation,
        position_map=positions,
    )
    audit = validate_experimental_units(manifest.records, spec)
    expected = (len(selected_candidates) + 1) * 2 * 6 * plants_per_cell
    assert len(manifest.records) == expected
    assert audit.biological_n == expected
    assert audit.water_treatment_n == 12
    assert {record.group_id for record in manifest.records} == set(
        selected_candidates
    ) | {"empty_vector"}
    assert min(record.run_sequence_ordinal for record in manifest.records) == 3


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("no_candidate", "CONFIRMATION_DESIGN_INVALID"),
        ("five_candidates", "CONFIRMATION_DESIGN_INVALID"),
        ("unordered_candidates", "CONFIRMATION_DESIGN_INVALID"),
        ("one_run", "CONFIRMATION_DESIGN_INVALID"),
        ("wrong_reservoir_count", "CONFIRMATION_DESIGN_INVALID"),
        ("wrong_plant_count", "CONFIRMATION_DESIGN_INVALID"),
        ("early_run", "POSITION_MAP_INVALID"),
    ],
)
def test_confirmation_boundary_rejects_wrong_family_or_schedule(
    mutation: str, code: str
) -> None:
    """Catches unselected arms, same-run leftovers, or wrong confirmation size."""
    confirmation, roster, positions = _confirmation_inputs()
    if mutation == "no_candidate":
        action = lambda: replace(confirmation, selected_candidate_ids=())
    elif mutation == "five_candidates":
        action = lambda: replace(
            confirmation, selected_candidate_ids=("C1", "C2", "C3", "C4", "C5")
        )
    elif mutation == "unordered_candidates":
        action = lambda: replace(confirmation, selected_candidate_ids=("C2", "C1"))
    elif mutation == "one_run":
        action = lambda: replace(confirmation, runs=("confirmation_run_a",))
    elif mutation == "wrong_reservoir_count":
        action = lambda: replace(confirmation, reservoirs_per_water=5)
    elif mutation == "wrong_plant_count":
        action = lambda: replace(
            confirmation, independent_plants_per_group_reservoir=4
        )
    else:
        def action():
            early_slots = tuple(
                replace(slot, run_sequence_ordinal=2)
                if slot.run_id == "confirmation_run_a"
                else slot
                for slot in positions.slots
            )
            return randomize(
                confirmation,
                SEED + 10,
                position_map=PositionMap(early_slots),
                baseline_roster=roster,
            )
    with pytest.raises(AlmondLabError) as exc_info:
        action()
    assert exc_info.value.code == code


def test_factory_derived_cohort_sets_are_exhaustive_and_strictly_later(
    manifest, design_inputs
) -> None:
    """Catches omitted identities or a caller-authored discovery maximum."""
    confirmation, roster, positions = _confirmation_inputs(
        selected_candidates=("C1",)
    )
    confirmation_manifest = randomize(
        confirmation,
        SEED + 10,
        position_map=positions,
        baseline_roster=roster,
    )
    discovery_set, confirmation_set = validate_cohort_separation(
        discovery_manifest=manifest,
        discovery_roster=design_inputs.baseline_roster,
        discovery_position_map=design_inputs.position_map,
        confirmation_manifest=confirmation_manifest,
        confirmation_roster=roster,
        confirmation_position_map=positions,
    )
    assert len(discovery_set.plant_ids) == 720
    assert len(confirmation_set.plant_ids) == 120
    assert discovery_set.run_sequence_ordinals == (1, 2)
    assert confirmation_set.run_sequence_ordinals == (3, 4)
    assert cohort_identity_set(
        manifest,
        baseline_roster=design_inputs.baseline_roster,
        position_map=design_inputs.position_map,
    ) == discovery_set


@pytest.mark.parametrize(
    "namespace",
    [
        "plant_ids",
        "transformation_batch_ids",
        "reservoir_ids",
        "water_batch_ids",
        "run_ids",
        "transformation_event_ids",
    ],
)
def test_authoritative_cohort_boundary_cannot_omit_physical_reuse(
    manifest, design_inputs, namespace: str
) -> None:
    """Catches a hand-authored identity set that omits a real overlap."""
    confirmation, roster, positions = _confirmation_inputs(
        selected_candidates=("C1",)
    )
    discovery_record = manifest.records[0]
    plants = list(roster.plants)
    slots = list(positions.slots)
    if namespace == "plant_ids":
        plants[0] = replace(plants[0], plant_id=discovery_record.plant_id)
    elif namespace == "transformation_batch_ids":
        plants = [
            replace(
                plant,
                transformation_batch_id=discovery_record.transformation_batch_id,
            )
            if plant.group_id == "C1"
            and plant.transformation_batch_block
            == discovery_record.transformation_batch_block
            else plant
            for plant in plants
        ]
    elif namespace == "transformation_event_ids":
        plants[0] = replace(
            plants[0],
            transformation_event_id=discovery_record.transformation_event_id,
        )
    elif namespace == "reservoir_ids":
        target = slots[0].reservoir_id
        slots = [
            replace(slot, reservoir_id=discovery_record.reservoir_id)
            if slot.reservoir_id == target
            else slot
            for slot in slots
        ]
    elif namespace == "water_batch_ids":
        target = slots[0].reservoir_id
        slots = [
            replace(slot, water_batch_id=discovery_record.water_batch_id)
            if slot.reservoir_id == target
            else slot
            for slot in slots
        ]
    else:
        target_run = slots[0].run_id
        slots = [
            replace(slot, run_id=discovery_record.run_id)
            if slot.run_id == target_run
            else slot
            for slot in slots
        ]
        confirmation = replace(
            confirmation,
            runs=(discovery_record.run_id, confirmation.runs[1]),
        )
    changed_roster = BaselineRoster(tuple(plants))
    changed_positions = PositionMap(tuple(slots))
    confirmation_manifest = randomize(
        confirmation,
        SEED + 10,
        position_map=changed_positions,
        baseline_roster=changed_roster,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_cohort_separation(
            discovery_manifest=manifest,
            discovery_roster=design_inputs.baseline_roster,
            discovery_position_map=design_inputs.position_map,
            confirmation_manifest=confirmation_manifest,
            confirmation_roster=changed_roster,
            confirmation_position_map=changed_positions,
        )
    assert exc_info.value.code == "COHORT_IDENTITY_REUSE"
    assert exc_info.value.details is not None
    assert exc_info.value.details["namespace"] == namespace


def test_authoritative_cohort_boundary_rejects_lie_about_discovery_max(
    manifest, design_inputs
) -> None:
    """Catches confirmation config lowering discovery max to admit an equal run."""
    confirmation, roster, positions = _confirmation_inputs(
        selected_candidates=("C1",)
    )
    confirmation = replace(
        confirmation, discovery_max_run_sequence_ordinal=1
    )
    positions = PositionMap(
        tuple(
            replace(slot, run_sequence_ordinal=slot.run_sequence_ordinal - 1)
            for slot in positions.slots
        )
    )
    confirmation_manifest = randomize(
        confirmation,
        SEED + 10,
        position_map=positions,
        baseline_roster=roster,
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_cohort_separation(
            discovery_manifest=manifest,
            discovery_roster=design_inputs.baseline_roster,
            discovery_position_map=design_inputs.position_map,
            confirmation_manifest=confirmation_manifest,
            confirmation_roster=roster,
            confirmation_position_map=positions,
        )
    assert exc_info.value.code == "COHORT_IDENTITY_REUSE"
    assert exc_info.value.field_path == "cohorts.run_sequence_ordinals"


def test_public_revalidation_reconstructs_and_rejects_copy_bypass(
    manifest, full_spec, design_inputs
) -> None:
    """Catches trusted dataclass instances forged with object.__setattr__."""
    assert revalidate_baseline_roster(design_inputs.baseline_roster) == design_inputs.baseline_roster
    assert revalidate_position_map(design_inputs.position_map) == design_inputs.position_map
    assert revalidate_randomization_manifest(manifest).canonical_json_bytes() == manifest.canonical_json_bytes()
    audit = validate_experimental_units(manifest.records, full_spec)
    assert revalidate_experimental_unit_audit(
        audit, records=manifest.records, spec=full_spec
    ) == audit

    forged_roster = BaselineRoster(design_inputs.baseline_roster.plants)
    object.__setattr__(forged_roster, "plants", (object(),))
    with pytest.raises(AlmondLabError):
        revalidate_baseline_roster(forged_roster)

    forged_map = PositionMap(design_inputs.position_map.slots)
    object.__setattr__(forged_map, "slots", (object(),))
    with pytest.raises(AlmondLabError):
        revalidate_position_map(forged_map)

    forged_manifest = revalidate_randomization_manifest(manifest)
    object.__setattr__(forged_manifest, "allocation_sha256", "0" * 64)
    with pytest.raises(AlmondLabError):
        revalidate_randomization_manifest(forged_manifest)

    forged_audit = replace(audit, biological_n=719)
    with pytest.raises(AlmondLabError):
        revalidate_experimental_unit_audit(
            forged_audit, records=manifest.records, spec=full_spec
        )


def test_seed_tree_and_exact_primitive_boundaries_reject_forgery(manifest) -> None:
    """Catches seed metadata forgery and str/int subclass smuggling."""
    class StringSubclass(str):
        pass

    forged_record_manifest = revalidate_randomization_manifest(manifest)
    object.__setattr__(
        forged_record_manifest.records[0], "plant_id", StringSubclass("smuggled")
    )
    with pytest.raises(AlmondLabError):
        revalidate_randomization_manifest(forged_record_manifest)

    forged_seed_manifest = revalidate_randomization_manifest(manifest)
    object.__setattr__(
        forged_seed_manifest.seed_tree.children[0], "name", "wrong_name"
    )
    with pytest.raises(AlmondLabError) as exc_info:
        revalidate_randomization_manifest(forged_seed_manifest)
    assert exc_info.value.code == "RANDOMIZATION_INVALID"
    assert exc_info.value.field_path == "seed_tree"


@pytest.mark.parametrize("target", ["child_pool", "root_pool", "schema", "model"])
def test_manifest_revalidation_rejects_numeric_and_version_forgery(
    manifest, target: str
) -> None:
    """Catches equality-compatible floats or unfrozen manifest versions."""
    forged = revalidate_randomization_manifest(manifest)
    if target == "child_pool":
        object.__setattr__(forged.seed_tree.children[0], "pool_size", 4.0)
    elif target == "root_pool":
        object.__setattr__(forged.seed_tree, "pool_size", 4.0)
    elif target == "schema":
        object.__setattr__(forged, "schema_version", "2.0")
    else:
        object.__setattr__(forged, "model_version", "unregistered-model")
    with pytest.raises(AlmondLabError) as exc_info:
        revalidate_randomization_manifest(forged)
    assert exc_info.value.code == "RANDOMIZATION_INVALID"


def test_cohort_factory_rejects_unpermitted_manifest_movement(
    manifest, design_inputs
) -> None:
    """Catches cohort authority accepting a movement not allowed by its slot."""
    forged = revalidate_randomization_manifest(manifest)
    object.__setattr__(
        forged.records[0], "movement_schedule_id", "unpermitted-movement"
    )
    forged_records = [record.to_dict() for record in forged.records]
    object.__setattr__(
        forged,
        "allocation_sha256",
        sha256_bytes(canonical_json_bytes(forged_records)),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        cohort_identity_set(
            forged,
            baseline_roster=design_inputs.baseline_roster,
            position_map=design_inputs.position_map,
        )
    assert exc_info.value.code == "COHORT_IDENTITY_INVALID"


@pytest.mark.parametrize(
    "bad_seed",
    [True, "20260812", 1.5, -1, 10**10000],
    ids=["bool", "string", "float", "negative", "huge-int"],
)
def test_randomize_rejects_coercive_root_seed(
    config, design_inputs, bad_seed: object
) -> None:
    """Catches bool/string/float/negative seeds being silently coerced."""
    with pytest.raises(AlmondLabError) as exc_info:
        randomize(
            config,
            bad_seed,
            position_map=design_inputs.position_map,
            baseline_roster=design_inputs.baseline_roster,
        )
    assert exc_info.value.code == "DESIGN_INPUT_INVALID"
    assert exc_info.value.field_path == "root_seed"


@pytest.mark.parametrize(
    "bad_value",
    [True, "1.0", float("nan"), float("inf"), 10**10000],
    ids=["bool", "string", "nan", "infinity", "huge-int"],
)
def test_roster_rejects_bool_string_and_nonfinite_canopy(bad_value: object) -> None:
    """Catches coercive or nonfinite pretreatment eligibility values."""
    with pytest.raises(AlmondLabError) as exc_info:
        BaselinePlant(
            plant_id="physical-plant",
            group_id="C1",
            pretreatment_canopy=bad_value,
            baseline_canopy_stratum="lower_canopy",
            transformation_batch_block="batch_a",
            transformation_batch_id="physical-batch-a",
            transformation_event_id="physical-event",
            cohort_id="discovery",
        )
    assert exc_info.value.code == "ROSTER_INVALID"
    assert exc_info.value.field_path == "pretreatment_canopy"


def test_roster_accepts_large_but_finite_primitive_canopy() -> None:
    """Catches applying integer identity limits to a finite measurement."""
    plant = BaselinePlant(
        plant_id="large-finite-plant",
        group_id="C1",
        pretreatment_canopy=1.0e100,
        baseline_canopy_stratum="lower_canopy",
        transformation_batch_block="batch_a",
        transformation_batch_id="large-finite-batch",
        transformation_event_id="large-finite-event",
        cohort_id="discovery",
    )
    assert plant.pretreatment_canopy == 1.0e100


def test_position_exact_integers_reject_noninteroperable_values() -> None:
    """Catches huge exact schedule integers escaping canonical JSON limits."""
    with pytest.raises(AlmondLabError) as exc_info:
        PositionSlot(
            position_id="huge-slot",
            run_id="discovery_run_1",
            run_sequence_ordinal=10**10000,
            water_id="nonsaline_nutrient_matched_control",
            reservoir_id="huge-reservoir",
            water_batch_id="huge-water-batch",
            greenhouse_compartment_id="huge-compartment",
            bench_id="huge-bench",
            row=1,
            column=1,
            spatial_gradient_profile_id="huge-gradient",
            permitted_movement_schedule_ids=("huge-movement",),
            cohort_id="discovery",
        )
    assert exc_info.value.code == "POSITION_MAP_INVALID"
    assert exc_info.value.field_path == "run_sequence_ordinal"


def test_public_models_reject_duplicate_trimmed_and_mutable_nested_inputs() -> None:
    """Catches mutable payloads and IDs that normalize into collisions."""
    plant = BaselinePlant(
        plant_id="physical-plant",
        group_id="C1",
        pretreatment_canopy=1.0,
        baseline_canopy_stratum="lower_canopy",
        transformation_batch_block="batch_a",
        transformation_batch_id="physical-batch-a",
        transformation_event_id="physical-event",
        cohort_id="discovery",
    )
    with pytest.raises(AlmondLabError) as duplicate:
        BaselineRoster((plant, plant))
    with pytest.raises(AlmondLabError) as whitespace:
        replace(plant, plant_id=" physical-plant")
    with pytest.raises(AlmondLabError) as mutable:
        PositionSlot(
            position_id="slot-1",
            run_id="discovery_run_1",
            run_sequence_ordinal=1,
            water_id="nonsaline_nutrient_matched_control",
            reservoir_id="reservoir-1",
            water_batch_id="water-batch-1",
            greenhouse_compartment_id="compartment-a",
            bench_id="bench-a",
            row=1,
            column=1,
            spatial_gradient_profile_id="gradient-a",
            permitted_movement_schedule_ids=["movement-a"],  # type: ignore[arg-type]
            cohort_id="discovery",
        )
    assert duplicate.value.code == "ROSTER_INVALID"
    assert whitespace.value.code == "ROSTER_INVALID"
    assert mutable.value.code == "POSITION_MAP_INVALID"


def test_physical_roster_and_loop_metadata_reject_internal_reuse(
    config, design_inputs
) -> None:
    """Catches duplicate transformation events or per-plant loop relabeling."""
    plants = list(design_inputs.baseline_roster.plants)
    event_source = next(
        plant for plant in plants if plant.transformation_event_id is not None
    )
    event_target_index = next(
        index
        for index, plant in enumerate(plants)
        if plant.transformation_event_id is not None
        and plant.plant_id != event_source.plant_id
    )
    plants[event_target_index] = replace(
        plants[event_target_index],
        transformation_event_id=event_source.transformation_event_id,
    )
    with pytest.raises(AlmondLabError) as event_error:
        BaselineRoster(tuple(plants))
    assert event_error.value.code == "ROSTER_INVALID"
    assert event_error.value.field_path == "plants.transformation_event_id"

    slots = list(design_inputs.position_map.slots)
    slots[0] = replace(slots[0], water_batch_id="relabeled-water-batch")
    with pytest.raises(AlmondLabError) as loop_error:
        randomize(
            config,
            SEED,
            position_map=PositionMap(tuple(slots)),
            baseline_roster=design_inputs.baseline_roster,
        )
    assert loop_error.value.code == "POSITION_MAP_INVALID"
    assert loop_error.value.field_path == "position_map.slots.water_batch_id"


def test_models_and_nested_maps_are_deeply_immutable(manifest, full_spec) -> None:
    """Catches mutation of allocation, seed, manifest, or audit summaries."""
    audit = validate_experimental_units(manifest.records, full_spec)
    with pytest.raises((AttributeError, TypeError)):
        manifest.records[0].plant_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        manifest.input_sha256s["new"] = "0" * 64  # type: ignore[index]
    with pytest.raises((AttributeError, TypeError)):
        manifest.seed_tree.children += manifest.seed_tree.children  # type: ignore[misc]
    with pytest.raises(TypeError):
        audit.counts["biological_n"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        audit.counts["group_counts"]["C1"] = 0  # type: ignore[index]
    assert isinstance(manifest.input_sha256s, MappingProxyType)
    assert isinstance(audit.counts, MappingProxyType)


def test_fixture_mirrors_are_exact_and_all_anchors_are_consumed(design_inputs) -> None:
    """Catches stale package bytes or unvalidated fixture anchors."""
    packaged = resources.files("almondlab.resources").joinpath("fixtures")
    assert FIXTURE.read_bytes() == packaged.joinpath(FIXTURE.name).read_bytes()
    assert TRAP.read_bytes() == packaged.joinpath(TRAP.name).read_bytes()
    assert design_inputs.consumed_anchors == (
        "schema_version",
        "evidence_label",
        "cohort_id",
        "oracles",
        "baseline_roster",
        "position_map",
    )
    assert len(design_inputs.baseline_roster.plants) == 720
    assert len(design_inputs.position_map.slots) == 720
    assert set(design_inputs.source_sha256s) == {
        "paper1_small",
        "baseline_roster_raw",
        "position_map_raw",
    }
    assert all(len(digest) == 64 for digest in design_inputs.source_sha256s.values())


def test_shared_reservoir_csv_parser_rejects_header_cell_and_row_corruption(
    tmp_path: Path,
) -> None:
    """Catches duplicate headers, excess cells, empty cells, or hidden extra rows."""
    original = TRAP.read_text(encoding="utf-8")
    header, *rows = original.splitlines()
    corruptions = {
        "duplicate-header": header.replace("plant_id", "allocation_id", 1)
        + "\n"
        + "\n".join(rows)
        + "\n",
        "excess-cell": header + "\n" + rows[0] + ",extra\n" + "\n".join(rows[1:]) + "\n",
        "empty-cell": header + "\n" + rows[0].replace("trap-plant-01", "", 1) + "\n" + "\n".join(rows[1:]) + "\n",
        "extra-row": original + rows[0] + "\n",
    }
    for name, contents in corruptions.items():
        path = tmp_path / f"{name}.csv"
        path.write_text(contents, encoding="utf-8", newline="")
        with pytest.raises(AlmondLabError) as exc_info:
            load_shared_reservoir_records(path)
        assert exc_info.value.code == "SHARED_RESERVOIR_FIXTURE_INVALID"


def test_separate_blinded_projection_excludes_treatment_identity(manifest, escrow_authority) -> None:
    """Catches staff-facing export leaking treatment or batch assignments."""
    projection = blinded_projection(manifest, escrow_authority=escrow_authority)
    payload = json.loads(projection.canonical_json_bytes())
    assert len(payload["records"]) == 720
    serialized = canonical_json_bytes(payload)
    for forbidden in (
        b'"group_id"',
        b'"water_id"',
        b'"transformation_batch_id"',
        b'"transformation_batch_block"',
        b'"transformation_event_id"',
    ):
        assert forbidden not in serialized


def test_acceptance_6_and_14_publish_together_and_failure_is_atomic(
    tmp_path: Path,
) -> None:
    """Catches caller-set pass state or partially published acceptance evidence."""
    successful = tmp_path / "successful-run"
    successful.mkdir()
    records = publish_design_acceptance(
        successful,
        config_path=CONFIG,
        design_fixture_path=FIXTURE,
        trap_path=TRAP,
        blinding_escrow_authority=BlindingEscrowAuthority(secret_key=BLINDING_KEY),
    )
    assert tuple(record.acceptance_test for record in records) == (6, 14)
    assert all(record.passed for record in records)
    assert all(record.evidence_label is EvidenceLabel.SYNTHETIC_ONLY for record in records)
    assert {path.name for path in (successful / "verification").iterdir()} == {
        "allocation_manifest.json",
        "blinded_allocation.json",
        "test_06.json",
        "test_14.json",
    }
    document = json.loads(
        (successful / "verification" / "test_06.json").read_text(encoding="utf-8")
    )
    assert document["passed"] is True
    assert document["observed_value"]["spatial_blocking"] is True
    assert document["oracle"]["spatial_blocking"] is True
    assert document["observed_value"]["spatial_group_balance"] is True
    assert document["observed_value"]["spatial_stratum_balance"] is True
    assert document["observed_value"]["spatial_batch_balance"] is True
    assert document["observed_value"]["spatial_balance_maxima"] == DISCOVERY_SPATIAL_MAXIMA
    assert document["oracle"]["spatial_balance_maxima"] == DISCOVERY_SPATIAL_MAXIMA
    assert document["auxiliary_artifacts_sha256s"]["allocation_manifest.json"] == sha256_file(
        successful / "verification" / "allocation_manifest.json"
    )

    failed = tmp_path / "failed-run"
    failed.mkdir()

    def inject(stage: str) -> None:
        if stage == "after_test_06":
            raise OSError("injected publication failure")

    with pytest.raises(OSError, match="injected publication failure"):
        publish_design_acceptance(
            failed,
            config_path=CONFIG,
            design_fixture_path=FIXTURE,
            trap_path=TRAP,
            blinding_escrow_authority=BlindingEscrowAuthority(secret_key=BLINDING_KEY),
            failure_injector=inject,
        )
    assert not (failed / "verification").exists()
    assert list(failed.iterdir()) == []


def test_manifest_hashes_all_scientific_fields(manifest) -> None:
    """Catches allocation hashes that omit a scientific assignment field."""
    payload = manifest.to_dict()
    records = payload["records"]
    original = sha256_bytes(canonical_json_bytes(records))
    records[0]["baseline_canopy_stratum"] = "mutated-stratum"
    changed = sha256_bytes(canonical_json_bytes(records))
    assert original == manifest.allocation_sha256
    assert changed != original


def test_no_winner_or_outcome_claim_fields_are_published(manifest) -> None:
    """Catches randomization being misrepresented as biological evidence."""
    payload = manifest.canonical_json_bytes()
    for forbidden in (
        b'"winner"',
        b'"best_candidate"',
        b'"salt_tolerance"',
        b'"survival_prediction"',
    ):
        assert forbidden not in payload


def test_staff_projection_uses_only_opaque_codes_bound_to_manifest(manifest, escrow_authority) -> None:
    """Catches semantic physical/treatment IDs leaking into staff aliases."""
    projection = blinded_projection(manifest, escrow_authority=escrow_authority)
    assert projection.manifest_sha256 == sha256_bytes(manifest.canonical_json_bytes())
    assert projection.model_version == "paper1_staff_opaque_projection_v1"
    assert len(projection.records) == 720
    assert len({record.staff_allocation_code for record in projection.records}) == 720
    assert len({record.staff_specimen_code for record in projection.records}) == 720
    assert len({record.staff_location_code for record in projection.records}) == 720
    assert len({record.blinded_treatment_code for record in projection.records}) == 720
    for public_record in projection.records:
        for value in public_record.to_dict().values():
            if type(value) is str and value != EvidenceLabel.SYNTHETIC_ONLY.value:
                assert value.startswith("OPQ-")
    public_values = {
        value
        for public_record in projection.records
        for value in public_record.to_dict().values()
    }
    for private_record in manifest.records:
        for semantic in (
            private_record.allocation_id,
            private_record.plant_id,
            private_record.group_id,
            private_record.water_id,
            private_record.run_id,
            private_record.reservoir_id,
            private_record.position_id,
            private_record.greenhouse_compartment_id,
            private_record.bench_id,
            private_record.cohort_id,
        ):
            assert semantic not in public_values


def test_blinded_models_reject_forgery_and_copy_bypass(manifest, escrow_authority) -> None:
    """Catches mutable, subclassed, stale, or object.__setattr__-forged projections."""
    projection = blinded_projection(manifest, escrow_authority=escrow_authority)
    first = projection.records[0]
    with pytest.raises(AlmondLabError) as exc_info:
        replace(first, staff_allocation_code="disc-C1-A-01")
    assert exc_info.value.code == "BLINDED_PROJECTION_INVALID"
    with pytest.raises(AlmondLabError):
        BlindedProjection(
            schema_version="1.0",
            model_version="paper1_staff_opaque_projection_v1",
            manifest_sha256=projection.manifest_sha256,
            records=list(projection.records),  # type: ignore[arg-type]
            projection_sha256=projection.projection_sha256,
            evidence_label=EvidenceLabel.SYNTHETIC_ONLY,
        )
    forged = replace(projection)
    object.__setattr__(forged.records[0], "staff_location_code", "OPQ-" + "0" * 32)
    with pytest.raises(AlmondLabError) as exc_info:
        revalidate_blinded_projection(
            forged, manifest=manifest, escrow_authority=escrow_authority
        )
    assert exc_info.value.code == "BLINDED_PROJECTION_INVALID"


def test_discovery_spatial_restriction_and_independent_audit(manifest, full_spec) -> None:
    """Catches unconstrained loop-wide position shuffling or a record-derived oracle."""
    for loop in {
        (record.run_id, record.greenhouse_compartment_id, record.water_id, record.reservoir_id)
        for record in manifest.records
    }:
        loop_rows = [
            record
            for record in manifest.records
            if (
                record.run_id,
                record.greenhouse_compartment_id,
                record.water_id,
                record.reservoir_id,
            ) == loop
        ]
        for row_number in range(1, 6):
            assert {record.group_id for record in loop_rows if record.row == row_number} == set(GROUPS)
        for group in GROUPS:
            columns = [record.column for record in loop_rows if record.group_id == group]
            assert len(columns) == len(set(columns))
    assert validate_experimental_units(manifest.records, full_spec).checks["spatial_blocking"] is True

    rows = list(manifest.records)
    first_index = next(i for i, record in enumerate(rows) if record.row == 1)
    first = rows[first_index]
    second_index = next(
        i
        for i, record in enumerate(rows)
        if record.run_id == first.run_id
        and record.water_id == first.water_id
        and record.reservoir_id == first.reservoir_id
        and record.row == 2
        and record.group_id != first.group_id
    )
    second = rows[second_index]
    physical_fields = (
        "run_id", "run_sequence_ordinal", "water_id", "reservoir_id", "water_batch_id",
        "greenhouse_compartment_id", "bench_id", "row", "column", "position_id",
        "spatial_gradient_profile_id", "movement_schedule_id", "cohort_id",
    )
    first_values = {name: getattr(second, name) for name in physical_fields}
    second_values = {name: getattr(first, name) for name in physical_fields}
    rows[first_index] = replace(first, **first_values)
    rows[second_index] = replace(second, **second_values)
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(tuple(rows), full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.spatial_block"


@pytest.mark.parametrize("stratum", ["lower_canopy", "fictional_canopy"])
def test_audit_rejects_missing_or_fictional_stratum_categories(
    manifest, full_spec, stratum: str
) -> None:
    """Catches an all-one-category or fictional vocabulary passing a balance range test."""
    with pytest.raises(AlmondLabError) as exc_info:
        forged = tuple(replace(record, baseline_canopy_stratum=stratum) for record in manifest.records)
        validate_experimental_units(forged, full_spec)
    assert exc_info.value.code in {"ALLOCATION_RECORD_INVALID", "EXPERIMENTAL_UNIT_INVALID"}
    assert exc_info.value.field_path == "baseline_canopy_stratum" or exc_info.value.field_path == "records.baseline_canopy_stratum"


def test_confirmation_crosses_each_registered_water_over_every_later_run() -> None:
    """Catches water/run confounding despite six total loops per water."""
    confirmation, roster, positions = _confirmation_inputs()
    slots = tuple(
        replace(
            slot,
            run_id=("confirmation_run_a" if slot.water_id == confirmation.water_ids[0] else "confirmation_run_b"),
            run_sequence_ordinal=(3 if slot.water_id == confirmation.water_ids[0] else 4),
            greenhouse_compartment_id=("confirm-compartment-1" if slot.water_id == confirmation.water_ids[0] else "confirm-compartment-2"),
        )
        for slot in positions.slots
    )
    with pytest.raises(AlmondLabError) as exc_info:
        randomize(
            confirmation,
            SEED,
            position_map=PositionMap(slots),
            baseline_roster=roster,
        )
    assert exc_info.value.code == "POSITION_MAP_INVALID"
    assert exc_info.value.field_path == "position_map.slots.run_id"

    valid_manifest = randomize(
        confirmation,
        SEED,
        position_map=positions,
        baseline_roster=roster,
    )
    confounded_records = tuple(
        replace(
            record,
            run_id=("confirmation_run_a" if record.water_id == confirmation.water_ids[0] else "confirmation_run_b"),
            run_sequence_ordinal=(3 if record.water_id == confirmation.water_ids[0] else 4),
        )
        for record in valid_manifest.records
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(
            confounded_records,
            ExperimentalUnitSpec(
                population=AnalysisPopulation.COMPOSITE_ROOT,
                expected_groups=confirmation.full_allocation_groups,
                expected_water_ids=confirmation.water_ids,
                expected_run_ids=confirmation.runs,
                expected_reservoirs_per_water=6,
                expected_plants_per_group_reservoir=5,
                minimum_run_sequence_ordinal=3,
            ),
        )
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.run_id"


@pytest.mark.parametrize(
    ("changes", "field_path"),
    [
        ({"reservoirs_per_water": 6.0}, "reservoirs_per_water"),
        ({"schema_version": type("HostileText", (str,), {})("1.0")}, "schema_version"),
        ({"construct_level_unit": type("HostileText", (str,), {})("independently_transformed_plant")}, "construct_level_unit"),
        ({"water_treatment_unit": type("HostileText", (str,), {})("reservoir")}, "water_treatment_unit"),
        ({"water_ids": ("arbitrary_water_a", "arbitrary_water_b")}, "water_ids"),
    ],
)
def test_confirmation_freezes_exact_primitives_and_registered_waters(
    changes: dict[str, object], field_path: str
) -> None:
    """Catches equality-based coercion and arbitrary confirmation chemistry IDs."""
    confirmation, _, _ = _confirmation_inputs()
    with pytest.raises(AlmondLabError) as exc_info:
        replace(confirmation, **changes)
    assert exc_info.value.code == "CONFIRMATION_DESIGN_INVALID"
    assert exc_info.value.field_path == field_path


def test_record_only_audit_rejects_per_plant_water_batch_relabel(manifest) -> None:
    """Catches a loop relabeled into multiple water batches without a position map."""
    changed = _replace_record(manifest.records, 0, water_batch_id="fictional-water-batch")
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(
            changed,
            ExperimentalUnitSpec(population=AnalysisPopulation.COMPOSITE_ROOT),
        )
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.water_batch_id"


@pytest.mark.parametrize(
    "payload",
    [
        "root: &shared {value: 1}\ncopy: *shared\n",
        "root: &cycle [*cycle]\n",
        "root: !!python/object/apply:builtins.str [unsafe]\n",
        "? [not, a, string]\n: value\n",
        "root: " + "[" * 80 + "0" + "]" * 80 + "\n",
    ],
    ids=("alias", "cycle", "hostile-tag", "non-string-key", "depth"),
)
def test_randomization_fixture_yaml_is_bounded_and_alias_safe(
    tmp_path: Path, payload: str
) -> None:
    """Catches YAML graph expansion, hostile tags, keys, or parser recursion leakage."""
    path = tmp_path / "hostile.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(AlmondLabError) as exc_info:
        load_randomization_fixture(path)
    assert exc_info.value.code == "RANDOMIZATION_FIXTURE_INVALID"


def test_randomization_fixture_rejects_excessive_node_count(tmp_path: Path) -> None:
    """Catches compact but excessive YAML documents before object construction."""
    path = tmp_path / "too-many-nodes.yaml"
    path.write_text("items:\n" + "".join("  - x\n" for _ in range(40000)), encoding="utf-8")
    with pytest.raises(AlmondLabError) as exc_info:
        load_randomization_fixture(path)
    assert exc_info.value.code == "RANDOMIZATION_FIXTURE_INVALID"


def _longest_equal_run(values: list[object]) -> int:
    longest = current = 0
    previous: object = object()
    for value in values:
        current = current + 1 if value == previous else 1
        longest = max(longest, current)
        previous = value
    return longest


def test_staff_order_is_keyed_permuted_and_escrow_only(
    manifest, escrow_authority
) -> None:
    """Catches manifest/group/cell order surviving under opaque-looking labels."""
    first = blinded_projection(manifest, escrow_authority=escrow_authority)
    second = blinded_projection(manifest, escrow_authority=escrow_authority)
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    crosswalk = blinding_escrow_crosswalk(
        manifest, escrow_authority=escrow_authority
    )
    crosswalk_by_code = {
        record.staff_allocation_code: record.private_allocation_id
        for record in crosswalk
    }
    decoded = [
        crosswalk_by_code[record.staff_allocation_code] for record in first.records
    ]
    manifest_order = [record.allocation_id for record in manifest.records]
    assert decoded != manifest_order
    index_by_id = {
        allocation_id: index for index, allocation_id in enumerate(manifest_order)
    }
    decoded_indices = [index_by_id[allocation_id] for allocation_id in decoded]
    assert abs(float(np.corrcoef(np.arange(720), decoded_indices)[0, 1])) < 0.10
    assert sum(
        left == right for left, right in zip(decoded, manifest_order, strict=True)
    ) <= 5
    private_by_id = {record.allocation_id: record for record in manifest.records}
    decoded_groups = [private_by_id[allocation_id].group_id for allocation_id in decoded]
    decoded_cells = [
        (
            private_by_id[allocation_id].run_id,
            private_by_id[allocation_id].water_id,
            private_by_id[allocation_id].reservoir_id,
        )
        for allocation_id in decoded
    ]
    assert _longest_equal_run(decoded_groups) <= 4
    assert _longest_equal_run(decoded_cells) <= 3

    serialized = first.canonical_json_bytes()
    assert BLINDING_KEY.hex().encode() not in serialized
    assert str(manifest.root_seed).encode() not in serialized
    assert b'"secret_key"' not in serialized
    changed_authority = BlindingEscrowAuthority(
        secret_key=hashlib.sha256(b"independent changed authority").digest()
    )
    assert blinded_projection(
        manifest, escrow_authority=changed_authority
    ).canonical_json_bytes() != serialized


def test_staff_projection_revalidation_rejects_caller_row_order(
    manifest, escrow_authority
) -> None:
    """Catches a caller rebuilding opaque records in manifest or arbitrary row order."""
    projection = blinded_projection(manifest, escrow_authority=escrow_authority)
    reordered_records = tuple(reversed(projection.records))
    reordered = replace(
        projection,
        records=reordered_records,
        projection_sha256=sha256_bytes(
            canonical_json_bytes([record.to_dict() for record in reordered_records])
        ),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        revalidate_blinded_projection(
            reordered,
            manifest=manifest,
            escrow_authority=escrow_authority,
        )
    assert exc_info.value.code == "BLINDED_PROJECTION_INVALID"


def test_blinding_authority_is_exact_private_seed_material(manifest) -> None:
    """Catches caller-coercible or weak escrow authority at the staff boundary."""
    for invalid in (
        b"short",
        b"\0" * 32,
        b"x" * 32,
        bytearray(BLINDING_KEY),
        BLINDING_KEY.hex(),
    ):
        with pytest.raises(AlmondLabError) as exc_info:
            BlindingEscrowAuthority(secret_key=invalid)  # type: ignore[arg-type]
        assert exc_info.value.code == "BLINDING_ESCROW_INVALID"
        assert exc_info.value.field_path == "secret_key"
        assert BLINDING_KEY.hex() not in str(exc_info.value)
    authority = BlindingEscrowAuthority(secret_key=BLINDING_KEY)
    assert "4ddc4d" not in repr(authority)
    forged = replace(authority)
    object.__setattr__(forged, "secret_key", bytearray(BLINDING_KEY))
    with pytest.raises(AlmondLabError) as exc_info:
        blinded_projection(
            manifest,
            escrow_authority=forged,
        )
    assert exc_info.value.code == "BLINDING_ESCROW_INVALID"


def test_generated_blinding_authority_is_nontrivial_and_private(manifest) -> None:
    """Catches deterministic/root-derived production escrow key generation."""
    generated = generate_blinding_escrow_authority()
    assert type(generated.secret_key) is bytes
    assert len(generated.secret_key) == 32
    assert len(set(generated.secret_key)) > 1
    guessed_from_root = BlindingEscrowAuthority(
        secret_key=hashlib.sha256(str(manifest.root_seed).encode()).digest()
    )
    assert blinded_projection(
        manifest, escrow_authority=generated
    ).canonical_json_bytes() != blinded_projection(
        manifest, escrow_authority=guessed_from_root
    ).canonical_json_bytes()


def test_escrow_crosswalk_is_deeply_immutable_exhaustive_and_bijective(
    manifest, escrow_authority
) -> None:
    """Catches partial or caller-mutable private staff-to-manifest authority."""
    crosswalk = blinding_escrow_crosswalk(
        manifest, escrow_authority=escrow_authority
    )
    assert len(crosswalk) == 720
    assert type(crosswalk) is tuple
    assert len({record.staff_allocation_code for record in crosswalk}) == 720
    assert len({record.staff_specimen_code for record in crosswalk}) == 720
    assert len({record.staff_location_code for record in crosswalk}) == 720
    assert len({record.private_allocation_id for record in crosswalk}) == 720
    assert len({record.private_plant_id for record in crosswalk}) == 720
    assert len({record.private_position_id for record in crosswalk}) == 720
    assert {record.private_allocation_id for record in crosswalk} == {
        record.allocation_id for record in manifest.records
    }
    with pytest.raises((AttributeError, TypeError)):
        crosswalk[0].private_plant_id = "forged"  # type: ignore[misc]


DISCOVERY_SPATIAL_MAXIMA = {
    "row_group_count_difference": 0,
    "column_group_max_count": 1,
    "compartment_group_count_difference": 0,
    "row_stratum_count_difference": 1,
    "column_stratum_count_difference": 1,
    "compartment_stratum_count_difference": 1,
    "row_transformed_batch_count_difference": 1,
    "column_transformed_batch_count_difference": 1,
    "compartment_transformed_batch_count_difference": 1,
    "row_not_applicable_max_count": 2,
    "column_not_applicable_max_count": 2,
    "compartment_not_applicable_max_count": 10,
}


def test_joint_spatial_blocking_has_literal_discovery_maxima(
    manifest, full_spec
) -> None:
    """Catches group-only placement followed by arbitrary stratum/batch popping."""
    audit = validate_experimental_units(manifest.records, full_spec)
    assert dict(audit.counts["spatial_balance_maxima"]) == DISCOVERY_SPATIAL_MAXIMA
    assert audit.checks["spatial_group_balance"] is True
    assert audit.checks["spatial_stratum_balance"] is True
    assert audit.checks["spatial_batch_balance"] is True


def _swap_fields(
    rows: tuple[AllocationRecord, ...],
    first: AllocationRecord,
    second: AllocationRecord,
    fields: tuple[str, ...],
) -> tuple[AllocationRecord, ...]:
    replacements = {
        first.allocation_id: replace(
            first, **{field: getattr(second, field) for field in fields}
        ),
        second.allocation_id: replace(
            second, **{field: getattr(first, field) for field in fields}
        ),
    }
    return tuple(replacements.get(record.allocation_id, record) for record in rows)


def test_joint_spatial_audit_rejects_coordinated_stratum_relabel(
    manifest, full_spec
) -> None:
    """Catches row/group/cell-preserving canopy-stratum spatial corruption."""
    loop = manifest.records[0]
    loop_rows = [
        record for record in manifest.records
        if (record.run_id, record.water_id, record.reservoir_id)
        == (loop.run_id, loop.water_id, loop.reservoir_id)
    ]
    lower_by_row = Counter(record.row for record in loop_rows if record.baseline_canopy_stratum == "lower_canopy")
    candidates = [
        (max(abs(2 * count - 9) for count in {
            **lower_by_row,
            left.row: lower_by_row[left.row] - 1,
            right.row: lower_by_row[right.row] + 1,
        }.values()), left, right)
        for left in loop_rows
        for right in loop_rows
        if left.group_id == right.group_id
        and left.row != right.row
        and left.baseline_canopy_stratum == "lower_canopy"
        and right.baseline_canopy_stratum == "upper_canopy"
    ]
    _, left, right = max(candidates, key=lambda item: item[0])
    corrupted = _swap_fields(
        manifest.records, left, right, ("baseline_canopy_stratum",)
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.spatial_stratum_block"


def test_joint_spatial_audit_rejects_coordinated_batch_relabel(
    manifest, full_spec
) -> None:
    """Catches row/group/cell-preserving transformation-batch spatial corruption."""
    loop = manifest.records[0]
    loop_rows = [
        record for record in manifest.records
        if (record.run_id, record.water_id, record.reservoir_id)
        == (loop.run_id, loop.water_id, loop.reservoir_id)
    ]
    batch_a_by_row = Counter(
        record.row for record in loop_rows
        if record.transformation_batch_block == "batch_a"
    )
    transformed_by_row = Counter(
        record.row for record in loop_rows
        if record.transformation_batch_block is not None
    )
    candidates = [
        (max(
            abs(2 * count - transformed_by_row[row])
            for row, count in {
                **batch_a_by_row,
                left.row: batch_a_by_row[left.row] - 1,
                right.row: batch_a_by_row[right.row] + 1,
            }.items()
        ), left, right)
        for left in loop_rows
        for right in loop_rows
        if left.group_id == right.group_id
        and left.row != right.row
        and left.transformation_batch_block == "batch_a"
        and right.transformation_batch_block == "batch_b"
    ]
    _, left, right = max(candidates, key=lambda item: item[0])
    corrupted = _swap_fields(
        manifest.records,
        left,
        right,
        ("transformation_batch_block", "transformation_batch_id"),
    )
    with pytest.raises(AlmondLabError) as exc_info:
        validate_experimental_units(corrupted, full_spec)
    assert exc_info.value.code == "EXPERIMENTAL_UNIT_INVALID"
    assert exc_info.value.field_path == "records.spatial_batch_block"


def _poison_cached_template(
    dimension: str, *, poison_digest: bool = False
) -> tuple[object, tuple[tuple[int, int], ...]]:
    """Replace one cached primitive bijection without changing its cardinality."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    entries = object.__getattribute__(
        cache, "_JointSpatialTemplateCache__entries"
    )
    for key, entry in entries.items():
        value = entry.template
        categories, geometry = key
        for first_index in range(len(value)):
            first_entry, first_slot = value[first_index]
            first_category = categories[first_entry]
            first_group = geometry[first_slot][0]
            for second_index in range(first_index + 1, len(value)):
                second_entry, second_slot = value[second_index]
                second_category = categories[second_entry]
                second_group = geometry[second_slot][0]
                if dimension == "stratum":
                    selected = (
                        first_group == second_group
                        and first_category[1] != second_category[1]
                    )
                elif dimension == "transformed_batch":
                    selected = (
                        first_group == second_group
                        and first_category[2] in {"batch_a", "batch_b"}
                        and second_category[2] in {"batch_a", "batch_b"}
                        and first_category[2] != second_category[2]
                    )
                elif dimension == "not_applicable":
                    selected = (first_category[2] == "NA") != (
                        second_category[2] == "NA"
                    )
                elif dimension == "same_category":
                    selected = (
                        first_group == second_group
                        and first_category == second_category
                    )
                else:  # pragma: no cover - test helper misuse
                    raise AssertionError(f"unknown poison dimension: {dimension}")
                if not selected:
                    continue
                poisoned = list(value)
                poisoned[first_index] = (first_entry, second_slot)
                poisoned[second_index] = (second_entry, first_slot)
                poisoned_template = tuple(poisoned)
                entries[key] = replace(
                    entry,
                    template=poisoned_template,
                    integrity_digest=(
                        b"\0" * 32
                        if poison_digest
                        else entry.integrity_digest
                    ),
                )
                return key, poisoned_template
    raise AssertionError(f"fixture lacks a {dimension} cache-poison pair")


@pytest.mark.parametrize(
    "dimension", ("stratum", "transformed_batch", "not_applicable")
)
def test_primitive_cache_poison_cannot_override_spatial_authority(
    config, design_inputs, full_spec, dimension
) -> None:
    """Catches unsigned cached bijections overriding the independent spatial audit."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    cache.clear()
    expected = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    _poison_cached_template(dimension)

    received = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )

    assert received.allocation_sha256 == expected.allocation_sha256
    audit = validate_experimental_units(received.records, full_spec)
    assert dict(audit.counts["spatial_balance_maxima"]) == DISCOVERY_SPATIAL_MAXIMA


def test_same_category_cache_swap_cannot_change_deterministic_manifest(
    config, design_inputs
) -> None:
    """Catches cache poison that preserves all categories and spatial marginals."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    cache.clear()
    expected = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    _poison_cached_template("same_category")

    received = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )

    assert received.allocation_sha256 == expected.allocation_sha256
    assert received.canonical_json_bytes() == expected.canonical_json_bytes()


def test_poisoned_cache_value_and_digest_cannot_forge_integrity(
    config, design_inputs
) -> None:
    """Catches replacing both the exact template and its stored digest."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    cache.clear()
    expected = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    _poison_cached_template("same_category", poison_digest=True)

    received = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )

    assert received.canonical_json_bytes() == expected.canonical_json_bytes()


def test_joint_spatial_cache_secret_is_absent_from_repr_serialization_and_errors() -> None:
    """Catches process HMAC authority escaping through generic object surfaces."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    secret = object.__getattribute__(
        cache, "_JointSpatialTemplateCache__integrity_key"
    )
    assert type(secret) is bytes
    assert len(secret) == 32
    assert secret.hex() not in repr(cache)

    with pytest.raises(TypeError) as serialization_error:
        pickle.dumps(cache)
    with pytest.raises(TypeError) as boundary_error:
        cache.put(("not-a-cache-key",), ())  # type: ignore[arg-type]

    for error in (serialization_error.value, boundary_error.value):
        rendered = f"{error!r} {error}"
        assert secret.hex() not in rendered
        assert repr(secret) not in rendered


@pytest.mark.parametrize(
    "dimension", ("stratum", "transformed_batch", "not_applicable")
)
def test_postbinding_oracle_recovers_if_cache_integrity_layer_is_bypassed(
    config, design_inputs, full_spec, dimension, monkeypatch
) -> None:
    """Catches trusting a cache hit without an independent complete spatial oracle."""

    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    cache.clear()
    expected = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    poisoned_key, poisoned_template = _poison_cached_template(dimension)
    original_get = type(cache).get
    delivered = False

    def bypassed_get(self, key):
        nonlocal delivered
        if not delivered and key == poisoned_key:
            delivered = True
            return poisoned_template
        return original_get(self, key)

    monkeypatch.setattr(type(cache), "get", bypassed_get)
    received = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    )

    assert delivered is True
    assert received.canonical_json_bytes() == expected.canonical_json_bytes()
    audit = validate_experimental_units(received.records, full_spec)
    assert dict(audit.counts["spatial_balance_maxima"]) == DISCOVERY_SPATIAL_MAXIMA


def test_joint_spatial_cache_is_bounded_pure_and_cross_input_safe(
    config, design_inputs, manifest, full_spec, monkeypatch
) -> None:
    """Catches cached plant/slot objects, incomplete keys, or cross-design contamination."""
    cache = design_module._JOINT_SPATIAL_TEMPLATE_CACHE
    cache.clear()
    monkeypatch.setattr(design_module, "JOINT_SPATIAL_CACHE_MAXSIZE", 2)
    baseline_by_seed = {}
    for seed in (SEED, SEED + 1, SEED + 2):
        generated = randomize(
            config,
            seed,
            position_map=design_inputs.position_map,
            baseline_roster=design_inputs.baseline_roster,
        )
        baseline_by_seed[seed] = generated.canonical_json_bytes()
        validate_experimental_units(generated.records, full_spec)
        assert len(cache) <= 2
    regenerated = randomize(
        config,
        SEED,
        position_map=PositionMap(tuple(reversed(design_inputs.position_map.slots))),
        baseline_roster=BaselineRoster(tuple(reversed(design_inputs.baseline_roster.plants))),
    )
    assert regenerated.canonical_json_bytes() == baseline_by_seed[SEED]
    assert len(cache) <= 2

    renamed_map = PositionMap(
        tuple(
            replace(
                slot,
                greenhouse_compartment_id="renamed-" + slot.greenhouse_compartment_id,
                bench_id="renamed-" + slot.bench_id,
                row=slot.row + 10,
                column=slot.column + 20,
            )
            for slot in design_inputs.position_map.slots
        )
    )
    renamed = randomize(
        config,
        SEED,
        position_map=renamed_map,
        baseline_roster=design_inputs.baseline_roster,
    )
    assert renamed.canonical_json_bytes() != baseline_by_seed[SEED]
    assert min(record.row for record in renamed.records) == 11
    assert min(record.column for record in renamed.records) == 21
    validate_experimental_units(
        renamed.records,
        ExperimentalUnitSpec.from_design(config, position_map=renamed_map),
    )
    assert len(cache) <= 2

    forged_map = PositionMap(tuple(replace(slot) for slot in design_inputs.position_map.slots))
    object.__setattr__(forged_map.slots[0], "row", "forged")
    with pytest.raises(AlmondLabError) as exc_info:
        randomize(
            config,
            SEED,
            position_map=forged_map,
            baseline_roster=design_inputs.baseline_roster,
        )
    assert exc_info.value.code == "POSITION_MAP_INVALID"

    confirmation, confirmation_roster, confirmation_positions = _confirmation_inputs(
        selected_candidates=("C1",), plants_per_cell=5
    )
    confirmation_manifest = randomize(
        confirmation,
        SEED,
        position_map=confirmation_positions,
        baseline_roster=confirmation_roster,
    )
    assert len(confirmation_manifest.records) == 120
    validate_experimental_units(
        confirmation_manifest.records,
        ExperimentalUnitSpec.from_confirmation_design(
            confirmation, position_map=confirmation_positions
        ),
    )
    assert len(cache) <= 2

    cache_text = repr(cache)
    assert "disc-C1-001" not in cache_text
    assert "disc-r1-w1-res01-slot01" not in cache_text
    for key, entry in cache.items():
        assert type(key) is tuple
        assert type(entry.template) is tuple
        assert type(entry.integrity_digest) is bytes
        assert len(entry.integrity_digest) == 32
        assert all(type(pair) is tuple for pair in entry.template)
        assert all(
            type(index) is int
            for pair in entry.template
            for index in pair
        )


def test_cached_and_fresh_process_manifests_are_identical(config, design_inputs) -> None:
    """Catches process-local cache history changing scientific manifest bytes."""
    sequential = randomize(
        config,
        SEED,
        position_map=design_inputs.position_map,
        baseline_roster=design_inputs.baseline_roster,
    ).allocation_sha256
    script = (
        "from pathlib import Path; "
        "from almondlab.design import load_randomization_fixture, randomize; "
        "from almondlab.paper1_contracts import load_paper1_design; "
        "c=load_paper1_design(Path('configs/experiment_paper1.yaml')); "
        "i=load_randomization_fixture(Path('tests/fixtures/paper1_small.yaml')); "
        "print(randomize(c,20260812,position_map=i.position_map,"
        "baseline_roster=i.baseline_roster).allocation_sha256)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stderr == ""
    assert completed.stdout.strip() == sequential
