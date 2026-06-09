#!/usr/bin/env bash
set -euo pipefail

DATASET_DIR="${1:?Usage: run-colmap.sh DATASET_DIR [sparse|dense]}"
MODE="${2:-dense}"
IMAGE_DIR="${DATASET_DIR}/working/images"
COLMAP_DIR="${DATASET_DIR}/colmap"
DATABASE="${COLMAP_DIR}/database.db"
SPARSE_DIR="${COLMAP_DIR}/sparse"
DENSE_DIR="${COLMAP_DIR}/dense"
SIFT_MAX_IMAGE_SIZE="${PGM_COLMAP_MAX_IMAGE_SIZE:-4096}"
SIFT_MAX_NUM_FEATURES="${PGM_COLMAP_MAX_NUM_FEATURES:-8192}"
MATCHER="${PGM_COLMAP_MATCHER:-exhaustive}"
SEQUENTIAL_OVERLAP="${PGM_COLMAP_SEQUENTIAL_OVERLAP:-20}"
MATCH_MAX_NUM_MATCHES="${PGM_COLMAP_MAX_NUM_MATCHES:-16384}"
EXHAUSTIVE_BLOCK_SIZE="${PGM_COLMAP_EXHAUSTIVE_BLOCK_SIZE:-50}"
FEATURE_MATCHING_TYPE="${PGM_COLMAP_FEATURE_MATCHING_TYPE:-}"
COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
COLMAP_BIN="${PGM_COLMAP_BIN:-}"
REQUIRE_CUDA="${PGM_COLMAP_REQUIRE_CUDA:-0}"
SKIP_SPARSE_IF_PRESENT="${PGM_COLMAP_SKIP_SPARSE_IF_PRESENT:-0}"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

if [[ -z "${COLMAP_BIN}" ]]; then
  if [[ -x "${COLMAP_PREFIX}/bin/colmap" ]]; then
    COLMAP_BIN="${COLMAP_PREFIX}/bin/colmap"
  elif command -v colmap >/dev/null 2>&1; then
    COLMAP_BIN="$(command -v colmap)"
  fi
fi

if [[ -z "${COLMAP_BIN}" || ! -x "${COLMAP_BIN}" ]]; then
  echo "COLMAP is not installed or not on PATH" >&2
  exit 127
fi

COLMAP_HELP="$("${COLMAP_BIN}" -h 2>&1 || true)"
if [[ "${REQUIRE_CUDA}" == "1" && "${COLMAP_HELP}" != *"with CUDA"* ]]; then
  echo "CUDA COLMAP is required, but ${COLMAP_BIN} does not report CUDA support." >&2
  echo "Set PGM_COLMAP_BIN or build CUDA COLMAP under ${COLMAP_PREFIX}." >&2
  exit 127
fi

echo "[colmap] using ${COLMAP_BIN}"
if [[ "${COLMAP_HELP}" == *"with CUDA"* ]]; then
  echo "[colmap] CUDA support detected"
fi

command_help() {
  "${COLMAP_BIN}" "$1" -h 2>&1 || true
}

option_supported() {
  local help_text="$1"
  local option_name="$2"
  [[ "${help_text}" == *"${option_name}"* ]]
}

run_colmap() {
  if [[ "${COLMAP_HELP}" == *"with CUDA"* ]]; then
    "${COLMAP_BIN}" "$@"
  elif command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a "${COLMAP_BIN}" "$@"
  else
    "${COLMAP_BIN}" "$@"
  fi
}

FEATURE_HELP="$(command_help feature_extractor)"
FEATURE_GPU_ARGS=()
FEATURE_SIZE_ARGS=()
if option_supported "${FEATURE_HELP}" "--FeatureExtraction.use_gpu"; then
  FEATURE_GPU_ARGS+=(--FeatureExtraction.use_gpu 1)
elif option_supported "${FEATURE_HELP}" "--SiftExtraction.use_gpu"; then
  FEATURE_GPU_ARGS+=(--SiftExtraction.use_gpu 1)
fi
if option_supported "${FEATURE_HELP}" "--FeatureExtraction.max_image_size"; then
  FEATURE_SIZE_ARGS+=(--FeatureExtraction.max_image_size "${SIFT_MAX_IMAGE_SIZE}")
elif option_supported "${FEATURE_HELP}" "--SiftExtraction.max_image_size"; then
  FEATURE_SIZE_ARGS+=(--SiftExtraction.max_image_size "${SIFT_MAX_IMAGE_SIZE}")
fi

MATCHER_HELP="$(command_help exhaustive_matcher)"
MATCHER_GPU_ARGS=()
if option_supported "${MATCHER_HELP}" "--FeatureMatching.use_gpu"; then
  MATCHER_GPU_ARGS+=(--FeatureMatching.use_gpu 1)
elif option_supported "${MATCHER_HELP}" "--SiftMatching.use_gpu"; then
  MATCHER_GPU_ARGS+=(--SiftMatching.use_gpu 1)
fi
MATCHER_LIMIT_ARGS=()
if option_supported "${MATCHER_HELP}" "--FeatureMatching.max_num_matches"; then
  MATCHER_LIMIT_ARGS+=(--FeatureMatching.max_num_matches "${MATCH_MAX_NUM_MATCHES}")
fi
MATCHER_TYPE_ARGS=()
if [[ -n "${FEATURE_MATCHING_TYPE}" ]] && option_supported "${MATCHER_HELP}" "--FeatureMatching.type"; then
  MATCHER_TYPE_ARGS+=(--FeatureMatching.type "${FEATURE_MATCHING_TYPE}")
fi

if [[ ! -d "${IMAGE_DIR}" ]]; then
  echo "Image directory not found: ${IMAGE_DIR}" >&2
  exit 2
fi

mkdir -p "${COLMAP_DIR}" "${SPARSE_DIR}" "${DENSE_DIR}" "${DATASET_DIR}/logs"

if [[ "${MODE}" != "sparse" && "${MODE}" != "dense" ]]; then
  echo "Mode must be sparse or dense, got: ${MODE}" >&2
  exit 2
fi

if [[ "${SKIP_SPARSE_IF_PRESENT}" == "1" && -f "${SPARSE_DIR}/0/cameras.bin" && -f "${SPARSE_DIR}/0/images.bin" && -f "${SPARSE_DIR}/0/points3D.bin" ]]; then
  echo "[colmap] using existing sparse model at ${SPARSE_DIR}/0"
else
  echo "[colmap] feature extraction"
  run_colmap feature_extractor \
    --database_path "${DATABASE}" \
    --image_path "${IMAGE_DIR}" \
    --ImageReader.single_camera 0 \
    "${FEATURE_GPU_ARGS[@]}" \
    "${FEATURE_SIZE_ARGS[@]}" \
    --SiftExtraction.max_num_features "${SIFT_MAX_NUM_FEATURES}"

  case "${MATCHER}" in
    exhaustive)
      echo "[colmap] exhaustive matching"
      run_colmap exhaustive_matcher \
        --database_path "${DATABASE}" \
        "${MATCHER_GPU_ARGS[@]}" \
        "${MATCHER_LIMIT_ARGS[@]}" \
        "${MATCHER_TYPE_ARGS[@]}" \
        --ExhaustiveMatching.block_size "${EXHAUSTIVE_BLOCK_SIZE}"
      ;;
    sequential)
      echo "[colmap] sequential matching"
      run_colmap sequential_matcher \
        --database_path "${DATABASE}" \
        "${MATCHER_GPU_ARGS[@]}" \
        "${MATCHER_LIMIT_ARGS[@]}" \
        "${MATCHER_TYPE_ARGS[@]}" \
        --SequentialMatching.overlap "${SEQUENTIAL_OVERLAP}"
      ;;
    *)
      echo "Unsupported matcher: ${MATCHER}. Use exhaustive or sequential." >&2
      exit 2
      ;;
  esac

  echo "[colmap] sparse mapping"
  run_colmap mapper \
    --database_path "${DATABASE}" \
    --image_path "${IMAGE_DIR}" \
    --output_path "${SPARSE_DIR}"

  if [[ ! -d "${SPARSE_DIR}/0" ]]; then
    echo "COLMAP did not produce sparse/0" >&2
    exit 3
  fi
fi

if [[ ! -f "${COLMAP_DIR}/sparse.ply" ]]; then
  echo "[colmap] model export"
  run_colmap model_converter \
    --input_path "${SPARSE_DIR}/0" \
    --output_path "${COLMAP_DIR}/sparse.ply" \
    --output_type PLY
else
  echo "[colmap] keeping existing sparse PLY at ${COLMAP_DIR}/sparse.ply"
fi

if [[ "${MODE}" == "sparse" ]]; then
  echo "[colmap] sparse-only mode complete"
  exit 0
fi

echo "[colmap] dense workspace"
run_colmap image_undistorter \
  --image_path "${IMAGE_DIR}" \
  --input_path "${SPARSE_DIR}/0" \
  --output_path "${DENSE_DIR}" \
  --output_type COLMAP

echo "[colmap] patch match stereo"
run_colmap patch_match_stereo \
  --workspace_path "${DENSE_DIR}" \
  --workspace_format COLMAP \
  --PatchMatchStereo.geom_consistency true

echo "[colmap] stereo fusion"
run_colmap stereo_fusion \
  --workspace_path "${DENSE_DIR}" \
  --workspace_format COLMAP \
  --input_type geometric \
  --output_path "${COLMAP_DIR}/fused.ply"

echo "[colmap] done"
