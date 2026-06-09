# Cloud Runbook

This runbook describes the intended Hetzner and Vast.ai flow. The local CLI generates exact commands for each dataset with `cloud-plan`.

## Roles

- Local M3 Max: ingest, EXIF extraction, checksums, preview generation, and QC.
- Hetzner: durable staging area and long-lived artifact store.
- Vast.ai: short-lived GPU compute for COLMAP, OpenMVS, and Nerfstudio Splatfacto.

## Hetzner Setup

V1 assumes an existing Hetzner host reachable through SSH. Create an SSH alias such as:

```sshconfig
Host hetzner-photogrammetry
  HostName example.your-hetzner-host.net
  User root
  IdentityFile ~/.ssh/your_key
```

The Hetzner storage root should be on an attached volume or large disk, for example:

```text
/mnt/HC_Volume_000/whatwesee-photogrammetry
```

Expected remote layout:

```text
REMOTE_ROOT/
  datasets/
    DATASET_NAME/
  pipeline/
    remote/
```

## Local Stage

Run:

```sh
python3 photogrammetry/scripts/pgm.py sync-hetzner --dataset DATASET_NAME
```

This syncs the dataset and the remote shell scripts to Hetzner. It does not delete remote files, because Hetzner is the durable store for cloud outputs.

For temporary GPU staging where the local machine remains the RAW archive, sync only active working images and metadata:

```sh
python3 photogrammetry/scripts/pgm.py sync-hetzner --dataset DATASET_NAME --working-only
```

Use a dry run to print commands only:

```sh
python3 photogrammetry/scripts/pgm.py sync-hetzner --dataset DATASET_NAME --dry-run
```

## Merge Candidate Stage

For mixed-camera experiments, keep the Canon and iPhone source datasets staged once, then create local merge candidates and stage them by remote hardlink:

```sh
python3 photogrammetry/scripts/pgm.py merge-candidate --name ROOM_MERGED --source ROOM_CANON --source ROOM_IPHONE --profile clean
python3 photogrammetry/scripts/pgm.py qc --dataset ROOM_MERGED
python3 photogrammetry/scripts/pgm.py cloud-plan --dataset ROOM_MERGED --target both
python3 photogrammetry/scripts/pgm.py stage-merge-hetzner --dataset ROOM_MERGED
```

`stage-merge-hetzner` transfers manifests, reports, logs, and cloud metadata only. On Hetzner it rebuilds `working/images/` from hardlinks to the already-staged source datasets, so candidate rebuilds do not spend upload bandwidth or duplicate disk blocks.

## Vast Launch

Search for a cost-effective GPU offer. For the current model bench, prefer at
least 48GB VRAM; 80GB is appropriate when the dataset is large or when neural
benchmarks are expected to run after COLMAP.

```sh
vastai search offers "verified=true rentable=true reliability > 0.98 gpu_ram >= 48"
```

If a local Apple Silicon sparse baseline has been accepted, promote and stage
it before building the GPU package:

```sh
python3 photogrammetry/scripts/pgm.py promote-colmap \
  --dataset DATASET_NAME \
  --bench-run LOCAL_BASELINE_RUN \
  --overwrite

python3 photogrammetry/scripts/pgm.py sync-hetzner \
  --dataset DATASET_NAME \
  --working-only
```

The staged dataset then includes `colmap/sparse/0`, `colmap/database.db`, and
`reports/promoted_colmap.json`. Splat-only jobs can reuse that sparse model and
skip the CUDA COLMAP build. Mesh or `both` jobs still require CUDA COLMAP for
dense PatchMatch work, but `run-colmap.sh` can skip feature extraction and
sparse mapping when `PGM_COLMAP_SKIP_SPARSE_IF_PRESENT=1`.

Before renting anything, build and stage a job package. For the current
`basement-garden-s0` handoff, use `--target splat` because a promoted local
COLMAP sparse baseline already exists and the immediate GPU goal is an
inspection splat, not dense mesh reconstruction:

```sh
python3 photogrammetry/scripts/pgm.py job-package \
  --dataset basement-fresh-iphone-001 \
  --target splat \
  --name basement-fresh-iphone-001-splat-s0-001 \
  --evidence-package basement-garden-s0 \
  --evidence-remote-root /srv/staging/evidence \
  --sync-hetzner
```

For a broader future run that intentionally does dense mesh and splat work,
use `--target both`:

```sh
python3 photogrammetry/scripts/pgm.py job-package \
  --dataset DATASET_NAME \
  --target both \
  --name DATASET_NAME-core-bench-001 \
  --evidence-package basement-garden-s0 \
  --evidence-remote-root /srv/staging/evidence \
  --sync-hetzner
```

This creates `REMOTE_ROOT/jobs/JOB_ID/` on Hetzner. The package carries the
manifests, image index, checksums, dependency list, bootstrap script, pull
script, readiness check, run script, sync-back script, and artifact contract.
It intentionally does not copy the photos into the package.

The package also carries the repo-level `gpu/scripts/` runtime. Those scripts
run preflight checks, build CUDA COLMAP from source when required, and write
machine-readable reports before expensive reconstruction starts.

Launch only after reviewing the cloud plan:

```sh
python3 photogrammetry/scripts/pgm.py vast-run --dataset DATASET_NAME --target both --offer-id OFFER_ID --confirm-cost
```

The launch step creates a CUDA/PyTorch instance and installs basic transfer tooling. The reconstruction job itself is run from the remote scripts after SSH access is ready, because the GPU machine needs SSH credentials or another approved path to pull from Hetzner.

## Run on Vast

On the Vast instance, make the Hetzner host reachable via SSH, then run the
staged job package. This is the preferred path when we can SSH into the GPU box:

```sh
export PGM_HETZNER_HOST=hetzner-photogrammetry
export PGM_HETZNER_ROOT=/mnt/HC_Volume_000/whatwesee-photogrammetry
export PGM_JOB_ID=DATASET_NAME-core-bench-001
export PGM_WORK_ROOT=/workspace/whatwesee

mkdir -p "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID"
rsync -aP --whole-file --inplace --partial \
  "$PGM_HETZNER_HOST:$PGM_HETZNER_ROOT/jobs/$PGM_JOB_ID/" \
  "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/"

bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/bootstrap-vast.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

The cloud job pulls the dataset from Hetzner, verifies readiness, runs the
selected target, writes logs and reports, and pushes everything back to Hetzner.
For manual diagnostics, run `pull-inputs.sh` and `verify-ready.sh` first, then
run `PGM_SKIP_PULL=1 PGM_SKIP_VERIFY=1 bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"`.

The bootstrap installs `aria2`, `uv`, `rsync`, `zstd`, `pigz`, `parallel`,
`fpart`, and `mbuffer`. When `scripts/gpu/` is present it also builds CUDA
COLMAP under `/workspace/colmap-cuda` and fails readiness if COLMAP does not
report CUDA support. Python packages install through `uv` when available, with
concurrent downloads/builds. Dataset pulls use rsync without compression because
the working set is already JPEG-heavy.

## Targets

- `mesh`: COLMAP dense plus OpenMVS when available. If a promoted sparse model
  is present, the dense stage starts from that sparse model.
- `splat`: Nerfstudio Splatfacto. If a promoted sparse model is present,
  Splatfacto uses it and the job does not need to build CUDA COLMAP.
- `both`: dense mesh path plus Splatfacto. CUDA COLMAP is still required for
  dense work, but the sparse stage can be reused.

## Sync Results Locally

After the Vast job has synced back to Hetzner:

```sh
python3 photogrammetry/scripts/pgm.py sync-results --dataset DATASET_NAME
```

This mirrors Hetzner outputs back to the local data root without deleting local files.

## Cost Controls

- Always run `qc` and `cloud-plan` before GPU work.
- Promote and stage a local sparse baseline before GPU work when one has
  registered well enough.
- Keep GPU instances stopped or destroyed when not actively running.
- Require CUDA COLMAP only for jobs that run new sparse or dense COLMAP work;
  a splat-only job with `PGM_USE_PRECOMPUTED_COLMAP=1` can skip it.
- Use smaller image sets for first tests before sending hundreds of photos.
- Increase image count, resolution, and iteration budgets only after COLMAP registration is healthy.
- Hetzner keeps all intermediates; Vast should be treated as disposable compute.

## Failure Recovery

- If local upload fails, rerun `sync-hetzner`; rsync resumes partial transfers.
- If merge candidate staging fails, check that all source datasets named in `source_dataset` are already staged under `REMOTE_ROOT/datasets/`.
- If Vast setup fails, destroy the instance unless debugging it is cheaper than relaunching.
- If COLMAP registers too few images, return to capture/QC before spending more GPU time.
- If Splatfacto trains but looks poor, inspect COLMAP sparse output and image coverage first.
