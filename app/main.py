"""
AI Browser Research Agent — FastAPI entry point.

Phase 1 endpoints:
  GET  /          → health check
  POST /research  → accepts query, searches web, optionally visits pages

Phase 2 endpoints:
  POST /extract   → visit a URL and return structured specs, prices, headings
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.core.config import settings
from app.models.schemas import (
    ResearchRequest, ResearchResponse, SearchResult, PageContent,
    ExtractRequest, ExtractResponse,
    AnalyzeRequest, AnalyzeResponse,
    FullResearchRequest, FullResearchResponse,
)
from app.tools.browser import search_web, visit_page, close_browser
from app.tools.extractor import full_extract
from app.tools.llm_extractor import extract_product_with_llm
from app.agents.planner import PlannerAgent
from app.agents.graph import research_graph

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("research-agent")


# ── Lifespan: startup / shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Starting AI Browser Research Agent (env=%s)", settings.app_env)
    yield
    log.info("🛑 Shutting down — closing browser...")
    await close_browser()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Browser Research Agent",
    description="Agentic system that autonomously browses the web, extracts product intelligence, and generates ranked comparative reports.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

planner = PlannerAgent()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["UI"])
async def frontend():
    """Serve the frontend UI."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend.html")
    return FileResponse(html_path)


@app.get("/status", tags=["Health"])
async def root():
    return {
        "service": "AI Browser Research Agent",
        "version": "0.1.0",
        "status": "running",
        "phase": "9b",
        "deployment": "docker-ready",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse, tags=["Research"])
async def research(req: ResearchRequest):
    """
    Core research endpoint.

    - Accepts a natural-language query.
    - Runs the planner to build a task list (Phase 1: single search step).
    - Executes the search via Playwright → returns top URLs + titles.
    - If `deep_visit=true`, also visits each page and extracts readable content.
    """
    log.info("📥 Research request: query=%r  max=%d  deep=%s", req.query, req.max_results, req.deep_visit)

    # Step 1 — Plan
    plan = planner.create_plan(req.query)
    log.info("📋 Plan: %d task(s)", len(plan))

    # Step 2 — Search
    try:
        raw_results = await search_web(req.query, max_results=req.max_results)
    except Exception as exc:
        log.exception("Browser search failed")
        raise HTTPException(status_code=502, detail=f"Browser search failed: {exc}") from exc

    search_results = [SearchResult(title=r["title"], url=r["url"]) for r in raw_results]
    log.info("🔎 Found %d results", len(search_results))

    # Step 3 — Deep visit (optional)
    pages: list[PageContent] = []
    if req.deep_visit and search_results:
        for result in search_results[:3]:   # visit top 3 only in Phase 1
            try:
                log.info("🌐 Visiting: %s", result.url)
                page_data = await visit_page(result.url)
                pages.append(PageContent(
                    url=page_data["url"],
                    title=page_data["title"],
                    headings=page_data["headings"][:5],
                    text_preview=page_data["text"][:500],
                ))
            except Exception as exc:
                log.warning("Failed to visit %s: %s", result.url, exc)
                continue

    return ResearchResponse(
        query=req.query,
        search_results=search_results,
        pages=pages,
        message=f"Found {len(search_results)} results" + (f", visited {len(pages)} pages" if pages else ""),
    )


@app.post("/extract", response_model=ExtractResponse, tags=["Research"])
async def extract(req: ExtractRequest):
    """
    Phase 2 — Structured extraction endpoint.

    - Visits the given URL with Playwright.
    - Runs BeautifulSoup extraction across 3 strategies:
        1. HTML <table> spec sheets
        2. <dl> definition lists
        3. Div/li pairs with spec-like CSS classes
    - Also pulls prices (₹/$ patterns) and clean body text.

    Use this to turn any product page into structured data before
    feeding it to the LLM in Phase 3.
    """
    log.info("🔬 Extract request: url=%s", req.url)

    try:
        page_data = await visit_page(req.url)
    except Exception as exc:
        log.exception("Failed to visit page")
        raise HTTPException(status_code=502, detail=f"Could not visit page: {exc}") from exc

    extracted = full_extract(page_data["html"])

    log.info(
        "✅ Extracted %d specs, %d prices from %s",
        len(extracted["specs"]), len(extracted["prices"]), req.url
    )

    return ExtractResponse(
        url=req.url,
        specs=extracted["specs"],
        prices=extracted["prices"],
        headings=extracted["headings"],
        text=extracted["text"],
    )


@app.post("/analyze", response_model=AnalyzeResponse, tags=["Research"])
async def analyze(req: AnalyzeRequest):
    """
    Phase 3 — LLM-powered structured extraction.

    Full pipeline in one call:
      1. Visit the URL with Playwright (scroll, handle popups)
      2. Extract clean text with BeautifulSoup
      3. Send text to Groq with a structured extraction prompt
      4. Return a clean ProductInfo JSON — name, CPU, GPU, RAM, price, etc.

    Works on ANY laptop page regardless of HTML structure.
    """
    log.info("🧠 Analyze request: url=%s", req.url)

    # Step 1 — Visit and scrape
    try:
        page_data = await visit_page(req.url)
    except Exception as exc:
        log.exception("Failed to visit page")
        raise HTTPException(status_code=502, detail=f"Could not visit page: {exc}") from exc

    # Step 2 — Extract clean text
    # Try full_extract first (BeautifulSoup pipeline), fall back to
    # the text already computed inside visit_page if extraction yields nothing
    extracted = full_extract(page_data["html"])
    text = extracted["text"].strip() or page_data["text"].strip()

    # Last resort — use raw headings joined together
    if not text:
        text = " ".join(page_data.get("headings", []))

    if not text:
        raise HTTPException(status_code=422, detail="Page returned no readable content. It may require JavaScript or block headless browsers.")

    log.info("📄 Extracted %d chars of text for LLM extraction", len(text))

    # Step 3 — Send to Groq
    product, llm_raw = await extract_product_with_llm(text=text, source_url=req.url)

    log.info("📦 Extracted product: %s | CPU: %s | Price: %s", product.name, product.cpu, product.price)

    return AnalyzeResponse(
        product=product,
        raw_text_preview=text[:300],
        llm_raw=llm_raw[:500],
    )


@app.post("/research/full", response_model=FullResearchResponse, tags=["Research"])
async def full_research(req: FullResearchRequest):
    """
    Phase 4 — Full multi-agent research pipeline.

    Runs the complete LangGraph agent graph in one call:
      1. Planner   → understands the query
      2. Browser   → searches the web, gets URLs
      3. Extractor → visits each page, pulls clean text
      4. Analyzer  → sends each page to Groq, gets structured ProductInfo
      5. Summarizer → generates a human-readable comparison + recommendation

    This is the flagship endpoint of the Agentic Web Research System.
    """
    log.info("🚀 Full research pipeline: query=%r  max=%d", req.query, req.max_results)

    initial_state: dict = {
        "query": req.query,
        "max_results": req.max_results,
        "search_results": [],
        "raw_pages": [],
        "products": [],
        "steps_completed": [],
        "errors": [],
        "summary": "",
    }

    try:
        final_state = await research_graph.ainvoke(initial_state)
    except Exception as exc:
        log.exception("Agent graph failed")
        raise HTTPException(status_code=500, detail=f"Agent pipeline failed: {exc}") from exc

    log.info(
        "✅ Pipeline complete: %d products | steps: %s",
        len(final_state.get("products", [])),
        final_state.get("steps_completed", []),
    )

    return FullResearchResponse(
        query=req.query,
        products=final_state.get("products", []),
        summary=final_state.get("summary", ""),
        steps_completed=final_state.get("steps_completed", []),
    )
