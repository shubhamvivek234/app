# SocialSync - Social Media Scheduler

A full-stack social media scheduling platform. Users can create, schedule, and publish posts to Twitter/X, Instagram, and LinkedIn. Includes AI content generation, calendar view, subscription billing, and connected account management.

> **Note:** Social media posting is currently **mock only** — the backend marks posts as published but does not call real platform APIs. OAuth flows for Twitter/Instagram/LinkedIn are not yet implemented.

---

## Project Structure

```
app/
├── backend/
│   ├── server.py          # Single-file FastAPI app — all routes, models, auth, jobs
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/         # One file per route (Dashboard, CreatePost, Billing, etc.)
│   │   ├── components/    # DashboardLayout.js + shadcn ui/ components
│   │   ├── context/       # AuthContext.js — global auth state
│   │   └── lib/           # api.js (axios client), utils.js
│   ├── tailwind.config.js
│   └── package.json
└── uploads/               # User-uploaded media files (local, not S3)
```

---

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt          # Install dependencies
uvicorn server:app --host 0.0.0.0 --port 8001 --reload  # Run locally
sudo supervisorctl restart backend       # Restart in deployed env
tail -f /var/log/supervisor/backend.err.log  # Check logs
```

### Frontend
```bash
cd frontend
yarn install          # Install dependencies
yarn start            # Run locally on port 3000
yarn build            # Production build
sudo supervisorctl restart frontend      # Restart in deployed env
```

### MongoDB
```bash
mongosh mongodb://localhost:27017/test_database
```

---

## Tech Stack

**Backend:** Python, FastAPI, MongoDB (Motor async), Pydantic v2, APScheduler, PyJWT, bcrypt, Resend (email), Stripe + Razorpay + PayPal (payments), Emergent LLM (AI via OpenAI GPT-5.2)

**Frontend:** React 19, React Router v6, Tailwind CSS, Shadcn UI (Radix primitives), Axios, date-fns, Sonner (toasts), FullCalendar, Context API (no Redux)

---

## Environment Variables

### Backend — `backend/.env`
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
JWT_SECRET=change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=720
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=*

EMERGENT_LLM_KEY=sk-emergent-...    # AI content generation
STRIPE_API_KEY=sk_test_emergent     # Works in test mode
RAZORPAY_KEY_ID=                    # Add your own
RAZORPAY_KEY_SECRET=                # Add your own
PAYPAL_CLIENT_ID=                   # Add your own
PAYPAL_SECRET=                      # Add your own
RESEND_API_KEY=                     # Add for email verification
SENDER_EMAIL=onboarding@resend.dev
```

### Frontend — `frontend/.env`
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

---

## Architecture & Key Patterns

### Backend (`server.py`)
All backend code lives in a single file. The structure is:
- **Models** (Pydantic): `User`, `Post`, `SocialAccount`, `PaymentTransaction`
- **Auth:** JWT (Authorization header) + session token (cookie) — both supported via `get_current_user`
- **Routes** mounted under `/api` prefix via `APIRouter`
- **Background jobs:** APScheduler runs `process_scheduled_posts()` every 1 minute

Auth middleware checks cookie first, falls back to `Authorization: Bearer` header.

### Frontend
- All API calls go through `src/lib/api.js` — never call axios directly in components
- Auth state lives in `AuthContext` — use `useAuth()` hook everywhere
- Token stored in `localStorage` under key `token`
- All protected routes use `<PrivateRoute>`, all guest-only routes use `<PublicRoute>`
- UI components come from `src/components/ui/` (shadcn) — don't re-implement them

### Database Collections
| Collection | Key fields |
|---|---|
| `users` | `user_id`, `email`, `subscription_status` |
| `posts` | `id`, `user_id`, `status` (draft/scheduled/published), `scheduled_time` |
| `social_accounts` | `id`, `user_id`, `platform`, `is_active` |
| `payment_transactions` | `id`, `user_id`, `session_id`, `payment_method`, `payment_status` |
| `user_sessions` | `user_id`, `session_token`, `expires_at` (used for Google OAuth) |

MongoDB `_id` is always excluded in queries with `{"_id": 0}`.

---

## Subscription & Feature Gating

Scheduling posts (`scheduled_time`) requires `subscription_status == "active"`. This is checked in `POST /api/posts`. Free users can only create drafts.

Pricing (INR):
- Monthly: ₹500 / 30 days
- Yearly: ₹3,000 / 365 days

---

## Payment Flows

- **Stripe:** Fully working with test key. Webhook at `POST /api/webhook/stripe`. Status check at `GET /api/payments/status/{session_id}`.
- **Razorpay:** Requires adding keys to `.env`. Creates Razorpay order, redirects to `/razorpay-checkout?order_id=...`.
- **PayPal:** Requires adding keys to `.env`. Sandbox environment configured.

After successful payment, `subscription_status` is set to `"active"` and `subscription_end_date` is set on the user document.

---

## Google OAuth

Uses Emergent-managed OAuth. Flow:
1. Frontend redirects to Emergent OAuth URL
2. Emergent redirects back with a `session_id`
3. Frontend calls `POST /api/auth/google/callback` with `{ session_id }`
4. Backend fetches user data from Emergent, creates/updates user, stores session in `user_sessions`

**Do not hardcode redirect URLs or add fallbacks — this breaks the OAuth flow.**

---

## What's Not Implemented Yet

- Real social media posting (Twitter, Instagram, LinkedIn APIs)
- Google OAuth UI buttons (backend is ready)
- PayPal payment UI (backend is ready)
- Video/image upload UI (backend endpoint `/api/upload` exists)
- Email verification UI (backend is ready)
- Rate limiting, request validation beyond Pydantic
- DB indexes for production (see PROJECT_SUMMARY.md for recommended indexes)

---

## Don'ts

- Don't add new route files — all backend routes go in `server.py`
- Don't call APIs directly from React components — use `src/lib/api.js`
- Don't store real social media tokens without encrypting them first
- Don't hardcode the backend URL in frontend — always use `process.env.REACT_APP_BACKEND_URL`
- Don't add fallback redirect URLs to the Google OAuth callback endpoint
- Don't change the `uploads/` path without updating the `/api/upload` endpoint

---

## Useful Files

- `API_DOCUMENTATION.md` — full API reference with request/response examples
- `FRONTEND_INTEGRATION_GUIDE.md` — step-by-step guide for adding Google OAuth, PayPal, video upload UI
- `PROJECT_SUMMARY.md` — current status, what works, what needs API keys
