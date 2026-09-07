"""Splice the measured photometric data from data/*.csv into index.html.

The browser tool carries its own copy of the beam profiles and the dimming curve
so that it stays a single file that runs from a memory stick on a boat. That copy
has to be generated, never typed: transcribing 400 numbers by hand goes wrong
silently, and a beam profile shifted by one index is invisible in a screenshot but
moves every number the tool reports.

Run this after regenerating the CSVs::

    python build_web_data.py

``test_photometry.py::test_embedded_web_data_matches_the_csvs`` fails if the two
ever drift apart, so this is checked rather than merely intended.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
HTML = HERE / "index.html"


def js_array(values: np.ndarray, sig: int) -> str:
    """Shortest round-trippable JS number list, e.g. ``0.9425,1,0``."""
    return ",".join(f"{v:.{sig}g}" for v in values)


def blocks() -> dict[str, str]:
    beams = np.loadtxt(HERE / "data" / "lsl_beam_profiles.csv", delimiter=",")
    dim = np.loadtxt(HERE / "data" / "lsl_seasense_dimming.csv", delimiter=",")
    return {
        "FLOOD": js_array(beams[:, 1], 5),
        "SPOT": js_array(beams[:, 2], 5),
        "DIM": js_array(dim[:, 1], 6),  # CSV holds 3 decimals on values up to 100
    }


def main() -> None:
    text = HTML.read_text(encoding="utf-8")
    for name, body in blocks().items():
        pattern = re.compile(rf"const {name}=\[[^\]]*\];")
        if not pattern.search(text):
            raise SystemExit(f"could not find 'const {name}=[...]' in {HTML.name}")
        text = pattern.sub(f"const {name}=[{body}];", text, count=1)
        print(f"  {name}: {body.count(',') + 1} values")
    HTML.write_text(text, encoding="utf-8")
    print(f"updated {HTML}")


if __name__ == "__main__":
    main()
