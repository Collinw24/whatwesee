#!/usr/bin/env bash
set -euo pipefail

WWS_GPU_WORK_ROOT="${WWS_GPU_WORK_ROOT:-${PGM_WORK_ROOT:-/workspace/whatwesee}}"
WWS_PREFLIGHT_DIR="${WWS_PREFLIGHT_DIR:-${WWS_GPU_WORK_ROOT}/runtime/preflight}"
WWS_PREFLIGHT_PHASE="${WWS_PREFLIGHT_PHASE:-full}"
WWS_MIN_DISK_FREE_GB="${WWS_MIN_DISK_FREE_GB:-80}"
WWS_MIN_GPU_VRAM_GB="${WWS_MIN_GPU_VRAM_GB:-48}"
WWS_HETZNER_HOST="${WWS_HETZNER_HOST:-${PGM_HETZNER_HOST:-}}"
WWS_HETZNER_TEST_PATH="${WWS_HETZNER_TEST_PATH:-${PGM_REMOTE_DATASET:-}}"
WWS_REQUIRE_HETZNER="${WWS_REQUIRE_HETZNER:-}"
WWS_COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
WWS_REQUIRE_COLMAP_CUDA="${WWS_REQUIRE_COLMAP_CUDA:-${PGM_COLMAP_REQUIRE_CUDA:-0}}"
PGM_COLMAP_BIN="${PGM_COLMAP_BIN:-}"

export WWS_GPU_WORK_ROOT WWS_PREFLIGHT_PHASE WWS_MIN_DISK_FREE_GB WWS_MIN_GPU_VRAM_GB

mkdir -p "${WWS_PREFLIGHT_DIR}"

REPORT_PATH="${WWS_PREFLIGHT_REPORT:-${WWS_PREFLIGHT_DIR}/gpu-preflight-$(date -u +%Y%m%dT%H%M%SZ).json}"
FAILURES_FILE="$(mktemp)"
WARNINGS_FILE="$(mktemp)"
CHECKS_FILE="$(mktemp)"
trap 'rm -f "${FAILURES_FILE}" "${WARNINGS_FILE}" "${CHECKS_FILE}"' EXIT

record_check() {
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"${CHECKS_FILE}"
}

fail() {
  printf '%s\n' "$1" >>"${FAILURES_FILE}"
  record_check "$2" "fail" "$1"
}

warn() {
  printf '%s\n' "$1" >>"${WARNINGS_FILE}"
  record_check "$2" "warn" "$1"
}

pass() {
  record_check "$1" "pass" "$2"
}

command_name() {
  command -v "$1" 2>/dev/null || true
}

require_command() {
  local name="$1"
  local path
  path="$(command_name "${name}")"
  if [[ -n "${path}" ]]; then
    pass "command:${name}" "${path}"
  else
    fail "required command missing: ${name}" "command:${name}"
  fi
}

optional_command() {
  local name="$1"
  local path
  path="$(command_name "${name}")"
  if [[ -n "${path}" ]]; then
    pass "command:${name}" "${path}"
  else
    warn "optional command missing: ${name}" "command:${name}"
  fi
}

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1 || true)"
  GPU_VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1 | tr -d ' ' || true)"
  pass "nvidia-smi" "${GPU_NAME:-unknown}"
  if [[ "${GPU_VRAM_MB}" =~ ^[0-9]+$ ]]; then
    GPU_VRAM_GB=$((GPU_VRAM_MB / 1024))
    if (( GPU_VRAM_GB < WWS_MIN_GPU_VRAM_GB )); then
      fail "GPU VRAM ${GPU_VRAM_GB}GB is below required ${WWS_MIN_GPU_VRAM_GB}GB" "gpu:vram"
    else
      pass "gpu:vram" "${GPU_VRAM_GB}GB"
    fi
  else
    fail "could not read GPU VRAM from nvidia-smi" "gpu:vram"
  fi
else
  fail "nvidia-smi missing; this does not look like a usable NVIDIA GPU host" "nvidia-smi"
fi

if command -v nvcc >/dev/null 2>&1; then
  pass "nvcc" "$(nvcc --version | tail -n1)"
else
  if [[ "${WWS_REQUIRE_NVCC:-1}" == "1" ]]; then
    fail "nvcc missing; CUDA source builds require a devel image" "nvcc"
  else
    warn "nvcc missing" "nvcc"
  fi
fi

mkdir -p "${WWS_GPU_WORK_ROOT}"
FREE_GB="$(df -BG "${WWS_GPU_WORK_ROOT}" | awk 'NR == 2 {gsub("G", "", $4); print $4}')"
if [[ "${FREE_GB}" =~ ^[0-9]+$ ]] && (( FREE_GB >= WWS_MIN_DISK_FREE_GB )); then
  pass "disk:free" "${FREE_GB}GB"
else
  fail "free disk ${FREE_GB:-unknown}GB is below required ${WWS_MIN_DISK_FREE_GB}GB at ${WWS_GPU_WORK_ROOT}" "disk:free"
fi

if [[ "${WWS_PREFLIGHT_PHASE}" != "prebootstrap" ]]; then
  for tool in ssh rsync aria2c parallel zstd pigz pv fpart mbuffer git curl python3; do
    require_command "${tool}"
  done
  optional_command jq
  optional_command ffmpeg
fi

if [[ -z "${WWS_REQUIRE_HETZNER}" ]]; then
  if [[ -n "${WWS_HETZNER_HOST}" ]]; then
    WWS_REQUIRE_HETZNER=1
  else
    WWS_REQUIRE_HETZNER=0
  fi
fi

if [[ "${WWS_REQUIRE_HETZNER}" == "1" ]]; then
  if [[ -z "${WWS_HETZNER_HOST}" ]]; then
    fail "Hetzner host is required but WWS_HETZNER_HOST/PGM_HETZNER_HOST is empty" "hetzner:ssh"
  else
    if [[ -n "${WWS_HETZNER_TEST_PATH}" ]]; then
      if ssh -o BatchMode=yes -o ConnectTimeout=10 "${WWS_HETZNER_HOST}" "test -e '${WWS_HETZNER_TEST_PATH}'" >/dev/null 2>&1; then
        pass "hetzner:ssh" "${WWS_HETZNER_HOST}:${WWS_HETZNER_TEST_PATH}"
      else
        fail "cannot reach Hetzner path ${WWS_HETZNER_HOST}:${WWS_HETZNER_TEST_PATH}" "hetzner:ssh"
      fi
    elif ssh -o BatchMode=yes -o ConnectTimeout=10 "${WWS_HETZNER_HOST}" "true" >/dev/null 2>&1; then
      pass "hetzner:ssh" "${WWS_HETZNER_HOST}"
    else
      fail "cannot SSH to Hetzner host ${WWS_HETZNER_HOST}" "hetzner:ssh"
    fi
  fi
fi

COLMAP_BIN="${PGM_COLMAP_BIN}"
if [[ -z "${COLMAP_BIN}" && -x "${WWS_COLMAP_PREFIX}/bin/colmap" ]]; then
  COLMAP_BIN="${WWS_COLMAP_PREFIX}/bin/colmap"
elif [[ -z "${COLMAP_BIN}" ]]; then
  COLMAP_BIN="$(command_name colmap)"
fi

if [[ "${WWS_REQUIRE_COLMAP_CUDA}" == "1" ]]; then
  if [[ -z "${COLMAP_BIN}" || ! -x "${COLMAP_BIN}" ]]; then
    fail "CUDA COLMAP is required but no colmap binary was found" "colmap:cuda"
  else
    COLMAP_HELP="$("${COLMAP_BIN}" -h 2>&1 || true)"
    if [[ "${COLMAP_HELP}" == *"with CUDA"* ]]; then
      pass "colmap:cuda" "${COLMAP_BIN}"
    else
      fail "COLMAP binary does not report CUDA support: ${COLMAP_BIN}" "colmap:cuda"
    fi
  fi
elif [[ -n "${COLMAP_BIN}" ]]; then
  pass "colmap" "${COLMAP_BIN}"
fi

STATUS="pass"
if [[ -s "${FAILURES_FILE}" ]]; then
  STATUS="fail"
fi

if command -v python3 >/dev/null 2>&1; then
  python3 - "${REPORT_PATH}" "${STATUS}" "${CHECKS_FILE}" "${FAILURES_FILE}" "${WARNINGS_FILE}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path, status, checks_file, failures_file, warnings_file = sys.argv[1:6]

def lines(path):
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    return [line for line in text.splitlines() if line]

checks = []
for line in lines(checks_file):
    name, state, detail = (line.split("\t", 2) + ["", ""])[:3]
    checks.append({"name": name, "status": state, "detail": detail})

payload = {
    "schema_version": 1,
    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "status": status,
    "phase": os.environ.get("WWS_PREFLIGHT_PHASE", "full"),
    "work_root": os.environ.get("WWS_GPU_WORK_ROOT"),
    "minimums": {
        "disk_free_gb": os.environ.get("WWS_MIN_DISK_FREE_GB"),
        "gpu_vram_gb": os.environ.get("WWS_MIN_GPU_VRAM_GB"),
    },
    "checks": checks,
    "failures": lines(failures_file),
    "warnings": lines(warnings_file),
}
Path(report_path).parent.mkdir(parents=True, exist_ok=True)
Path(report_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"[preflight] wrote {report_path}")
PY
else
  {
    printf 'status=%s\n' "${STATUS}"
    sed 's/^/failure=/' "${FAILURES_FILE}" || true
    sed 's/^/warning=/' "${WARNINGS_FILE}" || true
  } >"${REPORT_PATH%.json}.txt"
  echo "[preflight] wrote ${REPORT_PATH%.json}.txt"
fi

if [[ "${STATUS}" != "pass" ]]; then
  echo "[preflight] failed" >&2
  cat "${FAILURES_FILE}" >&2
  exit 2
fi

echo "[preflight] passed"
