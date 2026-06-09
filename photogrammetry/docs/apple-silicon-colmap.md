# Apple Silicon COLMAP Baselines

Use the M3 Max for sparse COLMAP/GLOMAP-style baselines before renting GPU
time. This is the cost-control gate for reconstruction: if camera registration
is weak locally, Splatfacto, dense MVS, and neural benches will inherit a bad
camera graph.

## Install

```sh
brew install colmap
```

Homebrew COLMAP on Apple Silicon is expected to report `without CUDA`. That is
fine for local sparse baselines:

```sh
colmap -h | head -1
```

Current COLMAP 4.x includes GLOMAP functionality as `global_mapper`. The
standalone GLOMAP project has been migrated into COLMAP, so local baseline
runs should use:

```sh
colmap global_mapper
```

## Run A Local Baseline

Run from the repo root. This command writes artifacts under the dataset's
external data directory:

```sh
python3 photogrammetry/scripts/local_colmap_bench.py \
  --dataset basement-fresh-iphone-001 \
  --name local-colmap-iphone-scaffold-global-hires-001 \
  --matcher exhaustive \
  --mapper global \
  --threads 12 \
  --max-image-size 4096 \
  --max-num-features 8192
```

Outputs:

```text
DATASET/benchmarks/RUN_NAME/
  database.db
  image_list.txt
  selection.json
  logs/
  sparse_incremental/
  sparse_global/
  exports/
  report.json
  report.md
```

`sparse_global/` is the GLOMAP-style result produced by COLMAP
`global_mapper`. `exports/*.ply` are sparse inspection point clouds.

## Known Basement/Garden S0 Result

The current accepted basement/garden S0 candidate is the fresh iPhone-only
capture with 308 working images. It replaced the earlier mixed Canon/iPhone
baseline because the camera graph is substantially more coherent.

| Run | Size/features | Registered | Source registration | Sparse points | Runtime |
| --- | --- | ---: | --- | ---: | ---: |
| `local-colmap-iphone-scaffold-global-hires-001` | 4096px, 8192 features | 305/308 | iPhone 305/308 | 73367 | about 41.7m |
| `local-colmap-mixed-all-global-001` | 2400px, 4096 features | 200/216 | Canon 135/151, iPhone 65/65 | 9907 | about 571s |
| `local-colmap-mixed-all-global-hires-001` | 4096px, 8192 features | 196/216 | Canon 131/151, iPhone 65/65 | 13535 | about 1857s |

Use the fresh iPhone 4096px run as the default camera-pose foundation for
`basement-garden-s0`. Keep the older mixed runs as superseded evidence and as a
record of why we reset the capture strategy.

Promote the selected model before cloud packaging:

```sh
python3 photogrammetry/scripts/pgm.py promote-colmap \
  --dataset basement-fresh-iphone-001 \
  --bench-run local-colmap-iphone-scaffold-global-hires-001 \
  --overwrite
```

After promotion, the canonical sparse model is:

```text
~/whatwesee_photogrammetry_data/basement-fresh-iphone-001/colmap/sparse/0/
```

## Suggested Progression

1. Run the iPhone room scaffold first; it provides wide coverage and stable
   camera poses.
2. Prefer `global_mapper` when unordered room captures fragment under
   incremental mapping.
3. Promote the best iPhone scaffold before paid GPU work.
4. Add Canon detail shots later as a separate candidate after the scaffold and
   first splat are inspected.
5. Do not merge Canon, LiDAR, VGGT, or Splatfacto outputs until a registration
   report scores the alignment.

For local M3 Max runs, leave `--use-gpu` off. Paid NVIDIA GPU jobs should only
build/use CUDA COLMAP when they actually need new sparse/dense COLMAP work. A
splat-only job with a promoted sparse model can skip the CUDA COLMAP build and
spend GPU time on Nerfstudio instead.
