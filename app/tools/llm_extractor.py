"""
LLM Extractor — Phase 3

Takes raw text scraped from a webpage and uses Groq to extract
structured product information as a clean ProductInfo object.

Why LLM instead of pure BeautifulSoup?
  Every website has a different HTML structure. Rather than writing
  custom parsers for each site, we give the messy text to an LLM
  and ask it to find the specs — works on ANY site automatically.

Flow:
  raw page text
      ↓
  build_extraction_prompt()
      ↓
  Groq chat model
      ↓
  parse JSON response
      ↓
  ProductInfo (Pydantic model)
"""

from __future__ import annotations

import json
import logging
import re

from app.core.config import get_llm
from app.models.schemas import ProductInfo

log = logging.getLogger("llm-extractor")


# ── Prompt ────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are a product data extraction expert.

Below is raw text scraped from a laptop product or review webpage.
Extract the laptop specifications and return ONLY a valid JSON object — no markdown, no explanation, just JSON.

If a field is not found in the text, use an empty string "" for strings or [] for lists.
If the page lists multiple laptops, choose the single best concrete laptop for the user's query.
The "name" field must be an actual laptop model name from the text. Do not return "Unknown Product", "Unknown", "Laptop", or a generic category name.

JSON schema to follow exactly:
{{
  "name": "Full product name",
  "price": "Price as string e.g. ₹89999 or $999 or 1100 euro",
  "cpu": "Processor name and model",
  "gpu": "Graphics card name",
  "ram": "RAM size and type e.g. 16GB LPDDR5",
  "storage": "Storage size and type e.g. 512GB NVMe SSD",
  "display": "Display size, resolution, refresh rate",
  "battery": "Battery capacity or life e.g. 72Wh or 10 hours",
  "weight": "Weight e.g. 1.5kg",
  "os": "Operating system",
  "pros": ["pro 1", "pro 2"],
  "cons": ["con 1", "con 2"],
  "source_url": ""
}}

Raw webpage text:
---
{text}
---

Return only the JSON object:"""


# ── Main extraction function ──────────────────────────────────────────────────

async def extract_product_with_llm(
    text: str,
    source_url: str = "",
    max_text_chars: int = 10_000,
) -> tuple[ProductInfo, str]:
    """
    Send scraped page text to the LLM and get back a structured ProductInfo.

    Args:
        text:           Raw text extracted from the page (from extractor.py)
        source_url:     Original URL, stored in the result for traceability
        max_text_chars: Truncate text to avoid hitting token limits

    Returns:
        ProductInfo — a Pydantic model with all laptop fields populated
    """
    # Truncate to avoid hitting context limits
    truncated = text[:max_text_chars]

    prompt = EXTRACTION_PROMPT.format(text=truncated)

    log.info("🤖 Sending %d chars to Groq for extraction...", len(truncated))

    try:
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        raw = response.content.strip()
        log.info("✅ Groq responded (%d chars)", len(raw))
    except Exception as exc:
        log.exception("LLM call failed")
        error_msg = f"LLM call failed: {exc}"
        return ProductInfo(source_url=source_url), error_msg

    # ── Parse JSON from response ──────────────────────────────────────────────
    product = _parse_json_response(raw, source_url)
    product.source_url = source_url
    if product.name.strip().lower() in {"unknown", "unknown product", "laptop", "product"}:
        product.name = ""
    return product, raw


def _parse_json_response(raw: str, source_url: str) -> ProductInfo:
    """
    Parse the LLM response into a ProductInfo.
    Handles cases where the model wraps JSON in markdown code fences.
    """
    # Strip markdown code fences if present: ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = cleaned.rstrip("`").strip()

    try:
        data = json.loads(cleaned)
        product = ProductInfo(
            name=data.get("name", ""),
            price=data.get("price", ""),
            cpu=data.get("cpu", ""),
            gpu=data.get("gpu", ""),
            ram=data.get("ram", ""),
            storage=data.get("storage", ""),
            display=data.get("display", ""),
            battery=data.get("battery", ""),
            weight=data.get("weight", ""),
            os=data.get("os", ""),
            pros=data.get("pros", []),
            cons=data.get("cons", []),
            source_url=source_url,
        )
        if product.name.strip().lower() in {"unknown", "unknown product", "laptop", "product"}:
            product.name = ""
        return product
    except json.JSONDecodeError as exc:
        log.warning("Failed to parse JSON from LLM response: %s\nRaw: %s", exc, raw[:300])
        # Return empty ProductInfo rather than crashing
        return ProductInfo(source_url=source_url)
