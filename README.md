# RAG Source Monitor

A production-ready Retrieval-Augmented Generation (RAG) system with automated source quality monitoring. The system ingests content from public documentation sites (Python Docs, MDN, Wikipedia), provides conversational Q&A via a Streamlit interface, and continuously monitors source data quality using configurable health checks with email alerting.

---

## Features

- 🤖 **RAG Q&A System**: Conversational interface powered by Ollama (llama3.1) or OpenAI with streaming responses
- 🔍 **Source Quality Monitoring**: 6 types of automated checks (link breaks, content changes, paywall detection, availability, structure shifts, staleness)
- 📊 **Health Dashboard**: Real-time visualization of source health with color-coded indicators
- 📧 **Email Alerts**: SMTP-based alert digest with deduplication (24h window)
- ⏰ **Flexible Scheduling**: On-demand checks or automated periodic monitoring via APScheduler
- 💾 **Persistent Storage**: ChromaDB for vector embeddings, SQLite for monitoring state
- 📈 **Analytics**: Check history with filtering, CSV export, and trend visualization

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Web UI                         │
│  ┌──────────────────┐        ┌──────────────────────┐      │
│  │   Chat Page      │        │  Health Dashboard    │      │
│  │  (RAG Q&A)       │        │  (Monitoring)        │      │
│  └──────────────────┘        └──────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                    │                          │
        ┌───────────┴──────────┐   ┌──────────┴──────────┐
        │   RAG Engine         │   │   Monitor Engine    │
        │                      │   │                     │
        │  - Query embedding   │   │  - 6 check types   │
        │  - Vector retrieval  │   │  - Alert engine    │
        │  - Answer generation │   │  - Scheduler       │
        └──────────────────────┘   └─────────────────────┘
                    │                          │
        ┌───────────┴──────────┐   ┌──────────┴──────────┐
        │   ChromaDB           │   │   SQLite            │
        │  (Vector Store)      │   │  (Monitoring State) │
        │                      │   │                     │
        │  - 694 chunks        │   │  - Check history    │
        │  - nomic-embed-text  │   │  - Alerts           │
        └──────────────────────┘   └─────────────────────┘
                    │                          │
        ┌───────────┴──────────┐   ┌──────────┴──────────┐
        │   Ingestion          │   │   Monitoring Checks │
        │                      │   │                     │
        │  - Web scraping      │   │  - Link validation  │
        │  - Text chunking     │   │  - Content diffing  │
        │  - Embedding         │   │  - SERP API         │
        └──────────────────────┘   └─────────────────────┘
```

### Data Flow

1. **Ingestion**: Scrape → Chunk → Embed → Store in ChromaDB
2. **RAG Query**: User question → Embed → Retrieve context → Generate answer
3. **Monitoring**: Check sources → Create alerts → Send email digest

---

## Setup

### Prerequisites

- **Python 3.10+**
- **Ollama** (for local LLM) - [Install Ollama](https://ollama.ai)
  ```bash
  # Start Ollama and pull required models
  ollama serve
  ollama pull llama3.1
  ollama pull nomic-embed-text
  ```
- **Gmail App Password** (for email alerts) - [Create App Password](https://support.google.com/accounts/answer/185833)
- **Bright Data API Key** (for SERP checks) - [Get API Key](https://brightdata.com)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd RAG_data_quality_monitor
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

   Required variables:
   ```env
   # LLM Backend
   LLM_BACKEND=ollama                    # "ollama" or "openai"

   # Ollama Configuration (if using Ollama)
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_EMBEDDING_MODEL=nomic-embed-text
   OLLAMA_CHAT_MODEL=llama3.1

   # OpenAI (if using OpenAI backend)
   OPENAI_API_KEY=sk-...

   # Monitoring
   BRIGHT_DATA_API_KEY=your_api_key_here

   # Email Alerts (use Gmail App Password, not account password)
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=your_app_password_here
   ALERT_RECIPIENT=recipient@example.com

   # Optional
   MONITOR_SCHEDULE_HOURS=6              # Default: 6 hours
   ```

5. **Run initial ingestion** (optional - can also do from UI)
   ```bash
   python -m ingestion.embedder
   ```

---

## Running the Application

### Quick Start

**Option 1: Using the startup script (recommended)**
```bash
./start_app.sh
```

This will:
- Activate virtual environment
- Verify Ollama is running
- Check database connections
- Start Streamlit app

**Option 2: Manual start**
```bash
source venv/bin/activate
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

### Usage

#### 💬 Chat Page
1. Ask questions about Python, JavaScript, Machine Learning, or Web technologies
2. Answers stream in real-time with source citations
3. Click "📚 Sources" to see document references
4. Use "🗑️ Clear Chat" to reset conversation

**Sample Questions:**
- "What is Python used for?"
- "Explain JavaScript arrow functions"
- "How does machine learning work?"
- "What are Python's built-in types?"

#### 📊 Health Dashboard
1. **View Metrics**: Monitor total sources, active alerts, warnings, and critical issues
2. **Source Health**: Check real-time status (🟢 Healthy, 🟡 Warning, 🔴 Error)
3. **Resolve Alerts**: Click "✅ Resolve" to acknowledge and dismiss alerts
4. **Run Checks**: Use "🔄 Run Checks Now" for on-demand monitoring
5. **Scheduler**: Start/stop automated periodic checks
6. **History**: View and filter check history, export to CSV

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_BACKEND` | No | `ollama` | LLM backend: "ollama" or "openai" |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_EMBEDDING_MODEL` | No | `nomic-embed-text` | Ollama embedding model |
| `OLLAMA_CHAT_MODEL` | No | `llama3.1` | Ollama chat model |
| `OPENAI_API_KEY` | If OpenAI | - | OpenAI API key (required if LLM_BACKEND=openai) |
| `BRIGHT_DATA_API_KEY` | Yes | - | Bright Data API key for SERP checks |
| `SMTP_HOST` | Yes | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP server port |
| `SMTP_USER` | Yes | - | SMTP username (email address) |
| `SMTP_PASSWORD` | Yes | - | SMTP password (Gmail App Password) |
| `ALERT_RECIPIENT` | Yes | - | Email address to receive alerts |
| `CHROMADB_PATH` | No | `./data/chromadb` | ChromaDB storage path |
| `MONITOR_DB_PATH` | No | `./data/monitor_state.db` | SQLite database path |
| `MONITOR_SCHEDULE_HOURS` | No | `6` | Monitoring check interval (hours) |

### Source Configuration

Sources are configured in `config.py`:

```python
SOURCE_SITES = {
    "python_docs": {
        "name": "Python Documentation",
        "base_url": "https://docs.python.org/3/",
        "pages": ["library/functions.html", ...],
        "expected_selectors": ["div.body", "div[role='main']"],
        "staleness_days": 365,
    },
    # ... more sources
}
```

**Adding a New Source:**
1. Add entry to `SOURCE_SITES` dict in `config.py`
2. Specify pages, selectors, and staleness threshold
3. Run re-ingestion from UI sidebar

---

## Monitoring

### How It Works

The monitoring system performs **6 types of checks** on each source page:

| Check Type | Status | Description |
|------------|--------|-------------|
| **Link Break** | Error | Detects 404s, timeouts, DNS failures |
| **Link Redirect** | Warning | Detects URL moves (301/302 redirects) |
| **Content Change** | Warning | Detects content modifications via SHA-256 hash |
| **Paywall** | Warning | Detects subscription prompts, short content |
| **Availability** | Error | Basic uptime check (HTTP 200) |
| **Structure Shift** | Warning | Detects HTML structure changes (missing CSS selectors) |
| **Staleness** | Warning | Checks Last-Modified header vs threshold |

### Alert System

**Severity Levels:**
- 🔴 **Critical**: Broken links, site down, access denied (401/403)
- ⚠️ **Warning**: Redirects, content changes, paywall detected, stale content

**Deduplication**: Alerts are deduplicated within a 24-hour window to prevent spam.

**Email Digest**: When new alerts are created, a digest email is sent with:
- Summary counts (critical vs warnings)
- Grouped alerts by severity
- Source details and clickable URLs

### Running Checks

**On-Demand:**
1. Navigate to Health Dashboard
2. Click "🔄 Run Checks Now"
3. Optionally enable "Deep Diff" for detailed content comparison
4. Wait 30-60 seconds for results

**Scheduled (Automated):**
1. Navigate to Health Dashboard
2. Click "▶️ Start Scheduler"
3. Checks run every N hours (default: 6, configured via `MONITOR_SCHEDULE_HOURS`)
4. Click "⏸️ Stop Scheduler" to disable

**Via Command Line:**
```bash
python -m monitor.scheduler
```

---

## Testing

### Run Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest

# Run specific test file
pytest tests/test_ingestion.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Test Coverage

- **test_ingestion.py**: Scraper, chunker, embedder
  - Retry logic, timeout handling, 404 responses
  - Chunk size and overlap validation
  - Deterministic doc ID generation

- **test_rag.py**: Query engine, context formatting
  - Prompt building with source citations
  - Empty collection handling
  - Source deduplication

- **test_monitor.py**: Monitoring checks, alerts, diffing
  - All 6 check types return valid CheckResult
  - Alert deduplication (24h window)
  - Hash comparison detects changes
  - Deep diff calculates change percentage

---

## Project Structure

```
.
├── app.py                    # Streamlit application (Chat + Dashboard)
├── config.py                 # Central configuration
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not in git)
├── .env.example              # Template for .env
├── start_app.sh              # Startup script with diagnostics
├── RUN_APP.md                # Detailed usage guide
├── SPEC.md                   # Full technical specification
├── SECURITY_AUDIT.md         # Security review report
│
├── ingestion/                # Data ingestion pipeline
│   ├── scraper.py            # Web scraping with retry logic
│   ├── chunker.py            # Text chunking with overlap
│   └── embedder.py           # Embedding generation (Ollama/OpenAI)
│
├── rag/                      # RAG query engine
│   └── engine.py             # Query, retrieval, answer generation
│
├── monitor/                  # Monitoring system
│   ├── checks.py             # 6 check types implementation
│   ├── differ.py             # Content comparison (light/deep)
│   ├── alerts.py             # Alert generation & email sending
│   ├── scheduler.py          # APScheduler integration
│   └── db.py                 # SQLite database operations
│
├── tests/                    # Test suite
│   ├── test_ingestion.py     # Ingestion tests
│   ├── test_rag.py           # RAG tests
│   └── test_monitor.py       # Monitoring tests
│
└── data/                     # Data storage (not in git)
    ├── chromadb/             # Vector database
    └── monitor_state.db      # Monitoring database
```

---

## Troubleshooting

### Ollama Not Running
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Verify models are available
ollama list  # Should show llama3.1 and nomic-embed-text
```

### Knowledge Base Empty
1. Click "🔄 Re-ingest Sources" in the sidebar
2. Wait 3-5 minutes for ingestion to complete
3. Refresh the page

### SMTP Authentication Fails
- Use Gmail **App Password**, not your account password
- Enable 2-factor authentication on your Google account first
- Generate App Password at: https://myaccount.google.com/apppasswords

### Port Already in Use
```bash
# Kill process using port 8501
lsof -ti:8501 | xargs kill -9

# Or use different port
streamlit run app.py --server.port 8502
```

### Tests Failing
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Install test dependencies
pip install pytest

# Run tests with verbose output
pytest -v
```

---

## Security

See [SECURITY_AUDIT.md](SECURITY_AUDIT.md) for detailed security review.

**Key Security Features:**
- ✅ All SQL queries use parameterized statements (no SQL injection)
- ✅ All HTTP requests have explicit timeouts
- ✅ Environment variables protected in `.env` (gitignored)
- ✅ API keys validated on startup with clear error messages
- ✅ No use of `eval()` or `exec()`
- ✅ SMTP uses TLS encryption (STARTTLS)
- ✅ Proper error handling and logging throughout

---

## Development

### Adding a New Source

1. **Update `config.py`**:
   ```python
   SOURCE_SITES["new_source"] = {
       "name": "New Source Name",
       "base_url": "https://example.com/",
       "pages": ["page1.html", "page2.html"],
       "expected_selectors": ["main", "article"],
       "staleness_days": 180,
   }
   ```

2. **Re-run ingestion** from UI or CLI:
   ```bash
   python -m ingestion.embedder
   ```

3. **Monitor the new source** on the Health Dashboard

### Switching from Ollama to OpenAI

1. **Update `.env`**:
   ```env
   LLM_BACKEND=openai
   OPENAI_API_KEY=sk-...
   ```

2. **Restart the application**

### Customizing Check Intervals

Edit `.env`:
```env
MONITOR_SCHEDULE_HOURS=12  # Check every 12 hours
```

---

## License

MIT License - See LICENSE file for details

---

## Support

For issues, questions, or contributions, please refer to:
- **Documentation**: See `SPEC.md` for full technical specification
- **Usage Guide**: See `RUN_APP.md` for detailed usage instructions
- **Security**: See `SECURITY_AUDIT.md` for security review

---

**Built with:**
- [Streamlit](https://streamlit.io/) - Web UI framework
- [ChromaDB](https://www.trychroma.com/) - Vector database
- [Ollama](https://ollama.ai/) - Local LLM inference
- [APScheduler](https://apscheduler.readthedocs.io/) - Task scheduling
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
