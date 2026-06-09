# Basement/Garden S0 Status

Current as of April 29, 2026.

## Dataset

- Local dataset: `~/whatwesee_photogrammetry_data/basement-fresh-iphone-001`
- Hetzner dataset: `$STAGING_HOST:/srv/staging/photogrammetry/datasets/basement-fresh-iphone-001`
- Evidence package: `~/whatwesee_evidence_data/basement-garden-s0`
- Hetzner evidence package: `$STAGING_HOST:/srv/staging/evidence/packages/basement-garden-s0`
- Working images: `308`
- Sources: iPhone only for this baseline
- Working image size: about `1.9 GB`
- Staged Hetzner dataset size: about `2.8 GB`

## Accepted Sparse Baseline

Promoted run:

```text
local-colmap-iphone-scaffold-global-hires-001
```

Result:

- Registered images: `305/308`
- Missing images: `IMG_0123.jpg`, `IMG_0126.jpg`, `IMG_0210.jpg`
- Sparse points: `73367`
- Observations: `295714`
- Mean track length: `4.030613`
- Mean observations per image: `969.554098`
- Mean reprojection error: `0.000363px`
- Matching runtime: about `41.7 minutes` on the M3 Max

This replaces the earlier mixed Canon/iPhone baseline. Canon detail shots are
deferred until the iPhone scaffold and first splat pass are inspected.

Canonical promoted paths:

```text
DATASET/colmap/sparse/0/
DATASET/colmap/database.db
DATASET/colmap/sparse.ply
DATASET/reports/promoted_colmap.json
```

## Cloud Handoff

The current staged splat-only GPU package is:

```text
/srv/staging/photogrammetry/jobs/basement-fresh-iphone-001-splat-s0-001
```

That package uses:

```text
PGM_USE_PRECOMPUTED_COLMAP=1
WWS_BUILD_COLMAP_CUDA=0
WWS_REQUIRE_COLMAP_CUDA=0
PGM_TARGET=splat
PGM_SPLAT_MAX_ITERATIONS=30000
```

For the next Vast run, the GPU should pull this package, verify that
`colmap/sparse/0` exists on Hetzner, skip sparse COLMAP, and spend compute on
Nerfstudio Splatfacto.

The package is intentionally not a mesh/dense-COLMAP job. Depth maps, dense
point maps, VGGT, and LiDAR alignment remain separate next-stage evidence
layers rather than being silently merged into this first splat run.
