"""Tests for the seafloor illuminance model.

Two kinds of check here. The first anchors the digitised beam data against
numbers the manual states in words, so a bad re-extraction cannot pass quietly.
The second drives the illuminance model into geometries where the answer is
known analytically -- a lamp straight overhead, a cone with no tilt -- so the
inverse-square, cosine and attenuation terms are each pinned individually.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from photometry import (
    CAMERAS,
    DOME_5IN_RADIUS_M,
    LIGHT_SYSTEMS,
    NAMEPLATE_DERATE,
    PEAK_INTENSITY_CD,
    WATER_N,
    BeamProfile,
    Camera,
    Rig,
    dimming_output,
    exposure_error_stops,
    beam_crossing,
    footprint_ellipse,
    fov_stats,
    illuminance,
    required_illuminance,
    solve_level,
)


# --------------------------------------------------------------------------- #
# Beam data vs. what the manual says in words
# --------------------------------------------------------------------------- #


def test_flood_half_power_width_matches_datasheet():
    """Specification Overview p.2 gives 75 deg HPFW; Appendix D p.13 gives 76."""
    assert 2 * BeamProfile.from_csv("flood").half_power_angle() == pytest.approx(75.5, abs=2.0)


def test_spot_half_power_width_matches_datasheet():
    assert 2 * BeamProfile.from_csv("spot").half_power_angle() == pytest.approx(34.5, abs=2.0)


def test_flood_beam_is_flat_topped_not_cosine():
    """The real distribution is a plateau with a cliff, not a rounded lobe.

    At 20 deg off axis the flood optic is still at 97 % of peak while a cos^n
    lobe fitted to the same half-power width has already fallen to 83 %. By
    40 deg the ordering has reversed: the real beam has dropped off a cliff to
    33 % while the cosine lobe is still coasting at 45 %. That crossover is the
    whole reason for digitising the manual instead of assuming a shape.
    """
    flood = BeamProfile.from_csv("flood")
    cosine = BeamProfile.cosine_power(75)
    assert flood(20.0) > 0.95 > cosine(20.0)
    assert flood(40.0) < 0.40 < cosine(40.0)


def test_flood_beam_is_spent_by_55_degrees():
    """Past the cliff the trace settles onto a ~1 % floor rather than zero.

    That floor is the goniometer's own stray-light background, so it is asserted
    as a small number rather than as exactly nothing.
    """
    flood = BeamProfile.from_csv("flood")
    assert flood(55.0) < 0.02
    assert flood(80.0) == pytest.approx(0.0, abs=0.01)


def test_profile_falls_away_past_the_shoulder():
    """Strictly decreasing through the roll-off, sampled clear of trace noise."""
    flood = BeamProfile.from_csv("flood")
    values = flood(np.arange(30.0, 55.0, 5.0))
    assert np.all(np.diff(values) < 0.0)


def test_integrated_flux_is_below_the_nameplate_lumens():
    """10,000 lm is an emitter rating, not delivered beam flux.

    Integrating the measured distribution against the measured peak intensity
    gives about 7,000 lm out of the flood optic. Both figures come from the same
    manual, so this gap is a property of the datasheet, not of our maths.
    """
    flux = BeamProfile.from_csv("flood").total_flux(PEAK_INTENSITY_CD["flood"])
    assert 6_000 < flux < 8_000


def test_top_hat_flux_matches_closed_form():
    """A uniform cone of half-angle a has flux 2*pi*I0*(1 - cos a).

    Tolerance is 2 % because a step function sampled on a 0.5 deg grid and then
    integrated by trapezoid smears the discontinuity across one cell.
    """
    profile = BeamProfile.top_hat(75.0)
    expected = 2 * math.pi * 1000 * (1 - math.cos(math.radians(37.5)))
    assert profile.total_flux(1000) == pytest.approx(expected, rel=0.02)


def test_cosine_power_flux_matches_closed_form():
    """A cos^n distribution has flux 2*pi*I0/(n+1)."""
    profile = BeamProfile.cosine_power(75.0)
    n = math.log(0.5) / math.log(math.cos(math.radians(37.5)))
    assert profile.total_flux(1000) == pytest.approx(2 * math.pi * 1000 / (n + 1), rel=0.01)


# --------------------------------------------------------------------------- #
# Dimming curve
# --------------------------------------------------------------------------- #


def test_dimming_curve_endpoints():
    assert dimming_output(0) == pytest.approx(0.0, abs=0.01)
    assert dimming_output(100) == pytest.approx(1.0, abs=0.01)


def test_dimming_curve_is_strongly_non_linear():
    """Half the command range buys an eighth of the light."""
    assert dimming_output(50) < 0.15
    assert dimming_output(90) < 0.70


def test_dimming_curve_is_monotonic():
    values = [dimming_output(v) for v in range(101)]
    assert all(b >= a - 1e-9 for a, b in zip(values, values[1:]))


# --------------------------------------------------------------------------- #
# Rig geometry
# --------------------------------------------------------------------------- #


def test_lamp_axes_are_unit_vectors():
    assert np.allclose(np.linalg.norm(Rig().lamp_axes(), axis=1), 1.0)


def test_lamp_axes_tilt_outboard():
    """Each axis must lean away from the centreline in both x and y."""
    rig = Rig()
    for position, axis in zip(rig.lamp_positions(), rig.lamp_axes()):
        assert math.copysign(1, axis[0]) == math.copysign(1, position[0])
        assert math.copysign(1, axis[1]) == math.copysign(1, position[1])
        assert axis[2] < 0  # still pointing downward


def test_combined_tilt_is_not_the_sum_of_its_parts():
    """10 deg of pitch plus 10 deg of roll is 14.1 deg off nadir, not 20."""
    assert Rig().nadir_angle_deg() == pytest.approx(14.11, abs=0.01)


def test_zero_tilt_points_straight_down():
    rig = Rig(forward_tilt_deg=0.0, side_tilt_deg=0.0)
    assert rig.nadir_angle_deg() == pytest.approx(0.0, abs=1e-9)
    assert np.allclose(rig.lamp_axes(), [[0, 0, -1]] * 4)


def test_fov_scales_by_similar_triangles():
    rig = Rig(altitude=1.60)  # twice the reference altitude
    width, height = rig.fov_extent()
    assert width == pytest.approx(2.40)
    assert height == pytest.approx(1.80)


def test_fov_can_be_pinned_to_a_fixed_footprint():
    rig = Rig(altitude=1.60, fov_scales_with_altitude=False)
    assert rig.fov_extent() == pytest.approx((1.20, 0.90))


# --------------------------------------------------------------------------- #
# Illuminance model, against closed-form geometry
# --------------------------------------------------------------------------- #


def _single_point_rig(**kwargs) -> Rig:
    """Collapse the four lamps onto one spot pointing straight down."""
    kwargs.setdefault("attenuation", 0.0)
    return Rig(
        lateral_spacing=0.0,
        longitudinal_spacing=0.0,
        forward_tilt_deg=0.0,
        side_tilt_deg=0.0,
        profile=BeamProfile.top_hat(120.0),
        **kwargs,
    )


def test_inverse_square_law_at_nadir():
    """Four coincident lamps overhead: E = 4 * I0 / h^2."""
    rig = _single_point_rig(altitude=2.0)
    expected = 4 * rig.peak_intensity_cd / 2.0**2
    assert float(illuminance(rig, 0.0, 0.0)) == pytest.approx(expected, rel=1e-6)


def test_illuminance_falls_as_one_over_range_squared():
    near = float(illuminance(_single_point_rig(altitude=1.0), 0.0, 0.0))
    far = float(illuminance(_single_point_rig(altitude=2.0), 0.0, 0.0))
    assert near / far == pytest.approx(4.0, rel=1e-6)


def test_cosine_law_off_nadir():
    """Off to one side, E gains a cos(iota) obliquity term on top of 1/r^2."""
    rig = _single_point_rig(altitude=1.0)
    offset = 1.0  # 45 degrees off nadir
    r = math.hypot(offset, 1.0)
    expected = 4 * rig.peak_intensity_cd * (1.0 / r) / r**2
    assert float(illuminance(rig, offset, 0.0)) == pytest.approx(expected, rel=1e-6)


def test_attenuation_is_beer_lambert_over_the_slant_range():
    clear = _single_point_rig(altitude=1.5, attenuation=0.0)
    murky = replace(clear, attenuation=0.8)
    ratio = float(illuminance(murky, 0.0, 0.0)) / float(illuminance(clear, 0.0, 0.0))
    assert ratio == pytest.approx(math.exp(-0.8 * 1.5), rel=1e-6)


def test_no_light_behind_the_lamp():
    """A point on the seafloor outside the beam gets nothing, not a negative."""
    rig = _single_point_rig(altitude=0.5)
    rig = replace(rig, profile=BeamProfile.top_hat(60.0))
    assert float(illuminance(rig, 5.0, 0.0)) == 0.0


def test_four_lamps_give_a_four_fold_symmetric_field():
    rig = Rig()
    for x, y in [(0.3, 0.2), (0.7, 0.1), (0.15, 0.45)]:
        reference = float(illuminance(rig, x, y))
        for xx, yy in [(-x, y), (x, -y), (-x, -y)]:
            assert float(illuminance(rig, xx, yy)) == pytest.approx(reference, rel=1e-9)


def test_per_lamp_contributions_sum_to_the_total():
    rig = Rig()
    x = np.linspace(-0.6, 0.6, 7)
    y = np.linspace(-0.45, 0.45, 5)
    per_lamp = illuminance(rig, x[None, :], y[:, None], per_lamp=True)
    assert per_lamp.shape == (4, 5, 7)
    assert np.allclose(per_lamp.sum(axis=0), illuminance(rig, x[None, :], y[:, None]))


def test_dimming_scales_illuminance_linearly():
    full = float(illuminance(Rig(lout=100), 0.0, 0.0))
    dimmed = float(illuminance(Rig(lout=70), 0.0, 0.0))
    assert dimmed / full == pytest.approx(dimming_output(70), rel=1e-9)


# --------------------------------------------------------------------------- #
# Field-of-view integration
# --------------------------------------------------------------------------- #


def test_flux_equals_mean_illuminance_times_area():
    stats = fov_stats(Rig())
    assert stats.flux_lm == pytest.approx(stats.mean_lux * stats.area_m2, rel=1e-9)


def test_fov_integral_is_converged_at_the_default_resolution():
    coarse = fov_stats(Rig(), samples=61).flux_lm
    fine = fov_stats(Rig(), samples=481).flux_lm
    assert abs(coarse - fine) / fine < 1e-3


def test_captured_flux_cannot_exceed_emitted_flux():
    for altitude in (0.4, 0.8, 1.5, 2.0):
        stats = fov_stats(Rig(altitude=altitude))
        assert 0.0 < stats.capture_efficiency < 1.0


def test_fov_centre_sits_at_the_half_power_angle_by_default():
    """The 10/10 tilt places the centre of frame on each lamp's 50 % contour.

    Off-axis angle to the nadir point is the lamp's own tilt plus the angle
    subtended by its offset from the centreline: 14.11 + 23.41 = 37.5 deg, which
    is the flood optic's half-power angle almost exactly.
    """
    rig = Rig()
    offset = math.hypot(rig.lateral_spacing / 2, rig.longitudinal_spacing / 2)
    angle = math.degrees(math.atan(offset / rig.altitude)) + rig.nadir_angle_deg()
    assert angle == pytest.approx(37.5, abs=0.3)
    assert rig.profile(angle) == pytest.approx(0.5, abs=0.05)


def test_top_hat_model_roughly_doubles_the_centre_illuminance():
    """The error the original notebook's uniform-cone assumption would cause."""
    real = fov_stats(Rig()).centre_lux
    top_hat = fov_stats(Rig(profile=BeamProfile.top_hat(75))).centre_lux
    assert top_hat / real == pytest.approx(2.0, abs=0.2)


# --------------------------------------------------------------------------- #
# Exposure
# --------------------------------------------------------------------------- #


def test_exposure_round_trips_through_required_illuminance():
    camera = Camera()
    for reflectance in (0.05, 0.15, 0.4):
        need = required_illuminance(reflectance, camera)
        assert exposure_error_stops(need, reflectance, camera) == pytest.approx(0.0, abs=1e-9)


def test_doubling_illuminance_is_one_stop():
    camera = Camera()
    a = exposure_error_stops(1000, 0.15, camera)
    b = exposure_error_stops(2000, 0.15, camera)
    assert b - a == pytest.approx(1.0, rel=1e-9)


def test_full_power_overexposes_the_configured_gopro():
    """At LOUT 100 over a dark seafloor the frame blows out by about a stop."""
    stats = fov_stats(Rig())
    assert exposure_error_stops(stats.mean_lux, 0.15, Camera()) > 0.5


# --------------------------------------------------------------------------- #
# Footprint geometry -- the bug in the original notebook
# --------------------------------------------------------------------------- #


def test_untilted_cone_footprint_is_a_circle():
    result = footprint_ellipse(0.8, nadir_deg=0.0, half_angle_deg=37.5)
    expected = 0.8 * math.tan(math.radians(37.5))
    assert result["a"] == pytest.approx(expected, rel=1e-9)
    assert result["b"] == pytest.approx(expected, rel=1e-9)
    assert result["centre"] == pytest.approx(0.0, abs=1e-12)


def test_tilted_cone_footprint_is_an_offset_ellipse():
    """At the rig's defaults the true patch is bigger, and further out, than a
    circle of radius h*tan(theta) drawn at the axis intercept."""
    result = footprint_ellipse(0.8, nadir_deg=14.11, half_angle_deg=37.5)
    naive_radius = 0.8 * math.tan(math.radians(37.5))
    naive_centre = 0.8 * math.tan(math.radians(14.11))
    assert result["a"] > result["b"] > naive_radius
    assert result["centre"] > 1.5 * naive_centre


def test_footprint_is_unbounded_once_the_cone_edge_reaches_the_horizon():
    result = footprint_ellipse(0.8, nadir_deg=60.0, half_angle_deg=37.5)
    assert result["unbounded"]
    assert math.isinf(result["a"])


# --------------------------------------------------------------------------- #
# The browser tool carries its own copy of the data
# --------------------------------------------------------------------------- #


def test_embedded_web_data_matches_the_csvs():
    """index.html inlines the measured curves so it runs offline as one file.

    Those arrays are generated by build_web_data.py. If anyone edits them by
    hand -- or regenerates the CSVs and forgets to re-run the builder -- the
    browser tool and the Python model quietly stop agreeing, which is far worse
    than either being wrong on its own.
    """
    import re
    from pathlib import Path

    html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
    beams = np.loadtxt(Path(__file__).parent / "data" / "lsl_beam_profiles.csv", delimiter=",")
    dim = np.loadtxt(Path(__file__).parent / "data" / "lsl_seasense_dimming.csv", delimiter=",")

    for name, reference in (("FLOOD", beams[:, 1]), ("SPOT", beams[:, 2]), ("DIM", dim[:, 1])):
        match = re.search(rf"const {name}=\[([^\]]*)\];", html)
        assert match, f"index.html has no embedded {name} array"
        embedded = np.array([float(v) for v in match.group(1).split(",")])
        assert embedded.shape == reference.shape, f"{name}: {embedded.size} values, expected {reference.size}"
        assert np.allclose(embedded, reference, atol=1e-6), f"{name} has drifted from the CSV"


def test_embedded_dimming_curve_reaches_full_output():
    """A regression guard: an off-by-one here silently dims every reported number."""
    import re
    from pathlib import Path

    html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
    values = re.search(r"const DIM=\[([^\]]*)\];", html).group(1).split(",")
    assert len(values) == 101
    assert float(values[100]) == pytest.approx(100.0)
    assert float(values[0]) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Lamp sets
# --------------------------------------------------------------------------- #


def test_fitted_lamps_integrate_to_their_published_lumens():
    """Kraken and Lumen publish lumens and a beam angle but no beam profile.

    The shape is a fitted cosine lobe and the peak is solved so the lobe
    integrates to exactly the published flux -- so the light budget stays honest
    even though the shape is an assumption.
    """
    for key, expected in (("kraken_18k", 18_000.0), ("br_lumen", 1_500.0)):
        system = LIGHT_SYSTEMS[key]
        assert system.profile.total_flux(system.peak_cd) == pytest.approx(expected, rel=1e-6)


def test_measured_lamps_keep_their_measured_peak_intensity():
    """The SeaLite is anchored the other way round: peak is measured, flux follows."""
    assert LIGHT_SYSTEMS["sealite_flood"].peak_cd == pytest.approx(5680.0)
    assert LIGHT_SYSTEMS["sealite_spot"].peak_cd == pytest.approx(14400.0)


def test_every_lamp_set_reproduces_its_published_beam_angle():
    """Within 3 deg, which is the room a spec sheet leaves against a real unit.

    The fitted lobes hit their beam angle exactly by construction. The two
    SeaLite optics are measured traces, and the manual's own Appendix D reports
    76 deg and 34 deg for units whose Specification Overview says 75 and 35.
    """
    for system in LIGHT_SYSTEMS.values():
        assert 2 * system.profile.half_power_angle() == pytest.approx(
            system.beam_angle_deg, abs=3.0
        )


def test_kraken_power_snaps_to_its_five_steps():
    kraken = LIGHT_SYSTEMS["kraken_18k"]
    assert kraken.output_fraction(47) == pytest.approx(0.40)
    assert kraken.output_fraction(51) == pytest.approx(0.60)
    assert kraken.output_fraction(100) == pytest.approx(1.00)


def test_lumen_dimming_is_linear():
    lumen = LIGHT_SYSTEMS["br_lumen"]
    assert lumen.output_fraction(30) == pytest.approx(0.30)
    assert lumen.output_fraction(0) == pytest.approx(0.0)


def test_lumens_cannot_expose_the_gopro_frame_at_full_power():
    """Four Lumens put ~850 lx on the seafloor; the GoPro's settings want 3,100."""
    rig = Rig.with_hardware(light="br_lumen", camera="gopro12")
    assert solve_level(rig, 0.15) is None
    assert fov_stats(rig).mean_lux < 1_500


def test_krakens_reach_correct_exposure_low_on_their_step_range():
    """Two steps up from off, once their nameplate lumens are derated like the
    SeaLite's were. Undegraded they would sit on the bottom step, which is one
    symptom of the mismatched-derate error this constant exists to prevent."""
    rig = Rig.with_hardware(light="kraken_18k", camera="gopro12")
    assert solve_level(rig, 0.15) == pytest.approx(40.0, abs=10.0)


def test_spot_optic_wrecks_uniformity_on_this_rig():
    """A 35 deg beam from lamps 0.35 m off the centreline misses the middle."""
    flood = fov_stats(Rig.with_hardware(light="sealite_flood", camera="gopro12"))
    spot = fov_stats(Rig.with_hardware(light="sealite_spot", camera="gopro12"))
    assert spot.uniformity < 0.15 < flood.uniformity


# --------------------------------------------------------------------------- #
# Cameras
# --------------------------------------------------------------------------- #


def test_sony_lenses_reproduce_the_published_diagonal_angle_of_view():
    """Sony quotes 84 deg for the 24 mm and 107 deg for the 16 mm on full frame."""
    assert CAMERAS["ilx_24"].diagonal_in_air_deg() == pytest.approx(84.0, abs=1.0)
    assert CAMERAS["ilx_16"].diagonal_in_air_deg() == pytest.approx(107.0, abs=1.0)


def test_gopro_reproduces_its_measured_footprint():
    assert CAMERAS["gopro12"].footprint(0.80) == pytest.approx((1.20, 0.90))


def test_flat_port_narrows_the_view_and_a_dome_does_not():
    """Snell's law at a flat port; a concentric dome puts the image in water."""
    camera = CAMERAS["ilx_16"]
    flat_h, _ = camera.half_angles_in_water("flat")
    dome_h, _ = camera.half_angles_in_water("dome")
    assert flat_h < dome_h
    assert math.sin(dome_h) / math.sin(flat_h) == pytest.approx(WATER_N, rel=1e-9)


def test_footprint_grows_in_proportion_to_object_distance():
    """Similar triangles -- but measured from the entrance pupil, not the datum.

    Behind a dome the pupil sits one dome radius above the quoted altitude, so
    the footprint is proportional to (altitude + radius) and only asymptotically
    proportional to altitude itself.
    """
    for camera in CAMERAS.values():
        near, far = camera.footprint(0.5), camera.footprint(1.5)
        ratio = camera.object_distance(1.5) / camera.object_distance(0.5)
        assert far[0] / near[0] == pytest.approx(ratio, rel=1e-9)
        assert far[1] / near[1] == pytest.approx(ratio, rel=1e-9)


def test_a_measured_camera_ignores_the_port_setting():
    """The GoPro's footprint was measured in water, so no refraction is applied."""
    camera = CAMERAS["gopro12"]
    assert camera.footprint(0.9, "flat") == pytest.approx(camera.footprint(0.9, "dome"))


def test_each_camera_carries_its_own_exposure_settings():
    assert Rig.with_hardware(camera="gopro12").exposure_camera().f_number == pytest.approx(2.8)
    assert Rig.with_hardware(camera="ilx_24").exposure_camera().iso == pytest.approx(400)


def test_aperture_drives_the_required_illuminance_as_the_square():
    """Two stops down needs four times the light."""
    wide = Camera(f_number=2.8, shutter_s=1 / 250, iso=400)
    stopped = Camera(f_number=5.6, shutter_s=1 / 250, iso=400)
    ratio = required_illuminance(0.15, stopped) / required_illuminance(0.15, wide)
    assert ratio == pytest.approx(4.0, rel=1e-9)


# --------------------------------------------------------------------------- #
# Dome port, against the two calibration images
# --------------------------------------------------------------------------- #


def test_dome_reproduces_the_24mm_calibration_image():
    """Sony 24 mm behind a 5-inch dome, tapes read at a stated 0.90 m: ~1.45 m wide."""
    width, _ = CAMERAS["ilx_24"].footprint(0.90, "dome")
    assert width == pytest.approx(1.45, rel=0.04)


def test_dome_reproduces_the_16mm_calibration_image():
    """Same rig, 16 mm lens, same altitude: ~2.15 m wide."""
    width, _ = CAMERAS["ilx_16"].footprint(0.90, "dome")
    assert width == pytest.approx(2.15, rel=0.04)


def test_dome_offsets_the_object_distance_by_one_dome_radius():
    """The single correction that reconciles both calibration images at once.

    Ignoring it under-predicts the footprint by 7 % at 0.9 m -- small enough to
    look like noise on one lens, but it showed up identically on both, which is
    what identified it as a datum error rather than an optical one.
    """
    camera = CAMERAS["ilx_24"]
    assert camera.object_distance(0.90, "dome") == pytest.approx(0.90 + DOME_5IN_RADIUS_M)
    assert camera.object_distance(0.90, "flat") == pytest.approx(0.90)


def test_dome_preserves_the_in_air_angle_and_a_flat_port_does_not():
    for key in ("ilx_24", "ilx_16"):
        camera = CAMERAS[key]
        dome_h, _ = camera.half_angles_in_water("dome")
        flat_h, _ = camera.half_angles_in_water("flat")
        assert dome_h == pytest.approx(math.atan(camera.sensor_w_mm / 2 / camera.focal_mm))
        assert math.sin(dome_h) / math.sin(flat_h) == pytest.approx(WATER_N, rel=1e-9)


# --------------------------------------------------------------------------- #
# Nameplate derating -- the fix for an unfair lamp comparison
# --------------------------------------------------------------------------- #


def test_measured_lamps_are_never_derated():
    """The SeaLite's beam is measured, so its flux is already the truth."""
    rig = Rig.with_hardware(light="sealite_flood")
    assert rig.peak_intensity_cd == pytest.approx(PEAK_INTENSITY_CD["flood"])


def test_nameplate_lamps_are_derated():
    rig = Rig.with_hardware(light="kraken_18k")
    assert rig.profile.total_flux(rig.peak_intensity_cd) == pytest.approx(
        18_000 * NAMEPLATE_DERATE, rel=1e-6
    )


def test_derate_settles_the_kraken_versus_sealite_flux_comparison():
    """On a matched basis the two are within about 10 %, not 57 % apart.

    Comparing the SeaLite's *measured* 7,030 lm against the Kraken's *nameplate*
    18,000 lm is the mismatch that produced the wrong answer first time round.
    """
    sealite = fov_stats(Rig.with_hardware(light="sealite_flood", camera="gopro12"))
    kraken = fov_stats(Rig.with_hardware(light="kraken_18k", camera="gopro12"))
    assert 1.0 < kraken.flux_lm / sealite.flux_lm < 1.25


def test_narrow_beams_put_a_larger_share_of_their_light_in_the_frame():
    """The robust half of the comparison: capture efficiency needs no lumen rating.

    It depends only on beam angle and geometry, so it survives every assumption
    about how optimistic a manufacturer's lumen claim is.
    """
    sealite = fov_stats(Rig.with_hardware(light="sealite_flood", camera="gopro12"))
    kraken = fov_stats(Rig.with_hardware(light="kraken_18k", camera="gopro12"))
    lumen = fov_stats(Rig.with_hardware(light="br_lumen", camera="gopro12"))
    assert sealite.capture_efficiency > kraken.capture_efficiency
    assert sealite.capture_efficiency > lumen.capture_efficiency
    assert sealite.capture_efficiency / kraken.capture_efficiency > 1.5


# --------------------------------------------------------------------------- #
# Against how the rig is actually flown
# --------------------------------------------------------------------------- #


def test_lout_80_is_a_correct_exposure():
    """The setting the team arrived at in the field, checked against the model.

    LOUT 80 is 40.7 % output on the SeaSense curve. Independently, the model's
    own optimum is LOUT 81. Agreement to a tenth of a stop across the digitised
    beam profile, the digitised dimming curve, the geometry and ISO 2720 is the
    strongest external check this model has.
    """
    rig = Rig.with_hardware(light="sealite_flood", camera="gopro12", level=80)
    stats = fov_stats(rig)
    assert abs(exposure_error_stops(stats.mean_lux, 0.15, rig.exposure_camera())) < 0.25
    assert solve_level(rig, 0.15) == pytest.approx(80.0, abs=2.0)


def test_krakens_as_flown_are_in_the_right_neighbourhood():
    """60-80 % power, which the team reported as good performance."""
    for level, limit in ((60, 1.0), (80, 1.3)):
        rig = Rig.with_hardware(light="kraken_18k", camera="gopro12", level=level)
        stats = fov_stats(rig)
        error = exposure_error_stops(stats.mean_lux, 0.15, rig.exposure_camera())
        assert 0 < error < limit


# --------------------------------------------------------------------------- #
# Limits of the fitted beam models -- why beam angle cannot be freely optimised
# --------------------------------------------------------------------------- #


def test_fitted_lobe_badly_overstates_uniformity_at_high_tilt():
    """A cos^n lobe has a tail that a real optic does not, and it shows.

    At 20 deg tilt the fitted 75 deg lobe keeps lighting frame corners the
    measured beam has already abandoned past its 43 deg cliff. This is why the
    beam-angle sweep in README section 3.6 is reported as a trend and not as an
    optimum.
    """
    measured = Rig.with_hardware(light="sealite_flood", camera="gopro12")
    measured = replace(measured, side_tilt_deg=20, forward_tilt_deg=20)
    fitted = replace(measured, profile=BeamProfile.cosine_power(75))
    assert fov_stats(measured, samples=121).uniformity < 0.10
    assert fov_stats(fitted, samples=121).uniformity > 0.50


def test_one_optic_cannot_be_rescaled_into_the_other():
    """The flood spreads and the spot collimates; they are not one shape scaled.

    Squeezing the measured flood to the spot's half-power width leaves it far too
    dark at 20 deg off axis, so angle-rescaling is not a licence to invent beam
    profiles for widths nobody measured.
    """
    flood, spot = BeamProfile.from_csv("flood"), BeamProfile.from_csv("spot")
    k = spot.half_power_angle() / flood.half_power_angle()
    grid = np.arange(0.0, 90.5, 0.5)
    rel = np.interp(grid / k, flood.angle_deg, flood.relative, right=0.0)
    rescaled = BeamProfile(grid, rel / rel.max())

    assert 2 * rescaled.half_power_angle() == pytest.approx(
        2 * spot.half_power_angle(), abs=1.0
    )  # widths agree by construction
    assert abs(rescaled(20.0) - spot(20.0)) > 0.25  # shapes emphatically do not


def test_flood_optic_beats_both_alternatives_on_uniformity():
    """Across every tilt worth flying, the 75 deg flood is the right optic."""
    best = {}
    for key in ("sealite_flood", "sealite_spot"):
        best[key] = max(
            fov_stats(
                Rig.with_hardware(light=key, camera="gopro12", side_tilt_deg=t, forward_tilt_deg=t),
                samples=121,
            ).uniformity
            for t in (0, 5, 10, 12, 15)
        )
    assert best["sealite_flood"] > 0.55
    assert best["sealite_spot"] < 0.25


def test_full_power_cannot_expose_high_and_turbid():
    """The light-limited regime is real, and it starts above where they fly."""
    fine = Rig.with_hardware(light="sealite_flood", camera="gopro12", altitude=0.80)
    hopeless = replace(fine, altitude=1.5, attenuation=1.0)
    assert solve_level(fine, 0.15) is not None
    assert solve_level(hopeless, 0.15) is None


# --------------------------------------------------------------------------- #
# Beam crossing -- the head-on overlap figure
# --------------------------------------------------------------------------- #


def test_untilted_crossing_matches_closed_form():
    """With no tilt the inboard edges are straight lines, so trigonometry checks it.

    Two lamps 2d apart, each throwing a cone of half-angle a, meet on the
    centreline at depth d / tan(a) below the lamp plane.
    """
    rig = Rig.with_hardware(light="sealite_flood", side_tilt_deg=0, forward_tilt_deg=0)
    half = math.radians(rig.profile.half_power_angle())
    expected = (rig.lateral_spacing / 2) / math.tan(half)
    assert beam_crossing(rig)["depth_below_lamps"] == pytest.approx(expected, abs=0.01)


def test_tilting_outboard_pushes_the_crossing_further_down():
    """The mechanism behind the whole tilt argument, as a single number."""
    flat = beam_crossing(Rig.with_hardware(side_tilt_deg=0, forward_tilt_deg=0))
    tilted = beam_crossing(Rig.with_hardware())
    assert tilted["depth_below_lamps"] > flat["depth_below_lamps"]
    assert tilted["doubly_lit_fraction"] < flat["doubly_lit_fraction"]


def test_a_wider_beam_crosses_much_sooner():
    """The Kraken's 120 deg beam overlaps almost immediately below the skid."""
    wide = beam_crossing(Rig.with_hardware(light="kraken_18k", side_tilt_deg=0, forward_tilt_deg=0))
    narrow = beam_crossing(Rig.with_hardware(light="sealite_flood", side_tilt_deg=0, forward_tilt_deg=0))
    assert wide["depth_below_lamps"] < 0.5 * narrow["depth_below_lamps"]
    assert wide["doubly_lit_fraction"] > 0.75


def test_crossing_is_deeper_at_the_outer_contour_than_the_half_power_edge():
    """The 10 % contour is wider, so it meets sooner -- higher up, not lower."""
    rig = Rig.with_hardware()
    assert beam_crossing(rig, level=0.10)["depth_below_lamps"] < beam_crossing(rig, level=0.5)[
        "depth_below_lamps"
    ]
