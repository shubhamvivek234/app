#!/bin/bash
echo "🔄 Restarting servers..."
lsof -ti :8000 | xargs kill -9 2>/dev/null
lsof -ti :3000 | xargs kill -9 2>/dev/null
sleep 2

# Backend
cd /Users/shubham/app/backend
source venv/bin/activate
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &

# Frontend
cd /Users/shubham/app/frontend
PORT=3000 npm start > /tmp/frontend.log 2>&1 &

echo "⏳ Waiting for servers to start..."
sleep 12
echo "✅ Backend: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/auth/me -H 'Authorization: Bearer x')"
echo "✅ Frontend: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)"
echo ""
echo "🌐 Open: http://localhost:3000"
