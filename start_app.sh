#!/bin/bash

echo "============================================================"
echo "RAG Source Monitor - Startup Diagnostics"
echo "============================================================"
echo ""

# Activate virtual environment
echo "1. Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "   ✗ Failed to activate venv"
    exit 1
fi
echo "   ✓ Virtual environment activated"
echo ""

# Check Ollama
echo "2. Checking Ollama service..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "   ✓ Ollama is running"
    echo "   Models available:"
    curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; models = json.load(sys.stdin)['models']; [print(f'     - {m[\"name\"]}') for m in models[:3]]"
else
    echo "   ✗ Ollama is not running"
    echo "   Please start Ollama first"
    exit 1
fi
echo ""

# Check ChromaDB
echo "3. Checking ChromaDB..."
python -c "from ingestion.embedder import is_collection_empty; empty = is_collection_empty(); print(f'   ✓ ChromaDB ready'); print(f'   Collection empty: {empty}')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "   ✗ ChromaDB connection failed"
    exit 1
fi
echo ""

# Check Monitor DB
echo "4. Checking Monitor Database..."
python -c "from monitor.db import get_alert_summary; s = get_alert_summary(); print(f'   ✓ Monitor DB ready'); print(f'   Active alerts: {s[\"total_active\"]}')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "   ✗ Monitor DB connection failed"
    exit 1
fi
echo ""

echo "============================================================"
echo "All systems operational! Starting Streamlit..."
echo "============================================================"
echo ""
echo "The app will open in your browser at: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start Streamlit
streamlit run app.py
