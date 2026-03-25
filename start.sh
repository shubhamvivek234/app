#!/bin/bash
# Persistent server startup script for SocialEntangler
# Usage: bash start.sh

# Kill any existing processes on ports 8000 and 3000
echo "Stopping any existing servers..."
lsof -ti :8000 | xargs kill -9 2>/dev/null
lsof -ti :3000 | xargs kill -9 2>/dev/null
sleep 1

# Start Backend with automatic restart on crash
echo "Starting backend on port 8000..."
cd /Users/shubham/app/backend
source venv/bin/activate
while true; do
    echo "[$(date)] Starting Uvicorn..."
    ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /Users/shubham/app/backend/backend.log
    echo "[$(date)] Backend crashed, restarting in 2s..."
    sleep 2
done &

# Start Frontend
echo "Starting frontend on port 3000..."
cd /Users/shubham/app/frontend
npm start 2>&1 | tee -a /Users/shubham/app/frontend.log &

echo ""
echo "✅ Both servers started!"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo ""
echo "To stop everything: lsof -ti :8000,:3000 | xargs kill -9"
wait
