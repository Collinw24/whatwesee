# What We See Photogrammetry Pipeline

This directory contains the first production-oriented photogrammetry pipeline for the project. It is built around three stages:

1. Local ingest and QC on the M3 Max.
2. Hetzner as durable staging and artifact storage.
3. Manually approved Vast.ai GPU jobs for COLMAP, mesh, and Gaussian splat outputs.

The project repo should not store large photo datasets. By default, dataset data lives in:

```sh
~/whatwesee_photogrammetry_data/
```

## Directory Layout

Each dataset uses this layout under the data root:

```text
DATASET_NAME/
  raw/
  working/
    images/
    previews/
  manifests/
  reports/
  colmap/
  mesh/
  splat/
  logs/
  cloud/
```

Important generated files:

- `manifests/dataset.json`: dataset identity and type.
- `manifests/manifest.json`: image list, checksums, EXIF, camera/lens/focal groups.
- `reports/qc_report.json`: duplicate, blur, exposure, EXIF, readability, and pass/fail status.
- `reports/cloud_plan.md`: exact staging and GPU launch checklist.
- `reports/run_report.json`: local/cloud run status when produced.

## First-Time Setup

Create a local config from the example and fill in the Hetzner SSH alias/root path:

```sh
cp photogrammetry/configs/pipeline.example.toml photogrammetry/configs/pipeline.local.toml
```

The config file is intentionally ignored by convention and should contain machine-specific hostnames or paths only. Secrets should stay in your shell, SSH agent, Hetzner console, or Vast.ai account, not in this repo.

## Local Workflow

Run commands from the project root:

```sh
python3 photogrammetry/scripts/pgm.py init-dataset --name chair-test --type object
python3 photogrammetry/scripts/pgm.py ingest --dataset chair-test --source /path/to/photos
python3 photogrammetry/scripts/pgm.py convert-raw --dataset chair-test
python3 photogrammetry/scripts/pgm.py normalize-working --dataset chair-test
python3 photogrammetry/scripts/pgm.py qc --dataset chair-test
python3 photogrammetry/scripts/pgm.py cloud-plan --dataset chair-test --target both
```

If the QC report passes and the cloud plan looks reasonable, stage to Hetzner:

```sh
python3 photogrammetry/scripts/pgm.py sync-hetzner --dataset chair-test
```

For VPS staging where RAW originals stay local and only active JPEG/TIFF working images should be uploaded:

```sh
python3 photogrammetry/scripts/pgm.py sync-hetzner --dataset chair-test --working-only
```

When combining staged camera sources into one reconstruction set, build merge candidates locally first. This preserves source provenance while hardlinking local working images instead of duplicating them:

```sh
python3 photogrammetry/scripts/pgm.py merge-candidate --name room-merged-clean --source room-canon --source room-iphone --profile clean
python3 photogrammetry/scripts/pgm.py qc --dataset room-merged-clean
python3 photogrammetry/scripts/pgm.py cloud-plan --dataset room-merged-clean --target both
```

Available merge profiles:

- `all`: include every source working image.
- `clean`: exclude source images with QC warnings.
- `no-ultrawide`: exclude QC-warning images and likely iPhone ultrawide frames.

If the source datasets are already on Hetzner, stage the merge candidate without re-uploading image data. This syncs metadata and creates remote hardlinks from the staged source datasets:

```sh
python3 photogrammetry/scripts/pgm.py stage-merge-hetzner --dataset room-merged-clean
```

Then create a Vast launch plan or launch a specific offer:

```sh
python3 photogrammetry/scripts/pgm.py job-package --dataset chair-test --target both --sync-hetzner
python3 photogrammetry/scripts/pgm.py vast-run --dataset chair-test --target both --offer-id OFFER_ID --confirm-cost
```

`job-package` is the preferred pre-GPU handoff. It writes a small bundle under
`cloud/jobs/JOB_ID/` and can stage it to `REMOTE_ROOT/jobs/JOB_ID` on Hetzner.
The bundle contains manifests, checksums, bootstrap scripts, pull/verify/run
scripts, the shared repo-level `gpu/scripts/` runtime, and the five-class
artifact contract. It does not duplicate photo files; the Vast box pulls the
already-staged working image set from Hetzner.

After the remote job finishes and syncs back to Hetzner, mirror results locally when needed:

```sh
python3 photogrammetry/scripts/pgm.py sync-results --dataset chair-test
```

## Tool Strategy

Local tools:

- `exiftool`: EXIF extraction and image metadata.
- `ffmpeg`: preview generation fallback and lightweight QC image metrics.
- `sips`: fast macOS preview generation where available.
- Homebrew `colmap`: local CPU sparse baselines on Apple Silicon. Current
  COLMAP includes GLOMAP functionality as `global_mapper`.
- `rsync`/`ssh`: staging to Hetzner and result sync.

Canon RAW note: capture RAW+JPEG. `.CR2`, `.CR3`, and `.DNG` files are preserved in `raw/` and linked from matching working JPEG records when names line up. The first COLMAP/Nerfstudio working set is built from JPEG/TIFF/PNG/HEIC files.

If a capture is RAW-only, run:

```sh
python3 photogrammetry/scripts/pgm.py convert-raw --dataset DATASET_NAME
```

This creates full-resolution JPEG quality 100 working images with `sips` by default. The CR2/CR3/DNG originals remain in `raw/`, so the JPEGs are disposable working derivatives. For Canon 5D Mark III CR2 files, expect roughly 8-20 MB per JPEG instead of about 125-130 MB per uncompressed 16-bit TIFF.

Use TIFF only when you have a specific reason to keep a lossless, high-bit-depth working set:

```sh
python3 photogrammetry/scripts/pgm.py convert-raw --dataset DATASET_NAME --format tiff
```

iPhone HEIC note: ingest preserves `.HEIC`/`.HEIF` originals under `raw/`, but cloud reconstruction should use JPEG working files. Normalize those captures before QC:

```sh
python3 photogrammetry/scripts/pgm.py normalize-working --dataset DATASET_NAME
```

Before spending GPU time, run local sparse baselines on the M3 Max:

```sh
python3 photogrammetry/scripts/local_colmap_bench.py \
  --dataset DATASET_NAME \
  --name local-colmap-test-001 \
  --source-dataset SOURCE_DATASET \
  --limit 64 \
  --mapper both
```

When a local baseline is good enough to become the current camera-pose
foundation, promote it into the canonical dataset `colmap/` directory:

```sh
python3 photogrammetry/scripts/pgm.py promote-colmap \
  --dataset DATASET_NAME \
  --bench-run LOCAL_BASELINE_RUN
```

`promote-colmap` copies the selected `sparse/*/0` model, `database.db`, sparse
PLY, and source reports into `DATASET/colmap/` and writes
`reports/promoted_colmap.json`. `sync-hetzner --working-only` stages this
promoted model along with working images and metadata, so Splatfacto GPU jobs
can reuse it instead of spending paid time on a fresh sparse COLMAP pass.

See `photogrammetry/docs/apple-silicon-colmap.md` for the Apple Silicon
COLMAP/GLOMAP baseline workflow and
`photogrammetry/docs/basement-s0-status.md` for the current basement/garden
handoff state.

Cloud tools:

- COLMAP for SfM and dense reconstruction.
- OpenMVS for optional mesh refinement/texturing where available.
- Nerfstudio Splatfacto for Gaussian splats.
- `gpu/scripts/` for reusable GPU rental preflight, CUDA COLMAP source builds,
  runtime reports, and cost-control gates across future non-photogrammetry jobs.
- `aria2`, `uv`, `rsync`, `zstd`, `pigz`, `parallel`, `fpart`, and `mbuffer`
  in GPU job bootstraps so paid instance time is not wasted on serial downloads
  or compressed rsync of already-compressed JPEGs.

Current basement/garden S0 rule: use
`local-colmap-iphone-scaffold-global-hires-001` from
`basement-fresh-iphone-001` as the default sparse foundation unless a new local
run scores better. It registered `305/308` iPhone images and is the promoted
camera-pose foundation for the first Splatfacto GPU pass. Older mixed
Canon/iPhone runs are retained as superseded evidence, not as the current
foundation.

Apple Object Capture is documented as a local object-capture path, but the first CLI keeps that as a manual/next-stage integration because it requires a small Swift/RealityKit command-line app.

## Cost Controls

- `cloud-plan` must run before GPU work.
- Vast.ai jobs require the explicit `vast-run` command.
- Actual Vast instance creation requires both `--offer-id` and `--confirm-cost`.
- Hetzner keeps all raw, intermediate, logs, and final artifacts by default.
- Vast instances should be stopped or destroyed after verified sync-back.

## References

- [COLMAP CLI](https://colmap.github.io/cli.html)
- [Nerfstudio Splatfacto](https://docs.nerf.studio/nerfology/methods/splat.html)
- [Apple Object Capture](https://developer.apple.com/documentation/realitykit/realitykit-object-capture/)
- [Vast.ai CLI](https://docs.vast.ai/cli/get-started)
- [Hetzner Volumes](https://docs.hetzner.com/cloud/volumes/overview/)
