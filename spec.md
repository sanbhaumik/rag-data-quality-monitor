# RAG System with Source Data Quality Monitor — Project Specification

## Project Overview

Build a RAG (Retrieval-Augmented Generation) system that ingests content from 3 public websites, stores embeddings in ChromaDB, and provides a conversational Q&A interface. A Source Data Quality Monitor continuously validates source integrity using Bright Data SERP APIs and surfaces issues via email alerts and a Streamlit health dashboard.

**Tech Stack:** Python 3.11+, ChromaDB, OpenAI API (embeddings + chat), Bright Data SERP API, Streamlit, SMTP email.

**Design Principles:** Simple, secure, lean (no redundant code), proper error handling throughout.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit App                         │
│  ┌──────────────┐  ┌─────────────────────────────────┐  │
│  │  Chat UI     │  │  Health Dashboard                │  │
│  │  (RAG Q&A)   │  │  (Source status, alerts, trends) │  │
│  └──────┬───────┘  └──────────────┬──────────────────┘  │
└─────────┼──────────────────────────┼────────────────────┘
          │                          │
          ▼                          ▼
┌──────────────────┐    ┌──────────────────────────────┐
│  RAG Engine      │    │  Source Quality Monitor       │
│  - Query embed   │    │  - Scheduler (APScheduler)    │
│  - ChromaDB      │    │  - Bright Data SERP checks    │
│  - OpenAI chat   │    │  - Content hash/diff engine   │
│  - Source cite    │    │  - Alert engine (SMTP)        │
└────────┬─────────┘    └──────────────┬───────────────┘
         │                             │
         ▼                             ▼
┌──────────────────┐    ┌──────────────────────────────┐
│  ChromaDB        │    │  SQLite (monitor_state.db)   │
│  (vector store)  │    │  - check history              │
│                  │    │  - content hashes             │
│                  │    │  - alerts log                 │
└──────────────────┘    └──────────────────────────────┘
```

---

## Directory Structure

```
rag-source-monitor/
├── .env.example              # Template for secrets
├── .gitignore
├── requirements.txt
├── README.md
├── config.py                 # Central config (loads .env, source URLs, schedules)
├── app.py                    # Streamlit app entry point (chat + dashboard)
├── ingestion/
│   ├── __init__.py
│   ├── scraper.py            # Web scraping for 3 source sites
│   ├── chunker.py            # Text chunking logic
│   └── embedder.py           # OpenAI embedding + ChromaDB storage
├── rag/
│   ├── __init__.py
│   └── engine.py             # Query processing, retrieval, response generation
├── monitor/
│   ├── __init__.py
│   ├── checks.py             # All 6 check types using Bright Data SERP API
│   ├── differ.py             # Content hash (light) + semantic diff (deep)
│   ├── scheduler.py          # APScheduler wrapper
│   ├── alerts.py             # SMTP email alerts
│   └── db.py                 # SQLite state persistence
└── tests/
    ├── test_ingestion.py
    ├── test_rag.py
    └── test_monitor.py
```

---

## Environment Variables (.env)

```
OPENAI_API_KEY=sk-...
BRIGHT_DATA_API_KEY=...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_RECIPIENT=alerts@yourdomain.com
CHROMADB_PATH=./data/chromadb
MONITOR_DB_PATH=./data/monitor_state.db
MONITOR_SCHEDULE_HOURS=6
```

---

## Chunk 1: Project Setup & Configuration

**File:** `config.py`, `.env.example`, `requirements.txt`, `.gitignore`

### `config.py`
- Load all env vars using `python-dotenv`
- Define a `SOURCE_SITES` dict:
  ```python
  SOURCE_SITES = {
      "python_docs": {
          "name": "Python Documentation",
          "base_url": "https://docs.python.org/3/",
          "pages": [
              "tutorial/index.html",
              "library/functions.html",
              "library/stdtypes.html",
              "library/os.html",
              "library/json.html",
          ]
      },
      "mdn": {
          "name": "MDN Web Docs",
          "base_url": "https://developer.mozilla.org/en-US/docs/",
          "pages": [
              "Web/JavaScript/Guide",
              "Web/HTML/Reference",
              "Web/CSS/Reference",
              "Web/API/Fetch_API",
              "Learn/JavaScript/First_steps",
          ]
      },
      "wikipedia": {
          "name": "Wikipedia",
          "base_url": "https://en.wikipedia.org/wiki/",
          "pages": [
              "Python_(programming_language)",
              "JavaScript",
              "Machine_learning",
              "Artificial_intelligence",
              "World_Wide_Web",
          ]
      }
  }
  ```
- Expose typed config: `OPENAI_API_KEY`, `BRIGHT_DATA_API_KEY`, `SMTP_*`, `CHROMADB_PATH`, `MONITOR_DB_PATH`, `MONITOR_SCHEDULE_HOURS`
- Validate required vars on import — raise clear error if missing

### `requirements.txt`
```
chromadb>=0.4.0
openai>=1.0.0
streamlit>=1.30.0
python-dotenv>=1.0.0
requests>=2.31.0
beautifulsoup4>=4.12.0
apscheduler>=3.10.0
```

### `.gitignore`
Ignore: `.env`, `data/`, `__pycache__/`, `*.pyc`, `.streamlit/`

---

## Chunk 2: Web Scraper

**File:** `ingestion/scraper.py`

### Responsibilities
- Fetch and parse HTML content from the 3 source sites
- Extract clean text (strip nav, footer, sidebar, scripts, styles)
- Return structured data: `{ url, title, content, fetched_at }`

### Implementation Details
- Use `requests` with timeout (10s), retries (3 with exponential backoff), and `User-Agent` header
- Use `BeautifulSoup` to parse HTML and extract main content:
  - Python docs: target `<div class="body">` or `<div role="main">`
  - MDN: target `<article>` or `<main>`
  - Wikipedia: target `<div id="mw-content-text">`
- Strip all `<script>`, `<style>`, `<nav>`, `<footer>` tags before text extraction
- Return `list[dict]` with keys: `url`, `title`, `text`, `fetched_at` (ISO timestamp)
- Function signature: `scrape_all_sources(source_sites: dict) -> list[dict]`
- Also expose: `scrape_single_page(url: str) -> dict | None` for monitor reuse
- Log progress with `logging` module — no print statements

### Error Handling
- Catch `requests.RequestException`, log warning, skip page, continue to next
- Return partial results (don't fail entire job if 1 page fails)

---

## Chunk 3: Text Chunker

**File:** `ingestion/chunker.py`

### Responsibilities
- Split scraped text into overlapping chunks suitable for embedding

### Implementation Details
- Chunk size: 500 tokens (approx 2000 chars), overlap: 100 tokens (approx 400 chars)
- Split on paragraph boundaries first (`\n\n`), then sentence boundaries (`. `), then hard split
- Each chunk carries metadata: `{ source_url, source_name, chunk_index, title }`
- Function signature: `chunk_documents(documents: list[dict], chunk_size=2000, overlap=400) -> list[dict]`
  - Returns `list[dict]` with keys: `text`, `metadata`

---

## Chunk 4: Embedding & ChromaDB Storage

**File:** `ingestion/embedder.py`

### Responsibilities
- Generate OpenAI embeddings for text chunks
- Store/update embeddings in ChromaDB
- Handle first-run ingestion and re-ingestion

### Implementation Details
- Use `openai.OpenAI()` client, model `text-embedding-3-small`
- Batch embedding calls: max 100 texts per API call
- ChromaDB collection name: `"rag_sources"`
- Document IDs: deterministic hash of `source_url + chunk_index` (so re-ingestion is idempotent)
- Function signatures:
  - `embed_texts(texts: list[str]) -> list[list[float]]` — batch embed with OpenAI
  - `store_embeddings(chunks: list[dict]) -> int` — store in ChromaDB, return count stored
  - `run_ingestion(source_sites: dict) -> int` — orchestrate full pipeline: scrape → chunk → embed → store
  - `is_collection_empty() -> bool` — check if first run needed
- On app startup: call `run_ingestion()` if collection is empty

### Error Handling
- Retry OpenAI API calls on rate limit (wait + retry, max 3 attempts)
- Log embedding counts and any failures

---

## Chunk 5: RAG Query Engine

**File:** `rag/engine.py`

### Responsibilities
- Accept user query, retrieve relevant chunks from ChromaDB, generate answer with OpenAI

### Implementation Details
- Query flow:
  1. Embed user query with `text-embedding-3-small`
  2. Query ChromaDB: `collection.query(query_embeddings, n_results=5)`
  3. Build prompt with retrieved context + user question
  4. Call OpenAI `gpt-4o-mini` for answer generation
- System prompt template:
  ```
  You are a helpful assistant. Answer the user's question based ONLY on the provided context.
  If the context doesn't contain enough information, say so clearly.
  Always cite which source(s) you used.

  Context:
  {context_chunks}
  ```
- Each context chunk should include its source URL and title for citation
- Function signature: `query(user_question: str) -> dict` returning `{ answer, sources: list[{url, title}] }`
- Stream support: also expose `query_stream(user_question: str)` using OpenAI streaming for Streamlit

### Error Handling
- Handle empty ChromaDB (prompt user to run ingestion)
- Handle OpenAI API errors with user-friendly messages
- Timeout: 30s for OpenAI chat completion

---

## Chunk 6: Monitor Database (SQLite)

**File:** `monitor/db.py`

### Responsibilities
- Persist monitoring state: check history, content hashes, alert logs

### Schema
```sql
CREATE TABLE IF NOT EXISTS check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,       -- e.g. "python_docs"
    url TEXT NOT NULL,
    check_type TEXT NOT NULL,       -- "link", "content", "paywall", "availability", "structure", "staleness"
    status TEXT NOT NULL,           -- "ok", "warning", "error"
    detail TEXT,                    -- Human-readable description
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    content_hash TEXT NOT NULL,     -- SHA-256 of page content
    content_text TEXT,              -- Full text (for deep diff, nullable)
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    url TEXT NOT NULL,
    check_type TEXT NOT NULL,
    severity TEXT NOT NULL,         -- "warning", "critical"
    message TEXT NOT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
```

### Implementation Details
- Use `sqlite3` stdlib — no ORM
- Provide a context-manager `get_db()` that handles connection/close
- Helper functions:
  - `save_check_result(source_key, url, check_type, status, detail)`
  - `save_content_snapshot(url, content_hash, content_text=None)`
  - `get_latest_snapshot(url) -> dict | None`
  - `save_alert(source_key, url, check_type, severity, message) -> int`
  - `mark_alert_emailed(alert_id)`
  - `get_active_alerts() -> list[dict]`
  - `get_check_history(source_key=None, limit=100) -> list[dict]`
  - `get_alert_summary() -> dict` — counts by severity/status for dashboard
- Auto-create tables on first `get_db()` call

---

## Chunk 7: Bright Data SERP Checks

**File:** `monitor/checks.py`

### Responsibilities
- Implement all 6 source quality check types using Bright Data SERP API + direct HTTP checks

### Check Types & Implementation

**1. Link Break Detection**
- Use `requests.head(url, allow_redirects=True, timeout=10)`
- Check: HTTP status (404, 410 = broken), redirect chains (>2 redirects = warning), final URL differs from original = moved
- Bright Data SERP: search for page title, verify URL still ranks (if not, content may have moved)

**2. Content Change Detection**
- Fetch page content, compute SHA-256 hash
- Compare to last stored hash in `content_snapshots`
- Light mode (default): hash mismatch = "changed" flag
- Deep mode (optional): if hashes differ, use `difflib.unified_diff` on stored text vs new text, report % changed
- Store new snapshot on every check

**3. Paywall Detection**
- Fetch page with and without cookies/auth headers
- Check for common paywall indicators in HTML: `paywall`, `subscribe`, `premium`, `login-required`, `access-denied` in class names or meta tags
- Check if content length is suspiciously short compared to last snapshot (>50% reduction = possible paywall)
- Check HTTP 401/403 status codes

**4. Availability Check**
- Simple: HTTP GET with 10s timeout
- Check status code: 200 = ok, 5xx = server error, timeout = offline
- Bright Data SERP: search `site:{domain}` — if no results, site may be deindexed

**5. Structure Shift Detection**
- Fetch page, check for expected CSS selectors (from `config.SOURCE_SITES` — add `expected_selectors` field):
  - Python docs: `div.body`, `div[role="main"]`
  - MDN: `article`, `main`
  - Wikipedia: `div#mw-content-text`
- If expected selector not found, structure has shifted
- Also compare DOM depth / tag distribution as heuristic

**6. Staleness Check**
- Use Bright Data SERP API: search for page URL, check `date` field in SERP results
- Check for `<meta>` last-modified or `Last-Modified` HTTP header
- Flag if last update > 365 days ago (configurable threshold)

### Function Signatures
```python
def run_all_checks(source_sites: dict, deep_diff: bool = False) -> list[CheckResult]
def check_single_source(source_key: str, source_config: dict, deep_diff: bool = False) -> list[CheckResult]
```

`CheckResult` is a dataclass:
```python
@dataclass
class CheckResult:
    source_key: str
    url: str
    check_type: str      # "link", "content", "paywall", "availability", "structure", "staleness"
    status: str          # "ok", "warning", "error"
    detail: str          # Human-readable explanation
    checked_at: datetime
```

### Bright Data SERP API Usage
- Endpoint: `https://api.brightdata.com/serp/req`
- Auth: Bearer token from `BRIGHT_DATA_API_KEY`
- Use for: SERP position checks, date extraction, site indexing verification
- Rate limit: batch requests, max 1 request per source per check cycle
- Example request:
  ```python
  response = requests.post(
      "https://api.brightdata.com/serp/req",
      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
      json={"query": search_query, "search_engine": "google", "country": "us"},
      timeout=30
  )
  ```
- **IMPORTANT:** Verify the exact Bright Data SERP API endpoint and request format from their documentation before implementing. The above is illustrative — the actual API contract may differ. Add a note in code to check https://docs.brightdata.com/scraping-automation/serp-api/introduction

### Error Handling
- Each check is independent — one failure doesn't block others
- Catch all exceptions per check, log, and return status="error" with detail
- Bright Data API failures: log and fall back to direct HTTP checks only

---

## Chunk 8: Content Differ

**File:** `monitor/differ.py`

### Responsibilities
- Light check: SHA-256 hash comparison
- Deep diff: text comparison with change percentage and summary

### Implementation Details
```python
def compute_hash(text: str) -> str:
    """SHA-256 hash of normalized text (stripped whitespace, lowered)."""

def light_check(url: str, current_text: str) -> dict:
    """Compare hash to last snapshot. Returns {changed: bool, previous_hash, current_hash}."""

def deep_diff(url: str, current_text: str) -> dict:
    """Full text diff. Returns {changed: bool, pct_changed: float, diff_summary: str, added_lines: int, removed_lines: int}."""
```

- Normalize text before hashing: strip extra whitespace, lowercase
- For deep diff, use `difflib.SequenceMatcher` to compute similarity ratio
- `diff_summary`: first 500 chars of unified diff output (for display in dashboard/alerts)
- Store snapshots in DB via `monitor.db` functions

---

## Chunk 9: Alert Engine (SMTP)

**File:** `monitor/alerts.py`

### Responsibilities
- Evaluate check results and generate alerts for issues
- Send email notifications via SMTP
- Deduplicate alerts (don't re-alert for same issue within 24h)

### Implementation Details
```python
def process_check_results(results: list[CheckResult]) -> list[dict]:
    """Evaluate results, create alerts for warning/error status, deduplicate, return new alerts."""

def send_alert_email(alert: dict) -> bool:
    """Send single alert email via SMTP. Returns True on success."""

def send_digest_email(alerts: list[dict]) -> bool:
    """Send batch digest of all new alerts. Returns True on success."""
```

- Alert severity mapping:
  - `status="warning"` → severity "warning" (content changed, structure shifted, staleness)
  - `status="error"` → severity "critical" (link broken, site offline, paywall detected)
- Deduplication: before creating alert, check if same `(source_key, url, check_type)` alert exists in last 24h
- Email format: HTML email with source name, URL, issue type, detail, timestamp
- Use `smtplib.SMTP` with TLS (`starttls()`)
- Send digest (one email with all new alerts) rather than individual emails to avoid spam
- Save alert to DB, mark `email_sent=True` on successful send

### Error Handling
- SMTP failures: log error, save alert to DB with `email_sent=False` (dashboard still shows it)
- Never crash on email failure

---

## Chunk 10: Monitor Scheduler

**File:** `monitor/scheduler.py`

### Responsibilities
- Schedule periodic monitoring checks
- Support on-demand trigger from Streamlit UI

### Implementation Details
```python
def start_scheduler(interval_hours: int = None) -> BackgroundScheduler:
    """Start APScheduler with interval from config. Returns scheduler instance."""

def run_monitor_now(deep_diff: bool = False) -> list[dict]:
    """On-demand: run all checks, process alerts, send emails. Returns alerts."""

def stop_scheduler(scheduler: BackgroundScheduler):
    """Graceful shutdown."""
```

- Use `APScheduler.BackgroundScheduler` with `IntervalTrigger`
- Default interval from `MONITOR_SCHEDULE_HOURS` env var
- Job function: `run_all_checks()` → `process_check_results()` → `send_digest_email()`
- Store scheduler instance in Streamlit `session_state` to persist across reruns
- Thread-safe: scheduler runs in background thread, results written to SQLite

---

## Chunk 11: Streamlit App — Chat UI Page

**File:** `app.py` (page 1 of 2-page Streamlit app)

### Responsibilities
- Conversational RAG Q&A interface
- Trigger ingestion if needed

### Implementation Details
- Use `st.set_page_config(page_title="RAG Source Monitor", layout="wide")`
- Sidebar navigation: "Chat" | "Health Dashboard"
- **Chat Page:**
  - On first load: check `is_collection_empty()`. If true, show info message + "Run Ingestion" button
  - Standard Streamlit chat pattern:
    ```python
    if prompt := st.chat_input("Ask a question..."):
        # Display user message
        # Call rag.engine.query_stream()
        # Display streamed response
        # Show source citations as expandable section
    ```
  - Store chat history in `st.session_state.messages`
  - Show source citations below each answer as clickable links
  - "Re-ingest Sources" button in sidebar (runs `run_ingestion()` with spinner)

### UI Guidelines
- Clean, minimal — no unnecessary widgets
- Use `st.spinner()` for long operations
- Use `st.error()` / `st.warning()` / `st.success()` for status feedback

---

## Chunk 12: Streamlit App — Health Dashboard Page

**File:** `app.py` (page 2 — same file, switched via sidebar)

### Responsibilities
- Display source health status, active alerts, check history, and trends

### Dashboard Layout

**Top Row — Overall Health Summary:**
- 3 metric columns (one per source): colored status indicator (🟢/🟡/🔴), source name, last check time
- Overall health score: % of checks passing

**Middle Row — Active Alerts:**
- `st.dataframe()` of active alerts: timestamp, source, check type, severity, message
- Color-code rows by severity (warning=yellow, critical=red)
- "Resolve" button per alert (sets `resolved_at`)

**Bottom Row — Controls & History:**
- "Run Check Now" button → calls `run_monitor_now()`, refreshes dashboard
- Toggle: "Enable Deep Diff" checkbox
- Dropdown: select source to filter history
- `st.dataframe()` of recent check history (last 50 checks)

**Sidebar (shared):**
- Navigation: Chat | Dashboard
- Scheduler status: running/stopped, next run time
- "Start/Stop Scheduler" toggle
- Last check timestamp

### Implementation Details
- Pull all data from SQLite via `monitor.db` functions
- Auto-refresh: use `st.rerun()` after running checks or resolving alerts
- No polling — manual refresh only (keeps it simple)

---

## Chunk 13: Configuration for Source Selectors

**Update to:** `config.py`

Add `expected_selectors` to each source in `SOURCE_SITES` for structure shift detection:

```python
SOURCE_SITES = {
    "python_docs": {
        "name": "Python Documentation",
        "base_url": "https://docs.python.org/3/",
        "pages": [...],
        "expected_selectors": ["div.body", "div[role='main']"],
        "staleness_days": 365,
    },
    "mdn": {
        "name": "MDN Web Docs",
        "base_url": "https://developer.mozilla.org/en-US/docs/",
        "pages": [...],
        "expected_selectors": ["article", "main"],
        "staleness_days": 180,
    },
    "wikipedia": {
        "name": "Wikipedia",
        "base_url": "https://en.wikipedia.org/wiki/",
        "pages": [...],
        "expected_selectors": ["div#mw-content-text"],
        "staleness_days": 365,
    }
}
```

---

## Chunk 14: Security & Error Handling Standards

### Security
- **All secrets in `.env`** — never hardcoded, never committed
- **`.env` in `.gitignore`** — enforced
- **API keys:** validated on startup, clear error messages if missing
- **SMTP password:** use Gmail App Password (not account password)
- **No user input in SQL:** all SQLite queries use parameterized statements (`?` placeholders)
- **Request timeouts:** all HTTP requests have explicit timeouts (10-30s)
- **No `eval()` or `exec()`** anywhere

### Error Handling Patterns
```python
# Pattern 1: HTTP requests — always wrap, always timeout
try:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
except requests.RequestException as e:
    logger.warning(f"Failed to fetch {url}: {e}")
    return None

# Pattern 2: OpenAI API — retry on rate limit
for attempt in range(3):
    try:
        response = client.embeddings.create(...)
        break
    except openai.RateLimitError:
        time.sleep(2 ** attempt)
    except openai.APIError as e:
        logger.error(f"OpenAI API error: {e}")
        raise

# Pattern 3: SQLite — context manager
with get_db() as conn:
    conn.execute("INSERT INTO ... VALUES (?, ?, ?)", (a, b, c))
```

### Logging
- Use Python `logging` module — no `print()` statements
- Log level: `INFO` for normal operations, `WARNING` for recoverable issues, `ERROR` for failures
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Configure in `config.py`

---

## Chunk 15: Testing & README

### Tests (`tests/`)

Lightweight tests using `pytest`. Focus on critical paths:

**`test_ingestion.py`:**
- Test chunker produces correct chunk sizes and overlap
- Test embedder generates deterministic doc IDs
- Test scraper handles 404 gracefully (mock requests)

**`test_rag.py`:**
- Test query engine formats context prompt correctly
- Test empty collection returns helpful message

**`test_monitor.py`:**
- Test each check type returns valid `CheckResult`
- Test alert deduplication (same issue within 24h → no new alert)
- Test hash comparison (light check) detects changes
- Test deep diff calculates correct change percentage

Use `unittest.mock` to mock external APIs (OpenAI, Bright Data, HTTP requests).

### `README.md`

Structure:
1. **Project overview** — one paragraph
2. **Setup** — clone, create `.env` from `.env.example`, `pip install -r requirements.txt`
3. **Run** — `streamlit run app.py`
4. **Architecture** — link to this spec or brief diagram
5. **Configuration** — table of env vars with descriptions
6. **Monitoring** — how checks work, how to trigger on-demand, how alerts work

---

## Build Order (Recommended)

Execute chunks in this order for incremental, testable progress:

| Step | Chunks | Milestone |
|------|--------|-----------|
| 1 | Chunk 1 | Project scaffolding, config loads, deps install |
| 2 | Chunks 2-3 | Scraper + chunker work, can see raw content |
| 3 | Chunk 4 | Embeddings stored in ChromaDB |
| 4 | Chunk 5 | RAG query works end-to-end (CLI test) |
| 5 | Chunk 11 | Streamlit chat UI functional |
| 6 | Chunk 6 | Monitor DB schema created |
| 7 | Chunks 7-8 | All checks implemented |
| 8 | Chunk 9-10 | Alerts + scheduler working |
| 9 | Chunks 12-13 | Health dashboard complete |
| 10 | Chunks 14-15 | Security hardened, tests pass, README done |