"""
LangGraph Agent Graph — Phase 4

Wires all tools into a sequential multi-agent pipeline:

  planner_node
      ↓
  browser_node      (search_web → get URLs)
      ↓
  extractor_node    (visit_page + full_extract → raw text per URL)
      ↓
  analyzer_node     (Groq → structured ProductInfo per URL)
      ↓
  summarizer_node   (Groq → human-readable comparison summary)
      ↓
  END

Each node reads from and writes to a shared AgentState dict.
This is what makes it a real agentic system — nodes are decoupled,
state flows through the graph, and each step builds on the last.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TypedDict, Annotated
import operator
import re

from langgraph.graph import StateGraph, END

from app.tools.browser import search_web, visit_page
from app.tools.extractor import full_extract
from app.tools.llm_extractor import extract_product_with_llm
from app.models.schemas import ProductInfo
from app.core.config import get_llm

log = logging.getLogger("agent-graph")


def _parse_budget(query: str) -> int | None:
    """Return a simple numeric budget from phrases like 'under 90000'."""
    match = re.search(r"(?:under|below|less than)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", query, re.I)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _parse_price(price: str) -> int | None:
    match = re.search(r"[\d,]+", price or "")
    if not match:
        return None
    return int(match.group(0).replace(",", ""))


def _parse_weight_kg(weight: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*kg", weight or "", re.I)
    if not match:
        return None
    return float(match.group(1))


def _rank_score(product: ProductInfo, query: str) -> int:
    """Small domain heuristic until the roadmap's dedicated scoring node exists."""
    score = 0
    query_l = query.lower()
    cpu = product.cpu.lower()
    gpu = product.gpu.lower()
    ram = product.ram.lower()
    storage = product.storage.lower()

    wants_ml = any(term in query_l for term in ("ml", "machine learning", "ai", "data science"))
    if wants_ml:
        if "rtx" in gpu:
            score += 45
        elif any(term in gpu for term in ("nvidia", "geforce", "radeon", "arc")):
            score += 30

    if any(term in cpu for term in ("ryzen 9", "core i9", "ultra 9")):
        score += 16
    elif any(term in cpu for term in ("ryzen 7", "core i7", "ultra 7")):
        score += 12
    elif any(term in cpu for term in ("ryzen 5", "core i5", "ultra 5")):
        score += 8

    ram_match = re.search(r"(\d+)\s*gb", ram)
    if ram_match:
        ram_gb = int(ram_match.group(1))
        if ram_gb >= 32:
            score += 12
        elif ram_gb >= 16:
            score += 8

    if "1tb" in storage or "1024" in storage:
        score += 4
    elif "512" in storage:
        score += 2

    budget = _parse_budget(query)
    price = _parse_price(product.price)
    if budget and price:
        score += 6 if price <= budget else -10

    if "lightweight" in query_l or "portable" in query_l:
        weight = _parse_weight_kg(product.weight)
        if weight is not None:
            if weight <= 1.5:
                score += 8
            elif weight <= 1.8:
                score += 5
            elif weight > 2.2:
                score -= 5

    return score


# ── Shared state flowing through the graph ────────────────────────────────────

class AgentState(TypedDict):
    # Input
    query: str
    max_results: int

    # Accumulated across nodes — lists use operator.add so nodes can append
    search_results: Annotated[list[dict], operator.add]   # [{title, url}]
    raw_pages: Annotated[list[dict], operator.add]        # [{url, text, html}]
    products: Annotated[list[ProductInfo], operator.add]  # structured products
    steps_completed: Annotated[list[str], operator.add]   # audit trail
    errors: Annotated[list[str], operator.add]            # non-fatal errors

    # Final output
    summary: str


# ── Node 1: Planner ───────────────────────────────────────────────────────────

async def planner_node(state: AgentState) -> dict:
    """
    Receives the user query and decides how many results to fetch.
    Phase 4: trivial passthrough — just logs the plan.
    Phase 5+ will use an LLM to generate a richer research plan.
    """
    query = state["query"]
    max_results = state.get("max_results", 4)
    log.info("📋 Planner: query=%r  max=%d", query, max_results)

    # Enrich query toward pages that are likely to include real model names
    # and specs, without locking search to a single site.
    enriched_query = (
        f"{query} laptop specifications price weight RTX Ryzen Intel India review "
        "-youtube -quora -facebook -instagram"
    )

    return {
        "query": enriched_query,
        "steps_completed": [f"planner: enriched query, fetch {max_results} results"],
    }


# ── Node 2: Browser ───────────────────────────────────────────────────────────

async def browser_node(state: AgentState) -> dict:
    """
    Runs search_web() and returns a list of {title, url} dicts.
    """
    query = state["query"]
    max_results = state.get("max_results", 4)

    log.info("🔎 Browser: searching for %r", query)

    try:
        results = await search_web(query, max_results=max_results)
        log.info("🔎 Browser: found %d results", len(results))
        return {
            "search_results": results,
            "steps_completed": [f"browser: found {len(results)} URLs"],
        }
    except Exception as exc:
        log.exception("Browser node failed")
        error = str(exc)
        return {
            "search_results": [],
            "errors": [f"browser_node: {error}"],
            "steps_completed": [f"browser: failed ({error[:160]})"],
        }


# ── Node 3: Extractor ─────────────────────────────────────────────────────────

async def extractor_node(state: AgentState) -> dict:
    """
    Visits each URL and extracts clean text using Playwright + BeautifulSoup.
    Runs visits concurrently with asyncio.gather for speed.
    """
    search_results = state.get("search_results", [])
    if not search_results:
        return {
            "raw_pages": [],
            "steps_completed": ["extractor: no URLs to visit"],
        }

    log.info("🌐 Extractor: visiting %d pages concurrently", len(search_results))

    async def visit_and_extract(result: dict) -> dict | None:
        url = result["url"]
        try:
            page_data = await visit_page(url)
            extracted = full_extract(page_data["html"])
            headings = extracted["headings"] or page_data.get("headings", [])
            body_text = extracted["text"].strip() or page_data["text"].strip()
            context_parts = [
                f"Search result title: {result.get('title', '')}",
                f"Page title: {page_data.get('title', '')}",
                "Page headings:\n" + "\n".join(headings[:20]),
                "Page text:\n" + body_text,
            ]
            text = "\n\n".join(part for part in context_parts if part.strip())
            if not text:
                return None
            return {
                "url": url,
                "title": page_data.get("title", ""),
                "search_title": result.get("title", ""),
                "text": text,
                "html": page_data["html"],
            }
        except Exception as exc:
            log.warning("Failed to visit %s: %s", url, exc)
            return None

    # Visit all pages concurrently
    results = await asyncio.gather(*[visit_and_extract(result) for result in search_results])
    pages = [r for r in results if r is not None]

    log.info("🌐 Extractor: extracted text from %d/%d pages", len(pages), len(search_results))

    return {
        "raw_pages": pages,
        "steps_completed": [f"extractor: extracted text from {len(pages)} pages"],
    }


# ── Node 4: Analyzer ──────────────────────────────────────────────────────────

async def analyzer_node(state: AgentState) -> dict:
    """
    Sends each page's text to the LLM and gets back a structured ProductInfo.
    Also runs concurrently — one LLM call per page in parallel.
    """
    pages = state.get("raw_pages", [])
    if not pages:
        return {
            "products": [],
            "steps_completed": ["analyzer: no pages to analyze"],
        }

    log.info("🤖 Analyzer: sending %d pages to Groq", len(pages))

    skipped_pages: list[str] = []
    errors_found: list[str] = []

    async def analyze_page(page: dict) -> ProductInfo | None:
        try:
            product, raw = await extract_product_with_llm(
                text=page["text"],
                source_url=page["url"],
            )
            if raw.startswith("LLM call failed") or raw.startswith("Groq") or "failed" in raw.lower():
                errors_found.append(f"LLM error for {page['url']}: {raw[:120]}")
                return None
            if not product.name.strip():
                skipped_pages.append(page["url"])
                return None

            # Keep product only if it has a name and at least one useful detail.
            if not any([product.cpu, product.gpu, product.ram, product.price,
                        product.display, product.weight, product.storage]):
                skipped_pages.append(page["url"])
                return None
            return product
        except Exception as exc:
            errors_found.append(f"Exception for {page['url']}: {exc}")
            log.warning("LLM extraction failed for %s: %s", page["url"], exc)
            return None

    results = await asyncio.gather(*[analyze_page(p) for p in pages])
    products = [r for r in results if r is not None]
    products.sort(key=lambda p: _rank_score(p, state["query"]), reverse=True)

    log.info(
        "🤖 Analyzer: structured %d products, skipped %d pages, %d errors",
        len(products), len(skipped_pages), len(errors_found)
    )

    steps = [f"analyzer: extracted {len(products)} structured products"]
    if skipped_pages:
        steps.append(f"analyzer: skipped {len(skipped_pages)} low-quality page(s)")
    if errors_found:
        steps.extend([f"analyzer error: {e}" for e in errors_found])

    return {
        "products": products,
        "steps_completed": steps,
    }


# ── Node 5: Summarizer ────────────────────────────────────────────────────────

async def summarizer_node(state: AgentState) -> dict:
    """
    Takes all structured products and asks the LLM to write a
    human-readable comparison summary with a recommendation.
    """
    products = state.get("products", [])
    query = state["query"]

    if not products:
        return {
            "summary": "No products could be extracted for comparison.",
            "steps_completed": ["summarizer: no products to summarize"],
        }

    # Build a compact product list for the prompt
    product_lines = []
    for i, p in enumerate(products, 1):
        line = (
            f"{i}. {p.name or 'Unknown'} | "
            f"CPU: {p.cpu or '?'} | "
            f"GPU: {p.gpu or '?'} | "
            f"RAM: {p.ram or '?'} | "
            f"Display: {p.display or '?'} | "
            f"Weight: {p.weight or '?'} | "
            f"Price: {p.price or '?'}"
        )
        product_lines.append(line)

    products_text = "\n".join(product_lines)

    prompt = f"""You are an expert laptop advisor.

A user asked: "{query}"

Here are the laptops found:
{products_text}

The laptops are already ordered by a lightweight suitability score. For machine learning queries, prefer a dedicated NVIDIA/RTX GPU when present, but call out missing price, RAM, or weight data honestly. Do not say the user must stretch their budget unless a listed price is actually above their budget.

Write a concise 3-5 sentence comparison summary. Include:
- Which laptop is best for the user's use case and why
- Key trade-offs between the options
- A clear final recommendation

Keep it friendly and direct."""

    log.info("📝 Summarizer: generating comparison summary...")

    try:
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        summary = response.content.strip()
    except Exception as exc:
        log.warning("Summarizer LLM call failed: %s", exc)
        summary = f"Found {len(products)} laptops. LLM summary unavailable — check your API quota."

    return {
        "summary": summary,
        "steps_completed": ["summarizer: generated comparison report"],
    }


# ── Build the graph ───────────────────────────────────────────────────────────

def build_research_graph() -> StateGraph:
    """
    Assemble and compile the full research agent graph.
    Returns a compiled LangGraph that can be invoked with a query.
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("planner", planner_node)
    graph.add_node("browser", browser_node)
    graph.add_node("extractor", extractor_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("summarizer", summarizer_node)

    # Wire edges: linear flow for now
    # Phase 5+ can add conditional edges (e.g. retry if 0 products found)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "browser")
    graph.add_edge("browser", "extractor")
    graph.add_edge("extractor", "analyzer")
    graph.add_edge("analyzer", "summarizer")
    graph.add_edge("summarizer", END)

    return graph.compile()


# Singleton compiled graph
research_graph = build_research_graph()
