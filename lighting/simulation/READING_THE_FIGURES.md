# Reading the figures

A guide to what the tool is showing you and, more usefully, *why* each control
moves what it moves. No maths beyond one formula, and that formula is worth the
five minutes because every figure in the tool is just that formula drawn from a
different angle.

---

## 1. Lumens, lux, and why the difference matters

**Lumens (lm)** measure *how much light there is in total*. It is a property of
the lamp, and it does not change with distance. A SeaLite flood emits about
7,030 lumens whether it is pointed at the seafloor or at the sky.

**Lux (lx)** measure *how much light lands on a square metre of something*. It is
a property of a **place**, not of a lamp, and it falls off fast with distance.

> Lumens are how much paint is in the can. Lux is how thick the coat ends up.
> Spread the same can over twice the wall and the coat is half as thick.

That is the whole reason the tool reports both. "Flux into frame" (lumens) is
your light *budget*: how much of what you emitted landed in the picture. "Mean
illuminance" (lux) is what the **camera** responds to, because exposure depends
on brightness per unit area, not on total light in the scene.

A third quantity appears once in the readout: **candela (cd)**, or lumens per
steradian — light per unit of *solid angle*, i.e. how concentrated the beam is in
a given direction. A spot optic and a flood optic can emit similar lumens while
differing 3× in candela, and that difference is the entire story of §5.

---

## 2. The one formula

For a single lamp, the illuminance landing on a patch of seafloor is

```
E  =  I(θ)  ×  cos(ι)  ×  1/r²  ×  exp(−c·r)
```

Four factors. Each one is a lever you have in the tool:

| term | what it means | what changes it |
|---|---|---|
| **I(θ)** | How much light the lamp throws in *this particular direction*. θ is the angle off the lamp's axis. | Beam angle, lamp choice, **tilt** (which changes θ to every point), power |
| **cos(ι)** | Obliquity. Light arriving at a slant smears the same beam over more floor, so it lands thinner. | Altitude, tilt, and *where in the frame you are* |
| **1/r²** | Inverse square. The light spreads over a sphere that grows as you move away. | Altitude — this is the strong one |
| **exp(−c·r)** | Water eats light on the way down. | Turbidity `c`, and altitude again |

Four lamps, so you add four of these together. **That sum is every figure in the
tool.** The transect is a slice through it; the plan view is a map of it; the
readout is statistics of it over the camera frame.

Two consequences worth internalising now, because they explain most of what you
will see:

- **Power is a pure multiplier.** Turning `LOUT` up scales `I(θ)` by the same
  factor everywhere, so the *shape* of every curve and contour is untouched —
  only the height. Power moves exposure and nothing else.
- **Everything else changes the shape.** Altitude, tilt, beam angle and lamp
  spacing all redistribute where the light goes. They change uniformity, and
  they change exposure only as a side effect.

That split — power controls level, geometry controls shape — is the single most
useful thing to hold on to.

---

## 3. The Illuminance Transect

**What it is:** imagine cutting a straight line across the seafloor, right under
the vehicle, and walking along it with a light meter. Horizontal axis is where
you are standing (metres from directly under the camera). Vertical axis is what
the meter reads (lux). "Across-track" cuts port-to-starboard; the selector
switches to an along-track cut.

**What the lines are:**

| line | meaning |
|---|---|
| thick dark | all four lamps together — the actual illuminance |
| blue | just the two port lamps |
| coral | just the two starboard lamps |
| coral dashed horizontal | the lux level that would give a correct exposure |
| grey band | the part of the seafloor the camera actually sees |

The two coloured lines add up to the dark one. Showing them separately is what
makes the shape legible.

### Why it has two humps

Each lamp lays down a rough pool of light centred a little outboard of the lamp
itself. Your lamps sit 0.26 m either side of the centreline and are tilted
*outboard*, so the port pool is centred left of the camera and the starboard pool
is centred right of it. Where the two pools overlap — directly under the camera —
you get the sum of the two pools' shoulders rather than either one's peak.

**So the dip in the middle is not a bug. It is the direct visual consequence of
mounting lamps at the corners instead of at the lens.** Everything about the tilt
argument is about managing that dip.

### What moves it

| move this | what happens to the transect | why |
|---|---|---|
| **Power / `LOUT`** up | whole curve scales up; **shape identical** | `I(θ)` multiplied everywhere |
| **Altitude** up | humps move apart, whole curve flattens and drops | `1/r²` weakens everything; the grey band widens faster than the light spreads |
| **Tilt** up | humps walk outwards, centre dip deepens | each lamp aims further from the centreline |
| **Beam angle** wider | humps broaden and merge, peaks drop | same lumens spread over more solid angle |
| **Turbidity** up | curve drops, edges more than the centre | edges are at longer slant range, so `exp(−c·r)` bites harder |
| **Lamp spacing** wider | humps separate | the pools start further apart |
| **Reflectance ρ** | *only the dashed line moves* | that line is about the camera, not the lights |

**The reading skill:** the *height* of the dark curve relative to the dashed line
tells you exposure. The *flatness* of the dark curve inside the grey band tells
you uniformity. Those are two independent things, and power only moves the first.

If the curve is the right height but sagging in the middle, more power will not
help — you need geometry. If it is flat but too low, geometry will not help — you
need power.

---

## 4. The Seafloor Illuminance map

Same data, seen from above. Colour is lux. It is a **map of brightness on the
seafloor**, with the vehicle directly above the centre.

| mark | meaning |
|---|---|
| **green dots** | where the four lamps are, in plan |
| **white rectangle** | the camera frame — what ends up in the picture |
| **green contour lines** | isolux lines at ¼, ½ and ¾ of the colour-scale top |
| **coral dashed contour** | the correct-exposure isolux |

### What an isolux line is

Exactly a contour line on a topographic map, but for brightness instead of
height. **Every point on one line receives the same lux.** Lines bunched close
together mean brightness is changing fast; lines far apart mean a broad even
plateau.

That makes them the fastest read of uniformity in the whole tool: *if the white
rectangle sits in a region with no contour lines crossing it, the frame is
evenly lit.* If contours march across the box, it is not.

### The coral one is different in kind

The green contours are set by **the lights** — they are fractions of whatever the
brightest point happens to be. The coral one is set by **the camera**: it is the
one specific lux value that produces a correct exposure at your current aperture,
shutter, ISO and assumed seafloor reflectance.

So it answers a different question:

- **Inside the coral line** → brighter than the camera wants → over-exposed
- **Outside it** → darker than the camera wants → under-exposed

**The goal is for the white rectangle to sit just inside the coral line, with the
line hugging it.** If the coral line is way outside the box (as it is at full
power now), you are over-exposed and should dim. If the coral line cuts *through*
the box, part of your frame is over and part is under — and no single exposure
setting fixes that, because it is a uniformity problem wearing an exposure
costume.

### What moves the contours

This is where the two families behave differently, and it is worth playing with:

| move this | green contours | coral contour |
|---|---|---|
| **Power / `LOUT`** | expand outward | **stays put** |
| **Reflectance ρ** | stay put | expands (dark floor needs more light) |
| **Aperture / ISO / shutter** | stay put | moves (faster settings need more light) |
| **Altitude** | expand then weaken | expands, then swallows everything as light runs out |
| **Tilt** | the four blobs separate | tracks the light, so it separates too |
| **Turbidity** | shrink | shrinks |

**Try this once and it will stick:** set reflectance to 0.05 and then 0.40, and
watch only the coral line breathe in and out while the green ones sit still. Then
drag `LOUT` and watch the opposite happen. Green = the lights. Coral = the
camera.

### The colour scale

The ramp runs deep navy (no light) through blue and cyan to white (brightest).
It is **pinned to what the brightest lamp set would put down at full power** —
currently the SeaLite spot, which concentrates its light into the highest peak
even though it is the worst overall performer.

That means colours mean the same thing no matter which lamp you select. Four
Blue Robotics Lumens genuinely render as a dim blue smudge, because they *are*
dim — they reach only about 6 % of the ramp. Tick **stretch scale to this view**
if you would rather see fine structure within one dim configuration; that
re-normalises to whatever is on screen and gives up the cross-lamp comparison.

---

## 5. Why the spot optic is the cautionary tale

The spot has the **highest candela** of any lamp here (14,400 cd against the
flood's 5,680) and the **lowest useful output** on this rig — uniformity 0.06,
versus 0.57 for the flood.

Both facts come from the same cause. A spot takes its lumens and squeezes them
into a narrow cone: high intensity, small solid angle. On a rig where the lamps
sit 0.35 m off the camera axis and are tilted *outboard*, that narrow cone lands
in four tight, bright pools that miss the middle of the frame entirely.

It also sets the top of the colour ramp, which is a nice demonstration in itself:
**the brightest single point and the best picture are not the same objective.**
Candela buys you reach; lumens spread over the right area buys you a photograph.

---

## 6. Five experiments that build the intuition fastest

Run these in order. Each isolates one idea.

1. **Power only.** Drag `LOUT` from 40 to 100. Watch the transect scale
   vertically with its shape frozen, the green contours expand, and the coral
   contour not budge. *Lesson: power is a pure multiplier.*

2. **Reflectance only.** Set ρ from 0.05 to 0.40. Only the coral contour moves.
   *Lesson: the coral line is a camera property, not a light property.*

3. **Altitude.** Take it from 0.5 m to 1.5 m. The frame grows (dimension labels
   update live), the transect humps separate and collapse, contours spread then
   fade. Note that **flux into frame barely changes between 0.8 and 1.5 m** while
   mean illuminance halves — the frame is growing as fast as the light thins.
   *Lesson: lumens and lux answer different questions.*

4. **Tilt, slowly, 0 → 20°.** Watch the humps walk apart and the middle sag.
   Somewhere around 13° the frame corners fall out of the beams and uniformity
   collapses. *Lesson: there is an optimum, and a cliff just past it.*

5. **Turbidity.** Take `c` from 0.2 to 1.8 and watch "Contrast kept" fall from
   99 % to 85 % while exposure barely moves. Then raise `LOUT` and watch contrast
   **not** recover. *Lesson: you cannot brighten your way out of backscatter —
   glare scales with your lights exactly as fast as signal does.*

That last one is the least intuitive and the most important operationally.

---

## 7. The five header numbers

| number | reads | you want |
|---|---|---|
| **Flux into frame** | lumens landing in the picture | high, but it is a budget not a goal |
| **Mean illuminance** | average lux over the frame | to match what the camera wants |
| **Uniformity min:mean** | dimmest point ÷ average | as close to 1 as you can get; 0.6 is good, under 0.3 is visibly patchy |
| **Contrast kept** | how much image contrast survives backscatter | above ~95 %; below 85 % the water is doing real damage |
| **Exposure** | stops over or under | within ½ stop |

Uniformity and Contrast kept are the two that geometry controls and power cannot
fix. Exposure is the one power *can* fix. Read them in that order.

---

## 8. Where to go next

- [`README.md` §3](README.md) — the tilt optimisation, worked through with these
  same quantities.
- [`README.md` §2.5](README.md) — why `LOUT` 80 turns out to be right.
- `python report.py` — every number in the write-up, regenerated from source.
