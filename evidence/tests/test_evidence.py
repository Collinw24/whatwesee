import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "scripts" / "evidence.py"

spec = importlib.util.spec_from_file_location("evidence", EVIDENCE_PATH)
evidence = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(evidence)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class EvidenceCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.evidence_root = self.root / "evidence-data"
        self.pgm_root = self.root / "photogrammetry-data"
        self.config = self.root / "evidence.toml"
        self.config.write_text(
            f"""
[local]
evidence_root = "{self.evidence_root}"
photogrammetry_root = "{self.pgm_root}"

[hetzner]
ssh_host = "hetzner-test"
remote_root = "/srv/staging/evidence-test"
photogrammetry_remote_root = "/srv/staging/photogrammetry-test"

[bench]
default_models = ["vggt", "colmap", "glomap", "splatfacto"]

[policy]
lidar_role = "reference_control_geometry"
raw_data_in_repo = false
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return evidence.main(["--config", str(self.config), *args])

    def write_fake_photogrammetry_dataset(self, name="basement-fresh-iphone-001"):
        dataset = self.pgm_root / name
        image_path = dataset / "working" / "images" / "frame001.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(PNG_1X1)
        (dataset / "manifests").mkdir(parents=True, exist_ok=True)
        (dataset / "reports").mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": 1,
            "dataset": name,
            "dataset_type": "mixed",
            "created_at": "2026-04-28T00:00:00+00:00",
            "source": "test",
            "image_count": 1,
            "raw_archive_count": 0,
            "raw_total_bytes": image_path.stat().st_size,
            "working_total_bytes": image_path.stat().st_size,
            "focal_groups": {
                "Apple | iPhone | wide | 5.1 | 25": {
                    "camera_make": "Apple",
                    "camera_model": "iPhone",
                    "lens_model": "wide",
                    "focal_length": 5.1,
                    "focal_length_35mm": 25,
                    "count": 1,
                }
            },
            "preview_warnings": [],
            "tools": {},
            "raw_archive": [],
            "images": [
                {
                    "relative_path": "frame001.jpg",
                    "working_path": "working/images/frame001.jpg",
                    "sha256": "abc123",
                    "camera_model": "iPhone",
                    "lens_model": "wide",
                    "focal_length": 5.1,
                }
            ],
        }
        qc = {
            "schema_version": 1,
            "dataset": name,
            "passed": True,
            "summary": {"image_count": 1, "warning_count": 0, "fatal_count": 0},
            "warnings": [],
            "fatal": [],
        }
        (dataset / "manifests" / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        (dataset / "reports" / "qc_report.json").write_text(json.dumps(qc) + "\n", encoding="utf-8")
        return dataset

    def test_init_package_creates_layout_and_state_summary(self):
        self.assertEqual(
            self.run_cli("init-package", "--name", "basement-garden-s0", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        package = self.evidence_root / "basement-garden-s0"
        manifest = json.loads((package / "manifests" / "package.json").read_text(encoding="utf-8"))
        state = json.loads((package / "state" / "S0_state.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "basement-garden-s0")
        self.assertEqual(manifest["policy"]["lidar_role"], "reference_control_geometry")
        self.assertTrue((package / "raw" / "photos").is_dir())
        self.assertTrue((package / "benchmarks" / "vggt").is_dir())
        self.assertIn("photo_dataset", state["missing"])
        self.assertFalse(str(package).startswith(str(ROOT)))

    def test_link_photogrammetry_records_provenance_and_symlink(self):
        source_dataset = self.write_fake_photogrammetry_dataset()
        self.assertEqual(
            self.run_cli("init-package", "--name", "pkg", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        self.assertEqual(self.run_cli("link-photogrammetry", "--package", "pkg", "--dataset", source_dataset.name), 0)

        package = self.evidence_root / "pkg"
        manifest = json.loads((package / "manifests" / "package.json").read_text(encoding="utf-8"))
        photo_manifest = json.loads((package / "manifests" / f"photogrammetry_{source_dataset.name}.json").read_text(encoding="utf-8"))
        image_list = json.loads((package / "working" / "image_lists" / f"{source_dataset.name}.json").read_text(encoding="utf-8"))

        self.assertTrue((package / "raw" / "photos" / source_dataset.name).is_symlink())
        self.assertEqual(manifest["modalities"]["photos"]["datasets"][0]["dataset"], source_dataset.name)
        self.assertEqual(photo_manifest["qc"]["passed"], True)
        self.assertEqual(image_list["images"][0]["absolute_working_path"], str((source_dataset / "working/images/frame001.jpg").resolve()))

    def test_ingest_lidar_records_reference_role(self):
        lidar = self.root / "basement_scan.ply"
        lidar.write_text("ply\nend_header\n", encoding="utf-8")
        self.assertEqual(
            self.run_cli("init-package", "--name", "pkg", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        self.assertEqual(
            self.run_cli("ingest-lidar", "--package", "pkg", "--source", str(lidar), "--device", "iphone-lidar"),
            0,
        )

        package = self.evidence_root / "pkg"
        manifest = json.loads((package / "manifests" / "package.json").read_text(encoding="utf-8"))
        records = manifest["modalities"]["lidar"]["records"]
        lidar_manifest = json.loads((package / records[0]["manifest"]).read_text(encoding="utf-8"))

        self.assertEqual(records[0]["role"], "reference_control_geometry")
        self.assertTrue((package / "raw" / "lidar" / "iphone" / "basement_scan.ply").exists())
        self.assertEqual(lidar_manifest["device"], "iphone-lidar")
        self.assertEqual(lidar_manifest["artifact_class"], "evidence")

    def test_write_session_bench_plan_and_register_report_smoke(self):
        source_dataset = self.write_fake_photogrammetry_dataset()
        notes = self.root / "notes.md"
        notes.write_text("Lights fixed. Fans off.\n", encoding="utf-8")

        self.assertEqual(
            self.run_cli("init-package", "--name", "pkg", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        self.assertEqual(self.run_cli("link-photogrammetry", "--package", "pkg", "--dataset", source_dataset.name), 0)
        self.assertEqual(
            self.run_cli(
                "write-session",
                "--package",
                "pkg",
                "--date",
                "2026-04-28",
                "--location",
                "basement",
                "--notes",
                str(notes),
                "--lighting",
                "grow lights fixed",
                "--fans",
                "off",
            ),
            0,
        )
        self.assertEqual(self.run_cli("bench-plan", "--package", "pkg"), 0)
        self.assertEqual(self.run_cli("register-report", "--package", "pkg"), 0)

        package = self.evidence_root / "pkg"
        session = json.loads((package / "manifests" / "session.json").read_text(encoding="utf-8"))
        bench = (package / "benchmarks" / "bench_plan.md").read_text(encoding="utf-8")
        report = json.loads((package / "registration" / "register_report.json").read_text(encoding="utf-8"))

        self.assertEqual(session["capture_date"], "2026-04-28")
        self.assertIn("VGGT", bench)
        self.assertIn("COLMAP", bench)
        self.assertIn("--target splat", bench)
        self.assertTrue(report["acceptance_checks"]["photo_dataset_linked"])
        self.assertFalse(report["acceptance_checks"]["lidar_reference_available"])
        self.assertEqual(report["model_metrics"][0]["status"], "not_run")

    def test_sync_hetzner_dry_run_does_not_require_network(self):
        source_dataset = self.write_fake_photogrammetry_dataset()
        self.assertEqual(
            self.run_cli("init-package", "--name", "pkg", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        self.assertEqual(self.run_cli("link-photogrammetry", "--package", "pkg", "--dataset", source_dataset.name), 0)
        self.assertEqual(self.run_cli("sync-hetzner", "--package", "pkg", "--dry-run"), 0)

    def test_rejects_unsupported_lidar_extension(self):
        bad = self.root / "scan.txt"
        bad.write_text("not lidar\n", encoding="utf-8")
        self.assertEqual(
            self.run_cli("init-package", "--name", "pkg", "--target", "basement-garden", "--state-id", "S0"),
            0,
        )
        self.assertEqual(self.run_cli("ingest-lidar", "--package", "pkg", "--source", str(bad)), 2)


if __name__ == "__main__":
    unittest.main()
