#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

NERFSTUDIO_VERSION="${NERFSTUDIO_VERSION:-1.1.5}"
GSPLAT_VERSION="${GSPLAT_VERSION:-1.4.0}"
UV_CONCURRENT_DOWNLOADS="${UV_CONCURRENT_DOWNLOADS:-16}"
UV_CONCURRENT_BUILDS="${UV_CONCURRENT_BUILDS:-8}"
UV_CONCURRENT_INSTALLS="${UV_CONCURRENT_INSTALLS:-8}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_SCRIPT_DIR="${WWS_GPU_SCRIPT_DIR:-${SCRIPT_DIR}/../gpu}"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_CONCURRENT_DOWNLOADS
export UV_CONCURRENT_BUILDS
export UV_CONCURRENT_INSTALLS

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=(sudo)
fi

if [[ -x "${GPU_SCRIPT_DIR}/bootstrap-gpu.sh" ]]; then
  echo "[setup-vast] running shared GPU bootstrap"
  export WWS_GPU_WORK_ROOT="${WWS_GPU_WORK_ROOT:-${PGM_WORK_ROOT:-/workspace/whatwesee}}"
  export WWS_COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
  export WWS_SRC_ROOT="${WWS_SRC_ROOT:-/workspace/src}"
  export WWS_BUILD_COLMAP_CUDA="${WWS_BUILD_COLMAP_CUDA:-1}"
  export WWS_REQUIRE_COLMAP_CUDA="${WWS_REQUIRE_COLMAP_CUDA:-${PGM_COLMAP_REQUIRE_CUDA:-1}}"
  bash "${GPU_SCRIPT_DIR}/bootstrap-gpu.sh"
else
  echo "[setup-vast] updating apt packages"
  "${SUDO[@]}" apt-get update
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

  if ! command -v colmap >/dev/null 2>&1; then
    echo "[setup-vast] installing COLMAP from apt if available"
    "${SUDO[@]}" apt-get install -y --no-install-recommends colmap || echo "[setup-vast] apt COLMAP install failed; install COLMAP manually before running reconstruction"
  fi
fi

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  "${SUDO[@]}" ln -sf "$(command -v python3)" /usr/local/bin/python
fi

python -m pip install --upgrade pip setuptools wheel uv || python -m pip install --upgrade pip setuptools wheel
if command -v uv >/dev/null 2>&1; then
  uv pip install --system --compile-bytecode --no-cache "nerfstudio==${NERFSTUDIO_VERSION}" "gsplat==${GSPLAT_VERSION}"
else
  python -m pip install --no-cache-dir --retries 10 "nerfstudio==${NERFSTUDIO_VERSION}" "gsplat==${GSPLAT_VERSION}"
fi

echo "[setup-vast] tool versions"
python --version || true
rsync --version | head -1 || true
aria2c --version | head -1 || true
ffmpeg -version | head -1 || true
colmap -h | head -1 || true
ns-train --help >/dev/null 2>&1 && echo "nerfstudio installed" || echo "nerfstudio command probe failed"
nvidia-smi || true

echo "[setup-vast] done"
