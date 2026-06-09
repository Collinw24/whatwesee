#!/usr/bin/env python3
"""Run local CPU COLMAP/GLOMAP-style sparse baselines for a dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any


DEFAULT_DATA_ROOT = "~/whatwesee_photogrammetry_data"


class UserError(RuntimeError):
    """Expected user-facing CLI error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_name(name: str) -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if not name or name in {".", ".."} or any(char not in allowed for char in name):
        raise UserError("Names may only contain letters, numbers, dot, dash, and underscore.")


def natural_key(value: str) -> list[int | str]:
    parts: list[int | str] = []
    for part in re.split(r"(\d+)", value.lower()):
        if part.isdigit():
            parts.append(int(part))
        elif part:
            parts.append(part)
    return parts


def data_root_from_args(args: argparse.Namespace) -> Path:
    root = args.data_root or os.environ.get("PGM_DATA_ROOT") or DEFAULT_DATA_ROOT
    return Path(root).expanduser().resolve()


def dataset_path(args: argparse.Namespace) -> Path:
    validate_name(args.dataset)
    path = data_root_from_args(args) / args.dataset
    if not (path / "manifests" / "manifest.json").exists():
        raise UserError(f"Dataset manifest not found: {path / 'manifests' / 'manifest.json'}")
    return path


def load_manifest(dataset: Path) -> dict[str, Any]:
    return json_read(dataset / "manifests" / "manifest.json")


def image_sort_key(image: dict[str, Any]) -> tuple[list[int | str], list[int | str]]:
    source = image.get("source_dataset") or ""
    rel = image.get("source_relative_path") or image.get("relative_path") or ""
    return natural_key(str(source)), natural_key(str(rel))


def select_images(args: argparse.Namespace, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = list(manifest.get("images", []))
    if args.source_dataset:
        allowed = set(args.source_dataset)
        selected = [image for image in selected if image.get("source_dataset") in allowed]
    if args.camera_model_contains:
        needle = args.camera_model_contains.lower()
        selected = [image for image in selected if needle in str(image.get("camera_model") or "").lower()]
    if args.lens_contains:
        needle = args.lens_contains.lower()
        selected = [image for image in selected if needle in str(image.get("lens_model") or "").lower()]
    if args.min_focal_length is not None:
        selected = [image for image in selected if numeric(image.get("focal_length")) is not None and numeric(image.get("focal_length")) >= args.min_focal_length]
    if args.max_focal_length is not None:
        selected = [image for image in selected if numeric(image.get("focal_length")) is not None and numeric(image.get("focal_length")) <= args.max_focal_length]

    selected.sort(key=image_sort_key)
    if args.start < 0:
        raise UserError("--start must be >= 0")
    if args.stride < 1:
        raise UserError("--stride must be >= 1")
    selected = selected[args.start :: args.stride]
    if args.limit:
        selected = selected[: args.limit]
    if len(selected) < 2:
        raise UserError("At least two images are required for a COLMAP baseline.")
    return selected


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def command_string(command: list[str | Path]) -> str:
    return " ".join(sh_quote(str(part)) for part in command)


def sh_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=,+@%-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def colmap_path(args: argparse.Namespace) -> str:
    if args.colmap_bin:
        path = shutil.which(args.colmap_bin) or args.colmap_bin
    else:
        path = shutil.which("colmap") or ""
    if not path:
        raise UserError("COLMAP is not installed or not on PATH. On Apple Silicon, run: brew install colmap")
    return path


def run_logged(command: list[str | Path], log_path: Path, cwd: Path | None = None) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    started_monotonic = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {command_string(command)}\n")
        log.flush()
        proc = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd) if cwd else None,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    elapsed = time.monotonic() - started_monotonic
    return {
        "command": [str(part) for part in command],
        "started_at": started,
        "finished_at": utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "returncode": proc.returncode,
        "log": str(log_path),
    }


def require_success(result: dict[str, Any], stage: str) -> None:
    if result["returncode"] != 0:
        raise UserError(f"{stage} failed with exit code {result['returncode']}. See {result['log']}")


def colmap_help(colmap: str) -> str:
    proc = subprocess.run([colmap, "-h"], check=False, capture_output=True, text=True)
    return (proc.stdout or proc.stderr or "").strip()


def build_feature_command(args: argparse.Namespace, colmap: str, run_dir: Path, dataset: Path) -> list[str | Path]:
    return [
        colmap,
        "feature_extractor",
        "--database_path",
        run_dir / "database.db",
        "--image_path",
        dataset / "working" / "images",
        "--image_list_path",
        run_dir / "image_list.txt",
        "--ImageReader.single_camera",
        "1" if args.single_camera else "0",
        "--FeatureExtraction.use_gpu",
        "1" if args.use_gpu else "0",
        "--FeatureExtraction.num_threads",
        str(args.threads),
        "--FeatureExtraction.max_image_size",
        str(args.max_image_size),
        "--SiftExtraction.max_num_features",
        str(args.max_num_features),
    ]


def build_match_command(args: argparse.Namespace, colmap: str, run_dir: Path) -> list[str | Path]:
    base: list[str | Path] = [
        colmap,
        "exhaustive_matcher" if args.matcher == "exhaustive" else "sequential_matcher",
        "--database_path",
        run_dir / "database.db",
        "--FeatureMatching.use_gpu",
        "1" if args.use_gpu else "0",
        "--FeatureMatching.num_threads",
        str(args.threads),
        "--FeatureMatching.max_num_matches",
        str(args.max_num_matches),
    ]
    if args.matcher == "exhaustive":
        base.extend(["--ExhaustiveMatching.block_size", str(args.exhaustive_block_size)])
    else:
        base.extend(["--SequentialMatching.overlap", str(args.sequential_overlap)])
    return base


def build_mapper_command(args: argparse.Namespace, colmap: str, run_dir: Path, dataset: Path) -> list[str | Path]:
    return [
        colmap,
        "mapper",
        "--database_path",
        run_dir / "database.db",
        "--image_path",
        dataset / "working" / "images",
        "--output_path",
        run_dir / "sparse_incremental",
        "--Mapper.image_list_path",
        run_dir / "image_list.txt",
        "--Mapper.num_threads",
        str(args.threads),
        "--Mapper.ba_use_gpu",
        "1" if args.use_gpu else "0",
    ]


def build_global_mapper_command(args: argparse.Namespace, colmap: str, run_dir: Path, dataset: Path) -> list[str | Path]:
    return [
        colmap,
        "global_mapper",
        "--database_path",
        run_dir / "database.db",
        "--image_path",
        dataset / "working" / "images",
        "--output_path",
        run_dir / "sparse_global",
        "--GlobalMapper.image_list_path",
        run_dir / "image_list.txt",
        "--GlobalMapper.num_threads",
        str(args.threads),
        "--GlobalMapper.gp_use_gpu",
        "1" if args.use_gpu else "0",
        "--GlobalMapper.ba_ceres_use_gpu",
        "1" if args.use_gpu else "0",
    ]


def database_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    metrics: dict[str, Any] = {}
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        for key, query in {
            "images": "select count(*) from images",
            "matches": "select count(*) from matches",
            "two_view_geometries": "select count(*) from two_view_geometries",
            "two_view_geometries_nonempty": "select count(*) from two_view_geometries where rows > 0",
            "two_view_inlier_rows": "select coalesce(sum(rows),0) from two_view_geometries",
        }.items():
            metrics[key] = cursor.execute(query).fetchone()[0]
    return metrics


def parse_analyzer_output(text: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {"raw": text}
    mappings = {
        "registered_images": r"Registered images:\s+(\d+)",
        "images": r"Images:\s+(\d+)",
        "points": r"Points:\s+(\d+)",
        "observations": r"Observations:\s+(\d+)",
        "mean_track_length": r"Mean track length:\s+([0-9.]+)",
        "mean_observations_per_image": r"Mean observations per image:\s+([0-9.]+)",
        "mean_reprojection_error_px": r"Mean reprojection error:\s+([0-9.]+)px",
    }
    for key, pattern in mappings.items():
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1)
        metrics[key] = float(value) if "." in value else int(value)
    return metrics


def model_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        [item for item in root.iterdir() if item.is_dir() and (item / "images.bin").exists()],
        key=lambda item: natural_key(item.name),
    )


def registered_names_from_txt(txt_path: Path) -> list[str]:
    images_txt = txt_path / "images.txt"
    if not images_txt.exists():
        return []
    lines = [line for line in images_txt.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    names: list[str] = []
    for line in lines[::2]:
        parts = line.split()
        if len(parts) >= 10:
            names.append(parts[9])
    return names


def registration_by_source(selected: list[dict[str, Any]], registered_names: list[str]) -> dict[str, Any]:
    registered = set(registered_names)
    source_totals: dict[str, int] = {}
    source_registered: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    for image in selected:
        source = str(image.get("source_dataset") or "unknown")
        rel = str(image["relative_path"])
        source_totals[source] = source_totals.get(source, 0) + 1
        if rel in registered:
            source_registered[source] = source_registered.get(source, 0) + 1
        else:
            missing.setdefault(source, []).append(rel)
    by_source = {
        source: {
            "selected": total,
            "registered": source_registered.get(source, 0),
            "missing": total - source_registered.get(source, 0),
        }
        for source, total in sorted(source_totals.items())
    }
    return {
        "registered_names": registered_names,
        "by_source": by_source,
        "missing_by_source": missing,
    }


def analyze_models(colmap: str, run_dir: Path, mapper_names: list[str], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    exports = run_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    roots = {
        "incremental": run_dir / "sparse_incremental",
        "global": run_dir / "sparse_global",
    }
    for mapper_name in mapper_names:
        for model_dir in model_dirs(roots[mapper_name]):
            analyzer = subprocess.run(
                [colmap, "model_analyzer", "--path", str(model_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            text = (analyzer.stdout or "") + (analyzer.stderr or "")
            record = {
                "mapper": mapper_name,
                "path": str(model_dir),
                "model_id": model_dir.name,
                "analyzer_returncode": analyzer.returncode,
                "metrics": parse_analyzer_output(text),
            }
            prefix = f"sparse_{mapper_name}_{model_dir.name}"
            ply_path = exports / f"{prefix}.ply"
            txt_path = exports / f"{prefix}_txt"
            txt_path.mkdir(exist_ok=True)
            ply = run_logged(
                [colmap, "model_converter", "--input_path", model_dir, "--output_path", ply_path, "--output_type", "PLY"],
                run_dir / "logs" / f"export_{prefix}_ply.log",
            )
            txt = run_logged(
                [colmap, "model_converter", "--input_path", model_dir, "--output_path", txt_path, "--output_type", "TXT"],
                run_dir / "logs" / f"export_{prefix}_txt.log",
            )
            record["exports"] = {
                "ply": str(ply_path) if ply["returncode"] == 0 else None,
                "txt": str(txt_path) if txt["returncode"] == 0 else None,
                "ply_returncode": ply["returncode"],
                "txt_returncode": txt["returncode"],
            }
            if txt["returncode"] == 0:
                record["registration"] = registration_by_source(selected, registered_names_from_txt(txt_path))
            results.append(record)
    return results


def best_model(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not models:
        return None
    return max(
        models,
        key=lambda item: (
            int(item.get("metrics", {}).get("registered_images", 0)),
            int(item.get("metrics", {}).get("points", 0)),
            -float(item.get("metrics", {}).get("mean_reprojection_error_px", 999999.0)),
        ),
    )


def write_markdown_report(run_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        f"# Local COLMAP Baseline: {report['run_name']}",
        "",
        f"- Dataset: `{report['dataset']}`",
        f"- Selected images: `{report['selection']['selected_count']}`",
        f"- Matcher: `{report['settings']['matcher']}`",
        f"- Mappers: `{', '.join(report['settings']['mappers'])}`",
        f"- COLMAP: `{report['tools']['colmap']['first_line']}`",
        f"- GLOMAP strategy: `COLMAP global_mapper`",
        "",
        "## Database",
        "",
    ]
    for key, value in report.get("database", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Models", "", "| Mapper | Model | Registered | Points | Mean error | PLY |", "| --- | --- | ---: | ---: | ---: | --- |"])
    for model in report.get("models", []):
        metrics = model.get("metrics", {})
        exports = model.get("exports", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    str(model.get("mapper")),
                    str(model.get("model_id")),
                    str(metrics.get("registered_images", "")),
                    str(metrics.get("points", "")),
                    str(metrics.get("mean_reprojection_error_px", "")),
                    str(exports.get("ply") or ""),
                ]
            )
            + " |"
        )
    source_rows: list[str] = []
    for model in report.get("models", []):
        registration = model.get("registration", {}).get("by_source", {})
        for source, counts in registration.items():
            source_rows.append(
                "| "
                + " | ".join(
                    [
                        str(model.get("mapper")),
                        str(model.get("model_id")),
                        str(source),
                        f"{counts.get('registered')}/{counts.get('selected')}",
                        str(counts.get("missing")),
                    ]
                )
                + " |"
            )
    if source_rows:
        lines.extend(
            [
                "",
                "## Source Registration",
                "",
                "| Mapper | Model | Source | Registered | Missing |",
                "| --- | --- | --- | ---: | ---: |",
                *source_rows,
            ]
        )
    best = report.get("best_model")
    if best:
        lines.extend(
            [
                "",
                "## Best Model",
                "",
                f"- Mapper: `{best.get('mapper')}`",
                f"- Model path: `{best.get('path')}`",
                f"- PLY: `{best.get('exports', {}).get('ply')}`",
            ]
        )
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(args: argparse.Namespace) -> int:
    dataset = dataset_path(args)
    manifest = load_manifest(dataset)
    selected = select_images(args, manifest)
    validate_name(args.name)
    run_dir = dataset / "benchmarks" / args.name
    if run_dir.exists() and not args.overwrite and not args.dry_run:
        raise UserError(f"Run directory already exists: {run_dir}. Use --overwrite to rebuild it.")

    colmap = colmap_path(args) if not args.dry_run else (args.colmap_bin or "colmap")
    mappers = ["incremental", "global"] if args.mapper == "both" else [args.mapper]
    feature_command = build_feature_command(args, colmap, run_dir, dataset)
    match_command = build_match_command(args, colmap, run_dir)
    mapper_commands = []
    if "incremental" in mappers:
        mapper_commands.append(("mapper", build_mapper_command(args, colmap, run_dir, dataset)))
    if "global" in mappers:
        mapper_commands.append(("global_mapper", build_global_mapper_command(args, colmap, run_dir, dataset)))

    if args.dry_run:
        print(f"Dataset: {dataset}")
        print(f"Selected images: {len(selected)}")
        print(f"Run directory: {run_dir}")
        print(command_string(feature_command))
        print(command_string(match_command))
        for _name, command in mapper_commands:
            print(command_string(command))
        return 0

    if run_dir.exists() and args.overwrite:
        shutil.rmtree(run_dir)
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "sparse_incremental").mkdir(exist_ok=True)
    (run_dir / "sparse_global").mkdir(exist_ok=True)
    image_list = [str(image["relative_path"]) for image in selected]
    (run_dir / "image_list.txt").write_text("\n".join(image_list) + "\n", encoding="utf-8")
    selection = {
        "dataset": args.dataset,
        "selected_count": len(selected),
        "source_datasets": sorted({str(image.get("source_dataset")) for image in selected if image.get("source_dataset")}),
        "first_image": image_list[0],
        "last_image": image_list[-1],
        "images": selected,
    }
    json_write(run_dir / "selection.json", selection)

    stages: list[dict[str, Any]] = []
    result = run_logged(feature_command, run_dir / "logs" / "feature_extractor.log")
    stages.append({"stage": "feature_extractor", **result})
    require_success(result, "feature extraction")
    result = run_logged(match_command, run_dir / "logs" / f"{args.matcher}_matcher.log")
    stages.append({"stage": f"{args.matcher}_matcher", **result})
    require_success(result, "feature matching")

    for name, command in mapper_commands:
        result = run_logged(command, run_dir / "logs" / f"{name}.log")
        stages.append({"stage": name, **result})
        require_success(result, name)

    models = analyze_models(colmap, run_dir, mappers, selected)
    report = {
        "schema_version": 1,
        "run_name": args.name,
        "dataset": args.dataset,
        "created_at": utc_now(),
        "run_dir": str(run_dir),
        "selection": {key: value for key, value in selection.items() if key != "images"},
        "settings": {
            "matcher": args.matcher,
            "mappers": mappers,
            "threads": args.threads,
            "max_image_size": args.max_image_size,
            "max_num_features": args.max_num_features,
            "max_num_matches": args.max_num_matches,
            "use_gpu": args.use_gpu,
            "single_camera": args.single_camera,
        },
        "tools": {
            "colmap": {
                "path": colmap,
                "first_line": (colmap_help(colmap).splitlines() or [""])[0],
                "glomap_note": "Standalone GLOMAP is deprecated upstream; use COLMAP global_mapper for local baselines.",
            }
        },
        "stages": stages,
        "database": database_metrics(run_dir / "database.db"),
        "models": models,
        "best_model": best_model(models),
    }
    json_write(run_dir / "report.json", report)
    write_markdown_report(run_dir, report)
    print(f"Wrote local COLMAP baseline: {run_dir / 'report.md'}")
    best = report["best_model"]
    if best:
        registered = best.get("metrics", {}).get("registered_images", 0)
        print(f"Best model: {best['mapper']}/{best['model_id']} registered {registered}/{len(selected)} images")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", help=f"Photogrammetry data root. Default: {DEFAULT_DATA_ROOT}")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--name", required=True, help="Benchmark run name under DATASET/benchmarks/")
    parser.add_argument("--source-dataset", action="append", help="Filter merged datasets by source_dataset. Repeatable.")
    parser.add_argument("--camera-model-contains", help="Filter by camera model substring.")
    parser.add_argument("--lens-contains", help="Filter by lens model substring.")
    parser.add_argument("--min-focal-length", type=float)
    parser.add_argument("--max-focal-length", type=float)
    parser.add_argument("--start", type=int, default=0, help="Start index after filtering and sorting.")
    parser.add_argument("--limit", type=int, help="Limit selected image count.")
    parser.add_argument("--stride", type=int, default=1, help="Keep every Nth image after filtering.")
    parser.add_argument("--matcher", choices=["exhaustive", "sequential"], default="exhaustive")
    parser.add_argument("--mapper", choices=["incremental", "global", "both"], default="both")
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--max-image-size", type=int, default=2400)
    parser.add_argument("--max-num-features", type=int, default=4096)
    parser.add_argument("--max-num-matches", type=int, default=8192)
    parser.add_argument("--exhaustive-block-size", type=int, default=25)
    parser.add_argument("--sequential-overlap", type=int, default=20)
    parser.add_argument("--single-camera", action="store_true")
    parser.add_argument("--use-gpu", action="store_true", help="Use COLMAP GPU flags. Leave off for Homebrew Apple Silicon COLMAP.")
    parser.add_argument("--colmap-bin", help="COLMAP binary path or command.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_benchmark(args)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
