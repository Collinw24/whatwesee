# GPU Runtime

This directory is the shared GPU rental layer for What We See jobs. It is not
photogrammetry-specific; photogrammetry job packages copy these scripts into
their handoff bundles so every rented instance starts from the same preflight,
bootstrap, build, and reporting flow.

## Contract

GPU instances are disposable compute. Durable inputs and outputs live elsewhere:

- Hetzner or another staging node stores datasets, job packages, logs, and final artifacts.
- The GPU host pulls inputs, runs the job, syncs everything back, then can be stopped or destroyed.
- Every paid job should leave machine-readable preflight and build reports under
  `/workspace/whatwesee/runtime/preflight/`.

## Standard Boot Order

On a fresh GPU host:

```sh
export WWS_GPU_WORK_ROOT=/workspace/whatwesee
export WWS_HETZNER_HOST=user@staging-host.example.com
export WWS_HETZNER_TEST_PATH=/srv/staging/photogrammetry/datasets/DATASET/manifests/manifest.json

# Use WWS_BUILD_COLMAP_CUDA=0 for splat-only jobs that reuse a promoted
# COLMAP sparse model from staging.
WWS_BUILD_COLMAP_CUDA=1 WWS_REQUIRE_COLMAP_CUDA=1 bash gpu/scripts/bootstrap-gpu.sh
bash gpu/scripts/preflight-gpu.sh
```

Photogrammetry job packages wrap this as:

```sh
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/bootstrap-vast.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/pull-inputs.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/verify-ready.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

## Scripts

- `scripts/preflight-gpu.sh`: validates NVIDIA GPU visibility, VRAM, disk,
  transfer tools, Hetzner SSH reachability, and CUDA COLMAP when required.
- `scripts/bootstrap-gpu.sh`: installs common transfer/runtime tools, installs
  `uv`, optionally builds CUDA COLMAP, then runs preflight.
- `scripts/build-colmap-cuda.sh`: builds COLMAP from source with CUDA enabled,
  GUI/OpenGL disabled, system OpenBLAS/OpenImageIO libraries, and a pinned
  install prefix.

## Runbooks

- `docs/predeploy-checklist.md`: mandatory launch, runtime, and teardown gates.
- `docs/vast-runbook.md`: Vast-specific offer, launch, preflight, and cleanup flow.

## Defaults

The defaults target CUDA/PyTorch Vast images with an NVIDIA devel toolchain:

- Work root: `/workspace/whatwesee`
- Source root: `/workspace/src`
- CUDA COLMAP prefix: `/workspace/colmap-cuda`
- Minimum VRAM: `48GB`
- Minimum free disk: `80GB`
- CUDA COLMAP: required only when a job runs new sparse or dense COLMAP work.
  Splat-only photogrammetry jobs can skip it when `PGM_USE_PRECOMPUTED_COLMAP=1`.

Copy `configs/runtime.example.toml` for operator-level notes. Secrets and live
SSH credentials stay outside the repo.
