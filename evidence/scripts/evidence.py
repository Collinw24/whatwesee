#!/usr/bin/env python3
"""Structured evidence package CLI for What We See."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ in this project.
    tomllib = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_CONFIG = PROJECT_ROOT / "configs" / "evidence.local.toml"
DEFAULT_CONFIG: dict[str, Any] = {
    "local": {
        "evidence_root": "~/whatwesee_evidence_data",
        "photogrammetry_root": "~/whatwesee_photogrammetry_data",
    },
    "hetzner": {
        "ssh_host": "",
        "remote_root": "/srv/staging/evidence",
        "photogrammetry_remote_root": "/srv/staging/photogrammetry",
        "rsync_extra_args": [],
    },
    "bench": {
        "default_models": ["vggt", "colmap", "glomap", "splatfacto"],
    },
    "policy": {
        "lidar_role": "reference_control_geometry",
        "raw_data_in_repo": False,
    },
}

PACKAGE_DIRS = [
    "raw/photos",
    "raw/lidar/iphone",
    "working/image_lists",
    "working/lidar",
    "working/masks",
    "working/previews",
    "manifests",
    "registration",
    "benchmarks/vggt",
    "benchmarks/colmap",
    "benchmarks/glomap",
    "benchmarks/splatfacto",
    "semantics",
    "state",
    "logs",
]
LIDAR_EXTENSIONS = {
    ".ply",
    ".obj",
    ".glb",
    ".gltf",
    ".usdz",
    ".usd",
    ".reality",
    ".zip",
    ".las",
    ".laz",
}
ARTIFACT_CLASSES = {"evidence", "inference", "visualization"}


class UserError(RuntimeError):
    """An expected CLI error with a clean message."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in base.items():
        merged[key] = deep_merge(value, {}) if isinstance(value, dict) else value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | None) -> tuple[dict[str, Any], Path | None]:
    if tomllib is None:
        raise UserError("Python tomllib is unavailable. Use Python 3.11 or newer.")

    config = deep_merge(DEFAULT_CONFIG, {})
    selected: Path | None = None
    env_path = os.environ.get("EVIDENCE_CONFIG")

    if config_path:
        selected = Path(config_path).expanduser()
    elif env_path:
        selected = Path(env_path).expanduser()
    elif DEFAULT_LOCAL_CONFIG.exists():
        selected = DEFAULT_LOCAL_CONFIG

    if selected:
        if not selected.exists():
            raise UserError(f"Config file not found: {selected}")
        with selected.open("rb") as handle:
            loaded = tomllib.load(handle)
        config = deep_merge(config, loaded)

    env_overrides = {
        "EVIDENCE_ROOT": ("local", "evidence_root"),
        "EVIDENCE_DATA_ROOT": ("local", "evidence_root"),
        "PGM_DATA_ROOT": ("local", "photogrammetry_root"),
        "EVIDENCE_HETZNER_HOST": ("hetzner", "ssh_host"),
        "EVIDENCE_HETZNER_ROOT": ("hetzner", "remote_root"),
        "PGM_HETZNER_ROOT": ("hetzner", "photogrammetry_remote_root"),
    }
    for env_name, path in env_overrides.items():
        value = os.environ.get(env_name)
        if value:
            config[path[0]][path[1]] = value

    return config, selected


def evidence_root(config: dict[str, Any]) -> Path:
    return Path(str(config["local"]["evidence_root"])).expanduser().resolve()


def photogrammetry_root(config: dict[str, Any]) -> Path:
    return Path(str(config["local"]["photogrammetry_root"])).expanduser().resolve()


def require_hetzner(config: dict[str, Any]) -> tuple[str, str, str]:
    host = str(config["hetzner"].get("ssh_host") or "").strip()
    root = str(config["hetzner"].get("remote_root") or "").strip()
    pgm_root = str(config["hetzner"].get("photogrammetry_remote_root") or "").strip()
    if not host:
        raise UserError("Hetzner ssh_host is not configured. Set EVIDENCE_HETZNER_HOST or evidence.local.toml.")
    if not root:
        raise UserError("Hetzner remote_root is not configured.")
    if not pgm_root:
        raise UserError("Hetzner photogrammetry_remote_root is not configured.")
    return host, root.rstrip("/"), pgm_root.rstrip("/")


def remote_package_path(config: dict[str, Any], package_name: str) -> str:
    _host, root, _pgm_root = require_hetzner(config)
    return f"{root}/packages/{package_name}"


def shell_join(args: list[str]) -> str:
    return shlex.join([str(arg) for arg in args])


def rsync_base_args(config: dict[str, Any], dry_run: bool = False) -> list[str]:
    args = ["rsync", "-azP"]
    if dry_run:
        args.append("--dry-run")
    extra = config["hetzner"].get("rsync_extra_args") or []
    if not isinstance(extra, list):
        raise UserError("hetzner.rsync_extra_args must be a list.")
    args.extend(str(item) for item in extra)
    return args


def validate_name(name: str, label: str = "Name") -> None:
    if not name:
        raise UserError(f"{label} is required.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(char not in allowed for char in name):
        raise UserError(f"{label} may only contain letters, numbers, dot, dash, and underscore.")
    if name in {".", ".."}:
        raise UserError(f"{label} is invalid.")


def package_path(config: dict[str, Any], name: str) -> Path:
    validate_name(name, "Package name")
    return evidence_root(config) / name


def ensure_package_dirs(path: Path) -> None:
    for rel in PACKAGE_DIRS:
        (path / rel).mkdir(parents=True, exist_ok=True)


def json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def package_manifest_path(package: Path) -> Path:
    return package / "manifests" / "package.json"


def artifact_ledger_path(package: Path) -> Path:
    return package / "manifests" / "artifacts.json"


def require_package(config: dict[str, Any], name: str) -> tuple[Path, dict[str, Any]]:
    path = package_path(config, name)
    manifest_path = package_manifest_path(path)
    if not manifest_path.exists():
        raise UserError(f"Evidence package is not initialized: {name}. Run init-package first.")
    return path, json_read(manifest_path)


def human_bytes(num: int | float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def load_artifacts(package: Path) -> dict[str, Any]:
    path = artifact_ledger_path(package)
    if path.exists():
        return json_read(path)
    return {"schema_version": 1, "created_at": utc_now(), "artifacts": []}


def add_artifact(
    package: Path,
    *,
    path: str,
    artifact_class: str,
    role: str,
    modality: str | None = None,
    source: str | None = None,
    description: str | None = None,
) -> None:
    if artifact_class not in ARTIFACT_CLASSES:
        raise UserError(f"Invalid artifact class: {artifact_class}")
    ledger = load_artifacts(package)
    artifacts = [item for item in ledger.get("artifacts", []) if item.get("path") != path]
    item: dict[str, Any] = {
        "path": path,
        "class": artifact_class,
        "role": role,
        "created_at": utc_now(),
    }
    if modality:
        item["modality"] = modality
    if source:
        item["source"] = source
    if description:
        item["description"] = description
    artifacts.append(item)
    artifacts.sort(key=lambda record: record["path"])
    ledger["updated_at"] = utc_now()
    ledger["artifacts"] = artifacts
    json_write(artifact_ledger_path(package), ledger)


def update_manifest(package: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    json_write(package_manifest_path(package), manifest)
    write_state_summary(package, manifest)


def linked_photo_datasets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    photos = manifest.get("modalities", {}).get("photos", {})
    datasets = photos.get("datasets", [])
    return datasets if isinstance(datasets, list) else []


def lidar_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    lidar = manifest.get("modalities", {}).get("lidar", {})
    records = lidar.get("records", [])
    return records if isinstance(records, list) else []


def write_state_summary(package: Path, manifest: dict[str, Any]) -> None:
    photos = linked_photo_datasets(manifest)
    lidar = lidar_records(manifest)
    models = manifest.get("bench", {}).get("models", ["vggt", "colmap", "glomap", "splatfacto"])
    missing: list[str] = []
    if not photos:
        missing.append("photo_dataset")
    if not lidar:
        missing.append("iphone_lidar_reference")
    if not (package / "benchmarks" / "bench_plan.md").exists():
        missing.append("bench_plan")
    if not (package / "registration" / "register_report.json").exists():
        missing.append("registration_report")

    state = {
        "schema_version": 1,
        "package": manifest["name"],
        "target": manifest["target"],
        "state_id": manifest["state_id"],
        "updated_at": utc_now(),
        "modalities_present": {
            "photos": bool(photos),
            "lidar": bool(lidar),
            "semantics": bool(manifest.get("modalities", {}).get("semantics")),
        },
        "photo_datasets": photos,
        "lidar_records": lidar,
        "bench_models": models,
        "missing": missing,
        "policy": manifest.get("policy", {}),
    }
    json_write(package / "state" / f"{manifest['state_id']}_state.json", state)

    lines = [
        f"# State Package: {manifest['name']} {manifest['state_id']}",
        "",
        f"- Target: `{manifest['target']}`",
        f"- Photos linked: `{len(photos)}`",
        f"- LiDAR records: `{len(lidar)}`",
        f"- Bench models: `{', '.join(models)}`",
        f"- Missing: `{', '.join(missing) if missing else 'none'}`",
        "",
        "## Evidence Policy",
        "",
        f"- LiDAR role: `{manifest.get('policy', {}).get('lidar_role')}`",
        "- Model outputs remain separate until registration reports score them.",
    ]
    (package / "state" / f"{manifest['state_id']}_state.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_or_link_file(src: Path, dst: Path, link: bool) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if link:
        os.symlink(src, dst)
        return "symlink"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def copy_or_link_directory(src: Path, dst: Path, link: bool) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if link:
        os.symlink(src, dst)
        return "symlink"
    shutil.copytree(src, dst)
    return "copytree"


def artifact_rel(package: Path, path: Path) -> str:
    return path.relative_to(package).as_posix()


def cmd_init_package(args: argparse.Namespace, config: dict[str, Any]) -> int:
    validate_name(args.name, "Package name")
    validate_name(args.state_id, "State id")
    package = package_path(config, args.name)
    if package.exists() and not args.overwrite:
        raise UserError(f"Evidence package already exists: {package}. Use --overwrite to rebuild it.")
    if package.exists() and args.overwrite:
        shutil.rmtree(package)
    ensure_package_dirs(package)

    manifest = {
        "schema_version": 1,
        "name": args.name,
        "target": args.target,
        "state_id": args.state_id,
        "created_at": utc_now(),
        "data_root": str(evidence_root(config)),
        "modalities": {
            "photos": {"datasets": []},
            "lidar": {"records": []},
        },
        "bench": {
            "models": list(config["bench"].get("default_models", ["vggt", "colmap", "glomap", "splatfacto"])),
        },
        "policy": {
            "lidar_role": str(config["policy"].get("lidar_role", "reference_control_geometry")),
            "raw_data_in_repo": bool(config["policy"].get("raw_data_in_repo", False)),
            "model_outputs_require_registration": True,
            "artifact_classes": sorted(ARTIFACT_CLASSES),
        },
        "status": {
            "initialized": True,
            "photo_dataset_linked": False,
            "lidar_ingested": False,
            "bench_plan_written": False,
        },
    }
    json_write(package_manifest_path(package), manifest)
    json_write(artifact_ledger_path(package), {"schema_version": 1, "created_at": utc_now(), "artifacts": []})
    add_artifact(
        package,
        path="manifests/package.json",
        artifact_class="evidence",
        role="package_manifest",
        description="Evidence package identity and modality inventory.",
    )
    write_state_summary(package, manifest)
    print(f"Initialized evidence package: {package}")
    return 0


def photogrammetry_dataset_path(config: dict[str, Any], dataset_name: str) -> Path:
    validate_name(dataset_name, "Photogrammetry dataset name")
    return photogrammetry_root(config) / dataset_name


def load_photogrammetry_dataset(config: dict[str, Any], dataset_name: str) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    dataset = photogrammetry_dataset_path(config, dataset_name)
    manifest_path = dataset / "manifests" / "manifest.json"
    if not manifest_path.exists():
        raise UserError(f"Photogrammetry manifest not found: {manifest_path}")
    qc_path = dataset / "reports" / "qc_report.json"
    manifest = json_read(manifest_path)
    qc_report = json_read(qc_path) if qc_path.exists() else None
    return dataset, manifest, qc_report


def cmd_link_photogrammetry(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, package_manifest = require_package(config, args.package)
    dataset, manifest, qc_report = load_photogrammetry_dataset(config, args.dataset)
    link_path = package / "raw" / "photos" / args.dataset
    link_mode = copy_or_link_directory(dataset, link_path, link=True)

    image_list = []
    for image in manifest.get("images", []):
        image_list.append(
            {
                "relative_path": image.get("relative_path"),
                "working_path": image.get("working_path"),
                "absolute_working_path": str((dataset / image.get("working_path", "")).resolve()),
                "sha256": image.get("sha256"),
                "camera_model": image.get("camera_model"),
                "lens_model": image.get("lens_model"),
                "focal_length": image.get("focal_length"),
                "source_dataset": image.get("source_dataset"),
                "source_relative_path": image.get("source_relative_path"),
            }
        )
    image_list_path = package / "working" / "image_lists" / f"{args.dataset}.json"
    json_write(image_list_path, {"schema_version": 1, "dataset": args.dataset, "images": image_list})

    summary = {
        "schema_version": 1,
        "dataset": args.dataset,
        "linked_at": utc_now(),
        "link_mode": link_mode,
        "source_dataset_path": str(dataset),
        "package_photo_path": artifact_rel(package, link_path),
        "source_manifest_path": str(dataset / "manifests" / "manifest.json"),
        "source_qc_report_path": str(dataset / "reports" / "qc_report.json"),
        "image_count": manifest.get("image_count", 0),
        "working_total_bytes": manifest.get("working_total_bytes", 0),
        "focal_groups": manifest.get("focal_groups", {}),
        "qc": {
            "available": qc_report is not None,
            "passed": qc_report.get("passed") if qc_report else None,
            "warning_count": qc_report.get("summary", {}).get("warning_count") if qc_report else None,
            "fatal_count": qc_report.get("summary", {}).get("fatal_count") if qc_report else None,
        },
        "artifact_class": "evidence",
    }
    summary_path = package / "manifests" / f"photogrammetry_{args.dataset}.json"
    json_write(summary_path, summary)

    photos = package_manifest.setdefault("modalities", {}).setdefault("photos", {})
    datasets = [item for item in photos.get("datasets", []) if item.get("dataset") != args.dataset]
    datasets.append(
        {
            "dataset": args.dataset,
            "image_count": manifest.get("image_count", 0),
            "working_total_bytes": manifest.get("working_total_bytes", 0),
            "manifest": artifact_rel(package, summary_path),
            "image_list": artifact_rel(package, image_list_path),
            "source_path": str(dataset),
            "link_path": artifact_rel(package, link_path),
            "qc_passed": summary["qc"]["passed"],
        }
    )
    datasets.sort(key=lambda item: item["dataset"])
    photos["datasets"] = datasets
    package_manifest["status"]["photo_dataset_linked"] = True
    update_manifest(package, package_manifest)

    add_artifact(
        package,
        path=artifact_rel(package, summary_path),
        artifact_class="evidence",
        role="photogrammetry_source_manifest",
        modality="photos",
        source=str(dataset),
        description="Linked photogrammetry dataset summary and QC provenance.",
    )
    add_artifact(
        package,
        path=artifact_rel(package, image_list_path),
        artifact_class="evidence",
        role="photogrammetry_working_image_list",
        modality="photos",
        source=str(dataset),
        description="Normalized list of working images for model bench inputs.",
    )
    print(f"Linked photogrammetry dataset {args.dataset} into {package}")
    print(f"Images: {manifest.get('image_count', 0)}")
    print(f"Working size: {human_bytes(int(manifest.get('working_total_bytes', 0)))}")
    return 0


def source_size(source: Path) -> int:
    if source.is_file():
        return source.stat().st_size
    return directory_size(source)


def source_checksum(source: Path) -> str | None:
    if source.is_file():
        return sha256_file(source)
    return None


def cmd_ingest_lidar(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, package_manifest = require_package(config, args.package)
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise UserError(f"LiDAR source does not exist: {source}")
    if source.is_file() and source.suffix.lower() not in LIDAR_EXTENSIONS:
        raise UserError(f"Unsupported LiDAR extension: {source.suffix}. Expected one of {sorted(LIDAR_EXTENSIONS)}")
    device = args.device
    validate_name(device.replace("-", "_"), "Device")
    device_dir = "iphone" if device == "iphone-lidar" else device.replace("-", "_")
    dst = package / "raw" / "lidar" / device_dir / source.name
    transfer_mode = copy_or_link_directory(source, dst, args.link) if source.is_dir() else copy_or_link_file(source, dst, args.link)
    record_id = f"{device}_{source.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    record = {
        "schema_version": 1,
        "id": record_id,
        "device": device,
        "role": str(config["policy"].get("lidar_role", "reference_control_geometry")),
        "ingested_at": utc_now(),
        "source_path": str(source),
        "package_path": artifact_rel(package, dst),
        "transfer_mode": transfer_mode,
        "bytes": source_size(dst),
        "sha256": source_checksum(dst),
        "extension": source.suffix.lower() if source.is_file() else "directory",
        "artifact_class": "evidence",
        "notes": args.notes,
    }
    record_path = package / "manifests" / f"lidar_{record_id}.json"
    json_write(record_path, record)

    lidar = package_manifest.setdefault("modalities", {}).setdefault("lidar", {})
    records = [item for item in lidar.get("records", []) if item.get("id") != record_id]
    records.append(
        {
            "id": record_id,
            "device": device,
            "role": record["role"],
            "manifest": artifact_rel(package, record_path),
            "package_path": artifact_rel(package, dst),
            "bytes": record["bytes"],
        }
    )
    lidar["records"] = records
    package_manifest["status"]["lidar_ingested"] = True
    update_manifest(package, package_manifest)

    add_artifact(
        package,
        path=artifact_rel(package, dst),
        artifact_class="evidence",
        role="lidar_reference_geometry",
        modality="lidar",
        source=str(source),
        description="LiDAR reference/control geometry export.",
    )
    add_artifact(
        package,
        path=artifact_rel(package, record_path),
        artifact_class="evidence",
        role="lidar_manifest",
        modality="lidar",
        source=str(source),
        description="LiDAR ingestion metadata and evidence role.",
    )
    print(f"Ingested LiDAR reference: {dst}")
    print(f"Role: {record['role']}")
    print(f"Size: {human_bytes(record['bytes'])}")
    return 0


def cmd_write_session(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, package_manifest = require_package(config, args.package)
    notes_path = Path(args.notes).expanduser().resolve() if args.notes else None
    if notes_path and not notes_path.exists():
        raise UserError(f"Notes file not found: {notes_path}")
    notes_text = notes_path.read_text(encoding="utf-8") if notes_path else ""
    session = {
        "schema_version": 1,
        "package": package_manifest["name"],
        "target": package_manifest["target"],
        "state_id": package_manifest["state_id"],
        "written_at": utc_now(),
        "capture_date": args.date,
        "location": args.location,
        "operator": args.operator,
        "notes_source": str(notes_path) if notes_path else None,
        "notes": notes_text,
        "capture_conditions": {
            "lighting": args.lighting,
            "fans_or_motion": args.fans,
            "grow_equipment": args.grow_equipment,
            "humidity": args.humidity,
            "temperature": args.temperature,
        },
    }
    session_path = package / "manifests" / "session.json"
    json_write(session_path, session)
    package_manifest["session"] = artifact_rel(package, session_path)
    update_manifest(package, package_manifest)
    add_artifact(
        package,
        path=artifact_rel(package, session_path),
        artifact_class="evidence",
        role="capture_session_metadata",
        description="Capture date, location, notes, and capture conditions.",
    )
    print(f"Wrote session metadata: {session_path}")
    return 0


def bench_model_contracts(package_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "model": "vggt",
            "role": "neural_geometry_pass",
            "artifact_class": "inference",
            "expected_outputs": ["cameras.json", "depth_maps/", "point_maps/", "tracks/", "confidence_maps/", "point_cloud.ply"],
            "metrics": ["camera_count", "point_count", "confidence_summary", "runtime_seconds", "failure_reason"],
        },
        {
            "model": "colmap",
            "role": "classical_sfm_mvs_baseline",
            "artifact_class": "inference",
            "expected_outputs": ["database.db", "sparse/0/", "sparse.ply", "dense/", "fused.ply"],
            "metrics": ["registered_image_count", "registered_image_percent", "reprojection_error", "sparse_point_count", "runtime_seconds"],
        },
        {
            "model": "glomap",
            "role": "fast_global_sfm_baseline",
            "artifact_class": "inference",
            "expected_outputs": ["sparse/0/", "sparse.ply", "metrics.json"],
            "metrics": ["registered_image_count", "registered_image_percent", "sparse_point_count", "runtime_seconds", "failure_reason"],
        },
        {
            "model": "splatfacto",
            "role": "gaussian_splat_visualization",
            "artifact_class": "visualization",
            "expected_outputs": ["nerfstudio-data/", "runs/", "exports/"],
            "metrics": ["source_geometry", "iterations", "runtime_seconds", "viewer_screenshot", "failure_reason"],
        },
    ]


def bench_plan_markdown(package: Path, manifest: dict[str, Any]) -> str:
    photos = linked_photo_datasets(manifest)
    lidar = lidar_records(manifest)
    primary_dataset = photos[0]["dataset"] if photos else "LINK_PHOTOGRAMMETRY_DATASET_FIRST"
    state_slug = str(manifest["state_id"]).lower()
    first_splat_job = f"{primary_dataset}-splat-{state_slug}-001"
    models = bench_model_contracts(manifest)
    display_names = {"vggt": "VGGT", "colmap": "COLMAP", "glomap": "GLOMAP", "splatfacto": "Splatfacto"}
    model_rows = "\n".join(
        f"| `{display_names.get(item['model'], item['model'])}` | {item['role']} | `{item['artifact_class']}` |"
        for item in models
    )
    photo_lines = "\n".join(
        f"- `{item['dataset']}`: `{item.get('image_count', 0)}` images, QC passed `{item.get('qc_passed')}`"
        for item in photos
    ) or "- None linked yet"
    lidar_lines = "\n".join(
        f"- `{item['id']}`: `{item['device']}`, role `{item['role']}`"
        for item in lidar
    ) or "- None ingested yet"

    return f"""# Core Model Bench Plan: {manifest['name']}

Generated: {utc_now()}

## Inputs

- Package: `{package}`
- Target: `{manifest['target']}`
- State: `{manifest['state_id']}`
- Primary photo dataset: `{primary_dataset}`
- LiDAR role: `{manifest.get('policy', {}).get('lidar_role')}`

## Linked Photos

{photo_lines}

## LiDAR Reference

{lidar_lines}

## Bench Models

| Model | Role | Artifact class |
| --- | --- | --- |
{model_rows}

## Execution Contract

Each model writes into `benchmarks/MODEL/` and must produce `metrics.json` with
runtime, status, output paths, and failure reason if incomplete. Outputs remain
separate until `registration/register_report.json` scores or describes their
alignment.

## Suggested First Commands

```sh
# If a promoted local COLMAP sparse baseline exists, make the first paid GPU
# run a bounded Splatfacto inspection pass instead of a broad mesh/both job.
python3 photogrammetry/scripts/pgm.py cloud-plan --dataset {primary_dataset} --target splat
python3 photogrammetry/scripts/pgm.py job-package \\
  --dataset {primary_dataset} \\
  --target splat \\
  --name {first_splat_job} \\
  --evidence-package {manifest['name']} \\
  --sync-hetzner

# Future bench runners should write outputs under:
# {package}/benchmarks/vggt
# {package}/benchmarks/colmap
# {package}/benchmarks/glomap
# {package}/benchmarks/splatfacto
```

## Metrics To Record

- registered image count and percentage;
- camera pose coherence/manual visual inspection screenshot;
- sparse and dense point counts;
- rough alignment to LiDAR reference;
- runtime, GPU type, and peak disk use if available;
- failure reason if a model cannot complete.
"""


def cmd_bench_plan(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, manifest = require_package(config, args.package)
    plan_path = package / "benchmarks" / "bench_plan.md"
    markdown = bench_plan_markdown(package, manifest)
    plan_path.write_text(markdown, encoding="utf-8")
    contracts = {
        "schema_version": 1,
        "package": manifest["name"],
        "created_at": utc_now(),
        "models": bench_model_contracts(manifest),
        "metrics_policy": {
            "outputs_separate_until_registered": True,
            "lidar_role": manifest.get("policy", {}).get("lidar_role"),
        },
    }
    json_write(package / "benchmarks" / "bench_plan.json", contracts)
    manifest["status"]["bench_plan_written"] = True
    update_manifest(package, manifest)
    add_artifact(
        package,
        path=artifact_rel(package, plan_path),
        artifact_class="evidence",
        role="model_bench_plan",
        description="Core VGGT/COLMAP/GLOMAP/Splatfacto benchmark plan and output contract.",
    )
    add_artifact(
        package,
        path="benchmarks/bench_plan.json",
        artifact_class="evidence",
        role="model_bench_contract",
        description="Machine-readable benchmark output and metric contract.",
    )
    print(f"Wrote bench plan: {plan_path}")
    return 0


def read_model_metrics(package: Path, model: str) -> dict[str, Any]:
    metrics_path = package / "benchmarks" / model / "metrics.json"
    if not metrics_path.exists():
        return {"model": model, "status": "not_run", "metrics_path": artifact_rel(package, metrics_path)}
    metrics = json_read(metrics_path)
    metrics.setdefault("model", model)
    metrics.setdefault("status", "unknown")
    metrics["metrics_path"] = artifact_rel(package, metrics_path)
    return metrics


def cmd_register_report(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, manifest = require_package(config, args.package)
    models = [item["model"] for item in bench_model_contracts(manifest)]
    metrics = [read_model_metrics(package, model) for model in models]
    report = {
        "schema_version": 1,
        "package": manifest["name"],
        "target": manifest["target"],
        "state_id": manifest["state_id"],
        "created_at": utc_now(),
        "registration_policy": {
            "lidar_role": manifest.get("policy", {}).get("lidar_role"),
            "model_outputs_remain_separate": True,
            "merge_allowed": False,
        },
        "modalities": {
            "photos": linked_photo_datasets(manifest),
            "lidar": lidar_records(manifest),
        },
        "model_metrics": metrics,
        "alignment_summary": {
            "status": "pending",
            "message": "No model outputs have been aligned yet. This report records readiness and expected metrics.",
        },
        "acceptance_checks": {
            "photo_dataset_linked": bool(linked_photo_datasets(manifest)),
            "lidar_reference_available": bool(lidar_records(manifest)),
            "bench_plan_available": (package / "benchmarks" / "bench_plan.md").exists(),
            "all_model_outputs_scored": all(item.get("status") not in {"not_run", "failed"} for item in metrics),
        },
    }
    report_path = package / "registration" / "register_report.json"
    json_write(report_path, report)
    lines = [
        f"# Registration Report: {manifest['name']}",
        "",
        f"- State: `{manifest['state_id']}`",
        f"- Photos linked: `{len(linked_photo_datasets(manifest))}`",
        f"- LiDAR references: `{len(lidar_records(manifest))}`",
        "- Alignment status: `pending`",
        "",
        "## Model Status",
        "",
    ]
    for item in metrics:
        lines.append(f"- `{item['model']}`: `{item.get('status')}`")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Model outputs remain separate until alignment is scored.",
            f"- LiDAR role: `{manifest.get('policy', {}).get('lidar_role')}`",
        ]
    )
    md_path = package / "registration" / "register_report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    update_manifest(package, manifest)
    add_artifact(
        package,
        path=artifact_rel(package, report_path),
        artifact_class="inference",
        role="registration_readiness_report",
        description="Current model/LiDAR/photo readiness and registration policy.",
    )
    print(f"Wrote registration report: {report_path}")
    return 0


def remote_photo_link_script(remote_package: str, pgm_remote_root: str, datasets: list[dict[str, Any]]) -> str:
    lines = [
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(remote_package + '/raw/photos')}",
    ]
    for dataset in datasets:
        name = str(dataset["dataset"])
        validate_name(name, "Photogrammetry dataset name")
        remote_source = f"{pgm_remote_root}/datasets/{name}"
        remote_link = f"{remote_package}/raw/photos/{name}"
        lines.extend(
            [
                f"test -d {shlex.quote(remote_source)}",
                f"rm -rf {shlex.quote(remote_link)}",
                f"ln -s {shlex.quote(remote_source)} {shlex.quote(remote_link)}",
            ]
        )
    return "\n".join(lines) + "\n"


def cmd_sync_hetzner(args: argparse.Namespace, config: dict[str, Any]) -> int:
    package, manifest = require_package(config, args.package)
    host, _root, pgm_remote_root = require_hetzner(config)
    remote_package = remote_package_path(config, manifest["name"])
    datasets = linked_photo_datasets(manifest)
    if not datasets:
        raise UserError("No linked photogrammetry datasets found. Run link-photogrammetry first.")

    marker = {
        "schema_version": 1,
        "package": manifest["name"],
        "synced_at": utc_now(),
        "remote_package": remote_package,
        "photogrammetry_remote_root": pgm_remote_root,
        "linked_photo_datasets": datasets,
        "mode": "metadata_plus_remote_photo_symlinks",
    }
    marker_path = package / "manifests" / "hetzner_sync.json"
    mkdir_cmd = ["ssh", host, f"mkdir -p {shlex.quote(remote_package)}"]
    sync_cmd = [
        *rsync_base_args(config, args.dry_run),
        "--delete",
        "--exclude",
        "raw/photos/***",
        f"{package}/",
        f"{host}:{remote_package}/",
    ]
    link_script = remote_photo_link_script(remote_package, pgm_remote_root, datasets)
    link_cmd = ["ssh", host, "bash -s"]

    print(shell_join(mkdir_cmd))
    print(shell_join(sync_cmd))
    print(f"{shell_join(link_cmd)} <<'SH'")
    print(link_script.rstrip())
    print("SH")
    if args.dry_run:
        return 0

    json_write(marker_path, marker)
    manifest["status"]["hetzner_synced"] = True
    manifest["hetzner_sync"] = artifact_rel(package, marker_path)
    update_manifest(package, manifest)
    add_artifact(
        package,
        path=artifact_rel(package, marker_path),
        artifact_class="evidence",
        role="hetzner_sync_marker",
        description="Remote staging marker for the structured evidence package.",
    )

    subprocess.run(mkdir_cmd, check=True)
    subprocess.run(sync_cmd, check=True)
    proc = subprocess.run(link_cmd, input=link_script, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        raise UserError("Remote photo evidence symlink creation failed. Check that photogrammetry datasets are staged.")
    print(f"Synced evidence package to {host}:{remote_package}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="What We See structured evidence package CLI")
    parser.add_argument("--config", help="Path to evidence TOML config")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-package", help="Create an evidence package skeleton")
    init.add_argument("--name", required=True)
    init.add_argument("--target", required=True)
    init.add_argument("--state-id", required=True)
    init.add_argument("--overwrite", action="store_true", help="Rebuild package if it already exists")

    link = sub.add_parser("link-photogrammetry", help="Link a photogrammetry dataset as photo evidence")
    link.add_argument("--package", required=True)
    link.add_argument("--dataset", required=True)

    lidar = sub.add_parser("ingest-lidar", help="Ingest an iPhone LiDAR/reference geometry export")
    lidar.add_argument("--package", required=True)
    lidar.add_argument("--source", required=True)
    lidar.add_argument("--device", default="iphone-lidar")
    lidar.add_argument("--notes", default="")
    lidar.add_argument("--link", action="store_true", help="Symlink the LiDAR export instead of copying/hardlinking")

    session = sub.add_parser("write-session", help="Write capture-session metadata and notes")
    session.add_argument("--package", required=True)
    session.add_argument("--date", required=True)
    session.add_argument("--location", required=True)
    session.add_argument("--notes", help="Path to a markdown/text notes file")
    session.add_argument("--operator", default="")
    session.add_argument("--lighting", default="")
    session.add_argument("--fans", default="")
    session.add_argument("--grow-equipment", default="")
    session.add_argument("--humidity", default="")
    session.add_argument("--temperature", default="")

    bench = sub.add_parser("bench-plan", help="Write VGGT/COLMAP/GLOMAP/Splatfacto bench plan")
    bench.add_argument("--package", required=True)

    register = sub.add_parser("register-report", help="Write current registration readiness report")
    register.add_argument("--package", required=True)

    sync = sub.add_parser("sync-hetzner", help="Sync evidence package metadata to Hetzner and create remote photo symlinks")
    sync.add_argument("--package", required=True)
    sync.add_argument("--dry-run", action="store_true", help="Print commands only")

    return parser


def run(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.command == "init-package":
        return cmd_init_package(args, config)
    if args.command == "link-photogrammetry":
        return cmd_link_photogrammetry(args, config)
    if args.command == "ingest-lidar":
        return cmd_ingest_lidar(args, config)
    if args.command == "write-session":
        return cmd_write_session(args, config)
    if args.command == "bench-plan":
        return cmd_bench_plan(args, config)
    if args.command == "register-report":
        return cmd_register_report(args, config)
    if args.command == "sync-hetzner":
        return cmd_sync_hetzner(args, config)
    raise UserError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config, _config_path = load_config(args.config)
        return run(args, config)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
