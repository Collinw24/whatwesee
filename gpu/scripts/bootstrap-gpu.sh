#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WWS_GPU_WORK_ROOT="${WWS_GPU_WORK_ROOT:-${PGM_WORK_ROOT:-/workspace/whatwesee}}"
WWS_SRC_ROOT="${WWS_SRC_ROOT:-/workspace/src}"
WWS_COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
WWS_BUILD_COLMAP_CUDA="${WWS_BUILD_COLMAP_CUDA:-0}"
WWS_REQUIRE_COLMAP_CUDA="${WWS_REQUIRE_COLMAP_CUDA:-${PGM_COLMAP_REQUIRE_CUDA:-0}}"

export WWS_GPU_WORK_ROOT WWS_SRC_ROOT WWS_COLMAP_PREFIX WWS_REQUIRE_COLMAP_CUDA
export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_CONCURRENT_DOWNLOADS="${UV_CONCURRENT_DOWNLOADS:-16}"
export UV_CONCURRENT_BUILDS="${UV_CONCURRENT_BUILDS:-8}"
export UV_CONCURRENT_INSTALLS="${UV_CONCURRENT_INSTALLS:-8}"

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=(sudo)
fi

mkdir -p "${WWS_GPU_WORK_ROOT}/runtime/logs" "${WWS_GPU_WORK_ROOT}/runtime/preflight" "${WWS_GPU_WORK_ROOT}/downloads" "${WWS_GPU_WORK_ROOT}/cache"

echo "[gpu-bootstrap] apt update"
"${SUDO[@]}" apt-get update

echo "[gpu-bootstrap] installing base transfer/runtime tools"
"${SUDO[@]}" apt-get install -y --no-install-recommends \
  aria2 \
  build-essential \
  ca-certificates \
  cmake \
  curl \
  ffmpeg \
  fpart \
  git \
  git-lfs \
  jq \
  lftp \
  mbuffer \
  ninja-build \
  openssh-client \
  parallel \
  pigz \
  pv \
  python3 \
  python3-pip \
  rsync \
  unzip \
  wget \
  zstd

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  "${SUDO[@]}" ln -sf "$(command -v python3)" /usr/local/bin/python
fi

python -m pip install --upgrade pip setuptools wheel uv || python -m pip install --upgrade pip setuptools wheel

if [[ "${WWS_BUILD_COLMAP_CUDA}" == "1" ]]; then
  if [[ ! -x "${SCRIPT_DIR}/build-colmap-cuda.sh" ]]; then
    echo "[gpu-bootstrap] build-colmap-cuda.sh missing next to bootstrap-gpu.sh" >&2
    exit 2
  fi
  bash "${SCRIPT_DIR}/build-colmap-cuda.sh"
else
  echo "[gpu-bootstrap] WWS_BUILD_COLMAP_CUDA=0; skipping CUDA COLMAP build"
fi

if [[ -x "${SCRIPT_DIR}/preflight-gpu.sh" ]]; then
  WWS_PREFLIGHT_PHASE=postbootstrap bash "${SCRIPT_DIR}/preflight-gpu.sh"
fi

echo "[gpu-bootstrap] done"
