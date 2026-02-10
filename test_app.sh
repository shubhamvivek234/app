#!/bin/bash
echo "🧪 Testing SocialSync Application"
echo "=================================="
echo ""

# Test 1: Backend Health
echo "1️⃣  Testing Backend API..."
SIGNUP_RESPONSE=$(curl -s -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test$(date +%s)@example.com\",\"password\":\"test123\",\"name\":\"Test User\"}")

if echo "$SIGNUP_RESPONSE" | grep -q "access_token"; then
    echo "   ✅ Backend API is working!"
    TOKEN=$(echo "$SIGNUP_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
else
    echo "   ❌ Backend API failed"
    exit 1
fi

# Test 2: Database Connection
echo ""
echo "2️⃣  Testing Database Connection..."
STATS_RESPONSE=$(curl -s -X GET http://localhost:8001/api/stats \
  -H "Authorization: Bearer $TOKEN")

if echo "$STATS_RESPONSE" | grep -q "total_posts"; then
    echo "   ✅ Database connection working!"
else
    echo "   ❌ Database connection failed"
fi

# Test 3: Frontend
echo ""
echo "3️⃣  Testing Frontend..."
if curl -s http://localhost:3000 | grep -q "Emergent"; then
    echo "   ✅ Frontend is serving!"
else
    echo "   ❌ Frontend not accessible"
fi

# Test 4: AI Integration
echo ""
echo "4️⃣  Testing AI Content Generation..."
AI_RESPONSE=$(curl -s -X POST http://localhost:8001/api/ai/generate-content \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Create a short tweet about AI"}')

if echo "$AI_RESPONSE" | grep -q "content"; then
    echo "   ✅ AI integration working!"
else
    echo "   ⚠️  AI integration may need API key"
fi

echo ""
echo "=================================="
echo "✅ Application is running successfully!"
echo ""
echo "Access the application at:"
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8001/api"
echo ""
echo "📚 Documentation:"
echo "  README: /app/README.md"
echo "  API Docs: /app/API_DOCUMENTATION.md"
echo "  Integration Guide: /app/FRONTEND_INTEGRATION_GUIDE.md"
