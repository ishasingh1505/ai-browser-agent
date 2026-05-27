"""
Content Extractor — Phase 2

Takes raw HTML (already fetched by Playwright) and pulls out:
  - Product spec tables  → dict of {label: value}
  - Key headings         → list of strings
  - Clean body text      → single string
  - Price mentions       → list of strings

The extractor is pure BeautifulSoup — no browser, no network calls.
It receives HTML that browser.py already fetched, so it's fast and testable.
"""

from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag


# ── Spec keywords we look for in table headers / label cells ──────────────────

SPEC_KEYWORDS = {
    # Processor
    "processor", "cpu", "chipset",
    # Memory
    "ram", "memory",
    # Storage
    "storage", "ssd", "hdd", "hard disk",
    # Display
    "display", "screen", "resolution", "refresh rate",
    # GPU
    "gpu", "graphics", "graphic card",
    # Battery
    "battery", "battery life",
    # Weight / dimensions
    "weight", "dimension",
    # OS
    "os", "operating system",
    # Connectivity
    "wifi", "bluetooth", "ports", "usb",
    # Camera
    "camera", "webcam",
    # Price
    "price", "mrp",
}


def _is_spec_label(text: str) -> bool:
    """Return True if this cell text looks like a spec label."""
    t = text.lower().strip()
    return any(kw in t for kw in SPEC_KEYWORDS)


def extract_spec_tables(html: str) -> dict[str, str]:
    """
    Scan all <table> and definition-list (<dl>) elements in the HTML.
    Return a flat dict of {spec_label: spec_value} for anything that
    looks like product specifications.

    Example output:
    {
        "Processor": "Intel Core i7-13700H",
        "RAM": "16 GB DDR5",
        "Storage": "512 GB SSD",
        "Battery": "72 Wh",
        "Weight": "1.76 kg",
        ...
    }
    """
    soup = BeautifulSoup(html, "lxml")
    specs: dict[str, str] = {}

    # ── Strategy 1: <table> elements ─────────────────────────────────────────
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = cells[0].get_text(separator=" ", strip=True)
            value = cells[1].get_text(separator=" ", strip=True)

            if not label or not value:
                continue

            # Accept if label matches a known spec keyword OR the table
            # looks like a 2-column spec sheet (short label, longer value)
            if _is_spec_label(label) or (len(label) < 40 and len(value) < 200):
                # Clean up the label
                clean_label = re.sub(r"\s+", " ", label).strip(": ")
                clean_value = re.sub(r"\s+", " ", value).strip()
                if clean_label and clean_value and clean_label != clean_value:
                    specs[clean_label] = clean_value

    # ── Strategy 2: <dl> definition lists ────────────────────────────────────
    for dl in soup.find_all("dl"):
        terms = dl.find_all("dt")
        definitions = dl.find_all("dd")
        for dt, dd in zip(terms, definitions):
            label = dt.get_text(strip=True)
            value = dd.get_text(separator=" ", strip=True)
            if label and value:
                specs[label] = re.sub(r"\s+", " ", value).strip()

    # ── Strategy 3: div/li pairs with spec-like class names ──────────────────
    # Many modern sites use <div class="spec-label"> / <div class="spec-value">
    spec_containers = soup.find_all(
        True,
        class_=re.compile(r"spec|feature|detail|attribute", re.I)
    )
    for container in spec_containers:
        # Look for paired children: label + value
        children = [c for c in container.children if isinstance(c, Tag)]
        if len(children) == 2:
            label = children[0].get_text(strip=True)
            value = children[1].get_text(separator=" ", strip=True)
            if label and value and len(label) < 60:
                specs.setdefault(label, re.sub(r"\s+", " ", value).strip())

    return specs


def extract_prices(html: str) -> list[str]:
    """
    Pull price strings from the page text.
    Looks for patterns like ₹89,999 or Rs. 90,000 or $999.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text()

    # Match Indian rupee and USD price patterns
    pattern = r"(?:₹|Rs\.?\s*|INR\s*|USD?\s*\$?)\s*[\d,]+(?:\.\d{1,2})?"
    matches = re.findall(pattern, text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    prices: list[str] = []
    for m in matches:
        clean = re.sub(r"\s+", "", m).strip()
        if clean not in seen and len(clean) > 2:
            seen.add(clean)
            prices.append(clean)

    return prices[:10]   # top 10 price mentions


def extract_headings(html: str) -> list[str]:
    """Return h1–h3 headings from the page, cleaned."""
    soup = BeautifulSoup(html, "lxml")
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 3:
            headings.append(text)
    return headings[:15]


def extract_clean_text(html: str, max_chars: int = 6_000) -> str:
    """
    Strip all HTML and return readable body text.
    Removes scripts, styles, navs, footers first.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "aside"]):
        tag.decompose()

    paragraphs = [
        p.get_text(separator=" ", strip=True)
        for p in soup.find_all(["p", "li", "td", "th", "div", "span"])
        if len(p.get_text(strip=True)) > 15
    ]

    # Deduplicate adjacent duplicate lines
    seen_lines: set[str] = set()
    unique = []
    for p in paragraphs:
        if p not in seen_lines:
            seen_lines.add(p)
            unique.append(p)

    return "\n".join(unique)[:max_chars]


def full_extract(html: str) -> dict:
    """
    Run all extractors on a page's HTML and return a combined result dict.

    This is the main function called by the /extract endpoint and later
    by the Phase 3 LLM extraction pipeline.
    """
    return {
        "specs": extract_spec_tables(html),
        "prices": extract_prices(html),
        "headings": extract_headings(html),
        "text": extract_clean_text(html),
    }
