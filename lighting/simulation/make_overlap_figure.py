"""Head-on figure: how far below the vehicle the port and starboard beams meet.

Three panels, identical framing, only the lamps and their aim changing. The point
of the figure is the shaded wedge where the two sides light the same water twice
-- the volume that turns into backscatter -- and how far down the rig you can push
its apex by choosing a narrower beam and tilting it outboard.

    python make_overlap_figure.py

Writes ``figures/beam_overlap.pdf`` and ``figures/beam_overlap.png``.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Polygon, Rectangle

from photometry import Rig, beam_crossing

# BlueROV2 frame and LED SeaLite envelope, for the schematic only.
BODY_W, BODY_H, LAMP_LEN = 0.338, 0.254, 0.0959

OUT = Path(__file__).parent / "figures"

# Seattle Aquarium palette
SALISH, FATHOM = "#004346", "#0C2340"
MEDITERRANEAN, ALGAE, SEAFOAM = "#1963B0", "#00C389", "#3CCBDA"
CORAL, STONE, PUMICE = "#F58674", "#575757", "#EEEEEE"

# Framing, shared by all three panels so only the beams differ.
XLIM = (-0.86, 0.86)
ZLIM = (-0.06, 1.17)


def projected_wedge(axis: np.ndarray, half_angle_deg: float, samples: int = 1441):
    """Silhouette of a cone seen end-on, as (left, right) angles from straight down.

    Projecting a tilted cone onto the across-track plane is not simply
    "axis angle plus or minus the half angle" once there is fore-aft tilt in it,
    so the rim is sampled and the extreme projected angles taken.
    """
    a = math.radians(half_angle_deg)
    n = np.asarray(axis, dtype=float)
    helper = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(helper, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)

    angles = []
    for phi in np.linspace(0, 2 * math.pi, samples, endpoint=False):
        d = math.cos(a) * n + math.sin(a) * (math.cos(phi) * u + math.sin(phi) * v)
        if d[2] >= -1e-9:  # heading up or sideways; contributes no downward silhouette
            continue
        angles.append(math.atan2(d[0], -d[2]))
    return min(angles), max(angles)


def wedge_polygon(x0: float, z0: float, left: float, right: float, z_floor: float = 0.0):
    """The beam wedge from a lamp down to the seafloor, as a filled polygon."""
    drop = z0 - z_floor
    return [
        (x0, z0),
        (x0 + drop * math.tan(left), z_floor),
        (x0 + drop * math.tan(right), z_floor),
    ]


def draw_vehicle(ax, rig: Rig) -> None:
    """A head-on schematic: skid, frame, both enclosures, thrusters, four lamps."""
    d, z0 = rig.lateral_spacing / 2, rig.altitude
    body_bottom = z0 + 0.055
    kw = dict(linewidth=0.9, edgecolor=STONE, zorder=6)

    # frame uprights and top plate
    ax.add_patch(Rectangle((-BODY_W / 2, body_bottom), BODY_W, BODY_H, facecolor="#243447", **kw))
    ax.add_patch(
        Rectangle((-BODY_W * 0.52, body_bottom + BODY_H), BODY_W * 1.04, 0.022,
                  facecolor=STONE, **kw)
    )
    # enclosures, seen end-on
    ax.add_patch(Circle((0, body_bottom + BODY_H * 0.66), 0.051, facecolor="#8D9AA5", **kw))
    ax.add_patch(Circle((0, body_bottom + BODY_H * 0.30), 0.040, facecolor=FATHOM, **kw))
    # vertical thrusters at the frame corners
    for s in (-1, 1):
        ax.add_patch(
            Rectangle(
                (s * BODY_W * 0.46 - 0.030, body_bottom + BODY_H - 0.045),
                0.060,
                0.075,
                facecolor="#1B2A3A",
                **kw,
            )
        )
    # payload skid, the plane the lamps live on
    ax.add_patch(Rectangle((-d - 0.045, z0), 2 * (d + 0.045), 0.030, facecolor=STONE, **kw))
    ax.add_patch(Rectangle((-d * 0.55, z0 - 0.016), d * 1.1, 0.018, facecolor=FATHOM, **kw))

    # the lamps themselves, drawn along their projected optical axis
    for position, axis in zip(rig.lamp_positions(), rig.lamp_axes()):
        if position[1] < 0:  # both lamps on a side project onto each other end-on
            continue
        tilt = math.atan2(axis[0], -axis[2])
        ax.add_patch(
            Rectangle(
                (position[0] - LAMP_LEN * 0.30, z0 - LAMP_LEN * 0.92),
                LAMP_LEN * 0.60,
                LAMP_LEN * 0.92,
                angle=-math.degrees(tilt),
                rotation_point=(position[0], z0),
                facecolor="#9AA7B0",
                **kw,
            )
        )


def panel(ax, rig: Rig, title: str, subtitle: str) -> dict:
    cross = beam_crossing(rig, level=0.5)
    d, z0 = rig.lateral_spacing / 2, rig.altitude

    # water column and seafloor
    ax.add_patch(
        Rectangle((XLIM[0], 0), XLIM[1] - XLIM[0], ZLIM[1], facecolor="#F4F8FB", zorder=0)
    )
    ax.add_patch(
        Rectangle((XLIM[0], ZLIM[0]), XLIM[1] - XLIM[0], -ZLIM[0], facecolor="#DDE3E6", zorder=1)
    )
    ax.plot(XLIM, [0, 0], color=STONE, linewidth=1.3, zorder=5)

    positions, axes = rig.lamp_positions(), rig.lamp_axes()
    forward = [(p, a) for p, a in zip(positions, axes) if p[1] > 0]
    inner = {}
    for position, axis in forward:
        for level, alpha, edge in ((0.10, 0.13, False), (0.50, 0.30, True)):
            half = rig.profile.fraction_angle(level)
            left, right = projected_wedge(axis, half)
            poly = wedge_polygon(position[0], z0, left, right)
            ax.add_patch(
                Polygon(
                    poly,
                    closed=True,
                    facecolor=SEAFOAM,
                    alpha=alpha,
                    edgecolor=MEDITERRANEAN if edge else "none",
                    linewidth=1.1 if edge else 0,
                    zorder=2,
                )
            )
            if level == 0.10:  # outer contour, dashed so it reads as "and a bit more"
                for ang in (left, right):
                    ax.plot(
                        [position[0], position[0] + z0 * math.tan(ang)],
                        [z0, 0],
                        color=ALGAE,
                        linewidth=0.9,
                        linestyle=(0, (4, 3)),
                        zorder=3,
                    )
            else:
                inner[position[0] > 0] = (left, right)

    # The doubly-lit wedge: bounded by each side's inboard edge, apex where they meet.
    zc = cross["height_above_seafloor"]
    port_inboard = inner[False][1]
    stbd_inboard = inner[True][0]
    overlap = [
        (0.0, zc),
        (d + z0 * math.tan(stbd_inboard), 0.0),
        (-d + z0 * math.tan(port_inboard), 0.0),
    ]
    ax.add_patch(
        Polygon(
            overlap,
            closed=True,
            facecolor=SEAFOAM,
            alpha=0.55,
            edgecolor=MEDITERRANEAN,
            linewidth=1.2,
            zorder=4,
        )
    )

    draw_vehicle(ax, rig)

    # the crossing, called out
    ax.plot([0], [zc], marker="o", markersize=7, color=CORAL, markeredgecolor="white",
            markeredgewidth=1.2, zorder=8)
    ax.add_patch(
        FancyArrowPatch(
            (0.0, z0), (0.0, zc),
            arrowstyle="<|-|>", mutation_scale=9,
            color=CORAL, linewidth=1.4, zorder=8,
        )
    )
    ax.text(
        0.035, (z0 + zc) / 2,
        f"{cross['depth_below_lamps']:.2f} m",
        color=CORAL, fontsize=10, fontweight="bold", va="center", ha="left", zorder=9,
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.85),
    )
    ax.text(
        0, zc - 0.06,
        f"beams meet {zc:.2f} m above seafloor",
        color=FATHOM, fontsize=8.5, ha="center", va="top", zorder=9,
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="none", alpha=0.82),
    )
    ax.text(
        0, 0.03,
        f"{100 * cross['doubly_lit_fraction']:.0f} % of the centreline doubly lit",
        color=FATHOM, fontsize=8.5, ha="center", va="bottom", zorder=9, style="italic",
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white", edgecolor="none", alpha=0.82),
    )

    ax.set_xlim(*XLIM)
    ax.set_ylim(*ZLIM)
    ax.set_aspect("equal")
    ax.set_xticks([-0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.tick_params(labelsize=8, colors=STONE, length=3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#C7CED2")
    ax.set_title(title, fontsize=11.5, fontweight="bold", color=FATHOM, pad=13)
    ax.text(
        0.5, 1.015, subtitle, transform=ax.transAxes,
        fontsize=9, color=STONE, ha="center", va="bottom",
    )
    return cross


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cases = [
        (
            Rig.with_hardware(light="kraken_18k", side_tilt_deg=0, forward_tilt_deg=0),
            "Kraken Solar Flare Mini",
            "120° beam · no tilt",
        ),
        (
            Rig.with_hardware(light="sealite_flood", side_tilt_deg=0, forward_tilt_deg=0),
            "DeepSea LED SeaLite",
            "75° flood · no tilt",
        ),
        (
            Rig.with_hardware(light="sealite_flood"),
            "DeepSea LED SeaLite",
            "75° flood · tilted 10° / 10° outboard",
        ),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.5))
    results = [panel(ax, rig, t, s) for ax, (rig, t, s) in zip(axes, cases)]
    axes[0].set_ylabel("height above seafloor (m)", fontsize=9, color=STONE)
    for ax in axes:
        ax.set_xlabel("across-track (m)", fontsize=9, color=STONE)

    fig.suptitle(
        "Where the port and starboard beams meet, seen head-on",
        fontsize=14.5, fontweight="bold", color=FATHOM, y=0.995,
    )
    fig.text(
        0.5, 0.925,
        "Shaded wedge = water lit by both sides at once, the volume that turns into backscatter. "
        "Lamps 0.514 m apart, 0.80 m above the seafloor.",
        fontsize=9.5, color=STONE, ha="center",
    )
    fig.text(
        0.5, 0.028,
        "Filled wedge: half-power (50 %) cone.   Dashed: 10 % contour.   "
        "Crossing solved in 3-D at the half-power edge, on the centreline beneath the vehicle.   "
        "Kraken beam shape is a cosine lobe fitted to its published 120°; the SeaLite is a "
        "measured trace (Operator's Manual, Appendix D).",
        fontsize=7.8, color=STONE, ha="center",
    )

    fig.subplots_adjust(left=0.055, right=0.985, top=0.845, bottom=0.115, wspace=0.16)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"beam_overlap.{ext}", dpi=220, facecolor="white")
    plt.close(fig)

    print(f"{'configuration':40s} {'half-angle':>11} {'below lamps':>12} {'above floor':>12} {'doubly lit':>11}")
    for (rig, title, sub), r in zip(cases, results):
        print(
            f"{title + ' — ' + sub:40s} {r['half_angle_deg']:10.1f}° "
            f"{r['depth_below_lamps']:11.3f} m {r['height_above_seafloor']:11.3f} m "
            f"{100 * r['doubly_lit_fraction']:10.0f} %"
        )
    print(f"\nwrote {OUT / 'beam_overlap.pdf'} and .png")


if __name__ == "__main__":
    main()
