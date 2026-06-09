import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "local_colmap_bench.py"

spec = importlib.util.spec_from_file_location("local_colmap_bench", SCRIPT_PATH)
bench = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bench)


class LocalColmapBenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_root = self.root / "data"
        self.dataset = self.data_root / "sample"
        (self.dataset / "manifests").mkdir(parents=True)
        (self.dataset / "working" / "images").mkdir(parents=True)
        images = [
            self.image("cam-a__IMG_10.jpg", "cam-a", "IMG_10.jpg"),
            self.image("cam-a__IMG_2.jpg", "cam-a", "IMG_2.jpg"),
            self.image("cam-b__IMG_1.jpg", "cam-b", "IMG_1.jpg"),
        ]
        manifest = {"schema_version": 1, "dataset": "sample", "images": images}
        (self.dataset / "manifests" / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def image(relative_path, source_dataset, source_relative_path):
        return {
            "relative_path": relative_path,
            "working_path": f"working/images/{relative_path}",
            "source_dataset": source_dataset,
            "source_relative_path": source_relative_path,
            "camera_model": "Test Camera",
            "lens_model": "Test Lens",
            "focal_length": 24,
        }

    def test_selection_uses_source_filter_and_natural_order(self):
        args = bench.build_parser().parse_args(
            [
                "--data-root",
                str(self.data_root),
                "--dataset",
                "sample",
                "--name",
                "dry",
                "--source-dataset",
                "cam-a",
                "--dry-run",
            ]
        )
        selected = bench.select_images(args, bench.load_manifest(self.dataset))
        self.assertEqual([item["relative_path"] for item in selected], ["cam-a__IMG_2.jpg", "cam-a__IMG_10.jpg"])

    def test_dry_run_does_not_create_run_directory_or_require_colmap(self):
        code = bench.main(
            [
                "--data-root",
                str(self.data_root),
                "--dataset",
                "sample",
                "--name",
                "dry",
                "--source-dataset",
                "cam-a",
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0)
        self.assertFalse((self.dataset / "benchmarks" / "dry").exists())


if __name__ == "__main__":
    unittest.main()
