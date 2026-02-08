# Running the RAG Source Monitor Streamlit App

## Quick Start

### Option 1: Use the Startup Script (Recommended)
```bash
./start_app.sh
```

This script will:
- Activate the virtual environment
- Check Ollama is running
- Verify ChromaDB connection
- Verify Monitor DB connection
- Start Streamlit app

### Option 2: Manual Start
```bash
source venv/bin/activate
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## Features

### 💬 Chat Page
- **RAG Q&A Interface**: Ask questions about Python, JavaScript, Machine Learning, AI, and Web technologies
- **Streaming Responses**: Real-time answer generation using Ollama
- **Source Citations**: Every answer includes clickable source links
- **Chat History**: Maintains conversation context
- **Re-ingestion**: Refresh the knowledge base from the sidebar

### 📊 Health Dashboard
- **Overall Health Metrics**: Total sources, active alerts, warnings, critical issues
- **Source Health Status**: Real-time status indicators (🟢/🟡/🔴) for each source
- **Active Alerts**: View and resolve alerts with one click
- **Monitoring Controls**:
  - Run on-demand checks with optional deep diff
  - Start/stop scheduler for automated periodic checks
  - Real-time scheduler status display
- **Check History**: Filterable history with color-coded status
- **CSV Export**: Download check history for analysis

## Usage Tips

### Sample Questions to Try:
- "What is Python used for?"
- "Explain JavaScript arrow functions"
- "How does machine learning work?"
- "What are the built-in types in Python?"
- "What is the World Wide Web?"

### Keyboard Shortcuts:
- `Ctrl+C` in terminal to stop the app
- `r` in browser to rerun/refresh the app
- `c` in browser to clear cache

## Troubleshooting

### App Not Loading?
If the browser shows "This site can't be reached" or similar:

1. **Check if Streamlit started successfully**
   - Look for "You can now view your Streamlit app" in the terminal
   - If you see errors, read them carefully

2. **Check the URL**
   - Should be `http://localhost:8501`
   - Try manually entering this URL in your browser

3. **Port already in use?**
   ```bash
   # Kill any process using port 8501
   lsof -ti:8501 | xargs kill -9
   ```
   Then restart the app

### Knowledge Base Empty?
If you see "Knowledge base is empty" message:
1. Click "Re-ingest Sources" button in the sidebar
2. Wait for ingestion to complete (3-5 minutes)
3. Start chatting!

### Ollama Not Running?
Make sure Ollama is running:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Or check models
ollama list  # Should show llama3.1 and nomic-embed-text
```

If Ollama is not running, start it:
```bash
ollama serve
```

### Chat Not Responding?
If the chat doesn't generate responses:
1. Check Ollama is running (see above)
2. Check terminal for error messages
3. Try a simpler question: "What is Python?"

### Health Dashboard Shows No Data?
If metrics show zeros or "No checks yet":
1. Click "🔄 Run Checks Now" button
2. Wait 30-60 seconds for checks to complete
3. Dashboard will update automatically

### Port Already in Use?
Specify a different port:
```bash
streamlit run app.py --server.port 8502
```

### Browser Doesn't Auto-Open?
Manually navigate to: `http://localhost:8501`

### Still Having Issues?
Check the logs:
```bash
# Run with verbose logging
streamlit run app.py --logger.level=debug
```

## Configuration

Edit `.env` file to configure:
- `LLM_BACKEND`: Set to "ollama" (default) or "openai"
- `OLLAMA_EMBEDDING_MODEL`: Embedding model (default: nomic-embed-text)
- `OLLAMA_CHAT_MODEL`: Chat model (default: llama3.1)

## Next Steps

After testing the Chat UI, proceed to Chunk 12 to build the full Health Dashboard with:
- Real-time source health monitoring
- On-demand check execution
- Scheduler controls
- Alert management
