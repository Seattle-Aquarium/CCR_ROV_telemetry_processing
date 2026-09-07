# ROV lighting simulation

How much light four lamps put on the seafloor, how much of it lands inside the
down-facing camera's frame, and whether that adds up to a correctly exposed
photograph — for every lamp set and camera this vehicle has flown or might fly.

Two pieces, split by job:

| | |
|---|---|
| **[`index.html`](index.html)** | Interactive tool. Open the file in any browser — no server, no install, no internet. Drag sliders, orbit the vehicle, swap hardware, read the numbers. |
| **[`photometry.py`](photometry.py)** | The same model in Python, for sweeps, tables, figures and anything that has to be reproducible. |
| **[`backscatter.py`](backscatter.py)** | Veiling glare from lit water in the line of sight — the other half of the tilt question (§3). |
| **[`READING_THE_FIGURES.md`](READING_THE_FIGURES.md)** | **Start here if the figures are new to you.** What lux, isolux lines and the transect actually mean, and which control moves which mark. |

```bash
python -m pytest                       # 87 checks on the physics, the optics and the data
python report.py                       # regenerates every table below
```

The two implementations agree to rounding across all twelve lamp/camera
combinations. Styling follows the Seattle Aquarium Visual Identity Guidelines
(v1, Aug 2023): Montserrat and Barlow Condensed, brand colours at their published
values, and the One Ocean gradient as the sequential ramp for illuminance.

---

## 1. Hardware you can switch between

### Lamp sets (always four, always at the same mount points)

| | beam angle | nameplate | **assumed delivered** | ×4 | control | beam data |
|---|---:|---:|---:|---:|---|---|
| **DeepSea LED SeaLite — flood** | 75° | 10,000 lm | **7,030 lm** | 28,120 lm | SeaSense `LOUT` 0–100 | **measured**, Appendix D |
| DeepSea LED SeaLite — spot | 35° | 10,000 lm | **4,684 lm** | 18,735 lm | SeaSense `LOUT` 0–100 | **measured**, Appendix D |
| Kraken Solar Flare Mini 18000 | 120° | 18,000 lm | 12,600 lm | 50,400 lm | 5 steps: 20/40/60/80/100 % | fitted to beam angle |
| Blue Robotics Lumen ×4 | 135° | 1,500 lm | 1,050 lm | 4,200 lm | PWM, continuous | fitted to beam angle |

Only the SeaLite publishes a beam profile. For the other two the shape is a
cosine lobe fitted to the published beam angle, with its peak solved so the lobe
integrates to the assumed delivered flux — so the *light budget* is right to
within that assumption even though the *shape* is a guess.

**On that derate.** The SeaLite is the one lamp here with both a nameplate and a
measured beam, and it comes out at 7,030 lm against a stated 10,000 — a 30 %
shortfall, which is the ordinary gap between an LED emitter rating and what
actually leaves the port. Every lamp without a measured beam is therefore derated
by the same 0.70 before being compared with it. Skipping that step is exactly how
this document got the Kraken comparison wrong the first time round (§2.1); the
derate is a slider in the tool, so you can see how much rests on it.

Both the Kraken and the Lumen explicitly state that their lens holds its beam
angle in air and in water. The SeaLite says nothing either way, which is the open
question in §7.

### Cameras

| | field of view in water | frame at 0.80 m | exposure as flown |
|---|---:|---:|---|
| **GoPro HERO 12 Black — Wide** | 73.7° × 58.7° | 1.20 × 0.90 m | f/2.8 · 1/300 s · ISO 200 |
| Sony ILX-LR1 + FE 24 mm F2.8 G | 73.3° × 52.7° | 1.28 × 0.86 m | f/5.6 · 1/250 s · ISO 400 |
| Sony ILX-LR1 + FE 16 mm F1.8 G | 96.3° × 73.3° | 1.93 × 1.28 m | f/4 · 1/250 s · ISO 400 |

*Sony bodies in the Blue Robotics 5-inch dome port, which is what they fly in;
see §1.1.*

The two Sony combinations are computed from first principles — 61 MP full frame
(35.7 × 23.8 mm) and the lens focal length — which reproduces Sony's published
84° and 107° diagonal angles of view exactly. That is asserted in the test suite,
so the geometry cannot drift.

The GoPro is handled differently, and deliberately. Its Wide setting is a
**fisheye projection**: the 156° that GoPro publishes is measured on a curved
mapping, and running it through rectilinear `tan` geometry gives nonsense (a
148° horizontal field, and a footprint half again too large). A fisheye is also
specified inconsistently across GoPro's own documentation. So the GoPro is pinned
to the footprint measured in the water — 1.20 × 0.90 m at 0.80 m altitude —
which is a real measurement of the real camera in the real housing at the real
settings, and beats a spec sheet. This is the one place where switching *away*
from that measurement would have made the model worse rather than better.

### 1.1 The 5-inch dome, and the altitude datum it exposed

A flat port refracts every ray at the glass, so the camera sees a narrower field
underwater than in air, by `sin θ_water = sin θ_air / 1.333`. A concentric dome
puts the lens's virtual image in the water and preserves the angle. That much is
textbook. What the two calibration images added is a second, smaller effect that
turns out to matter at survey altitudes.

Reading the meter tapes in the two images — 24 mm and 16 mm, both behind the 5″
dome at a stated 0.90 m — gives roughly 1.45 m and 2.15 m across the frame.
"Dome preserves the in-air angle" predicts 1.34 m and 2.01 m. Both are short by
**the same 7–8 %**, which is the signature of a systematic error rather than an
optical one. Solving each image for the object distance that would explain it:

| | in-air HFOV | implied range | offset from the stated 0.90 m |
|---|---:|---:|---:|
| 24 mm | 73.3° | 0.975 m | **+75 mm** |
| 16 mm | 96.3° | 0.964 m | **+64 mm** |

A 5″ dome has a **63.5 mm radius**, and a correctly set-up dome sits with the
lens's entrance pupil at the dome's centre of curvature — one radius behind the
outer face. So the altitude quoted to the vehicle understates the optical range
by exactly one dome radius. Adding it back:

| | predicted at a stated 0.90 m | measured | error |
|---|---:|---:|---:|
| ILX-LR1 + 24 mm | 1.433 × 0.955 m | ~1.45 m | −1.2 % |
| ILX-LR1 + 16 mm | 2.150 × 1.433 m | ~2.15 m | −0.0 % |

One physical constant, no fitting, and it reconciles both lenses at once. The
model now carries it, and the readout shows the range from the entrance pupil
alongside the altitude so the distinction stays visible.

**The practical consequence is a survey one:** at 0.9 m altitude a 64 mm datum
error is 7 % on every linear dimension and 15 % on every area. If image footprints
are being used to scale quadrat counts or percent-cover estimates, that is a
systematic bias worth pinning down — decide whether "altitude" means the dome
face, the skid, or the entrance pupil, and write it down.

Port comparison at 0.80 m, with the offset applied:

| | flat port | 5″ dome |
|---|---|---|
| ILX-LR1 + 24 mm | 0.80 × 0.57 m · 53.2° × 38.9° | 1.28 × 0.86 m · 73.3° × 52.7° |
| ILX-LR1 + 16 mm | 1.08 × 0.80 m · 67.9° × 53.2° | 1.93 × 1.28 m · 96.3° × 73.3° |

Worth noticing: **the 24 mm behind the dome gives very nearly the footprint the
GoPro gives now** — 1.28 × 0.86 m against 1.20 × 0.90 m. If the goal is to keep
survey geometry roughly continuous while moving to the Sony, that is the
combination that does it, and it does it with a rectilinear lens, which the
GoPro's fisheye is not.

---

## 2. What the corrected model says

At the as-built configuration — 0.80 m altitude, 0.514 m × 0.4635 m lamp
spacing, 10°/10° outboard tilt, SeaLite flood, `LOUT` 100, `c = 0.5 m⁻¹`,
GoPro:

| | |
|---|---:|
| **Luminous flux into the 1.20 × 0.90 m frame** | **7,706 lm** |
| Mean illuminance | 7,135 lx |
| Range across the frame | 4,068 – 8,916 lx |
| Uniformity (min:mean) | 0.57 |
| Emitted by all four lamps | 28,120 lm |
| Fraction landing in the frame | 27.4 % |
| Exposure vs the configured GoPro, ρ = 0.15 | **+1.21 stops over** |

### 2.1 Every lamp set against every camera

Full power, 0.80 m, ρ = 0.15, nameplate lamps derated to 0.70. Exposure is stops
over (+) or under (−), against each camera's own settings.

| lamps | camera | frame | flux in | mean | uniformity | captured | exposure |
|---|---|---|---:|---:|---:|---:|---:|
| SeaLite flood | HERO 12 | 1.20 × 0.90 | 7,706 lm | 7,135 lx | 0.57 | **27.4 %** | +1.21 |
| SeaLite flood | ILX 24 mm | 1.28 × 0.86 | 7,783 lm | 7,076 lx | 0.55 | 27.7 % | +0.46 |
| SeaLite flood | ILX 16 mm | 1.93 × 1.28 | 12,977 lm | 5,244 lx | 0.24 | 46.1 % | +1.00 |
| SeaLite spot | HERO 12 | 1.20 × 0.90 | 6,577 lm | 6,090 lx | **0.06** | 35.1 % | +0.98 |
| SeaLite spot | ILX 24 mm | 1.28 × 0.86 | 6,485 lm | 5,896 lx | 0.07 | 34.6 % | +0.20 |
| SeaLite spot | ILX 16 mm | 1.93 × 1.28 | 10,585 lm | 4,277 lx | 0.02 | 56.5 % | +0.71 |
| Kraken 18k | HERO 12 | 1.20 × 0.90 | 8,467 lm | 7,840 lx | 0.57 | 16.8 % | +1.35 |
| Kraken 18k | ILX 24 mm | 1.28 × 0.86 | 8,512 lm | 7,739 lx | 0.55 | 16.9 % | +0.59 |
| Kraken 18k | ILX 16 mm | 1.93 × 1.28 | 14,221 lm | 5,746 lx | 0.28 | 28.2 % | +1.13 |
| BR Lumen | HERO 12 | 1.20 × 0.90 | 645 lm | 597 lx | 0.58 | 15.4 % | **−2.37** |
| BR Lumen | ILX 24 mm | 1.28 × 0.86 | 648 lm | 589 lx | 0.56 | 15.4 % | −3.12 |
| BR Lumen | ILX 16 mm | 1.93 × 1.28 | 1,089 lm | 440 lx | 0.30 | 25.9 % | −2.57 |

#### A correction: the wide beam really does spread the light

An earlier version of this document claimed the Krakens put **57 % more** light
into the frame than the SeaLites. That was wrong, and wrong for an avoidable
reason: it compared the SeaLite's *measured* 7,030 lm against the Kraken's
*nameplate* 18,000 lm. One number had been through a goniometer; the other had
not. Derating both on the same basis (§1) closes almost all of the gap:

| | emitted ×4 | into the frame | **captured** |
|---|---:|---:|---:|
| SeaLite flood | 28,120 lm | 7,706 lm | **27.4 %** |
| Kraken 18k | 50,400 lm | 8,467 lm | 16.8 % |

The Krakens still edge ahead on absolute flux — 10 %, which is well inside the
uncertainty on a fitted beam shape and an assumed derate — but the efficiency
result is the robust one, and it goes the other way. **The SeaLite puts 63 % more
of its light where the camera is looking**, because capture efficiency depends
only on beam angle and geometry, not on anybody's lumen claim. A 120° beam
scatters most of its output outside a 1.2 × 0.9 m frame; a 75° beam does not.

So the field impression was right and the model was wrong. What the wide beam
buys is not brightness in frame but *tolerance* — it holds the same 0.57
uniformity while being far less sensitive to tilt and altitude, which is a real
operational virtue that the flux number alone does not show.

#### The Lumens could not have worked for this survey

Four of them deliver 597 lx to the frame against the ~3,080 lx the GoPro's
settings want — **2.4 stops under, at full power, with nowhere left to go.** No
dimming setting fixes an under-exposure. Even taking their nameplate 1,500 lm at
face value they are 1.85 stops short.

#### The spot optic is unusable on this rig

Uniformity 0.06. Four 35° beams from lamps 0.35 m off the centreline, tilted
outboard, simply miss the middle of the frame. It captures the *highest* fraction
of emitted light of any combination and still produces the worst picture — a good
reminder that capture efficiency is not by itself the figure of merit.

#### The 16 mm frame is larger than the lit patch

Behind the dome the 16 mm sees 1.93 × 1.28 m, which reaches well past the pool of
light the four lamps make. It captures 46 % of the emitted flux — the most of any
combination — but uniformity falls to 0.24, and the mean drops to 5,244 lx
because that flux is spread over 2.5 m². The 24 mm is the better match to this
lighting rig: essentially the same flux in frame, over a smaller area, at more
than twice the uniformity.


### 2.2 The outward tilt puts the centre of frame on the half-power contour

This falls straight out of the geometry and is the most useful single result
here. Each lamp sits `√((0.514/2)² + (0.4635/2)²)` = 0.346 m off the centreline,
so the ray from a lamp to the point directly below the camera is already 23.4°
off vertical. The lamp is tilted 14.1° the *other* way. Total: **37.5° off axis —
which is the flood optic's half-power angle almost exactly.**

Every SeaLite is illuminating the middle of your frame at 49 % of its peak
intensity. Untilting them entirely raises the flux into frame by 45 %. This is
also why the wide-beam Kraken does better here: at 37.5° off axis a 120° beam is
still near its peak.

### 2.3 But the tilt is buying uniformity, and 10° is close to the sweet spot

| tilt | off nadir | flux into frame | mean | min | uniformity | exposure |
|---:|---:|---:|---:|---:|---:|---:|
| 0° | 0.0° | 11,196 lm | 10,367 lx | 3,696 lx | 0.36 | +1.75 |
| 5° | 7.1° | 9,479 lm | 8,776 lx | 4,030 lx | 0.46 | +1.51 |
| **10°** | **14.1°** | **7,706 lm** | **7,135 lx** | **4,068 lx** | **0.57** | **+1.21** |
| 12.5° | 17.6° | 6,852 lm | 6,345 lx | 3,993 lx | **0.63** | +1.04 |
| 15° | 21.1° | 6,030 lm | 5,583 lx | 1,403 lx | 0.25 | +0.86 |
| 20° | 28.0° | 4,499 lm | 4,166 lx | 80 lx | 0.02 | +0.44 |

Uniformity climbs steadily to about 12.5° and then **falls off a cliff**. Past
13° or so the beams' 50 %-to-10 % shoulders sweep inboard past the frame corners
and leave them nearly unlit — the minimum drops from 3,993 lx to 1,403 lx over
2.5° of tilt, and to 80 lx by 20°.

So the as-built 10° is a good setting and there is a little more uniformity
available at 12.5°, at the cost of 11 % of the light. **What you must not do is
overshoot.** Given you are over-exposed anyway, trading light for uniformity is
the right direction — but the usable window closes hard at ~13°.

### 2.4 Altitude: 0.80 m is close to the uniformity optimum too

| altitude | frame | flux into frame | mean | uniformity |
|---:|---|---:|---:|---:|
| 0.40 m | 0.60 × 0.45 m | 3,136 lm | 11,617 lx | **0.02** |
| 0.60 m | 0.90 × 0.67 m | 6,487 lm | 10,679 lx | 0.25 |
| **0.80 m** | 1.20 × 0.90 m | 7,706 lm | 7,135 lx | **0.57** |
| 1.00 m | 1.50 × 1.12 m | 7,940 lm | 4,705 lx | 0.44 |
| 1.20 m | 1.80 × 1.35 m | 7,727 lm | 3,180 lx | 0.36 |
| 2.00 m | 3.00 × 2.25 m | 5,744 lm | 851 lx | 0.23 |

The flux into frame barely moves between 0.8 and 1.5 m — the frame grows at
almost exactly the rate the illuminance falls. What changes is the mean, and
therefore the exposure.

**Below ~0.6 m the rig develops a dark hole directly under the camera.** At 0.40 m
the angle from each lamp to the frame centre is 40.9° + 14.1° = 55°, past the
point where the flood optic has any output left. The frame is lit around the
edges and black in the middle. If you have ever flown low and wondered why the
imagery went strange, that is why.

### 2.5 `LOUT` 80 is the right setting, and that is the model's best validation

At f/2.8 and ISO 200 with a 1/300 s shutter, a nominally correct exposure on a
ρ = 0.15 seafloor needs about **3,080 lx**. At full power the rig delivers 7,135 lx
— 1.2 stops over. Solving for the setting that lands it:

| lamps | control level for a correct exposure (GoPro, ρ = 0.15) |
|---|---|
| SeaLite flood | `LOUT` **81** — which is only 43 % output |
| SeaLite spot | `LOUT` 84 — 51 % output |
| Kraken 18k | power step **40 %** |
| BR Lumen | beyond full power |

**The rig is flown at `LOUT` 80.** That setting was arrived at in the field, by
looking at pictures. The model, built from a beam profile digitised out of a PDF,
a dimming curve digitised out of the same PDF, the rig geometry, an inverse-square
and cosine falloff, an assumed water attenuation, and the ISO 2720 exposure
relation, independently lands on `LOUT` 81 — and puts `LOUT` 80 at **−0.08 stops**.

Nothing in the model was tuned to that. It is the one place where a long chain of
digitisation and assumption gets checked against an outcome nobody in the chain
knew about, and it comes out within a tenth of a stop. It also means the pieces
that are individually uncertain — the derate, the attenuation coefficient, the
reflectance — cannot all be far wrong at once, because their errors would have to
cancel to land this close.

Two caveats, so this is not oversold. It is one operating point, not a curve; and
`c = 0.5 m⁻¹` and ρ = 0.15 were chosen as reasonable middles before this
comparison was made, so a compensating pair of errors is possible in principle.
Test 3 in §8 is the cheap way to turn one point into a curve.

Because of the SeaSense curve's shape, `LOUT` 81 *looks* like a high setting
while the light is well down at 43 %. The tool has a **Correctly exposed** preset
that solves for this at whatever settings you dial in, and an **As flown** preset
that reproduces the `LOUT` 80 operating point.

### 2.6 Water is the biggest unknown in the absolute numbers

| `c` (m⁻¹) | 0.0 | 0.35 | 0.5 | 0.8 | 1.2 | 2.0 |
|---|---:|---:|---:|---:|---:|---:|
| mean illuminance | 10,898 | 8,102 | **7,135** | 5,535 | 3,947 | 2,008 lx |

A 5× swing across a plausible range for Puget Sound. The default of 0.5 m⁻¹ is a
reasonable middle for coastal water but it is a guess, and it is the term most
worth replacing with a measurement. The *relative* results — where the light
goes, how uniform it is, the shape of the tilt optimum, which lamp set wins — are
almost untouched by it. Only the absolute lux and the exposure move.

---

## 3. Choosing the tilt

The tilt is the only setting on this rig that trades two different things against
each other, and until now the model only knew about one of them. Backscatter was
on the "not modelled" list, so every earlier statement about tilt was answering
half the question. [`backscatter.py`](backscatter.py) supplies the other half.

### 3.1 What the tilt is actually buying

Light scattered off particles in the water *between* the lamps and the seafloor
reaches the sensor carrying no information about the bottom. It is
signal-independent haze: contrast falls, and no exposure setting brings it back.
The model is the backscatter term of Jaffe–McGlamery — walk down the camera's
line of sight, ask how brightly each lamp lights each volume element, scatter a
fraction of that back toward the lens with a Henyey–Greenstein phase function,
attenuate it on the way up, and compare the total against the image-forming light
coming off the seafloor.

Two structural results make this easier to reason about than it looks:

- **Contrast does not depend on how bright you run the lamps.** Signal and veil
  both scale linearly with output, so their ratio does not. Dimming cannot buy
  back contrast lost to backscatter — which means the tilt question can be
  settled without first settling the exposure question. Asserted in the tests.
- **The tilt fights glare by dimming the shared volume, not by shrinking it.**
  The top of the lit column the camera looks through moves only from 0.594 m to
  0.562 m between 0° and 10°. What changes far more is the *intensity* in that
  column as the beam cores swing away from the line of sight — which is why glare
  falls by a third while the overlap height barely moves. Your mental model was
  right about the mechanism mattering, but the lever is brightness, not height.

### 3.2 The answer: no, do not go to 0°

| tilt | flux into frame | uniformity | veil : signal | contrast kept |
|---:|---:|---:|---:|---:|
| **0°** | 11,197 lm | **0.36** | **0.0275** | 97.3 % |
| 5° | 9,479 lm | 0.46 | 0.0243 | 97.7 % |
| **10° — as flown** | 7,706 lm | **0.57** | **0.0182** | 98.2 % |
| 12° | 7,021 lm | **0.62** | 0.0169 | 98.3 % |
| 13° | 6,685 lm | 0.62 | 0.0162 | 98.4 % |
| 14° | 6,355 lm | **0.42** ⚠ | 0.0156 | 98.5 % |
| 20° | 4,499 lm | 0.02 ⚠ | 0.0124 | 98.8 % |

**Dropping to 0° would make both things worse at once.** Uniformity falls from
0.57 to 0.36, and glare rises by 51 %.

The part that does not survive contact with the numbers is the intuition that
flat lamps give more even coverage — because the lamps are not at the centre of
the frame. They sit 0.35 m off the camera axis, so pointing them straight down
puts four bright pools *under the lamps* and a dim patch in the middle. Tilting
outboard is what pushes those pools apart until their shoulders overlap under the
camera and fill it in.

The only thing 0° buys is flux — 45 % more light in the frame — and this rig has
light to spare: you are over-exposed at full power and already flying at
`LOUT` 80.

So the tilt was a good call, and for one more reason than you had in mind. You
adopted it to fight backscatter, and it turns out to be the thing fixing the
uniformity as well.

### 3.3 The optimum, and the cliff right behind it

Uniformity climbs to **12–13°** and then falls off a cliff: 0.62 at 13°, 0.42 at
14°, 0.02 by 20°. That is real physics rather than a metric artefact — past ~13°
the beams' 50 %-to-10 % shoulders sweep inboard past the frame corners and leave
them unlit.

Sweeping both axes independently finds a slightly better peak off the diagonal,
because the frame is wider (1.20 m) than it is tall (0.90 m):

| setting | uniformity | worst within ±2° | veil : signal |
|---|---:|---:|---:|
| 0° / 0° | 0.363 | 0.363 | 0.0275 |
| **10° / 10° — as flown** | 0.574 | 0.525 | 0.0182 |
| 12° / 12° | 0.620 | 0.416 | 0.0169 |
| 8° side / 17° fore-aft — nominal peak | **0.669** | 0.299 ⚠ | 0.0178 |
| 16° side / 4° fore-aft — most robust | 0.618 | **0.579** | 0.0203 |

The nominal peak at 8/17 is a spike sitting next to the cliff: knock it 2° and it
collapses to 0.30. Since these are ball mounts set by eye, the column that
actually matters is "worst within ±2°", and by that measure the best setting uses
more side tilt than fore-aft tilt — which makes sense for a landscape frame.

**The practical read: you are already close, and the available gain is small.**
Going 10/10 → 12/12 buys about 8 % uniformity with 1–2° of margin before the
cliff. Going to 16° side / 4° fore-aft buys about 10 % and is markedly more
tolerant of being knocked, at the cost of an asymmetric setup that is harder to
set and verify. Neither is worth a field trip on its own. **What matters far more
is not overshooting 13° symmetric.**

### 3.4 The right tilt tracks the altitude you fly

This is the one result that might change how you operate.

| altitude | best symmetric tilt | uniformity there | at 0° | at 10° |
|---:|---:|---:|---:|---:|
| 0.50 m | **2°** | 0.84 | 0.77 | 0.04 |
| 0.60 m | 7° | 0.76 | 0.57 | 0.25 |
| 0.70 m | 10° | 0.68 | 0.44 | 0.68 |
| **0.80 m** | **13°** | 0.62 | 0.36 | 0.57 |
| 0.90 m | 15° | 0.61 | 0.31 | 0.50 |
| 1.00 m | 16° | 0.56 | 0.27 | 0.44 |
| 1.20 m | 19° | 0.53 | 0.22 | 0.36 |

The frame grows with altitude while the lamp spacing does not, so the beams have
to spread further to cover it. Two consequences:

- **At 0.5–0.6 m your 10° tilt is actively harmful** — uniformity 0.04 at 0.50 m
  against 0.77 with the lamps flat. That is the dark hole of §2.4 seen from the
  other side: down there the tilt walks the beams straight past the centre of
  frame. If you ever fly that low deliberately, flatten the lamps.
- **Above 1 m you are under-tilted**, though the penalty is milder — 0.44 against
  a possible 0.56 at 1.0 m.

Your 10° is the right answer for roughly 0.70–0.85 m, which is where you fly. It
is well chosen for the altitude band, not a compromise.

### 3.5 How much any of this is worth depends on the water

| `c` (m⁻¹) | veil at 0° | veil at 10° | glare cut | contrast kept, 0° → 10° |
|---:|---:|---:|---:|---|
| 0.2 — clear | 0.0088 | 0.0061 | 31 % | 99.1 % → 99.4 % |
| 0.5 — default | 0.0275 | 0.0182 | 34 % | 97.3 % → 98.2 % |
| 1.0 | 0.0810 | 0.0505 | 38 % | 92.5 % → 95.2 % |
| 1.8 — turbid | 0.2827 | 0.1594 | 44 % | 78.0 % → **86.3 %** |
| 2.5 — bad day | 0.7278 | 0.3762 | 48 % | 57.9 % → **72.7 %** |

In clear water the backscatter argument is nearly irrelevant — a third off
something already under 1 % — and the tilt is worth having purely for uniformity.
**In turbid water it earns its keep properly**: at `c = 1.8` the tilt is the
difference between retaining 78 % and 86 % of your contrast, and at the worst
corner of the frame between 26 % and 41 %. The murkier the day, the more the tilt
is doing for you, and the more the extra couple of degrees toward 12–13° is worth
taking.

The absolute glare numbers here are an optimistic bound: only single scattering is
modelled, so genuinely turbid water will be worse than the table says. The
*relative* comparison between tilt angles is much sturdier than the absolute
values, because it is driven by geometry rather than by the phase function.



### 3.6 Beam angle: a lever you have, but not one this model can optimise freely

You can change the optic, so it is fair to ask what beam angle you *should* want.
The honest answer is bounded by data, and the bound is worth stating plainly.

I have exactly **two measured beam profiles**: the flood (75°, flat-topped with a
cliff at ~43°) and the spot (35°, a smooth rounded lobe). Two attempts to
generalise beyond them both failed:

- **A `cosⁿ` lobe fitted to an arbitrary beam angle** has a long tail that a real
  optic does not. At 20° tilt it predicts uniformity 0.83 for a 75° beam, where
  the measured profile gives **0.02** — because the fitted tail keeps lighting
  frame corners that the real beam has already abandoned. Useful for the *trend*
  at modest tilt, badly wrong at the extremes.
- **Stretching the measured flood to a different width** also fails: squeezed to
  the spot's 33° it predicts 0.05 at 20° off axis where the measured spot gives
  0.36. The two optics are not the same shape scaled — the flood spreads, the
  spot collimates, and they belong to different families.

So **any beam angle without a measured trace is speculation**, and the tool
labels fitted shapes as such. What can be compared honestly is the three optics
DSPL actually sells, with power free (since contrast does not depend on it) and
correct exposure required to be reachable:

| optic | tilt | uniformity | veil : signal | `LOUT` for ρ = 0.15 |
|---|---:|---:|---:|---:|
| spot 35° *(measured)* | 5° | 0.21 | 0.0163 | 79 |
| **flood 75° *(measured)*** | **12°** | **0.62** | **0.0168** | **83** |
| flood 75° *(measured)* | 15° | 0.25 ⚠ | 0.0150 | 86 |
| wide 115° *(fitted shape)* | 12° | 0.59 | 0.0462 | 92 |
| wide 115° *(fitted shape)* | 20° | 0.64 | 0.0331 | 96 |

**The flood at 12° wins, and it is not close.** The spot never exceeds 0.21. The
wide optic reaches a marginally better uniformity only at 20° tilt, and pays
**three times the backscatter** for it while needing `LOUT` 96 — no power headroom
left for a murky day. Its shape is a fitted guess anyway.

Which means the beam-angle lever, in practice, is already pulled: you are on the
right optic and the useful adjustment is the couple of degrees of tilt in §3.3.

### 3.7 "More lumens in frame" is not the trade it looks like

The specific hypothesis worth testing was: accept more beam overlap, higher up in
the camera's view, to put more light in the frame and buy a better exposure. Two
findings say no.

**First, you are not short of light where you fly.** At 0.80 m in moderate water
a correct exposure needs `LOUT` 83 of a possible 100. Lumens are not the binding
constraint, so trading anything for more of them is trading something for nothing.
Full power stops reaching a correct exposure only here:

| altitude | c = 0.5 | c = 1.0 | c = 1.5 | c = 2.0 |
|---:|---:|---:|---:|---:|
| 0.60 m | 76 | 82 | 88 | 96 |
| **0.80 m** | **83** | 92 | — | — |
| 1.00 m | 92 | — | — | — |
| 1.20 m | — | — | — | — |

*(`LOUT` needed at 12° tilt; "—" = beyond full power.)*

**Second — and this is the part that surprised me — even inside the light-limited
regime, flattening the lamps is still the wrong move.** At 1.5 m in `c = 1.0`
water, where full power cannot expose the frame at any tilt:

| tilt | mean illuminance | uniformity | veil : signal | contrast kept |
|---:|---:|---:|---:|---:|
| 0° | 1,066 lx | 0.16 | **1.198** | 45 % |
| 6° | 942 lx | 0.22 | 0.856 | 54 % |
| 12° | 776 lx | 0.29 | 0.638 | **61 %** |

Dropping to 0° buys 37 % more light and costs 16 points of contrast and half the
uniformity. Note the veil:signal ratio at 0°: **greater than 1 — the glare is
brighter than the picture.**

The reason is the invariance from §3.1. Signal and veil both scale linearly with
lamp output, so their ratio is fixed. **You cannot brighten your way out of
backscatter** — and precisely in the conditions that tempt you to flatten the
lamps for more light, backscatter is what is destroying the image, and flattening
makes it worse.

When you are genuinely light-limited the fixes are: **fly lower** (the strongest
lever, since `1/r²` and `exp(−c·r)` compound), open the aperture, raise ISO, or
accept underexposure and recover it in RAW. Flattening the lamps is not on that
list at any altitude or turbidity in the operating envelope.

---

## 4. Review of the original Colab notebook

The notebook draws the right *picture* — four lamps, four tilted cones, four
patches on the seafloor — and the geometry it does attempt is mostly sound. The
lamp positions, the outboard tilt convention and the labelling are all fine. What
follows is what needed changing, worst first.

### 4.1 The beam was modelled as a uniform cone. It is nothing like one

This is the one that matters. The notebook treats the 75° beam angle as the edge
of the light: full brightness inside the cone, nothing outside. Two things are
wrong with that.

**75° is the half-power full width (HPFW).** The manual says so explicitly in the
Specification Overview. At the rim of the cone the notebook draws, the lamp is at
**50 %** of peak intensity, not 100 %, and there is still useful light well
outside it — the flood optic does not fall below 10 % until 43.8° off axis, and
not below 1 % until 50.2°.

**The distribution is flat-topped, not a lobe.** Digitising Appendix D shows a
plateau at 94–100 % of peak from the axis all the way out to ~25°, then a cliff:
75 % at 30°, 49 % at 37.5°, 33 % at 40°, 7 % at 45°. It is a top hat with soft
shoulders. A `cosⁿ` lobe fitted to the same beam angle — the usual guess when
only a beam angle is published — gets the middle and the edge both wrong, in
opposite directions.

What that costs, at the as-built settings:

| beam model | illuminance directly below camera | mean over frame | uniformity |
|---|---:|---:|---:|
| measured (Appendix D) | **8,764 lx** | 7,135 lx | 0.57 |
| uniform cone (the notebook) | 17,751 lx | 7,662 lx | 0.53 |
| `cos²·⁹⁹` fitted to 75° | 8,879 lx | 7,759 lx | 0.59 |

The uniform-cone assumption **overstates the light directly beneath the camera by
a factor of two** — a full stop of exposure. Note the mean is only 7 % out: the
top hat over-predicts the centre and under-predicts the edges and the two errors
largely cancel when you average. So the old model was not bad for a crude flux
budget, and badly wrong for anything spatial.

All three models are selectable in the tool.

### 4.2 There was no photometry at all

The notebook draws where the light goes but never how much arrives. Missing:

- **Inverse-square falloff** — illuminance goes as `1/r²`.
- **The cosine law** — a ray striking the seafloor at an angle spreads its flux
  over a larger area, by `cos(incidence)`.
- **Attenuation in water** — `exp(−c·r)`, and over a 0.87 m slant path with
  `c = 0.5 m⁻¹` that is already a 35 % loss.

Without these there is no lux, no lumens, and no way to answer the question you
actually asked. This is the bulk of what has been added.

### 4.3 The footprint radius used altitude instead of slant range

```python
beam_radius = np.tan(theta) * rov_altitude   # should be the slant distance
```

The lamps are tilted, so the distance to the seafloor along the beam axis is
`altitude / cos(tilt)` = 0.825 m, not 0.800 m. Small — 3 % — but free to fix.

### 4.4 A tilted cone cuts a plane in an ellipse, not a circle

The notebook draws a circle centred on the point where the beam axis hits the
seafloor. Neither is right. A tilted cone meets a horizontal plane in an
**ellipse**, and the ellipse's centre is **not** the axis intercept — it sits
further out, because the far edge of the cone runs away downrange faster than the
near edge comes in.

| | semi-major | semi-minor | centre offset from nadir |
|---|---:|---:|---:|
| true half-power patch | 0.678 m | 0.645 m | **0.332 m** |
| circle the notebook drew | 0.614 m | 0.614 m | 0.201 m |

So the drawn patch is 9 % too small and sits 39 % too close to the vehicle. Turn
on *Overlay old notebook's circle* in the tool to see both at once.
`footprint_ellipse()` in `photometry.py` has the closed form.

### 4.5 Smaller things

- **`ax.set_box_aspect([1,1,1])` with unequal ranges.** x and y span 3 m, z spans
  1.25 m, so the vertical was stretched 2.4×. Every beam looked far steeper than
  it is — misleading in a figure whose entire purpose is beam geometry.
- **Hard-coded axis limits** (±1.5 m, z ≤ 1.25). At 2.0 m altitude the footprints
  run off the plot with no warning.
- **`plt.tight_layout()`** on a 3-D axes warns and does very little.
- **`light_labels.get(...)`** keys on `int(np.sign(x))`, so a spacing of exactly
  zero silently loses the label.
- The alpha-blended overlap of the four patches looks like a measure of beam
  overlap but is not one — it is just four translucent polygons.

### 4.6 One thing that looked wrong and is not

The tilt is built from tangents rather than a rotation:

```python
dx = np.tan(side_tilt); dy = np.tan(forward_tilt); dz = -1
```

That is not the same as rotating the downward axis by 10° and then 10° again, but
the difference is 14.01° vs 14.11° off nadir — a tenth of a degree, far below any
angle you can set on a ball mount. `photometry.py` uses the proper composed
rotation, but the original was fine.

Worth stating plainly though, because it is a common trap: **10° of pitch plus
10° of roll is 14.1° off vertical, not 20°.**

---

## 5. What the manual actually gives you

The charts in the LED SeaLite manual are vector art, not images, so the polylines
carry the manufacturer's measured values.
[`data/extract_from_manual.py`](data/extract_from_manual.py) pulls them out and
converts them to physical units; the results are committed as CSV so nobody needs
the PDF to run anything.

| quantity | flood (`-075-`) | spot (`-035-`) | source |
|---|---:|---:|---|
| Peak intensity | 5,680 cd | 14,400 cd | Appendix D, p.13 |
| Beam angle (HPFW) | 75° | 35° | Spec Overview, p.2 |
| Measured half-power width | 74.4° | 32.7° | integrated from the digitised trace |
| Falls to 10 % by | 43.8° | 26.6° | " |
| Integrated flux | **~7,030 lm** | ~4,684 lm | " |

**The 10,000 lm on the spec sheet does not survive contact with the beam data.**
Integrating the measured distribution against the measured peak intensity gives
about 7,000 lm out of the flood optic and 4,700 out of the spot. Both numbers
come from the same document. The most likely reading is that 10,000 lm is the LED
package rating before the optic, the port and the housing take their cut — the
spot integrating to even less is what you would expect from a tighter optic with
more surface interactions. **Use ~7,000 lm per lamp, not 10,000**, and it is
worth a note to DSPL to confirm.

The SeaSense dimming curve (Appendix C) is also digitised, because it is severely
non-linear and the Pico drives it directly via `Sealite.set_level()`:

| LOUT | 25 | 50 | 60 | 70 | 80 | 90 | 100 |
|---|---:|---:|---:|---:|---:|---:|---:|
| light output | 6.6 % | 12.6 % | 15.0 % | 24.2 % | 40.7 % | 65.3 % | 100 % |

Two thirds of the light lives in the top quarter of the command range. Anything
that maps a joystick axis linearly onto `LOUT` will feel dead for most of its
travel and then jump.

---

## 6. What is not modelled

- **Occlusion by the vehicle.** The payload skid and frame block part of each
  beam, so every number here is a mild over-estimate. Bounded by the skid's solid
  angle seen from each lamp; would need the CAD to do properly.
- **Multiple scattering.** Backscatter itself *is* now modelled (§3), but only to
  first order: a photon is allowed to scatter once on its way to the lens. In
  genuinely turbid water light scatters repeatedly, adding veiling the model does
  not see, so every contrast figure is an optimistic bound. Comparisons between
  tilt angles hold up much better than the absolute numbers, because they are
  driven by geometry rather than by the phase function.
- **The shape of the volume scattering function.** Henyey–Greenstein with
  `g = 0.92` gets the integrated backscatter fraction right (1.8 %, inside
  Petzold's range) but is known to be wrong in detail across the backward
  hemisphere.
- **Return-path attenuation in the exposure model.** The contrast model
  attenuates the seafloor-to-lens path by the full beam coefficient, which is
  correct for image formation: only unscattered light forms an image. The
  *exposure* model deliberately does not, because forward-scattered light still
  lands on the sensor and still exposes it. The truth sits between the two, which
  is one reason `c` is better thought of as a fitted effective coefficient than
  as a measured optical property.
- **Spectral effects.** Everything here is photometric — lumens, weighted for
  human vision. Water kills red far faster than blue, so a photometric budget
  flatters a white LED underwater. Fine for exposure, not for colour rendition.
- **Beam shape for the Kraken and Lumen**, which is fitted rather than measured.
- **How much of a nameplate lumen rating is real.** The 0.70 derate is borrowed
  from the one lamp that can be checked, and applied to two that cannot. It is a
  slider in the tool for exactly that reason: the Kraken/SeaLite flux comparison
  in §2.1 moves with it, though the capture-efficiency comparison does not.
- **Whether the SeaLite's beam spec is in air or in water.** See below.

---

## 7. The air-versus-water question, and how to settle it

The Kraken and the Lumen both state that their lens holds its beam angle in air
and in water. DSPL says nothing either way about the SeaLite, and it matters.

If DSPL measured that 75° on a goniophotometer in air, then in water each ray
refracts at the flat port and the beam **narrows** — `sin θ_water = sin θ_air /
1.33` gives a 54° in-water beam, with the peak intensity nearly doubled as the
same flux is packed into a smaller solid angle.

Running that through the model is striking. The mean illuminance rises only 19 %
(+0.25 stops), but **uniformity collapses from 0.57 to 0.02**: the narrowed beams
stop overlapping under the camera and leave the centre of frame dark.

That makes it easy to settle without any equipment. **Look at imagery you already
have.** If your frames are broadly evenly lit, the datasheet angle is already
effectively the in-water figure and the model's defaults are right. If there is a
persistent dark patch in the middle of the frame, the beams are narrower than the
datasheet says and everything here should be re-run with the narrowed profile.
`BeamProfile.refract_into_water()` does that transformation.

The model takes the datasheet at face value by default, because that is the
defensible assumption until measured.

---

## 8. Field tests this suggests

Roughly in order of how much they would tighten the model:

1. **A lux meter on the seafloor, one lamp on, at a known altitude.** One reading
   calibrates the two largest unknowns at once — whether `I₀` is right in water,
   and what `c` actually is at your sites. Two readings at different altitudes
   separate them: the ratio gives `c`, the absolute value gives `I₀`.
2. **A grey card in frame, at several `LOUT` values.** Ties the dimming curve, the
   exposure model and the GoPro's actual metering together, and tells you the
   `LOUT` you should be flying at. Cheaper than (1) and uses gear you have.
3. **A tilt sweep at 0°, 10°, 12.5° and 15°** over a flat, uniform patch,
   ideally on a murky day. §3.2 predicts uniformity peaks near 12.5° and
   collapses by 15°, and that 0° is visibly *both* patchier and hazier than 10°.
   Shooting it in turbid water is what separates the two effects: the uniformity
   difference is there in any water, the glare difference only bites when
   `c` is high (§3.5).
4. **An altitude sweep down to 0.4 m.** §2.4 predicts a dark centre appearing
   below ~0.6 m, and §3.4 predicts that flattening the lamps *fixes* it down
   there. Two predictions from one sweep, both sharp.
5. **Nail down the altitude datum.** Two more tape shots like the dome
   calibration images, at 0.6 m and 1.2 m, would confirm the 64 mm entrance-pupil
   offset directly from the slope rather than inferring it from a single altitude
   — and would say once and for all whether "altitude" in the flight log means
   the dome face, the skid, or the pupil. Cheapest test here, and the one with a
   direct bearing on any area-based estimate (§1.1).
6. **If the Krakens are still on the shelf, one flight with them** at 40 % power
   against the SeaLites at `LOUT` 80. §2.1 predicts near-identical exposure and
   uniformity, with the Krakens ahead on flux into frame by about 10 % and behind
   on capture efficiency by 63 %. That is a sharper A/B than it sounds: if the
   Krakens come out visibly brighter than the SeaLites at those settings, the
   0.70 derate on their nameplate is too harsh; if they come out dimmer, it is
   too generous.
7. **A photograph of the seafloor with a single lamp on, from a known altitude.**
   Photometry from a single image against a grey reference recovers the whole beam
   profile in situ, which would settle §7 outright and replace both the fitted
   lobes and the derate with measurements.

---

## 9. On Google Colab, and why this is not in a notebook

Colab was a reasonable place to start, and it is a bad place to end up for this
particular job. The problems are structural, not cosmetic:

- **Every slider drag is a network round trip.** `ipywidgets.interact` re-runs the
  function on the kernel and ships a fresh PNG back — 200–500 ms per update on a
  good connection, which is exactly the interaction the exercise needs to be fast.
  You learn what tilt does by *sweeping* it, not by sampling it.
- **Matplotlib's 3-D is not a renderer.** It sorts whole artists by depth with no
  real occlusion, which is why a vehicle body drawn there would punch through its
  own beams. It cannot do the thing you asked for.
- **It needs a runtime, an account and the internet.** A 30–90 s cold start every
  session, a Google login for every collaborator, and nothing at all on a boat.
- **It does not version-control.** A notebook is a JSON blob with output embedded;
  the diffs are unreadable and the outputs are committed alongside the source.

So the tool is a **single self-contained HTML file** instead. No build step, no
package manager, no CDN, no dependencies — it renders its own 3-D. Consequences
that matter here:

- Double-click it and it runs. Offline, from a memory stick, on the boat.
- It is a text file, so it diffs and reviews like the rest of the repo.
- If Pages is enabled for this repository it serves straight from `main` at
  `…/lighting/simulation/`, which gives collaborators a URL rather than a
  checkout.

Options considered and not taken: **Plotly/Dash/Streamlit** all render nicely but
need a live Python process, which is the same "needs a runtime" problem in a new
suit; **three.js** would have been less code for the 3-D view, but it has to come
off a CDN, and a tool that stops working exactly when you are offshore is not
worth the saved lines.

What a notebook *is* good for is batch work, and [`report.py`](report.py) covers
that without one: every table above regenerates from `python report.py`.

---

## 10. Files

```
index.html                     the interactive tool (open it in a browser)
photometry.py                  the model: lamps, cameras, illuminance, FOV, exposure
backscatter.py                 veiling glare and contrast retention (Jaffe-McGlamery)
READING_THE_FIGURES.md         how to read the figures and what each control moves
report.py                      regenerates every table in this README
test_photometry.py             63 checks, incl. two dome-port calibration images
test_backscatter.py            17 checks on the phase function and the tilt trade
build_web_data.py              splices data/*.csv into index.html (never hand-edit those arrays)
data/
  extract_from_manual.py       recovers the curves from the manual's vector charts
  lsl_beam_profiles.csv        flood + spot relative intensity, 0-90 deg
  lsl_seasense_dimming.csv     LOUT command -> per-cent output
```

The LED SeaLite manual is not redistributed here; it lives in the team Dropbox at
`documents/ROV_documents/lights/LEDSeaLite_Manual.pdf`. You only need it (and
`pymupdf`) to regenerate the CSVs.

### Conventions

Right-handed, metres, origin on the seafloor below the vehicle's centre: **+x**
starboard, **+y** forward, **+z** up. `altitude` is the height of the **lamp
emitters** above the seafloor — the vehicle's altimeter reads from wherever it is
mounted, so offset a measured altitude onto the lamp plane before using it here.

### Sources

Beam and dimming data: *LED SeaLite Operator's Manual* rev. 08/27/18, Appendices
C and D. Vehicle frame: [Blue Robotics BlueROV2](https://bluerobotics.com/store/rov/bluerov2/)
(457 × 338 × 254 mm). Lamp specifications:
[Kraken Solar Flare Mini 18000](https://krakensports.ca/product/solar-flare-mini-18000/),
[Blue Robotics Lumen](https://bluerobotics.com/store/thrusters/lights/lumen-r2-rp/).
Cameras: [Sony ILX-LR1](https://pro.sony/ue_US/products/installable-cameras/ilx-lr1),
[FE 16 mm F1.8 G](https://www.sony-asia.com/electronics/camera-lenses/sel16f18g/specifications),
[GoPro HERO12 Black](https://gopro.com/en/us/shop/cameras/hero12-black/CHDHX-121-master.html).
Styling: *Seattle Aquarium Visual Identity Guidelines*, v1, August 2023.
