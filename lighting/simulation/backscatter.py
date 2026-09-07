"""Veiling glare from the water between the lamps and the seafloor.

The tilt on the lamps is not there to improve the light on the bottom -- it makes
that slightly worse (see ``report.py``). It is there to keep the beams out of the
water the camera is looking through. Light scattered off particles in that shared
volume arrives at the sensor carrying no information about the seafloor, so it
adds signal-independent haze: contrast falls, and no amount of exposure
correction brings it back.

Answering "what tilt is best?" therefore needs this term, because the whole
trade-off lives between it and the illuminance model in ``photometry.py``.

The model
---------
This is the backscatter term of the Jaffe-McGlamery underwater imaging model.
Along the camera's line of sight to a seafloor point, each volume element is lit
by the four lamps, scatters a fraction of that light back toward the lens, and
the result is attenuated on its way up::

    L_veil = sum_j integral_0^S  E_j(Q) * b * p(psi_j) * exp(-c * s)  ds

with ``E_j`` the irradiance the lamp puts on the volume element, ``b`` the
scattering coefficient, ``p`` the scattering phase function, ``psi`` the angle
between the light's direction of travel and the direction on to the camera, and
``s`` the distance already travelled up the camera ray.

Against that sits the image-forming light off the seafloor itself::

    L_signal = rho * E_floor / pi * exp(-c * S)

Both are luminances in cd/m^2, so their ratio is the quantity that matters.

Two honest caveats
------------------
* The phase function is Henyey-Greenstein with ``g = 0.92``. Its *shape* in the
  backward hemisphere is known to be wrong in detail for seawater -- the real
  volume scattering function has a flatter back lobe -- but its integrated
  backscatter fraction (1.8 %) sits inside the range Petzold measured, and the
  tilt comparison here is driven by geometry rather than by the shape of ``p``.
* Only single scattering is modelled. In genuinely turbid water multiple
  scattering adds more veiling than this predicts, so the contrast numbers are
  an optimistic bound. Relative comparisons between tilt angles hold up much
  better than the absolute values.

Note the return path is attenuated by the full beam coefficient ``c`` here, which
is right for *contrast*: only unscattered light forms an image. The exposure
model in ``photometry.py`` deliberately does not attenuate that path, because
forward-scattered light still lands on the sensor and still exposes it. Those are
different questions about the same photons, not an inconsistency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from photometry import Rig, illuminance

# Henyey-Greenstein asymmetry parameter. 0.92 is representative of natural sea
# water and gives a backscatter fraction of 1.8 %, within Petzold's range.
HG_ASYMMETRY = 0.92

# Scattering coefficient as a fraction of beam attenuation, b/c. Coastal water is
# scattering-dominated; 0.8 is typical for the turbid inshore case.
SCATTER_FRACTION = 0.80


def henyey_greenstein(cos_psi: np.ndarray, g: float = HG_ASYMMETRY) -> np.ndarray:
    """Scattering phase function, normalised so its integral over 4*pi is 1."""
    return (1 - g * g) / (4 * np.pi * (1 + g * g - 2 * g * cos_psi) ** 1.5)


def backscatter_fraction(g: float = HG_ASYMMETRY) -> float:
    """Share of scattered light sent into the backward hemisphere."""
    return (1 - g) / (2 * g) * ((1 + g) / math.sqrt(1 + g * g) - 1)


@dataclass
class ContrastResult:
    """Signal against veiling glare, averaged over the camera frame."""

    signal_cd_m2: float
    veil_cd_m2: float
    veil_ratio: float  # veil / signal
    contrast_retention: float  # signal / (signal + veil), 1.0 is perfect
    worst_retention: float  # at the least favourable point in the frame
    overlap_height_m: float  # top of the lit volume the camera sees

    def as_rows(self) -> list[tuple[str, str]]:
        return [
            ("Signal luminance", f"{self.signal_cd_m2:,.1f} cd/m2"),
            ("Veiling luminance", f"{self.veil_cd_m2:,.1f} cd/m2"),
            ("Veil : signal", f"{self.veil_ratio:.3f}"),
            ("Contrast retained", f"{100 * self.contrast_retention:.1f} %"),
            ("Worst in frame", f"{100 * self.worst_retention:.1f} %"),
            ("Lit volume starts", f"{self.overlap_height_m:.3f} m above seafloor"),
        ]


def overlap_height(rig: Rig, level: float = 0.5) -> float:
    """Height above the seafloor where the camera first sees lit water.

    Walks down the camera's viewing cone and finds the highest point at which any
    lamp's beam -- taken out to the angle where it still holds ``level`` of peak
    intensity -- crosses into the camera's field of view. This is the top of the
    common volume, and it is the quantity the outboard tilt is really moving:
    the lower it sits, the shorter the column of illuminated water the camera has
    to look through.

    Returns the camera height when no intersection is found (i.e. the whole
    column is lit), and 0.0 when the beams never enter the frame at all.
    """
    beam_half = math.radians(rig.profile.fraction_angle(level))
    half_w, half_h = (math.atan(e / 2 / rig.camera_height()) for e in rig.fov_extent())
    camera_z = rig.camera_height()
    positions, axes = rig.lamp_positions(), rig.lamp_axes()

    for step in range(400):  # walk down from just under the lens
        z = camera_z * (1 - step / 400.0)
        depth = camera_z - z
        if depth <= 1e-4:
            continue
        # Half-extent of the camera's cone at this depth, along each axis.
        cone_x, cone_y = depth * math.tan(half_w), depth * math.tan(half_h)
        for position, axis in zip(positions, axes):
            # Closest point of the camera's footprint rectangle to this lamp's axis
            # at this depth, then test whether it lies inside the beam cone.
            t = (position[2] - z) / -axis[2]
            beam_x, beam_y = position[0] + axis[0] * t, position[1] + axis[1] * t
            beam_r = t * math.tan(beam_half)
            near_x = max(-cone_x, min(cone_x, beam_x))
            near_y = max(-cone_y, min(cone_y, beam_y))
            if math.hypot(beam_x - near_x, beam_y - near_y) <= beam_r:
                return z
    return 0.0


def contrast(
    rig: Rig,
    reflectance: float = 0.15,
    scatter_fraction: float = SCATTER_FRACTION,
    asymmetry: float = HG_ASYMMETRY,
    grid: int = 25,
    steps: int = 64,
) -> ContrastResult:
    """Veiling glare and contrast retention over the camera frame."""
    width, height = rig.fov_extent()
    camera = np.array([0.0, 0.0, rig.camera_height()])
    c = rig.attenuation
    b = scatter_fraction * c
    scale = rig.peak_intensity_cd * rig.dim_fraction()

    # Cell centres, matching fov_stats, so the two never disagree over sampling.
    ny = max(5, int(round(grid * height / width)))
    xs = -width / 2 + (np.arange(grid) + 0.5) * width / grid
    ys = -height / 2 + (np.arange(ny) + 0.5) * height / ny
    px, py = np.meshgrid(xs, ys)

    # Camera ray to each seafloor point.
    dx, dy, dz = px - camera[0], py - camera[1], -camera[2]
    path = np.sqrt(dx * dx + dy * dy + dz * dz)
    ux, uy, uz = dx / path, dy / path, dz / path

    # Midpoint rule along each ray.
    frac = (np.arange(steps) + 0.5) / steps
    s = frac[:, None, None] * path[None, :, :]
    ds = path[None, :, :] / steps
    qx = camera[0] + ux[None, :, :] * s
    qy = camera[1] + uy[None, :, :] * s
    qz = camera[2] + uz[None, :, :] * s

    veil = np.zeros_like(px)
    for position, axis in zip(rig.lamp_positions(), rig.lamp_axes()):
        wx, wy, wz = qx - position[0], qy - position[1], qz - position[2]
        r = np.sqrt(wx * wx + wy * wy + wz * wz)
        r = np.maximum(r, 1e-6)
        cos_off = (wx * axis[0] + wy * axis[1] + wz * axis[2]) / r
        theta = np.degrees(np.arccos(np.clip(cos_off, -1.0, 1.0)))
        irradiance = scale * rig.profile(theta) * np.exp(-c * r) / (r * r)
        irradiance = np.where(cos_off > 0, irradiance, 0.0)

        # Scattering angle: light travels along w-hat, and must leave along -u-hat
        # to reach the lens.
        cos_psi = -(wx * ux[None] + wy * uy[None] + wz * uz[None]) / r
        phase = henyey_greenstein(np.clip(cos_psi, -1.0, 1.0), asymmetry)
        veil += np.sum(irradiance * b * phase * np.exp(-c * s), axis=0) * ds[0]

    floor_lux = illuminance(rig, px, py)
    signal = reflectance * floor_lux / np.pi * np.exp(-c * path)
    retention = signal / np.maximum(signal + veil, 1e-12)

    mean_signal, mean_veil = float(signal.mean()), float(veil.mean())
    return ContrastResult(
        signal_cd_m2=mean_signal,
        veil_cd_m2=mean_veil,
        veil_ratio=mean_veil / mean_signal if mean_signal else float("inf"),
        contrast_retention=mean_signal / (mean_signal + mean_veil) if mean_signal else 0.0,
        worst_retention=float(retention.min()),
        overlap_height_m=overlap_height(rig),
    )
