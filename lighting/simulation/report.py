"""Regenerate the parameter sweeps quoted in README.md.

Every number in the write-up comes out of here, so the review can be re-checked
rather than taken on trust::

    python report.py
"""

from __future__ import annotations

import math
from dataclasses import replace

from backscatter import contrast, overlap_height
from photometry import (
    CAMERAS,
    DOME_5IN_RADIUS_M,
    NAMEPLATE_DERATE,
    LIGHT_SYSTEMS,
    BeamProfile,
    Camera,
    Rig,
    dimming_output,
    exposure_error_stops,
    fov_stats,
    footprint_ellipse,
    solve_level,
)

BASE = Rig()
CAM = Camera()
RHO = 0.15  # kelp-and-rock seafloor; sand is nearer 0.30


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def baseline() -> None:
    rule("As built (0.80 m, 10/10 deg tilt, LOUT 100, c = 0.5 /m)")
    stats = fov_stats(BASE)
    for key, value in stats.as_rows():
        print(f"  {key:26s} {value}")
    print(f"  {'Lamp axis off nadir':26s} {BASE.nadir_angle_deg():.2f} deg")

    offset = math.hypot(BASE.lateral_spacing / 2, BASE.longitudinal_spacing / 2)
    angle = math.degrees(math.atan(offset / BASE.altitude)) + BASE.nadir_angle_deg()
    print(f"  {'Angle to frame centre':26s} {angle:.1f} deg")
    print(f"  {'Beam intensity there':26s} {100 * BASE.profile(angle):.0f} % of peak")
    print(f"  {'Exposure error':26s} {exposure_error_stops(stats.mean_lux, RHO, CAM):+.2f} stops")


def tilt_sweep() -> None:
    rule("Tilt sweep (both axes equal)")
    print(f"{'tilt':>5} {'nadir':>6} {'flux':>8} {'mean lx':>8} {'min lx':>7} {'U0':>5} {'stops':>7}")
    for tilt in (0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 25):
        rig = replace(BASE, forward_tilt_deg=tilt, side_tilt_deg=tilt)
        s = fov_stats(rig)
        print(
            f"{tilt:5.1f} {rig.nadir_angle_deg():6.2f} {s.flux_lm:8,.0f} {s.mean_lux:8,.0f} "
            f"{s.min_lux:7,.0f} {s.uniformity:5.2f} {exposure_error_stops(s.mean_lux, RHO, CAM):+7.2f}"
        )


def altitude_sweep() -> None:
    rule("Altitude sweep (frame scales with altitude)")
    print(f"{'alt':>5} {'frame':>12} {'flux':>8} {'mean lx':>8} {'U0':>5} {'capture':>8} {'stops':>7}")
    for altitude in (0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0):
        s = fov_stats(replace(BASE, altitude=altitude))
        print(
            f"{altitude:5.2f} {s.width_m:5.2f}x{s.height_m:5.2f} {s.flux_lm:8,.0f} {s.mean_lux:8,.0f} "
            f"{s.uniformity:5.2f} {100 * s.capture_efficiency:7.1f}% "
            f"{exposure_error_stops(s.mean_lux, RHO, CAM):+7.2f}"
        )


def water_sweep() -> None:
    rule("Water attenuation -- the largest single uncertainty")
    print(f"{'c 1/m':>6} {'mean lx':>8} {'flux':>8} {'stops':>7}")
    for c in (0.0, 0.2, 0.35, 0.5, 0.8, 1.2, 2.0):
        s = fov_stats(replace(BASE, attenuation=c))
        print(
            f"{c:6.2f} {s.mean_lux:8,.0f} {s.flux_lm:8,.0f} "
            f"{exposure_error_stops(s.mean_lux, RHO, CAM):+7.2f}"
        )


def model_comparison() -> None:
    rule("What the beam model costs you")
    print(f"{'model':16s} {'centre lx':>10} {'mean lx':>9} {'U0':>5} {'capture':>8}")
    for profile in (
        BeamProfile.from_csv("flood"),
        BeamProfile.top_hat(75),
        BeamProfile.cosine_power(75),
    ):
        s = fov_stats(replace(BASE, profile=profile))
        print(
            f"{profile.name:16s} {s.centre_lux:10,.0f} {s.mean_lux:9,.0f} "
            f"{s.uniformity:5.2f} {100 * s.capture_efficiency:7.1f}%"
        )

    rule("Footprint geometry at the as-built settings")
    truth = footprint_ellipse(BASE.altitude, BASE.nadir_angle_deg(), 37.5)
    naive_r = BASE.altitude * math.tan(math.radians(37.5))
    naive_c = BASE.altitude * math.tan(math.radians(BASE.nadir_angle_deg()))
    print(f"  true half-power patch  ellipse {truth['a']:.3f} x {truth['b']:.3f} m")
    print(f"                         centred {truth['centre']:.3f} m from nadir")
    print(f"  notebook drew          circle  r = {naive_r:.3f} m")
    print(f"                         centred {naive_c:.3f} m from nadir")
    print(f"  understates semi-major by {100 * (1 - naive_r / truth['a']):.0f} %")
    print(f"  understates offset by     {100 * (1 - naive_c / truth['centre']):.0f} %")


def dim_levels() -> None:
    rule("Dim level for a correctly exposed frame")
    for rho in (0.08, 0.15, 0.30):
        stats = fov_stats(BASE)
        want = BASE.dim_fraction() * (math.pi * CAM.required_luminance() / rho) / stats.mean_lux
        if want > 1:
            print(f"  reflectance {rho:.2f}: needs more than full power")
            continue
        lout = min(
            range(101), key=lambda v: abs(dimming_output(v) - want)
        )
        print(
            f"  reflectance {rho:.2f}: LOUT {lout:3d}  ({100 * dimming_output(lout):.0f} % output, "
            f"{100 * want:.0f} % wanted)"
        )


def hardware_matrix() -> None:
    rule("Every lamp set against every camera, at 0.80 m and full power")
    print(
        f"  lamps with no measured beam are derated to {100 * NAMEPLATE_DERATE:.0f} % of nameplate,"
        " the same shortfall the SeaLite's own datasheet shows"
    )
    print(
        f"{'lamps':15s} {'camera':15s} {'frame':12s} {'flux lm':>8} {'mean lx':>8} "
        f"{'U0':>5} {'capture':>8} {'stops':>7}"
    )
    for light_key, light in LIGHT_SYSTEMS.items():
        for camera_key, camera in CAMERAS.items():
            rig = Rig.with_hardware(light=light_key, camera=camera_key)
            s = fov_stats(rig)
            stops = exposure_error_stops(s.mean_lux, RHO, rig.exposure_camera())
            print(
                f"{light.short:15s} {camera.short:15s} {s.width_m:.2f}x{s.height_m:.2f}  "
                f"{s.flux_lm:8,.0f} {s.mean_lux:8,.0f} {s.uniformity:5.2f} "
                f"{100 * s.capture_efficiency:7.1f}% {stops:+7.2f}"
            )
        print()

    rule("Control level for a correct exposure on the GoPro, rho = 0.15")
    for light_key, light in LIGHT_SYSTEMS.items():
        rig = Rig.with_hardware(light=light_key, camera="gopro12")
        level = solve_level(rig, RHO)
        setting = "beyond full power" if level is None else (
            f"{light.level_label()} {level:.0f}  ({100 * light.output_fraction(level):.0f} % output)"
        )
        print(f"  {light.short:15s} {setting}")

    rule("Dome-port model against the two calibration images (stated 0.90 m)")
    print(f"{'camera':15s} {'predicted':>12} {'measured':>10} {'error':>7}")
    for key, observed in (("ilx_24", 1.45), ("ilx_16", 2.15)):
        camera = CAMERAS[key]
        width, height = camera.footprint(0.90, "dome")
        print(
            f"{camera.short:15s} {width:6.3f} x {height:.3f} {observed:9.2f} m "
            f"{100 * (width - observed) / observed:+6.1f}%"
        )
    print(
        f"  entrance pupil sits one dome radius ({1000 * DOME_5IN_RADIUS_M:.1f} mm) above"
        f" the datum, so the optical range at a stated 0.90 m altitude is"
        f" {CAMERAS['ilx_24'].object_distance(0.90):.4f} m"
    )

    rule("Housing port, Sony bodies only (GoPro footprint was measured in water)")
    print(f"{'camera':15s} {'port':6s} {'frame at 0.80 m':17s} {'FOV in water':>16}")
    for key in ("ilx_24", "ilx_16"):
        camera = CAMERAS[key]
        for port in ("flat", "dome"):
            width, height = camera.footprint(0.80, port)
            hh, hv = camera.half_angles_in_water(port)
            print(
                f"{camera.short:15s} {port:6s} {width:.2f} x {height:.2f} m     "
                f"{2 * math.degrees(hh):6.1f} x {2 * math.degrees(hv):.1f} deg"
            )


def tilt_optimisation() -> None:
    """The trade the outboard tilt is really making: light on the bottom against
    glare in the water between the lamps and the bottom."""
    import numpy as np

    rig0 = Rig.with_hardware(light="sealite_flood", camera="gopro12", level=100)

    rule("Symmetric tilt: what you gain and what you give up")
    print(
        f"{'tilt':>5} {'nadir':>6} {'flux':>8} {'U0':>5} {'veil:sig':>9} "
        f"{'contrast':>9} {'lit from':>9}"
    )
    for tilt in (0, 2, 4, 6, 8, 10, 11, 12, 13, 14, 16, 20):
        rig = replace(rig0, side_tilt_deg=float(tilt), forward_tilt_deg=float(tilt))
        s = fov_stats(rig, samples=121)
        cr = contrast(rig, grid=21, steps=48)
        print(
            f"{tilt:5.0f} {rig.nadir_angle_deg():6.2f} {s.flux_lm:8,.0f} {s.uniformity:5.2f} "
            f"{cr.veil_ratio:9.4f} {100 * cr.contrast_retention:8.1f}% "
            f"{cr.overlap_height_m:8.3f}m"
        )

    rule("Best symmetric tilt against altitude (uniformity-optimal)")
    tilts = np.arange(0, 21, 1.0)
    print(f"{'alt':>5} {'best':>6} {'U0':>6} {'U0 at 0':>8} {'U0 at 10':>9} {'veil:sig':>9}")
    for altitude in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5):
        scores = [
            fov_stats(
                replace(rig0, altitude=altitude, side_tilt_deg=float(t), forward_tilt_deg=float(t)),
                samples=121,
            ).uniformity
            for t in tilts
        ]
        best = int(np.argmax(scores))
        rig = replace(
            rig0, altitude=altitude, side_tilt_deg=float(tilts[best]), forward_tilt_deg=float(tilts[best])
        )
        print(
            f"{altitude:5.2f} {tilts[best]:5.0f}° {scores[best]:6.2f} {scores[0]:8.2f} "
            f"{scores[10]:9.2f} {contrast(rig, grid=15, steps=32).veil_ratio:9.4f}"
        )

    rule("Turbidity is what decides how much the tilt is worth")
    print(f"{'c 1/m':>6} {'veil 0°':>9} {'veil 10°':>9} {'glare cut':>10} {'contrast 0°':>12} {'contrast 10°':>13}")
    for c in (0.2, 0.5, 1.0, 1.8, 2.5):
        flat = contrast(replace(rig0, attenuation=c, side_tilt_deg=0, forward_tilt_deg=0), grid=21, steps=48)
        tilted = contrast(replace(rig0, attenuation=c), grid=21, steps=48)
        print(
            f"{c:6.1f} {flat.veil_ratio:9.4f} {tilted.veil_ratio:9.4f} "
            f"{100 * (1 - tilted.veil_ratio / flat.veil_ratio):9.0f}% "
            f"{100 * flat.contrast_retention:11.1f}% {100 * tilted.contrast_retention:12.1f}%"
        )


if __name__ == "__main__":
    baseline()
    tilt_optimisation()
    hardware_matrix()
    tilt_sweep()
    altitude_sweep()
    water_sweep()
    model_comparison()
    dim_levels()
