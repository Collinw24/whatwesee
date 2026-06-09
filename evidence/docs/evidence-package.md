# Evidence Package Contract

## Purpose

An evidence package is a state-oriented capture bundle. It links raw evidence,
derived model outputs, semantic annotations, registration results, and validation
artifacts without pretending they are the same kind of truth.

## Core Claims

- Raw photos and LiDAR exports are evidence.
- VGGT, COLMAP, GLOMAP, masks, and splats are derived inference or visualization.
- Model outputs are not merged until they have a registration report.
- LiDAR is a reference/control modality in v1, not the authoritative geometry.

## Required Manifests

- `manifests/package.json`: package identity, target, state id, modalities,
  policy, and current status.
- `manifests/artifacts.json`: evidence/inference/visualization ledger.
- `manifests/session.json`: capture date, location, notes, and capture
  conditions when known.
- `manifests/photogrammetry_*.json`: linked photo dataset provenance.
- `manifests/lidar_*.json`: LiDAR source metadata and role.

## Registration Policy

The package may contain many geometric outputs at once:

- iPhone LiDAR reference mesh/point cloud;
- VGGT point maps and camera estimates;
- COLMAP sparse/dense reconstructions;
- GLOMAP sparse reconstructions;
- Splatfacto visual model.

They remain separate until `registration/register_report.json` records what was
aligned, what metric was used, and what residual or visual QA is available.

## State Summary

`state/S0_state.json` summarizes the current state package:

- modalities present;
- source photogrammetry datasets;
- LiDAR role and availability;
- benchmark readiness;
- known missing evidence.

Future states should use `S1`, `S2`, and so on, then register back to the
previous state for change detection and validation.
