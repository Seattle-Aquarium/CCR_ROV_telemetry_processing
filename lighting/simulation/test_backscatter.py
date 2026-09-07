"""Tests for the veiling-glare model.

The phase function is checked against its own closed-form integrals, and the
geometry against the behaviour the tilt is supposed to produce -- less lit water
in the line of sight as the lamps swing outboard.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from backscatter import (
    HG_ASYMMETRY,
    backscatter_fraction,
    contrast,
    henyey_greenstein,
    overlap_height,
)
from photometry import Rig, fov_stats


def _rig(**kwargs) -> Rig:
    kwargs.setdefault("level", 100)
    return Rig.with_hardware(light="sealite_flood", camera="gopro12", **kwargs)


# --------------------------------------------------------------------------- #
# Phase function
# --------------------------------------------------------------------------- #


def test_phase_function_integrates_to_one_over_the_sphere():
    """A normalised phase function must conserve the scattered photon."""
    mu = np.linspace(-1, 1, 200001)
    assert 2 * np.pi * np.trapezoid(henyey_greenstein(mu), mu) == pytest.approx(1.0, rel=1e-4)


def test_phase_function_is_strongly_forward_peaked():
    """Sea water scatters mostly forward; that is why g is 0.92 and not 0."""
    assert henyey_greenstein(np.array(1.0)) > 100 * henyey_greenstein(np.array(-1.0))


def test_backscatter_fraction_matches_direct_integration():
    mu = np.linspace(-1, 0, 100001)
    back = 2 * np.pi * np.trapezoid(henyey_greenstein(mu), mu)
    assert back == pytest.approx(backscatter_fraction(), rel=1e-3)


def test_backscatter_fraction_is_in_the_range_petzold_measured():
    """1.8 % — within the 1.8-2.5 % band reported for natural sea water."""
    assert 0.015 < backscatter_fraction(HG_ASYMMETRY) < 0.026


# --------------------------------------------------------------------------- #
# Veiling glare
# --------------------------------------------------------------------------- #


def test_veil_ratio_does_not_depend_on_lamp_output():
    """Signal and veil both scale linearly with lamp output, so contrast does not.

    This is why the tilt question can be answered without first settling the
    exposure question: dimming cannot buy back contrast lost to backscatter.
    """
    ratios = [contrast(_rig(level=lvl), grid=15, steps=32).veil_ratio for lvl in (40, 70, 100)]
    assert ratios[0] == pytest.approx(ratios[1], rel=1e-9)
    assert ratios[1] == pytest.approx(ratios[2], rel=1e-9)


def test_veil_ratio_scales_inversely_with_reflectance():
    """A darker seafloor returns less signal against the same glare."""
    dark = contrast(_rig(), reflectance=0.08, grid=15, steps=32).veil_ratio
    light = contrast(_rig(), reflectance=0.32, grid=15, steps=32).veil_ratio
    assert dark / light == pytest.approx(4.0, rel=1e-6)


def test_clear_water_produces_almost_no_veiling():
    assert contrast(_rig(attenuation=0.1), grid=15, steps=32).veil_ratio < 0.01


def test_turbid_water_wrecks_contrast():
    """At c = 1.8 the worst corner of the frame keeps under half its contrast."""
    result = contrast(_rig(attenuation=1.8), grid=21, steps=48)
    assert result.veil_ratio > 0.1
    assert result.worst_retention < 0.5


def test_veiling_rises_monotonically_with_turbidity():
    ratios = [contrast(_rig(attenuation=c), grid=15, steps=32).veil_ratio for c in (0.2, 0.5, 1.0, 1.8)]
    assert all(b > a for a, b in zip(ratios, ratios[1:]))


def test_contrast_retention_is_a_fraction():
    for c in (0.1, 0.5, 1.5, 2.5):
        result = contrast(_rig(attenuation=c), grid=15, steps=32)
        assert 0.0 < result.worst_retention <= result.contrast_retention <= 1.0


def test_veil_integral_is_converged_at_the_default_resolution():
    coarse = contrast(_rig(), grid=21, steps=48).veil_ratio
    fine = contrast(_rig(), grid=31, steps=96).veil_ratio
    assert abs(coarse - fine) / fine < 0.05


# --------------------------------------------------------------------------- #
# What the tilt is actually for
# --------------------------------------------------------------------------- #


def test_tilting_outboard_reduces_veiling_glare():
    """The whole point of the outboard tilt, and it does work: a third less glare."""
    flat = contrast(_rig(side_tilt_deg=0, forward_tilt_deg=0), grid=21, steps=48)
    tilted = contrast(_rig(side_tilt_deg=10, forward_tilt_deg=10), grid=21, steps=48)
    assert tilted.veil_ratio < flat.veil_ratio
    assert 1 - tilted.veil_ratio / flat.veil_ratio > 0.25


def test_glare_falls_monotonically_as_the_lamps_swing_out():
    ratios = [
        contrast(_rig(side_tilt_deg=t, forward_tilt_deg=t), grid=15, steps=32).veil_ratio
        for t in (0, 5, 10, 15, 20)
    ]
    assert all(b < a for a, b in zip(ratios, ratios[1:]))


def test_tilting_lowers_the_top_of_the_lit_column():
    """The mechanism the tilt was chosen for, stated as a number."""
    high = overlap_height(_rig(side_tilt_deg=0, forward_tilt_deg=0))
    low = overlap_height(_rig(side_tilt_deg=15, forward_tilt_deg=15))
    assert low < high


def test_zero_tilt_is_worse_on_both_counts_at_survey_altitude():
    """The headline answer to 'should I just set them to zero?' -- no.

    At 0.80 m, dropping the tilt costs uniformity *and* adds glare. The only
    thing it buys is flux, which this rig has to spare.
    """
    flat_rig = _rig(side_tilt_deg=0, forward_tilt_deg=0)
    tilted_rig = _rig(side_tilt_deg=10, forward_tilt_deg=10)
    assert fov_stats(flat_rig).uniformity < fov_stats(tilted_rig).uniformity
    assert contrast(flat_rig, grid=21, steps=48).veil_ratio > contrast(
        tilted_rig, grid=21, steps=48
    ).veil_ratio
    assert fov_stats(flat_rig).flux_lm > fov_stats(tilted_rig).flux_lm  # the one gain


def test_low_altitude_reverses_the_advice():
    """Below about 0.7 m the tilt starts digging a hole under the camera instead.

    The lamps are then so close to the seafloor that swinging them outboard takes
    the centre of frame past the beam edge, so *less* tilt is better down there.
    """
    shallow_flat = fov_stats(_rig(altitude=0.55, side_tilt_deg=0, forward_tilt_deg=0))
    shallow_tilted = fov_stats(_rig(altitude=0.55, side_tilt_deg=12, forward_tilt_deg=12))
    assert shallow_flat.uniformity > shallow_tilted.uniformity


def test_the_uniformity_cliff_sits_just_past_thirteen_degrees():
    """Real physics, not a metric artefact: the frame corners leave the beam."""
    good = fov_stats(_rig(side_tilt_deg=12, forward_tilt_deg=12)).uniformity
    cliff = fov_stats(_rig(side_tilt_deg=16, forward_tilt_deg=16)).uniformity
    assert good > 0.55
    assert cliff < 0.25


# --------------------------------------------------------------------------- #
# The light-limited regime -- where the "more lumens" trade would be tempting
# --------------------------------------------------------------------------- #


def test_tilt_still_wins_when_the_rig_is_light_limited():
    """The counter-intuitive one, and the answer to 'should I flatten them?'.

    At 1.5 m in c = 1.0 water full power cannot expose the frame at any tilt, so
    lumens are genuinely scarce. Flattening the lamps still loses: it buys light
    the camera cannot use and gives up contrast the picture needs.
    """
    flat = _rig(altitude=1.5, attenuation=1.0, side_tilt_deg=0, forward_tilt_deg=0)
    tilted = _rig(altitude=1.5, attenuation=1.0, side_tilt_deg=12, forward_tilt_deg=12)
    assert fov_stats(flat, samples=121).mean_lux > fov_stats(tilted, samples=121).mean_lux
    assert contrast(tilted, grid=15, steps=32).contrast_retention > contrast(
        flat, grid=15, steps=32
    ).contrast_retention
    assert fov_stats(tilted, samples=121).uniformity > fov_stats(flat, samples=121).uniformity


def test_glare_can_exceed_signal_outright():
    """Veil : signal above 1 -- the haze is brighter than the seafloor."""
    result = contrast(
        _rig(altitude=1.5, attenuation=1.0, side_tilt_deg=0, forward_tilt_deg=0),
        grid=15,
        steps=32,
    )
    assert result.veil_ratio > 1.0
    assert result.contrast_retention < 0.5


def test_power_cannot_recover_contrast_lost_to_backscatter():
    """The invariance stated plainly: turning the lamps up changes nothing here.

    Signal and veil scale together, so contrast retention is identical at every
    output level. This is the reason 'more lumens in frame' is not a route out of
    a hazy image.
    """
    dim = contrast(_rig(attenuation=1.5, level=30), grid=15, steps=32)
    bright = contrast(_rig(attenuation=1.5, level=100), grid=15, steps=32)
    # The picture really did get brighter ...
    assert bright.signal_cd_m2 > 2 * dim.signal_cd_m2
    # ... and not one point of contrast came back with it.
    assert dim.contrast_retention == pytest.approx(bright.contrast_retention, rel=1e-9)
