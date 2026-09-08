"""Three lamp configurations by three power settings, on one fixed colour scale.

The whole point is comparability, so everything that could differ between panels
and confuse the eye is pinned: the same window, the same colour scale, the same
contour levels, the same camera frame. Only the light changes.

Reading it: rows differ in the *shape* of the light, columns only in its *level*.
Uniformity and contrast are therefore constant along each row -- power is a pure
multiplier, so it cannot change how evenly the frame is lit or how much glare
sits in front of it. Only mean illuminance and exposure move left to right.

    python make_illuminance_grid.py

Writes ``figures/illuminance_grid.pdf`` and ``figures/illuminance_grid.png``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, PowerNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from backscatter import contrast
from photometry import LIGHT_SYSTEMS, Rig, exposure_error_stops, fov_stats, illuminance

OUT = Path(__file__).parent / "figures"

SALISH, FATHOM = "#004346", "#0C2340"
MEDITERRANEAN, ALGAE, SEAFOAM = "#1963B0", "#00C389", "#3CCBDA"
CORAL, STONE = "#F58674", "#575757"

# The One Ocean ramp, same anchors and same gamma as the interactive tool, so a
# colour here means what it means there.
RAMP = LinearSegmentedColormap.from_list(
    "one_ocean", ["#0C2340", "#1963B0", "#3CCBDA", "#FFFFFF"]
)
GAMMA = 0.55

WINDOW = 1.10  # metres either side, the tool's frame-sized window at 0.80 m
GRID = 320
REFLECTANCE = 0.15

ROWS = [
    ("Kraken Solar Flare Mini", "120° beam · no tilt", "kraken_18k", 0.0, [60, 80, 100]),
    ("DeepSea LED SeaLite", "75° flood · no tilt", "sealite_flood", 0.0, [80, 90, 100]),
    ("DeepSea LED SeaLite", "75° flood · 10° / 10° outboard", "sealite_flood", 10.0, [80, 90, 100]),
]


def build(light: str, tilt: float, level: float) -> Rig:
    return Rig.with_hardware(
        light=light, camera="gopro12", level=level, side_tilt_deg=tilt, forward_tilt_deg=tilt
    )


def level_label(light: str, level: float) -> str:
    system = LIGHT_SYSTEMS[light]
    output = 100 * system.output_fraction(level)
    if system.dimming == "seasense":
        return f"LOUT {level:.0f}  →  {output:.0f} % output"
    return f"{output:.0f} % power"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the labels carry arrows
    OUT.mkdir(exist_ok=True)
    axis = np.linspace(-WINDOW, WINDOW, GRID)
    X, Y = np.meshgrid(axis, axis)

    # Pass one: every field, so the colour scale can be pinned to the brightest.
    panels = []
    for title, subtitle, light, tilt, levels in ROWS:
        for level in levels:
            rig = build(light, tilt, level)
            field = illuminance(rig, X, Y)
            stats = fov_stats(rig)
            glare = contrast(rig, grid=21, steps=48)
            panels.append(
                {
                    "rig": rig,
                    "field": field,
                    "stats": stats,
                    "kept": glare.contrast_retention,
                    "stops": exposure_error_stops(
                        stats.mean_lux, REFLECTANCE, rig.exposure_camera()
                    ),
                    "label": level_label(light, level),
                    "peak": float(field.max()),
                    "need": np.pi
                    * rig.exposure_camera().required_luminance()
                    / REFLECTANCE,
                }
            )
    reference = max(p["peak"] for p in panels)
    brightest = max(panels, key=lambda p: p["peak"])
    norm = PowerNorm(gamma=GAMMA, vmin=0.0, vmax=reference)

    fig = plt.figure(figsize=(12.4, 16.4))
    # Each row needs room beneath it for three lines of statistics, hence the
    # generous hspace and the deep bottom margin for the shared scale and key.
    gs = fig.add_gridspec(
        3, 3, left=0.125, right=0.985, top=0.885, bottom=0.190, wspace=0.09, hspace=0.46
    )

    grid_axes = [[None] * 3 for _ in range(3)]
    for index, panel in enumerate(panels):
        row, col = divmod(index, 3)
        ax = fig.add_subplot(gs[row, col])
        grid_axes[row][col] = ax
        rig, field, stats = panel["rig"], panel["field"], panel["stats"]

        ax.imshow(
            field,
            extent=[-WINDOW, WINDOW, -WINDOW, WINDOW],
            origin="lower",
            cmap=RAMP,
            norm=norm,
            interpolation="bilinear",
            zorder=1,
        )
        # Isolux at fractions of the *shared* full scale, so contours in one panel
        # mark the same lux as contours in any other.
        ax.contour(
            X, Y, field,
            levels=[0.25 * reference, 0.50 * reference, 0.75 * reference],
            colors=ALGAE, linewidths=1.0, zorder=3,
        )
        ax.contour(
            X, Y, field, levels=[panel["need"]],
            colors=CORAL, linewidths=1.7, linestyles=[(0, (5, 3))], zorder=4,
        )

        width, height = stats.width_m, stats.height_m
        ax.add_patch(
            Rectangle((-width / 2, -height / 2), width, height,
                      fill=False, edgecolor="white", linewidth=1.9, zorder=5)
        )
        lamps = rig.lamp_positions()
        ax.scatter(lamps[:, 0], lamps[:, 1], s=42, facecolor=ALGAE,
                   edgecolor="#0B3B2E", linewidth=0.8, zorder=6)

        ax.set_xlim(-WINDOW, WINDOW)
        ax.set_ylim(-WINDOW, WINDOW)
        ax.set_aspect("equal")
        ax.set_xticks([-1, -0.5, 0, 0.5, 1])
        ax.set_yticks([-1, -0.5, 0, 0.5, 1])
        ax.tick_params(labelsize=8.5, colors=STONE, length=3)
        if row != 2:
            ax.set_xticklabels([])
        if col != 0:
            ax.set_yticklabels([])
        for spine in ax.spines.values():
            spine.set_color("#C7CED2")

        ax.set_title(panel["label"], fontsize=10.5, color=FATHOM, fontweight="bold", pad=7)

        ax.text(
            0.5, -0.085,
            f"{stats.flux_lm:,.0f} lm into frame   ·   {stats.mean_lux:,.0f} lx mean",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=9.2, color=FATHOM, fontweight="semibold",
        )
        ax.text(
            0.5, -0.145,
            f"uniformity {stats.uniformity:.2f}   ·   contrast kept {100 * panel['kept']:.0f} %",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.8, color=STONE,
        )
        sign = "+" if panel["stops"] > 0 else "−"
        ax.text(
            0.5, -0.205,
            f"exposure {sign}{abs(panel['stops']):.2f} stops",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=9.0, color=STONE, fontweight="bold",
        )

    fig.canvas.draw()  # aspect='equal' resizes the boxes; read them after that

    # Row identities, down the left-hand side
    for row, (title, subtitle, _light, _tilt, _levels) in enumerate(ROWS):
        box = grid_axes[row][0].get_position()
        centre = (box.y0 + box.y1) / 2
        fig.text(0.052, centre + 0.011, title, rotation=90, ha="center", va="center",
                 fontsize=11.5, color=FATHOM, fontweight="bold")
        fig.text(0.077, centre + 0.011, subtitle, rotation=90, ha="center", va="center",
                 fontsize=9.2, color=STONE)

    # Axis titles once each, as asked
    # Clear of the bottom row's statistics block, which reaches down to ~0.147.
    fig.text(0.555, 0.122, "across-track (m)", ha="center", va="top",
             fontsize=11, color=FATHOM)
    fig.text(0.018, 0.545, "along-track (m)", rotation=90, va="center",
             fontsize=11, color=FATHOM)

    fig.suptitle(
        "Seafloor illuminance across lamp set, aim and power",
        fontsize=16.5, fontweight="bold", color=FATHOM, y=0.978,
    )
    fig.text(
        0.5, 0.951,
        "All nine panels share one colour scale, one window and one set of contour levels, so colours and "
        "contours are directly comparable.",
        ha="center", fontsize=10.2, color=STONE,
    )
    fig.text(
        0.5, 0.935,
        "Rows change the shape of the light; columns change only its level — which is why uniformity and "
        "contrast are constant along each row.",
        ha="center", fontsize=10.2, color=MEDITERRANEAN, style="italic",
    )

    # Shared colour bar
    cax = fig.add_axes([0.315, 0.083, 0.37, 0.010])
    bar = fig.colorbar(
        matplotlib.cm.ScalarMappable(norm=norm, cmap=RAMP), cax=cax, orientation="horizontal"
    )
    bar.set_ticks([0, 2000, 4000, 8000, 12000, reference])
    bar.set_ticklabels(["0", "2k", "4k", "8k", "12k", f"{reference:,.0f}"])
    bar.ax.tick_params(labelsize=8.5, colors=STONE, length=2)
    bar.outline.set_edgecolor("#C7CED2")
    fig.text(
        0.5, 0.064,
        f"seafloor illuminance (lx) — full scale is {brightest['label'].split('→')[0].strip()} "
        f"on the {ROWS[1][0]}, {ROWS[1][1]}",
        ha="center", fontsize=8.8, color=STONE,
    )

    handles = [
        Line2D([], [], color="white", marker="s", markersize=10, linestyle="none",
               markeredgecolor=STONE, markeredgewidth=1.2, label="camera frame (1.20 × 0.90 m)"),
        Line2D([], [], color=ALGAE, marker="o", markersize=8, linestyle="none",
               markeredgecolor="#0B3B2E", label="lamp position"),
        Line2D([], [], color=CORAL, linewidth=1.9, linestyle=(0, (5, 3)),
               label="correct-exposure isolux (ρ = 0.15)"),
        Line2D([], [], color=ALGAE, linewidth=1.4,
               label="isolux at ¼ · ½ · ¾ of full scale"),
    ]
    fig.legend(
        handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.014),
        ncol=4, frameon=False, fontsize=9.6, handletextpad=0.7, columnspacing=2.4,
        labelcolor=FATHOM,
    )

    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"illuminance_grid.{ext}", dpi=200, facecolor="white")
    plt.close(fig)

    print(f"colour scale pinned to {reference:,.0f} lx ({brightest['label']})\n")
    print(f"{'configuration':38s} {'setting':>22} {'flux lm':>9} {'mean lx':>9} {'U0':>5} {'kept':>6} {'stops':>7}")
    for index, panel in enumerate(panels):
        row = index // 3
        name = f"{ROWS[row][0]} — {ROWS[row][1]}"
        s = panel["stats"]
        print(
            f"{name:38s} {panel['label']:>22} {s.flux_lm:9,.0f} {s.mean_lux:9,.0f} "
            f"{s.uniformity:5.2f} {100 * panel['kept']:5.0f}% {panel['stops']:+7.2f}"
        )
    print(f"\nwrote {OUT / 'illuminance_grid.pdf'} and .png")


if __name__ == "__main__":
    main()
