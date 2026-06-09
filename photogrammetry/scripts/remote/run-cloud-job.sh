#!/usr/bin/env bash
set -euo pipefail

DATASET="${PGM_DATASET:?Set PGM_DATASET}"
TARGET="${PGM_TARGET:-both}"
HETZNER_HOST="${PGM_HETZNER_HOST:?Set PGM_HETZNER_HOST}"
HETZNER_ROOT="${PGM_HETZNER_ROOT:?Set PGM_HETZNER_ROOT}"
WORK_ROOT="${PGM_WORK_ROOT:-/workspace/whatwesee}"
REMOTE_DATASET="${HETZNER_ROOT%/}/datasets/${DATASET}"
LOCAL_DATASET="${WORK_ROOT}/datasets/${DATASET}"
REMOTE_PIPELINE="${HETZNER_ROOT%/}/pipeline/remote"
LOCAL_PIPELINE="${WORK_ROOT}/pipeline/remote"
STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p "${WORK_ROOT}/datasets" "${LOCAL_PIPELINE}" "${LOCAL_DATASET}/logs" "${LOCAL_DATASET}/reports"

rsync_args() {
  local args=(-aP --whole-file --inplace --partial)
  if rsync --help 2>&1 | grep -q -- "--info"; then
    args+=(--info=progress2)
  fi
  printf "%s\n" "${args[@]}"
}

mapfile -t RSYNC_ARGS < <(rsync_args)

echo "[cloud-job] syncing scripts from Hetzner"
rsync "${RSYNC_ARGS[@]}" "${HETZNER_HOST}:${REMOTE_PIPELINE}/" "${LOCAL_PIPELINE}/"

echo "[cloud-job] syncing dataset from Hetzner"
rsync "${RSYNC_ARGS[@]}" "${HETZNER_HOST}:${REMOTE_DATASET}/" "${LOCAL_DATASET}/"

chmod +x "${LOCAL_PIPELINE}"/*.sh || true

status="success"
failure=""

run_stage() {
  local name="$1"
  shift
  echo "[cloud-job] starting ${name}"
  if ! "$@" >"${LOCAL_DATASET}/logs/${name}.log" 2>&1; then
    status="failed"
    failure="${name}"
    echo "[cloud-job] ${name} failed; see logs/${name}.log"
    return 1
  fi
  echo "[cloud-job] finished ${name}"
}

if [[ "${TARGET}" == "mesh" || "${TARGET}" == "both" ]]; then
  run_stage colmap "${LOCAL_PIPELINE}/run-colmap.sh" "${LOCAL_DATASET}" dense || true
fi

if [[ "${status}" == "success" && ( "${TARGET}" == "mesh" || "${TARGET}" == "both" ) ]]; then
  run_stage openmvs "${LOCAL_PIPELINE}/run-openmvs.sh" "${LOCAL_DATASET}" || true
fi

if [[ "${status}" == "success" && ( "${TARGET}" == "splat" || "${TARGET}" == "both" ) ]]; then
  run_stage splatfacto "${LOCAL_PIPELINE}/run-splatfacto.sh" "${LOCAL_DATASET}" || true
fi

FINISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
cat >"${LOCAL_DATASET}/reports/run_report.json" <<JSON
{
  "dataset": "${DATASET}",
  "target": "${TARGET}",
  "started_at": "${STARTED_AT}",
  "finished_at": "${FINISHED_AT}",
  "status": "${status}",
  "failure_stage": "${failure}",
  "host": "$(hostname)",
  "tools": {
    "colmap": "$(command -v colmap || true)",
    "ns_train": "$(command -v ns-train || true)",
    "interface_colmap": "$(command -v InterfaceCOLMAP || true)",
    "texture_mesh": "$(command -v TextureMesh || true)"
  }
}
JSON

echo "[cloud-job] syncing outputs back to Hetzner"
rsync "${RSYNC_ARGS[@]}" "${LOCAL_DATASET}/" "${HETZNER_HOST}:${REMOTE_DATASET}/"

if [[ "${status}" != "success" ]]; then
  exit 1
fi

echo "[cloud-job] done"
