# SocialSync - Social Media Scheduler

A full-stack social media scheduling platform. Users can create, schedule, and publish posts to Twitter/X, Instagram, Facebook, LinkedIn, and YouTube. Includes AI content generation, calendar view, subscription billing, and connected account management.

---

## Project Structure

```
app/
├── backend/
│   ├── server.py              # Single-file FastAPI app — all routes, models, auth, jobs
│   ├── requirements.txt
│   └── app/
│       ├── social/            # Real OAuth integrations (version-6+)
│       │   ├── facebook.py    # FacebookAuth
│       │   ├── instagram.py   # InstagramAuth
│       │   ├── google.py      # GoogleAuth (Google + YouTube)
│       │   ├── twitter.py     # TwitterAuth
│       │   └── linkedin.py    # LinkedInAuth
│       ├── handlers/
│       │   ├── posts.py       # Post handling logic
│       │   └── notifications.py
│       └── models/
│           ├── posts.py       # Post models
│           └── notifications.py
├── frontend/
│   ├── src/
│   │   ├── pages/             # One file per route (Dashboard, CreatePostForm, CalendarView, etc.)
│   │   ├── components/        # DashboardLayout.js + shadcn ui/ components
│   │   ├── context/           # AuthContext.js — global auth state
│   │   └── lib/               # api.js (axios client), utils.js
│   ├── tailwind.config.js
│   └── package.json
└── uploads/                   # User-uploaded media files (local, not S3)
```

---

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt                                      # Install dependencies
uvicorn server:app --host 0.0.0.0 --port 8001 --reload              # Run locally
sudo supervisorctl restart backend                                    # Restart in deployed env
tail -f /var/log/supervisor/backend.err.log                          # Check logs
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

**Backend:** Python, FastAPI, MongoDB (Motor async), Pydantic v2, APScheduler, PyJWT, bcrypt, Firebase Admin (storage), Resend (email), Stripe + Razorpay (payments), Emergent LLM (AI)

**Frontend:** React 19, React Router v6, Tailwind CSS, Shadcn UI (Radix primitives), Axios, date-fns, Sonner (toasts), FullCalendar, Context API (no Redux)

---

## Environment Variables

### Backend — `backend/.env`
```
# Core
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
JWT_SECRET=change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=720
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=*

# AI
EMERGENT_LLM_KEY=sk-emergent-...

# Payments
STRIPE_API_KEY=sk_test_emergent     # Works in test mode
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=

# Email
RESEND_API_KEY=
SENDER_EMAIL=onboarding@resend.dev

# Firebase (storage)
FIREBASE_STORAGE_BUCKET=your-bucket.appspot.com

# Google OAuth + YouTube
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8001/api/oauth/google/callback
YOUTUBE_REDIRECT_URI=http://localhost:9500/oauth/callback
MOCK_GOOGLE_AUTH=false              # Set to "true" in dev to skip real OAuth

# Twitter / X
TWITTER_CLIENT_ID=
TWITTER_CLIENT_SECRET=
TWITTER_REDIRECT_URI=http://localhost:8001/api/oauth/twitter/callback

# LinkedIn
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=http://localhost:8001/api/oauth/linkedin/callback

# Facebook
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_REDIRECT_URI=http://localhost:8001/api/oauth/facebook/callback

# Instagram (shares Facebook app credentials)
INSTAGRAM_APP_ID=                   # Falls back to FACEBOOK_APP_ID if not set
INSTAGRAM_APP_SECRET=               # Falls back to FACEBOOK_APP_SECRET if not set
INSTAGRAM_REDIRECT_URI=             # Falls back to FACEBOOK_REDIRECT_URI if not set
```

### Frontend — `frontend/.env`
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

---

## Architecture & Key Patterns

### Backend (`server.py`)
All route definitions live in a single file. Imports platform OAuth classes from `app/social/`.

Structure:
- **Models** (Pydantic): `User`, `Post`, `SocialAccount`, `PaymentTransaction`
- **Auth:** JWT (Authorization header) + session token (cookie) — both supported via `get_current_user`
- **Routes** mounted under `/api` prefix via `APIRouter`
- **Background jobs:** APScheduler runs `process_scheduled_posts()` every 1 minute
- **Social OAuth modules:** imported from `app/social/` — do not inline OAuth logic into `server.py`

Auth middleware checks cookie first, falls back to `Authorization: Bearer` header.

### Social OAuth Modules (`backend/app/social/`)
Each platform has its own class. All classes are instantiated and used inside `server.py` route handlers.

| Module | Class | Env vars used |
|---|---|---|
| `google.py` | `GoogleAuth` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `YOUTUBE_REDIRECT_URI` |
| `twitter.py` | `TwitterAuth` | `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET`, `TWITTER_REDIRECT_URI` |
| `linkedin.py` | `LinkedInAuth` | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_REDIRECT_URI` |
| `facebook.py` | `FacebookAuth` | `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI` |
| `instagram.py` | `InstagramAuth` | `INSTAGRAM_APP_ID` (falls back to `FACEBOOK_APP_ID`), `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI` |

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
| `user_sessions` | `user_id`, `session_token`, `expires_at` |

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

After successful payment, `subscription_status` is set to `"active"` and `subscription_end_date` is set on the user document.

---

## OAuth Flows (version-6)

Real OAuth is implemented for all platforms via `backend/app/social/`. General flow:

1. Frontend calls backend `/api/oauth/{platform}/url` to get the authorization URL
2. User is redirected to the platform's OAuth page
3. Platform redirects back to `/api/oauth/{platform}/callback` with auth code
4. Backend exchanges code for tokens, stores in `social_accounts` collection
5. Frontend receives success and updates connected accounts UI

**Important:**
- Do not hardcode redirect URIs — always read from env vars
- Instagram shares Facebook app credentials unless `INSTAGRAM_*` vars are explicitly set
- Set `MOCK_GOOGLE_AUTH=true` in dev to skip real Google OAuth

---

## Don'ts

- Don't add new route files — all backend routes go in `server.py`
- Don't inline OAuth logic in `server.py` — put it in `backend/app/social/`
- Don't call APIs directly from React components — use `src/lib/api.js`
- Don't store real social media tokens without encrypting them first
- Don't hardcode the backend URL in frontend — always use `process.env.REACT_APP_BACKEND_URL`
- Don't change the `uploads/` path without updating the `/api/upload` endpoint

---

## Useful Files

- `API_DOCUMENTATION.md` — full API reference with request/response examples
- `FRONTEND_INTEGRATION_GUIDE.md` — guide for adding OAuth UI, video upload UI
- `PROJECT_SUMMARY.md` — current status, what works, what needs API keys
