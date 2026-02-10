# SocialSync API Documentation

## Base URL
```
Production: {REACT_APP_BACKEND_URL}/api
Development: http://localhost:8001/api
```

## Authentication

All authenticated endpoints require either:
- **JWT Token**: `Authorization: Bearer <token>` header
- **Session Cookie**: `session_token` cookie (auto-sent by browser)

---

## Authentication Endpoints

### 1. Sign Up (Email/Password)
```http
POST /api/auth/signup
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securePassword123",
  "name": "John Doe"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "user_id": "user_abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "email_verified": false,
    "subscription_status": "free",
    "created_at": "2026-02-10T12:00:00Z"
  }
}
```

**Notes:**
- Email verification link sent to user's email (requires RESEND_API_KEY)
- User can access app immediately, but some features may require verification

---

### 2. Login (Email/Password)
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securePassword123"
}
```

**Response:** Same as signup

---

### 3. Google OAuth Callback
```http
POST /api/auth/google/callback
Content-Type: application/json

{
  "session_id": "google_session_id_from_emergent_auth"
}
```

**Response:**
```json
{
  "session_token": "session_abc123",
  "user": {
    "user_id": "user_abc123",
    "email": "user@example.com",
    "name": "John Doe",
    "picture": "https://...",
    "email_verified": true,
    "subscription_status": "free"
  }
}
```

**Frontend Flow:**
1. Redirect to: `https://auth.emergentagent.com/?redirect={YOUR_CALLBACK_URL}`
2. User completes Google OAuth
3. Redirected to: `{YOUR_CALLBACK_URL}?session_id={SESSION_ID}`
4. Call this endpoint with session_id
5. Receive session_token, set as cookie

**CRITICAL:** Do NOT hardcode redirect URL or add fallbacks - breaks OAuth

---

### 4. Verify Email
```http
GET /api/auth/verify-email?token={verification_token}
```

**Response:**
```json
{
  "message": "Email verified successfully"
}
```

**Token received via email link**

---

### 5. Get Current User
```http
GET /api/auth/me
Authorization: Bearer <token>
```

**Response:** User object

---

### 6. Logout
```http
POST /api/auth/logout
```

**Response:**
```json
{
  "message": "Logged out successfully"
}
```

---

## Post Management

### 1. Create Post
```http
POST /api/posts
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "Check out this amazing post!",
  "post_type": "text",  // "text" | "image" | "video"
  "platforms": ["twitter", "linkedin", "instagram"],
  "scheduled_time": "2026-02-15T14:00:00Z",  // optional
  "media_urls": ["http://..."],  // for image posts
  "video_url": "http://...",  // for video posts
  "cover_image_url": "http://...",  // optional for videos
  "video_title": "My Video Title"  // optional for videos
}
```

**Response:**
```json
{
  "id": "post_abc123",
  "user_id": "user_abc123",
  "content": "Check out this amazing post!",
  "post_type": "text",
  "platforms": ["twitter", "linkedin"],
  "status": "scheduled",  // "draft" | "scheduled" | "published" | "failed"
  "scheduled_time": "2026-02-15T14:00:00Z",
  "created_at": "2026-02-10T12:00:00Z",
  "ai_generated": false
}
```

**Notes:**
- Scheduling requires active subscription
- Posts without scheduled_time are saved as drafts
- Background job publishes scheduled posts every minute

---

### 2. Upload Media File
```http
POST /api/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <binary_data>
```

**Response:**
```json
{
  "url": "/uploads/abc123.jpg",
  "filename": "my-image.jpg"
}
```

**Supported formats:**
- Images: PNG, JPG, JPEG, GIF
- Videos: MP4, MOV, AVI

**Storage:** Files stored in `/app/uploads/` (use S3/CloudFlare R2 for production)

---

### 3. Get All Posts
```http
GET /api/posts
GET /api/posts?status=scheduled
Authorization: Bearer <token>
```

**Query Parameters:**
- `status` (optional): Filter by status (draft, scheduled, published, failed)

**Response:** Array of post objects

---

### 4. Get Single Post
```http
GET /api/posts/{post_id}
Authorization: Bearer <token>
```

**Response:** Post object

---

### 5. Update Post
```http
PATCH /api/posts/{post_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "Updated content",
  "platforms": ["twitter"],
  "scheduled_time": "2026-02-16T10:00:00Z"
}
```

**Response:** Updated post object

---

### 6. Delete Post
```http
DELETE /api/posts/{post_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Post deleted"
}
```

---

## AI Content Generation

### Generate Content
```http
POST /api/ai/generate-content
Authorization: Bearer <token>
Content-Type: application/json

{
  "prompt": "Write a motivational post about productivity for entrepreneurs",
  "platform": "twitter"  // optional: "twitter" | "linkedin" | "instagram"
}
```

**Response:**
```json
{
  "content": "Productivity isn't about doing *more*—it's about doing what moves the needle. As an entrepreneur, your to-do list will never end..."
}
```

**Platform-specific optimization:**
- Twitter: <280 characters
- LinkedIn: Professional tone
- Instagram: Engaging with hashtags

**Powered by:** OpenAI GPT-5.2 via Emergent LLM Key

---

## Social Media Accounts

### 1. Connect Account
```http
POST /api/social-accounts
Authorization: Bearer <token>
Content-Type: application/json

{
  "platform": "twitter",  // "twitter" | "instagram" | "linkedin"
  "platform_username": "@johndoe"
}
```

**Response:**
```json
{
  "id": "account_abc123",
  "user_id": "user_abc123",
  "platform": "twitter",
  "platform_username": "@johndoe",
  "is_active": true,
  "connected_at": "2026-02-10T12:00:00Z"
}
```

**Note:** Currently mock implementation. For production:
- Implement OAuth flow for each platform
- Store access_token, refresh_token
- See README for API setup instructions

---

### 2. Get Connected Accounts
```http
GET /api/social-accounts
Authorization: Bearer <token>
```

**Response:** Array of account objects

---

### 3. Disconnect Account
```http
DELETE /api/social-accounts/{account_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "message": "Account disconnected"
}
```

---

## Payments & Subscriptions

### Plans
- **Monthly**: ₹500/month (30 days)
- **Yearly**: ₹3,000/year (365 days)

### 1. Create Checkout Session
```http
POST /api/payments/checkout
Authorization: Bearer <token>
Content-Type: application/json

{
  "plan": "monthly",  // "monthly" | "yearly"
  "payment_method": "stripe"  // "stripe" | "razorpay" | "paypal"
}
```

**Response:**
```json
{
  "url": "https://checkout.stripe.com/...",
  "session_id": "cs_abc123"
}
```

**Flow:**
1. Call this endpoint
2. Redirect user to `url`
3. User completes payment
4. Redirected back with session_id
5. Call status endpoint to verify

---

### 2. Check Payment Status
```http
GET /api/payments/status/{session_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "status": "paid",
  "payment_status": "paid",
  "amount_total": 50000,  // in paise/cents
  "currency": "INR",
  "metadata": {
    "user_id": "user_abc123",
    "plan": "monthly"
  }
}
```

**Subscription automatically activated on successful payment**

---

### 3. Stripe Webhook
```http
POST /api/webhook/stripe
Stripe-Signature: <signature>

<stripe_webhook_payload>
```

**Handles:**
- `checkout.session.completed`: Activates subscription
- Automatically updates user subscription status

**Setup:** Configure webhook URL in Stripe dashboard

---

## Statistics

### Get User Stats
```http
GET /api/stats
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_posts": 25,
  "scheduled_posts": 5,
  "published_posts": 18,
  "connected_accounts": 3
}
```

---

## Content Pages

### 1. Terms of Service
```http
GET /api/pages/terms
```

**Response:**
```json
{
  "content": "Terms of Service - SocialSync provides..."
}
```

---

### 2. Privacy Policy
```http
GET /api/pages/privacy
```

**Response:**
```json
{
  "content": "Privacy Policy - We respect your privacy..."
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid email or password"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Scheduling requires active subscription"
}
```

### 404 Not Found
```json
{
  "detail": "Post not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "AI generation failed: ..."
}
```

---

## Rate Limiting

**Current:** No rate limiting implemented

**Recommendation for production:**
- 100 requests/minute per user for general endpoints
- 10 requests/minute for AI generation
- 5 requests/minute for file uploads

Implement using:
```python
from slowapi import Limiter
```

---

## Background Jobs

### Scheduled Post Processor
- **Runs:** Every 1 minute
- **Function:** `process_scheduled_posts()`
- **Action:** Publishes posts where `scheduled_time <= now`

**Status:** Marks posts as "published"
**Production:** Implement actual posting to social platforms via their APIs

---

## Environment Variables Required

### Backend (.env)
```bash
# Core
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"
JWT_SECRET=your-strong-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=720

# AI (Already configured)
EMERGENT_LLM_KEY=sk-emergent-758930a3e9c4dF8851

# Payments
STRIPE_API_KEY=sk_test_emergent  # Test key provided
RAZORPAY_KEY_ID=your_razorpay_key_id  # Add your keys
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
PAYPAL_CLIENT_ID=your_paypal_client_id  # Add your keys
PAYPAL_SECRET=your_paypal_secret

# Email Verification
RESEND_API_KEY=your_resend_api_key  # Get from resend.com
SENDER_EMAIL=onboarding@resend.dev

# URLs
FRONTEND_URL=http://localhost:3000
```

### Frontend (.env)
```bash
REACT_APP_BACKEND_URL=your_backend_url  # Auto-configured
```

---

## Integration Guides

### Google OAuth Frontend Integration
```javascript
// 1. Redirect to Emergent Auth
const handleGoogleLogin = () => {
  const redirectUrl = window.location.origin + '/auth/callback';
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

// 2. Handle callback (AuthCallback component)
const sessionId = new URLSearchParams(window.location.search).get('session_id');
const response = await axios.post('/api/auth/google/callback', { session_id: sessionId });
Cookies.set('session_token', response.data.session_token, { expires: 7 });
```

### PayPal Integration Setup
```bash
# 1. Create PayPal app at developer.paypal.com
# 2. Get Client ID and Secret
# 3. Add to backend/.env:
PAYPAL_CLIENT_ID=your_client_id
PAYPAL_SECRET=your_secret

# 4. Test with sandbox credentials first
```

### Email Verification Setup
```bash
# 1. Sign up at resend.com
# 2. Get API key
# 3. Add to backend/.env:
RESEND_API_KEY=re_abc123
SENDER_EMAIL=noreply@yourdomain.com

# 4. Verify domain for production
```

---

## Testing Endpoints

### Quick Health Check
```bash
curl http://localhost:8001/api/pages/terms
```

### Create User & Login
```bash
# Signup
curl -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","name":"Test User"}'

# Login
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
```

### AI Generation
```bash
TOKEN="your_jwt_token"
curl -X POST http://localhost:8001/api/ai/generate-content \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a tweet about productivity","platform":"twitter"}'
```

---

## Database Collections

### users
```javascript
{
  user_id: "user_abc123",
  email: "user@example.com",
  name: "John Doe",
  password: "hashed_password",
  picture: "https://...",
  email_verified: true,
  verification_token: "token_abc",
  verification_expires: "2026-02-11T12:00:00Z",
  subscription_status: "active",  // "free" | "active" | "expired"
  subscription_plan: "monthly",  // "monthly" | "yearly"
  subscription_end_date: "2026-03-10T12:00:00Z",
  created_at: "2026-02-10T12:00:00Z"
}
```

### posts
```javascript
{
  id: "post_abc123",
  user_id: "user_abc123",
  content: "Post content",
  post_type: "text",  // "text" | "image" | "video"
  platforms: ["twitter", "linkedin"],
  media_urls: ["http://..."],
  video_url: "http://...",
  cover_image_url: "http://...",
  video_title: "Video Title",
  scheduled_time: "2026-02-15T14:00:00Z",
  status: "scheduled",  // "draft" | "scheduled" | "published" | "failed"
  published_at: "2026-02-15T14:00:05Z",
  ai_generated: false,
  created_at: "2026-02-10T12:00:00Z"
}
```

### social_accounts
```javascript
{
  id: "account_abc123",
  user_id: "user_abc123",
  platform: "twitter",
  platform_user_id: "12345",
  platform_username: "@johndoe",
  access_token: "encrypted_token",
  refresh_token: "encrypted_token",
  token_expiry: "2026-03-10T12:00:00Z",
  is_active: true,
  connected_at: "2026-02-10T12:00:00Z"
}
```

### payment_transactions
```javascript
{
  id: "trans_abc123",
  user_id: "user_abc123",
  session_id: "cs_abc123",
  payment_id: "pi_abc123",
  amount: 500.0,
  currency: "INR",
  plan: "monthly",
  payment_method: "stripe",  // "stripe" | "razorpay" | "paypal"
  payment_status: "paid",  // "pending" | "paid" | "failed" | "expired"
  metadata: {},
  created_at: "2026-02-10T12:00:00Z",
  updated_at: "2026-02-10T12:05:00Z"
}
```

### user_sessions (for Google OAuth)
```javascript
{
  user_id: "user_abc123",
  session_token: "session_abc123",
  expires_at: "2026-02-17T12:00:00Z",
  created_at: "2026-02-10T12:00:00Z"
}
```

---

## Security Best Practices

### Implemented
✅ JWT token authentication
✅ Password hashing with bcrypt
✅ CORS configuration
✅ Environment variable management
✅ Stripe webhook signature verification

### Recommended for Production
- [ ] Add rate limiting (slowapi or redis)
- [ ] Input validation and sanitization
- [ ] HTTPS enforcement
- [ ] Database connection encryption
- [ ] Secret rotation strategy
- [ ] Logging and monitoring (Sentry)
- [ ] GDPR compliance measures
- [ ] API key encryption in database
- [ ] Request/response logging

---

## Deployment Checklist

### Backend
- [ ] Update JWT_SECRET to strong random string
- [ ] Configure production MongoDB (MongoDB Atlas)
- [ ] Add production payment keys (Stripe, Razorpay, PayPal)
- [ ] Configure email service (Resend with verified domain)
- [ ] Set up cloud storage (S3/CloudFlare R2) for uploads
- [ ] Configure CORS for production domain
- [ ] Enable HTTPS
- [ ] Set up monitoring (New Relic, Datadog)
- [ ] Configure webhooks for payment providers
- [ ] Implement social media OAuth flows

### Frontend
- [ ] Update REACT_APP_BACKEND_URL to production API
- [ ] Build optimized production bundle
- [ ] Configure CDN for static assets
- [ ] Enable service worker for offline support
- [ ] Set up error tracking (Sentry)
- [ ] Implement analytics (Google Analytics, Mixpanel)

---

## Support & Resources

- **Stripe Docs**: https://stripe.com/docs
- **Razorpay Docs**: https://razorpay.com/docs
- **PayPal Docs**: https://developer.paypal.com/docs
- **Resend Docs**: https://resend.com/docs
- **Twitter API**: https://developer.twitter.com
- **Instagram API**: https://developers.facebook.com/docs/instagram-api
- **LinkedIn API**: https://developer.linkedin.com

For issues or questions, check `/app/README.md` or backend logs at `/var/log/supervisor/backend.err.log`
