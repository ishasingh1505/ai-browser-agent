#!/bin/bash
# Quick-start script for local development

set -e

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🎭 Installing Playwright browsers..."
playwright install chromium

echo "🚀 Starting server at http://localhost:8000"
echo "   Docs → http://localhost:8000/docs"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
