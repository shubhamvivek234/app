# SocialEntangler - Social Media Scheduler

A production-ready social media scheduling platform inspired by Post-Bridge. Schedule and publish content across Twitter/X, Instagram, and LinkedIn with AI-powered content generation.

## Features

### Core Functionality
- **Multi-Platform Posting**: Post to Twitter/X, Instagram, and LinkedIn simultaneously
- **Post Scheduling**: Schedule posts for optimal engagement times (requires subscription)
- **Calendar View**: Visual calendar to manage all scheduled posts
- **Content Library**: Manage all posts (drafts, scheduled, published) in one place
- **AI Content Generation**: Generate engaging posts using OpenAI GPT-5.2
- **Connected Accounts**: Manage social media account connections

### Subscription & Billing
- **Flexible Pricing**: Monthly (₹500) and Yearly (₹3,000) plans
- **Dual Payment Options**: Stripe and Razorpay integration
- **Subscription Management**: Track subscription status and renewal dates

### User Management
- **JWT Authentication**: Secure user authentication and authorization
- **User Dashboard**: Overview of posts, stats, and activity

## Tech Stack

### Backend
- **FastAPI**: High-performance async Python framework
- **MongoDB**: Document database with Motor async driver
- **JWT**: Token-based authentication
- **APScheduler**: Background job processing for scheduled posts
- **OpenAI GPT-5.2**: AI content generation via Emergent LLM key
- **Stripe & Razorpay**: Payment processing

### Frontend
- **React 19**: Modern React with hooks
- **React Router**: Client-side routing
- **Tailwind CSS**: Utility-first styling
- **Shadcn UI**: Accessible component library
- **date-fns**: Date manipulation
- **Axios**: HTTP client
- **Sonner**: Toast notifications

## Getting Started

### Prerequisites
- Node.js 18+ and Yarn
- Python 3.11+
- MongoDB running locally or remote connection

### Environment Variables

#### Backend (`/app/backend/.env`)
```bash
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"

# JWT Configuration
JWT_SECRET=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=720

# AI Content Generation (Already configured)
EMERGENT_LLM_KEY=sk-emergent-758930a3e9c4dF8851

# Payment Gateways
STRIPE_API_KEY=sk_test_emergent  # Test key provided
RAZORPAY_KEY_ID=your_razorpay_key_id  # Add your keys
RAZORPAY_KEY_SECRET=your_razorpay_key_secret

# Social Media APIs (Optional - for production)
TWITTER_API_KEY=your_twitter_key
TWITTER_API_SECRET=your_twitter_secret
INSTAGRAM_ACCESS_TOKEN=your_instagram_token
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
```

#### Frontend (`/app/frontend/.env`)
```bash
REACT_APP_BACKEND_URL=your_backend_url  # Auto-configured
```

### Installation

1. **Install Backend Dependencies**
```bash
cd /app/backend
pip install -r requirements.txt
```

2. **Install Frontend Dependencies**
```bash
cd /app/frontend
yarn install
```

3. **Start Services**
```bash
# Restart both services
sudo supervisorctl restart backend frontend

# Check status
sudo supervisorctl status
```

### Running Locally

Backend runs on: `http://0.0.0.0:8001`
Frontend runs on: `http://localhost:3000`

API endpoints are available at: `{BACKEND_URL}/api/*`

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Create new account
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user

### Posts
- `POST /api/posts` - Create post
- `GET /api/posts` - Get all posts (with optional status filter)
- `GET /api/posts/{id}` - Get single post
- `PATCH /api/posts/{id}` - Update post
- `DELETE /api/posts/{id}` - Delete post

### AI Content Generation
- `POST /api/ai/generate-content` - Generate post content with AI

### Social Accounts
- `POST /api/social-accounts` - Connect social account
- `GET /api/social-accounts` - Get connected accounts
- `DELETE /api/social-accounts/{id}` - Disconnect account

### Payments
- `POST /api/payments/checkout` - Create checkout session
- `GET /api/payments/status/{session_id}` - Check payment status
- `POST /api/webhook/stripe` - Stripe webhook handler

### Stats
- `GET /api/stats` - Get user statistics

## Social Media Integration

### Current State
The app currently uses **mock connections** for social media accounts. This allows you to test the full flow without real API credentials.

### For Production Use

To enable real social media posting, you need to:

#### 1. Twitter/X API
- Create app at: https://developer.twitter.com
- Get API Key and Secret
- Add to backend/.env

#### 2. Instagram (via Facebook Graph API)
- Create Facebook app: https://developers.facebook.com
- Enable Instagram Graph API
- Get access token
- Add to backend/.env

#### 3. LinkedIn API
- Create app at: https://developer.linkedin.com
- Get Client ID and Secret
- Implement OAuth flow
- Add to backend/.env

#### 4. Update Backend Code
Implement actual posting logic in `/app/backend/server.py`:
- Replace mock connections with OAuth flows
- Implement platform-specific posting logic
- Handle rate limits and errors

## Subscription Plans

### Free Plan
- Create and manage posts
- Access to all features (view-only for scheduling)
- AI content generation

### Monthly Plan (₹500/month)
- Connect up to 3 social accounts
- Unlimited posts
- Schedule posts
- AI content generation
- Email support

### Yearly Plan (₹3,000/year)
- All Monthly features
- 50% discount
- Priority support
- Early access to new features

## Payment Integration

### Stripe
- Test mode configured with: `sk_test_emergent`
- Supports: Cards, Digital wallets
- Automatic subscription management

### Razorpay
- **Setup Required**: Add your keys to backend/.env
- Supports: UPI, Cards, Net Banking, Wallets
- Popular in Indian market

## Background Jobs

The app uses APScheduler to process scheduled posts every minute:
- Checks for posts scheduled to be published
- Marks them as published (integrate with actual APIs for production)
- Runs automatically in the background

## Database Schema

### Users Collection
```javascript
{
  id: string,
  email: string,
  name: string,
  password: string (hashed),
  subscription_status: "free" | "active" | "expired",
  subscription_plan: "monthly" | "yearly",
  subscription_end_date: datetime,
  created_at: datetime
}
```

### Posts Collection
```javascript
{
  id: string,
  user_id: string,
  content: string,
  platforms: ["twitter", "instagram", "linkedin"],
  media_urls: [string],
  scheduled_time: datetime,
  status: "draft" | "scheduled" | "published" | "failed",
  created_at: datetime,
  published_at: datetime,
  ai_generated: boolean
}
```

### Social Accounts Collection
```javascript
{
  id: string,
  user_id: string,
  platform: string,
  platform_user_id: string,
  platform_username: string,
  access_token: string,
  refresh_token: string,
  token_expiry: datetime,
  is_active: boolean,
  connected_at: datetime
}
```

### Payment Transactions Collection
```javascript
{
  id: string,
  user_id: string,
  session_id: string,
  payment_id: string,
  amount: float,
  currency: string,
  plan: "monthly" | "yearly",
  payment_method: "stripe" | "razorpay",
  payment_status: "pending" | "paid" | "failed" | "expired",
  metadata: object,
  created_at: datetime,
  updated_at: datetime
}
```

## Security Considerations

### Implemented
- ✅ JWT-based authentication
- ✅ Password hashing with bcrypt
- ✅ CORS configuration
- ✅ Environment variable management
- ✅ Webhook signature verification (Stripe)

### For Production
- [ ] Rate limiting on API endpoints
- [ ] Input validation and sanitization
- [ ] HTTPS enforcement
- [ ] Database connection encryption
- [ ] Secret rotation strategy
- [ ] Logging and monitoring
- [ ] GDPR compliance measures

## Scaling Considerations

### Database
- Add indexes on frequently queried fields (user_id, created_at, scheduled_time)
- Consider sharding for 10k+ users
- Implement caching layer (Redis)

### Backend
- Horizontal scaling with load balancer
- Separate worker processes for scheduled posts
- Queue system for high-volume posting (Celery/RabbitMQ)

### Frontend
- CDN for static assets
- Code splitting and lazy loading
- Service worker for offline capability

## Deployment

### Recommended Stack
- **Backend**: AWS ECS/EKS, Google Cloud Run, or DigitalOcean App Platform
- **Frontend**: Vercel, Netlify, or CloudFlare Pages
- **Database**: MongoDB Atlas
- **File Storage**: AWS S3 or Cloudflare R2

## License

MIT License - feel free to use for personal or commercial projects

## Support

For issues or questions:
- Check the Settings page for API setup instructions
- Review logs: `/var/log/supervisor/backend.err.log`
- Check MongoDB connection status

## Acknowledgments

- Inspired by [Post-Bridge](https://www.post-bridge.com/)
- Built with [Emergent](https://emergent.sh)
- UI components from [Shadcn UI](https://ui.shadcn.com/)
