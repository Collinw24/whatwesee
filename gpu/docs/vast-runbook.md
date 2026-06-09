# Vast GPU Runbook

Use this runbook before spending GPU money. The goal is repeatability: launch,
bootstrap, verify, run, sync back, and tear down without improvising on a paid
host.

## Offer Selection

Prefer verified, reliable hosts with enough VRAM and disk for the specific job.
For photogrammetry model benches, start at 48GB VRAM and use 80GB when running
larger neural reconstruction or high-resolution splat work.

```sh
vastai search offers "verified=true rentable=true reliability > 0.98 gpu_ram >= 48"
```

Check:

- GPU model and VRAM.
- Disk price plus GPU price, not just GPU price.
- Public SSH availability.
- Internet bandwidth.
- CUDA image compatibility with the model stack.

## Launch Rules

- Do not launch until the dataset is staged on Hetzner and a job package exists.
- Do not launch without an explicit offer id and a cost confirmation.
- Treat the GPU filesystem as temporary. Anything not synced back can disappear.
- Keep SSH keys scoped to the run and remove temporary Hetzner keys after teardown.

## First Commands On The GPU

After SSH works and Hetzner credentials are available:

```sh
export PGM_HETZNER_HOST=user@staging-host.example.com
export PGM_HETZNER_ROOT=/srv/staging/photogrammetry
export PGM_JOB_ID=DATASET-core-bench-001
export PGM_WORK_ROOT=/workspace/whatwesee

mkdir -p "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID"
rsync -aP --whole-file --inplace --partial \
  "$PGM_HETZNER_HOST:$PGM_HETZNER_ROOT/jobs/$PGM_JOB_ID/" \
  "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/"

bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/bootstrap-vast.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

For this repo's Hetzner staging flow, the safest credential path is a temporary
GPU-side key. Create it after the Vast instance is reachable and before running
the bootstrap:

```sh
gpu/scripts/prepare-vast-hetzner-access.sh \
  root@GPU_PUBLIC_HOST_OR_SSH_ALIAS \
  user@staging-host.example.com \
  "$PGM_JOB_ID"
```

After the job has synced back, revoke it:

```sh
gpu/scripts/revoke-vast-hetzner-access.sh \
  user@staging-host.example.com \
  "$PGM_JOB_ID" \
  root@GPU_PUBLIC_HOST_OR_SSH_ALIAS
```

`bootstrap-vast.sh` delegates shared machine setup to `scripts/gpu/` when the
job package includes it. That path builds CUDA COLMAP when the package requires
new sparse or dense COLMAP work; splat-only packages with a staged promoted
COLMAP sparse model can skip that build.

`run-job.sh` handles pull, readiness verification, compute, and sync-back. For
manual diagnostics, run `pull-inputs.sh` and `verify-ready.sh` first, then run
`PGM_SKIP_PULL=1 PGM_SKIP_VERIFY=1 bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"`.

## Preflight Gates

The preflight report must pass before compute:

- `nvidia-smi` sees the GPU.
- VRAM is above the job minimum.
- Free disk is above the job minimum.
- Transfer tools are installed.
- Hetzner SSH can read the staged dataset.
- CUDA COLMAP reports `with CUDA` when photogrammetry requires it.
- Nerfstudio commands exist for splat jobs.

Reports are written to:

```text
/workspace/whatwesee/runtime/preflight/
```

## Cost Controls

- Use Hetzner for durable storage and sync-back; never rely on Vast retention.
- Use `rsync --whole-file --inplace --partial` for JPEG-heavy datasets.
- Use GNU `parallel` for per-image pulls when the dataset has many files.
- Use `aria2c` for direct model/checkpoint downloads.
- Keep build logs; if a build fails, decide quickly whether debugging is cheaper
  than destroying the instance and relaunching from a corrected job package.
- Stop or destroy the instance only after sync-back verification passes.

## Teardown Checklist

Before destroying the instance:

- `reports/run_report.json` exists locally on the GPU.
- Dataset outputs have synced to Hetzner.
- Job logs have synced to Hetzner.
- Hetzner has the COLMAP sparse output, splat outputs if requested, and logs.
- Temporary SSH keys used by the GPU have been removed from Hetzner.
