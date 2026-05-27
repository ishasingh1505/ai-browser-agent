# AI Browser Research Agent — Personal Project Guide

## 1. What This Project Is

AI Browser Research Agent is an autonomous web research application. It takes a natural-language query, searches the web, visits relevant pages, extracts product information, ranks the results, and generates a short comparison summary with a recommendation.

The main demo use case is laptop research, for example:

```text
best lightweight laptop under 90000 for ML
```

The app then attempts to return:

- Relevant laptop products
- Structured specifications such as CPU, GPU, RAM, storage, display, battery, weight, price, and OS
- Source links for each product
- A ranked recommendation summary
- A visible step-by-step trace of what the agent did

The project is useful because it combines practical web automation, LLM extraction, agent orchestration, backend APIs, frontend UI, and cloud deployment in one working system.

## 2. One-Line Resume Description

Built and deployed an autonomous AI web research agent using FastAPI, LangGraph, Playwright, BeautifulSoup, and Groq/Llama to search the web, extract structured product data, rank results, and generate comparison summaries through a web UI.

## 3. Longer Portfolio Description

AI Browser Research Agent is a full-stack agentic research tool that automates product comparison workflows. The user enters a natural-language research query, and the backend runs a LangGraph pipeline that plans the search, gathers URLs from multiple search providers, visits pages with Playwright, cleans and extracts page text with BeautifulSoup, uses Groq-hosted Llama for structured product extraction, ranks the products with a lightweight domain heuristic, and returns a comparison summary through a simple Tailwind frontend.

The project is Dockerized and deployed on Railway. It includes search fallbacks for rate-limited providers, safe environment-variable handling, and a deployable frontend that works both locally and in production.

## 4. Key Technologies

| Area | Technology |
|---|---|
| Backend API | FastAPI |
| Server | Uvicorn |
| Agent orchestration | LangGraph |
| LLM provider | Groq |
| LLM model | Llama 3.3 70B Versatile |
| Browser automation | Playwright |
| HTML parsing | BeautifulSoup + lxml |
| Search | DuckDuckGo Search + Brave/Startpage fallback |
| Validation | Pydantic v2 |
| Frontend | Vanilla JavaScript + Tailwind CSS |
| Deployment | Docker + Railway |

## 5. High-Level Architecture

```text
User Query
   |
   v
FastAPI Backend
   |
   v
LangGraph Agent Pipeline
   |
   +--> Planner Node
   |      Enriches the query with useful laptop/spec terms
   |
   +--> Browser Node
   |      Searches the web using DDG, Brave, and Startpage fallback
   |
   +--> Extractor Node
   |      Uses Playwright to visit pages and BeautifulSoup to clean text
   |
   +--> Analyzer Node
   |      Sends page text to Groq/Llama for structured JSON extraction
   |
   +--> Ranking Step
   |      Scores products based on ML suitability, GPU, CPU, RAM, price, etc.
   |
   +--> Summarizer Node
          Uses Groq/Llama to write the final recommendation
```

The frontend calls:

```text
POST /research/full
```

and displays:

- Agent steps
- Summary
- Product cards
- Source links

## 6. Main User Flow

1. User opens the frontend.
2. User enters a research query.
3. Frontend sends query to the backend.
4. Planner enriches the query.
5. Browser node searches for relevant pages.
6. Extractor visits pages concurrently.
7. Analyzer extracts structured product data with an LLM.
8. Low-quality pages are skipped.
9. Products are ranked.
10. Summarizer writes a recommendation.
11. Frontend displays the result.

## 7. Project Folder Structure

```text
ai-browser-agent/
├── app/
│   ├── main.py
│   ├── agents/
│   │   ├── graph.py
│   │   └── planner.py
│   ├── core/
│   │   └── config.py
│   ├── models/
│   │   └── schemas.py
│   └── tools/
│       ├── browser.py
│       ├── extractor.py
│       └── llm_extractor.py
├── frontend.html
├── README.md
├── PROJECT_GUIDE.md
├── requirements.txt
├── Dockerfile
├── railway.toml
├── run.sh
├── .env.example
├── .gitignore
└── .dockerignore
```

## 8. File-by-File Explanation

### `app/main.py`

This is the FastAPI entry point.

Important responsibilities:

- Creates the FastAPI app
- Adds CORS middleware
- Serves the frontend at `/`
- Provides health/status endpoints
- Defines research/extraction/analyze/full-pipeline endpoints
- Calls the LangGraph pipeline for `/research/full`
- Closes the shared Playwright browser during shutdown

Important endpoints:

```text
GET  /
GET  /health
GET  /status
POST /research
POST /extract
POST /analyze
POST /research/full
```

### `app/agents/graph.py`

This is the heart of the agent system.

It defines:

- `AgentState`
- `planner_node`
- `browser_node`
- `extractor_node`
- `analyzer_node`
- `summarizer_node`
- lightweight ranking helpers
- compiled LangGraph object

The graph is currently linear:

```text
planner -> browser -> extractor -> analyzer -> summarizer -> END
```

This is intentionally simple and readable.

### `app/agents/planner.py`

This contains a basic planner abstraction.

It currently creates simple research tasks and is kept as a clean place to expand planning later.

### `app/tools/browser.py`

This handles search and page visits.

Important responsibilities:

- Search web using DuckDuckGo first
- Fall back to Brave and Startpage if needed
- Filter low-quality domains like YouTube, Quora, Facebook, Instagram, Reddit, etc.
- Launch a shared Playwright Chromium browser
- Visit pages with realistic user agent
- Click common cookie consent buttons
- Scroll pages to trigger lazy-loaded content
- Extract HTML, title, headings, and readable text

This file is important because web search often fails due to rate limits. The fallback system makes the app more robust.

### `app/tools/extractor.py`

This is a pure BeautifulSoup parser.

It extracts:

- Spec tables
- Definition lists
- Spec-like div/list structures
- Prices
- Headings
- Clean body text

It does not make network calls, so it is easier to test and reason about.

### `app/tools/llm_extractor.py`

This sends cleaned page text to Groq/Llama and asks the model to return structured product JSON.

It also:

- Truncates text to avoid too much context
- Parses JSON responses
- Handles markdown code fences
- Rejects generic names like `Unknown Product`

### `app/core/config.py`

This manages environment settings.

Important values:

```text
GROQ_API_KEY
GROQ_MODEL
APP_ENV
LOG_LEVEL
BROWSER_HEADLESS
BROWSER_TIMEOUT_MS
CHROMA_PERSIST_DIR
```

It also defines `get_llm()`, which returns a cached Groq chat model.

### `app/models/schemas.py`

This contains the Pydantic request and response models.

Important models:

- `ResearchRequest`
- `ResearchResponse`
- `ExtractRequest`
- `ExtractResponse`
- `ProductInfo`
- `AnalyzeRequest`
- `AnalyzeResponse`
- `FullResearchRequest`
- `FullResearchResponse`

### `frontend.html`

This is the frontend UI.

It:

- Lets the user type a query
- Lets the user choose number of results
- Calls `/research/full`
- Shows live-looking agent steps while waiting
- Displays final steps, summary, and product cards

Important deployment detail:

```js
const API = window.location.origin;
```

This lets the frontend work on both:

```text
http://localhost:8000
https://railway-deployment-url
```

### `Dockerfile`

Uses Microsoft’s official Playwright Python image. This is important because Playwright needs browser dependencies that are annoying to install manually.

The Docker image:

- Installs Python requirements
- Copies app files
- Starts Uvicorn

### `railway.toml`

Railway deployment config.

Important command:

```toml
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```

This matters because Railway injects a dynamic `PORT`. The shell command ensures `${PORT}` is expanded correctly.

### `.dockerignore`

Prevents unsafe or unnecessary files from entering the Docker image.

Important exclusions:

```text
.env
.venv/
__pycache__/
logs/
chroma_db/
.DS_Store
```

### `.env.example`

Shows what environment variables are required, but does not contain real secrets.

## 9. Environment Variables

Local `.env` example:

```env
GROQ_API_KEY=your_real_key_here
GROQ_MODEL=llama-3.3-70b-versatile
APP_ENV=development
LOG_LEVEL=INFO
BROWSER_HEADLESS=true
BROWSER_TIMEOUT_MS=30000
```

Railway variables:

```env
GROQ_API_KEY=your_real_key_here
GROQ_MODEL=llama-3.3-70b-versatile
APP_ENV=production
LOG_LEVEL=INFO
BROWSER_HEADLESS=true
BROWSER_TIMEOUT_MS=30000
```

Never upload `.env` to GitHub.

## 10. Running Locally

From the project folder:

```bash
cd "/Users/issingh/Desktop/Agentic AI/ai-browser-agent"
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/health
```

API docs:

```text
http://localhost:8000/docs
```

## 11. Running With Docker

Build:

```bash
docker build -t ai-browser-agent:deploy-check .
```

Run:

```bash
docker run --rm -p 8001:8000 ai-browser-agent:deploy-check
```

Test:

```bash
curl http://localhost:8001/health
```

Expected:

```json
{"status":"ok"}
```

## 12. Railway Deployment Flow

1. Create GitHub repo.
2. Upload safe project files.
3. Do not upload `.env`.
4. Create Railway project from GitHub repo.
5. Configure Railway GitHub App access if repo does not appear.
6. Add Railway variables.
7. Deploy.
8. Generate public domain.
9. Test `/health`.
10. Test the frontend.

Important Railway fix:

```toml
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```

Without this, Railway may pass `$PORT` literally and Uvicorn will fail with:

```text
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

## 13. Security Notes

Do not upload:

```text
.env
.venv/
logs/
chroma_db/
__pycache__/
.DS_Store
```

Why:

- `.env` contains secrets.
- `.venv` is huge and machine-specific.
- logs can leak queries, errors, URLs, or local paths.
- local vector DB files may contain user data later.
- caches and macOS files are useless in production.

## 14. What Makes This Project Agentic

This project is agentic because it is not a single prompt call. It coordinates multiple steps, each with its own role:

- planning
- searching
- browsing
- extracting
- analyzing
- ranking
- summarizing

Each step reads from and writes to a shared state object managed by LangGraph.

The app also exposes intermediate steps to the user, which makes the process more transparent.

## 15. What Makes This Project Practical

The project handles real-world issues:

- Search providers rate-limit requests.
- Web pages have inconsistent HTML.
- Some pages do not contain useful product data.
- LLMs may return generic or empty results.
- Deployment needs correct port handling.
- Secrets must not be committed.

The final app includes practical fixes for these problems:

- Multiple search fallbacks
- Page-quality filtering
- Product-name validation
- Lightweight ranking
- Docker deployment
- Safe `.dockerignore`
- Railway variable handling

## 16. Ranking Logic

The ranking is intentionally lightweight.

For ML-related laptop queries, it gives preference to:

- dedicated NVIDIA/RTX GPUs
- stronger CPU class
- 16GB+ RAM
- larger SSD
- price within budget
- lower weight when the query asks for lightweight/portable

This is not a full scoring engine, but it improves recommendations compared to raw search order.

## 17. Known Limitations

The app is solid for a portfolio/demo, but it is not a production shopping engine.

Known limitations:

- Search results can still vary by provider availability.
- Some websites block automated browsing.
- LLM extraction may miss details if pages are sparse or heavily scripted.
- Prices can become outdated.
- Citations are source links, not sentence-level citations.
- No persistent user memory is implemented.
- No formal test suite is included yet.

## 18. Future Improvements

Good future upgrades:

- Add sentence-level citations in summaries.
- Track LLM calls and estimated cost.
- Add product deduplication across multiple pages.
- Add persistent user preferences with ChromaDB or a simpler database.
- Add a test suite for extraction and ranking.
- Add screenshots or a short GIF to the README.
- Improve frontend responsiveness and loading states.

## 19. Interview Talking Points

If asked, explain the project like this:

> I built an autonomous research agent that takes a natural-language product query and performs a multi-step workflow: it searches the web, visits pages with Playwright, extracts text with BeautifulSoup, uses an LLM for structured extraction, ranks the products with a lightweight heuristic, and generates a recommendation summary. I used LangGraph to model the pipeline as separate nodes so each step is isolated and extensible.

Strong points to mention:

- Used LangGraph instead of one giant function.
- Used Playwright for dynamic web pages.
- Used BeautifulSoup before the LLM to reduce noise.
- Added search fallback providers after DuckDuckGo rate-limited.
- Added validation to reject `Unknown Product` style hallucinations.
- Added ranking for ML-specific laptop recommendations.
- Dockerized and deployed to Railway.
- Kept secrets out of GitHub and Docker images.

## 20. Common Debugging Notes

### Search fails

Possible cause:

- DDG/Brave/Startpage rate limit
- Network issue

What to check:

- Server logs
- `browser: failed (...)` step
- Whether fallback providers are returning results

### No products extracted

Possible cause:

- Pages are low quality
- Website blocks browser
- Page is mostly JavaScript
- LLM extracted no concrete product name

What to check:

- `steps_completed`
- Source URLs
- `/extract` endpoint for one URL

### Railway says `$PORT` is invalid

Fix `railway.toml`:

```toml
startCommand = "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```

### Groq call fails

Possible cause:

- Missing `GROQ_API_KEY`
- Invalid key
- Rate limit
- Model unavailable

Check:

- Railway Variables
- local `.env`
- server logs

## 21. Final Project Status

The project is complete at a strong demo/portfolio level.

Completed:

- backend API
- agent pipeline
- browser automation
- search fallback system
- LLM extraction
- recommendation summary
- ranking heuristic
- frontend UI
- Docker setup
- Railway deployment
- safe GitHub upload flow

Not required for current completion:

- memory
- cost tracking
- sentence-level citations
- test suite
- GIF/screenshots

This is a good stopping point.

