# What We See Evidence Packages

This directory defines the structured evidence layer above `photogrammetry/`.
It does not store large capture data in the repo. By default, evidence packages
live in:

```sh
~/whatwesee_evidence_data/
```

The first package target is `basement-garden-s0`: the April 28, 2026 basement
and indoor garden baseline state. It links to the existing photogrammetry
dataset and leaves room for iPhone LiDAR reference geometry, model benchmarks,
semantic annotations, registration reports, and later change detection.

## Package Layout

```text
PACKAGE_NAME/
  raw/
    photos/
    lidar/
      iphone/
  working/
    image_lists/
    lidar/
    masks/
    previews/
  manifests/
  registration/
  benchmarks/
    vggt/
    colmap/
    glomap/
    splatfacto/
  semantics/
  state/
  logs/
```

## Local Workflow

Run commands from the project root:

```sh
python3 evidence/scripts/evidence.py init-package --name basement-garden-s0 --target basement-garden --state-id S0
python3 evidence/scripts/evidence.py link-photogrammetry --package basement-garden-s0 --dataset basement-fresh-iphone-001
python3 evidence/scripts/evidence.py write-session --package basement-garden-s0 --date 2026-04-28 --location basement --notes /path/to/session-notes.md
python3 evidence/scripts/evidence.py ingest-lidar --package basement-garden-s0 --source /path/to/lidar-export.ply --device iphone-lidar
python3 evidence/scripts/evidence.py bench-plan --package basement-garden-s0
python3 evidence/scripts/evidence.py register-report --package basement-garden-s0
```

`ingest-lidar` treats iPhone LiDAR as reference/control geometry. It is useful
for scale, coarse layout, and QA, but not authoritative truth unless later
validated.

## Artifact Classes

Every package artifact should be classed as one of:

- `evidence`: raw capture data, checksums, sensor exports, source manifests.
- `inference`: reconstructions, camera poses, depth maps, masks, registrations.
- `visualization`: splats, rendered previews, screenshots, forecast images.

The practical rule from the research notes applies here: if the system cannot
explain how a model was made, it should not use that model as hard evidence.

## First Model Bench

The first benchmark is intentionally narrow:

- VGGT: neural cameras, depth, point maps, tracks, confidence.
- COLMAP: conservative SfM/MVS baseline.
- GLOMAP: fast global SfM baseline using COLMAP-style inputs/outputs.
- Splatfacto: Gaussian splat initialized from the best classical geometry path.

MASt3R, Fast3R, CUT3R, depth priors, and Grounded SAM 2 are next-stage
extensions once the evidence package contract is stable.
