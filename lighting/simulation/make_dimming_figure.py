"""The SeaSense LOUT command against the light you actually get.

The curve is severely non-linear and the shape is not intuitive: more than half
the command range buys a seventh of the light, and the top quarter carries two
thirds of it. Anything that maps a joystick axis or a PWM duty cycle linearly
onto LOUT will therefore feel dead for most of its travel and then jump.

Data is the SeaSense serial dimming curve digitised from Appendix C, p.10 of the
LED SeaLite Operator's Manual rev. 08/27/18 -- see data/extract_from_manual.py.
Lumens come from integrating the measured Appendix D beam against its measured
peak intensity (7,030 lm delivered per lamp), not from the 10,000 lm nameplate.

    python make_dimming_figure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from photometry import DATA_DIR, PEAK_INTENSITY_CD, BeamProfile

OUT = Path(__file__).parent / "figures"

FATHOM, MEDITERRANEAN = "#0C2340", "#1963B0"
ALGAE, CORAL, STONE = "#00C389", "#F58674", "#575757"
PUMICE = "#EEEEEE"

OPERATING_LOUT = 80  # what the rig is actually flown at


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(exist_ok=True)

    table = np.loadtxt(DATA_DIR / "lsl_seasense_dimming.csv", delimiter=",")
    lout, output = table[:, 0], table[:, 1]
    per_lamp = BeamProfile.from_csv("flood").total_flux(PEAK_INTENSITY_CD["flood"])

    fig, ax = plt.subplots(figsize=(10.6, 6.9))
    fig.subplots_adjust(left=0.085, right=0.885, top=0.845, bottom=0.155)

    # Bands that carry the headline: most of the range does almost nothing.
    ax.axvspan(0, 60, color=PUMICE, zorder=0)
    ax.axvspan(75, 100, color=ALGAE, alpha=0.10, zorder=0)
    ax.text(30, 88, "LOUT 0–60\n60 % of the command range\nbuys 15 % of the light",
            ha="center", va="top", fontsize=10, color=STONE, linespacing=1.5)
    ax.text(88, 17, "LOUT 75–100\nthe top quarter carries\n70 % of the light",
            ha="center", va="top", fontsize=10, color="#0B6B4F", linespacing=1.5)

    ax.plot([0, 100], [0, 100], linestyle=(0, (5, 4)), color="#AAB3B8", linewidth=1.6,
            zorder=2, label="what a linear command would give")
    ax.plot(lout, output, color=MEDITERRANEAN, linewidth=2.8, zorder=4,
            label="measured SeaSense curve (manual, Appendix C)")

    marks = np.arange(0, 101, 10)
    values = np.interp(marks, lout, output)
    ax.scatter(marks, values, s=54, facecolor="white", edgecolor=MEDITERRANEAN,
               linewidth=2.0, zorder=5)

    for x, y in zip(marks, values):
        if x == 0:
            continue
        lumens = y / 100 * per_lamp
        dx, dy, ha, va = -7, 6, "right", "bottom"
        ax.annotate(
            f"{y:.1f} %\n{lumens:,.0f} lm",
            xy=(x, y), xytext=(dx, dy), textcoords="offset points",
            ha=ha, va=va, fontsize=9.0, color=FATHOM, linespacing=1.35, zorder=7,
            fontweight="bold" if x == OPERATING_LOUT else "normal",
        )

    # The operating point
    operating = float(np.interp(OPERATING_LOUT, lout, output))
    ax.scatter([OPERATING_LOUT], [operating], s=190, facecolor="none",
               edgecolor=CORAL, linewidth=2.6, zorder=6)
    ax.annotate(
        "flown here",
        xy=(OPERATING_LOUT, operating), xytext=(OPERATING_LOUT + 3.0, operating - 9.5),
        textcoords="data", fontsize=10.5, color=CORAL, fontweight="bold",
        ha="left", va="top", zorder=7,
        arrowprops=dict(arrowstyle="-", color=CORAL, linewidth=1.6,
                        connectionstyle="arc3,rad=-0.25", shrinkB=7),
    )

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 113)
    ax.set_xticks(marks)
    ax.set_yticks(np.arange(0, 101, 20))
    ax.set_xlabel("LOUT command value sent to the lamp", fontsize=11.5, color=FATHOM)
    ax.set_ylabel("light output (% of full)", fontsize=11.5, color=FATHOM)
    ax.tick_params(labelsize=10, colors=STONE)
    ax.grid(axis="y", color="#E4E8EA", linewidth=0.9, zorder=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#C7CED2")

    # Lumens on the right, sharing the same axis by construction
    right = ax.twinx()
    right.set_ylim(0, 113 / 100 * per_lamp)
    right.set_yticks(np.arange(0, per_lamp + 1, 1000))
    right.set_yticklabels([f"{v:,.0f}" for v in np.arange(0, per_lamp + 1, 1000)])
    right.set_ylabel("delivered luminous flux, one lamp (lm)", fontsize=11.5, color=FATHOM)
    right.tick_params(labelsize=10, colors=STONE)
    for side in ("top", "left"):
        right.spines[side].set_visible(False)
    right.spines["right"].set_color("#C7CED2")
    right.spines["bottom"].set_color("#C7CED2")

    ax.legend(loc="upper left", frameon=False, fontsize=10.5, labelcolor=FATHOM,
              bbox_to_anchor=(0.015, 0.995))

    fig.suptitle("The SeaSense LOUT command is not a brightness slider",
                 fontsize=16, fontweight="bold", color=FATHOM, x=0.085, ha="left", y=0.965)
    fig.text(0.085, 0.905,
             "DeepSea LED SeaLite, flood optic. Right axis is one lamp; the four-lamp rig "
             f"delivers {4 * per_lamp:,.0f} lm at LOUT 100.",
             fontsize=10.5, color=STONE, ha="left")
    fig.text(0.085, 0.052,
             "Curve digitised from Appendix C, p.10 of the LED SeaLite Operator's Manual rev. 08/27/18.",
             fontsize=8.6, color=STONE, ha="left")
    fig.text(0.085, 0.022,
             "Lumens from integrating the measured Appendix D beam — 7,030 lm delivered per lamp, "
             "not the 10,000 lm nameplate.",
             fontsize=8.6, color=STONE, ha="left")

    written, locked = [], []
    for ext in ("png", "pdf"):
        target = OUT / f"lout_dimming_curve.{ext}"
        try:
            fig.savefig(target, dpi=200, facecolor="white")
            written.append(target.name)
        except PermissionError:
            locked.append(target.name)
    plt.close(fig)

    print(f"{'LOUT':>5} {'output':>8} {'lm/lamp':>9} {'lm rig':>9}")
    for x, y in zip(marks, values):
        print(f"{x:5.0f} {y:7.1f}% {y / 100 * per_lamp:9,.0f} {4 * y / 100 * per_lamp:9,.0f}")
    print(f"\nwrote {', '.join(written)} to {OUT}")
    if locked:
        print(f"COULD NOT WRITE {', '.join(locked)} — close it in your viewer and re-run")


if __name__ == "__main__":
    main()
