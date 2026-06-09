# Experiment Roadmap

## Purpose
Define a practical path from the current photogrammetry pipeline to the first validated future-state rendering experiment.

## Core Claim
The first meaningful experiment should be small, repeatable, and honest. It should produce a baseline state estimate, a repeated capture, a change measurement, a simple forecast, and a validation result.

## Agent Takeaways
- Start with a bounded object or surface, not a huge site.
- Prefer repeatability over sensor maximalism.
- Forecast one measurable change first.
- Validate the forecast with the next scan.

## Paper Grounding
- Section 2.4, report pp. 8-9: level of detail should be set by intended use.
- Section 2.8, report pp. 19-20: registration and repeated observations affect accuracy.
- Section 3.12.1, report p. 71: uncertainty and repeated observations must be considered.
- Section 5.6-5.9, report pp. 86-87: digital twins and AI/ML support monitoring, maintenance, and prediction.

## Phase 1: Baseline State
Choose a small enough target to measure honestly:

- weathered object;
- garden structure;
- wall patch;
- concrete/wood/stone surface;
- artifact with visible surface detail.

Capture:

- RAW+JPEG photo set following [../../photogrammetry/docs/capture-guide.md](../../photogrammetry/docs/capture-guide.md);
- scale bars or known-size references;
- optional iPhone/iPad LiDAR pass;
- environmental notes;
- object/session slate photo.

Process through the existing photogrammetry pipeline:

- ingest;
- RAW conversion or normalization;
- QC;
- cloud plan;
- COLMAP/OpenMVS and/or Splatfacto.

## Phase 0: Public Dataset Dry Run
Before field capture, run a dry validation loop on public data where possible:

- OpenHeritage3D for archive/package and reuse expectations;
- CULTURE3D for reconstruction and Gaussian-splat benchmarking;
- Kijkduin 4D TLS for repeated point-cloud change analysis;
- USGS M3C2-PM repeat survey data for precision-map and significant-change practice;
- hyperspectral/moisture/crack datasets for material-state classification limits.

The goal is not to solve those datasets. The goal is to test the project habit: state variables, provenance, uncertainty, forecast package, and validation metrics.

## Phase 2: Semantic State
Add:

- region-of-interest masks;
- material/condition labels;
- geometry and texture artifacts;
- metadata/paradata file;
- known uncertainty notes.

The output should be a baseline state package, not just a model.

## Phase 3: Repeat Capture And Change Detection
Repeat the capture after a meaningful interval or controlled intervention. Register `S_1` to `S_0`. Measure:

- geometry difference;
- texture difference;
- mask/region changes;
- uncertainty or registration residuals.

Use CloudCompare/M3C2 or Open3D for first-pass change measurement.

Record LoD95 or an equivalent threshold if using M3C2-style tools. Apparent changes below the detection threshold should be visualized as uncertain, not forecast as physical movement.

## Phase 4: First Rendered Forecast
Make a narrow forecast:

- crack extension;
- moisture/darkening persistence;
- surface weathering;
- deformation direction;
- plant/organic growth;
- thermal anomaly region.

Render:

- one conservative forecast;
- one uncertainty map;
- one alternate plausible trajectory.

## Phase 5: Validation
Capture `S_2`. Compare the forecast from `S_1` to actual `S_2`.

Score:

- did the forecasted region change?
- was the direction correct?
- was the magnitude within the uncertainty band?
- did the visualization overstate confidence?

## Evidence / Inference / Visualization
Each experiment should produce:

- evidence archive;
- derived state estimate;
- semantic annotations;
- change report;
- forecast package;
- validation report.

## Future-State Imaging Implication
This roadmap creates the smallest complete loop:

```text
measure -> estimate -> compare -> predict -> render -> validate
```

That loop is the foundation for generating images of the future responsibly.
