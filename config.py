"""
Central configuration module for RAG Source Monitor.
Loads environment variables, defines source sites, and validates configuration.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Source websites configuration
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
        ],
        "expected_selectors": ["div.body", "div[role='main']"],
        "staleness_days": 365,
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
        ],
        "expected_selectors": ["article", "main"],
        "staleness_days": 180,
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
        ],
        "expected_selectors": ["div#mw-content-text"],
        "staleness_days": 365,
    }
}

# LLM Backend Configuration
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")  # "openai" or "ollama"

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BRIGHT_DATA_API_KEY = os.getenv("BRIGHT_DATA_API_KEY")

# Ollama Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ALERT_RECIPIENT = os.getenv("ALERT_RECIPIENT")

# Storage Paths
CHROMADB_PATH = os.getenv("CHROMADB_PATH", "./data/chromadb")
MONITOR_DB_PATH = os.getenv("MONITOR_DB_PATH", "./data/monitor_state.db")

# Monitoring Configuration
MONITOR_SCHEDULE_HOURS = int(os.getenv("MONITOR_SCHEDULE_HOURS", "6"))

# Ensure data directories exist
Path(CHROMADB_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(MONITOR_DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def validate_config():
    """
    Validate that all required configuration variables are set.
    Raises ValueError with clear error message if any required variable is missing.
    """
    required_vars = {
        "BRIGHT_DATA_API_KEY": BRIGHT_DATA_API_KEY,
        "SMTP_USER": SMTP_USER,
        "SMTP_PASSWORD": SMTP_PASSWORD,
        "ALERT_RECIPIENT": ALERT_RECIPIENT,
    }

    # OpenAI key only required if using OpenAI backend
    if LLM_BACKEND == "openai":
        required_vars["OPENAI_API_KEY"] = OPENAI_API_KEY

    missing_vars = [var_name for var_name, var_value in required_vars.items() if not var_value]

    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            f"Please create a .env file based on .env.example and fill in all required values."
        )


# Validate configuration on module import
validate_config()

# Export logger
logger = logging.getLogger(__name__)
logger.info("Configuration loaded successfully")
