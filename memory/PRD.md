# Post Bridge - Social Media Scheduler PRD

## Original Problem Statement
Build a production-level social media scheduling application with:
- Authentication (Email/password signup with email verification, Google OAuth)
- Multi-step onboarding flow (user type selection, account connection, pricing, payment)
- Social media connections dashboard
- Create Post feature with Text/Image/Video post types
- Calendar view for scheduled posts
- Payment integration (Stripe, Razorpay, PayPal)
- Landing page with professional design

## Core Requirements

### Authentication
- [x] Email/password signup with email verification
- [x] Google OAuth integration via Emergent Auth
- [x] JWT token-based authentication
- [x] "Back to Home" links on auth pages

### Onboarding Flow
- [x] User type selection (Founder, Creator, Agency, etc.)
- [x] Skippable account connection step
- [x] Pricing plan selection page
- [x] Payment page UI

### Dashboard & Navigation
- [x] Sidebar navigation matching "post bridge" design
- [x] Sections: Workspace, Create, Posts, Configuration, Support
- [x] Dashboard overview with stats cards
- [x] Mobile-responsive layout

### Create Post Feature
- [x] Post type selection (Text, Image, Video) with platform icons
- [x] Text Post support for: Facebook, Twitter, LinkedIn, Threads, Bluesky
- [x] Image Post support for: Facebook, Twitter, LinkedIn, Instagram, Pinterest, TikTok, Threads
- [x] Video Post support for: All platforms including YouTube

### Video Post Creation (NEW - Feb 2026)
- [x] Account selection with circular avatars and platform icons
- [x] Video upload area with drag-and-drop
- [x] Main caption with character count
- [x] Platform-specific captions (expandable)
- [x] YouTube Title option
- [x] TikTok Config option
- [x] Schedule post panel with date/time picker
- [x] Save to Drafts functionality

### Connections Page (NEW - Feb 2026)
- [x] All 9 platforms: Bluesky, Facebook, Instagram, LinkedIn, Pinterest, Threads, TikTok, Twitter, YouTube
- [x] Connect buttons for each platform (dark style)
- [x] Connected account tags with avatars and X to disconnect
- [x] Refresh buttons for Instagram, Twitter, TikTok, Facebook
- [x] Help link at bottom

### Calendar Page (NEW - Feb 2026)
- [x] Monthly calendar view with full grid
- [x] Day headers (Sun-Sat)
- [x] Month/Year navigation with arrows
- [x] Month/Week toggle buttons
- [x] Current day highlighting (green)
- [x] Post indicators in each day cell
- [x] "No posts" indicator for empty days

### Payments
- [x] Stripe integration
- [x] Razorpay integration  
- [x] PayPal integration
- [x] Checkout session creation
- [x] Payment status verification

## Technical Architecture

### Frontend
- React with React Router
- TailwindCSS for styling
- Shadcn/UI components
- react-icons for platform icons (including Si for Bluesky, Threads)
- date-fns for calendar functionality

### Backend
- FastAPI (Python)
- MongoDB database
- JWT authentication
- APScheduler for scheduled posts

### Key Files
- `/app/frontend/src/pages/CreatePost.js` - Post type selection
- `/app/frontend/src/pages/CreatePostForm.js` - Video/Image/Text post form
- `/app/frontend/src/pages/ConnectedAccounts.js` - Connections management
- `/app/frontend/src/pages/CalendarView.js` - Calendar view
- `/app/frontend/src/components/DashboardLayout.js` - Sidebar navigation
- `/app/backend/server.py` - All API endpoints

## What's Implemented (as of Feb 2026)

### Completed
1. ✅ Full authentication system (email + Google OAuth)
2. ✅ Multi-step onboarding flow
3. ✅ Create Post page with 3 post types
4. ✅ Connections page with 9 platforms and mock accounts
5. ✅ Calendar page with monthly view
6. ✅ Video post creation form with:
   - Account selection grid
   - Video upload area
   - Platform-specific captions
   - YouTube Title option
   - TikTok Config option
   - Schedule/Draft functionality
7. ✅ Landing page with header/footer
8. ✅ Payment page UI

### Mocked Features (Need Real Integration)
- ⚠️ Social media OAuth connections (mock data displayed)
- ⚠️ Actual post publishing to platforms
- ⚠️ Payment processing (UI complete, backend ready for keys)

## Upcoming Tasks

### P0 - Critical
- None currently

### P1 - High Priority
- Real OAuth integration for all platforms (requires API keys)
- Payment processing activation (requires Stripe/Razorpay/PayPal keys)
- Google Sign-Up verification

### P2 - Medium Priority
- Video preview in right panel
- Cover image selection for videos
- Past captions functionality
- Processing options

### P3 - Backlog
- Analytics dashboard
- Team collaboration features
- Content library
- Bulk scheduling tools
- AI content generation improvements

## Test Credentials
- Email: testdemo@example.com
- Password: test123
- User has onboarding_completed=true

## Preview URL
https://postflow-25.preview.emergentagent.com
