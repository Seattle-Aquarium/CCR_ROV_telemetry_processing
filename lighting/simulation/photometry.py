"""Seafloor illuminance under a four-lamp ROV light rig.

This is the quantitative core of the lighting simulation: given the rig geometry,
the lamps, the camera and the water, it returns the illuminance field on the
seafloor, the luminous flux landing inside the down-facing camera's field of
view, and whether that adds up to a correctly exposed frame.

Coordinate frame
----------------
Right-handed, metres, origin on the seafloor directly below the ROV's centre::

    +x  starboard          +y  forward (direction of travel)
    +z  up                 seafloor is the plane z = 0

``altitude`` is defined as the height of the *lamp emitters* above the seafloor.
That definition matters: the vehicle's own altimeter reads from wherever it is
mounted, so a measured altitude has to be offset onto the lamp plane before it
is used here.

The optical model
-----------------
Each lamp is treated as a point source with an axially symmetric intensity
distribution ``I(theta) = I0 * f(theta)``, where ``f`` is the beam profile.
Illuminance at a seafloor point P is then::

    E = I0 * dim * f(theta) * cos(iota) / r**2 * exp(-c * r)

with ``r`` the lamp-to-point range, ``theta`` the angle off the lamp's optical
axis, ``iota`` the angle of incidence on the (horizontal) seafloor, and ``c`` the
water's attenuation coefficient. Contributions from the four lamps add.

The point-source approximation is safe here: the LED SeaLite's exit port is 63 mm
across and the working range is ~0.8 m, a ratio of 13, comfortably past the
factor of 5 at which inverse-square is good to about a per cent.

Not modelled
------------
* **Occlusion by the vehicle.** The payload skid and frame block part of each
  beam. This makes every number here a mild over-estimate, bounded by the skid's
  solid angle as seen from each lamp.
* **Backscatter.** Water between lamp and seafloor scatters light back into the
  camera, lowering contrast. It adds veiling luminance without adding useful
  signal, so it makes the exposure prediction slightly optimistic and the
  contrast prediction considerably so.
* **Spectral effects.** Everything here is photometric (lumens, weighted by human
  photopic response). Water attenuates red far faster than blue, so a photometric
  budget flatters a white LED underwater. Fine for exposure, not for colour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"

# Peak on-axis luminous intensity, candela. The manual quotes these as "peak lux
# at 1 m", which is numerically identical. Specification Overview p.2 gives
# 5,600 lx for the flood; Appendix D p.13 gives 5,680 lx for the measured unit.
PEAK_INTENSITY_CD = {"flood": 5680.0, "spot": 14400.0}

# Reflected-light meter calibration constant, ISO 2720. 12.5 is the value used by
# Canon, Nikon and Sekonic; Minolta and Pentax use 14.
METER_CONSTANT_K = 12.5

# Refractive index of seawater at visible wavelengths.
WATER_N = 1.333

# Blue Robotics 5-inch dome port: the entrance pupil of a correctly set-up dome
# sits at its centre of curvature, one radius behind the outer face.
DOME_5IN_RADIUS_M = 0.0635

# How much of a lamp's nameplate lumen rating actually leaves the port. The one
# lamp here with both a nameplate and a measured beam -- the LED SeaLite -- comes
# out at 7,030 lm against a stated 10,000, so 0.70 is the house assumption for
# any lamp whose beam has never been measured. Comparing a measured lamp against
# an underated one is the single easiest way to get a lamp comparison wrong.
NAMEPLATE_DERATE = 0.70


# --------------------------------------------------------------------------- #
# Beam profile
# --------------------------------------------------------------------------- #


class BeamProfile:
    """Relative luminous intensity ``f(theta)``, normalised so the peak is 1.0."""

    def __init__(self, angle_deg: np.ndarray, relative: np.ndarray, name: str = ""):
        self.angle_deg = np.asarray(angle_deg, dtype=float)
        self.relative = np.asarray(relative, dtype=float)
        self.name = name

    @classmethod
    def from_csv(cls, optic: str = "flood", path: Path | None = None) -> "BeamProfile":
        path = path or DATA_DIR / "lsl_beam_profiles.csv"
        table = np.loadtxt(path, delimiter=",")
        column = {"flood": 1, "spot": 2}[optic]
        return cls(table[:, 0], table[:, column], name=optic)

    @classmethod
    def top_hat(cls, beam_angle_deg: float) -> "BeamProfile":
        """The uniform cone the original Colab notebook assumed.

        Kept so the two models can be compared directly rather than argued about.
        """
        half = beam_angle_deg / 2.0
        angle = np.arange(0.0, 90.5, 0.5)
        return cls(angle, (angle <= half).astype(float), name=f"top-hat {beam_angle_deg:g}deg")

    @classmethod
    def cosine_power(cls, beam_angle_deg: float) -> "BeamProfile":
        """``cos^n(theta)`` with ``n`` chosen to hit the quoted half-power width.

        This is the honest fallback when a manufacturer publishes a beam angle
        and nothing else, which is the case for every lamp here except the
        SeaLite. It is a smooth, physically plausible lobe that integrates to the
        published lumens; it is *not* a measurement.
        """
        half = math.radians(beam_angle_deg / 2.0)
        n = math.log(0.5) / math.log(math.cos(half))
        angle = np.arange(0.0, 90.5, 0.5)
        return cls(angle, np.cos(np.radians(angle)) ** n, name=f"cos^{n:.2f}")

    def __call__(self, theta_deg: np.ndarray) -> np.ndarray:
        return np.interp(
            np.abs(theta_deg), self.angle_deg, self.relative, left=self.relative[0], right=0.0
        )

    def half_power_angle(self) -> float:
        """Half-angle at which intensity falls to 50 % of peak, degrees."""
        return float(np.interp(-0.5, -self.relative, self.angle_deg))

    def fraction_angle(self, level: float) -> float:
        """Half-angle at which intensity falls to ``level`` x peak, degrees."""
        return float(np.interp(-level, -self.relative, self.angle_deg))

    def total_flux(self, peak_cd: float) -> float:
        """Luminous flux over the forward hemisphere, lumens.

        ``Phi = 2*pi * I0 * integral f(theta) sin(theta) dtheta``.
        """
        theta = np.radians(self.angle_deg)
        return float(2 * np.pi * peak_cd * np.trapezoid(self.relative * np.sin(theta), theta))

    def refract_into_water(self, n: float = WATER_N) -> "BeamProfile":
        """The same beam seen through a flat port into water.

        Every ray bends toward the axis by Snell's law, so the beam narrows and
        the peak intensity rises as the same flux is packed into a smaller solid
        angle. Only relevant for a lamp whose beam angle was measured in air --
        the Kraken and Blue Robotics lamps both specify a lens that holds its
        beam angle in either medium, so this does not apply to them.
        """
        wet = np.degrees(np.arcsin(np.clip(np.sin(np.radians(self.angle_deg)) / n, -1, 1)))
        grid = np.arange(0.0, 90.5, 0.5)
        return BeamProfile(
            grid, np.interp(grid, wet, self.relative, right=0.0), name=f"{self.name} (in water)"
        )


# --------------------------------------------------------------------------- #
# Dimming
# --------------------------------------------------------------------------- #


def dimming_output(lout: float, path: Path | None = None) -> float:
    """Fraction of full output for a SeaSense ``LOUT`` command value (0-100).

    The curve is emphatically not linear: LOUT 60 buys only 15 % of full output,
    and the top quarter of the command range carries two thirds of the light.
    """
    path = path or DATA_DIR / "lsl_seasense_dimming.csv"
    table = np.loadtxt(path, delimiter=",")
    return float(np.interp(lout, table[:, 0], table[:, 1]) / 100.0)


# --------------------------------------------------------------------------- #
# Lamps
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LightSystem:
    """One of the lamp sets that has flown on this vehicle."""

    key: str
    label: str
    short: str
    beam_angle_deg: float
    published_flux_lm: float
    dimming: str  # "seasense" | "linear" | "steps"
    measured: bool  # True when the profile is a goniometer trace, not a fit
    water_stable: bool | None  # does the maker say the beam holds its angle in water?
    profile: BeamProfile
    peak_cd: float
    steps: tuple[float, ...] = ()
    note: str = ""

    def output_fraction(self, level: float) -> float:
        """Light output as a fraction of full, for this system's control scheme."""
        if self.dimming == "seasense":
            return dimming_output(level)
        if self.dimming == "steps":
            return min(self.steps, key=lambda s: abs(s - level)) / 100.0
        return max(0.0, min(100.0, level)) / 100.0

    def level_label(self) -> str:
        return {"seasense": "LOUT command", "steps": "Power level", "linear": "Output"}[
            self.dimming
        ]


def _fitted(beam_angle_deg: float, flux_lm: float) -> tuple[BeamProfile, float]:
    """Beam profile and peak intensity for a lamp specified by angle and lumens.

    The peak is solved so the profile integrates to exactly the published flux,
    which keeps the light budget honest even though the shape is a guess.
    """
    profile = BeamProfile.cosine_power(beam_angle_deg)
    return profile, flux_lm / profile.total_flux(1.0)


def _build_light_systems() -> dict[str, LightSystem]:
    kraken_profile, kraken_peak = _fitted(120.0, 18_000.0)
    lumen_profile, lumen_peak = _fitted(135.0, 1_500.0)
    flood, spot = BeamProfile.from_csv("flood"), BeamProfile.from_csv("spot")
    return {
        "sealite_flood": LightSystem(
            key="sealite_flood",
            label="DeepSea Power & Light LED SeaLite — flood optic",
            short="SeaLite flood",
            beam_angle_deg=75.0,
            published_flux_lm=flood.total_flux(PEAK_INTENSITY_CD["flood"]),
            dimming="seasense",
            measured=True,
            water_stable=None,
            profile=flood,
            peak_cd=PEAK_INTENSITY_CD["flood"],
            note=(
                "Beam digitised from Appendix D. The 10,000 lm on the spec sheet is an "
                "emitter rating; integrating the measured beam gives ~7,000 lm."
            ),
        ),
        "sealite_spot": LightSystem(
            key="sealite_spot",
            label="DeepSea Power & Light LED SeaLite — spot optic",
            short="SeaLite spot",
            beam_angle_deg=35.0,
            published_flux_lm=spot.total_flux(PEAK_INTENSITY_CD["spot"]),
            dimming="seasense",
            measured=True,
            water_stable=None,
            profile=spot,
            peak_cd=PEAK_INTENSITY_CD["spot"],
            note="Beam digitised from Appendix D.",
        ),
        "kraken_18k": LightSystem(
            key="kraken_18k",
            label="Kraken Solar Flare Mini 18000",
            short="Kraken 18k",
            beam_angle_deg=120.0,
            published_flux_lm=18_000.0,
            dimming="steps",
            measured=False,
            water_stable=True,
            profile=kraken_profile,
            peak_cd=kraken_peak,
            steps=(0.0, 20.0, 40.0, 60.0, 80.0, 100.0),
            note=(
                "18,000 lm, 120 deg beam held in air and water, five power steps. No beam "
                "profile is published, so the shape is a cosine lobe fitted to the beam angle."
            ),
        ),
        "br_lumen": LightSystem(
            key="br_lumen",
            label="Blue Robotics Lumen (x4 daisy chain)",
            short="BR Lumen",
            beam_angle_deg=135.0,
            published_flux_lm=1_500.0,
            dimming="linear",
            measured=False,
            water_stable=True,
            profile=lumen_profile,
            peak_cd=lumen_peak,
            note=(
                "1,500 lm each at 15 W, 135 deg, moulded lens holds the beam angle in air "
                "and water, continuous PWM dimming. Shape is a fitted cosine lobe."
            ),
        ),
    }


LIGHT_SYSTEMS = _build_light_systems()


# --------------------------------------------------------------------------- #
# Cameras
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CameraSpec:
    """A camera and lens, and the exposure it is normally flown at.

    Two ways of pinning down the field of view:

    ``optical``
        Sensor size and focal length, which is exact for a rectilinear lens. The
        in-air angles are then bent by the housing port -- a flat port narrows
        the view by Snell's law, a dome port preserves it.

    ``measured``
        A footprint measured on the seafloor at a known altitude. This is the
        better specification for the GoPro, whose Wide setting is a fisheye
        projection: its published field of view is measured on a curved mapping
        that plain ``tan`` geometry does not describe, so a measurement beats a
        spec sheet.
    """

    key: str
    label: str
    short: str
    mode: str  # "optical" | "measured"
    f_number: float
    iso: float
    shutter_denominator: float
    sensor_w_mm: float = 0.0
    sensor_h_mm: float = 0.0
    focal_mm: float = 0.0
    ref_width_m: float = 0.0
    ref_height_m: float = 0.0
    ref_altitude_m: float = 0.0
    dome_radius_m: float = DOME_5IN_RADIUS_M
    apertures: tuple[float, ...] = ()
    note: str = ""

    def half_angles_in_water(self, port: str = "dome") -> tuple[float, float]:
        """Half-angles (across-track, along-track) as seen underwater, radians."""
        if self.mode == "measured":
            return (
                math.atan(self.ref_width_m / 2 / self.ref_altitude_m),
                math.atan(self.ref_height_m / 2 / self.ref_altitude_m),
            )
        air = (
            math.atan(self.sensor_w_mm / 2 / self.focal_mm),
            math.atan(self.sensor_h_mm / 2 / self.focal_mm),
        )
        if port == "dome":  # a concentric dome puts the virtual image in water
            return air
        return tuple(math.asin(min(1.0, math.sin(a) / WATER_N)) for a in air)  # type: ignore[return-value]

    def object_distance(self, altitude: float, port: str = "dome") -> float:
        """Range from the entrance pupil to the seafloor, metres.

        A dome port is set up with the lens's entrance pupil at the dome's centre
        of curvature, which sits one dome radius *behind* the dome's outer face.
        An altitude quoted to the vehicle therefore understates the optical range
        by that radius -- 64 mm on a 5-inch dome, which is 7 % at 0.9 m and
        plainly visible in a calibration image.

        For a flat port the pupil-to-glass standoff has a much weaker effect,
        because the refraction at the interface dominates, so it is left out.
        """
        if self.mode == "measured" or port != "dome":
            return altitude
        return altitude + self.dome_radius_m

    def diagonal_in_air_deg(self) -> float:
        if self.mode == "measured":
            return float("nan")
        diagonal = math.hypot(self.sensor_w_mm, self.sensor_h_mm)
        return 2 * math.degrees(math.atan(diagonal / 2 / self.focal_mm))

    def footprint(self, altitude: float, port: str = "dome") -> tuple[float, float]:
        hh, hv = self.half_angles_in_water(port)
        distance = self.object_distance(altitude, port)
        return 2 * distance * math.tan(hh), 2 * distance * math.tan(hv)


CAMERAS: dict[str, CameraSpec] = {
    "gopro12": CameraSpec(
        key="gopro12",
        label="GoPro HERO 12 Black — Wide, dive housing",
        short="HERO 12 Wide",
        mode="measured",
        f_number=2.8,
        iso=200,
        shutter_denominator=300,
        ref_width_m=1.20,
        ref_height_m=0.90,
        ref_altitude_m=0.80,
        apertures=(2.8,),
        note=(
            "Fixed f/2.8. Settings from the repository README: Photo, Wide, RAW, "
            "1/300 s, ISO 100-200. Footprint measured in water, because the Wide "
            "setting is a fisheye projection and rectilinear geometry would not "
            "describe it."
        ),
    ),
    "ilx_24": CameraSpec(
        key="ilx_24",
        label="Sony ILX-LR1 + FE 24 mm F2.8 G",
        short="ILX-LR1 24 mm",
        mode="optical",
        f_number=5.6,
        iso=400,
        shutter_denominator=250,
        sensor_w_mm=35.7,
        sensor_h_mm=23.8,
        focal_mm=24.0,
        apertures=(2.8, 4.0, 5.6, 8.0, 11.0, 16.0),
        note="61 MP full frame. Sony quotes 84 deg diagonal, which this geometry reproduces.",
    ),
    "ilx_16": CameraSpec(
        key="ilx_16",
        label="Sony ILX-LR1 + FE 16 mm F1.8 G",
        short="ILX-LR1 16 mm",
        mode="optical",
        f_number=4.0,
        iso=400,
        shutter_denominator=250,
        sensor_w_mm=35.7,
        sensor_h_mm=23.8,
        focal_mm=16.0,
        apertures=(1.8, 2.8, 4.0, 5.6, 8.0, 11.0),
        note="61 MP full frame. Sony quotes 107 deg diagonal, which this geometry reproduces.",
    ),
}


# --------------------------------------------------------------------------- #
# Rig geometry
# --------------------------------------------------------------------------- #

LAMP_LABELS = {(-1, 1): "FL", (1, 1): "FR", (-1, -1): "AL", (1, -1): "AR"}


@dataclass
class Rig:
    """Geometry, lamps, camera and water. Defaults are the CCR ROV as built."""

    altitude: float = 0.80  # lamp emitter plane above seafloor, m
    lateral_spacing: float = 0.514  # port-to-starboard lamp separation, m
    longitudinal_spacing: float = 0.4635  # fore-to-aft lamp separation, m
    forward_tilt_deg: float = 10.0  # outboard fore/aft tilt, positive = away from centre
    side_tilt_deg: float = 10.0  # outboard port/starboard tilt
    peak_intensity_cd: float = PEAK_INTENSITY_CD["flood"]
    lout: float = 100.0  # control level, interpreted by the light system
    attenuation: float = 0.5  # water attenuation coefficient, 1/m
    camera_dz: float = 0.0  # camera height relative to the lamp plane, m
    fov_width: float = 1.20  # used only when `camera` is None
    fov_height: float = 0.90
    fov_ref_altitude: float = 0.80
    fov_scales_with_altitude: bool = True
    port: str = "dome"  # housing port for optical cameras: "flat" or "dome"
    derate: float = NAMEPLATE_DERATE  # applied to lamps with no measured beam
    profile: BeamProfile = field(default_factory=BeamProfile.from_csv)
    system: LightSystem | None = None
    camera: CameraSpec | None = None

    @classmethod
    def with_hardware(
        cls, light: str = "sealite_flood", camera: str = "gopro12", level: float = 100.0, **kwargs
    ) -> "Rig":
        """Build a rig from the named lamp set and camera."""
        system = LIGHT_SYSTEMS[light]
        derate = kwargs.get("derate", NAMEPLATE_DERATE)
        # A measured beam is already the truth; only nameplate lamps get derated.
        scale = 1.0 if system.measured else derate
        return cls(
            system=system,
            profile=system.profile,
            peak_intensity_cd=system.peak_cd * scale,
            lout=level,
            camera=CAMERAS[camera],
            **kwargs,
        )

    # -- derived geometry -------------------------------------------------- #

    def lamp_positions(self) -> np.ndarray:
        """(4, 3) array of lamp positions, ordered FL, FR, AL, AR."""
        sx = self.lateral_spacing / 2.0
        sy = self.longitudinal_spacing / 2.0
        return np.array(
            [
                [-sx, sy, self.altitude],
                [sx, sy, self.altitude],
                [-sx, -sy, self.altitude],
                [sx, -sy, self.altitude],
            ]
        )

    def lamp_axes(self) -> np.ndarray:
        """(4, 3) array of unit optical-axis vectors, same order as positions.

        Each lamp starts pointing straight down and is rotated outboard: roll by
        ``side_tilt`` about the fore-aft axis, then pitch by ``forward_tilt``
        about the lateral axis. Composing those two rotations gives

            n = (sx*sin(side), sy*sin(fwd)*cos(side), -cos(fwd)*cos(side))

        so the total angle off nadir is ``acos(cos(fwd) * cos(side))`` -- 14.1 deg
        for the 10 deg / 10 deg default, not 20 deg.
        """
        fwd, side = math.radians(self.forward_tilt_deg), math.radians(self.side_tilt_deg)
        axes = []
        for sx, sy in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
            axes.append(
                [
                    sx * math.sin(side),
                    sy * math.sin(fwd) * math.cos(side),
                    -math.cos(fwd) * math.cos(side),
                ]
            )
        return np.array(axes)

    def nadir_angle_deg(self) -> float:
        """Total tilt of each lamp axis away from straight down, degrees."""
        fwd, side = math.radians(self.forward_tilt_deg), math.radians(self.side_tilt_deg)
        return math.degrees(math.acos(math.cos(fwd) * math.cos(side)))

    def dim_fraction(self) -> float:
        if self.system is not None:
            return self.system.output_fraction(self.lout)
        return dimming_output(self.lout)

    def lamp_flux(self) -> float:
        """Luminous flux emitted by one lamp at the current dim level, lumens."""
        return self.profile.total_flux(self.peak_intensity_cd) * self.dim_fraction()

    # -- camera ------------------------------------------------------------ #

    def camera_height(self) -> float:
        return self.altitude + self.camera_dz

    def fov_extent(self) -> tuple[float, float]:
        """Camera footprint on the seafloor at the current altitude, metres.

        With a camera fitted, this comes from its optics (or its measured
        footprint) and grows with altitude the way a real lens does. Pinning
        ``fov_scales_with_altitude`` off holds the footprint at its reference
        size, which is only right if you never leave the reference altitude.
        """
        if self.camera is not None:
            if not self.fov_scales_with_altitude:
                return self.camera.footprint(self.camera.ref_altitude_m or 0.80, self.port)
            return self.camera.footprint(self.camera_height(), self.port)  # dome offset inside
        if not self.fov_scales_with_altitude:
            return self.fov_width, self.fov_height
        scale = self.camera_height() / self.fov_ref_altitude
        return self.fov_width * scale, self.fov_height * scale

    def fov_angles_deg(self) -> tuple[float, float]:
        """Across-track and along-track full field of view underwater, degrees."""
        if self.camera is not None:
            hh, hv = self.camera.half_angles_in_water(self.port)
            return 2 * math.degrees(hh), 2 * math.degrees(hv)
        return (
            2 * math.degrees(math.atan(self.fov_width / 2 / self.fov_ref_altitude)),
            2 * math.degrees(math.atan(self.fov_height / 2 / self.fov_ref_altitude)),
        )

    def exposure_camera(self) -> "Camera":
        if self.camera is None:
            return Camera()
        return Camera(
            f_number=self.camera.f_number,
            shutter_s=1.0 / self.camera.shutter_denominator,
            iso=self.camera.iso,
            name=self.camera.label,
        )


# --------------------------------------------------------------------------- #
# Illuminance
# --------------------------------------------------------------------------- #


def illuminance(rig: Rig, x: np.ndarray, y: np.ndarray, per_lamp: bool = False) -> np.ndarray:
    """Seafloor illuminance in lux at points ``(x, y)``, z = 0.

    ``x`` and ``y`` broadcast together. With ``per_lamp`` the leading axis of the
    result indexes the four lamps instead of summing them.
    """
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    scale = rig.peak_intensity_cd * rig.dim_fraction()
    contributions = []

    for position, axis in zip(rig.lamp_positions(), rig.lamp_axes()):
        dx, dy = x - position[0], y - position[1]
        dz = -position[2]  # seafloor is at z = 0
        r = np.sqrt(dx * dx + dy * dy + dz * dz)
        r = np.maximum(r, 1e-9)

        cos_off = (dx * axis[0] + dy * axis[1] + dz * axis[2]) / r
        cos_inc = -dz / r  # = altitude / r, the cosine law on a flat seafloor
        theta = np.degrees(np.arccos(np.clip(cos_off, -1.0, 1.0)))

        e = scale * rig.profile(theta) * cos_inc / (r * r) * np.exp(-rig.attenuation * r)
        contributions.append(np.where((cos_off > 0) & (cos_inc > 0), e, 0.0))

    return np.array(contributions) if per_lamp else np.sum(contributions, axis=0)


@dataclass
class FovResult:
    """What lands inside the camera's field of view."""

    flux_lm: float  # luminous flux incident on the FOV
    area_m2: float
    mean_lux: float
    min_lux: float
    max_lux: float
    centre_lux: float
    uniformity: float  # min / mean, the CIE U0 measure
    min_to_max: float
    cv: float  # coefficient of variation of illuminance
    emitted_lm: float  # total emitted by all four lamps
    capture_efficiency: float  # flux_lm / emitted_lm
    width_m: float
    height_m: float

    def as_rows(self) -> list[tuple[str, str]]:
        return [
            ("Flux into FOV", f"{self.flux_lm:,.0f} lm"),
            ("FOV footprint", f"{self.width_m:.2f} x {self.height_m:.2f} m"),
            ("Mean illuminance", f"{self.mean_lux:,.0f} lx"),
            ("Range", f"{self.min_lux:,.0f} - {self.max_lux:,.0f} lx"),
            ("Centre", f"{self.centre_lux:,.0f} lx"),
            ("Uniformity min/mean", f"{self.uniformity:.2f}"),
            ("Uniformity min/max", f"{self.min_to_max:.2f}"),
            ("Emitted by 4 lamps", f"{self.emitted_lm:,.0f} lm"),
            ("Captured in FOV", f"{100 * self.capture_efficiency:.1f} %"),
        ]


def fov_stats(rig: Rig, samples: int = 241) -> FovResult:
    """Integrate the illuminance field over the camera's field of view.

    Midpoint rule on a regular grid. ``samples`` is the cell count on the long
    axis; the default converges the flux to better than 0.1 %.
    """
    width, height = rig.fov_extent()
    nx = samples
    ny = max(8, int(round(samples * height / width)))

    # Cell centres, so no sample sits on the boundary.
    xs = np.linspace(-width / 2, width / 2, nx + 1)
    ys = np.linspace(-height / 2, height / 2, ny + 1)
    xc = (xs[:-1] + xs[1:]) / 2
    yc = (ys[:-1] + ys[1:]) / 2
    grid = illuminance(rig, xc[None, :], yc[:, None])

    cell = (width / nx) * (height / ny)
    flux = float(grid.sum() * cell)
    area = width * height
    mean = flux / area
    emitted = 4 * rig.lamp_flux()

    return FovResult(
        flux_lm=flux,
        area_m2=area,
        mean_lux=mean,
        min_lux=float(grid.min()),
        max_lux=float(grid.max()),
        centre_lux=float(illuminance(rig, 0.0, 0.0)),
        uniformity=float(grid.min() / mean) if mean else 0.0,
        min_to_max=float(grid.min() / grid.max()) if grid.max() else 0.0,
        cv=float(grid.std() / mean) if mean else 0.0,
        emitted_lm=emitted,
        capture_efficiency=flux / emitted if emitted else 0.0,
        width_m=width,
        height_m=height,
    )


# --------------------------------------------------------------------------- #
# Exposure
# --------------------------------------------------------------------------- #


@dataclass
class Camera:
    """Exposure settings, defaulting to the GoPro as configured in the README."""

    f_number: float = 2.8
    shutter_s: float = 1.0 / 300.0
    iso: float = 200.0
    name: str = "GoPro HERO 12/13, Wide, 1/300 s"

    def required_luminance(self) -> float:
        """Scene luminance for a nominally correct exposure, cd/m^2."""
        return self.f_number**2 * METER_CONSTANT_K / (self.shutter_s * self.iso)


def exposure_error_stops(mean_lux: float, reflectance: float, camera: Camera) -> float:
    """Stops of over- (positive) or under-exposure (negative).

    The seafloor is taken as a Lambertian diffuser, so a surface of reflectance
    ``rho`` under illuminance ``E`` has luminance ``L = rho * E / pi``.
    """
    if mean_lux <= 0:
        return float("-inf")
    luminance = reflectance * mean_lux / math.pi
    return math.log2(luminance / camera.required_luminance())


def required_illuminance(reflectance: float, camera: Camera) -> float:
    """Seafloor illuminance giving a correct exposure, lux."""
    return math.pi * camera.required_luminance() / reflectance


def solve_level(rig: Rig, reflectance: float) -> float | None:
    """Control level that best exposes the frame, or None if unreachable.

    Mean illuminance is linear in the light output, so this inverts the dimming
    curve directly rather than searching.
    """
    stats = fov_stats(rig, samples=81)
    if stats.mean_lux <= 0:
        return None
    want = rig.dim_fraction() * required_illuminance(reflectance, rig.exposure_camera()) / stats.mean_lux
    if want > 1.0:
        return None
    levels = np.arange(0.0, 100.5, 0.5)
    system = rig.system
    outputs = np.array(
        [system.output_fraction(v) if system else dimming_output(v) for v in levels]
    )
    return float(levels[int(np.argmin(np.abs(outputs - want)))])


# --------------------------------------------------------------------------- #
# Beam footprint geometry (for drawing, and for checking the original notebook)
# --------------------------------------------------------------------------- #


def footprint_ellipse(altitude: float, nadir_deg: float, half_angle_deg: float) -> dict:
    """Where a tilted cone actually meets the seafloor.

    A cone tilted off vertical cuts a horizontal plane in an **ellipse**, not a
    circle, and the ellipse is not centred on the point the axis hits. Returns the
    semi-major axis ``a`` (along the tilt direction), semi-minor ``b``, and the
    offset of the ellipse centre from the nadir point.
    """
    phi, theta = math.radians(nadir_deg), math.radians(half_angle_deg)
    if phi + theta >= math.pi / 2 - 1e-9:
        return {"a": math.inf, "b": math.inf, "centre": math.inf, "unbounded": True}

    near = altitude * math.tan(phi - theta)
    far = altitude * math.tan(phi + theta)
    a = (far - near) / 2.0
    centre = (far + near) / 2.0
    b = math.sqrt(
        (centre * math.sin(phi) + altitude * math.cos(phi)) ** 2 / math.cos(theta) ** 2
        - centre**2
        - altitude**2
    )
    return {"a": a, "b": b, "centre": centre, "unbounded": False}


def beam_crossing(rig: Rig, level: float = 0.5) -> dict:
    """Where a port beam and a starboard beam first meet, coming down from the rig.

    Above this height the two sides light separate columns of water; below it they
    light the same water twice. It is the quantity the outboard tilt was chosen to
    push downwards, so it is worth being able to state as a number rather than
    gesture at on a picture.

    Solved in 3-D rather than off the head-on projection: two cones can overlap in
    a flat projection while missing each other in space, and with fore-aft tilt in
    play they are not co-planar. The contact point lies on x = 0 by mirror
    symmetry, so the search runs over ``y`` at every height and the shallowest
    (port, starboard) pair wins.

    ``level`` selects which contour counts as the beam edge: 0.5 is the half-power
    cone drawn in the tool, 0.1 the outer contour.

    Returns the crossing height above the seafloor, its depth below the lamp
    plane, and the fraction of the centreline column that is doubly lit.
    """
    cos_half = math.cos(math.radians(rig.profile.fraction_angle(level)))
    positions, axes = rig.lamp_positions(), rig.lamp_axes()
    port = [(p, a) for p, a in zip(positions, axes) if p[0] < 0]
    starboard = [(p, a) for p, a in zip(positions, axes) if p[0] > 0]

    # Descending heights, so the first row that lights up is the highest crossing.
    zs = np.linspace(rig.altitude, 0.0, 1201)
    ys = np.linspace(-1.5, 1.5, 601)
    Z, Y = np.meshgrid(zs, ys, indexing="ij")

    def inside(position, axis):
        wx = 0.0 - position[0]
        wy = Y - position[1]
        wz = Z - position[2]
        norm = np.sqrt(wx * wx + wy * wy + wz * wz)
        norm = np.maximum(norm, 1e-12)
        return (wx * axis[0] + wy * axis[1] + wz * axis[2]) / norm >= cos_half

    best = 0.0
    for pp, pa in port:
        lit_port = inside(pp, pa)
        for sp, sa in starboard:
            rows = (lit_port & inside(sp, sa)).any(axis=1)
            if rows.any():
                best = max(best, float(zs[int(rows.argmax())]))

    return {
        "height_above_seafloor": best,
        "depth_below_lamps": rig.altitude - best,
        "doubly_lit_fraction": best / rig.altitude if rig.altitude else 0.0,
        "half_angle_deg": rig.profile.fraction_angle(level),
    }
