# GPU Predeploy Checklist

Run this checklist before launching a paid GPU instance.

## Local Package Gate

- Dataset QC passed.
- Dataset is staged on durable storage.
- Job package exists and was staged to durable storage.
- Job package checksum verification passed on durable storage.
- Job package does not contain raw photos or large generated artifacts.
- `downloads/pip-packages.txt` uses compatible pinned versions.
- `downloads/aria2.urls` contains direct URLs for large optional downloads.

## Offer Gate

- Offer id, GPU type, VRAM, disk size, and hourly total price were recorded.
- Disk is large enough for input plus expected expansion.
- Public SSH is available.
- Image includes the required CUDA/devel toolchain when source builds are needed.
- The chosen offer is worth its speed/cost tradeoff versus cheaper GPUs.

## SSH And Transfer Gate

- Local machine can SSH to the GPU.
- GPU can SSH to Hetzner or the selected staging node.
- Temporary GPU SSH credentials are scoped to the run. Prefer
  `gpu/scripts/prepare-vast-hetzner-access.sh GPU_SSH_HOST HETZNER_SSH_HOST JOB_ID`
  before bootstrap, then `gpu/scripts/revoke-vast-hetzner-access.sh HETZNER_SSH_HOST JOB_ID GPU_SSH_HOST`
  after sync-back.
- `rsync`, `parallel`, `aria2c`, `zstd`, `pigz`, `pv`, `fpart`, and `mbuffer`
  are installed or will be installed by bootstrap.
- Dataset pull uses non-compressed rsync for JPEG-heavy inputs.

## Runtime Gate

- `nvidia-smi` sees the expected GPU.
- VRAM meets the job minimum.
- Free disk meets the job minimum.
- CUDA build tools exist when source builds are required.
- Required model/tool binaries are present after bootstrap.
- Preflight report status is `pass`.

## Photogrammetry Gate

- If the job runs new sparse or dense COLMAP work, CUDA COLMAP is required and
  the binary reports `with CUDA`.
- If the job is splat-only and uses `PGM_USE_PRECOMPUTED_COLMAP=1`,
  `colmap/sparse/0` is staged and complete before launch.
- `PGM_COLMAP_BIN` points to the CUDA binary when CUDA COLMAP is required.
- Matching strategy, image size, and feature count are explicit in `job.env`.
- The first run writes camera poses, point clouds, depth/point-map outputs where
  requested, COLMAP-compatible sparse outputs, and splat artifacts where requested.

## Teardown Gate

- Dataset outputs synced back to durable storage.
- Job logs synced back to durable storage.
- Runtime preflight/build reports synced back to durable storage.
- Output checks were inspected enough to decide whether follow-on compute is worth it.
- Temporary SSH keys were removed from staging hosts.
- Vast instance was stopped or destroyed.
