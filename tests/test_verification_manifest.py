from importlib import resources

import hypothesis
import yaml
from hypothesis import Phase, given, seed, settings, strategies as st


def _generated_examples(candidates: tuple[object, ...], seed_value: int) -> list[object]:
    observed: list[object] = []

    @seed(seed_value)
    @settings(
        max_examples=2,
        database=None,
        deadline=None,
        phases=(Phase.generate,),
    )
    @given(st.sampled_from(candidates))
    def generate(candidate: object) -> None:
        observed.append(candidate)

    generate()
    return observed


def test_frozen_conservation_manifest_is_reproducible_from_pinned_hypothesis() -> None:
    manifest = yaml.safe_load(
        resources.files("almondlab.resources")
        .joinpath("fixtures/conservation_case_manifest.yaml")
        .read_bytes()
    )
    generator = manifest["generator"]

    assert generator == {
        "name": "hypothesis",
        "version": hypothesis.__version__,
        "properties": {
            "blend": {"seed": 20260814, "max_examples": 2, "database": None, "deadline": None},
            "flow": {"seed": 20260812, "max_examples": 2, "database": None, "deadline": None},
            "ro": {"seed": 20260813, "max_examples": 2, "database": None, "deadline": None},
        },
    }
    assert {
        property_id: [case["id"] for case in manifest["cases"][property_id]]
        for property_id in ("blend", "flow", "ro")
    } == {
        "blend": ["blend_seed_20260814_01", "blend_seed_20260814_02"],
        "flow": ["flow_seed_20260812_01", "flow_seed_20260812_02"],
        "ro": ["ro_seed_20260813_01", "ro_seed_20260813_02"],
    }

    flow_candidates = (
        (12.0, 3.0, 2.0, 1.0),
        (25.0, 5.0, 1.5, 2.0),
        (18.0, 2.0, 1.0, 3.0),
        (30.0, 10.0, 4.0, 1.0),
    )
    ro_candidates = (
        (12.0, 0.25, 0.90, 0.80),
        (40.0, 0.75, 0.25, 1.0),
        (25.0, 0.50, 0.50, 0.75),
        (10.0, 0.60, 1.0, 0.0),
    )
    blend_candidates = (
        (1.0, 3.0),
        (5.0, 2.0),
        (2.0, 5.0),
        (4.0, 1.0),
    )

    assert [
        (
            case["source_volume_l"],
            case["target_volume_l"],
            case["rate_l_per_hour"],
            case["duration_hours"],
        )
        for case in manifest["cases"]["flow"]
    ] == _generated_examples(flow_candidates, 20260812)
    assert [
        (
            case["feed_volume_l"],
            case["recovery"],
            case["rejection"]["na"],
            case["rejection"]["cl"],
        )
        for case in manifest["cases"]["ro"]
    ] == _generated_examples(ro_candidates, 20260813)
    assert [tuple(case["volumes_l"]) for case in manifest["cases"]["blend"]] == (
        _generated_examples(blend_candidates, 20260814)
    )
