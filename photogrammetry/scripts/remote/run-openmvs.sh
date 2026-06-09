#!/usr/bin/env bash
set -euo pipefail

DATASET_DIR="${1:?Usage: run-openmvs.sh DATASET_DIR}"
COLMAP_DENSE="${DATASET_DIR}/colmap/dense"
MESH_DIR="${DATASET_DIR}/mesh/openmvs"

mkdir -p "${MESH_DIR}"

required=(InterfaceCOLMAP DensifyPointCloud ReconstructMesh RefineMesh TextureMesh)
missing=()
for tool in "${required[@]}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    missing+=("${tool}")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "OpenMVS tools missing: ${missing[*]}" >&2
  echo "Skipping OpenMVS mesh stage. COLMAP dense outputs remain available." >&2
  exit 0
fi

if [[ ! -d "${COLMAP_DENSE}" ]]; then
  echo "COLMAP dense workspace not found: ${COLMAP_DENSE}" >&2
  exit 2
fi

echo "[openmvs] interface colmap"
InterfaceCOLMAP \
  -i "${COLMAP_DENSE}" \
  -o "${MESH_DIR}/scene.mvs" \
  --working-folder "${MESH_DIR}"

echo "[openmvs] densify"
DensifyPointCloud \
  -i "${MESH_DIR}/scene.mvs" \
  -o "${MESH_DIR}/dense.mvs" \
  --working-folder "${MESH_DIR}"

echo "[openmvs] reconstruct"
ReconstructMesh \
  -i "${MESH_DIR}/dense.mvs" \
  -o "${MESH_DIR}/mesh.mvs" \
  --working-folder "${MESH_DIR}"

echo "[openmvs] refine"
RefineMesh \
  -i "${MESH_DIR}/mesh.mvs" \
  -o "${MESH_DIR}/mesh_refined.mvs" \
  --working-folder "${MESH_DIR}"

echo "[openmvs] texture"
TextureMesh \
  -i "${MESH_DIR}/mesh_refined.mvs" \
  -o "${MESH_DIR}/mesh_textured.mvs" \
  --export-type obj \
  --working-folder "${MESH_DIR}"

echo "[openmvs] done"
