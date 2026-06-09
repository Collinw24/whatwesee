#!/usr/bin/env python3
"""Build a local research index from public Time Machine Europe sources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import html
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET


BASE_URL = "https://www.timemachine.eu/"
WP_API_BASE = urljoin(BASE_URL, "wp-json/wp/v2/")
USER_AGENT = "WhatWeSeeResearchScraper/1.0"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "timemachine" / "index.md"
MANUAL_DOWNLOADS_FILENAME = "manual-downloads.md"
DEFAULT_MIN_SCORE = 12
DEFAULT_MAX_RESULTS = 80
DEFAULT_MAX_PDF_MB = 50
DEFAULT_DELAY_SECONDS = 0.15
MAX_DISCOVERY_HTML_BYTES = 1_000_000
TLS_CONTEXT: ssl.SSLContext | None = None
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

SEED_URLS = [
    "https://www.timemachine.eu/study-on-quality-in-3d-digitisation-of-tangible-cultural-heritage/",
    "https://www.timemachine.eu/making-the-europeana-data-model-a-better-fit-for-documentation-of-3d-objects/",
    "https://www.timemachine.eu/automatic-removal-of-non-architectural-elements-in-3d-models-of-historic-buildings-with-language-embedded-radiance-fields/",
    "https://www.timemachine.eu/publication-handbook-of-digital-3d-reconstruction-of-historical-architecture/",
    "https://www.timemachine.eu/publication-a-digital-4d-information-system-on-world-scale/",
    "https://www.timemachine.eu/3d-digitisation-prepare-for-success/",
]

CATEGORY_WEIGHTS = {
    "3D Data": 8,
    "Publication": 7,
    "3D-4CH": 5,
    "3DBigDataSpace": 5,
    "5Dculture": 4,
    "Request for Comments": 3,
    "Survey": 2,
    "Local Time Machine": 2,
}
LOW_SIGNAL_CATEGORIES = {
    "Funding",
    "Job Opportunity",
    "Event",
    "Call for Participation",
    "Call for Papers",
}

SCORE_RULES: list[tuple[str, str, int, re.Pattern[str]]] = [
    ("Temporal digital twins", "digital twin", 9, re.compile(r"\bdigital twins?\b", re.I)),
    ("Temporal digital twins", "4D or temporal modeling", 8, re.compile(r"\b4d\b|temporal|time series|world scale|geoviewer", re.I)),
    ("Future-state imaging", "forecasting or prediction", 8, re.compile(r"future-state|forecast|prediction|predictive|plausible trajector|monitoring|maintenance|risk scenario|fault detection", re.I)),
    ("3D reconstruction and capture", "3D reconstruction", 8, re.compile(r"3d reconstruction|3d digitisation|3d digitization|3d model|3d models|3d data|3d cultural heritage", re.I)),
    ("3D reconstruction and capture", "photogrammetry or capture", 7, re.compile(r"photogrammetry|structure[- ]from[- ]motion|multi[- ]view|capture|digitisation workflow|digitization workflow", re.I)),
    ("3D reconstruction and capture", "mesh, point cloud, NeRF, or radiance field", 7, re.compile(r"mesh|point cloud|neural radiance|radiance field|\bnerf\b|gaussian splat|splatting", re.I)),
    ("Metadata, paradata, and interoperability", "metadata or paradata", 8, re.compile(r"metadata|paradata|provenance|europeana data model|\bedm\b", re.I)),
    ("Metadata, paradata, and interoperability", "FAIR, standards, or data spaces", 6, re.compile(r"\bfair\b|interoperab|data space|common european data space|standardi[sz]ation|schema", re.I)),
    ("Quality, uncertainty, and standards", "quality and uncertainty", 6, re.compile(r"quality|uncertainty|accuracy|precision|validation|benchmark|guideline", re.I)),
    ("Visualization, XR, and viewers", "visualization, rendering, viewer, or XR", 5, re.compile(r"visuali[sz]|render|viewer|extended reality|\bxr\b|virtual reality|augmented reality|immersive", re.I)),
    ("AI-assisted visual analysis", "AI or semantic analysis", 5, re.compile(r"artificial intelligence|\bai\b|machine learning|semantic enrichment|segmentation|classification|language embedded", re.I)),
    ("Research publication", "paper, report, article, handbook, or study", 4, re.compile(r"publication|paper|article|report|handbook|study|journal|book|open access", re.I)),
    ("Time Machine infrastructure", "Time Machine infrastructure", 3, re.compile(r"time machine|data graph|request for comments|\brfc\b|roadmap|infrastructure", re.I)),
]

THEME_ORDER = [
    "Future-state imaging",
    "Temporal digital twins",
    "3D reconstruction and capture",
    "Metadata, paradata, and interoperability",
    "Quality, uncertainty, and standards",
    "Visualization, XR, and viewers",
    "AI-assisted visual analysis",
    "Research publication",
    "Time Machine infrastructure",
]

PAPER_DOMAINS = {
    "mdpi.com",
    "www.mdpi.com",
    "link.springer.com",
    "springer.com",
    "www.springer.com",
    "op.europa.eu",
    "digital-strategy.ec.europa.eu",
    "ec.europa.eu",
    "doi.org",
    "zenodo.org",
    "arxiv.org",
    "www.dataspace-culturalheritage.eu",
    "dataspace-culturalheritage.eu",
    "5dculture.eu",
    "eureka3d.eu",
    "www.3d4ch-competencecentre.eu",
    "3d4ch-competencecentre.eu",
}

@dataclass
class PdfArtifact:
    url: str
    status: str
    path: Path | None = None
    text_path: Path | None = None
    meta_path: Path | None = None
    sha256: str | None = None
    bytes: int | None = None
    content_type: str | None = None
    text_status: str | None = None
    error: str | None = None


@dataclass
class Candidate:
    title: str
    date: str
    source_url: str
    source_type: str
    text: str
    categories: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    pdf_links: list[str] = field(default_factory=list)
    paper_links: list[str] = field(default_factory=list)
    score: int = 0
    themes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    artifacts: list[PdfArtifact] = field(default_factory=list)


class ScrapeError(RuntimeError):
    """Expected scraper failure with a concise message."""


def build_tls_context(insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() in {"href", "src"} and value:
                self.links.append(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return collapse_ws(html.unescape(cleaned))


def normalize_url(value: str, base: str = BASE_URL) -> str:
    value = html.unescape(value or "").strip()
    if not value:
        return ""
    joined = urljoin(base, value)
    parts = urlsplit(joined)
    if parts.scheme not in {"http", "https"}:
        return ""
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_QUERY_KEYS and not key.startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = re.sub(r"/{2,}", "/", parts.path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def extract_urls(value: str, base: str = BASE_URL) -> list[str]:
    if not value:
        return []
    extractor = LinkExtractor()
    try:
        extractor.feed(value)
    except Exception:
        pass
    raw_urls = list(extractor.links)
    raw_urls.extend(re.findall(r"https?://[^\s\"'<>]+", html.unescape(value)))
    seen: set[str] = set()
    urls: list[str] = []
    for raw in raw_urls:
        raw = raw.rstrip(").,;]")
        url = normalize_url(raw, base)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def is_pdf_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.lower()
    return path.endswith(".pdf") or path.endswith("/pdf") or "/content/pdf/" in path


def looks_like_paper_url(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    path = parts.path.lower()
    if is_pdf_url(url):
        return True
    if host in PAPER_DOMAINS:
        return True
    if re.search(r"call-for|open-call|registration|programme|program|events?|conference|workshop|funding|job", path):
        return False
    return bool(re.search(r"publication|paper|article|report|handbook|study|guideline|journal|book|doi", path))


def slugify(value: str, fallback: str = "document") -> str:
    value = strip_html(value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or fallback


def pdf_filename(url: str, title: str = "") -> str:
    parts = urlsplit(url)
    basename = Path(parts.path).name
    if basename.lower().endswith(".pdf"):
        stem = basename[:-4]
    elif basename.lower() == "pdf":
        stem = title or Path(parts.path).parent.name
    else:
        stem = title or basename or parts.netloc
    stable = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{slugify(stem)[:80]}-{stable}.pdf"


def request_url(url: str, timeout: float, accept: str = "*/*", method: str = "GET") -> tuple[bytes, dict[str, str], str]:
    request = Request(
        url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    with urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
        final_url = response.geturl()
        headers = {key.lower(): value for key, value in response.headers.items()}
        if method == "HEAD":
            return b"", headers, final_url
        return response.read(), headers, final_url


def request_json(url: str, timeout: float) -> tuple[Any, dict[str, str]]:
    body, headers, _ = request_url(url, timeout=timeout, accept="application/json")
    return json.loads(body.decode("utf-8")), headers


def request_text(url: str, timeout: float, accept: str = "text/plain,*/*") -> tuple[str, dict[str, str]]:
    body, headers, _ = request_url(url, timeout=timeout, accept=accept)
    charset = "utf-8"
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type)
    if match:
        charset = match.group(1)
    return body.decode(charset, errors="replace"), headers


def fetch_wp_collection(rest_base: str, timeout: float, per_page: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in rest_base else "?"
        url = f"{rest_base}{separator}per_page={per_page}&page={page}"
        data, headers = request_json(url, timeout)
        if not isinstance(data, list):
            break
        items.extend(data)
        total_pages = int(headers.get("x-wp-totalpages", "1") or "1")
        if page >= total_pages:
            break
        page += 1
    return items


def fetch_categories(timeout: float) -> dict[int, str]:
    categories = fetch_wp_collection(urljoin(WP_API_BASE, "categories"), timeout=timeout)
    result: dict[int, str] = {}
    for category in categories:
        try:
            result[int(category["id"])] = strip_html(category.get("name", ""))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def fetch_sitemap_urls(url: str, timeout: float, max_sitemaps: int = 50) -> list[str]:
    visited: set[str] = set()
    urls: list[str] = []

    def walk(sitemap_url: str) -> None:
        if len(visited) >= max_sitemaps:
            return
        sitemap_url = normalize_url(sitemap_url)
        if not sitemap_url or sitemap_url in visited:
            return
        visited.add(sitemap_url)
        text, _ = request_text(sitemap_url, timeout=timeout, accept="application/xml,text/xml,*/*")
        root = ET.fromstring(text)
        locs = [element.text or "" for element in root.iter() if element.tag.endswith("loc")]
        if root.tag.endswith("sitemapindex"):
            for loc in locs:
                if normalize_url(loc).startswith(normalize_url(BASE_URL)):
                    walk(loc)
        else:
            for loc in locs:
                normalized = normalize_url(loc)
                if normalized.startswith(normalize_url(BASE_URL)):
                    urls.append(normalized)

    walk(url)
    return sorted(set(urls))


def check_robots(timeout: float) -> str:
    robots_url = urljoin(BASE_URL, "robots.txt")
    text, _ = request_text(robots_url, timeout=timeout)
    for line in text.splitlines():
        if line.strip().lower() == "disallow: /":
            raise ScrapeError("robots.txt disallows public crawling for this site.")
    return text


def classify_links(links: list[str]) -> tuple[list[str], list[str]]:
    pdfs: list[str] = []
    papers: list[str] = []
    for link in links:
        if is_pdf_url(link):
            pdfs.append(link)
        elif looks_like_paper_url(link):
            papers.append(link)
    return sorted(set(pdfs)), sorted(set(papers))


def build_candidate_from_wp(item: dict[str, Any], source_type: str, category_names: dict[int, str]) -> Candidate:
    title = strip_html(item.get("title", {}).get("rendered", "Untitled"))
    date = str(item.get("date", ""))
    source_url = normalize_url(str(item.get("link", "")))
    content_html = item.get("content", {}).get("rendered", "") or ""
    excerpt_html = item.get("excerpt", {}).get("rendered", "") or ""
    text = collapse_ws(" ".join([title, strip_html(excerpt_html), strip_html(content_html)]))
    links = extract_urls(" ".join([content_html, excerpt_html]), source_url or BASE_URL)
    pdf_links, paper_links = classify_links(links)
    categories = []
    for category_id in item.get("categories", []) or []:
        try:
            name = category_names.get(int(category_id))
        except (TypeError, ValueError):
            name = None
        if name:
            categories.append(name)
    return Candidate(
        title=title,
        date=date,
        source_url=source_url,
        source_type=source_type,
        text=text,
        categories=categories,
        links=links,
        pdf_links=pdf_links,
        paper_links=paper_links,
    )


def build_candidate_from_media(item: dict[str, Any]) -> Candidate:
    title = strip_html(item.get("title", {}).get("rendered", "Untitled PDF"))
    source_url = normalize_url(str(item.get("source_url", "")))
    text = collapse_ws(f"{title} {source_url}")
    links = [source_url] if source_url else []
    pdf_links, paper_links = classify_links(links)
    return Candidate(
        title=title,
        date=str(item.get("date", "")),
        source_url=source_url,
        source_type="media_pdf",
        text=text,
        links=links,
        pdf_links=pdf_links,
        paper_links=paper_links,
    )


def score_candidate(candidate: Candidate) -> Candidate:
    text = " ".join([candidate.title, candidate.text, " ".join(candidate.links)])
    score = 0
    themes: set[str] = set()
    reasons: list[str] = []
    seen_reasons: set[str] = set()

    for theme, reason, weight, pattern in SCORE_RULES:
        if pattern.search(text):
            score += weight
            themes.add(theme)
            if reason not in seen_reasons:
                reasons.append(reason)
                seen_reasons.add(reason)

    for category in candidate.categories:
        score += CATEGORY_WEIGHTS.get(category, 0)
        if category == "Publication":
            themes.add("Research publication")

    low_signal = any(category in LOW_SIGNAL_CATEGORIES for category in candidate.categories)
    if low_signal and "Publication" not in candidate.categories:
        score -= 14
        if not candidate.pdf_links:
            score -= 8
    if re.match(r"(?i)\s*call for papers?", candidate.title):
        score -= 16

    candidate.score = max(score, 0)
    candidate.themes = [theme for theme in THEME_ORDER if theme in themes]
    candidate.reasons = reasons
    return candidate


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_url: dict[str, Candidate] = {}
    for candidate in candidates:
        key = normalize_url(candidate.source_url)
        if not key:
            continue
        existing = by_url.get(key)
        if existing is None:
            by_url[key] = candidate
            continue
        existing.text = collapse_ws(f"{existing.text} {candidate.text}")
        existing.categories = sorted(set(existing.categories + candidate.categories))
        existing.links = sorted(set(existing.links + candidate.links))
        existing.pdf_links = sorted(set(existing.pdf_links + candidate.pdf_links))
        existing.paper_links = sorted(set(existing.paper_links + candidate.paper_links))
        if candidate.date and (not existing.date or candidate.date > existing.date):
            existing.date = candidate.date
    return list(by_url.values())


def springer_pdf_candidates(url: str) -> list[str]:
    parts = urlsplit(url)
    if parts.netloc.lower() != "link.springer.com":
        return []
    match = re.match(r"^/(chapter|book)/(.+)$", parts.path)
    if not match:
        return []
    doi = match.group(2).strip("/")
    if not doi:
        return []
    return [f"https://link.springer.com/content/pdf/{doi}.pdf"]


def mdpi_pdf_candidates(url: str) -> list[str]:
    parts = urlsplit(url)
    if parts.netloc.lower() not in {"mdpi.com", "www.mdpi.com"}:
        return []
    if is_pdf_url(url):
        return []
    if re.search(r"/\d+-\d+/\d+/\d+/\d+", parts.path):
        return [url.rstrip("/") + "/pdf"]
    return []


def discover_pdf_links(url: str, timeout: float) -> list[str]:
    normalized = normalize_url(url)
    if not normalized:
        return []
    if is_pdf_url(normalized):
        return [normalized]

    candidates = []
    candidates.extend(springer_pdf_candidates(normalized))
    candidates.extend(mdpi_pdf_candidates(normalized))

    try:
        request = Request(
            normalized,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"},
        )
        with urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
            content_type = response.headers.get("Content-Type", "")
            final_url = normalize_url(response.geturl())
            if "application/pdf" in content_type.lower():
                candidates.append(final_url)
            elif "text/html" in content_type.lower() or "application/xhtml" in content_type.lower():
                body = response.read(MAX_DISCOVERY_HTML_BYTES + 1)
                if len(body) <= MAX_DISCOVERY_HTML_BYTES:
                    html_text = body.decode("utf-8", errors="replace")
                    candidates.extend(link for link in extract_urls(html_text, final_url) if is_pdf_url(link))
    except (HTTPError, URLError, TimeoutError, OSError):
        pass

    return sorted(set(candidates))


def head_content(url: str, timeout: float) -> tuple[dict[str, str], str] | None:
    try:
        _, headers, final_url = request_url(url, timeout=timeout, method="HEAD")
        return headers, final_url
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def existing_artifact(pdf_path: Path, text_path: Path, meta_path: Path, url: str) -> PdfArtifact:
    digest = sha256_file(pdf_path)
    text_status = "extracted" if text_path.exists() else "missing"
    return PdfArtifact(
        url=url,
        status="existing",
        path=pdf_path,
        text_path=text_path if text_path.exists() else None,
        meta_path=meta_path if meta_path.exists() else None,
        sha256=digest,
        bytes=pdf_path.stat().st_size,
        text_status=text_status,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(pdf_path: Path, text_path: Path, timeout: float = 120) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return "pdftotext unavailable"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [pdftotext, "-layout", str(pdf_path), str(text_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        message = collapse_ws(proc.stderr or proc.stdout or "pdftotext failed")
        return f"failed: {message[:160]}"
    return "extracted"


def download_pdf(
    url: str,
    title: str,
    source_page: str,
    output_dir: Path,
    timeout: float,
    max_bytes: int,
) -> PdfArtifact:
    pdf_dir = output_dir / "pdfs"
    text_dir = output_dir / "text"
    meta_dir = output_dir / "metadata"
    filename = pdf_filename(url, title)
    pdf_path = pdf_dir / filename
    text_path = text_dir / f"{pdf_path.stem}.txt"
    meta_path = meta_dir / f"{pdf_path.stem}.json"

    if pdf_path.exists():
        artifact = existing_artifact(pdf_path, text_path, meta_path, url)
        if not text_path.exists():
            artifact.text_status = extract_pdf_text(pdf_path, text_path)
            artifact.text_path = text_path if text_path.exists() else None
        return artifact

    head = head_content(url, timeout)
    if head is not None:
        headers, final_url = head
        content_type = headers.get("content-type", "")
        content_length = headers.get("content-length", "")
        try:
            length = int(content_length) if content_length else 0
        except ValueError:
            length = 0
        if length and length > max_bytes:
            return PdfArtifact(url=url, status="skipped", content_type=content_type, error="over size cap")
        if content_type and "application/pdf" not in content_type.lower() and not is_pdf_url(final_url):
            return PdfArtifact(url=url, status="skipped", content_type=content_type, error="not a PDF content type")

    pdf_dir.mkdir(parents=True, exist_ok=True)
    temp_path = pdf_path.with_suffix(".part")
    download_complete = False
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"})
        with urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/pdf" not in content_type.lower():
                return PdfArtifact(url=url, status="skipped", content_type=content_type, error="not application/pdf")
            total = 0
            first_chunk = True
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if first_chunk and not chunk.startswith(b"%PDF-"):
                        return PdfArtifact(url=url, status="skipped", content_type=content_type, error="missing PDF header")
                    first_chunk = False
                    total += len(chunk)
                    if total > max_bytes:
                        return PdfArtifact(url=url, status="skipped", content_type=content_type, error="over size cap")
                    handle.write(chunk)
            download_complete = True
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return PdfArtifact(url=url, status="failed", error=str(exc))
    finally:
        if temp_path.exists() and not download_complete:
            temp_path.unlink(missing_ok=True)

    if not temp_path.exists():
        return PdfArtifact(url=url, status="failed", error="download did not produce a file")
    temp_path.replace(pdf_path)
    digest = sha256_file(pdf_path)
    text_status = extract_pdf_text(pdf_path, text_path)
    meta_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source_url": url,
        "source_page": source_page,
        "sha256": digest,
        "bytes": pdf_path.stat().st_size,
        "content_type": "application/pdf",
        "downloaded_at": utc_now(),
        "text_status": text_status,
    }
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PdfArtifact(
        url=url,
        status="downloaded",
        path=pdf_path,
        text_path=text_path if text_path.exists() else None,
        meta_path=meta_path,
        sha256=digest,
        bytes=pdf_path.stat().st_size,
        content_type="application/pdf",
        text_status=text_status,
    )


def candidate_primary_theme(candidate: Candidate) -> str:
    for theme in THEME_ORDER:
        if theme in candidate.themes:
            return theme
    return "Other relevant sources"


def markdown_link(label: str, url: str) -> str:
    safe_label = label.replace("[", "\\[").replace("]", "\\]")
    return f"[{safe_label}]({url})"


def relative_markdown_path(path: Path, base: Path) -> str:
    return os.path.relpath(path, base).replace(os.sep, "/")


def artifact_status(artifact: PdfArtifact, output_dir: Path) -> str:
    if artifact.path:
        pdf_rel = relative_markdown_path(artifact.path, output_dir)
        digest = artifact.sha256[:12] if artifact.sha256 else "unknown"
        text_part = ""
        if artifact.text_path:
            text_rel = relative_markdown_path(artifact.text_path, output_dir)
            text_part = f"; text: {markdown_link(Path(text_rel).name, text_rel)}"
        return f"{markdown_link(artifact.path.name, pdf_rel)}; sha256 `{digest}`{text_part}"
    message = artifact.status
    if artifact.error:
        message += f" ({artifact.error})"
    return f"{artifact.url} - {message}"


def render_markdown(
    candidates: list[Candidate],
    output_path: Path,
    stats: dict[str, Any],
    dry_run: bool,
) -> str:
    output_dir = output_path.parent
    lines: list[str] = [
        "# Time Machine Research Index",
        "",
        f"Generated: `{utc_now()}`",
        f"Mode: `{'dry-run' if dry_run else 'download-pdfs'}`",
        "",
        "This index is generated from public Time Machine Europe WordPress API, sitemap, and PDF media records. It is ranked for the What We See future-state imaging work: state estimates, temporal digital twins, uncertainty-bearing rendered forecasts, and validation.",
        "",
        "## Crawl Summary",
        "",
        f"- WordPress posts: {stats.get('posts', 0)}",
        f"- WordPress events: {stats.get('events', 0)}",
        f"- PDF media records: {stats.get('media_pdfs', 0)}",
        f"- Sitemap URLs: {stats.get('sitemap_urls', 0)}",
        f"- Indexed candidates: {len(candidates)}",
        "",
    ]

    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate_primary_theme(candidate), []).append(candidate)

    for theme in [*THEME_ORDER, "Other relevant sources"]:
        items = grouped.get(theme)
        if not items:
            continue
        lines.extend([f"## {theme}", ""])
        for candidate in items:
            date = candidate.date[:10] if candidate.date else "unknown"
            lines.extend(
                [
                    f"### {candidate.title}",
                    "",
                    f"- Date: `{date}`",
                    f"- Score: `{candidate.score}`",
                    f"- Source: {markdown_link(candidate.source_type, candidate.source_url)}",
                ]
            )
            if candidate.categories:
                lines.append(f"- Categories: {', '.join(candidate.categories)}")
            if candidate.themes:
                lines.append(f"- Themes: {', '.join(candidate.themes)}")
            if candidate.reasons:
                lines.append(f"- Relevance: {', '.join(candidate.reasons[:8])}")
            if candidate.paper_links:
                links = ", ".join(markdown_link(urlsplit(link).netloc or "paper", link) for link in candidate.paper_links[:8])
                lines.append(f"- Paper/report pages: {links}")
            if candidate.pdf_links:
                links = ", ".join(markdown_link(Path(urlsplit(link).path).name or "PDF", link) for link in candidate.pdf_links[:8])
                lines.append(f"- PDF links: {links}")
            if candidate.artifacts:
                lines.append("- Local PDFs:")
                for artifact in candidate.artifacts:
                    lines.append(f"  - {artifact_status(artifact, output_dir)}")
            else:
                status = "no downloadable public PDF found" if candidate.paper_links or candidate.pdf_links else "link-only research candidate"
                lines.append(f"- Status: {status}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def manual_download_needed(candidate: Candidate) -> bool:
    if candidate.paper_links and not any(artifact.path for artifact in candidate.artifacts):
        return True
    for artifact in candidate.artifacts:
        if artifact.status in {"failed", "skipped"}:
            return True
    return False


def render_manual_downloads(candidates: list[Candidate], output_path: Path) -> str:
    output_dir = output_path.parent
    manual_dir = output_dir / "manual"
    lines: list[str] = [
        "# Manual Download Queue",
        "",
        f"Generated: `{utc_now()}`",
        "",
        "Some relevant paper/report pages block automated PDF download, require browser interaction, or publish files behind landing pages. Put manually downloaded PDFs in `manual/`; keep the source URL in the filename or add a short note beside the index entry.",
        "",
        "Suggested convention:",
        "",
        "```text",
        "Research/timemachine/manual/source-title-or-doi.pdf",
        "```",
        "",
    ]

    queued = [candidate for candidate in candidates if manual_download_needed(candidate)]
    if not queued:
        lines.extend(["No manual downloads are currently queued.", ""])
        return "\n".join(lines)

    for candidate in queued:
        date = candidate.date[:10] if candidate.date else "unknown"
        filename = f"{slugify(candidate.title)[:90]}.pdf"
        lines.extend(
            [
                f"## {candidate.title}",
                "",
                f"- Date: `{date}`",
                f"- Score: `{candidate.score}`",
                f"- Source: {markdown_link(candidate.source_type, candidate.source_url)}",
                f"- Suggested manual path: `{relative_markdown_path(manual_dir / filename, output_dir)}`",
            ]
        )
        if candidate.paper_links:
            links = ", ".join(markdown_link(urlsplit(link).netloc or "paper", link) for link in candidate.paper_links[:12])
            lines.append(f"- Paper/report pages: {links}")
        blocked = [artifact for artifact in candidate.artifacts if artifact.status in {"failed", "skipped"}]
        if blocked:
            lines.append("- Automated download status:")
            for artifact in blocked:
                reason = artifact.error or artifact.status
                lines.append(f"  - {artifact.url} - {reason}")
        if candidate.reasons:
            lines.append(f"- Why it matters: {', '.join(candidate.reasons[:6])}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def acceptance_missing(candidates: list[Candidate]) -> list[str]:
    found_urls: set[str] = set()
    for candidate in candidates:
        found_urls.add(normalize_url(candidate.source_url))
        found_urls.update(normalize_url(link) for link in candidate.links)
    missing = []
    for seed in SEED_URLS:
        if normalize_url(seed) not in found_urls:
            missing.append(seed)
    return missing


def crawl(args: argparse.Namespace) -> tuple[list[Candidate], dict[str, Any]]:
    if args.check_robots:
        check_robots(args.timeout)

    category_names = fetch_categories(args.timeout)
    posts_url = urljoin(WP_API_BASE, "posts") + "?_fields=id,date,link,title,excerpt,content,categories"
    events_url = urljoin(WP_API_BASE, "event") + "?_fields=id,date,link,title,excerpt,content,categories"
    media_url = urljoin(WP_API_BASE, "media") + "?mime_type=application/pdf&_fields=id,date,source_url,title,mime_type,post"

    posts = fetch_wp_collection(posts_url, timeout=args.timeout)
    events = fetch_wp_collection(events_url, timeout=args.timeout)
    media_pdfs = fetch_wp_collection(media_url, timeout=args.timeout)
    sitemap_urls = fetch_sitemap_urls(urljoin(BASE_URL, "sitemap.xml"), timeout=args.timeout)

    candidates: list[Candidate] = []
    candidates.extend(build_candidate_from_wp(item, "post", category_names) for item in posts)
    candidates.extend(build_candidate_from_wp(item, "event", category_names) for item in events)
    candidates.extend(build_candidate_from_media(item) for item in media_pdfs)

    sitemap_known = {normalize_url(candidate.source_url) for candidate in candidates}
    for sitemap_url in sitemap_urls:
        if sitemap_url not in sitemap_known and looks_like_paper_url(sitemap_url):
            candidates.append(
                Candidate(
                    title=Path(urlsplit(sitemap_url).path).name.replace("-", " ").title() or sitemap_url,
                    date="",
                    source_url=sitemap_url,
                    source_type="sitemap",
                    text=sitemap_url,
                    links=[sitemap_url],
                    pdf_links=[sitemap_url] if is_pdf_url(sitemap_url) else [],
                    paper_links=[] if is_pdf_url(sitemap_url) else [sitemap_url],
                )
            )

    candidates = [score_candidate(candidate) for candidate in dedupe_candidates(candidates)]
    candidates = [candidate for candidate in candidates if candidate.score >= args.min_score]
    candidates.sort(key=lambda item: (-item.score, item.date, item.title.lower()))
    if args.max_results:
        candidates = candidates[: args.max_results]

    stats = {
        "posts": len(posts),
        "events": len(events),
        "media_pdfs": len(media_pdfs),
        "sitemap_urls": len(sitemap_urls),
    }
    return candidates, stats


def hydrate_downloads(candidates: list[Candidate], args: argparse.Namespace, output_dir: Path) -> None:
    downloaded_urls: dict[str, PdfArtifact] = {}
    downloaded_hashes: dict[str, PdfArtifact] = {}
    max_bytes = int(args.max_pdf_mb * 1024 * 1024)
    for candidate in candidates:
        pdf_urls = list(candidate.pdf_links)
        if args.external_discovery:
            for paper_url in candidate.paper_links:
                pdf_urls.extend(discover_pdf_links(paper_url, timeout=args.timeout))
                time.sleep(args.delay)
        candidate.pdf_links = sorted(set(pdf_urls))
        for pdf_url in candidate.pdf_links:
            canonical = normalize_url(pdf_url)
            artifact = downloaded_urls.get(canonical)
            if artifact is None:
                artifact = download_pdf(
                    canonical,
                    title=candidate.title,
                    source_page=candidate.source_url,
                    output_dir=output_dir,
                    timeout=args.timeout,
                    max_bytes=max_bytes,
                )
                if artifact.sha256:
                    duplicate = downloaded_hashes.get(artifact.sha256)
                    if duplicate is not None:
                        remove_duplicate_artifact(artifact, duplicate)
                        artifact = duplicate
                    else:
                        downloaded_hashes[artifact.sha256] = artifact
                downloaded_urls[canonical] = artifact
                time.sleep(args.delay)
            candidate.artifacts.append(artifact)


def remove_duplicate_artifact(artifact: PdfArtifact, duplicate: PdfArtifact) -> None:
    for path, kept_path in (
        (artifact.path, duplicate.path),
        (artifact.text_path, duplicate.text_path),
        (artifact.meta_path, duplicate.meta_path),
    ):
        if path and kept_path and path != kept_path:
            path.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape public Time Machine Europe research sources.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown index output path.")
    parser.add_argument("--download-pdfs", action="store_true", help="Download valid public application/pdf links.")
    parser.add_argument("--dry-run", action="store_true", help="Crawl and write the index without downloading PDFs.")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE, help="Minimum relevance score to include.")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Maximum indexed candidates, 0 for no cap.")
    parser.add_argument("--max-pdf-mb", type=float, default=DEFAULT_MAX_PDF_MB, help="Per-PDF download size cap.")
    parser.add_argument("--timeout", type=float, default=25.0, help="Network request timeout in seconds.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between follow-up/download requests.")
    parser.add_argument("--acceptance-check", action="store_true", help="Fail if known seed candidates are missing.")
    parser.add_argument("--no-robots-check", dest="check_robots", action="store_false", help="Skip robots.txt guard.")
    parser.add_argument("--no-external-discovery", dest="external_discovery", action="store_false", help="Do not fetch linked paper pages looking for PDFs.")
    parser.add_argument("--insecure-tls", action="store_true", help="Disable TLS verification if the local Python certificate store is broken.")
    parser.set_defaults(check_robots=True, external_discovery=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global TLS_CONTEXT
    args = parse_args(argv or sys.argv[1:])
    TLS_CONTEXT = build_tls_context(args.insecure_tls)
    args.output = args.output.expanduser().resolve()
    if args.dry_run:
        args.download_pdfs = False

    try:
        candidates, stats = crawl(args)
        if args.acceptance_check:
            missing = acceptance_missing(candidates)
            if missing:
                for url in missing:
                    print(f"Missing seed candidate: {url}", file=sys.stderr)
                return 2

        output_dir = args.output.parent
        if args.download_pdfs:
            hydrate_downloads(candidates, args, output_dir)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        markdown = render_markdown(candidates, args.output, stats, dry_run=not args.download_pdfs)
        args.output.write_text(markdown, encoding="utf-8")
        (args.output.parent / "manual").mkdir(parents=True, exist_ok=True)
        manual_markdown = render_manual_downloads(candidates, args.output)
        (args.output.parent / MANUAL_DOWNLOADS_FILENAME).write_text(manual_markdown, encoding="utf-8")

        downloaded = sum(1 for candidate in candidates for artifact in candidate.artifacts if artifact.status in {"downloaded", "existing"})
        print(f"Indexed {len(candidates)} candidates at {args.output}")
        if args.download_pdfs:
            print(f"PDF artifacts available: {downloaded}")
        return 0
    except ScrapeError as exc:
        print(f"scrape_timemachine: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("scrape_timemachine: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
