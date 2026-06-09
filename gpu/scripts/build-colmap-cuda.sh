#!/usr/bin/env bash
set -euo pipefail

WWS_GPU_WORK_ROOT="${WWS_GPU_WORK_ROOT:-${PGM_WORK_ROOT:-/workspace/whatwesee}}"
WWS_SRC_ROOT="${WWS_SRC_ROOT:-/workspace/src}"
WWS_COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
WWS_COLMAP_REPO="${WWS_COLMAP_REPO:-https://github.com/colmap/colmap.git}"
WWS_COLMAP_REF="${WWS_COLMAP_REF:-main}"
WWS_COLMAP_BUILD_DIR="${WWS_COLMAP_BUILD_DIR:-build-cuda-system}"
WWS_COLMAP_BUILD_JOBS="${WWS_COLMAP_BUILD_JOBS:-}"
WWS_FORCE_REBUILD_COLMAP="${WWS_FORCE_REBUILD_COLMAP:-0}"
WWS_CUDA_ARCH="${WWS_CUDA_ARCH:-}"

LOG_DIR="${WWS_GPU_WORK_ROOT}/runtime/logs"
REPORT_DIR="${WWS_GPU_WORK_ROOT}/runtime/preflight"
mkdir -p "${LOG_DIR}" "${REPORT_DIR}" "${WWS_SRC_ROOT}"

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=(sudo)
fi

COLMAP_BIN="${WWS_COLMAP_PREFIX}/bin/colmap"
if [[ "${WWS_FORCE_REBUILD_COLMAP}" != "1" && -x "${COLMAP_BIN}" ]] && "${COLMAP_BIN}" -h 2>&1 | grep -q "with CUDA"; then
  echo "[colmap-cuda] existing CUDA COLMAP found: ${COLMAP_BIN}"
  exit 0
fi

echo "[colmap-cuda] installing build dependencies"
export DEBIAN_FRONTEND=noninteractive
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y --no-install-recommends \
  build-essential \
  ca-certificates \
  ccache \
  curl \
  g++-10 \
  gcc-10 \
  git \
  libboost-graph-dev \
  libboost-program-options-dev \
  libboost-system-dev \
  libceres-dev \
  libcurl4-openssl-dev \
  libeigen3-dev \
  libglew-dev \
  libgoogle-glog-dev \
  libgmock-dev \
  libgtest-dev \
  libmetis-dev \
  libopenblas-dev \
  libopenexr-dev \
  libopenimageio-dev \
  libsqlite3-dev \
  libssl-dev \
  libsuitesparse-dev \
  libtiff-dev \
  ninja-build \
  openimageio-tools \
  python3 \
  python3-pip

# Some OpenImageIO CMake packages reference this include directory even when
# OpenCV is not used by COLMAP. Creating it avoids a false configure failure.
"${SUDO[@]}" mkdir -p /usr/include/opencv4

select_cmake() {
  local candidates=()
  if [[ -n "${WWS_CMAKE_BIN:-}" ]]; then
    candidates+=("${WWS_CMAKE_BIN}")
  fi
  candidates+=("/opt/conda/bin/cmake" "cmake")
  local candidate version major minor
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]] || command -v "${candidate}" >/dev/null 2>&1; then
      version="$("${candidate}" --version | awk 'NR == 1 {print $3}')"
      major="${version%%.*}"
      minor="${version#*.}"
      minor="${minor%%.*}"
      if [[ "${major}" =~ ^[0-9]+$ && "${minor}" =~ ^[0-9]+$ ]] && (( major > 3 || (major == 3 && minor >= 24) )); then
        printf '%s\n' "${candidate}"
        return 0
      fi
    fi
  done
  python3 -m pip install --upgrade cmake ninja
  command -v cmake
}

detect_cuda_arch() {
  if [[ -n "${WWS_CUDA_ARCH}" ]]; then
    printf '%s\n' "${WWS_CUDA_ARCH}"
    return 0
  fi
  if command -v nvidia-smi >/dev/null 2>&1; then
    local arch
    arch="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d '. ' || true)"
    if [[ -n "${arch}" ]]; then
      printf '%s\n' "${arch}"
      return 0
    fi
  fi
  printf '80\n'
}

CMAKE_BIN="$(select_cmake)"
CUDA_ARCH="$(detect_cuda_arch)"
if [[ -z "${CUDA_ARCH}" ]]; then
  CUDA_ARCH="80"
fi
if [[ -z "${WWS_COLMAP_BUILD_JOBS}" ]]; then
  WWS_COLMAP_BUILD_JOBS="$(nproc)"
fi

echo "[colmap-cuda] cmake: ${CMAKE_BIN}"
echo "[colmap-cuda] CUDA arch: ${CUDA_ARCH}"

SRC_DIR="${WWS_SRC_ROOT}/colmap"
if [[ ! -d "${SRC_DIR}/.git" ]]; then
  git clone --filter=blob:none "${WWS_COLMAP_REPO}" "${SRC_DIR}"
fi

cd "${SRC_DIR}"
git fetch origin "${WWS_COLMAP_REF}" --depth 1 || git fetch origin "${WWS_COLMAP_REF}"
git checkout FETCH_HEAD

export CC="${CC:-/usr/bin/gcc-10}"
export CXX="${CXX:-/usr/bin/g++-10}"
export CUDAHOSTCXX="${CUDAHOSTCXX:-/usr/bin/g++-10}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset LD_LIBRARY_PATH PYTHONPATH CONDA_PREFIX

rm -rf "${WWS_COLMAP_BUILD_DIR}"
mkdir -p "${WWS_COLMAP_BUILD_DIR}"
cd "${WWS_COLMAP_BUILD_DIR}"

"${CMAKE_BIN}" .. -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${WWS_COLMAP_PREFIX}" \
  -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCH}" \
  -DCUDA_ENABLED=ON \
  -DGUI_ENABLED=OFF \
  -DOPENGL_ENABLED=OFF \
  -DTESTS_ENABLED=OFF \
  -DCGAL_ENABLED=OFF \
  -DONNX_ENABLED=OFF \
  -DFETCH_ONNX=OFF \
  -DBLA_VENDOR=OpenBLAS \
  -DCMAKE_IGNORE_PREFIX_PATH=/opt/conda 2>&1 | tee "${LOG_DIR}/colmap-cuda-configure.log"

ninja -j "${WWS_COLMAP_BUILD_JOBS}" 2>&1 | tee "${LOG_DIR}/colmap-cuda-build.log"
ninja install 2>&1 | tee "${LOG_DIR}/colmap-cuda-install.log"

"${COLMAP_BIN}" -h | head -5
if ! "${COLMAP_BIN}" -h 2>&1 | grep -q "with CUDA"; then
  echo "[colmap-cuda] installed COLMAP does not report CUDA support" >&2
  exit 2
fi

python3 - "${REPORT_DIR}/colmap-cuda-build.json" "${COLMAP_BIN}" "${SRC_DIR}" "${CUDA_ARCH}" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

report, colmap_bin, src_dir, cuda_arch = sys.argv[1:5]
commit = subprocess.check_output(["git", "-C", src_dir, "rev-parse", "HEAD"], text=True).strip()
help_text = subprocess.check_output([colmap_bin, "-h"], text=True, stderr=subprocess.STDOUT)
payload = {
    "schema_version": 1,
    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "status": "success",
    "colmap_bin": colmap_bin,
    "colmap_commit": commit,
    "cuda_arch": cuda_arch,
    "reports_cuda": "with CUDA" in help_text,
}
Path(report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"[colmap-cuda] wrote {report}")
PY

echo "[colmap-cuda] done"
