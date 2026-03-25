#!/bin/bash

echo "Aggressively cleaning up old server processes to prevent hanging..."
# Kill any processes explicitly listening on our ports
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
# Kill dangling app instances by name
pkill -f "python3 -m uvicorn" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true

source backend/venv/bin/activate
export MONGODB_URI="mongodb://localhost:27017"
export DB_NAME="social_scheduler"
export REDIS_URL="redis://localhost:6379/0"
export REDIS_QUEUE_URL="redis://localhost:6379/0"
export REDIS_CACHE_URL="redis://localhost:6379/1"
export FIREBASE_ADMIN_SDK_JSON="backend/serviceAccountKey.json"
export ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"

# Start Backend
echo "Starting Backend v2.9 on port 8000..."
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --env-file backend/.env > backend.log 2>&1 &
BACKEND_PID=$!

# Start Frontend
echo "Starting Frontend on port 3000..."
cd frontend
export PORT=3000
npm start &
FRONTEND_PID=$!

# Trap to kill both on exit
trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait $BACKEND_PID $FRONTEND_PID
