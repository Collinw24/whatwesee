import base64
import contextlib
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PGM_PATH = ROOT / "scripts" / "pgm.py"

spec = importlib.util.spec_from_file_location("pgm", PGM_PATH)
pgm = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pgm)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class PhotogrammetryCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_root = self.root / "data"
        self.source = self.root / "source"
        self.source.mkdir()
        self.config = self.root / "pipeline.toml"
        self.config.write_text(
            f"""
[local]
data_root = "{self.data_root}"
preview_max_width = 64

[hetzner]
ssh_host = "hetzner-test"
remote_root = "/srv/whatwesee-photogrammetry-test"

[vast]
offer_query = "verified=true rentable=true reliability > 0.98 gpu_ram >= 48"
disk_gb = 64
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return pgm.main(["--config", str(self.config), *args])

    def write_fake_dataset(self, name, images, warnings=None):
        dataset = self.data_root / name
        pgm.ensure_dataset_dirs(dataset)
        warnings = warnings or []
        (dataset / "manifests" / "dataset.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "dataset_type": "mixed",
                    "created_at": "2026-04-28T00:00:00+00:00",
                    "data_root": str(self.data_root),
                    "pipeline_version": 1,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        records = []
        for item in images:
            rel = item["relative_path"]
            image_path = dataset / "working" / "images" / rel
            preview_path = dataset / "working" / "previews" / Path(rel).with_suffix(".jpg")
            image_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(item.get("bytes", PNG_1X1))
            preview_path.write_bytes(PNG_1X1)
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            records.append(
                {
                    "id": digest[:16],
                    "relative_path": rel,
                    "raw_path": f"raw/{rel}",
                    "working_path": f"working/images/{rel}",
                    "preview_path": f"working/previews/{Path(rel).with_suffix('.jpg').as_posix()}",
                    "sha256": digest,
                    "bytes": image_path.stat().st_size,
                    "extension": ".jpg",
                    "camera_make": item.get("camera_make", "Apple"),
                    "camera_model": item.get("camera_model", "iPhone 12 Pro Max"),
                    "lens_model": item.get("lens_model", "wide"),
                    "focal_length": item.get("focal_length", 5.1),
                    "focal_length_35mm": item.get("focal_length_35mm", 26),
                    "width": item.get("width", 1),
                    "height": item.get("height", 1),
                }
            )

        manifest = {
            "schema_version": 1,
            "dataset": name,
            "dataset_type": "mixed",
            "created_at": "2026-04-28T00:00:00+00:00",
            "source": "test",
            "image_count": len(records),
            "raw_archive_count": 0,
            "raw_total_bytes": sum(record["bytes"] for record in records),
            "working_total_bytes": sum(record["bytes"] for record in records),
            "focal_groups": pgm.focal_groups(records),
            "preview_warnings": [],
            "tools": {},
            "raw_archive": [],
            "images": records,
        }
        (dataset / "manifests" / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        qc = {
            "schema_version": 1,
            "dataset": name,
            "dataset_type": "mixed",
            "created_at": "2026-04-28T00:00:00+00:00",
            "passed": True,
            "summary": {"image_count": len(records), "warning_count": len(warnings), "fatal_count": 0},
            "warnings": warnings,
            "fatal": [],
            "metrics": {},
        }
        (dataset / "reports" / "qc_report.json").write_text(json.dumps(qc) + "\n", encoding="utf-8")
        return dataset

    def test_init_ingest_qc_and_cloud_plan(self):
        (self.source / "a.png").write_bytes(PNG_1X1)
        (self.source / "nested").mkdir()
        (self.source / "nested" / "b.png").write_bytes(PNG_1X1)

        self.assertEqual(self.run_cli("init-dataset", "--name", "sample", "--type", "object"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "sample", "--source", str(self.source)), 0)
        self.assertEqual(self.run_cli("qc", "--dataset", "sample"), 0)
        self.assertEqual(self.run_cli("cloud-plan", "--dataset", "sample", "--target", "both"), 0)

        dataset = self.data_root / "sample"
        manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))
        qc_report = json.loads((dataset / "reports" / "qc_report.json").read_text(encoding="utf-8"))
        cloud_plan = dataset / "reports" / "cloud_plan.md"

        self.assertEqual(manifest["image_count"], 2)
        self.assertEqual(len(manifest["images"]), 2)
        self.assertTrue(qc_report["passed"])
        self.assertTrue(cloud_plan.exists())
        self.assertIn("vastai search offers", cloud_plan.read_text(encoding="utf-8"))

    def test_sync_hetzner_dry_run_does_not_require_network(self):
        (self.source / "a.png").write_bytes(PNG_1X1)

        self.assertEqual(self.run_cli("init-dataset", "--name", "syncsample", "--type", "mixed"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "syncsample", "--source", str(self.source)), 0)
        self.assertEqual(self.run_cli("sync-hetzner", "--dataset", "syncsample", "--dry-run"), 0)
        self.assertEqual(self.run_cli("sync-hetzner", "--dataset", "syncsample", "--working-only", "--dry-run"), 0)

    def test_canon_raw_is_archived_not_used_as_working_image(self):
        (self.source / "IMG_0001.JPG").write_bytes(PNG_1X1)
        (self.source / "IMG_0001.CR3").write_bytes(b"fake canon raw")

        self.assertEqual(self.run_cli("init-dataset", "--name", "canon", "--type", "mixed"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "canon", "--source", str(self.source)), 0)

        dataset = self.data_root / "canon"
        manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["image_count"], 1)
        self.assertEqual(manifest["raw_archive_count"], 1)
        self.assertEqual(manifest["images"][0]["raw_sidecar_path"], "raw/IMG_0001.CR3")
        self.assertFalse((dataset / "working" / "images" / "IMG_0001.CR3").exists())

    def test_convert_raw_dry_run_for_raw_only_dataset(self):
        (self.source / "IMG_0002.CR2").write_bytes(b"fake canon raw")

        self.assertEqual(self.run_cli("init-dataset", "--name", "rawonly", "--type", "mixed"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "rawonly", "--source", str(self.source)), 0)
        self.assertEqual(self.run_cli("convert-raw", "--dataset", "rawonly", "--dry-run"), 0)

        dataset = self.data_root / "rawonly"
        manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["image_count"], 0)
        self.assertEqual(manifest["raw_archive_count"], 1)

    def test_convert_raw_tiff_dry_run(self):
        (self.source / "IMG_0003.CR2").write_bytes(b"fake canon raw")

        self.assertEqual(self.run_cli("init-dataset", "--name", "rawtiff", "--type", "mixed"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "rawtiff", "--source", str(self.source)), 0)
        self.assertEqual(self.run_cli("convert-raw", "--dataset", "rawtiff", "--format", "tiff", "--dry-run"), 0)

    def test_normalize_working_dry_run_for_heic_dataset(self):
        (self.source / "IMG_0100.HEIC").write_bytes(b"fake heic")

        self.assertEqual(self.run_cli("init-dataset", "--name", "iphone", "--type", "mixed"), 0)
        self.assertEqual(self.run_cli("ingest", "--dataset", "iphone", "--source", str(self.source)), 0)
        self.assertEqual(self.run_cli("normalize-working", "--dataset", "iphone", "--dry-run"), 0)

        dataset = self.data_root / "iphone"
        manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["image_count"], 1)
        self.assertEqual(manifest["images"][0]["extension"], ".heic")

    def test_merge_candidate_no_ultrawide_excludes_warnings_and_iphone_ultrawide(self):
        self.write_fake_dataset(
            "canon-src",
            [
                {"relative_path": "canon_keep.jpg", "camera_make": "Canon", "camera_model": "EOS 5D Mark III", "lens_model": "EF100mm", "focal_length": 100},
                {"relative_path": "canon_dark.jpg", "camera_make": "Canon", "camera_model": "EOS 5D Mark III", "lens_model": "EF100mm", "focal_length": 100},
            ],
            warnings=[{"code": "possibly_underexposed", "image": "canon_dark.jpg"}],
        )
        self.write_fake_dataset(
            "iphone-src",
            [
                {"relative_path": "iphone_wide.jpg", "lens_model": "iPhone wide", "focal_length": 5.1},
                {"relative_path": "iphone_ultra.jpg", "lens_model": "iPhone ultra wide 1.54mm", "focal_length": 1.54},
            ],
        )

        self.assertEqual(
            self.run_cli(
                "merge-candidate",
                "--name",
                "merged",
                "--source",
                "canon-src",
                "--source",
                "iphone-src",
                "--profile",
                "no-ultrawide",
            ),
            0,
        )

        dataset = self.data_root / "merged"
        manifest = json.loads((dataset / "manifests" / "manifest.json").read_text(encoding="utf-8"))
        report = json.loads((dataset / "reports" / "merge_selection_report.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["image_count"], 2)
        self.assertEqual(report["excluded_by_reason"]["qc_warning:possibly_underexposed"], 1)
        self.assertEqual(report["excluded_by_reason"]["iphone_ultrawide"], 1)
        self.assertTrue(all("source_dataset" in image for image in manifest["images"]))
        self.assertTrue((dataset / "working" / "images" / "canon-src__canon_keep.jpg").exists())
        self.assertTrue((dataset / "working" / "images" / "iphone-src__iphone_wide.jpg").exists())

    def test_stage_merge_hetzner_dry_run_does_not_require_network(self):
        self.write_fake_dataset("a-src", [{"relative_path": "a.jpg"}])
        self.write_fake_dataset("b-src", [{"relative_path": "b.jpg"}])
        self.assertEqual(
            self.run_cli(
                "merge-candidate",
                "--name",
                "merged-stage",
                "--source",
                "a-src",
                "--source",
                "b-src",
                "--profile",
                "all",
            ),
            0,
        )
        self.assertEqual(self.run_cli("stage-merge-hetzner", "--dataset", "merged-stage", "--dry-run"), 0)

    def test_promote_colmap_copies_baseline_to_canonical_colmap_path(self):
        dataset = self.write_fake_dataset("promote-src", [{"relative_path": "a.jpg"}, {"relative_path": "b.jpg"}])
        model_dir = dataset / "benchmarks" / "local-run" / "sparse_global" / "0"
        model_dir.mkdir(parents=True)
        for name in ("cameras.bin", "images.bin", "points3D.bin"):
            (model_dir / name).write_bytes(f"fake {name}".encode("utf-8"))
        (dataset / "benchmarks" / "local-run" / "database.db").write_bytes(b"fake db")
        exports = dataset / "benchmarks" / "local-run" / "exports"
        exports.mkdir()
        (exports / "sparse_global_0.ply").write_text("ply\n", encoding="utf-8")
        report = {
            "schema_version": 1,
            "run_name": "local-run",
            "dataset": "promote-src",
            "best_model": {
                "mapper": "global",
                "model_id": "0",
                "path": str(model_dir),
                "metrics": {"registered_images": 2, "points": 10, "mean_reprojection_error_px": 0.4},
                "registration": {"by_source": {"unknown": {"selected": 2, "registered": 2, "missing": 0}}},
                "exports": {"ply": str(exports / "sparse_global_0.ply")},
            },
            "models": [],
        }
        (dataset / "benchmarks" / "local-run" / "report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")

        self.assertEqual(
            self.run_cli("promote-colmap", "--dataset", "promote-src", "--bench-run", "local-run"),
            0,
        )

        promoted = dataset / "colmap" / "sparse" / "0"
        promoted_report = json.loads((dataset / "reports" / "promoted_colmap.json").read_text(encoding="utf-8"))

        self.assertTrue((promoted / "cameras.bin").exists())
        self.assertTrue((dataset / "colmap" / "database.db").exists())
        self.assertTrue((dataset / "colmap" / "sparse.ply").exists())
        self.assertEqual(promoted_report["target_model_path"], "colmap/sparse/0")
        self.assertEqual(promoted_report["metrics"]["registered_images"], 2)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.run_cli("sync-hetzner", "--dataset", "promote-src", "--working-only", "--dry-run"), 0)
        self.assertIn("colmap/***", out.getvalue())

    def test_job_package_writes_gpu_handoff_without_copying_photos(self):
        dataset = self.write_fake_dataset("job-src", [{"relative_path": "a.jpg"}, {"relative_path": "b.jpg"}])
        (dataset / "cloud" / "hetzner_sync.json").write_text(
            json.dumps(
                {
                    "dataset": "job-src",
                    "remote_dataset": "/srv/whatwesee-photogrammetry-test/datasets/job-src",
                    "synced_at": "2026-04-28T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(
            self.run_cli(
                "job-package",
                "--dataset",
                "job-src",
                "--target",
                "both",
                "--name",
                "job-test",
                "--evidence-package",
                "evidence-test",
                "--evidence-remote-root",
                "/srv/evidence-test",
            ),
            0,
        )

        job_dir = dataset / "cloud" / "jobs" / "job-test"
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        image_index = json.loads((job_dir / "manifests" / "image_index.json").read_text(encoding="utf-8"))

        self.assertEqual(job["image_count"], 2)
        self.assertEqual(job["cost_controls"]["contains_photos"], False)
        self.assertEqual(job["artifact_contract"][0]["class"], "camera_poses")
        self.assertEqual(image_index["image_count"], 2)
        self.assertTrue((job_dir / "scripts" / "bootstrap-vast.sh").exists())
        self.assertTrue((job_dir / "scripts" / "pull-inputs.sh").exists())
        self.assertTrue((job_dir / "scripts" / "verify-ready.sh").exists())
        self.assertTrue((job_dir / "scripts" / "run-job.sh").exists())
        self.assertTrue((job_dir / "scripts" / "pipeline" / "run-colmap.sh").exists())
        self.assertTrue((job_dir / "scripts" / "gpu" / "preflight-gpu.sh").exists())
        self.assertTrue((job_dir / "scripts" / "gpu" / "build-colmap-cuda.sh").exists())
        self.assertTrue((job_dir / "checksums.sha256").exists())
        self.assertIn("gsplat==1.4.0", (job_dir / "downloads" / "pip-packages.txt").read_text(encoding="utf-8"))
        self.assertIn("parallel -0", (job_dir / "scripts" / "pull-inputs.sh").read_text(encoding="utf-8"))
        self.assertIn("PGM_COLMAP_REQUIRE_CUDA=1", (job_dir / "job.env").read_text(encoding="utf-8"))
        self.assertIn("aria2", (job_dir / "README.md").read_text(encoding="utf-8"))
        self.assertFalse((job_dir / "working" / "images").exists())

    def test_splat_job_package_reuses_promoted_colmap_without_cuda_colmap_build(self):
        dataset = self.write_fake_dataset("job-precompute", [{"relative_path": "a.jpg"}, {"relative_path": "b.jpg"}])
        promoted = dataset / "colmap" / "sparse" / "0"
        promoted.mkdir(parents=True)
        for name in ("cameras.bin", "images.bin", "points3D.bin"):
            (promoted / name).write_bytes(f"fake {name}".encode("utf-8"))
        (dataset / "reports" / "promoted_colmap.json").write_text(
            json.dumps({"schema_version": 1, "dataset": "job-precompute", "target_model_path": "colmap/sparse/0"}) + "\n",
            encoding="utf-8",
        )
        (dataset / "cloud" / "hetzner_sync.json").write_text(
            json.dumps(
                {
                    "dataset": "job-precompute",
                    "remote_dataset": "/srv/whatwesee-photogrammetry-test/datasets/job-precompute",
                    "synced_at": "2026-04-28T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(
            self.run_cli("job-package", "--dataset", "job-precompute", "--target", "splat", "--name", "job-precompute-test"),
            0,
        )

        job_dir = dataset / "cloud" / "jobs" / "job-precompute-test"
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        env = (job_dir / "job.env").read_text(encoding="utf-8")
        run_script = (job_dir / "scripts" / "run-job.sh").read_text(encoding="utf-8")
        pull_script = (job_dir / "scripts" / "pull-inputs.sh").read_text(encoding="utf-8")

        self.assertTrue(job["precomputed_colmap"]["use_for_job"])
        self.assertFalse(job["precomputed_colmap"]["requires_cuda_colmap"])
        self.assertIn("PGM_USE_PRECOMPUTED_COLMAP=1", env)
        self.assertIn("WWS_BUILD_COLMAP_CUDA=0", env)
        self.assertIn("PGM_COLMAP_REQUIRE_CUDA=0", env)
        self.assertIn("skipping colmap_sparse", run_script)
        self.assertIn("colmap/***", pull_script)

    def test_rejects_unsafe_dataset_name(self):
        code = self.run_cli("init-dataset", "--name", "../bad", "--type", "object")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
