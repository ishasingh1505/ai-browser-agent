"""
Pydantic schemas for API request/response.

Phase 1: ResearchRequest / ResearchResponse
Phase 3 will add: ProductInfo, ComparisonResult
Phase 6 will add: UserPreference
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Phase 1: Core research flow ───────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Natural-language research query")
    max_results: int = Field(default=6, ge=1, le=20, description="Max search results to fetch")
    deep_visit: bool = Field(default=False, description="If true, visit each page and extract content")


class SearchResult(BaseModel):
    title: str
    url: str


class PageContent(BaseModel):
    url: str
    title: str
    headings: list[str]
    text_preview: str  # first 500 chars of extracted text


class ResearchResponse(BaseModel):
    query: str
    search_results: list[SearchResult]
    pages: list[PageContent] = Field(default_factory=list)
    status: str = "ok"
    message: str = ""


# ── Phase 2: Structured extraction response ───────────────────────────────────

class ExtractRequest(BaseModel):
    url: str = Field(..., description="URL of the page to visit and extract specs from")


class ExtractResponse(BaseModel):
    url: str
    specs: dict[str, str] = Field(default_factory=dict, description="Key-value product specs from tables")
    prices: list[str] = Field(default_factory=list, description="Price strings found on the page")
    headings: list[str] = Field(default_factory=list, description="H1-H3 headings")
    text: str = Field(default="", description="Clean readable body text")
    status: str = "ok"


# ── Phase 3 placeholder: Structured product extraction ────────────────────────

class ProductInfo(BaseModel):
    """Populated in Phase 3 via LLM extraction."""
    name: str = ""
    price: str = ""
    cpu: str = ""
    gpu: str = ""
    ram: str = ""
    storage: str = ""
    display: str = ""
    battery: str = ""
    weight: str = ""
    os: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    source_url: str = ""


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="URL to visit, scrape, and analyze with the LLM")


class AnalyzeResponse(BaseModel):
    product: ProductInfo
    raw_text_preview: str = Field(default="", description="First 300 chars of scraped text for debugging")
    llm_raw: str = Field(default="", description="Raw LLM response for debugging")
    status: str = "ok"


# ── Phase 4: Full agent pipeline ─────────────────────────────────────────────

class FullResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Natural-language research query")
    max_results: int = Field(default=4, ge=1, le=8, description="Number of pages to analyze")


class FullResearchResponse(BaseModel):
    query: str
    products: list[ProductInfo] = Field(default_factory=list)
    summary: str = Field(default="", description="LLM-generated comparison summary")
    steps_completed: list[str] = Field(default_factory=list, description="Agent steps that ran")
    status: str = "ok"


# ── Phase 6 placeholder: User preferences ─────────────────────────────────────

class UserPreference(BaseModel):
    """Stored in ChromaDB in Phase 6."""
    key: str
    value: str
    embedding: list[float] = Field(default_factory=list)
