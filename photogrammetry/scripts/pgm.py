#!/usr/bin/env python3
"""Local orchestration CLI for the What We See photogrammetry pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ in this project.
    tomllib = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_LOCAL_CONFIG = PROJECT_ROOT / "configs" / "pipeline.local.toml"
WORKING_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
ARCHIVAL_RAW_EXTENSIONS = {
    ".cr2",
    ".cr3",
    ".dng",
}
IMAGE_EXTENSIONS = WORKING_IMAGE_EXTENSIONS | ARCHIVAL_RAW_EXTENSIONS
DATASET_DIRS = [
    "raw",
    "working/images",
    "working/previews",
    "manifests",
    "reports",
    "colmap",
    "mesh",
    "splat",
    "logs",
    "cloud",
]
DEFAULT_CONFIG: dict[str, Any] = {
    "local": {
        "data_root": "~/whatwesee_photogrammetry_data",
        "preview_max_width": 1600,
        "blur_threshold": 80.0,
        "dark_mean_threshold": 25.0,
        "bright_mean_threshold": 235.0,
    },
    "hetzner": {
        "ssh_host": "",
        "remote_root": "/mnt/HC_Volume_000/whatwesee-photogrammetry",
        "rsync_extra_args": [],
    },
    "vast": {
        "image": "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel",
        "disk_gb": 256,
        "offer_query": "verified=true rentable=true reliability > 0.98 gpu_ram >= 48",
        "remote_workdir": "/workspace/whatwesee",
        "nerfstudio_version": "1.1.5",
        "gsplat_version": "1.4.0",
    },
    "retention": {
        "hetzner": "keep_everything",
        "vast": "sync_back_then_delete",
    },
}


class UserError(RuntimeError):
    """An expected CLI error with a clean message."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def human_bytes(num: int | float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


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
    env_path = os.environ.get("PGM_CONFIG")

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
        "PGM_DATA_ROOT": ("local", "data_root"),
        "PGM_HETZNER_HOST": ("hetzner", "ssh_host"),
        "PGM_HETZNER_ROOT": ("hetzner", "remote_root"),
        "PGM_VAST_IMAGE": ("vast", "image"),
    }
    for env_name, path in env_overrides.items():
        value = os.environ.get(env_name)
        if value:
            config[path[0]][path[1]] = value

    return config, selected


def data_root(config: dict[str, Any]) -> Path:
    return Path(str(config["local"]["data_root"])).expanduser().resolve()


def validate_dataset_name(name: str) -> None:
    if not name:
        raise UserError("Dataset name is required.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(char not in allowed for char in name):
        raise UserError("Dataset names may only contain letters, numbers, dot, dash, and underscore.")
    if name in {".", ".."}:
        raise UserError("Dataset name is invalid.")


def dataset_path(config: dict[str, Any], name: str) -> Path:
    validate_dataset_name(name)
    return data_root(config) / name


def ensure_dataset_dirs(path: Path) -> None:
    for rel in DATASET_DIRS:
        (path / rel).mkdir(parents=True, exist_ok=True)


def json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require_dataset(config: dict[str, Any], name: str) -> tuple[Path, dict[str, Any]]:
    path = dataset_path(config, name)
    meta_path = path / "manifests" / "dataset.json"
    if not meta_path.exists():
        raise UserError(f"Dataset is not initialized: {name}. Run init-dataset first.")
    return path, json_read(meta_path)


def tool_path(name: str) -> str | None:
    return shutil.which(name)


def tool_version(name: str, args: list[str] | None = None) -> dict[str, Any]:
    exe = tool_path(name)
    if not exe:
        return {"available": False, "path": None, "version": None}
    version_args = args if args is not None else ["--version"]
    try:
        proc = subprocess.run(
            [exe, *version_args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
    except Exception as exc:  # noqa: BLE001 - version probing should never fail the CLI.
        first_line = f"version probe failed: {exc}"
    return {"available": True, "path": exe, "version": first_line}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source.is_dir():
        raise UserError(f"Source path does not exist: {source}")
    images = [path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(images, key=lambda item: str(item.relative_to(source)).lower())


def relative_image_path(source: Path, image: Path) -> Path:
    if source.is_file():
        return Path(image.name)
    rel = image.relative_to(source)
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise UserError(f"Unsafe relative path discovered: {rel}")
    return rel


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    shutil.copy2(src, dst)


def hardlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def chunked(items: list[Path], size: int) -> list[list[Path]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def read_exiftool(paths: list[Path]) -> dict[Path, dict[str, Any]]:
    exe = tool_path("exiftool")
    if not exe or not paths:
        return {}
    result: dict[Path, dict[str, Any]] = {}
    for group in chunked(paths, 80):
        proc = subprocess.run(
            [exe, "-json", "-n", "-m", *[str(path) for path in group]],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            continue
        try:
            entries = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for entry in entries:
            source = entry.get("SourceFile")
            if source:
                result[Path(source).resolve()] = entry
    return result


def sips_dimensions(path: Path) -> tuple[int | None, int | None]:
    exe = tool_path("sips")
    if not exe:
        return None, None
    proc = subprocess.run(
        [exe, "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, None
    width: int | None = None
    height: int | None = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            value = line.split(":", 1)[1].strip()
            width = int(value) if value.isdigit() else None
        elif line.startswith("pixelHeight:"):
            value = line.split(":", 1)[1].strip()
            height = int(value) if value.isdigit() else None
    return width, height


def first_value(entry: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = entry.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_exif(entry: dict[str, Any], path: Path) -> dict[str, Any]:
    width = first_value(entry, ["ImageWidth", "ExifImageWidth"])
    height = first_value(entry, ["ImageHeight", "ExifImageHeight"])
    if width is None or height is None:
        fallback_width, fallback_height = sips_dimensions(path)
        width = width or fallback_width
        height = height or fallback_height

    normalized = {
        "camera_make": first_value(entry, ["Make"]),
        "camera_model": first_value(entry, ["Model"]),
        "lens_model": first_value(entry, ["LensModel", "LensID", "Lens"]),
        "focal_length": first_value(entry, ["FocalLength"]),
        "focal_length_35mm": first_value(entry, ["FocalLengthIn35mmFormat", "FocalLength35efl"]),
        "aperture": first_value(entry, ["Aperture", "FNumber"]),
        "exposure_time": first_value(entry, ["ExposureTime", "ShutterSpeed"]),
        "iso": first_value(entry, ["ISO"]),
        "created_at": first_value(entry, ["DateTimeOriginal", "CreateDate", "ModifyDate"]),
        "width": int(width) if isinstance(width, (int, float)) or str(width or "").isdigit() else None,
        "height": int(height) if isinstance(height, (int, float)) or str(height or "").isdigit() else None,
    }
    return normalized


def preview_path_for(dataset: Path, rel: Path) -> Path:
    return dataset / "working" / "previews" / rel.with_suffix(".jpg")


def generate_preview(src: Path, dst: Path, max_width: int) -> str | None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return None

    sips = tool_path("sips")
    if sips:
        proc = subprocess.run(
            [sips, "-s", "format", "jpeg", "-Z", str(max_width), str(src), "--out", str(dst)],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            return None

    ffmpeg = tool_path("ffmpeg")
    if ffmpeg:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-vf",
                f"scale={max_width}:{max_width}:force_original_aspect_ratio=decrease",
                str(dst),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            return None
        return (proc.stderr or proc.stdout or "ffmpeg preview generation failed").strip()

    return "no preview generator found; install sips or ffmpeg"


def convert_raw_file(src: Path, dst: Path, converter: str, output_format: str, quality: int) -> str | None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp")
    if tmp.exists():
        tmp.unlink()

    if converter == "sips":
        exe = tool_path("sips")
        if not exe:
            return "sips not found"
        if output_format == "jpeg":
            command = [exe, "-s", "format", "jpeg", "-s", "formatOptions", str(quality), str(src), "--out", str(tmp)]
        elif output_format == "tiff":
            command = [exe, "-s", "format", "tiff", str(src), "--out", str(tmp)]
        else:
            return f"unsupported output format for sips: {output_format}"
    elif converter == "dcraw_emu":
        exe = tool_path("dcraw_emu")
        if not exe:
            return "dcraw_emu not found"
        if output_format != "tiff":
            return "dcraw_emu currently supports TIFF output only in this pipeline"
        command = [exe, "-w", "-T", "-6", "-q", "3", "-o", "1", "-Z", str(tmp), str(src)]
    else:
        return f"unsupported RAW converter: {converter}"

    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        if tmp.exists():
            tmp.unlink()
        return (proc.stderr or proc.stdout or "RAW conversion failed").strip()

    tmp.replace(dst)
    return None


def camera_group_key(image: dict[str, Any]) -> str:
    parts = [
        image.get("camera_make") or "unknown_make",
        image.get("camera_model") or "unknown_model",
        image.get("lens_model") or "unknown_lens",
        str(image.get("focal_length") or "unknown_focal"),
        str(image.get("focal_length_35mm") or "unknown_35mm"),
    ]
    return " | ".join(parts)


def focal_groups(images: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for image in images:
        key = camera_group_key(image)
        group = groups.setdefault(
            key,
            {
                "camera_make": image.get("camera_make"),
                "camera_model": image.get("camera_model"),
                "lens_model": image.get("lens_model"),
                "focal_length": image.get("focal_length"),
                "focal_length_35mm": image.get("focal_length_35mm"),
                "count": 0,
            },
        )
        group["count"] += 1
    return groups


def parse_pgm(data: bytes) -> tuple[int, int, bytes]:
    index = 0

    def skip_ws_and_comments() -> None:
        nonlocal index
        while index < len(data):
            if data[index:index + 1] == b"#":
                while index < len(data) and data[index:index + 1] not in {b"\n", b"\r"}:
                    index += 1
            elif data[index:index + 1].isspace():
                index += 1
            else:
                break

    def next_token() -> bytes:
        nonlocal index
        skip_ws_and_comments()
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        return data[start:index]

    magic = next_token()
    if magic != b"P5":
        raise ValueError("not a binary PGM image")
    width = int(next_token())
    height = int(next_token())
    max_value = int(next_token())
    if max_value > 255:
        raise ValueError("unsupported PGM max value")
    if data[index:index + 2] == b"\r\n":
        index += 2
    elif index < len(data) and data[index:index + 1].isspace():
        index += 1
    pixels = data[index : index + width * height]
    if len(pixels) < width * height:
        raise ValueError("truncated PGM pixel data")
    return width, height, pixels


def image_metrics(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg:
        return None, "ffmpeg not found"
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            "scale=320:320:force_original_aspect_ratio=decrease,format=gray",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "pgm",
            "-",
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        return None, (proc.stderr.decode("utf-8", "replace") or "ffmpeg decode failed").strip()

    try:
        width, height, pixels = parse_pgm(proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report bad media cleanly.
        return None, str(exc)

    values = list(pixels)
    mean = sum(values) / len(values) if values else 0.0
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0

    blur_score: float | None = None
    if width >= 3 and height >= 3:
        laplacian: list[int] = []
        for y in range(1, height - 1):
            row = y * width
            for x in range(1, width - 1):
                center = pixels[row + x]
                lap = (
                    4 * center
                    - pixels[row + x - 1]
                    - pixels[row + x + 1]
                    - pixels[row - width + x]
                    - pixels[row + width + x]
                )
                laplacian.append(lap)
        if laplacian:
            lap_mean = sum(laplacian) / len(laplacian)
            blur_score = sum((value - lap_mean) ** 2 for value in laplacian) / len(laplacian)

    return {
        "width": width,
        "height": height,
        "mean_luma": round(mean, 3),
        "luma_stdev": round(stdev, 3),
        "blur_score": round(blur_score, 3) if blur_score is not None else None,
    }, None


def manifest_path(dataset: Path) -> Path:
    return dataset / "manifests" / "manifest.json"


def qc_report_path(dataset: Path) -> Path:
    return dataset / "reports" / "qc_report.json"


def load_manifest(dataset: Path) -> dict[str, Any]:
    path = manifest_path(dataset)
    if not path.exists():
        raise UserError("Manifest not found. Run ingest first.")
    return json_read(path)


def load_qc_report(dataset: Path) -> dict[str, Any]:
    path = qc_report_path(dataset)
    if not path.exists():
        raise UserError("QC report not found. Run qc first.")
    return json_read(path)


def cmd_init_dataset(args: argparse.Namespace, config: dict[str, Any]) -> int:
    validate_dataset_name(args.name)
    if args.type not in {"object", "space", "mixed"}:
        raise UserError("--type must be object, space, or mixed")

    path = dataset_path(config, args.name)
    ensure_dataset_dirs(path)
    meta_path = path / "manifests" / "dataset.json"
    if meta_path.exists():
        meta = json_read(meta_path)
        meta["updated_at"] = utc_now()
        meta["dataset_type"] = args.type
    else:
        meta = {
            "name": args.name,
            "dataset_type": args.type,
            "created_at": utc_now(),
            "data_root": str(data_root(config)),
            "pipeline_version": 1,
        }
    json_write(meta_path, meta)
    print(f"Initialized dataset: {path}")
    return 0


def cmd_ingest(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    source = Path(args.source).expanduser().resolve()
    images = find_images(source)
    if not images:
        raise UserError(f"No supported image files found in {source}")

    copied_paths: list[Path] = []
    working_source_paths: list[Path] = []
    records: list[dict[str, Any]] = []
    raw_archive_records: list[dict[str, Any]] = []
    preview_warnings: list[dict[str, str]] = []
    max_width = int(config["local"]["preview_max_width"])

    for src in images:
        rel = relative_image_path(source, src)
        raw_dst = dataset / "raw" / rel
        copy_file(src, raw_dst)
        copied_paths.append(raw_dst.resolve())

        if raw_dst.suffix.lower() in WORKING_IMAGE_EXTENSIONS:
            working_dst = dataset / "working" / "images" / rel
            hardlink_or_copy(raw_dst, working_dst)
            working_source_paths.append(raw_dst.resolve())
            preview_dst = preview_path_for(dataset, rel)
            warning = generate_preview(working_dst, preview_dst, max_width)
            if warning:
                preview_warnings.append({"image": rel.as_posix(), "warning": warning})

    exif = read_exiftool(copied_paths)
    raw_total = 0
    working_total = 0
    raw_sidecars: dict[str, str] = {}

    for raw_path in copied_paths:
        rel = raw_path.relative_to(dataset / "raw")
        checksum = sha256_file(raw_path)
        stat = raw_path.stat()
        raw_total += stat.st_size
        normalized = normalize_exif(exif.get(raw_path.resolve(), {}), raw_path)
        if raw_path.suffix.lower() in ARCHIVAL_RAW_EXTENSIONS:
            archive_record = {
                "id": checksum[:16],
                "relative_path": rel.as_posix(),
                "raw_path": f"raw/{rel.as_posix()}",
                "sha256": checksum,
                "bytes": stat.st_size,
                "extension": raw_path.suffix.lower(),
                **normalized,
            }
            raw_archive_records.append(archive_record)
            raw_sidecars[rel.with_suffix("").as_posix().lower()] = archive_record["raw_path"]

    for raw_path in working_source_paths:
        rel = raw_path.relative_to(dataset / "raw")
        working_path = dataset / "working" / "images" / rel
        checksum = sha256_file(raw_path)
        stat = raw_path.stat()
        if working_path.exists():
            working_total += working_path.stat().st_size
        normalized = normalize_exif(exif.get(raw_path.resolve(), {}), raw_path)
        record = {
            "id": checksum[:16],
            "relative_path": rel.as_posix(),
            "raw_path": f"raw/{rel.as_posix()}",
            "working_path": f"working/images/{rel.as_posix()}",
            "preview_path": f"working/previews/{rel.with_suffix('.jpg').as_posix()}",
            "raw_sidecar_path": raw_sidecars.get(rel.with_suffix("").as_posix().lower()),
            "sha256": checksum,
            "bytes": stat.st_size,
            "extension": raw_path.suffix.lower(),
            **normalized,
        }
        records.append(record)

    manifest = {
        "schema_version": 1,
        "dataset": meta["name"],
        "dataset_type": meta["dataset_type"],
        "created_at": utc_now(),
        "source": str(source),
        "image_count": len(records),
        "raw_archive_count": len(raw_archive_records),
        "raw_total_bytes": raw_total,
        "working_total_bytes": working_total,
        "focal_groups": focal_groups(records),
        "preview_warnings": preview_warnings,
        "tools": {
            "python": sys.version.split()[0],
            "exiftool": tool_version("exiftool", ["-ver"]),
            "ffmpeg": tool_version("ffmpeg", ["-version"]),
            "sips": tool_version("sips", ["--version"]),
        },
        "raw_archive": raw_archive_records,
        "images": records,
    }
    json_write(manifest_path(dataset), manifest)
    print(f"Ingested {len(records)} working images and {len(raw_archive_records)} RAW archives into {dataset}")
    print(f"Raw size: {human_bytes(raw_total)}")
    if preview_warnings:
        print(f"Preview warnings: {len(preview_warnings)}")
    return 0


def cmd_convert_raw(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.quality < 1 or args.quality > 100:
        raise UserError("--quality must be between 1 and 100")
    if args.converter == "dcraw_emu" and args.format != "tiff":
        raise UserError("dcraw_emu conversion currently requires --format tiff")

    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    raw_archive = manifest.get("raw_archive", [])
    if not raw_archive:
        raise UserError("Manifest contains no archived RAW files. Run ingest on a RAW source first.")

    existing_bases = {
        Path(image["relative_path"]).with_suffix("").as_posix().lower()
        for image in manifest.get("images", [])
    }
    selected = []
    for record in raw_archive:
        base = Path(record["relative_path"]).with_suffix("").as_posix().lower()
        if base in existing_bases and not args.include_with_sidecars:
            continue
        selected.append(record)

    if args.limit:
        selected = selected[: args.limit]

    if not selected:
        print("No RAW files need conversion. Use --include-with-sidecars to convert RAWs that already have working JPEGs.")
        return 0

    extension = ".jpg" if args.format == "jpeg" else ".tif"
    print(f"Converting {len(selected)} RAW files to {args.format.upper()} with {args.converter}")
    if args.dry_run:
        for record in selected:
            rel = Path(record["relative_path"]).with_suffix(extension)
            print(f"{record['raw_path']} -> working/images/{rel.as_posix()}")
        return 0

    max_width = int(config["local"]["preview_max_width"])
    converted_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    preview_warnings = list(manifest.get("preview_warnings", []))
    exif_by_path = read_exiftool([(dataset / record["raw_path"]).resolve() for record in selected])

    for index, record in enumerate(selected, start=1):
        raw_src = dataset / record["raw_path"]
        rel = Path(record["relative_path"]).with_suffix(extension)
        working_dst = dataset / "working" / "images" / rel

        if working_dst.exists() and not args.overwrite:
            print(f"[{index}/{len(selected)}] exists, skipping {rel.as_posix()}")
        else:
            print(f"[{index}/{len(selected)}] converting {record['relative_path']} -> {rel.as_posix()}")
            error = convert_raw_file(raw_src, working_dst, args.converter, args.format, args.quality)
            if error:
                failures.append({"raw_path": record["raw_path"], "message": error})
                print(f"  failed: {error}", file=sys.stderr)
                continue

        preview_dst = preview_path_for(dataset, rel)
        warning = generate_preview(working_dst, preview_dst, max_width)
        if warning:
            preview_warnings.append({"image": rel.as_posix(), "warning": warning})

        checksum = sha256_file(working_dst)
        stat = working_dst.stat()
        normalized = normalize_exif(exif_by_path.get(raw_src.resolve(), {}), raw_src)
        converted_records.append(
            {
                "id": checksum[:16],
                "relative_path": rel.as_posix(),
                "raw_path": record["raw_path"],
                "working_path": f"working/images/{rel.as_posix()}",
                "preview_path": f"working/previews/{rel.with_suffix('.jpg').as_posix()}",
                "raw_sidecar_path": record["raw_path"],
                "generated_from_raw_path": record["raw_path"],
                "sha256": checksum,
                "bytes": stat.st_size,
                "extension": extension,
                "source_extension": record.get("extension"),
                "conversion": {
                    "converter": args.converter,
                    "converted_at": utc_now(),
                    "output_format": args.format,
                    "jpeg_quality": args.quality if args.format == "jpeg" else None,
                },
                **normalized,
            }
        )

    if failures:
        json_write(dataset / "reports" / "raw_conversion_failures.json", {"created_at": utc_now(), "failures": failures})

    existing_paths = {image["relative_path"]: image for image in manifest.get("images", [])}
    for record in converted_records:
        existing_paths[record["relative_path"]] = record
    images = list(existing_paths.values())
    images.sort(key=lambda image: image["relative_path"])

    manifest["updated_at"] = utc_now()
    manifest["image_count"] = len(images)
    manifest["working_total_bytes"] = sum((dataset / image["working_path"]).stat().st_size for image in images if (dataset / image["working_path"]).exists())
    manifest["focal_groups"] = focal_groups(images)
    manifest["preview_warnings"] = preview_warnings
    manifest["images"] = images
    manifest["raw_conversion"] = {
        "last_run_at": utc_now(),
        "converter": args.converter,
        "output_format": args.format,
        "jpeg_quality": args.quality if args.format == "jpeg" else None,
        "selected_count": len(selected),
        "converted_count": len(converted_records),
        "failure_count": len(failures),
    }
    json_write(manifest_path(dataset), manifest)

    if failures:
        raise UserError(f"RAW conversion finished with {len(failures)} failures. See reports/raw_conversion_failures.json.")

    print(f"Converted {len(converted_records)} {args.format.upper()} working images into {dataset / 'working' / 'images'}")
    print(f"Working size: {human_bytes(manifest['working_total_bytes'])}")
    return 0


def cmd_normalize_working(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.quality < 1 or args.quality > 100:
        raise UserError("--quality must be between 1 and 100")

    dataset, _meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    source_extensions = {".heic", ".heif"}
    selected = [image for image in manifest.get("images", []) if image.get("extension") in source_extensions]

    if args.limit:
        selected = selected[: args.limit]

    if not selected:
        print("No HEIC/HEIF working images need normalization.")
        return 0

    print(f"Normalizing {len(selected)} HEIC/HEIF working images to JPEG quality {args.quality}")
    if args.dry_run:
        for image in selected:
            rel = Path(image["relative_path"]).with_suffix(".jpg")
            print(f"{image['working_path']} -> working/images/{rel.as_posix()}")
        return 0

    max_width = int(config["local"]["preview_max_width"])
    normalized_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    preview_warnings = list(manifest.get("preview_warnings", []))
    source_paths = [(dataset / image["raw_path"]).resolve() for image in selected]
    exif_by_path = read_exiftool(source_paths)

    for index, image in enumerate(selected, start=1):
        source = dataset / image["working_path"]
        if not source.exists():
            source = dataset / image["raw_path"]
        rel = Path(image["relative_path"]).with_suffix(".jpg")
        working_dst = dataset / "working" / "images" / rel

        if working_dst.exists() and not args.overwrite:
            print(f"[{index}/{len(selected)}] exists, skipping {rel.as_posix()}")
        else:
            print(f"[{index}/{len(selected)}] converting {image['relative_path']} -> {rel.as_posix()}")
            error = convert_raw_file(source, working_dst, "sips", "jpeg", args.quality)
            if error:
                failures.append({"source_path": image["working_path"], "message": error})
                print(f"  failed: {error}", file=sys.stderr)
                continue

        preview_dst = preview_path_for(dataset, rel)
        warning = generate_preview(working_dst, preview_dst, max_width)
        if warning:
            preview_warnings.append({"image": rel.as_posix(), "warning": warning})

        raw_source = dataset / image["raw_path"]
        checksum = sha256_file(working_dst)
        stat = working_dst.stat()
        normalized = normalize_exif(exif_by_path.get(raw_source.resolve(), {}), raw_source)
        normalized_records.append(
            {
                "id": checksum[:16],
                "relative_path": rel.as_posix(),
                "raw_path": image["raw_path"],
                "working_path": f"working/images/{rel.as_posix()}",
                "preview_path": f"working/previews/{rel.with_suffix('.jpg').as_posix()}",
                "raw_sidecar_path": image.get("raw_sidecar_path"),
                "generated_from_working_path": image["working_path"],
                "sha256": checksum,
                "bytes": stat.st_size,
                "extension": ".jpg",
                "source_extension": image.get("extension"),
                "conversion": {
                    "converter": "sips",
                    "converted_at": utc_now(),
                    "output_format": "jpeg",
                    "jpeg_quality": args.quality,
                },
                **normalized,
            }
        )

        if not args.keep_source_working:
            old_working = dataset / image["working_path"]
            if old_working.exists() and old_working.resolve() != working_dst.resolve():
                old_working.unlink()

    if failures:
        json_write(dataset / "reports" / "working_normalization_failures.json", {"created_at": utc_now(), "failures": failures})

    existing_paths = {image["relative_path"]: image for image in manifest.get("images", [])}
    for image in selected:
        existing_paths.pop(image["relative_path"], None)
    for record in normalized_records:
        existing_paths[record["relative_path"]] = record
    images = list(existing_paths.values())
    images.sort(key=lambda item: item["relative_path"])

    manifest["updated_at"] = utc_now()
    manifest["image_count"] = len(images)
    manifest["working_total_bytes"] = sum(
        (dataset / image["working_path"]).stat().st_size
        for image in images
        if (dataset / image["working_path"]).exists()
    )
    manifest["focal_groups"] = focal_groups(images)
    manifest["preview_warnings"] = preview_warnings
    manifest["images"] = images
    manifest["working_normalization"] = {
        "last_run_at": utc_now(),
        "source_extensions": sorted(source_extensions),
        "output_format": "jpeg",
        "jpeg_quality": args.quality,
        "selected_count": len(selected),
        "converted_count": len(normalized_records),
        "failure_count": len(failures),
        "kept_source_working": args.keep_source_working,
    }
    json_write(manifest_path(dataset), manifest)

    if failures:
        raise UserError(f"Working image normalization finished with {len(failures)} failures. See reports/working_normalization_failures.json.")

    print(f"Normalized {len(normalized_records)} JPEG working images into {dataset / 'working' / 'images'}")
    print(f"Working size: {human_bytes(manifest['working_total_bytes'])}")
    return 0


def image_warning_map(qc_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    warnings: dict[str, list[dict[str, Any]]] = {}
    for warning in qc_report.get("warnings", []):
        image = warning.get("image")
        if image:
            warnings.setdefault(image, []).append(warning)
    return warnings


def clean_image_record(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(record))


def prefixed_relative_path(source_dataset: str, rel: str) -> str:
    prefix = "".join(char if char.isalnum() or char in "._-" else "_" for char in source_dataset)
    name = Path(rel).name
    return f"{prefix}__{name}"


def is_ultrawide_image(image: dict[str, Any]) -> bool:
    lens = str(image.get("lens_model") or "").lower()
    focal = image.get("focal_length")
    try:
        focal_value = float(focal)
    except (TypeError, ValueError):
        focal_value = None
    return "1.54mm" in lens or "ultra" in lens or (focal_value is not None and focal_value <= 2.0)


def merge_exclusion_reason(profile: str, image: dict[str, Any], warnings: list[dict[str, Any]]) -> str | None:
    if profile == "all":
        return None
    if profile in {"clean", "no-ultrawide"} and warnings:
        codes = ", ".join(sorted({str(warning.get("code")) for warning in warnings}))
        return f"qc_warning:{codes}"
    if profile == "no-ultrawide" and is_ultrawide_image(image):
        return "iphone_ultrawide"
    return None


def cmd_merge_candidate(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.profile not in {"all", "clean", "no-ultrawide"}:
        raise UserError("--profile must be all, clean, or no-ultrawide")
    if len(args.source) < 2:
        raise UserError("At least two --source datasets are required.")

    validate_dataset_name(args.name)
    target = dataset_path(config, args.name)
    if target.exists() and not args.overwrite:
        raise UserError(f"Target dataset already exists: {target}. Use --overwrite to rebuild it.")
    if target.exists() and args.overwrite:
        shutil.rmtree(target)
    ensure_dataset_dirs(target)

    source_payloads: list[tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, list[dict[str, Any]]]]] = []
    for source_name in args.source:
        source_path, source_meta = require_dataset(config, source_name)
        source_manifest = load_manifest(source_path)
        source_qc = load_qc_report(source_path)
        if not source_qc.get("passed"):
            raise UserError(f"Source dataset QC has not passed: {source_name}")
        source_payloads.append((source_name, source_path, source_manifest, source_qc, image_warning_map(source_qc)))

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    working_total = 0
    preview_warnings: list[dict[str, str]] = []
    max_width = int(config["local"]["preview_max_width"])

    for source_name, source_path, source_manifest, _source_qc, warnings_by_image in source_payloads:
        for image in sorted(source_manifest.get("images", []), key=lambda item: item["relative_path"]):
            warnings = warnings_by_image.get(image["relative_path"], [])
            reason = merge_exclusion_reason(args.profile, image, warnings)
            if reason:
                excluded.append(
                    {
                        "source_dataset": source_name,
                        "relative_path": image["relative_path"],
                        "reason": reason,
                    }
                )
                continue

            src = source_path / image["working_path"]
            if not src.exists():
                raise UserError(f"Missing source working image: {src}")

            rel = Path(prefixed_relative_path(source_name, image["relative_path"]))
            dst = target / "working" / "images" / rel
            hardlink_or_copy(src, dst)
            working_total += dst.stat().st_size

            source_preview = source_path / image.get("preview_path", "")
            preview_dst = preview_path_for(target, rel)
            if source_preview.exists():
                hardlink_or_copy(source_preview, preview_dst)
            else:
                warning = generate_preview(dst, preview_dst, max_width)
                if warning:
                    preview_warnings.append({"image": rel.as_posix(), "warning": warning})

            record = clean_image_record(image)
            record["relative_path"] = rel.as_posix()
            record["working_path"] = f"working/images/{rel.as_posix()}"
            record["preview_path"] = f"working/previews/{rel.with_suffix('.jpg').as_posix()}"
            record["source_dataset"] = source_name
            record["source_relative_path"] = image["relative_path"]
            record["source_working_path"] = image["working_path"]
            record["source_qc_warnings"] = warnings
            included.append(record)

    if not included:
        raise UserError("Merge candidate would contain no images.")

    included.sort(key=lambda item: (item["source_dataset"], item["source_relative_path"]))
    meta = {
        "name": args.name,
        "dataset_type": "mixed",
        "created_at": utc_now(),
        "data_root": str(data_root(config)),
        "pipeline_version": 1,
        "merge_candidate": {
            "profile": args.profile,
            "source_datasets": args.source,
        },
    }
    json_write(target / "manifests" / "dataset.json", meta)

    manifest = {
        "schema_version": 1,
        "dataset": args.name,
        "dataset_type": "mixed",
        "created_at": utc_now(),
        "source": "merge_candidate",
        "image_count": len(included),
        "raw_archive_count": 0,
        "raw_total_bytes": working_total,
        "working_total_bytes": working_total,
        "focal_groups": focal_groups(included),
        "preview_warnings": preview_warnings,
        "tools": {
            "python": sys.version.split()[0],
            "ffmpeg": tool_version("ffmpeg", ["-version"]),
            "sips": tool_version("sips", ["--version"]),
        },
        "raw_archive": [],
        "images": included,
        "merge_candidate": {
            "profile": args.profile,
            "source_datasets": args.source,
            "included_count": len(included),
            "excluded_count": len(excluded),
        },
    }
    json_write(manifest_path(target), manifest)

    report = {
        "schema_version": 1,
        "dataset": args.name,
        "created_at": utc_now(),
        "profile": args.profile,
        "source_datasets": args.source,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "included_by_source": {},
        "excluded_by_reason": {},
        "excluded": excluded,
    }
    for record in included:
        report["included_by_source"][record["source_dataset"]] = report["included_by_source"].get(record["source_dataset"], 0) + 1
    for record in excluded:
        report["excluded_by_reason"][record["reason"]] = report["excluded_by_reason"].get(record["reason"], 0) + 1
    json_write(target / "reports" / "merge_selection_report.json", report)

    markdown_lines = [
        f"# Merge Candidate: {args.name}",
        "",
        f"- Profile: `{args.profile}`",
        f"- Sources: `{', '.join(args.source)}`",
        f"- Included images: `{len(included)}`",
        f"- Excluded images: `{len(excluded)}`",
        f"- Working size: `{human_bytes(working_total)}`",
        "",
        "## Included By Source",
        "",
    ]
    for source_name, count in sorted(report["included_by_source"].items()):
        markdown_lines.append(f"- `{source_name}`: `{count}`")
    markdown_lines.extend(["", "## Excluded By Reason", ""])
    if report["excluded_by_reason"]:
        for reason, count in sorted(report["excluded_by_reason"].items()):
            markdown_lines.append(f"- `{reason}`: `{count}`")
    else:
        markdown_lines.append("- None")
    (target / "reports" / "merge_selection_report.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    print(f"Created merge candidate: {target}")
    print(f"Included {len(included)} images, excluded {len(excluded)}")
    print(f"Working size: {human_bytes(working_total)}")
    return 0


def recommended_min_images(dataset_type: str) -> int:
    return {"object": 40, "space": 80, "mixed": 60}.get(dataset_type, 60)


def cmd_qc(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    images = manifest["images"]
    warnings: list[dict[str, Any]] = []
    fatal: list[dict[str, Any]] = []
    metrics_by_image: dict[str, Any] = {}

    if not images:
        fatal.append(
            {
                "code": "no_working_images",
                "message": "Dataset contains no JPEG/TIFF/PNG/HEIC working images. RAW-only captures are archived but not used for COLMAP/Nerfstudio.",
            }
        )

    min_images = recommended_min_images(meta["dataset_type"])
    if len(images) < min_images:
        warnings.append(
            {
                "code": "low_image_count",
                "message": f"{len(images)} images found; recommended minimum for {meta['dataset_type']} is {min_images}.",
            }
        )

    by_checksum: dict[str, list[str]] = {}
    for image in images:
        by_checksum.setdefault(image["sha256"], []).append(image["relative_path"])
        if not image.get("camera_model") or not image.get("focal_length"):
            warnings.append(
                {
                    "code": "missing_exif",
                    "image": image["relative_path"],
                    "message": "Camera model or focal length is missing.",
                }
            )
        if not image.get("width") or not image.get("height"):
            fatal.append(
                {
                    "code": "missing_dimensions",
                    "image": image["relative_path"],
                    "message": "Image dimensions could not be read.",
                }
            )
        if image.get("extension") in {".heic", ".heif"}:
            fatal.append(
                {
                    "code": "unnormalized_heic",
                    "image": image["relative_path"],
                    "message": "HEIC/HEIF is archived but should be converted with normalize-working before cloud reconstruction.",
                }
            )

    for checksum, rels in by_checksum.items():
        if len(rels) > 1:
            warnings.append(
                {
                    "code": "duplicate_image",
                    "sha256": checksum,
                    "images": rels,
                    "message": f"{len(rels)} identical files share one checksum.",
                }
            )

    ffmpeg_available = tool_path("ffmpeg") is not None
    if not ffmpeg_available:
        warnings.append({"code": "metrics_unavailable", "message": "ffmpeg not found; blur/exposure metrics skipped."})
    else:
        blur_threshold = float(config["local"]["blur_threshold"])
        dark_threshold = float(config["local"]["dark_mean_threshold"])
        bright_threshold = float(config["local"]["bright_mean_threshold"])

        for image in images:
            rel = image["relative_path"]
            path = dataset / image["working_path"]
            metrics, error = image_metrics(path)
            if error:
                fatal.append({"code": "decode_failed", "image": rel, "message": error})
                continue
            assert metrics is not None
            metrics_by_image[rel] = metrics
            blur_score = metrics.get("blur_score")
            mean_luma = float(metrics["mean_luma"])
            if blur_score is not None and blur_score < blur_threshold:
                warnings.append(
                    {
                        "code": "possibly_blurry",
                        "image": rel,
                        "blur_score": blur_score,
                        "threshold": blur_threshold,
                        "message": "Low Laplacian variance suggests possible blur.",
                    }
                )
            if mean_luma < dark_threshold:
                warnings.append(
                    {
                        "code": "possibly_underexposed",
                        "image": rel,
                        "mean_luma": mean_luma,
                        "threshold": dark_threshold,
                        "message": "Mean luma is very low.",
                    }
                )
            if mean_luma > bright_threshold:
                warnings.append(
                    {
                        "code": "possibly_overexposed",
                        "image": rel,
                        "mean_luma": mean_luma,
                        "threshold": bright_threshold,
                        "message": "Mean luma is very high.",
                    }
                )

    report = {
        "schema_version": 1,
        "dataset": meta["name"],
        "dataset_type": meta["dataset_type"],
        "created_at": utc_now(),
        "passed": not fatal,
        "summary": {
            "image_count": len(images),
            "raw_archive_count": len(manifest.get("raw_archive", [])),
            "warning_count": len(warnings),
            "fatal_count": len(fatal),
            "duplicate_group_count": sum(1 for rels in by_checksum.values() if len(rels) > 1),
            "missing_exif_count": sum(1 for item in warnings if item["code"] == "missing_exif"),
        },
        "warnings": warnings,
        "fatal": fatal,
        "metrics": metrics_by_image,
    }
    json_write(qc_report_path(dataset), report)
    status = "passed" if report["passed"] else "failed"
    print(f"QC {status}: {len(warnings)} warnings, {len(fatal)} fatal issues")
    return 0 if report["passed"] else 2


def shell_join(args: list[str]) -> str:
    return shlex.join([str(arg) for arg in args])


def remote_dataset_path(config: dict[str, Any], dataset_name: str) -> str:
    root = str(config["hetzner"]["remote_root"]).rstrip("/")
    return f"{root}/datasets/{dataset_name}"


def remote_pipeline_path(config: dict[str, Any]) -> str:
    root = str(config["hetzner"]["remote_root"]).rstrip("/")
    return f"{root}/pipeline/remote"


def remote_job_path(config: dict[str, Any], job_id: str) -> str:
    root = str(config["hetzner"]["remote_root"]).rstrip("/")
    return f"{root}/jobs/{job_id}"


def require_hetzner(config: dict[str, Any]) -> tuple[str, str]:
    host = str(config["hetzner"].get("ssh_host") or "").strip()
    root = str(config["hetzner"].get("remote_root") or "").strip()
    if not host:
        raise UserError("Hetzner ssh_host is not configured. Set it in pipeline.local.toml or PGM_HETZNER_HOST.")
    if not root:
        raise UserError("Hetzner remote_root is not configured.")
    return host, root


def rsync_base_args(config: dict[str, Any], dry_run: bool = False) -> list[str]:
    args = ["rsync", "-azP"]
    if dry_run:
        args.append("--dry-run")
    extra = config["hetzner"].get("rsync_extra_args") or []
    if not isinstance(extra, list):
        raise UserError("hetzner.rsync_extra_args must be a list.")
    args.extend(str(item) for item in extra)
    return args


def cmd_sync_hetzner(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    host, _root = require_hetzner(config)
    remote_dataset = remote_dataset_path(config, meta["name"])
    remote_pipeline = remote_pipeline_path(config)

    mkdir_cmd = ["ssh", host, f"mkdir -p {shlex.quote(remote_dataset)} {shlex.quote(remote_pipeline)}"]
    dataset_cmd = [*rsync_base_args(config, args.dry_run)]
    if args.working_only:
        dataset_cmd.extend(
            [
                "--delete",
                "--exclude",
                "/raw/",
                "--include",
                "*/",
                "--include",
                "/working/***",
                "--include",
                "/manifests/***",
                "--include",
                "/reports/***",
                "--include",
                "/colmap/***",
                "--include",
                "/cloud/***",
                "--include",
                "/logs/***",
                "--exclude",
                "*",
            ]
        )
    dataset_cmd.extend([f"{dataset}/", f"{host}:{remote_dataset}/"])
    scripts_cmd = [
        *rsync_base_args(config, args.dry_run),
        f"{PROJECT_ROOT / 'scripts' / 'remote'}/",
        f"{host}:{remote_pipeline}/",
    ]

    print(shell_join(mkdir_cmd))
    print(shell_join(dataset_cmd))
    print(shell_join(scripts_cmd))
    if args.dry_run:
        return 0

    subprocess.run(mkdir_cmd, check=True)
    subprocess.run(dataset_cmd, check=True)
    marker = {
        "dataset": meta["name"],
        "synced_at": utc_now(),
        "image_count": manifest["image_count"],
        "working_only": args.working_only,
        "local_dataset": str(dataset),
        "remote_dataset": remote_dataset,
        "remote_pipeline": remote_pipeline,
    }
    json_write(dataset / "cloud" / "hetzner_sync.json", marker)
    marker_cmd = [
        *rsync_base_args(config, False),
        str(dataset / "cloud" / "hetzner_sync.json"),
        f"{host}:{remote_dataset}/cloud/hetzner_sync.json",
    ]
    subprocess.run(marker_cmd, check=True)
    subprocess.run(scripts_cmd, check=True)
    print(f"Synced dataset to {host}:{remote_dataset}")
    return 0


def colmap_model_complete(path: Path) -> bool:
    return all((path / name).exists() for name in ("cameras.bin", "images.bin", "points3D.bin"))


def promoted_colmap_model(dataset: Path) -> Path:
    return dataset / "colmap" / "sparse" / "0"


def promoted_colmap_report_path(dataset: Path) -> Path:
    return dataset / "reports" / "promoted_colmap.json"


def load_benchmark_report(run_dir: Path) -> dict[str, Any]:
    report_path = run_dir / "report.json"
    if not report_path.exists():
        return {}
    return json_read(report_path)


def select_colmap_model_for_promotion(run_dir: Path, mapper: str, model_id: str) -> tuple[Path, dict[str, Any]]:
    report = load_benchmark_report(run_dir)
    if mapper == "best":
        best = report.get("best_model") or {}
        best_path_value = str(best.get("path") or "")
        best_path = Path(best_path_value) if best_path_value else None
        if best_path and colmap_model_complete(best_path):
            return best_path, best
        for fallback_mapper in ("global", "incremental"):
            candidate = run_dir / f"sparse_{fallback_mapper}" / model_id
            if colmap_model_complete(candidate):
                model_record = next(
                    (
                        model
                        for model in report.get("models", [])
                        if model.get("mapper") == fallback_mapper and str(model.get("model_id")) == model_id
                    ),
                    {"mapper": fallback_mapper, "model_id": model_id, "path": str(candidate)},
                )
                return candidate, model_record
        raise UserError(f"No complete COLMAP model found under {run_dir}")

    candidate = run_dir / f"sparse_{mapper}" / model_id
    if not colmap_model_complete(candidate):
        raise UserError(f"COLMAP model is incomplete or missing: {candidate}")
    model_record = next(
        (
            model
            for model in report.get("models", [])
            if model.get("mapper") == mapper and str(model.get("model_id")) == model_id
        ),
        {"mapper": mapper, "model_id": model_id, "path": str(candidate)},
    )
    return candidate, model_record


def promoted_colmap_markdown(report: dict[str, Any]) -> str:
    metrics = report.get("metrics") or {}
    registration = report.get("registration") or {}
    lines = [
        "# Promoted COLMAP Sparse Model",
        "",
        f"- Dataset: `{report['dataset']}`",
        f"- Benchmark run: `{report['bench_run']}`",
        f"- Mapper: `{report['mapper']}`",
        f"- Model id: `{report['model_id']}`",
        f"- Promoted at: `{report['promoted_at']}`",
        f"- Canonical sparse model: `{report['target_model_path']}`",
        f"- Database: `{report.get('target_database_path') or 'not copied'}`",
        f"- Sparse PLY: `{report.get('target_ply_path') or 'not copied'}`",
        "",
        "## Metrics",
        "",
        f"- Registered images: `{metrics.get('registered_images', 'unknown')}`",
        f"- Points: `{metrics.get('points', 'unknown')}`",
        f"- Mean reprojection error px: `{metrics.get('mean_reprojection_error_px', 'unknown')}`",
        "",
    ]
    by_source = registration.get("by_source") or {}
    if by_source:
        lines.extend(["## Source Registration", "", "| Source | Registered | Missing |", "| --- | ---: | ---: |"])
        for source, counts in sorted(by_source.items()):
            lines.append(
                f"| {source} | {counts.get('registered', 0)}/{counts.get('selected', 0)} | {counts.get('missing', 0)} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Use",
            "",
            "This is the current promoted local sparse reconstruction. GPU job packages should stage it to Hetzner and reuse it for Splatfacto instead of rerunning sparse COLMAP unless a run intentionally requests a new sparse pass.",
        ]
    )
    return "\n".join(lines) + "\n"


def cmd_promote_colmap(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    run_dir = dataset / "benchmarks" / args.bench_run
    if not run_dir.exists():
        raise UserError(f"Benchmark run not found: {run_dir}")

    source_model, model_record = select_colmap_model_for_promotion(run_dir, args.mapper, args.model_id)
    target_model = promoted_colmap_model(dataset)
    colmap_dir = dataset / "colmap"
    source_database = run_dir / "database.db"
    target_database_candidate = colmap_dir / "database.db" if source_database.exists() else None
    source_ply_value = model_record.get("exports", {}).get("ply") if isinstance(model_record.get("exports"), dict) else None
    source_ply = Path(str(source_ply_value)) if source_ply_value else run_dir / "exports" / f"sparse_{model_record.get('mapper', args.mapper)}_{model_record.get('model_id', args.model_id)}.ply"
    target_ply_candidate = colmap_dir / "sparse.ply" if source_ply.exists() else None
    if target_model.exists() and not args.overwrite:
        raise UserError(f"Promoted COLMAP model already exists: {target_model}. Use --overwrite to replace it.")
    if target_database_candidate and target_database_candidate.exists() and not args.overwrite:
        raise UserError(f"Promoted COLMAP database already exists: {target_database_candidate}. Use --overwrite to replace it.")
    if target_ply_candidate and target_ply_candidate.exists() and not args.overwrite:
        raise UserError(f"Promoted sparse PLY already exists: {target_ply_candidate}. Use --overwrite to replace it.")
    if target_model.exists():
        shutil.rmtree(target_model)
    target_model.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_model, target_model)

    target_database: Path | None = None
    if source_database.exists():
        target_database = target_database_candidate
        shutil.copy2(source_database, target_database)

    target_ply: Path | None = None
    if source_ply.exists():
        target_ply = target_ply_candidate
        shutil.copy2(source_ply, target_ply)

    for src, dst in [
        (run_dir / "image_list.txt", colmap_dir / "source_image_list.txt"),
        (run_dir / "selection.json", colmap_dir / "source_selection.json"),
        (run_dir / "report.json", colmap_dir / "source_benchmark_report.json"),
        (run_dir / "report.md", colmap_dir / "source_benchmark_report.md"),
    ]:
        if src.exists():
            shutil.copy2(src, dst)

    report = {
        "schema_version": 1,
        "dataset": meta["name"],
        "bench_run": args.bench_run,
        "promoted_at": utc_now(),
        "mapper": model_record.get("mapper", args.mapper),
        "model_id": str(model_record.get("model_id", args.model_id)),
        "artifact_class": "inference",
        "role": "promoted_local_sparse_baseline",
        "source_model_path": str(source_model),
        "source_report_path": str(run_dir / "report.json"),
        "target_model_path": "colmap/sparse/0",
        "target_database_path": "colmap/database.db" if target_database else None,
        "target_ply_path": "colmap/sparse.ply" if target_ply else None,
        "metrics": model_record.get("metrics", {}),
        "registration": model_record.get("registration", {}),
        "notes": [
            "Promoted from a local Apple Silicon COLMAP/GLOMAP-style baseline.",
            "Use as the default camera-pose and sparse-reconstruction foundation for Splatfacto jobs unless a newer baseline scores better.",
        ],
    }
    json_write(promoted_colmap_report_path(dataset), report)
    (dataset / "reports" / "promoted_colmap.md").write_text(promoted_colmap_markdown(report), encoding="utf-8")

    print(f"Promoted COLMAP model: {source_model} -> {target_model}")
    if target_database:
        print(f"Copied database: {target_database}")
    if target_ply:
        print(f"Copied sparse PLY: {target_ply}")
    print(f"Wrote report: {promoted_colmap_report_path(dataset)}")
    return 0


def merge_candidate_sources(manifest: dict[str, Any]) -> list[str]:
    source_names: list[str] = []
    seen: set[str] = set()
    for image in manifest.get("images", []):
        source_name = image.get("source_dataset")
        source_working_path = image.get("source_working_path")
        if not source_name or not source_working_path:
            raise UserError("Dataset manifest is not a merge candidate with source_dataset/source_working_path provenance.")
        if source_name not in seen:
            source_names.append(str(source_name))
            seen.add(str(source_name))
    return source_names


def remote_merge_stage_script(remote_root: str, dataset_name: str) -> str:
    payload = {
        "remote_root": remote_root,
        "dataset_name": dataset_name,
    }
    return f"""#!/usr/bin/env python3
import json
import os
import shutil
from pathlib import Path

payload = {json.dumps(payload, sort_keys=True)}
root = Path(payload["remote_root"])
dataset = payload["dataset_name"]
target = root / "datasets" / dataset
manifest_path = target / "manifests" / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

images_root = target / "working" / "images"
if images_root.exists():
    shutil.rmtree(images_root)
images_root.mkdir(parents=True, exist_ok=True)

hardlinked = 0
copied = 0
missing = []
for image in manifest.get("images", []):
    source_dataset = image.get("source_dataset")
    source_working_path = image.get("source_working_path")
    working_path = image.get("working_path")
    if not source_dataset or not source_working_path or not working_path:
        missing.append({{"image": image.get("relative_path"), "reason": "missing_provenance"}})
        continue

    src = root / "datasets" / source_dataset / source_working_path
    dst = target / working_path
    if not src.exists():
        missing.append({{"image": image.get("relative_path"), "source": str(src), "reason": "source_missing"}})
        continue
    try:
        dst.relative_to(images_root)
    except ValueError:
        missing.append({{"image": image.get("relative_path"), "target": str(dst), "reason": "unsafe_target"}})
        continue

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
        hardlinked += 1
    except OSError:
        shutil.copy2(src, dst)
        copied += 1

report = {{
    "dataset": dataset,
    "staged_at": "{utc_now()}",
    "image_count": len(manifest.get("images", [])),
    "hardlinked_count": hardlinked,
    "copied_count": copied,
    "missing_count": len(missing),
    "missing": missing,
}}
(target / "cloud").mkdir(parents=True, exist_ok=True)
(target / "cloud" / "hetzner_stage_merge.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
print(json.dumps(report, indent=2, sort_keys=True))
if missing:
    raise SystemExit(2)
"""


def cmd_stage_merge_hetzner(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    source_names = merge_candidate_sources(manifest)
    host, remote_root = require_hetzner(config)
    remote_dataset = remote_dataset_path(config, meta["name"])
    remote_pipeline = remote_pipeline_path(config)

    mkdir_cmd = ["ssh", host, f"mkdir -p {shlex.quote(remote_dataset)} {shlex.quote(remote_pipeline)}"]
    metadata_cmd = [
        *rsync_base_args(config, args.dry_run),
        "--delete",
        "--include",
        "*/",
        "--include",
        "/manifests/***",
        "--include",
        "/reports/***",
        "--include",
        "/colmap/***",
        "--include",
        "/cloud/***",
        "--include",
        "/logs/***",
        "--exclude",
        "*",
        f"{dataset}/",
        f"{host}:{remote_dataset}/",
    ]
    scripts_cmd = [
        *rsync_base_args(config, args.dry_run),
        f"{PROJECT_ROOT / 'scripts' / 'remote'}/",
        f"{host}:{remote_pipeline}/",
    ]
    remote_python_cmd = ["ssh", host, "python3 -"]
    remote_script = remote_merge_stage_script(remote_root, meta["name"])

    print(shell_join(mkdir_cmd))
    print(shell_join(metadata_cmd))
    print(shell_join(scripts_cmd))
    print(f"{shell_join(remote_python_cmd)} <<'PY'")
    print(remote_script.rstrip())
    print("PY")
    print(f"Expected remote source datasets: {', '.join(source_names)}")
    print(f"Expected remote hardlinks/copies: {manifest['image_count']}")
    if args.dry_run:
        return 0

    subprocess.run(mkdir_cmd, check=True)
    subprocess.run(metadata_cmd, check=True)
    subprocess.run(scripts_cmd, check=True)
    proc = subprocess.run(remote_python_cmd, input=remote_script, check=False, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        raise UserError("Remote merge staging failed. Check missing source paths above.")

    marker = {
        "dataset": meta["name"],
        "synced_at": utc_now(),
        "image_count": manifest["image_count"],
        "working_only": True,
        "stage_mode": "merge_remote_hardlinks",
        "source_datasets": source_names,
        "local_dataset": str(dataset),
        "remote_dataset": remote_dataset,
        "remote_pipeline": remote_pipeline,
    }
    json_write(dataset / "cloud" / "hetzner_sync.json", marker)
    marker_cmd = [
        *rsync_base_args(config, False),
        str(dataset / "cloud" / "hetzner_sync.json"),
        f"{host}:{remote_dataset}/cloud/hetzner_sync.json",
    ]
    subprocess.run(marker_cmd, check=True)
    print(f"Staged merge candidate on {host}:{remote_dataset}")
    return 0


def estimate_cloud_expansion(raw_bytes: int, target: str) -> tuple[int, str]:
    factors = {"mesh": 8, "splat": 5, "both": 12}
    factor = factors[target]
    return raw_bytes * factor, f"{factor}x raw input"


def config_arg_for_command(config_path: Path | None) -> str:
    if not config_path:
        return ""
    return f" --config {shlex.quote(str(config_path))}"


def default_job_id(dataset_name: str, target: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{dataset_name}-{target}-{stamp}"


def shell_export(name: str, value: Any) -> str:
    return f"export {name}={shlex.quote(str(value))}"


def validate_job_inputs(dataset: Path, manifest: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    images = manifest.get("images", [])
    issues: list[dict[str, Any]] = []
    total_bytes = 0

    if int(manifest.get("image_count", len(images))) != len(images):
        issues.append(
            {
                "code": "image_count_mismatch",
                "manifest_image_count": manifest.get("image_count"),
                "actual_record_count": len(images),
            }
        )

    for image in images:
        rel = image.get("working_path")
        if not rel:
            issues.append({"code": "missing_working_path", "image": image.get("relative_path")})
            continue
        path = dataset / rel
        if not path.exists():
            issues.append({"code": "missing_working_file", "image": image.get("relative_path"), "path": rel})
            continue
        total_bytes += path.stat().st_size
        expected = image.get("sha256")
        if expected:
            actual = sha256_file(path)
            if actual != expected:
                issues.append(
                    {
                        "code": "checksum_mismatch",
                        "image": image.get("relative_path"),
                        "path": rel,
                        "expected": expected,
                        "actual": actual,
                    }
                )

    return total_bytes, issues


def newest_mtime(paths: list[Path]) -> float:
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    return max(mtimes) if mtimes else 0.0


def job_artifact_contract(target: str) -> list[dict[str, Any]]:
    artifacts = [
        {
            "class": "camera_poses",
            "artifact_class": "inference",
            "primary_paths": ["colmap/sparse/0/images.bin", "colmap/sparse/0/cameras.bin"],
            "notes": "Camera poses from COLMAP mapper; VGGT/GLOMAP can be added as separate benchmark outputs later.",
        },
        {
            "class": "point_clouds",
            "artifact_class": "inference",
            "primary_paths": ["colmap/sparse.ply", "colmap/fused.ply"],
            "notes": "Sparse and dense point clouds from COLMAP when the selected target runs them.",
        },
        {
            "class": "depth_maps_point_maps",
            "artifact_class": "inference",
            "primary_paths": ["colmap/dense/stereo/depth_maps"],
            "notes": "COLMAP PatchMatch depth maps for mesh/both jobs; neural point maps are a next bench extension.",
        },
        {
            "class": "colmap_sparse_reconstruction",
            "artifact_class": "inference",
            "primary_paths": ["colmap/database.db", "colmap/sparse/0"],
            "notes": "COLMAP-compatible sparse reconstruction for downstream tools and sanity checks.",
        },
        {
            "class": "gaussian_splats_inspection_renders",
            "artifact_class": "visualization",
            "primary_paths": ["splat/nerfstudio-data", "splat/runs"],
            "notes": "Splatfacto trained outputs and any viewer/export artifacts.",
        },
    ]
    if target == "mesh":
        artifacts[-1]["status_for_target"] = "not_requested"
    if target == "splat":
        artifacts[0]["status_for_target"] = "input_from_promoted_colmap"
        artifacts[1]["status_for_target"] = "input_sparse_point_cloud"
        artifacts[2]["status_for_target"] = "not_requested"
        artifacts[3]["status_for_target"] = "input_from_promoted_colmap"
        artifacts[4]["status_for_target"] = "generated_by_this_job"
    return artifacts


def job_bootstrap_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

JOB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${JOB_DIR}/job.env"

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export UV_CONCURRENT_DOWNLOADS="${UV_CONCURRENT_DOWNLOADS:-16}"
export UV_CONCURRENT_BUILDS="${UV_CONCURRENT_BUILDS:-8}"
export UV_CONCURRENT_INSTALLS="${UV_CONCURRENT_INSTALLS:-8}"

SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=(sudo)
fi

if [[ -x "${JOB_DIR}/scripts/gpu/bootstrap-gpu.sh" ]]; then
  echo "[bootstrap] running shared GPU bootstrap"
  export WWS_GPU_WORK_ROOT="${PGM_WORK_ROOT}"
  export WWS_HETZNER_HOST="${PGM_HETZNER_HOST}"
  export WWS_HETZNER_TEST_PATH="${PGM_REMOTE_DATASET}/manifests/manifest.json"
  export WWS_COLMAP_PREFIX="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}"
  export WWS_SRC_ROOT="${WWS_SRC_ROOT:-/workspace/src}"
  export WWS_BUILD_COLMAP_CUDA="${WWS_BUILD_COLMAP_CUDA:-1}"
  export WWS_REQUIRE_COLMAP_CUDA="${WWS_REQUIRE_COLMAP_CUDA:-${PGM_COLMAP_REQUIRE_CUDA:-1}}"
  bash "${JOB_DIR}/scripts/gpu/bootstrap-gpu.sh"
else
  echo "[bootstrap] apt update"
  "${SUDO[@]}" apt-get update

  echo "[bootstrap] installing transfer/build tools"
  "${SUDO[@]}" apt-get install -y --no-install-recommends \\
    aria2 \\
    build-essential \\
    ca-certificates \\
    cmake \\
    curl \\
    ffmpeg \\
    fpart \\
    git \\
    git-lfs \\
    jq \\
    lftp \\
    mbuffer \\
    ninja-build \\
    openssh-client \\
    parallel \\
    pigz \\
    pv \\
    python3 \\
    python3-pip \\
    rsync \\
    unzip \\
    wget \\
    zstd

  if ! command -v colmap >/dev/null 2>&1; then
    echo "[bootstrap] installing COLMAP from apt if available"
    "${SUDO[@]}" apt-get install -y --no-install-recommends colmap || echo "[bootstrap] apt COLMAP install failed; verify-ready will catch this"
  fi
fi

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  "${SUDO[@]}" ln -sf "$(command -v python3)" /usr/local/bin/python
fi

mkdir -p "${PGM_WORK_ROOT}/downloads" "${PGM_WORK_ROOT}/cache"

if [[ -s "${JOB_DIR}/downloads/aria2.urls" ]]; then
  echo "[bootstrap] parallel URL downloads via aria2"
  aria2c \\
    --continue=true \\
    --file-allocation=none \\
    --max-concurrent-downloads=8 \\
    --max-connection-per-server=16 \\
    --split=16 \\
    --summary-interval=10 \\
    --input-file="${JOB_DIR}/downloads/aria2.urls" \\
    --dir="${PGM_WORK_ROOT}/downloads"
fi

echo "[bootstrap] installing Python packages with uv concurrency"
python -m pip install --upgrade pip setuptools wheel uv || python -m pip install --upgrade pip setuptools wheel
if command -v uv >/dev/null 2>&1; then
  uv pip install --system --compile-bytecode --no-cache -r "${JOB_DIR}/downloads/pip-packages.txt"
else
  python -m pip install --no-cache-dir --retries 10 -r "${JOB_DIR}/downloads/pip-packages.txt"
fi

echo "[bootstrap] tool versions"
python --version || true
rsync --version | head -1 || true
aria2c --version | head -1 || true
ffmpeg -version | head -1 || true
if command -v colmap >/dev/null 2>&1; then
  colmap -h | head -1 || true
else
  echo "colmap not installed; not required for splat-only precomputed-COLMAP jobs"
fi
ns-train --help >/dev/null 2>&1 && echo "nerfstudio installed" || echo "nerfstudio command probe failed"
nvidia-smi || true

echo "[bootstrap] done"
"""


def job_rsync_prelude() -> str:
    return """rsync_args() {
  local args=(-aP --whole-file --inplace --partial)
  if rsync --help 2>&1 | grep -q -- "--info"; then
    args+=(--info=progress2)
  fi
  printf "%s\\n" "${args[@]}"
}

mapfile -t RSYNC_ARGS < <(rsync_args)
"""


def job_pull_inputs_script() -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

JOB_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
# shellcheck source=/dev/null
source "${{JOB_DIR}}/job.env"

LOCAL_DATASET="${{PGM_WORK_ROOT}}/datasets/${{PGM_DATASET}}"
LOCAL_EVIDENCE="${{PGM_WORK_ROOT}}/evidence/packages/${{PGM_EVIDENCE_PACKAGE:-}}"

{job_rsync_prelude()}

mkdir -p "${{LOCAL_DATASET}}" "${{PGM_WORK_ROOT}}/pipeline/remote"

echo "[pull] syncing job-local pipeline scripts"
rsync "${{RSYNC_ARGS[@]}}" "${{JOB_DIR}}/scripts/pipeline/" "${{PGM_WORK_ROOT}}/pipeline/remote/"
chmod +x "${{PGM_WORK_ROOT}}/pipeline/remote/"*.sh || true

echo "[pull] syncing dataset metadata from Hetzner"
rsync "${{RSYNC_ARGS[@]}}" \\
  --include "*/" \\
  --include "/manifests/***" \\
  --include "/reports/***" \\
  --include "/colmap/***" \\
  --include "/cloud/***" \\
  --include "/logs/***" \\
  --exclude "*" \\
  "${{PGM_HETZNER_HOST}}:${{PGM_REMOTE_DATASET}}/" \\
  "${{LOCAL_DATASET}}/"

echo "[pull] syncing working images from Hetzner in parallel"
IMAGE_SRC="${{PGM_REMOTE_DATASET}}/working/images"
IMAGE_DST="${{LOCAL_DATASET}}/working/images"
mkdir -p "${{IMAGE_DST}}"
if command -v parallel >/dev/null 2>&1; then
  export PGM_HETZNER_HOST IMAGE_SRC IMAGE_DST
  ssh "${{PGM_HETZNER_HOST}}" "cd '${{IMAGE_SRC}}' && find . -type f -print0" | \\
    parallel -0 -j "${{PGM_PARALLEL_RSYNC_JOBS:-8}}" --line-buffer '
      rel="{{}}"
      mkdir -p "${{IMAGE_DST}}/$(dirname "${{rel}}")"
      rsync -a --whole-file --inplace --partial "${{PGM_HETZNER_HOST}}:${{IMAGE_SRC}}/${{rel}}" "${{IMAGE_DST}}/${{rel}}" && echo "[pull] image ${{rel}}"
    '
else
  rsync "${{RSYNC_ARGS[@]}}" \\
    "${{PGM_HETZNER_HOST}}:${{IMAGE_SRC}}/" \\
    "${{IMAGE_DST}}/"
fi

if [[ -n "${{PGM_EVIDENCE_PACKAGE:-}}" && -n "${{PGM_EVIDENCE_REMOTE_ROOT:-}}" ]]; then
  echo "[pull] syncing evidence package metadata"
  mkdir -p "${{LOCAL_EVIDENCE}}"
  rsync "${{RSYNC_ARGS[@]}}" \\
    --include "*/" \\
    --include "manifests/***" \\
    --include "working/image_lists/***" \\
    --include "benchmarks/bench_plan.*" \\
    --include "registration/***" \\
    --include "state/***" \\
    --exclude "*" \\
    "${{PGM_HETZNER_HOST}}:${{PGM_EVIDENCE_REMOTE_ROOT%/}}/packages/${{PGM_EVIDENCE_PACKAGE}}/" \\
    "${{LOCAL_EVIDENCE}}/" || echo "[pull] evidence metadata sync skipped or failed"
fi

echo "[pull] done"
"""


def job_verify_ready_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

JOB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${JOB_DIR}/job.env"

LOCAL_DATASET="${PGM_WORK_ROOT}/datasets/${PGM_DATASET}"
MANIFEST="${LOCAL_DATASET}/manifests/manifest.json"
IMAGE_DIR="${LOCAL_DATASET}/working/images"
PRECOMPUTED_SPARSE="${LOCAL_DATASET}/colmap/sparse/0"

echo "[verify] package checksums"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "${JOB_DIR}" && sha256sum -c checksums.sha256)
else
  echo "[verify] sha256sum unavailable; package checksum verification skipped"
fi

echo "[verify] remote staging reachable"
ssh -o BatchMode=yes -o ConnectTimeout=10 "${PGM_HETZNER_HOST}" "test -f '${PGM_REMOTE_DATASET}/manifests/manifest.json' && test -d '${PGM_REMOTE_DATASET}/working/images'"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "Local manifest missing. Run pull-inputs.sh first: ${MANIFEST}" >&2
  exit 2
fi

if [[ ! -d "${IMAGE_DIR}" ]]; then
  echo "Local image directory missing. Run pull-inputs.sh first: ${IMAGE_DIR}" >&2
  exit 2
fi

python - "${LOCAL_DATASET}" "${PGM_IMAGE_COUNT}" <<'PY'
import json
import sys
from pathlib import Path

dataset = Path(sys.argv[1])
expected = int(sys.argv[2])
manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))
images = manifest.get("images", [])
missing = [item.get("working_path") for item in images if not (dataset / str(item.get("working_path", ""))).exists()]
if len(images) != expected:
    raise SystemExit(f"manifest record count {len(images)} != expected {expected}")
if missing:
    raise SystemExit(f"missing working images: {missing[:10]}")
print(f"[verify] manifest images: {len(images)}")
PY

count="$(find "${IMAGE_DIR}" -type f \\( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.tif" -o -iname "*.tiff" \\) | wc -l | tr -d " ")"
if [[ "${count}" != "${PGM_IMAGE_COUNT}" ]]; then
  echo "working image file count ${count} != expected ${PGM_IMAGE_COUNT}" >&2
  exit 2
fi
echo "[verify] working image files: ${count}"

if [[ "${PGM_USE_PRECOMPUTED_COLMAP:-0}" == "1" ]]; then
  if [[ ! -f "${PRECOMPUTED_SPARSE}/cameras.bin" || ! -f "${PRECOMPUTED_SPARSE}/images.bin" || ! -f "${PRECOMPUTED_SPARSE}/points3D.bin" ]]; then
    echo "PGM_USE_PRECOMPUTED_COLMAP=1, but promoted sparse COLMAP model is missing or incomplete: ${PRECOMPUTED_SPARSE}" >&2
    exit 2
  fi
  echo "[verify] precomputed COLMAP sparse model: ${PRECOMPUTED_SPARSE}"
fi

if [[ "${PGM_TARGET}" == "mesh" || "${PGM_TARGET}" == "both" || "${PGM_TARGET}" == "splat" ]]; then
  if [[ -x "${JOB_DIR}/scripts/gpu/preflight-gpu.sh" ]]; then
    export WWS_GPU_WORK_ROOT="${PGM_WORK_ROOT}"
    export WWS_HETZNER_HOST="${PGM_HETZNER_HOST}"
    export WWS_HETZNER_TEST_PATH="${PGM_REMOTE_DATASET}/manifests/manifest.json"
    export WWS_REQUIRE_COLMAP_CUDA="${WWS_REQUIRE_COLMAP_CUDA:-${PGM_COLMAP_REQUIRE_CUDA:-1}}"
    WWS_PREFLIGHT_PHASE=verify bash "${JOB_DIR}/scripts/gpu/preflight-gpu.sh"
  fi
  if [[ ! ( "${PGM_TARGET}" == "splat" && "${PGM_USE_PRECOMPUTED_COLMAP:-0}" == "1" ) ]]; then
    COLMAP_BIN="${PGM_COLMAP_BIN:-}"
    if [[ -z "${COLMAP_BIN}" && -x "${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}/bin/colmap" ]]; then
      COLMAP_BIN="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}/bin/colmap"
    elif [[ -z "${COLMAP_BIN}" ]]; then
      COLMAP_BIN="$(command -v colmap || true)"
    fi
    if [[ -z "${COLMAP_BIN}" || ! -x "${COLMAP_BIN}" ]]; then
      echo "colmap missing" >&2
      exit 127
    fi
    if [[ "${PGM_COLMAP_REQUIRE_CUDA:-0}" == "1" && "$("${COLMAP_BIN}" -h 2>&1 || true)" != *"with CUDA"* ]]; then
      echo "CUDA COLMAP required, but ${COLMAP_BIN} does not report CUDA support" >&2
      exit 127
    fi
    echo "[verify] colmap: ${COLMAP_BIN}"
  else
    echo "[verify] splat-only job will reuse precomputed COLMAP sparse model; CUDA COLMAP is not required"
  fi
fi
if [[ "${PGM_TARGET}" == "splat" || "${PGM_TARGET}" == "both" ]]; then
  command -v ns-process-data >/dev/null 2>&1 || { echo "ns-process-data missing" >&2; exit 127; }
  command -v ns-train >/dev/null 2>&1 || { echo "ns-train missing" >&2; exit 127; }
fi

echo "[verify] ready"
"""


def job_sync_back_script() -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

JOB_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
# shellcheck source=/dev/null
source "${{JOB_DIR}}/job.env"

LOCAL_DATASET="${{PGM_WORK_ROOT}}/datasets/${{PGM_DATASET}}"

{job_rsync_prelude()}

echo "[sync-back] ensuring remote directories"
ssh "${{PGM_HETZNER_HOST}}" "mkdir -p '${{PGM_REMOTE_DATASET}}' '${{PGM_REMOTE_JOB}}'"

echo "[sync-back] syncing dataset outputs to Hetzner"
rsync "${{RSYNC_ARGS[@]}}" "${{LOCAL_DATASET}}/" "${{PGM_HETZNER_HOST}}:${{PGM_REMOTE_DATASET}}/"

echo "[sync-back] syncing job logs/package state to Hetzner"
rsync "${{RSYNC_ARGS[@]}}" "${{JOB_DIR}}/" "${{PGM_HETZNER_HOST}}:${{PGM_REMOTE_JOB}}/"

if [[ -d "${{PGM_WORK_ROOT}}/runtime/preflight" ]]; then
  echo "[sync-back] syncing GPU preflight reports to Hetzner"
  ssh "${{PGM_HETZNER_HOST}}" "mkdir -p '${{PGM_REMOTE_JOB}}/runtime/preflight'"
  rsync "${{RSYNC_ARGS[@]}}" "${{PGM_WORK_ROOT}}/runtime/preflight/" "${{PGM_HETZNER_HOST}}:${{PGM_REMOTE_JOB}}/runtime/preflight/"
fi

echo "[sync-back] done"
"""


def job_run_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

JOB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${JOB_DIR}/job.env"

if [[ -x "${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}/bin/colmap" ]]; then
  export PATH="${WWS_COLMAP_PREFIX:-/workspace/colmap-cuda}/bin:${PATH}"
fi

LOCAL_DATASET="${PGM_WORK_ROOT}/datasets/${PGM_DATASET}"
PIPELINE="${PGM_WORK_ROOT}/pipeline/remote"
PRECOMPUTED_SPARSE="${LOCAL_DATASET}/colmap/sparse/0"
STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
mkdir -p "${LOCAL_DATASET}/logs" "${LOCAL_DATASET}/reports" "${JOB_DIR}/logs"

if [[ "${PGM_SKIP_PULL:-0}" == "1" ]]; then
  echo "[job] skipping pull-inputs because PGM_SKIP_PULL=1"
else
  echo "[job] pulling inputs"
  bash "${JOB_DIR}/scripts/pull-inputs.sh" | tee "${JOB_DIR}/logs/pull-inputs.log"
fi

if [[ "${PGM_SKIP_VERIFY:-0}" == "1" ]]; then
  echo "[job] skipping verify-ready because PGM_SKIP_VERIFY=1"
else
  echo "[job] verifying readiness"
  bash "${JOB_DIR}/scripts/verify-ready.sh" | tee "${JOB_DIR}/logs/verify-ready.log"
fi

status="success"
failure=""

run_stage() {
  local name="$1"
  shift
  echo "[job] starting ${name}"
  local started finished
  started="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if ! "$@" >"${LOCAL_DATASET}/logs/${name}.log" 2>&1; then
    status="failed"
    failure="${name}"
    finished="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    printf '{"stage":"%s","started_at":"%s","finished_at":"%s","status":"failed"}\n' "${name}" "${started}" "${finished}" >"${LOCAL_DATASET}/logs/${name}.stage.json"
    echo "[job] ${name} failed; see ${LOCAL_DATASET}/logs/${name}.log"
    return 1
  fi
  finished="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  printf '{"stage":"%s","started_at":"%s","finished_at":"%s","status":"success"}\n' "${name}" "${started}" "${finished}" >"${LOCAL_DATASET}/logs/${name}.stage.json"
  echo "[job] finished ${name}"
}

if [[ "${PGM_TARGET}" == "mesh" || "${PGM_TARGET}" == "both" ]]; then
  run_stage colmap_dense "${PIPELINE}/run-colmap.sh" "${LOCAL_DATASET}" dense || true
fi

if [[ "${status}" == "success" && "${PGM_TARGET}" == "splat" ]]; then
  if [[ "${PGM_USE_PRECOMPUTED_COLMAP:-0}" == "1" && -f "${PRECOMPUTED_SPARSE}/images.bin" ]]; then
    echo "[job] skipping colmap_sparse; using precomputed sparse model at ${PRECOMPUTED_SPARSE}"
    printf '{"stage":"%s","started_at":"%s","finished_at":"%s","status":"skipped","reason":"precomputed_colmap"}\n' "colmap_sparse" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" >"${LOCAL_DATASET}/logs/colmap_sparse.stage.json"
  else
    run_stage colmap_sparse "${PIPELINE}/run-colmap.sh" "${LOCAL_DATASET}" sparse || true
  fi
fi

if [[ "${status}" == "success" && ( "${PGM_TARGET}" == "mesh" || "${PGM_TARGET}" == "both" ) ]]; then
  run_stage openmvs "${PIPELINE}/run-openmvs.sh" "${LOCAL_DATASET}" || true
fi

if [[ "${status}" == "success" && ( "${PGM_TARGET}" == "splat" || "${PGM_TARGET}" == "both" ) ]]; then
  run_stage splatfacto "${PIPELINE}/run-splatfacto.sh" "${LOCAL_DATASET}" || true
fi

FINISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
cat >"${LOCAL_DATASET}/reports/run_report.json" <<JSON
{
  "schema_version": 1,
  "job_id": "${PGM_JOB_ID}",
  "dataset": "${PGM_DATASET}",
  "target": "${PGM_TARGET}",
  "started_at": "${STARTED_AT}",
  "finished_at": "${FINISHED_AT}",
  "status": "${status}",
  "failure_stage": "${failure}",
  "host": "$(hostname)",
  "work_root": "${PGM_WORK_ROOT}",
  "artifact_contract_path": "${PGM_REMOTE_JOB}/job.json",
  "tools": {
    "colmap": "${PGM_COLMAP_BIN:-$(command -v colmap || true)}",
    "ns_process_data": "$(command -v ns-process-data || true)",
    "ns_train": "$(command -v ns-train || true)",
    "nvidia_smi_available": "$(command -v nvidia-smi || true)"
  },
  "outputs": {
    "camera_poses": "colmap/sparse/0",
    "point_clouds": ["colmap/sparse.ply", "colmap/fused.ply"],
    "depth_maps_point_maps": "colmap/dense/stereo/depth_maps",
    "colmap_sparse_reconstruction": "colmap/sparse/0",
    "gaussian_splats_inspection_renders": "splat/runs"
  }
}
JSON

cp "${LOCAL_DATASET}/reports/run_report.json" "${JOB_DIR}/run_report.json" || true

echo "[job] syncing back to Hetzner"
if ! bash "${JOB_DIR}/scripts/sync-back.sh" | tee "${JOB_DIR}/logs/sync-back.log"; then
  echo "[job] sync-back failed; keep this instance alive until artifacts are recovered" >&2
  exit 1
fi

if [[ "${status}" != "success" ]]; then
  exit 1
fi

echo "[job] done"
"""


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def write_job_checksums(job_dir: Path) -> None:
    lines: list[str] = []
    for path in sorted(item for item in job_dir.rglob("*") if item.is_file()):
        rel = path.relative_to(job_dir).as_posix()
        if rel == "checksums.sha256":
            continue
        lines.append(f"{sha256_file(path)}  {rel}")
    (job_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_remote_scripts_into_job(job_dir: Path) -> None:
    target = job_dir / "scripts" / "pipeline"
    target.mkdir(parents=True, exist_ok=True)
    for src in sorted((PROJECT_ROOT / "scripts" / "remote").glob("*.sh")):
        dst = target / src.name
        shutil.copy2(src, dst)
        dst.chmod(0o755)
    gpu_source = REPO_ROOT / "gpu" / "scripts"
    if gpu_source.exists():
        gpu_target = job_dir / "scripts" / "gpu"
        gpu_target.mkdir(parents=True, exist_ok=True)
        for src in sorted(gpu_source.glob("*.sh")):
            dst = gpu_target / src.name
            shutil.copy2(src, dst)
            dst.chmod(0o755)


def job_readme(job: dict[str, Any]) -> str:
    job_id = job["job_id"]
    host = job["hetzner"]["ssh_host"]
    remote_root = job["hetzner"]["remote_root"]
    work_root = job["vast"]["work_root"]
    target = job["target"]
    if target == "splat":
        artifact_summary = """This splat-only package tracks the five project artifact classes, but it does
not generate all five from scratch. For this run:

1. Camera poses: reused from the promoted COLMAP sparse model.
2. Point clouds: reused as the promoted COLMAP sparse point cloud.
3. Depth maps / point maps: not requested; VGGT or dense COLMAP/OpenMVS handle this later.
4. COLMAP-compatible sparse reconstruction: reused from the promoted local baseline.
5. Gaussian splats / inspection renders: generated by this Splatfacto job.

This is intentional. The goal is to make `S0` inspectable without paying for a
new sparse or dense reconstruction pass."""
    elif target == "mesh":
        artifact_summary = """This mesh package focuses on COLMAP/OpenMVS geometry. It should produce or
reuse camera poses, sparse reconstruction, point-cloud outputs, and dense
depth/mesh artifacts. Gaussian splats are not requested for this target."""
    else:
        artifact_summary = """This `both` package is the broad reconstruction target. It is expected to run
mesh/dense stages and Splatfacto, so it may produce all five project artifact
classes when the GPU, disk, and toolchain preflight gates pass."""
    return f"""# GPU Job Package: {job_id}

This package is the handoff bundle for a short-lived Vast.ai GPU instance.
It does not contain the photo files. The photos stay staged on Hetzner and are
pulled directly to the GPU box.

## Dataset

- Dataset: `{job['dataset']}`
- Target: `{job['target']}`
- Images: `{job['image_count']}`
- Working image bytes: `{human_bytes(int(job['working_total_bytes']))}`
- Remote dataset: `{host}:{job['hetzner']['remote_dataset']}`
- Remote job package: `{host}:{job['hetzner']['remote_job']}`
- Evidence package: `{job.get('evidence_package') or 'none'}`
- Precomputed COLMAP sparse model: `{'yes' if job.get('precomputed_colmap', {}).get('use_for_job') else 'no'}`

## Vast First Commands

Run these after the Vast instance is reachable over SSH and can reach the
Hetzner host with your SSH key/agent.

```sh
export PGM_HETZNER_HOST={shlex.quote(host)}
export PGM_HETZNER_ROOT={shlex.quote(remote_root)}
export PGM_JOB_ID={shlex.quote(job_id)}
export PGM_WORK_ROOT={shlex.quote(work_root)}

mkdir -p "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID"
rsync -aP --whole-file --inplace --partial "$PGM_HETZNER_HOST:$PGM_HETZNER_ROOT/jobs/$PGM_JOB_ID/" "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/"

bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/bootstrap-vast.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

`run-job.sh` performs the dataset pull, readiness verification, Splatfacto run,
and sync-back. For debugging, you can run `pull-inputs.sh` and
`verify-ready.sh` manually first, then run:

```sh
PGM_SKIP_PULL=1 PGM_SKIP_VERIFY=1 bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

`bootstrap-vast.sh` installs transfer tools including `aria2`, `rsync`, `zstd`,
`pigz`, `parallel`, `fpart`, and `mbuffer`. When `scripts/gpu/` is present it
also builds CUDA COLMAP under `/workspace/colmap-cuda`, writes preflight reports
under `/workspace/whatwesee/runtime/preflight/`, and fails readiness if CUDA
COLMAP is required but missing. Python packages install with `uv` concurrency
when available. `pull-inputs.sh` uses non-compressed rsync flags for JPEG-heavy
data, because compressing already-compressed images wastes paid GPU time.
If `precomputed_colmap.use_for_job` is true in `job.json`, the job pulls the
promoted `colmap/sparse/0` model from Hetzner and Splatfacto reuses it instead
of spending paid GPU time on a fresh sparse COLMAP pass. If Nerfstudio cannot
reuse the promoted model, the splat stage fails fast instead of silently running
internal COLMAP.

## Artifact Contract

{artifact_summary}

The exact paths and evidence classifications are in `job.json`.
"""


def cmd_job_package(args: argparse.Namespace, config: dict[str, Any]) -> int:
    if args.target not in {"mesh", "splat", "both"}:
        raise UserError("--target must be mesh, splat, or both")

    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    qc_report = load_qc_report(dataset)
    if not qc_report.get("passed"):
        raise UserError("QC report failed. Refusing to package GPU work.")

    sync_marker = dataset / "cloud" / "hetzner_sync.json"
    if not sync_marker.exists():
        raise UserError("Dataset has not been staged on Hetzner. Run sync-hetzner or stage-merge-hetzner first.")

    working_total, input_issues = validate_job_inputs(dataset, manifest)
    if input_issues:
        preview = json.dumps(input_issues[:10], indent=2, sort_keys=True)
        raise UserError(f"Working image validation failed with {len(input_issues)} issue(s):\n{preview}")

    host, remote_root = require_hetzner(config)
    job_id = args.name or default_job_id(meta["name"], args.target)
    validate_dataset_name(job_id)
    job_dir = dataset / "cloud" / "jobs" / job_id
    if job_dir.exists() and not args.overwrite:
        raise UserError(f"Job package already exists: {job_dir}. Use --overwrite to rebuild it.")
    if job_dir.exists() and args.overwrite:
        shutil.rmtree(job_dir)

    (job_dir / "downloads").mkdir(parents=True, exist_ok=True)
    (job_dir / "manifests").mkdir(parents=True, exist_ok=True)
    (job_dir / "logs").mkdir(parents=True, exist_ok=True)

    remote_dataset = remote_dataset_path(config, meta["name"])
    remote_pipeline = remote_pipeline_path(config)
    remote_job = remote_job_path(config, job_id)
    work_root = args.work_root or str(config["vast"]["remote_workdir"])
    disk_gb = int(args.disk_gb or config["vast"]["disk_gb"])
    splat_iterations = int(args.splat_iterations)
    evidence_remote_root = args.evidence_remote_root.rstrip("/") if args.evidence_remote_root else ""
    created_at = utc_now()
    precomputed_model = promoted_colmap_model(dataset)
    precomputed_report = promoted_colmap_report_path(dataset)
    precomputed_colmap_available = colmap_model_complete(precomputed_model)
    use_precomputed_colmap = precomputed_colmap_available
    cuda_colmap_required = not (args.target == "splat" and use_precomputed_colmap)
    build_cuda_colmap = cuda_colmap_required
    if use_precomputed_colmap:
        promoted_inputs = [
            precomputed_report,
            dataset / "reports" / "promoted_colmap.md",
            dataset / "colmap" / "database.db",
            dataset / "colmap" / "sparse.ply",
            *list(precomputed_model.glob("*")),
        ]
        if sync_marker.stat().st_mtime < newest_mtime(promoted_inputs):
            raise UserError(
                "Promoted COLMAP model is newer than the last Hetzner dataset sync. "
                "Run sync-hetzner --working-only before building a GPU job package."
            )

    image_index = {
        "schema_version": 1,
        "dataset": meta["name"],
        "created_at": created_at,
        "image_count": manifest.get("image_count", len(manifest.get("images", []))),
        "working_total_bytes": working_total,
        "images": [
            {
                "relative_path": image.get("relative_path"),
                "working_path": image.get("working_path"),
                "sha256": image.get("sha256"),
                "bytes": image.get("bytes"),
                "camera_model": image.get("camera_model"),
                "lens_model": image.get("lens_model"),
                "focal_length": image.get("focal_length"),
                "source_dataset": image.get("source_dataset"),
                "source_relative_path": image.get("source_relative_path"),
            }
            for image in manifest.get("images", [])
        ],
    }
    json_write(job_dir / "manifests" / "image_index.json", image_index)

    for src, dst_name in [
        (dataset / "manifests" / "dataset.json", "dataset.json"),
        (manifest_path(dataset), "manifest.json"),
        (qc_report_path(dataset), "qc_report.json"),
        (dataset / "reports" / "cloud_plan.md", "cloud_plan.md"),
        (dataset / "reports" / "merge_selection_report.json", "merge_selection_report.json"),
        (precomputed_report, "promoted_colmap.json"),
        (dataset / "reports" / "promoted_colmap.md", "promoted_colmap.md"),
        (sync_marker, "hetzner_sync.json"),
    ]:
        if src.exists():
            shutil.copy2(src, job_dir / "manifests" / dst_name)

    copy_remote_scripts_into_job(job_dir)

    pip_packages = [
        f"nerfstudio=={config['vast']['nerfstudio_version']}",
        f"gsplat=={config['vast']['gsplat_version']}",
    ]
    (job_dir / "downloads" / "pip-packages.txt").write_text("\n".join(pip_packages) + "\n", encoding="utf-8")
    (job_dir / "downloads" / "aria2.urls").write_text(
        "# Optional direct model/checkpoint URLs, one per line. aria2c will download these in parallel during bootstrap.\n",
        encoding="utf-8",
    )

    env_lines = [
        shell_export("PGM_JOB_ID", job_id),
        shell_export("PGM_DATASET", meta["name"]),
        shell_export("PGM_TARGET", args.target),
        shell_export("PGM_HETZNER_HOST", host),
        shell_export("PGM_HETZNER_ROOT", remote_root.rstrip("/")),
        shell_export("PGM_REMOTE_DATASET", remote_dataset),
        shell_export("PGM_REMOTE_PIPELINE", remote_pipeline),
        shell_export("PGM_REMOTE_JOB", remote_job),
        shell_export("PGM_WORK_ROOT", work_root),
        shell_export("WWS_GPU_WORK_ROOT", work_root),
        shell_export("WWS_SRC_ROOT", "/workspace/src"),
        shell_export("WWS_COLMAP_PREFIX", "/workspace/colmap-cuda"),
        shell_export("WWS_BUILD_COLMAP_CUDA", 1 if build_cuda_colmap else 0),
        shell_export("WWS_REQUIRE_COLMAP_CUDA", 1 if cuda_colmap_required else 0),
        shell_export("WWS_REQUIRE_NVCC", 1 if build_cuda_colmap else 0),
        shell_export("WWS_MIN_GPU_VRAM_GB", 48),
        shell_export("PGM_COLMAP_BIN", "/workspace/colmap-cuda/bin/colmap" if build_cuda_colmap else ""),
        shell_export("PGM_COLMAP_REQUIRE_CUDA", 1 if cuda_colmap_required else 0),
        shell_export("PGM_USE_PRECOMPUTED_COLMAP", 1 if use_precomputed_colmap else 0),
        shell_export("PGM_COLMAP_SKIP_SPARSE_IF_PRESENT", 1 if use_precomputed_colmap else 0),
        shell_export("PGM_COLMAP_MATCHER", "exhaustive"),
        shell_export("PGM_COLMAP_MAX_IMAGE_SIZE", 4096),
        shell_export("PGM_COLMAP_MAX_NUM_FEATURES", 8192),
        shell_export("PGM_COLMAP_MAX_NUM_MATCHES", 16384),
        shell_export("PGM_COLMAP_EXHAUSTIVE_BLOCK_SIZE", 50),
        shell_export("PGM_PARALLEL_RSYNC_JOBS", 8),
        shell_export("PGM_IMAGE_COUNT", manifest.get("image_count", len(manifest.get("images", [])))),
        shell_export("PGM_WORKING_TOTAL_BYTES", working_total),
        shell_export("PGM_SPLAT_MAX_ITERATIONS", splat_iterations),
        shell_export("NERFSTUDIO_VERSION", config["vast"]["nerfstudio_version"]),
        shell_export("GSPLAT_VERSION", config["vast"]["gsplat_version"]),
        shell_export("UV_CONCURRENT_DOWNLOADS", args.uv_concurrent_downloads),
        shell_export("UV_CONCURRENT_BUILDS", args.uv_concurrent_builds),
        shell_export("UV_CONCURRENT_INSTALLS", args.uv_concurrent_installs),
    ]
    if args.evidence_package:
        env_lines.extend(
            [
                shell_export("PGM_EVIDENCE_PACKAGE", args.evidence_package),
                shell_export("PGM_EVIDENCE_REMOTE_ROOT", evidence_remote_root),
            ]
        )
    (job_dir / "job.env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    job = {
        "schema_version": 1,
        "job_id": job_id,
        "created_at": created_at,
        "dataset": meta["name"],
        "dataset_type": meta.get("dataset_type"),
        "target": args.target,
        "image_count": manifest.get("image_count", len(manifest.get("images", []))),
        "working_total_bytes": working_total,
        "qc": {
            "passed": qc_report.get("passed"),
            "warning_count": qc_report.get("summary", {}).get("warning_count"),
            "fatal_count": qc_report.get("summary", {}).get("fatal_count"),
        },
        "hetzner": {
            "ssh_host": host,
            "remote_root": remote_root.rstrip("/"),
            "remote_dataset": remote_dataset,
            "remote_pipeline": remote_pipeline,
            "remote_job": remote_job,
        },
        "vast": {
            "image": config["vast"]["image"],
            "disk_gb": disk_gb,
            "work_root": work_root,
            "splat_max_iterations": splat_iterations,
            "nerfstudio_version": config["vast"]["nerfstudio_version"],
            "gsplat_version": config["vast"]["gsplat_version"],
        },
        "precomputed_colmap": {
            "available": precomputed_colmap_available,
            "use_for_job": use_precomputed_colmap,
            "model_path": "colmap/sparse/0" if precomputed_colmap_available else None,
            "report_path": "reports/promoted_colmap.json" if precomputed_report.exists() else None,
            "requires_cuda_colmap": cuda_colmap_required,
            "builds_cuda_colmap": build_cuda_colmap,
        },
        "evidence_package": args.evidence_package,
        "evidence_remote_root": evidence_remote_root or None,
        "artifact_contract": job_artifact_contract(args.target),
        "input_validation": {
            "checked_at": created_at,
            "status": "passed",
            "checksum_verified": True,
            "issue_count": 0,
        },
        "cost_controls": {
            "vast_launch_required": "manual",
            "contains_photos": False,
            "pulls_inputs_from_hetzner": True,
            "sync_back_before_destroy": True,
        },
    }
    json_write(job_dir / "job.json", job)
    (job_dir / "README.md").write_text(job_readme(job), encoding="utf-8")

    write_executable(job_dir / "scripts" / "bootstrap-vast.sh", job_bootstrap_script())
    write_executable(job_dir / "scripts" / "pull-inputs.sh", job_pull_inputs_script())
    write_executable(job_dir / "scripts" / "verify-ready.sh", job_verify_ready_script())
    write_executable(job_dir / "scripts" / "sync-back.sh", job_sync_back_script())
    write_executable(job_dir / "scripts" / "run-job.sh", job_run_script())
    write_job_checksums(job_dir)

    print(f"Wrote job package: {job_dir}")
    print(f"Images validated: {job['image_count']}")
    print(f"Working size: {human_bytes(working_total)}")

    if args.sync_hetzner:
        mkdir_cmd = ["ssh", host, f"mkdir -p {shlex.quote(remote_job)}"]
        rsync_cmd = [
            *rsync_base_args(config, args.dry_run),
            f"{job_dir}/",
            f"{host}:{remote_job}/",
        ]
        verify_cmd = ["ssh", host, f"cd {shlex.quote(remote_job)} && sha256sum -c checksums.sha256"]
        print(shell_join(mkdir_cmd))
        print(shell_join(rsync_cmd))
        print(shell_join(verify_cmd))
        if args.dry_run:
            return 0
        subprocess.run(mkdir_cmd, check=True)
        subprocess.run(rsync_cmd, check=True)
        subprocess.run(verify_cmd, check=True)
        marker = {
            "job_id": job_id,
            "dataset": meta["name"],
            "synced_at": utc_now(),
            "local_job": str(job_dir),
            "remote_job": remote_job,
            "remote_dataset": remote_dataset,
        }
        json_write(dataset / "cloud" / f"job_package_{job_id}.json", marker)
        print(f"Staged job package on {host}:{remote_job}")

    return 0


def cloud_plan_markdown(
    args: argparse.Namespace,
    config: dict[str, Any],
    config_path: Path | None,
    dataset: Path,
    meta: dict[str, Any],
    manifest: dict[str, Any],
    qc_report: dict[str, Any],
) -> str:
    target = args.target
    estimated_bytes, factor = estimate_cloud_expansion(int(manifest["raw_total_bytes"]), target)
    host = str(config["hetzner"].get("ssh_host") or "<configure-hetzner-host>")
    remote_dataset = remote_dataset_path(config, meta["name"])
    remote_pipeline = remote_pipeline_path(config)
    pgm = f"python3 {shlex.quote(str(Path(__file__).resolve()))}{config_arg_for_command(config_path)}"
    offer_query = str(config["vast"]["offer_query"])
    disk_gb = int(config["vast"]["disk_gb"])
    image = str(config["vast"]["image"])
    is_merge_candidate = bool(manifest.get("merge_candidate")) or any(
        image_record.get("source_dataset") for image_record in manifest.get("images", [])
    )
    stage_command = (
        f"{pgm} stage-merge-hetzner --dataset {shlex.quote(meta['name'])}"
        if is_merge_candidate
        else f"{pgm} sync-hetzner --dataset {shlex.quote(meta['name'])} --working-only"
    )

    sync_marker = dataset / "cloud" / "hetzner_sync.json"
    prereqs = []
    for name in ("rsync", "ssh", "vastai"):
        if not tool_path(name):
            prereqs.append(f"Missing local tool: {name}")
    if not str(config["hetzner"].get("ssh_host") or "").strip():
        prereqs.append("Hetzner ssh_host is not configured.")
    if not sync_marker.exists():
        prereqs.append("Dataset has not been synced to Hetzner yet.")
    if not qc_report.get("passed"):
        prereqs.append("QC report did not pass.")

    prereq_lines = "\n".join(f"- {item}" for item in prereqs) if prereqs else "- None"
    remote_env = "\n".join(
        [
            f"export PGM_HETZNER_HOST={shlex.quote(host)}",
            f"export PGM_HETZNER_ROOT={shlex.quote(str(config['hetzner']['remote_root']))}",
            f"export PGM_DATASET={shlex.quote(meta['name'])}",
            f"export PGM_TARGET={shlex.quote(target)}",
        ]
    )

    return f"""# Cloud Plan: {meta['name']}

Generated: {utc_now()}

## Dataset

- Type: `{meta['dataset_type']}`
- Target: `{target}`
- Images: `{manifest['image_count']}`
- Raw size: `{human_bytes(manifest['raw_total_bytes'])}`
- Estimated cloud working size: `{human_bytes(estimated_bytes)}` ({factor})
- Local dataset: `{dataset}`
- Hetzner dataset: `{host}:{remote_dataset}`
- Hetzner pipeline scripts: `{host}:{remote_pipeline}`

## Current Gates

- QC passed: `{qc_report.get('passed')}`
- QC warnings: `{qc_report.get('summary', {}).get('warning_count')}`
- QC fatal issues: `{qc_report.get('summary', {}).get('fatal_count')}`

## Missing Prerequisites

{prereq_lines}

## Commands

Stage to Hetzner:

```sh
{stage_command}
```

Build and stage the GPU job package:

```sh
{pgm} job-package --dataset {shlex.quote(meta['name'])} --target {shlex.quote(target)} --sync-hetzner
```

Search Vast offers:

```sh
vastai search offers {shlex.quote(offer_query)}
```

Launch a selected Vast offer:

```sh
{pgm} vast-run --dataset {shlex.quote(meta['name'])} --target {shlex.quote(target)} --offer-id OFFER_ID --confirm-cost
```

Expected Vast image and disk:

```text
image={image}
disk_gb={disk_gb}
```

Run on the Vast instance after SSH access and Hetzner credentials are ready:

```sh
{remote_env}
export PGM_JOB_ID={shlex.quote(meta['name'] + '-' + target + '-JOBSTAMP')}
export PGM_WORK_ROOT=/workspace/whatwesee

mkdir -p "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID"
rsync -aP --whole-file --inplace --partial "$PGM_HETZNER_HOST:$PGM_HETZNER_ROOT/jobs/$PGM_JOB_ID/" "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/bootstrap-vast.sh"
bash "$PGM_WORK_ROOT/jobs/$PGM_JOB_ID/scripts/run-job.sh"
```

The generated package includes shared `scripts/gpu/` preflight/bootstrap helpers
when this repo-level GPU runtime is present. Jobs that run new sparse or dense
COLMAP work require CUDA COLMAP. A splat-only package with a staged promoted
`colmap/sparse/0` model can skip the CUDA COLMAP build and reuse that sparse
foundation. `run-job.sh` pulls inputs, verifies readiness, runs the selected
target, and syncs outputs back. For manual diagnostics, run `pull-inputs.sh`
and `verify-ready.sh` first, then start `run-job.sh` with
`PGM_SKIP_PULL=1 PGM_SKIP_VERIFY=1`.

Mirror Hetzner results locally after the cloud job completes:

```sh
{pgm} sync-results --dataset {shlex.quote(meta['name'])}
```

## Retention

- Hetzner: `{config['retention']['hetzner']}`
- Vast: `{config['retention']['vast']}`
"""


def cmd_cloud_plan(args: argparse.Namespace, config: dict[str, Any], config_path: Path | None) -> int:
    if args.target not in {"mesh", "splat", "both"}:
        raise UserError("--target must be mesh, splat, or both")
    dataset, meta = require_dataset(config, args.dataset)
    manifest = load_manifest(dataset)
    qc_report = load_qc_report(dataset)
    if not qc_report.get("passed"):
        raise UserError("QC report failed. Fix fatal issues before planning cloud work.")
    markdown = cloud_plan_markdown(args, config, config_path, dataset, meta, manifest, qc_report)
    path = dataset / "reports" / "cloud_plan.md"
    path.write_text(markdown, encoding="utf-8")
    print(f"Wrote cloud plan: {path}")
    print(markdown)
    return 0


def cmd_vast_run(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    load_manifest(dataset)
    qc_report = load_qc_report(dataset)
    if not qc_report.get("passed"):
        raise UserError("QC report failed. Refusing to launch paid GPU work.")

    sync_marker = dataset / "cloud" / "hetzner_sync.json"
    if not sync_marker.exists():
        raise UserError("Dataset has not been synced to Hetzner. Run sync-hetzner first.")
    if not tool_path("vastai"):
        raise UserError("vastai CLI is not installed or not on PATH.")
    if not args.offer_id:
        query = str(config["vast"]["offer_query"])
        print(f"Select an offer first:\n\nvastai search offers {shlex.quote(query)}")
        return 2
    if not args.confirm_cost and not args.dry_run:
        raise UserError("Refusing to create a paid Vast instance without --confirm-cost.")

    image = str(config["vast"]["image"])
    disk_gb = str(args.disk_gb or config["vast"]["disk_gb"])
    onstart = (
        "bash -lc "
        + shlex.quote(
            "apt-get update && "
            "apt-get install -y rsync openssh-client git curl ca-certificates && "
            "mkdir -p /workspace/whatwesee && "
            "echo 'Vast instance ready. Sync or mount Hetzner credentials, then run setup-vast.sh and run-cloud-job.sh.'"
        )
    )
    command = [
        "vastai",
        "create",
        "instance",
        str(args.offer_id),
        "--image",
        image,
        "--disk",
        disk_gb,
        "--ssh",
        "--direct",
        "--onstart-cmd",
        onstart,
    ]
    print(shell_join(command))
    launch_record: dict[str, Any] = {
        "dataset": meta["name"],
        "target": args.target,
        "created_at": utc_now(),
        "command": command,
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        json_write(dataset / "cloud" / "vast_launch_dry_run.json", launch_record)
        return 0

    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    launch_record["returncode"] = proc.returncode
    launch_record["stdout"] = proc.stdout
    launch_record["stderr"] = proc.stderr
    json_write(dataset / "cloud" / f"vast_launch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", launch_record)
    if proc.returncode != 0:
        raise UserError(f"vastai create instance failed:\n{proc.stderr or proc.stdout}")
    print(proc.stdout.strip())
    return 0


def cmd_sync_results(args: argparse.Namespace, config: dict[str, Any]) -> int:
    dataset, meta = require_dataset(config, args.dataset)
    host, _root = require_hetzner(config)
    remote_dataset = remote_dataset_path(config, meta["name"])
    command = [
        *rsync_base_args(config, args.dry_run),
        f"{host}:{remote_dataset}/",
        f"{dataset}/",
    ]
    print(shell_join(command))
    if args.dry_run:
        return 0
    subprocess.run(command, check=True)
    marker = {
        "dataset": meta["name"],
        "synced_at": utc_now(),
        "remote_dataset": remote_dataset,
        "local_dataset": str(dataset),
    }
    json_write(dataset / "cloud" / "results_sync.json", marker)
    print(f"Synced results from {host}:{remote_dataset}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="What We See photogrammetry pipeline CLI")
    parser.add_argument("--config", help="Path to pipeline TOML config")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-dataset", help="Create a dataset directory skeleton")
    init.add_argument("--name", required=True)
    init.add_argument("--type", required=True, choices=["object", "space", "mixed"])

    ingest = sub.add_parser("ingest", help="Copy photos into raw/working, extract EXIF, and write manifest")
    ingest.add_argument("--dataset", required=True)
    ingest.add_argument("--source", required=True)

    convert = sub.add_parser("convert-raw", help="Convert archived Canon RAW files into working images")
    convert.add_argument("--dataset", required=True)
    convert.add_argument("--converter", choices=["sips", "dcraw_emu"], default="sips")
    convert.add_argument("--format", choices=["jpeg", "tiff"], default="jpeg", help="Working image format; JPEG is the default")
    convert.add_argument("--quality", type=int, default=100, help="JPEG quality for sips conversion, 1-100")
    convert.add_argument("--overwrite", action="store_true", help="Regenerate working images that already exist")
    convert.add_argument(
        "--include-with-sidecars",
        action="store_true",
        help="Also convert RAW files that already have matching working JPEG/TIFF names",
    )
    convert.add_argument("--limit", type=int, help="Convert only the first N selected RAW files")
    convert.add_argument("--dry-run", action="store_true", help="Print conversions without writing working images")

    normalize = sub.add_parser("normalize-working", help="Convert HEIC/HEIF working images to JPEG quality 100")
    normalize.add_argument("--dataset", required=True)
    normalize.add_argument("--quality", type=int, default=100, help="JPEG quality for sips conversion, 1-100")
    normalize.add_argument("--overwrite", action="store_true", help="Regenerate normalized JPEGs that already exist")
    normalize.add_argument("--keep-source-working", action="store_true", help="Keep HEIC/HEIF files in working/images after conversion")
    normalize.add_argument("--limit", type=int, help="Normalize only the first N selected files")
    normalize.add_argument("--dry-run", action="store_true", help="Print conversions without writing JPEGs")

    merge = sub.add_parser("merge-candidate", help="Create a local mixed dataset from QC-passed source datasets")
    merge.add_argument("--name", required=True, help="Target merge dataset name")
    merge.add_argument("--source", required=True, action="append", help="Source dataset name; pass once per source")
    merge.add_argument("--profile", choices=["all", "clean", "no-ultrawide"], default="clean")
    merge.add_argument("--overwrite", action="store_true", help="Rebuild the target dataset if it already exists")

    qc = sub.add_parser("qc", help="Run local readability, duplicate, EXIF, blur, and exposure checks")
    qc.add_argument("--dataset", required=True)

    sync_h = sub.add_parser("sync-hetzner", help="Sync dataset and remote scripts to Hetzner")
    sync_h.add_argument("--dataset", required=True)
    sync_h.add_argument("--working-only", action="store_true", help="Stage only working images, manifests, reports, logs, and cloud metadata; exclude raw originals")
    sync_h.add_argument("--dry-run", action="store_true", help="Print commands only")

    promote = sub.add_parser("promote-colmap", help="Promote a local COLMAP baseline into DATASET/colmap for cloud reuse")
    promote.add_argument("--dataset", required=True)
    promote.add_argument("--bench-run", required=True, help="Run name under DATASET/benchmarks/")
    promote.add_argument("--mapper", choices=["best", "global", "incremental"], default="best")
    promote.add_argument("--model-id", default="0")
    promote.add_argument("--overwrite", action="store_true", help="Replace an existing promoted model")

    stage_merge = sub.add_parser("stage-merge-hetzner", help="Stage a merge candidate to Hetzner using remote hardlinks from staged source datasets")
    stage_merge.add_argument("--dataset", required=True)
    stage_merge.add_argument("--dry-run", action="store_true", help="Print commands only")

    cloud = sub.add_parser("cloud-plan", help="Generate the manual cloud execution plan")
    cloud.add_argument("--dataset", required=True)
    cloud.add_argument("--target", required=True, choices=["mesh", "splat", "both"])

    job = sub.add_parser("job-package", help="Build and optionally stage a self-contained Vast GPU job bundle")
    job.add_argument("--dataset", required=True)
    job.add_argument("--target", required=True, choices=["mesh", "splat", "both"])
    job.add_argument("--name", help="Stable job id; defaults to DATASET-TARGET-UTCSTAMP")
    job.add_argument("--evidence-package", help="Evidence package name to sync as metadata/reference context")
    job.add_argument("--evidence-remote-root", default="/srv/staging/evidence", help="Hetzner evidence root containing packages/")
    job.add_argument("--work-root", help="GPU instance work root; defaults to vast.remote_workdir")
    job.add_argument("--disk-gb", type=int, help="Disk size used in the job metadata")
    job.add_argument("--splat-iterations", type=int, default=30000, help="Splatfacto max iterations")
    job.add_argument("--uv-concurrent-downloads", type=int, default=16)
    job.add_argument("--uv-concurrent-builds", type=int, default=8)
    job.add_argument("--uv-concurrent-installs", type=int, default=8)
    job.add_argument("--sync-hetzner", action="store_true", help="Stage the job bundle under REMOTE_ROOT/jobs/JOB_ID")
    job.add_argument("--overwrite", action="store_true", help="Rebuild an existing local job bundle")
    job.add_argument("--dry-run", action="store_true", help="Print sync commands without transferring the job bundle")

    vast = sub.add_parser("vast-run", help="Create a manually approved Vast.ai instance")
    vast.add_argument("--dataset", required=True)
    vast.add_argument("--target", required=True, choices=["mesh", "splat", "both"])
    vast.add_argument("--offer-id", help="Vast offer id selected from vastai search offers")
    vast.add_argument("--disk-gb", type=int, help="Override configured Vast disk size")
    vast.add_argument("--confirm-cost", action="store_true", help="Required for actual paid instance creation")
    vast.add_argument("--dry-run", action="store_true", help="Print and record the launch command only")

    results = sub.add_parser("sync-results", help="Sync Hetzner dataset outputs back to local storage")
    results.add_argument("--dataset", required=True)
    results.add_argument("--dry-run", action="store_true", help="Print commands only")

    return parser


def run(args: argparse.Namespace, config: dict[str, Any], config_path: Path | None) -> int:
    if args.command == "init-dataset":
        return cmd_init_dataset(args, config)
    if args.command == "ingest":
        return cmd_ingest(args, config)
    if args.command == "convert-raw":
        return cmd_convert_raw(args, config)
    if args.command == "normalize-working":
        return cmd_normalize_working(args, config)
    if args.command == "merge-candidate":
        return cmd_merge_candidate(args, config)
    if args.command == "qc":
        return cmd_qc(args, config)
    if args.command == "sync-hetzner":
        return cmd_sync_hetzner(args, config)
    if args.command == "promote-colmap":
        return cmd_promote_colmap(args, config)
    if args.command == "stage-merge-hetzner":
        return cmd_stage_merge_hetzner(args, config)
    if args.command == "cloud-plan":
        return cmd_cloud_plan(args, config, config_path)
    if args.command == "job-package":
        return cmd_job_package(args, config)
    if args.command == "vast-run":
        return cmd_vast_run(args, config)
    if args.command == "sync-results":
        return cmd_sync_results(args, config)
    raise UserError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config, config_path = load_config(args.config)
        return run(args, config, config_path)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed: {shell_join([str(part) for part in exc.cmd])}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
