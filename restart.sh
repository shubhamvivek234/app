#!/bin/bash
echo "🔄 Restarting servers..."
lsof -ti :8001 | xargs kill -9 2>/dev/null
lsof -ti :9500 | xargs kill -9 2>/dev/null
sleep 2

# Backend
cd /Users/shubham/app/backend
source venv/bin/activate
python3 -m uvicorn server:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &

# Frontend  
cd /Users/shubham/app/frontend
PORT=9500 npm start > /tmp/frontend.log 2>&1 &

echo "⏳ Waiting for servers to start..."
sleep 12
echo "✅ Backend: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/auth/me -H 'Authorization: Bearer x')"
echo "✅ Frontend: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:9500)"
echo ""
echo "🌐 Open: http://localhost:9500"
