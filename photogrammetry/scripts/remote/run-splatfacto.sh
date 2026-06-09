#!/usr/bin/env bash
set -euo pipefail

DATASET_DIR="${1:?Usage: run-splatfacto.sh DATASET_DIR}"
IMAGE_DIR="${DATASET_DIR}/working/images"
SPLAT_DIR="${DATASET_DIR}/splat"
NS_DATA="${SPLAT_DIR}/nerfstudio-data"
NS_RUNS="${SPLAT_DIR}/runs"
COLMAP_MODEL="${DATASET_DIR}/colmap/sparse/0"
MAX_ITERATIONS="${PGM_SPLAT_MAX_ITERATIONS:-30000}"
REQUIRE_PRECOMPUTED="${PGM_USE_PRECOMPUTED_COLMAP:-0}"
SPLAT_EXPORT_DIR="${SPLAT_DIR}/exports"

if ! command -v ns-process-data >/dev/null 2>&1; then
  echo "ns-process-data is not installed or not on PATH" >&2
  exit 127
fi

if ! command -v ns-train >/dev/null 2>&1; then
  echo "ns-train is not installed or not on PATH" >&2
  exit 127
fi

if [[ ! -d "${IMAGE_DIR}" ]]; then
  echo "Image directory not found: ${IMAGE_DIR}" >&2
  exit 2
fi

mkdir -p "${SPLAT_DIR}" "${NS_RUNS}"

help_text="$(ns-process-data images --help 2>&1 || true)"
if [[ -d "${COLMAP_MODEL}" ]] && grep -q -- "--skip-colmap" <<<"${help_text}" && grep -q -- "--colmap-model-path" <<<"${help_text}"; then
  echo "[splatfacto] processing images with existing COLMAP model"
  ns-process-data images \
    --data "${IMAGE_DIR}" \
    --output-dir "${NS_DATA}" \
    --skip-colmap \
    --colmap-model-path "${COLMAP_MODEL}"
else
  if [[ "${REQUIRE_PRECOMPUTED}" == "1" ]]; then
    echo "PGM_USE_PRECOMPUTED_COLMAP=1, but Nerfstudio cannot reuse the staged COLMAP model." >&2
    echo "Refusing to fall back to internal COLMAP on paid GPU time." >&2
    echo "COLMAP model: ${COLMAP_MODEL}" >&2
    exit 2
  fi
  echo "[splatfacto] processing images into Nerfstudio dataset with internal COLMAP"
  ns-process-data images \
    --data "${IMAGE_DIR}" \
    --output-dir "${NS_DATA}" \
    --matching-method exhaustive \
    --sfm-tool colmap
fi

echo "[splatfacto] training"
ns-train splatfacto \
  --data "${NS_DATA}" \
  --output-dir "${NS_RUNS}" \
  --max-num-iterations "${MAX_ITERATIONS}" \
  --vis viewer

config_path="$(find "${NS_RUNS}" -type f \( -name "config.yml" -o -name "config.yaml" \) | sort | tail -n 1 || true)"
if [[ -n "${config_path}" && -n "$(command -v ns-export || true)" ]]; then
  if ns-export --help 2>&1 | grep -q "gaussian-splat"; then
    echo "[splatfacto] exporting gaussian splat artifact"
    mkdir -p "${SPLAT_EXPORT_DIR}"
    ns-export gaussian-splat \
      --load-config "${config_path}" \
      --output-dir "${SPLAT_EXPORT_DIR}" || echo "[splatfacto] gaussian splat export failed; training outputs remain in ${NS_RUNS}" >&2
  fi
fi

echo "[splatfacto] done"
