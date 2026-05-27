# AI Browser Research Agent

An autonomous multi-agent system that takes a natural-language research query, searches the web, visits product pages, extracts structured data using an LLM, and returns a ranked comparison report — all without any manual browsing.

**Example query:** *"best lightweight laptop under ₹90,000 for machine learning"*
**Output:** Structured specs table (CPU, GPU, RAM, price, weight) + AI-written comparison summary with a recommendation.

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                   FastAPI Server                     │
│  POST /research/full                                │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   LangGraph Pipeline  │
        └───────────┬───────────┘
                    │
    ┌───────────────▼──────────────────────┐
    │  1. Planner Node                     │
    │     Enriches query with spec terms   │
    │     and noisy-site exclusions        │
    └───────────────┬──────────────────────┘
                    │
    ┌───────────────▼──────────────────────┐
    │  2. Browser Node                     │
    │     DDG search + HTML fallbacks      │
    │     → filtered top URLs              │
    └───────────────┬──────────────────────┘
                    │
    ┌───────────────▼──────────────────────┐
    │  3. Extractor Node                   │
    │     Playwright visits each URL       │
    │     BeautifulSoup parses HTML        │
    │     Runs concurrently (asyncio)      │
    └───────────────┬──────────────────────┘
                    │
    ┌───────────────▼──────────────────────┐
    │  4. Analyzer Node                    │
    │     Groq (Llama 3.3 70B) extracts   │
    │     structured ProductInfo JSON      │
    │     Runs concurrently per page       │
    └───────────────┬──────────────────────┘
                    │
    ┌───────────────▼──────────────────────┐
    │  5. Summarizer Node                  │
    │     Ranks products, then Groq writes │
    │     comparison + recommendation      │
    └───────────────┬──────────────────────┘
                    │
                    ▼
            Structured JSON Response
          (products + summary + steps)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + uvicorn |
| Agent Orchestration | LangGraph (StateGraph) |
| LLM | Groq API — Llama 3.3 70B Versatile |
| Web Search | duckduckgo-search (DDGS) + Brave/Startpage HTML fallback |
| Browser Automation | Playwright (Chromium, headless) |
| HTML Parsing | BeautifulSoup4 + lxml |
| Data Validation | Pydantic v2 |
| Frontend | Vanilla JS + Tailwind CSS (single HTML file) |
| Deployment | Docker + Railway |

---

## Project Structure

```
ai-browser-agent/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── core/
│   │   └── config.py        # Settings + LLM singleton
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   ├── tools/
│   │   ├── browser.py       # search_web + visit_page
│   │   ├── extractor.py     # BeautifulSoup extraction strategies
│   │   └── llm_extractor.py # Groq structured extraction
│   └── agents/
│       ├── planner.py       # ResearchTask planner
│       └── graph.py         # LangGraph multi-agent pipeline
├── frontend.html            # Single-file UI (served at GET /)
├── Dockerfile
├── .dockerignore
├── railway.toml
├── requirements.txt
└── .env                     # API keys (not committed)
```

---

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/ai-browser-agent
cd ai-browser-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
APP_ENV=development
LOG_LEVEL=INFO
BROWSER_HEADLESS=true
BROWSER_TIMEOUT_MS=30000
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000` in your browser — the frontend loads automatically.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Frontend UI |
| `GET` | `/health` | Health check |
| `GET` | `/status` | Version + deployment info |
| `POST` | `/research` | Web search with optional page visits |
| `POST` | `/extract` | Structured HTML extraction from a URL |
| `POST` | `/analyze` | LLM extraction from a URL |
| `POST` | `/research/full` | Full multi-agent research pipeline |

### Example request

```bash
curl -X POST http://localhost:8000/research/full \
  -H "Content-Type: application/json" \
  -d '{"query": "best lightweight laptop under 90000 for ML", "max_results": 3}'
```

### Example response

```json
{
  "query": "best lightweight laptop under 90000 for ML",
  "products": [
    {
      "name": "ASUS VivoBook 16X",
      "cpu": "Intel Core i5-13500H",
      "gpu": "NVIDIA GeForce RTX 3050",
      "ram": "16 GB DDR4",
      "storage": "512 GB SSD",
      "display": "16 inch, 1920x1200, IPS",
      "weight": "1.88 kg",
      "price": "₹82,990",
      "source_url": "https://www.notebookcheck.net/..."
    }
  ],
  "summary": "The ASUS VivoBook 16X is the best pick for ML...",
  "steps_completed": [
    "planner: enriched query, fetch 3 results",
    "browser: found 3 URLs",
    "extractor: extracted text from 3 pages",
    "analyzer: extracted 2 structured products",
    "summarizer: generated comparison report"
  ]
}
```

---

## Deploy to Railway

The project is Dockerized and deployed with Railway. Local Docker preflight:

```bash
docker build -t ai-browser-agent:deploy-check .
docker run --rm -p 8001:8000 ai-browser-agent:deploy-check
curl http://localhost:8001/health
```

The Docker image excludes `.env`, `.venv`, logs, caches, and local database files via `.dockerignore`. The frontend uses the current origin for API calls, so it works on localhost and deployed URLs.

1. Push the project to GitHub (`.env` is gitignored — never committed)
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select your repo
4. Add environment variables in the Railway dashboard (same as `.env`)
5. Railway auto-detects the `Dockerfile` and builds + deploys

Your agent will be live at a public URL like `https://ai-browser-agent-production.up.railway.app`.

---

## How It Works — Deep Dive

### Why LangGraph?
LangGraph lets each agent node read from and write to a shared `AgentState` dict. Nodes are fully decoupled — the browser node doesn't know about the LLM, and the summarizer doesn't know about Playwright. This makes the system easy to extend: add a scoring node, a memory node, or a re-ranking step without touching existing nodes.

### Why Groq over OpenAI?
Groq's free tier gives access to Llama 3.3 70B — a genuinely capable open-source model — with very fast inference (tokens per second). No credit card required for development.

### Why multiple search fallbacks?
DuckDuckGo is the first search provider because `duckduckgo-search` avoids browser-based search flows and runs in a thread pool to avoid blocking the async event loop. If DDG rate-limits the request, the browser tool falls back to Brave and Startpage HTML result pages, then filters low-signal domains like YouTube, Quora, and social sites.

### Why concurrent extraction?
`asyncio.gather()` runs all page visits and LLM calls in parallel. For 3 results, this cuts wall-clock time from ~45s (sequential) to ~15s (parallel).

### Why lightweight ranking?
The current ranking step uses a small domain heuristic before summarization. For ML-oriented laptop queries, it prefers dedicated NVIDIA/RTX GPUs, then considers CPU class, RAM, storage, price-vs-budget, and lightweight hints when available. This keeps the architecture simple while still producing better recommendations than raw search order.

---

## Current Status

- FastAPI backend with health, status, search, extraction, analysis, and full research endpoints
- LangGraph pipeline for planning, searching, extracting, analyzing, ranking, and summarizing
- Playwright-powered page visits with BeautifulSoup cleanup
- Groq/Llama-powered structured product extraction and comparison summaries
- Search fallback chain using DuckDuckGo, Brave, and Startpage
- Lightweight ranking heuristic for laptop recommendations
- Single-file Tailwind frontend served by the API
- Dockerized deployment with Railway support

## Future Improvements

- Add citations inside the generated summary, not just source links on product cards
- Track LLM/search calls and estimated cost per research run
- Add optional memory for user preferences such as budget, brands, and use cases
- Improve product deduplication across list pages and review pages
- Add screenshots or a short demo GIF for portfolio presentation

---

## License

MIT
