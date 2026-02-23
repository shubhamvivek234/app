#!/bin/bash

echo "Aggressively cleaning up old server processes to prevent hanging..."
# Kill any processes explicitly listening on our ports
lsof -ti:8001 | xargs kill -9 2>/dev/null || true
lsof -ti:9500 | xargs kill -9 2>/dev/null || true
# Kill dangling app instances by name
pkill -f "python3 -m uvicorn server:app" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true

source venv/bin/activate
export MONGO_URL="mongodb://localhost:27017" # mocked anyway
export DB_NAME="social_scheduler"

# Start Backend
echo "Starting Backend on port 8001..."
cd backend
python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!
cd ..

# Start Frontend
echo "Starting Frontend on port 9500..."
cd frontend
export PORT=9500
npm start &
FRONTEND_PID=$!

# Trap to kill both on exit
trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait $BACKEND_PID $FRONTEND_PID
