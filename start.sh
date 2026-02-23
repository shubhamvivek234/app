#!/bin/bash
# Persistent server startup script for SocialEntangler
# Usage: bash start.sh

# Kill any existing processes on ports 8001 and 9500
echo "Stopping any existing servers..."
lsof -ti :8001 | xargs kill -9 2>/dev/null
lsof -ti :9500 | xargs kill -9 2>/dev/null
sleep 1

# Start Backend with automatic restart on crash
echo "Starting backend on port 8001..."
cd /Users/shubham/app/backend
source venv/bin/activate
while true; do
    echo "[$(date)] Starting Uvicorn..."
    ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 2>&1 | tee -a /Users/shubham/app/backend/backend.log
    echo "[$(date)] Backend crashed, restarting in 2s..."
    sleep 2
done &

# Start Frontend
echo "Starting frontend on port 9500..."
cd /Users/shubham/app/frontend
npm start 2>&1 | tee -a /Users/shubham/app/frontend.log &

echo ""
echo "✅ Both servers started!"
echo "   Backend:  http://localhost:8001"
echo "   Frontend: http://localhost:9500"
echo ""
echo "To stop everything: lsof -ti :8001,:9500 | xargs kill -9"
wait
