# Core Model Bench

## Purpose

The first bench answers a narrow question: which geometry path gives us the
most coherent baseline for the basement/garden capture package?

## Models

| Model | Role | First outputs |
| --- | --- | --- |
| VGGT | Neural geometry pass | cameras, depth maps, point maps, tracks, confidence |
| COLMAP | Conservative SfM/MVS baseline | database, sparse model, dense point cloud |
| GLOMAP | Fast global SfM baseline | sparse model from COLMAP database |
| Splatfacto | Visual/radiance representation | trained Gaussian splat, viewer/export artifacts |

## Current Basement/Garden S0 Baseline

The first accepted geometry baseline is the local Apple Silicon COLMAP
`global_mapper` run:

```text
photogrammetry dataset: basement-fresh-iphone-001
run: local-colmap-iphone-scaffold-global-hires-001
registered: 305/308 images
source registration: iPhone 305/308
sparse points: 73367
```

This has been promoted with `pgm.py promote-colmap` and staged to Hetzner as
the current camera-pose foundation for `basement-garden-s0`. Model bench outputs
remain separate: the promoted COLMAP sparse model is the pose foundation, not a
blind merge with VGGT, LiDAR, or Splatfacto.

This choice follows the research framing: the promoted sparse model is an
`inference` artifact inside the `S0` state package. It is useful because it
creates camera poses, a sparse point cloud, and a COLMAP-compatible handoff. It
is not treated as complete measured truth, and it does not replace later LiDAR,
VGGT depth/point maps, semantic labels, or repeat-capture change reports.

The first staged GPU package is splat-only:

```text
job: basement-fresh-iphone-001-splat-s0-001
target: splat
precomputed COLMAP: true
build CUDA COLMAP: false
splat iterations: 30000
```

This first GPU job is deliberately a visualization/inspection pass, not the
whole future-state stack. It should answer: given the current accepted camera
graph, can Splatfacto produce a coherent navigable view of the basement/garden
state without rerunning paid sparse COLMAP? If it succeeds, the result becomes a
`visualization` artifact linked back to the promoted COLMAP inference. If it
fails, the failure is evidence about coverage, pose quality, or model settings,
not a reason to merge in unrelated outputs blindly.

## Alignment With Future-State Goals

The current order is:

```text
fresh capture -> local QC -> local COLMAP/GLOMAP-style baseline
  -> promoted S0 camera/point foundation
  -> Splatfacto inspection view
  -> LiDAR/VGGT registration and scoring
  -> semantics and repeat-capture change detection
  -> future-state forecast package
```

That sequence keeps future rendering downstream of measured state. The splat is
useful now because it makes `S0` inspectable from novel viewpoints, but the
forecasting path still depends on later `S1`/`S2` captures, registration
residuals, semantic regions, and uncertainty.

## First Metrics

- registered image count and percentage;
- camera pose coherence;
- sparse and dense point counts;
- rough alignment to iPhone LiDAR reference;
- runtime and GPU type when available;
- failure stage and reason.

## Deferred Models

MASt3R, Fast3R, CUT3R, Depth Pro, Metric3D, Depth Anything V2, and Grounded SAM 2
are important, but they come after the package contract and first benchmark
report are stable.
