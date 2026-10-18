"""Colour conversion and the lookalike scoring heuristic."""

from __future__ import annotations

import color as colour
import scoring


def test_white_converts_to_the_lab_origin():
    lab_l, lab_a, lab_b = colour.srgb_to_lab(255, 255, 255)
    assert abs(lab_l - 100.0) < 0.5
    assert abs(lab_a) < 0.5
    assert abs(lab_b) < 0.5


def test_hex_and_rgb_paths_agree():
    assert colour.hex_to_lab("#EDE0B8") == colour.srgb_to_lab(0xED, 0xE0, 0xB8)
    assert colour.rgb_to_hex(colour.hex_to_rgb("#B77B2E")) == "#B77B2E"


def test_delta_e_is_zero_for_the_same_colour_and_grows_with_distance():
    cream = colour.hex_to_lab("#EDE0B8")
    assert colour.delta_e_cie76(cream, cream) == 0.0
    brown = colour.hex_to_lab("#4A2E1C")
    assert colour.delta_e_cie76(cream, brown) > 40


def test_confidence_decays_as_delta_e_grows():
    assert colour.confidence_from_delta_e(0.0) == 100.0
    assert colour.confidence_from_delta_e(2.0) > colour.confidence_from_delta_e(12.0)
    assert 0.0 <= colour.confidence_from_delta_e(200.0) < 1.0


def test_two_plus_two_measurements_are_low_risk_with_two_factor_sentences():
    result = scoring.score_find(30.0, 7.0)
    assert result.risk_band == "low"
    assert result.score < 34
    assert [factor["component"] for factor in result.factors] == ["cap", "gill"]
    assert "Cap" in result.factors[0]["text"]
    assert "gill-crowding" in result.factors[1]["text"]


def test_broad_cap_and_crowded_gills_saturates_to_high_risk():
    result = scoring.score_find(250.0, 1.0)
    assert result.risk_band == "high"
    assert result.score >= 67
    assert result.score == 100


def test_moderate_band_sits_between_the_two_thresholds():
    result = scoring.score_find(120.0, 4.0)
    assert 34 <= result.score <= 66
    assert result.risk_band == "moderate"


def test_score_is_deterministic_and_monotonic_in_cap_width():
    first = scoring.score_payload(100.0, 5.0)
    second = scoring.score_payload(100.0, 5.0)
    assert first == second
    assert scoring.score_payload(160.0, 5.0)["score"] > first["score"]


def test_measurement_range_is_enforced():
    for cap, gill in ((4.0, 5.0), (301.0, 5.0), (50.0, 0.4), (50.0, 30.5)):
        try:
            scoring.score_find(cap, gill)
        except ValueError:
            continue
        raise AssertionError(f"{cap}/{gill} should be rejected")
