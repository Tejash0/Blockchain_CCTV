#!/bin/bash

# AI Crime Detection Service Startup Script

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Start the service
echo "Starting AI Crime Detection Service..."
echo "API: http://localhost:8000"
echo "WebSocket: ws://localhost:8000/ws/alerts"
echo ""
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
