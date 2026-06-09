# Basement/Garden S0 Alignment

## Purpose
Check the current basement/garden execution plan against the project theory
before spending more GPU time.

## Core Decision
Proceed with the staged Splatfacto run only as a bounded `S0` visualization and
inspection pass initialized from the promoted local COLMAP sparse model. Do not
treat the splat as the digital twin, and do not treat it as metric truth.

## Why This Matches The Theory
The research system says future-state imaging must start from a state estimate:

```text
raw evidence -> calibrated/registered inference -> inspectable representation
  -> semantic state -> repeat capture -> change model -> rendered forecast
```

The current basement/garden package has a credible first state scaffold:

- `basement-fresh-iphone-001` provides 308 normalized iPhone working images.
- Local COLMAP `global_mapper` registered `305/308` images.
- The promoted sparse model provides camera poses, sparse points, and a
  COLMAP-compatible handoff.
- Hetzner holds the staged working set, evidence package, and GPU job package.

That is enough to render and inspect `S0`. It is not enough to forecast the
future. Forecasting still requires repeat capture, registered change, semantic
regions of interest, uncertainty, and validation.

## Artifact Status

| Artifact | Current role | Class |
| --- | --- | --- |
| iPhone photos | source capture evidence | `evidence` |
| EXIF/checksums/QC reports | provenance and quality record | `evidence` |
| promoted COLMAP sparse model | camera/point state scaffold | `inference` |
| Splatfacto output | navigable inspection representation | `visualization` |
| iPhone LiDAR export | future scale/layout reference | `evidence` |
| VGGT cameras/depth/point maps | future neural comparison layer | `inference` |
| semantic masks/labels | future state interpretation layer | `inference` |
| future rendered forecast | later scenario visualization | `visualization` |

## What The Next GPU Run Should Prove
The next paid GPU run should answer a narrow question:

```text
Can the promoted S0 camera graph produce a coherent Gaussian splat that is
worth using as an inspection/viewer layer for the evidence package?
```

Expected output:

- Splatfacto training logs and config.
- Gaussian splat/checkpoint/export artifacts if available.
- Inspection renders or viewer artifacts.
- Runtime, GPU type, disk use, and failure reason if incomplete.

It should not rerun sparse COLMAP unless explicitly requested. The M3 Max has
already done the cost-control camera-pose gate.

## What Still Comes After

1. Ingest iPhone LiDAR as reference/control geometry.
2. Register or visually compare LiDAR, COLMAP, and Splatfacto-derived views.
3. Run VGGT as a separate neural geometry bench for cameras, depth maps, point
   maps, tracks, and confidence.
4. Decide whether dense COLMAP/OpenMVS mesh work is worth the GPU cost.
5. Add semantic regions: plants, pots, shelves, lights, walls, floor, problem
   regions, and stable control surfaces.
6. Capture `S1`, register it to `S0`, and measure change before making any
   future-state forecast.

## Stop Conditions
Pause GPU work and return to capture or preprocessing if:

- the Splatfacto result shows major camera-pose tearing;
- inspection renders expose large unmodeled coverage gaps;
- LiDAR cannot be roughly aligned to the photo scaffold;
- the artifact ledger cannot explain whether an output is evidence,
  inference, or visualization.

## Practical Rule
The basement splat can be beautiful, but its job is to make `S0` inspectable.
The future-state project begins when `S0` can be compared to a later measured
state and the differences can be scored.
