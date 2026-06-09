import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = ROOT / "tools" / "scrape_timemachine.py"

spec = importlib.util.spec_from_file_location("scrape_timemachine", SCRAPER_PATH)
scraper = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = scraper
spec.loader.exec_module(scraper)


class TimeMachineScraperTests(unittest.TestCase):
    def test_extract_urls_normalizes_relative_and_tracking_links(self):
        html = """
        <a href="/publication-handbook-of-digital-3d-reconstruction-of-historical-architecture/?utm_source=x#top">book</a>
        <a href="https://www.mdpi.com/2571-9408/7/6/157">paper</a>
        https://example.org/report.pdf).
        """

        urls = scraper.extract_urls(html, "https://www.timemachine.eu/source-page/")

        self.assertIn(
            "https://www.timemachine.eu/publication-handbook-of-digital-3d-reconstruction-of-historical-architecture",
            urls,
        )
        self.assertIn("https://www.mdpi.com/2571-9408/7/6/157", urls)
        self.assertIn("https://example.org/report.pdf", urls)

    def test_score_candidate_prioritizes_future_visualizer_research(self):
        candidate = scraper.Candidate(
            title="Automatic Removal of Non-Architectural Elements in 3D Models",
            date="2024-07-15T10:35:04",
            source_url="https://www.timemachine.eu/example/",
            source_type="post",
            categories=["Publication"],
            text=(
                "This open access paper uses language embedded neural radiance fields "
                "for 3D models, point cloud cleaning, semantic segmentation, and validation."
            ),
        )

        scored = scraper.score_candidate(candidate)

        self.assertGreaterEqual(scored.score, scraper.DEFAULT_MIN_SCORE)
        self.assertIn("3D reconstruction and capture", scored.themes)
        self.assertIn("AI-assisted visual analysis", scored.themes)
        self.assertIn("Research publication", scored.themes)

    def test_pdf_filename_is_stable_and_safe(self):
        url = "https://www.mdpi.com/2571-9408/7/6/157/pdf"
        name1 = scraper.pdf_filename(url, "Automatic Removal: 3D Models?")
        name2 = scraper.pdf_filename(url, "Automatic Removal: 3D Models?")

        self.assertEqual(name1, name2)
        self.assertTrue(name1.endswith(".pdf"))
        self.assertNotIn(":", name1)
        self.assertNotIn("?", name1)

    def test_dedupe_candidates_merges_links_and_categories(self):
        first = scraper.Candidate(
            title="Shared",
            date="2025-01-01T00:00:00",
            source_url="https://www.timemachine.eu/shared/?utm_source=x",
            source_type="post",
            text="3D reconstruction",
            categories=["Publication"],
            links=["https://example.org/a"],
        )
        second = scraper.Candidate(
            title="Shared",
            date="2025-01-02T00:00:00",
            source_url="https://www.timemachine.eu/shared/#fragment",
            source_type="post",
            text="metadata paradata",
            categories=["3D Data"],
            links=["https://example.org/b"],
        )

        merged = scraper.dedupe_candidates([first, second])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].date, "2025-01-02T00:00:00")
        self.assertEqual(merged[0].categories, ["3D Data", "Publication"])
        self.assertEqual(merged[0].links, ["https://example.org/a", "https://example.org/b"])

    def test_external_pdf_discovery_candidates_cover_common_paper_hosts(self):
        self.assertEqual(
            scraper.mdpi_pdf_candidates("https://www.mdpi.com/2571-9408/7/6/157"),
            ["https://www.mdpi.com/2571-9408/7/6/157/pdf"],
        )
        self.assertEqual(
            scraper.springer_pdf_candidates("https://link.springer.com/chapter/10.1007/978-3-031-78590-0_6"),
            ["https://link.springer.com/content/pdf/10.1007/978-3-031-78590-0_6.pdf"],
        )

    def test_manual_download_queue_includes_blocked_external_papers(self):
        candidate = scraper.Candidate(
            title="Blocked Paper",
            date="2026-01-01T00:00:00",
            source_url="https://www.timemachine.eu/blocked-paper/",
            source_type="post",
            text="3D reconstruction publication",
            paper_links=["https://example.org/paper"],
            reasons=["3D reconstruction"],
            score=20,
            artifacts=[
                scraper.PdfArtifact(
                    url="https://example.org/paper.pdf",
                    status="failed",
                    error="HTTP Error 403: Forbidden",
                )
            ],
        )

        markdown = scraper.render_manual_downloads(
            [candidate],
            Path("/tmp/whatwesee/Research/timemachine/index.md"),
        )

        self.assertIn("Blocked Paper", markdown)
        self.assertIn("manual/blocked-paper.pdf", markdown)
        self.assertIn("HTTP Error 403: Forbidden", markdown)


if __name__ == "__main__":
    unittest.main()
