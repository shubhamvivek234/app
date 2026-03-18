from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header, Cookie, UploadFile, File, Form
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import structlog
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
from passlib.context import CryptContext
import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
import razorpay
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import resend
import httpx
import html as _html
import html as _html_module
import re as _re
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.social.facebook import FacebookAuth
from app.social.instagram import InstagramAuth
from app.social.google import GoogleAuth
from app.social.twitter import TwitterAuth
from app.social.linkedin import LinkedInAuth
from app.social.threads import ThreadsAuth
from app.social.reddit import RedditAuth
from app.social.pinterest import PinterestAuth
from app.social.snapchat import SnapchatAuth
from app.social.tiktok import TikTokAuth
from app.social.bluesky import BlueskyAuth
from app.media_validator import validate_upload, MediaValidationError
from app.dlq import get_dlq_items, retry_from_dlq
from app.errors import ErrorCode as StructuredErrorCode, api_error, structured_error_response, classify_platform_error as classify_platform_error_structured
# from paypal_checkout_sdk.core import PayPalHttpClient, SandboxEnvironment
# from paypal_checkout_sdk.orders import OrdersCreateRequest, OrdersCaptureRequest

# ── Error Classification (Stage 3.5) ───────────────────────────────────────────
# Error codes from Architecture Blueprint v2.8
class ErrorCode:
    # Publishing errors
    EC1  = "EC1:NETWORK_FAILURE"         # Network error during platform API call
    EC2  = "EC2:AUTH_EXPIRED"            # Platform OAuth token expired
    EC3  = "EC3:RATE_LIMITED"            # Hit platform rate limit
    EC4  = "EC4:MEDIA_TOO_LARGE"        # File exceeds platform size limit
    EC5  = "EC5:INVALID_MEDIA_FORMAT"   # Unsupported file format
    EC6  = "EC6:CAPTION_TOO_LONG"       # Caption exceeds platform character limit
    EC7  = "EC7:ACCOUNT_SUSPENDED"      # Platform account suspended
    EC8  = "EC8:PERMISSION_DENIED"      # Missing required API permission
    EC9  = "EC9:DUPLICATE_POST"         # Idempotency key collision detected
    EC10 = "EC10:MEDIA_PROCESSING_TIMEOUT"  # Video processing exceeded 2.5 min
    # System errors
    EC17 = "EC17:DB_WRITE_FAILURE"      # MongoDB write failed after publish
    EC20 = "EC20:QUEUE_OVERFLOW"        # Upload queue depth exceeded
    EC26 = "EC26:REDIS_UNAVAILABLE"     # Redis connection failed
    # Auth errors
    EC30 = "EC30:SUBSCRIPTION_REQUIRED" # Feature requires active subscription


def classify_platform_error(error: Exception, platform: str) -> str:
    """Classify an exception into an EC error code."""
    msg = str(error).lower()
    if "token" in msg and ("expired" in msg or "invalid" in msg or "auth" in msg):
        return ErrorCode.EC2
    if "rate" in msg and "limit" in msg:
        return ErrorCode.EC3
    if "size" in msg or "too large" in msg or "file size" in msg:
        return ErrorCode.EC4
    if "format" in msg or "unsupported" in msg or "codec" in msg:
        return ErrorCode.EC5
    if "caption" in msg or "text" in msg and "long" in msg:
        return ErrorCode.EC6
    if "suspended" in msg or "disabled" in msg or "banned" in msg:
        return ErrorCode.EC7
    if "permission" in msg or "scope" in msg or "access" in msg:
        return ErrorCode.EC8
    if "timeout" in msg or "timed out" in msg:
        return ErrorCode.EC10
    if "network" in msg or "connection" in msg or "connect" in msg:
        return ErrorCode.EC1
    return ErrorCode.EC1  # Default to network failure


def sanitize_text_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize user text input:
    - Strip leading/trailing whitespace
    - Remove null bytes
    - Truncate to max_length
    - HTML-escape for display contexts
    """
    if not text:
        return ""
    # Remove null bytes and control characters
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\r\t")
    # Normalize unicode whitespace — collapse 3+ newlines to 2
    text = _re.sub(r"\n{3,}", "\n\n", text)
    # Truncate
    text = text[:max_length]
    return text.strip()


ROOT_DIR = Path(__file__).parent.resolve()
env_path = ROOT_DIR / '.env'
print(f"LOADING ENV FROM: {env_path}")
load_dotenv(env_path, override=True)

# Verify critical env vars
if not os.environ.get("GOOGLE_CLIENT_ID"):
    print(f"WARNING: GOOGLE_CLIENT_ID NOT FOUND in env. Keys loaded: {[k for k in os.environ.keys() if 'GOOGLE' in k]}")
else:
    print(f"SUCCESS: Loaded GOOGLE_CLIENT_ID: {os.environ.get('GOOGLE_CLIENT_ID')[:10]}...")

print(f"TWITTER_REDIRECT_URI: {os.environ.get('TWITTER_REDIRECT_URI')}")

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=25,           # Max connections per API instance
    minPoolSize=2,            # Keep minimum alive
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=30000,
)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 720))

# Frontend URL
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Uploads Configuration
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# ── Upload Backpressure (Addendum Section B.7) ────────────────────────────────
# Per-plan concurrent upload limits
UPLOAD_LIMITS = {
    "starter": 3,
    "pro": 5,
    "agency": 10,
    "enterprise": 20,
    "free": 2,
    "active": 5,   # default for any active subscription
}
GLOBAL_QUEUE_LIMIT = 200  # Max pending uploads across all users

# In-memory counter (for single-instance deployments)
# At scale: replace with Redis INCR/DECR (see Phase 2.8)
import threading as _threading
_upload_counters: dict = {}
_upload_lock = _threading.Lock()


def _get_upload_limit(user) -> int:
    plan = getattr(user, "subscription_plan", None) or getattr(user, "subscription_status", "free")
    return UPLOAD_LIMITS.get(plan, UPLOAD_LIMITS["free"])


def _increment_upload_counter(user_id: str) -> int:
    with _upload_lock:
        _upload_counters[user_id] = _upload_counters.get(user_id, 0) + 1
        return _upload_counters[user_id]


def _decrement_upload_counter(user_id: str):
    with _upload_lock:
        val = _upload_counters.get(user_id, 1) - 1
        _upload_counters[user_id] = max(0, val)


def _get_global_queue_depth() -> int:
    with _upload_lock:
        return sum(_upload_counters.values())


async def _handle_upload(file: UploadFile):
    """Internal helper to handle file uploads."""
    file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
    unique_filename = f"{uuid.uuid4()}.{file_ext}"
    
    file_path = UPLOADS_DIR / unique_filename
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    return f"/uploads/{unique_filename}"

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()

# Resend Email
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Stripe
stripe_api_key = os.environ.get('STRIPE_API_KEY')

# Razorpay
razorpay_key_id = os.environ.get('RAZORPAY_KEY_ID', '')
razorpay_key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
razorpay_client = None
if razorpay_key_id and razorpay_key_secret:
    razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

# PayPal
paypal_client_id = os.environ.get('PAYPAL_CLIENT_ID')
paypal_secret = os.environ.get('PAYPAL_SECRET')
paypal_client = None
if paypal_client_id and paypal_secret:
    # environment = SandboxEnvironment(client_id=paypal_client_id, client_secret=paypal_secret)
    # paypal_client = PayPalHttpClient(environment)
    pass

# APScheduler for scheduled posts
scheduler = AsyncIOScheduler()

# Create the main app
app = FastAPI(title="Social Scheduler API")
api_router = APIRouter(prefix="/api")

# ── Rate Limiting (Stage 3) ────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Security Headers (Stage 3.6) ─────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Only add HSTS in production
    if os.environ.get("ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# CORS Configuration (Stage 3 — environment-aware)
_cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:9500,http://127.0.0.1:3000,http://127.0.0.1:9500")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
# Always include FRONTEND_URL if not already present
if FRONTEND_URL and FRONTEND_URL not in _cors_origins:
    _cors_origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import uuid as _uuid

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Attach a trace_id to every request for cross-service correlation."""
    trace_id = request.headers.get("X-Trace-ID") or str(_uuid.uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Initialize Firebase Admin
try:
    service_account_path = os.path.join(ROOT_DIR, 'serviceAccountKey.json')
    fb_options = {}
    bucket_env = os.environ.get('FIREBASE_STORAGE_BUCKET')
    if bucket_env:
        fb_options['storageBucket'] = bucket_env

    if os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred, fb_options) if fb_options else firebase_admin.initialize_app(cred)
        logging.info("Firebase Admin initialized with service account")
    else:
        # No service account key — initialize with project ID only.
        # Sufficient for verify_id_token (uses Google public keys).
        project_id = 'socialentangler-b92a8'
        fb_options['projectId'] = project_id
        firebase_admin.initialize_app(options=fb_options)
        logging.info(f"Firebase Admin initialized with project ID only ({project_id})")
except Exception as e:
    logging.error(f"Failed to initialize Firebase Admin: {e}")

# Firebase project ID for token verification
FIREBASE_PROJECT_ID = 'socialentangler-b92a8'
_google_certs_cache: Dict[str, Any] = {}
_google_certs_expiry: float = 0.0

async def verify_firebase_token(id_token: str) -> dict:
    """
    Verify a Firebase ID token by fetching Google's public certs directly.
    Does not require Firebase Admin credentials.
    """
    import time
    global _google_certs_cache, _google_certs_expiry

    # Refresh certs if expired
    if time.time() > _google_certs_expiry:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
            )
            r.raise_for_status()
            _google_certs_cache = r.json()
            # Cache-Control max-age tells us when to refresh
            cc = r.headers.get("cache-control", "max-age=3600")
            max_age = 3600
            for part in cc.split(","):
                part = part.strip()
                if part.startswith("max-age="):
                    try:
                        max_age = int(part.split("=")[1])
                    except ValueError:
                        pass
            _google_certs_expiry = time.time() + max_age

    # Get the key ID from the token header
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    if not kid or kid not in _google_certs_cache:
        raise ValueError(f"Unknown key ID: {kid}")

    # Build RSA public key from the X.509 cert
    cert_pem = _google_certs_cache[kid].encode("utf-8")
    cert = load_pem_x509_certificate(cert_pem, default_backend())
    public_key = cert.public_key()

    # Decode and verify the JWT
    decoded = jwt.decode(
        id_token,
        public_key,
        algorithms=["RS256"],
        audience=FIREBASE_PROJECT_ID,
        issuer=f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}",
    )

    # Map Firebase claims to the shape firebase_auth.verify_id_token returns
    decoded.setdefault("uid", decoded.get("sub"))
    return decoded


# ==================== MODELS ====================

class UserSignup(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None
    email_verified: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    subscription_status: str = "free"
    subscription_plan: Optional[str] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    user_type: Optional[str] = None  # founder, creator, agency, enterprise, small_business, personal
    onboarding_completed: bool = False
    has_password: bool = False  # False for Google-authenticated users
    timezone: str = "UTC"  # IANA timezone string (e.g. "Asia/Kolkata"). Addendum B.6.

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class Post(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    content: str
    post_type: str = "text"  # text, image, video
    platforms: List[str]
    accounts: List[str] = []
    media_urls: Optional[List[str]] = []
    media_alt_texts: Optional[List[str]] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_privacy: Optional[str] = "public"
    scheduled_time: Optional[datetime] = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    ai_generated: bool = False
    # Instagram specific fields
    instagram_post_format: Optional[str] = "Post"
    instagram_first_comment: Optional[str] = None
    instagram_location: Optional[str] = None
    instagram_shop_grid_link: Optional[str] = None
    recurring_rule_id: Optional[str] = None
    rejection_note: Optional[str] = None
    thread_tweets: Optional[List[Dict[str, Any]]] = None  # [{content, media_url, id}]
    internal_notes: Optional[List[Dict[str, Any]]] = []   # [{id, text, created_at}]
    linkedin_document_url: Optional[str] = None
    linkedin_document_title: Optional[str] = None
    tiktok_privacy: Optional[str] = "public"
    tiktok_allow_duet: Optional[bool] = True
    tiktok_allow_stitch: Optional[bool] = True
    tiktok_allow_comments: Optional[bool] = True

    # Per-platform publish results (Stage 1.6 — independent execution)
    platform_results: Optional[Dict[str, Any]] = None
    # e.g. {"instagram": {"status": "published", "post_id": "123", "published_at": "..."},
    #        "facebook": {"status": "failed", "error": "...", "retry_count": 0}}

    # Status history for audit trail
    # status values include: draft, scheduled, processing, published, partial, failed
    status_history: Optional[List[Dict[str, Any]]] = None
    # e.g. [{"status": "scheduled", "at": "...", "note": "..."},
    #        {"status": "published", "at": "...", "note": "Published to instagram, facebook"}]

class PostCreate(BaseModel):
    content: str
    post_type: str = "text"
    platforms: List[str]
    accounts: List[str] = []
    media_urls: Optional[List[str]] = []
    media_alt_texts: Optional[List[str]] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_privacy: Optional[str] = "public"
    cover_image: Optional[str] = None
    scheduled_time: Optional[str] = None
    thread_tweets: Optional[List[Dict[str, Any]]] = None  # [{content, media_url, id}]
    # Instagram specific fields
    instagram_post_format: Optional[str] = "Post"
    instagram_first_comment: Optional[str] = None
    instagram_location: Optional[str] = None
    instagram_shop_grid_link: Optional[str] = None
    linkedin_document_url: Optional[str] = None
    linkedin_document_title: Optional[str] = None
    tiktok_privacy: Optional[str] = "public"
    tiktok_allow_duet: Optional[bool] = True
    tiktok_allow_stitch: Optional[bool] = True
    tiktok_allow_comments: Optional[bool] = True

class PostUpdate(BaseModel):
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    accounts: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    media_alt_texts: Optional[List[str]] = None
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_privacy: Optional[str] = None
    cover_image: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None
    # Instagram specific fields
    instagram_post_format: Optional[str] = None
    instagram_first_comment: Optional[str] = None
    instagram_location: Optional[str] = None
    instagram_shop_grid_link: Optional[str] = None
    linkedin_document_url: Optional[str] = None
    linkedin_document_title: Optional[str] = None
    tiktok_privacy: Optional[str] = None
    tiktok_allow_duet: Optional[bool] = None
    tiktok_allow_stitch: Optional[bool] = None
    tiktok_allow_comments: Optional[bool] = None

class HashtagGroupCreate(BaseModel):
    name: str
    hashtags: List[str]

class HashtagGroupUpdate(BaseModel):
    name: Optional[str] = None
    hashtags: Optional[List[str]] = None

class RecurringRuleCreate(BaseModel):
    content: str
    platforms: List[str]
    accounts: List[str] = []
    post_type: str = "text"
    media_urls: Optional[List[str]] = []
    frequency: str = "weekly"      # daily | weekly | monthly
    days_of_week: List[int] = [1]  # JS convention: 0=Sun … 6=Sat (weekly only)
    day_of_month: int = 1          # 1-28 (monthly only)
    time_of_day: str = "09:00"     # HH:MM UTC

class RecurringRuleUpdate(BaseModel):
    status: Optional[str] = None       # active | paused
    content: Optional[str] = None
    frequency: Optional[str] = None
    days_of_week: Optional[List[int]] = None
    day_of_month: Optional[int] = None
    time_of_day: Optional[str] = None

class CalendarNoteCreate(BaseModel):
    date: str          # YYYY-MM-DD
    text: str
    color: str = "green"  # green | blue | yellow | red

class CalendarNoteUpdate(BaseModel):
    text: Optional[str] = None
    color: Optional[str] = None

class ApiKey(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    key_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None

class ApiKeyCreate(BaseModel):
    name: str

class AIContentRequest(BaseModel):
    prompt: str
    platform: Optional[str] = None

class Notification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    post_id: str
    type: str  # "success" or "error"
    message: str
    is_read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SocialAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    platform: str
    platform_user_id: Optional[str] = None
    platform_username: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    is_active: bool = True
    picture_url: Optional[str] = None
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SocialAccountConnect(BaseModel):
    platform: str
    platform_username: str

class PaymentTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    session_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount: float
    currency: str
    plan: str
    payment_method: str
    payment_status: str = "pending"
    metadata: Optional[Dict[str, Any]] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CheckoutRequest(BaseModel):
    plan: str
    payment_method: str

class RazorpayVerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str

class PayPalCaptureBody(BaseModel):
    order_id: str

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GoogleAuthCallback(BaseModel):
    session_id: str

# ==================== AUTH UTILITIES ====================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def generate_verification_token() -> str:
    return str(uuid.uuid4())

async def get_current_user_from_cookie(session_token: Optional[str] = Cookie(None)) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    # Check session in database
    session_doc = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    
    # Check expiry
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    
    # Get user
    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Parse dates
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
    if user_doc.get('subscription_status') == 'active' and user_doc.get('subscription_end_date'):
        end_date = user_doc['subscription_end_date']
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        if end_date < datetime.now(timezone.utc):
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"subscription_status": "expired"}}
            )
            user_doc['subscription_status'] = "expired"

    if user_doc.get('subscription_status') == 'active' and user_doc.get('subscription_end_date'):
        end_date = user_doc['subscription_end_date']
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        
        if end_date < datetime.now(timezone.utc):
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"subscription_status": "expired"}}
            )
            user_doc['subscription_status'] = "expired"

    return User(**user_doc)

def generate_api_key():
    """Generate a random URL-safe API key."""
    import secrets
    return f"se_{secrets.token_urlsafe(32)}"

def hash_api_key(key: str):
    """Hash an API key using SHA-256."""
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()

async def get_api_key_user(x_api_key: str = Header(None)) -> User:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API Key required")
    
    key_hash = hash_api_key(x_api_key)
    api_key_doc = await db.api_keys.find_one({"key_hash": key_hash})
    if not api_key_doc:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    user_id = api_key_doc["user_id"]
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Update last used
    await db.api_keys.update_one(
        {"_id": api_key_doc["_id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc)}}
    )
    
    return User(**user)

async def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    # 1. Check for Authorization Header (Bearer Token)
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.replace("Bearer ", "")
    user_doc = None

    # 2. Try to verify as Firebase ID Token first
    try:
        decoded_token = await verify_firebase_token(token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')

        if not email:
            raise ValueError("No email in token")

        # Fetch user by Firebase UID
        user_doc = await db.users.find_one({"user_id": uid})

        if not user_doc:
            # Check by email and merge if needed
            existing = await db.users.find_one({"email": email})
            if existing:
                logging.info(f"Merging legacy user {existing['user_id']} with Firebase UID {uid}")
                await db.users.update_one({"email": email}, {"$set": {"user_id": uid}})
                await db.posts.update_many({"user_id": existing["user_id"]}, {"$set": {"user_id": uid}})
                await db.social_accounts.update_many({"user_id": existing["user_id"]}, {"$set": {"user_id": uid}})
                await db.payment_transactions.update_many({"user_id": existing["user_id"]}, {"$set": {"user_id": uid}})
                user_doc = existing
                user_doc["user_id"] = uid
            else:
                # Create new user
                user_doc = {
                    "user_id": uid,
                    "email": email,
                    "name": decoded_token.get('name', 'User'),
                    "picture": decoded_token.get('picture'),
                    "email_verified": decoded_token.get('email_verified', False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "subscription_status": "free",
                    "onboarding_completed": False,
                    "timezone": "UTC",
                }
                await db.users.insert_one(user_doc)
    except (jwt.InvalidTokenError, ValueError) as firebase_error:
        logging.debug(f"Firebase token verification failed: {firebase_error}, trying JWT fallback")

        # 3. Fallback to JWT token verification
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: No user_id")

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except Exception as e:
            logging.error(f"JWT verification failed: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception as e:
        logging.error(f"Auth error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")

    # 4. Process user_doc
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Parse dates
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])

    # Check subscription expiry
    if user_doc.get('subscription_status') == 'active' and user_doc.get('subscription_end_date'):
        end_date = user_doc['subscription_end_date']
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        if end_date < datetime.now(timezone.utc):
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"subscription_status": "expired"}}
            )
            user_doc['subscription_status'] = "expired"

    return User(**user_doc)

async def send_verification_email(email: str, verification_token: str):
    """Send email verification link"""
    if not RESEND_API_KEY:
        logging.warning("RESEND_API_KEY not set, skipping email")
        return
    
    verification_url = f"{FRONTEND_URL}/verify-email?token={verification_token}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{ display: inline-block; padding: 12px 24px; background: #6366F1; color: white; text-decoration: none; border-radius: 6px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Verify Your Email</h2>
            <p>Thank you for signing up! Please click the button below to verify your email address:</p>
            <p><a href="{verification_url}" class="button">Verify Email</a></p>
            <p>Or copy and paste this link: {verification_url}</p>
            <p>This link will expire in 24 hours.</p>
        </div>
    </body>
    </html>
    """
    
    params = {
        "from": SENDER_EMAIL,
        "to": [email],
        "subject": "Verify your email - SocialEntangler",
        "html": html_content
    }
    
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logging.info(f"Verification email sent to {email}")
    except Exception as e:
        logging.error(f"Failed to send verification email: {e}")

async def send_team_invite_email(invite_email: str, owner_name: str, role: str, invite_token: str, expires_at) -> bool:
    """Send team invitation email via Resend. Returns True if sent, False otherwise."""
    if not RESEND_API_KEY:
        logging.warning("RESEND_API_KEY not set, skipping team invite email")
        return False

    accept_url = f"{FRONTEND_URL}/accept-invite?token={invite_token}"

    if isinstance(expires_at, str):
        from datetime import datetime as _dt
        expires_at = _dt.fromisoformat(expires_at)
    expiry_str = expires_at.strftime("%B %d, %Y")

    role_info = {
        "admin":  ("Admin",  "manage team members, connect social accounts, create and publish posts"),
        "member": ("Member", "create, edit, and schedule posts for publication"),
        "viewer": ("Viewer", "view scheduled posts and analytics"),
    }
    role_label, role_capability = role_info.get(role, ("Member", "access the workspace"))
    safe_owner = _html.escape(owner_name)
    safe_role_label = _html.escape(role_label)
    safe_role_cap = _html.escape(role_capability)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background:#f5f7f5; margin:0; padding:0; }}
    .wrap {{ max-width:600px; margin:40px auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
    .hdr {{ background:linear-gradient(135deg,#6366f1,#8b5cf6); padding:36px 48px 28px; text-align:center; }}
    .hdr-logo {{ font-size:20px; font-weight:700; color:#fff; letter-spacing:-0.5px; }}
    .hdr h1 {{ color:#fff; font-size:26px; font-weight:600; margin:12px 0 0; }}
    .body {{ padding:36px 48px; }}
    .card {{ background:#f8f9ff; border:1px solid #e5e7fb; border-radius:12px; padding:20px 24px; margin:20px 0; }}
    .lbl {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:#8a8fa8; margin-bottom:3px; }}
    .val {{ font-size:15px; font-weight:600; color:#1a1a2e; }}
    .badge {{ display:inline-block; padding:3px 12px; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff; border-radius:20px; font-size:13px; font-weight:600; }}
    .cap {{ font-size:13px; color:#6b7280; margin-top:6px; }}
    .cta-wrap {{ text-align:center; margin:28px 0; }}
    .cta {{ display:inline-block; padding:15px 40px; background:linear-gradient(135deg,#6366f1,#8b5cf6); color:#fff !important; text-decoration:none; border-radius:12px; font-size:15px; font-weight:700; }}
    .exp {{ text-align:center; font-size:12px; color:#9ca3af; margin-top:8px; }}
    .link-wrap {{ font-size:12px; color:#9ca3af; line-height:1.6; }}
    .link-wrap a {{ color:#6366f1; word-break:break-all; }}
    .ftr {{ background:#f8f9ff; padding:20px 48px; border-top:1px solid #e5e7fb; }}
    .ftr p {{ font-size:12px; color:#9ca3af; line-height:1.6; margin:0; }}
    .ftr a {{ color:#6366f1; text-decoration:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hdr">
      <div class="hdr-logo">SocialEntangler</div>
      <h1>You're invited to a workspace</h1>
    </div>
    <div class="body">
      <p style="font-size:15px;line-height:1.7;color:#4b5563;">
        <strong>{safe_owner}</strong> has invited you to collaborate on their
        SocialEntangler workspace.
      </p>
      <div class="card">
        <div class="lbl">Invited by</div>
        <div class="val">{safe_owner}</div>
        <div style="height:12px;"></div>
        <div class="lbl">Your role</div>
        <div class="val"><span class="badge">{safe_role_label}</span></div>
        <div class="cap">As {safe_role_label}, you can {safe_role_cap}.</div>
      </div>
      <div class="cta-wrap">
        <a href="{accept_url}" class="cta">Accept Invitation</a>
        <p class="exp">This invitation expires on {expiry_str}</p>
      </div>
      <p class="link-wrap">
        Or copy and paste this link:<br>
        <a href="{accept_url}">{accept_url}</a>
      </p>
    </div>
    <div class="ftr">
      <p>If you didn't expect this invitation, you can safely ignore this email. Your account will not be affected.</p>
    </div>
  </div>
</body>
</html>"""

    params = {
        "from": SENDER_EMAIL,
        "to": [invite_email],
        "subject": f"{owner_name} invited you to their SocialEntangler workspace",
        "html": html_content,
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logging.info(f"Team invite email sent to {invite_email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send team invite email: {e}")
        return False

async def send_approval_request_email(approver_email: str, approver_name: str, owner_name: str,
                                       post_content: str, post_id: str):
    """Email sent to can_approve team members when a post is submitted for review."""
    if not RESEND_API_KEY:
        return
    review_url = f"{FRONTEND_URL}/approvals"
    preview = _html.escape((post_content or "")[:200] + ("…" if len(post_content or "") > 200 else ""))
    safe_approver = _html.escape(approver_name)
    safe_owner = _html.escape(owner_name)
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{{font-family:'Helvetica Neue',Arial,sans-serif;background:#f5f7f5;margin:0;padding:0;}}
  .wrap{{max-width:580px;margin:40px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);}}
  .hdr{{background:linear-gradient(135deg,#f59e0b,#d97706);padding:32px 40px 24px;}}
  .hdr-logo{{font-size:18px;font-weight:700;color:#fff;}}
  .hdr h1{{color:#fff;font-size:22px;font-weight:600;margin:10px 0 0;}}
  .body{{padding:32px 40px;}}
  .preview{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 16px;margin:16px 0;font-size:14px;color:#78350f;line-height:1.6;white-space:pre-line;}}
  .cta-wrap{{text-align:center;margin:24px 0;}}
  .cta{{display:inline-block;padding:13px 36px;background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff!important;text-decoration:none;border-radius:10px;font-size:15px;font-weight:700;}}
  .ftr{{background:#f8f9ff;padding:18px 40px;border-top:1px solid #e5e7fb;}}
  .ftr p{{font-size:12px;color:#9ca3af;margin:0;}}
</style>
</head><body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-logo">SocialEntangler</div>
    <h1>Post awaiting your review</h1>
  </div>
  <div class="body">
    <p style="font-size:15px;line-height:1.7;color:#4b5563;">
      Hi <strong>{safe_approver}</strong>,<br>
      <strong>{safe_owner}</strong> has submitted a post for your review.
    </p>
    <div class="preview">{preview}</div>
    <div class="cta-wrap">
      <a href="{review_url}" class="cta">Review Post</a>
    </div>
  </div>
  <div class="ftr"><p>You're receiving this because you have post approval permissions in this workspace.</p></div>
</div>
</body></html>"""
    params = {"from": SENDER_EMAIL, "to": [approver_email],
               "subject": f"{owner_name} submitted a post for your review — SocialEntangler",
               "html": html_content}
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logging.error(f"Failed to send approval request email: {e}")

async def send_approval_result_email(owner_email: str, owner_name: str, reviewer_name: str,
                                      post_content: str, approved: bool, rejection_note: str = None):
    """Email sent to the post owner when their post is approved or rejected."""
    if not RESEND_API_KEY:
        return
    post_url = f"{FRONTEND_URL}/approvals"
    preview = _html.escape((post_content or "")[:200] + ("…" if len(post_content or "") > 200 else ""))
    safe_reviewer = _html.escape(reviewer_name)
    safe_owner_name = _html.escape(owner_name)
    if approved:
        accent = "#10b981"; icon = "✓"; headline = "Your post was approved!"
        body_text = f"<strong>{safe_reviewer}</strong> approved your post. It's now scheduled."
        extra = ""
    else:
        accent = "#ef4444"; icon = "✗"; headline = "Your post needs changes"
        body_text = f"<strong>{safe_reviewer}</strong> rejected your post."
        safe_note = _html.escape(rejection_note) if rejection_note else ""
        note_html = f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:12px 16px;margin:12px 0;font-size:14px;color:#991b1b;"><strong>Reason:</strong> {safe_note}</div>' if safe_note else ""
        extra = note_html
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{{font-family:'Helvetica Neue',Arial,sans-serif;background:#f5f7f5;margin:0;padding:0;}}
  .wrap{{max-width:580px;margin:40px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);}}
  .hdr{{background:{accent};padding:32px 40px 24px;}}
  .hdr-logo{{font-size:18px;font-weight:700;color:#fff;}}
  .hdr h1{{color:#fff;font-size:22px;font-weight:600;margin:10px 0 0;}}
  .body{{padding:32px 40px;}}
  .preview{{background:#f8f9ff;border:1px solid #e5e7fb;border-radius:10px;padding:14px 16px;margin:16px 0;font-size:14px;color:#374151;line-height:1.6;white-space:pre-line;}}
  .cta{{display:inline-block;padding:13px 36px;background:{accent};color:#fff!important;text-decoration:none;border-radius:10px;font-size:14px;font-weight:700;}}
  .ftr{{background:#f8f9ff;padding:18px 40px;border-top:1px solid #e5e7fb;}}
  .ftr p{{font-size:12px;color:#9ca3af;margin:0;}}
</style>
</head><body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-logo">SocialEntangler</div>
    <h1>{icon} {headline}</h1>
  </div>
  <div class="body">
    <p style="font-size:15px;line-height:1.7;color:#4b5563;">Hi <strong>{safe_owner_name}</strong>, {body_text}</p>
    {extra}
    <div class="preview">{preview}</div>
    <p style="text-align:center;margin-top:20px;"><a href="{post_url}" class="cta">View in SocialEntangler</a></p>
  </div>
  <div class="ftr"><p>You're receiving this because a team member reviewed your post.</p></div>
</div>
</body></html>"""
    subject = f"{'✓ Post approved' if approved else '✗ Post needs changes'} — SocialEntangler"
    params = {"from": SENDER_EMAIL, "to": [owner_email], "subject": subject, "html": html_content}
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logging.error(f"Failed to send approval result email: {e}")

async def send_mention_email(mentioned_email: str, mentioned_name: str, author_name: str,
                              post_content: str, note_text: str):
    """Email sent when a team member is @mentioned in an internal note."""
    if not RESEND_API_KEY:
        return
    post_url = f"{FRONTEND_URL}/content"
    preview = _html.escape((post_content or "")[:120] + ("…" if len(post_content or "") > 120 else ""))
    safe_mentioned = _html.escape(mentioned_name)
    safe_author = _html.escape(author_name)
    safe_note = _html.escape(note_text)
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body{{font-family:'Helvetica Neue',Arial,sans-serif;background:#f5f7f5;margin:0;padding:0;}}
  .wrap{{max-width:580px;margin:40px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);}}
  .hdr{{background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px 40px 24px;}}
  .hdr-logo{{font-size:18px;font-weight:700;color:#fff;}}
  .hdr h1{{color:#fff;font-size:22px;font-weight:600;margin:10px 0 0;}}
  .body{{padding:32px 40px;}}
  .mention-box{{background:#eef2ff;border:1px solid #c7d2fe;border-radius:10px;padding:14px 16px;margin:16px 0;font-size:14px;color:#3730a3;line-height:1.6;}}
  .post-preview{{background:#f8f9ff;border:1px solid #e5e7fb;border-radius:10px;padding:12px 16px;margin:12px 0;font-size:13px;color:#6b7280;}}
  .cta{{display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff!important;text-decoration:none;border-radius:10px;font-size:14px;font-weight:700;}}
  .ftr{{background:#f8f9ff;padding:18px 40px;border-top:1px solid #e5e7fb;}}
  .ftr p{{font-size:12px;color:#9ca3af;margin:0;}}
</style>
</head><body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-logo">SocialEntangler</div>
    <h1>@ {safe_author} mentioned you</h1>
  </div>
  <div class="body">
    <p style="font-size:15px;line-height:1.7;color:#4b5563;">
      Hi <strong>{safe_mentioned}</strong>,<br>
      <strong>{safe_author}</strong> mentioned you in a note on a post.
    </p>
    <div class="mention-box">{safe_note}</div>
    <p style="font-size:13px;color:#6b7280;margin-bottom:4px;">On post:</p>
    <div class="post-preview">{preview}</div>
    <p style="text-align:center;margin-top:20px;"><a href="{post_url}" class="cta">View Post</a></p>
  </div>
  <div class="ftr"><p>You're receiving this because you were mentioned in an internal note.</p></div>
</div>
</body></html>"""
    params = {"from": SENDER_EMAIL, "to": [mentioned_email],
               "subject": f"{author_name} mentioned you in a note — SocialEntangler",
               "html": html_content}
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logging.error(f"Failed to send mention email: {e}")

# ==================== AUTH ROUTES ====================

@limiter.limit("5/minute")
@api_router.post("/auth/signup", response_model=Token)
async def signup(request: Request, user_data: UserSignup):
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    verification_token = generate_verification_token()
    
    user = User(
        user_id=user_id,
        email=user_data.email,
        name=user_data.name,
        email_verified=False
    )
    
    user_dict = user.model_dump()
    user_dict['password'] = hash_password(user_data.password)
    user_dict['verification_token'] = verification_token
    user_dict['verification_expires'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    
    await db.users.insert_one(user_dict)
    
    # Send verification email
    await send_verification_email(user_data.email, verification_token)
    
    access_token = create_access_token({"sub": user.user_id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user=user.model_dump(mode='json')
    )

@api_router.get("/auth/verify-email")
async def verify_email(token: str):
    user_doc = await db.users.find_one({"verification_token": token})
    if not user_doc:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    
    # Check expiry
    expires = datetime.fromisoformat(user_doc['verification_expires'])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification token expired")
    
    # Update user
    await db.users.update_one(
        {"user_id": user_doc['user_id']},
        {"$set": {
            "email_verified": True,
            "verification_token": None,
            "verification_expires": None
        }}
    )
    
    return {"message": "Email verified successfully"}

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
from fastapi.responses import JSONResponse, RedirectResponse

# ... (imports remain)

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
# Replaced proxy callback with direct Google OAuth flow

@api_router.get("/auth/google/login")
async def google_login():
    """Initiate Google Login flow"""
    google_auth = GoogleAuth()
    state = str(uuid.uuid4())
    # In a real app, store state in cookie/session to verify CSRF
    return RedirectResponse(url=google_auth.get_login_url(state))

@api_router.get("/auth/google/callback")
async def google_auth_callback(code: str, state: Optional[str] = None):
    """Handle Google OAuth callback directly"""
    try:
        google_auth = GoogleAuth()
        
        # 1. Exchange code for token
        token_data = await google_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        
        # 2. Get User Info
        user_info = await google_auth.get_user_info(access_token)
        email = user_info.get('email')
        
        if not email:
            raise HTTPException(status_code=400, detail="No email provided by Google")
            
        # 3. Check or Create User
        user_doc = await db.users.find_one({"email": email}, {"_id": 0})
        
        if user_doc:
            # Update existing user — never overwrite name/picture the user may have customised
            user_id = user_doc["user_id"]
            update_data: dict = {"email_verified": True}

            # Only set name from Google if user has no name stored yet
            if not user_doc.get("name") and user_info.get("name"):
                update_data["name"] = user_info["name"]

            # Only set picture from Google if user hasn't uploaded a custom one.
            # Custom uploads are stored as /uploads/... paths; Google URLs start with https://
            current_picture = user_doc.get("picture") or ""
            google_picture = user_info.get("picture")
            if google_picture and not current_picture.startswith("/uploads/"):
                update_data["picture"] = google_picture

            await db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
        else:
            # Create new user
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            new_user = {
                "user_id": user_id,
                "email": email,
                "name": user_info.get("name", "User"),
                "picture": user_info.get("picture"),
                "email_verified": True,
                "subscription_status": "free",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.users.insert_one(new_user)
        
        # 4. Create JWT Access Token
        access_token = create_access_token({"sub": user_id, "email": email})

        # 5. Redirect to Frontend with Token
        redirect_url = f"{FRONTEND_URL}/auth/callback?token={access_token}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logging.error(f"Google auth error: {e}")
        # Redirect to login with error
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_failed")


@limiter.limit("10/minute")
@api_router.post("/auth/login", response_model=Token)
async def login(request: Request, credentials: UserLogin):
    user_doc = await db.users.find_one({"email": credentials.email})
    if not user_doc or 'password' not in user_doc:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if not verify_password(credentials.password, user_doc['password']):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
    
    user = User(**{k: v for k, v in user_doc.items() if k not in ['password', '_id']})
    access_token = create_access_token({"sub": user.user_id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user=user.model_dump(mode='json')
    )

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    # Look up raw doc to compute has_password
    raw = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    has_pw = bool(raw and raw.get("password"))
    user_dict = current_user.model_dump()
    user_dict["has_password"] = has_pw
    return User(**user_dict)

@api_router.patch("/auth/me", response_model=User)
async def update_me(
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update current user profile"""
    # Filter allowed fields
    allowed_fields = ['user_type', 'onboarding_completed', 'name', 'picture', 'timezone']
    update_fields = {k: v for k, v in update_data.items() if k in allowed_fields}

    if not update_fields:
        return current_user

    # Validate timezone if provided
    if "timezone" in update_fields:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(update_fields["timezone"])
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {update_fields['timezone']}")

    # Update in database
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": update_fields}
    )

    # Get updated user
    updated_user = await db.users.find_one({"user_id": current_user.user_id})
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return User(**updated_user)

@api_router.post("/auth/profile-photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a profile photo (max 1 MB). Returns the new picture URL."""
    # Read content to check size
    content = await file.read()
    if len(content) > 1 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 1 MB.")

    # Allowed image types
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, GIF, or WebP images are allowed.")

    # Save file
    file_ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg").lower()
    unique_filename = f"avatar_{current_user.user_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    file_path = UPLOADS_DIR / unique_filename
    with open(file_path, "wb") as buf:
        buf.write(content)
    picture_url = f"/uploads/{unique_filename}"

    # Update user record
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"picture": picture_url}}
    )
    return {"picture": picture_url}

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@api_router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user)
):
    """Change password for email/password accounts. Not available for Google-authenticated users."""
    # Fetch raw user doc (includes hashed password)
    user_doc = await db.users.find_one({"user_id": current_user.user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    if "password" not in user_doc:
        raise HTTPException(status_code=400, detail="Password change is not available for accounts signed in with Google.")

    if not verify_password(body.old_password, user_doc["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")

    new_hash = hash_password(body.new_password)
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"password": new_hash}}
    )
    return {"message": "Password updated successfully."}

@api_router.post("/auth/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    return {"message": "Logged out successfully"}

# Continued in next part...

# ==================== POST ROUTES ====================

@limiter.limit("60/minute")
@api_router.post("/posts", response_model=Post)
async def create_post(request: Request, post_data: PostCreate, current_user: User = Depends(get_current_user)):
    if post_data.scheduled_time and current_user.subscription_status != "active":
        raise api_error(
            403, StructuredErrorCode.POST_SCHEDULE_REQUIRES_SUB,
            "Active subscription required to schedule posts. Free users can save drafts only."
        )
    
    scheduled_time = None
    status = "draft"
    if post_data.scheduled_time:
        scheduled_time = datetime.fromisoformat(post_data.scheduled_time.replace('Z', '+00:00'))
        status = "scheduled"
    
    post = Post(
        user_id=current_user.user_id,
        content=post_data.content,
        post_type=post_data.post_type,
        platforms=post_data.platforms,
        accounts=post_data.accounts,
        media_urls=post_data.media_urls or [],
        video_url=post_data.video_url,
        cover_image_url=post_data.cover_image_url or post_data.cover_image,
        video_title=post_data.video_title,
        youtube_title=post_data.youtube_title,
        youtube_privacy=post_data.youtube_privacy,
        scheduled_time=scheduled_time,
        status=status,
        # Instagram specific fields
        instagram_post_format=post_data.instagram_post_format,
        instagram_first_comment=post_data.instagram_first_comment,
        instagram_location=post_data.instagram_location,
        instagram_shop_grid_link=post_data.instagram_shop_grid_link,
        thread_tweets=post_data.thread_tweets,
    )
    
    post_dict = post.model_dump()
    post_dict['created_at'] = post_dict['created_at'].isoformat()
    if post_dict.get('scheduled_time'):
        post_dict['scheduled_time'] = post_dict['scheduled_time'].isoformat()
    
    await db.posts.insert_one(post_dict)
    return post



@api_router.get("/posts", response_model=List[Post])
async def get_posts(current_user: User = Depends(get_current_user), status: Optional[str] = None, search: Optional[str] = None):
    query = {"user_id": current_user.user_id}
    if status:
        query["status"] = status
    if search:
        query["content"] = {"$regex": search, "$options": "i"}
    
    posts = await db.posts.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    for post in posts:
        if isinstance(post.get('created_at'), str):
            post['created_at'] = datetime.fromisoformat(post['created_at'])
        if post.get('scheduled_time') and isinstance(post['scheduled_time'], str):
            post['scheduled_time'] = datetime.fromisoformat(post['scheduled_time'])
        if post.get('published_at') and isinstance(post['published_at'], str):
            post['published_at'] = datetime.fromisoformat(post['published_at'])
    
    return posts

@api_router.get("/posts/{post_id}", response_model=Post)
async def get_post(post_id: str, current_user: User = Depends(get_current_user)):
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if isinstance(post.get('created_at'), str):
        post['created_at'] = datetime.fromisoformat(post['created_at'])
    if post.get('scheduled_time') and isinstance(post['scheduled_time'], str):
        post['scheduled_time'] = datetime.fromisoformat(post['scheduled_time'])
    if post.get('published_at') and isinstance(post['published_at'], str):
        post['published_at'] = datetime.fromisoformat(post['published_at'])
    
    return Post(**post)

@api_router.patch("/posts/{post_id}", response_model=Post)
async def update_post(post_id: str, post_data: PostUpdate, current_user: User = Depends(get_current_user)):
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    update_dict = {k: v for k, v in post_data.model_dump(exclude_unset=True).items() if v is not None}
    
    if 'scheduled_time' in update_dict and update_dict['scheduled_time']:
        update_dict['scheduled_time'] = datetime.fromisoformat(update_dict['scheduled_time'].replace('Z', '+00:00')).isoformat()
    
    if update_dict:
        await db.posts.update_one({"id": post_id}, {"$set": update_dict})
    
    updated_post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    
    if isinstance(updated_post.get('created_at'), str):
        updated_post['created_at'] = datetime.fromisoformat(updated_post['created_at'])
    if updated_post.get('scheduled_time') and isinstance(updated_post['scheduled_time'], str):
        updated_post['scheduled_time'] = datetime.fromisoformat(updated_post['scheduled_time'])
    if updated_post.get('published_at') and isinstance(updated_post['published_at'], str):
        updated_post['published_at'] = datetime.fromisoformat(updated_post['published_at'])
    
    return Post(**updated_post)

@api_router.delete("/posts/{post_id}")
async def delete_post(post_id: str, current_user: User = Depends(get_current_user)):
    result = await db.posts.delete_one({"id": post_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"message": "Post deleted"}

@api_router.post("/posts/{post_id}/duplicate", status_code=201)
async def duplicate_post(post_id: str, current_user: User = Depends(get_current_user)):
    original = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not original:
        raise HTTPException(status_code=404, detail="Post not found")
    duplicate = {
        **original,
        "id": str(uuid.uuid4()),
        "status": "draft",
        "scheduled_time": None,
        "published_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.posts.insert_one(duplicate)
    duplicate.pop("_id", None)
    return duplicate

# ==================== INTERNAL NOTES ====================

class NoteCreate(BaseModel):
    text: str

@api_router.post("/posts/{post_id}/notes", status_code=201)
async def add_internal_note(post_id: str, body: NoteCreate, current_user: User = Depends(get_current_user)):
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    note = {
        "id":           str(uuid.uuid4()),
        "text":         body.text.strip(),
        "author_id":    current_user.user_id,
        "author_name":  current_user.name,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    await db.posts.update_one(
        {"id": post_id, "user_id": current_user.user_id},
        {"$push": {"internal_notes": note}}
    )
    # Detect @mentions (format: @email or @Name) and send notifications (non-fatal)
    import re as _re
    mentioned_emails = _re.findall(r'@([\w.+-]+@[\w.-]+\.\w+)', body.text)
    if mentioned_emails:
        team_members = await db.team_members.find(
            {"owner_user_id": current_user.user_id, "status": "accepted",
             "email": {"$in": [e.lower() for e in mentioned_emails]}},
            {"email": 1, "member_user_id": 1}
        ).to_list(20)
        for tm in team_members:
            if tm["email"].lower() == current_user.email.lower():
                continue  # don't notify yourself
            member_user = await db.users.find_one({"user_id": tm.get("member_user_id")}, {"name": 1})
            mentioned_name = member_user.get("name", tm["email"]) if member_user else tm["email"]
            await send_mention_email(
                mentioned_email=tm["email"],
                mentioned_name=mentioned_name,
                author_name=current_user.name,
                post_content=post.get("content", ""),
                note_text=body.text.strip(),
            )
    return note

@api_router.delete("/posts/{post_id}/notes/{note_id}", status_code=200)
async def delete_internal_note(post_id: str, note_id: str, current_user: User = Depends(get_current_user)):
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.posts.update_one(
        {"id": post_id, "user_id": current_user.user_id},
        {"$pull": {"internal_notes": {"id": note_id}}}
    )
    return {"ok": True}

# ==================== DEAD LETTER QUEUE ====================

@api_router.get("/dlq")
async def get_dead_letter_queue(current_user: User = Depends(get_current_user)):
    """Get permanently failed posts for manual review."""
    items = await get_dlq_items(db, current_user.user_id)
    return {"items": items, "count": len(items)}


@api_router.post("/dlq/{post_id}/retry")
async def retry_dead_letter_post(post_id: str, current_user: User = Depends(get_current_user)):
    """Re-queue a DLQ post for retry."""
    result = await retry_from_dlq(db, post_id, current_user.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    return {"success": True, "message": "Post re-queued for publishing"}

# ==================== WORKSPACE / TEAMS (Stage 5.9) ====================
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceInvite, ROLE_PERMISSIONS, has_permission
import re as _workspace_re

class WorkspaceCreateRequest(BaseModel):
    name: str

class WorkspaceInviteRequest(BaseModel):
    email: str
    role: str = "viewer"

class WorkspaceMemberUpdateRequest(BaseModel):
    role: str

@api_router.get("/workspace")
async def get_my_workspace(current_user: User = Depends(get_current_user)):
    """Get the current user's primary workspace."""
    workspace = await db.workspaces.find_one(
        {"owner_id": current_user.user_id}, {"_id": 0}
    )
    if not workspace:
        # Auto-create personal workspace if missing
        import re as _re2, uuid as _uuid2
        slug_base = _re2.sub(r"[^a-z0-9]", "-", (current_user.name or "workspace").lower())[:20]
        slug = f"{slug_base}-{current_user.user_id[:8]}"
        workspace = {
            "id": str(_uuid2.uuid4()),
            "name": f"{current_user.name} Workspace",
            "slug": slug,
            "owner_id": current_user.user_id,
            "members": [{"user_id": current_user.user_id, "email": current_user.email,
                         "name": current_user.name, "role": "owner",
                         "joined_at": datetime.now(timezone.utc).isoformat()}],
            "plan": "starter",
            "subscription_status": current_user.subscription_status,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "settings": {},
            "max_members": 1,
            "max_accounts": 5,
            "max_scheduled_posts": 30,
        }
        await db.workspaces.insert_one(workspace)
        workspace.pop("_id", None)
    return workspace


@api_router.get("/workspace/members")
async def get_workspace_members(current_user: User = Depends(get_current_user)):
    """Get all members of the current user's workspace."""
    workspace = await db.workspaces.find_one({"owner_id": current_user.user_id}, {"_id": 0})
    if not workspace:
        return {"members": []}
    return {"members": workspace.get("members", []), "workspace_id": workspace.get("id")}


@api_router.post("/workspace/invite")
async def invite_workspace_member(
    invite_req: WorkspaceInviteRequest,
    current_user: User = Depends(get_current_user)
):
    """Invite a user to the workspace by email."""
    workspace = await db.workspaces.find_one({"owner_id": current_user.user_id})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check member limit
    current_member_count = len(workspace.get("members", []))
    max_members = workspace.get("max_members", 1)
    if current_member_count >= max_members:
        raise HTTPException(
            status_code=403,
            detail=f"Member limit reached ({max_members}). Upgrade your plan to add more members."
        )

    # Check if already invited
    existing = await db.workspace_invites.find_one({
        "workspace_id": workspace["id"],
        "invited_email": invite_req.email,
        "accepted": False,
    })
    if existing:
        raise HTTPException(status_code=409, detail="Invitation already sent to this email")

    invite = WorkspaceInvite(
        workspace_id=workspace["id"],
        workspace_name=workspace["name"],
        invited_email=invite_req.email,
        invited_by_id=current_user.user_id,
        invited_by_name=current_user.name,
        role=invite_req.role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    await db.workspace_invites.insert_one(invite.model_dump())

    # TODO: Send invite email via Resend
    logging.info(f"Workspace invite sent: {invite_req.email} to {workspace['name']} (token: {invite.token[:8]}...)")

    return {"success": True, "message": f"Invitation sent to {invite_req.email}", "invite_id": invite.id}


@api_router.get("/workspace/invite/{token}")
async def get_invite_details(token: str):
    """Get invite details by token (public endpoint for accept-invite page)."""
    invite = await db.workspace_invites.find_one({"token": token}, {"_id": 0})
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")
    if invite.get("accepted"):
        raise HTTPException(status_code=410, detail="Invitation already accepted")
    expiry = invite.get("expires_at")
    if expiry and datetime.fromisoformat(expiry) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation has expired")
    return invite


@api_router.post("/workspace/invite/{token}/accept")
async def accept_workspace_invite(token: str, current_user: User = Depends(get_current_user)):
    """Accept a workspace invitation."""
    invite = await db.workspace_invites.find_one({"token": token})
    if not invite or invite.get("accepted"):
        raise HTTPException(status_code=404, detail="Invitation not found or already accepted")

    if invite.get("invited_email") != current_user.email:
        raise HTTPException(status_code=403, detail="This invitation was sent to a different email address")

    # Add member to workspace
    new_member = {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "name": current_user.name,
        "role": invite.get("role", "viewer"),
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "invited_by": invite.get("invited_by_id"),
    }
    await db.workspaces.update_one(
        {"id": invite["workspace_id"]},
        {"$push": {"members": new_member}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await db.workspace_invites.update_one({"token": token}, {"$set": {"accepted": True}})

    return {"success": True, "message": "You've joined the workspace!", "workspace_id": invite["workspace_id"]}


@api_router.delete("/workspace/members/{member_user_id}")
async def remove_workspace_member(member_user_id: str, current_user: User = Depends(get_current_user)):
    """Remove a member from the workspace (owner only)."""
    workspace = await db.workspaces.find_one({"owner_id": current_user.user_id})
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if member_user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself (owner)")

    await db.workspaces.update_one(
        {"owner_id": current_user.user_id},
        {"$pull": {"members": {"user_id": member_user_id}},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Member removed"}

# ==================== HASHTAG GROUPS ====================

@api_router.get("/hashtag-groups")
async def get_hashtag_groups(current_user: User = Depends(get_current_user)):
    groups = await db.hashtag_groups.find(
        {"user_id": current_user.user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    return groups

@api_router.post("/hashtag-groups", status_code=201)
async def create_hashtag_group(data: HashtagGroupCreate, current_user: User = Depends(get_current_user)):
    group = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.user_id,
        "name": data.name,
        "hashtags": data.hashtags,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hashtag_groups.insert_one(group)
    group.pop("_id", None)
    return group

@api_router.patch("/hashtag-groups/{group_id}")
async def update_hashtag_group(group_id: str, data: HashtagGroupUpdate, current_user: User = Depends(get_current_user)):
    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if update:
        await db.hashtag_groups.update_one(
            {"id": group_id, "user_id": current_user.user_id},
            {"$set": update}
        )
    group = await db.hashtag_groups.find_one({"id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Hashtag group not found")
    return group

@api_router.delete("/hashtag-groups/{group_id}", status_code=204)
async def delete_hashtag_group(group_id: str, current_user: User = Depends(get_current_user)):
    result = await db.hashtag_groups.delete_one({"id": group_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Hashtag group not found")

# ==================== INBOX (COMMENTS / DMs) ====================

class InboxMessageCreate(BaseModel):
    platform: str
    type: str = "comment"         # comment | dm
    author_name: str
    author_avatar: Optional[str] = None
    content: str
    post_id: Optional[str] = None # linked post if comment
    platform_message_id: Optional[str] = None
    received_at: Optional[str] = None

@api_router.get("/inbox")
async def get_inbox(
    platform: Optional[str] = None,
    msg_type: Optional[str] = None,   # comment | dm
    status: Optional[str] = None,     # unread | read | replied
    current_user: User = Depends(get_current_user),
):
    query: dict = {"user_id": current_user.user_id}
    if platform:
        query["platform"] = platform
    if msg_type:
        query["type"] = msg_type
    if status:
        query["status"] = status
    messages = await db.inbox.find(query, {"_id": 0}).sort("received_at", -1).to_list(500)
    return messages

@api_router.post("/inbox", status_code=201)
async def create_inbox_message(body: InboxMessageCreate, current_user: User = Depends(get_current_user)):
    """Manually add a message (used by platform sync jobs or testing)."""
    msg = {
        "id":                    str(uuid.uuid4()),
        "user_id":               current_user.user_id,
        "platform":              body.platform,
        "type":                  body.type,
        "author_name":           body.author_name,
        "author_avatar":         body.author_avatar,
        "content":               body.content,
        "post_id":               body.post_id,
        "platform_message_id":   body.platform_message_id,
        "status":                "unread",
        "reply":                 None,
        "received_at":           body.received_at or datetime.now(timezone.utc).isoformat(),
        "replied_at":            None,
    }
    await db.inbox.insert_one(msg)
    msg.pop("_id", None)
    return msg

@api_router.patch("/inbox/{message_id}")
async def update_inbox_message(
    message_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Mark read/unread, add reply text."""
    update: dict = {}
    if "status" in body:
        update["status"] = body["status"]
    if "reply" in body:
        update["reply"] = body["reply"]
        update["replied_at"] = datetime.now(timezone.utc).isoformat()
        update["status"] = "replied"
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    result = await db.inbox.update_one(
        {"id": message_id, "user_id": current_user.user_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}

@api_router.delete("/inbox/{message_id}")
async def delete_inbox_message(message_id: str, current_user: User = Depends(get_current_user)):
    await db.inbox.delete_one({"id": message_id, "user_id": current_user.user_id})
    return {"ok": True}

@api_router.get("/inbox/stats")
async def get_inbox_stats(current_user: User = Depends(get_current_user)):
    total   = await db.inbox.count_documents({"user_id": current_user.user_id})
    unread  = await db.inbox.count_documents({"user_id": current_user.user_id, "status": "unread"})
    replied = await db.inbox.count_documents({"user_id": current_user.user_id, "status": "replied"})
    return {"total": total, "unread": unread, "replied": replied}

# ==================== CALENDAR NOTES ====================

@api_router.get("/calendar-notes")
async def get_calendar_notes(month: str, current_user: User = Depends(get_current_user)):
    """Get all notes for a given month. month format: YYYY-MM"""
    notes = await db.calendar_notes.find(
        {"user_id": current_user.user_id, "date": {"$regex": f"^{month}"}},
        {"_id": 0}
    ).to_list(1000)
    return notes

@api_router.post("/calendar-notes", status_code=201)
async def create_calendar_note(data: CalendarNoteCreate, current_user: User = Depends(get_current_user)):
    note = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.user_id,
        "date": data.date,
        "text": data.text,
        "color": data.color,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_notes.insert_one(note)
    note.pop("_id", None)
    return note

@api_router.patch("/calendar-notes/{note_id}")
async def update_calendar_note(note_id: str, data: CalendarNoteUpdate, current_user: User = Depends(get_current_user)):
    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if update:
        await db.calendar_notes.update_one(
            {"id": note_id, "user_id": current_user.user_id}, {"$set": update}
        )
    return await db.calendar_notes.find_one({"id": note_id}, {"_id": 0})

@api_router.delete("/calendar-notes/{note_id}", status_code=204)
async def delete_calendar_note(note_id: str, current_user: User = Depends(get_current_user)):
    await db.calendar_notes.delete_one({"id": note_id, "user_id": current_user.user_id})

# ==================== CALENDAR SHARE ====================

@api_router.post("/calendar/share")
async def create_calendar_share(current_user: User = Depends(get_current_user)):
    """Generate (or return existing) public share token for the user's calendar."""
    existing = await db.calendar_shares.find_one({"user_id": current_user.user_id}, {"_id": 0})
    if existing:
        existing.pop("_id", None)
        return existing
    share = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.user_id,
        "token": str(uuid.uuid4()).replace("-", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calendar_shares.insert_one(share)
    share.pop("_id", None)
    return share

@api_router.get("/calendar/public/{token}")
async def get_public_calendar(token: str):
    """Public endpoint — no auth required. Returns scheduled posts for a shared calendar."""
    share = await db.calendar_shares.find_one({"token": token}, {"_id": 0})
    if not share:
        raise HTTPException(status_code=404, detail="Calendar not found")
    posts = await db.posts.find(
        {"user_id": share["user_id"], "status": "scheduled"},
        {"_id": 0}
    ).to_list(500)
    for post in posts:
        post.pop("user_id", None)
    return {"posts": posts}

@api_router.delete("/calendar/share", status_code=204)
async def delete_calendar_share(current_user: User = Depends(get_current_user)):
    """Revoke the public share link."""
    await db.calendar_shares.delete_one({"user_id": current_user.user_id})

# ==================== ANALYTICS ====================

@api_router.get("/analytics/overview")
async def get_analytics_overview(
    days: int = 30,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Return aggregate counts for the dashboard analytics page."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    base_q: Dict[str, Any] = {"user_id": current_user.user_id, "status": "published", "published_at": {"$gte": since}}
    if platform:
        base_q["platforms"] = platform
    if account_id:
        base_q["accounts"] = account_id

    published_in_period = await db.posts.count_documents(base_q)
    total_q: Dict[str, Any] = {"user_id": current_user.user_id, "status": "published"}
    if platform:
        total_q["platforms"] = platform
    if account_id:
        total_q["accounts"] = account_id
    total_published = await db.posts.count_documents(total_q)
    scheduled = await db.posts.count_documents({"user_id": current_user.user_id, "status": "scheduled"})
    drafts = await db.posts.count_documents({"user_id": current_user.user_id, "status": "draft"})

    # Pull lightweight fields for breakdowns
    published_posts = await db.posts.find(
        base_q,
        {"_id": 0, "platforms": 1, "post_type": 1},
    ).to_list(5000)

    platform_counts: dict = {}
    type_counts: dict = {"text": 0, "image": 0, "video": 0}
    for post in published_posts:
        for p in post.get("platforms", []):
            platform_counts[p] = platform_counts.get(p, 0) + 1
        t = post.get("post_type", "text")
        type_counts[t] = type_counts.get(t, 0) + 1

    top_platform = max(platform_counts, key=platform_counts.get) if platform_counts else None

    return {
        "published_in_period": published_in_period,
        "total_published": total_published,
        "scheduled": scheduled,
        "drafts": drafts,
        "top_platform": top_platform,
        "platform_counts": platform_counts,
        "type_counts": type_counts,
    }


@api_router.get("/analytics/timeline")
async def get_analytics_timeline(
    days: int = 30,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Return a list of {date, count} for published posts per day over the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.isoformat()

    q: Dict[str, Any] = {"user_id": current_user.user_id, "status": "published", "published_at": {"$gte": since_str}}
    if platform:
        q["platforms"] = platform
    if account_id:
        q["accounts"] = account_id

    posts = await db.posts.find(q, {"_id": 0, "published_at": 1}).to_list(5000)

    day_counts: dict = {}
    for post in posts:
        pa = post.get("published_at")
        if pa:
            try:
                date_str = pa[:10]  # YYYY-MM-DD
                day_counts[date_str] = day_counts.get(date_str, 0) + 1
            except Exception:
                pass

    # Build a complete date series (no gaps)
    result = []
    cursor = since
    now = datetime.now(timezone.utc)
    while cursor <= now:
        date_str = cursor.strftime("%Y-%m-%d")
        result.append({"date": date_str, "count": day_counts.get(date_str, 0)})
        cursor += timedelta(days=1)

    return result


@api_router.get("/analytics/engagement")
async def get_analytics_engagement(
    days: int = 30,
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Fetch real engagement metrics (likes, comments, shares, views) from connected social accounts.
    Aggregates totals, per-platform breakdown, and returns top posts sorted by engagement.
    """
    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "is_active": True}
    if account_id:
        acct_query["id"] = account_id
    if platform:
        acct_query["platform"] = platform

    accounts = await db.social_accounts.find(acct_query, {"_id": 0}).to_list(100)
    if not accounts:
        return {
            "totals": {"total_posts": 0, "total_likes": 0, "total_comments": 0, "total_shares": 0, "total_views": 0},
            "platform_breakdown": {},
            "top_posts": [],
            "accounts_fetched": 0,
        }

    ig_auth = InstagramAuth()
    fb_auth = FacebookAuth()
    tw_auth = TwitterAuth()
    li_auth = LinkedInAuth()
    yt_auth = GoogleAuth()
    threads_auth = ThreadsAuth()
    reddit_auth = RedditAuth()
    pinterest_auth = PinterestAuth()
    tiktok_auth = TikTokAuth()
    bluesky_auth = BlueskyAuth()
    snapchat_auth = SnapchatAuth()

    all_posts = []
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)

    for account in accounts:
        plat = account.get("platform")
        token = account.get("access_token")
        if not token:
            continue

        try:
            posts = []
            if plat == "instagram":
                uid = account.get("platform_user_id", "me")
                posts = await ig_auth.fetch_media(token, uid, 50)
            elif plat == "facebook":
                page_id = account.get("platform_user_id")
                if page_id:
                    posts = await fb_auth.fetch_page_posts(token, page_id, 50)
            elif plat == "twitter":
                uid = account.get("platform_user_id")
                if uid:
                    posts = await tw_auth.fetch_user_tweets(token, uid, 50)
            elif plat == "linkedin":
                person_urn = account.get("platform_user_id")
                if person_urn:
                    posts = await li_auth.fetch_posts(token, person_urn, 50)
            elif plat == "youtube":
                refresh_tok = account.get("refresh_token")
                if refresh_tok:
                    try:
                        new_tokens = await yt_auth.refresh_access_token(refresh_tok)
                        token = new_tokens.get("access_token", token)
                    except Exception:
                        pass
                posts = await yt_auth.fetch_channel_videos(token, 50)
            elif plat == "threads":
                uid = account.get("platform_user_id", "me")
                posts = await threads_auth.fetch_posts(token, uid, 50)
            elif plat == "reddit":
                username = account.get("platform_username")
                if username:
                    posts = await reddit_auth.fetch_user_posts(token, username, 50)
            elif plat == "pinterest":
                posts = await pinterest_auth.fetch_pins(token, 50)
            elif plat == "tiktok":
                posts = await tiktok_auth.fetch_posts(token, 50)
            elif plat == "bluesky":
                handle = account.get("platform_username")
                if handle:
                    posts = await bluesky_auth.fetch_posts(token, handle, 50)
            elif plat == "snapchat":
                posts = await snapchat_auth.fetch_posts(token, 50)

            # Filter to posts within the selected date range
            def _in_range(p):
                pa = p.get("published_at")
                if not pa:
                    return True  # include if no date info
                try:
                    dt = datetime.fromisoformat(pa.replace("Z", "+00:00"))
                    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    return dt >= since_dt
                except Exception:
                    return True

            for post in posts:
                if _in_range(post):
                    post["account_id"] = account.get("id")
                    post["platform"] = plat
                    post["account_username"] = account.get("platform_username", plat)
                    post["account_picture"] = account.get("picture_url")
                    all_posts.append(post)

        except Exception as e:
            logging.error(f"[analytics/engagement] Error fetching from {plat}: {e}")
            continue

    # Aggregate totals
    totals = {"total_posts": 0, "total_likes": 0, "total_comments": 0, "total_shares": 0, "total_views": 0}
    platform_breakdown: dict = {}

    for post in all_posts:
        m = post.get("metrics", {}) or {}
        likes = m.get("likes") or 0
        comments = m.get("comments") or 0
        shares = m.get("shares") or 0
        views = m.get("views") or 0
        totals["total_posts"] += 1
        totals["total_likes"] += likes
        totals["total_comments"] += comments
        totals["total_shares"] += shares
        totals["total_views"] += views

        plat_key = post.get("platform", "unknown")
        if plat_key not in platform_breakdown:
            platform_breakdown[plat_key] = {"posts": 0, "likes": 0, "comments": 0, "shares": 0, "views": 0}
        platform_breakdown[plat_key]["posts"] += 1
        platform_breakdown[plat_key]["likes"] += likes
        platform_breakdown[plat_key]["comments"] += comments
        platform_breakdown[plat_key]["shares"] += shares
        platform_breakdown[plat_key]["views"] += views

    # Top posts sorted by total engagement (likes + comments + shares)
    def _engagement_score(p):
        m = p.get("metrics", {}) or {}
        return (m.get("likes") or 0) + (m.get("comments") or 0) + (m.get("shares") or 0)

    top_posts = sorted(all_posts, key=_engagement_score, reverse=True)[:10]

    return {
        "totals": totals,
        "platform_breakdown": platform_breakdown,
        "top_posts": top_posts,
        "accounts_fetched": len(accounts),
    }

# ==================== ANALYTICS DEMOGRAPHICS ====================

DEMOGRAPHICS_PLATFORMS = {"instagram", "facebook"}

@api_router.get("/analytics/demographics")
async def get_analytics_demographics(
    platform: Optional[str] = None,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Fetch follower/fan demographics from Instagram and Facebook."""
    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "is_active": True}
    if account_id:
        acct_query["id"] = account_id
    if platform:
        acct_query["platform"] = platform

    accounts = await db.social_accounts.find(acct_query, {"_id": 0}).to_list(100)
    eligible = [a for a in accounts if a.get("platform") in DEMOGRAPHICS_PLATFORMS]

    if not eligible:
        return {
            "supported": False,
            "message": "Demographics require an Instagram Business or Facebook Page account.",
            "demographics": {"age": [], "gender": [], "cities": [], "countries": []},
        }

    ig_auth = InstagramAuth()
    fb_auth = FacebookAuth()

    # Aggregate demographics from all eligible accounts
    combined = {"age": {}, "gender": {}, "cities": {}, "countries": {}}
    accounts_used = []
    errors = []

    for account in eligible:
        plat = account.get("platform")
        token = account.get("access_token")
        if not token:
            continue

        try:
            if plat == "instagram":
                uid = account.get("platform_user_id", "me")
                demo = await ig_auth.fetch_demographics(token, uid)
            elif plat == "facebook":
                page_id = account.get("platform_user_id")
                if not page_id:
                    continue
                demo = await fb_auth.fetch_page_demographics(token, page_id)
            else:
                continue

            if not demo.get("supported", True):
                errors.append({"account": account.get("platform_username", plat), "error": demo.get("error", "")})
                continue

            accounts_used.append(account.get("platform_username", plat))

            # Merge into combined
            for item in demo.get("age", []):
                key = item["range"]
                combined["age"][key] = combined["age"].get(key, 0) + item["count"]
            for item in demo.get("gender", []):
                key = item["label"]
                combined["gender"][key] = combined["gender"].get(key, 0) + item["count"]
            for item in demo.get("cities", []):
                key = item["name"]
                combined["cities"][key] = combined["cities"].get(key, 0) + item["count"]
            for item in demo.get("countries", []):
                key = item["name"]
                combined["countries"][key] = combined["countries"].get(key, 0) + item["count"]

        except Exception as e:
            logging.error(f"[analytics/demographics] Error from {plat}: {e}")
            errors.append({"account": account.get("platform_username", plat), "error": str(e)})

    def to_sorted_list(d, key_name):
        return sorted([{key_name: k, "count": v} for k, v in d.items()], key=lambda x: x["count"], reverse=True)

    return {
        "supported": True,
        "demographics": {
            "age": to_sorted_list(combined["age"], "range"),
            "gender": to_sorted_list(combined["gender"], "label"),
            "cities": to_sorted_list(combined["cities"], "name")[:20],
            "countries": to_sorted_list(combined["countries"], "name")[:20],
        },
        "accounts_used": accounts_used,
        "errors": errors,
    }


# ==================== COMMENTS ====================

COMMENT_PLATFORMS = {"instagram", "facebook", "youtube", "threads", "reddit", "bluesky"}
REPLY_PLATFORMS = {"instagram", "facebook", "threads", "reddit", "bluesky"}  # YouTube needs youtube.force-ssl scope

@api_router.get("/comments/{platform}/{post_id:path}")
async def get_post_comments(
    platform: str,
    post_id: str,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Fetch comments for a post from the platform API."""
    if platform not in COMMENT_PLATFORMS:
        return {"comments": [], "supported": False, "message": f"Comments not available for {platform}"}

    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "platform": platform, "is_active": True}
    if account_id:
        acct_query["id"] = account_id

    account = await db.social_accounts.find_one(acct_query, {"_id": 0})
    if not account:
        return {"comments": [], "supported": False, "message": "No connected account found"}

    token = account.get("access_token")
    if not token:
        return {"comments": [], "supported": False, "message": "No access token"}

    try:
        comments = []
        if platform == "instagram":
            comments = await InstagramAuth().fetch_comments(token, post_id)
        elif platform == "facebook":
            comments = await FacebookAuth().fetch_comments(token, post_id)
        elif platform == "youtube":
            # Refresh token if available
            refresh_tok = account.get("refresh_token")
            if refresh_tok:
                try:
                    new_tokens = await GoogleAuth().refresh_access_token(refresh_tok)
                    token = new_tokens.get("access_token", token)
                except Exception:
                    pass
            comments = await GoogleAuth().fetch_comments(token, post_id)
        elif platform == "threads":
            comments = await ThreadsAuth().fetch_replies(token, post_id)
        elif platform == "reddit":
            comments = await RedditAuth().fetch_comments(token, post_id)
        elif platform == "bluesky":
            comments = await BlueskyAuth().fetch_replies(token, post_id)

        return {
            "comments": comments,
            "supported": True,
            "platform": platform,
            "post_id": post_id,
            "can_reply": platform in REPLY_PLATFORMS,
        }
    except Exception as e:
        logging.error(f"[comments] Error fetching comments from {platform}: {e}")
        return {"comments": [], "supported": True, "error": str(e)}


@api_router.post("/comments/{platform}/{comment_id:path}/reply")
async def reply_to_comment(
    platform: str,
    comment_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Reply to a comment on a platform."""
    text = body.get("text", "").strip()
    account_id = body.get("account_id")
    post_id = body.get("post_id")

    if not text:
        raise HTTPException(status_code=400, detail="Reply text is required")
    if platform not in REPLY_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Replying not supported for {platform}")

    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "platform": platform, "is_active": True}
    if account_id:
        acct_query["id"] = account_id

    account = await db.social_accounts.find_one(acct_query, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="No connected account found")

    token = account.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="No access token")

    try:
        result = {}
        if platform == "instagram":
            result = await InstagramAuth().reply_to_comment(token, comment_id, text)
        elif platform == "facebook":
            result = await FacebookAuth().reply_to_comment(token, comment_id, text)
        elif platform == "threads":
            uid = account.get("platform_user_id", "me")
            reply_id = await ThreadsAuth().reply_to_thread(token, uid, comment_id, text)
            result = {"id": reply_id}
        elif platform == "reddit":
            result = await RedditAuth().reply_to_comment(token, comment_id, text)
        elif platform == "bluesky":
            # For Bluesky, comment_id is the parent URI
            # We need the parent CID and root info from the body
            parent_cid = body.get("parent_cid")
            root_uri = body.get("root_uri")
            root_cid = body.get("root_cid")
            did = account.get("platform_user_id")
            if did and parent_cid and root_uri and root_cid:
                reply_ref = {
                    "root": {"uri": root_uri, "cid": root_cid},
                    "parent": {"uri": comment_id, "cid": parent_cid},
                }
                result_id = await BlueskyAuth().publish_post(token, did, text, reply_ref=reply_ref)
                result = {"id": result_id}
            else:
                raise Exception("Missing Bluesky reply context (parent_cid, root_uri, root_cid)")

        return {"ok": True, "reply_id": result.get("id"), "platform": platform}

    except Exception as e:
        logging.error(f"[comments/reply] Error replying on {platform}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MESSAGES / DMs ====================

DM_PLATFORMS = {"instagram", "facebook"}

@api_router.get("/messages/{platform}")
async def get_conversations(
    platform: str,
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Fetch DM conversations from a platform."""
    if platform not in DM_PLATFORMS:
        return {"conversations": [], "supported": False, "message": f"DMs not available for {platform}"}

    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "platform": platform, "is_active": True}
    if account_id:
        acct_query["id"] = account_id

    account = await db.social_accounts.find_one(acct_query, {"_id": 0})
    if not account:
        return {"conversations": [], "supported": False, "message": "No connected account found"}

    token = account.get("access_token")
    if not token:
        return {"conversations": [], "supported": False, "message": "No access token"}

    try:
        conversations = []
        if platform == "instagram":
            uid = account.get("platform_user_id", "me")
            conversations = await InstagramAuth().fetch_conversations(token, uid)
        elif platform == "facebook":
            page_id = account.get("platform_user_id")
            if page_id:
                conversations = await FacebookAuth().fetch_page_conversations(token, page_id)

        return {
            "conversations": conversations,
            "supported": True,
            "platform": platform,
            "account_id": account.get("id"),
        }
    except Exception as e:
        logging.error(f"[messages] Error fetching conversations from {platform}: {e}")
        return {"conversations": [], "supported": True, "error": str(e)}


@api_router.post("/messages/{platform}/{conversation_id}/reply")
async def send_dm_reply(
    platform: str,
    conversation_id: str,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """Send a DM reply on a platform."""
    text = body.get("text", "").strip()
    account_id = body.get("account_id")
    recipient_id = body.get("recipient_id")

    if not text:
        raise HTTPException(status_code=400, detail="Message text is required")
    if platform not in DM_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"DMs not supported for {platform}")
    if not recipient_id:
        raise HTTPException(status_code=400, detail="recipient_id is required")

    acct_query: Dict[str, Any] = {"user_id": current_user.user_id, "platform": platform, "is_active": True}
    if account_id:
        acct_query["id"] = account_id

    account = await db.social_accounts.find_one(acct_query, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="No connected account found")

    token = account.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="No access token")

    try:
        result = {}
        if platform == "instagram":
            result = await InstagramAuth().send_message(token, recipient_id, text)
        elif platform == "facebook":
            page_id = account.get("platform_user_id")
            if page_id:
                result = await FacebookAuth().send_page_message(token, page_id, recipient_id, text)

        return {"ok": True, "platform": platform, "result": result}

    except Exception as e:
        logging.error(f"[messages/reply] Error sending DM on {platform}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RECURRING POSTS ====================

def _generate_recurring_times(
    frequency: str,
    days_of_week: list,   # JS convention: 0=Sun … 6=Sat
    day_of_month: int,
    time_of_day: str,     # "HH:MM" UTC
    horizon_days: int = 60,
) -> list:
    """Return ISO-format UTC datetime strings for recurring scheduled posts."""
    try:
        hour, minute = map(int, time_of_day.split(":"))
    except Exception:
        hour, minute = 9, 0

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=horizon_days)

    # Start cursor at the first occurrence on/after tomorrow
    cursor = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cursor <= now:
        cursor += timedelta(days=1)

    results = []

    if frequency == "daily":
        while cursor <= end:
            results.append(cursor.isoformat())
            cursor += timedelta(days=1)

    elif frequency == "weekly":
        # Convert JS weekday (0=Sun) → Python weekday (0=Mon)
        py_days = {(d + 6) % 7 for d in (days_of_week or [1])}
        while cursor <= end:
            if cursor.weekday() in py_days:
                results.append(cursor.isoformat())
            cursor += timedelta(days=1)

    elif frequency == "monthly":
        target_day = max(1, min(28, day_of_month or 1))
        while cursor <= end:
            if cursor.day == target_day:
                results.append(cursor.isoformat())
                cursor += timedelta(days=28)
            else:
                cursor += timedelta(days=1)

    return results[:200]  # safety cap


async def _create_posts_for_rule(rule: dict, user_id: str) -> int:
    """Bulk-insert scheduled posts for all times generated by a rule."""
    times = _generate_recurring_times(
        frequency=rule.get("frequency", "weekly"),
        days_of_week=rule.get("days_of_week", [1]),
        day_of_month=rule.get("day_of_month", 1),
        time_of_day=rule.get("time_of_day", "09:00"),
    )
    if not times:
        return 0

    now_str = datetime.now(timezone.utc).isoformat()
    posts = [
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "content": rule.get("content", ""),
            "post_type": rule.get("post_type", "text"),
            "platforms": rule.get("platforms", []),
            "accounts": rule.get("accounts", []),
            "media_urls": rule.get("media_urls", []),
            "media_alt_texts": [],
            "scheduled_time": st,
            "status": "scheduled",
            "created_at": now_str,
            "published_at": None,
            "ai_generated": False,
            "recurring_rule_id": rule["id"],
        }
        for st in times
    ]
    await db.posts.insert_many(posts)
    return len(posts)


@api_router.post("/recurring-rules", status_code=201)
async def create_recurring_rule(data: RecurringRuleCreate, current_user: User = Depends(get_current_user)):
    """Create a recurring rule and pre-generate scheduled posts for the next 60 days."""
    rule = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.user_id,
        "content": data.content,
        "platforms": data.platforms,
        "accounts": data.accounts,
        "post_type": data.post_type,
        "media_urls": data.media_urls or [],
        "frequency": data.frequency,
        "days_of_week": data.days_of_week,
        "day_of_month": data.day_of_month,
        "time_of_day": data.time_of_day,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.recurring_rules.insert_one(rule)
    rule.pop("_id", None)

    count = await _create_posts_for_rule(rule, current_user.user_id)
    rule["upcoming_count"] = count
    return rule


@api_router.get("/recurring-rules")
async def list_recurring_rules(current_user: User = Depends(get_current_user)):
    """List all recurring rules for the current user with upcoming post counts."""
    rules = await db.recurring_rules.find(
        {"user_id": current_user.user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    now_str = datetime.now(timezone.utc).isoformat()
    for rule in rules:
        rule["upcoming_count"] = await db.posts.count_documents({
            "recurring_rule_id": rule["id"],
            "status": "scheduled",
            "scheduled_time": {"$gte": now_str},
        })
    return rules


@api_router.patch("/recurring-rules/{rule_id}")
async def update_recurring_rule(
    rule_id: str,
    data: RecurringRuleUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a rule's status (pause/resume) or schedule. Re-generates posts on schedule change."""
    rule = await db.recurring_rules.find_one(
        {"id": rule_id, "user_id": current_user.user_id}, {"_id": 0}
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    schedule_fields = {"frequency", "days_of_week", "day_of_month", "time_of_day"}
    schedule_changed = bool(updates.keys() & schedule_fields)

    if updates:
        await db.recurring_rules.update_one({"id": rule_id}, {"$set": updates})

    # If schedule changed or rule re-activated, delete old future posts and regenerate
    if schedule_changed or updates.get("status") == "active":
        now_str = datetime.now(timezone.utc).isoformat()
        await db.posts.delete_many({
            "recurring_rule_id": rule_id,
            "status": "scheduled",
            "scheduled_time": {"$gte": now_str},
        })
        if updates.get("status", rule.get("status")) == "active":
            updated_rule = {**rule, **updates}
            await _create_posts_for_rule(updated_rule, current_user.user_id)

    # If paused, delete upcoming scheduled posts
    if updates.get("status") == "paused":
        now_str = datetime.now(timezone.utc).isoformat()
        await db.posts.delete_many({
            "recurring_rule_id": rule_id,
            "status": "scheduled",
            "scheduled_time": {"$gte": now_str},
        })

    updated = await db.recurring_rules.find_one({"id": rule_id}, {"_id": 0})
    return updated


@api_router.delete("/recurring-rules/{rule_id}", status_code=204)
async def delete_recurring_rule(rule_id: str, current_user: User = Depends(get_current_user)):
    """Delete a rule and all its future scheduled posts."""
    result = await db.recurring_rules.delete_one({"id": rule_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    now_str = datetime.now(timezone.utc).isoformat()
    await db.posts.delete_many({
        "recurring_rule_id": rule_id,
        "status": "scheduled",
        "scheduled_time": {"$gte": now_str},
    })

# ==================== POST APPROVAL WORKFLOW ====================

@api_router.post("/posts/{post_id}/submit-for-review")
async def submit_post_for_review(post_id: str, current_user: User = Depends(get_current_user)):
    """Move a draft/rejected post into the approval queue and notify can_approve team members."""
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get("status") not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Only draft or rejected posts can be submitted for review")
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"status": "pending_review", "rejection_note": None}},
    )
    # Notify can_approve team members (non-fatal)
    approvers = await db.team_members.find(
        {"owner_user_id": current_user.user_id, "status": "accepted", "can_approve": True},
        {"email": 1, "member_user_id": 1}
    ).to_list(50)
    for approver in approvers:
        approver_user = await db.users.find_one({"user_id": approver.get("member_user_id")}, {"name": 1})
        approver_name = approver_user.get("name", approver["email"]) if approver_user else approver["email"]
        await send_approval_request_email(
            approver_email=approver["email"],
            approver_name=approver_name,
            owner_name=current_user.name,
            post_content=post.get("content", ""),
            post_id=post_id,
        )
    return {"id": post_id, "status": "pending_review"}


async def _get_post_for_approval(post_id: str, current_user: User):
    """
    Return the post if current_user is allowed to approve/reject it:
      - the post owner themselves, OR
      - a team member with can_approve=True in the owner's workspace.
    Raises 404 if not found, 403 if not authorised.
    """
    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Owner can always act on their own post
    if post["user_id"] == current_user.user_id:
        return post

    # Check if current_user is a can_approve member of the post owner's workspace
    member = await db.team_members.find_one({
        "owner_user_id": post["user_id"],
        "email": current_user.email.lower(),
        "status": "accepted",
        "can_approve": True,
    })
    if not member:
        raise HTTPException(status_code=403, detail="You do not have permission to approve or reject this post")

    return post


@api_router.post("/posts/{post_id}/approve")
async def approve_post(post_id: str, current_user: User = Depends(get_current_user)):
    """Approve a pending-review post (moves to scheduled or draft) and notify post owner."""
    post = await _get_post_for_approval(post_id, current_user)
    if post.get("status") != "pending_review":
        raise HTTPException(status_code=400, detail="Only pending-review posts can be approved")
    new_status = "scheduled" if post.get("scheduled_time") else "draft"
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"status": new_status, "rejection_note": None}},
    )
    # Notify post owner if approver is different (team member approving)
    owner_doc = await db.users.find_one({"user_id": post["user_id"]}, {"email": 1, "name": 1})
    if owner_doc and owner_doc.get("email") != current_user.email:
        await send_approval_result_email(
            owner_email=owner_doc["email"],
            owner_name=owner_doc.get("name", ""),
            reviewer_name=current_user.name,
            post_content=post.get("content", ""),
            approved=True,
        )
    return {"id": post_id, "status": new_status}


@api_router.post("/posts/{post_id}/reject")
async def reject_post(post_id: str, payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """Reject a pending-review post with an optional note (status → rejected) and notify owner."""
    post = await _get_post_for_approval(post_id, current_user)
    if post.get("status") != "pending_review":
        raise HTTPException(status_code=400, detail="Only pending-review posts can be rejected")
    note = (payload.get("note") or "").strip() or None
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"status": "rejected", "rejection_note": note}},
    )
    # Notify post owner if rejector is different (team member)
    owner_doc = await db.users.find_one({"user_id": post["user_id"]}, {"email": 1, "name": 1})
    if owner_doc and owner_doc.get("email") != current_user.email:
        await send_approval_result_email(
            owner_email=owner_doc["email"],
            owner_name=owner_doc.get("name", ""),
            reviewer_name=current_user.name,
            post_content=post.get("content", ""),
            approved=False,
            rejection_note=note,
        )
    return {"id": post_id, "status": "rejected", "rejection_note": note}


@api_router.post("/posts/{post_id}/resubmit")
async def resubmit_post(post_id: str, current_user: User = Depends(get_current_user)):
    """Move a rejected post back to draft so it can be edited and re-submitted."""
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get("status") != "rejected":
        raise HTTPException(status_code=400, detail="Only rejected posts can be resubmitted")
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"status": "draft", "rejection_note": None}},
    )
    return {"id": post_id, "status": "draft"}

# ==================== BULK IMPORT ====================

@api_router.post("/posts/bulk")
async def bulk_create_posts(payload: Dict[str, Any], current_user: User = Depends(get_current_user)):
    """
    Bulk-create posts from a parsed CSV payload.
    Body: { "posts": [ {content, platforms, scheduled_time?, post_type?, media_urls?, ...} ] }
    Returns: { created, skipped, errors: [{row, message}] }
    """
    rows = payload.get("posts", [])
    if not rows:
        raise HTTPException(status_code=400, detail="No posts provided")

    created = 0
    errors = []
    now_str = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(rows):
        row_num = i + 1
        try:
            content = (row.get("content") or "").strip()
            if not content:
                errors.append({"row": row_num, "message": "content is required"})
                continue

            platforms = row.get("platforms") or []
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split("|") if p.strip()]
            if not platforms:
                errors.append({"row": row_num, "message": "platforms is required"})
                continue

            scheduled_time = None
            status = "draft"
            raw_time = (row.get("scheduled_time") or "").strip()
            if raw_time:
                if current_user.subscription_status != "active":
                    errors.append({"row": row_num, "message": "scheduling requires an active subscription"})
                    continue
                try:
                    if len(raw_time) == 16:  # "YYYY-MM-DD HH:MM"
                        raw_time = raw_time.replace(" ", "T") + ":00+00:00"
                    scheduled_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    status = "scheduled"
                except ValueError:
                    errors.append({"row": row_num, "message": f"invalid scheduled_time format: '{raw_time}'"})
                    continue

            media_urls_raw = (row.get("media_urls") or "").strip()
            media_urls = [u.strip() for u in media_urls_raw.split("|") if u.strip()] if media_urls_raw else []

            post_dict = {
                "id": str(uuid.uuid4()),
                "user_id": current_user.user_id,
                "content": content,
                "post_type": (row.get("post_type") or "text").strip() or "text",
                "platforms": platforms,
                "accounts": [],
                "media_urls": media_urls,
                "media_alt_texts": [],
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
                "status": status,
                "created_at": now_str,
                "published_at": None,
                "ai_generated": False,
                "instagram_first_comment": (row.get("instagram_first_comment") or "").strip() or None,
                "instagram_post_format": "Post",
            }
            await db.posts.insert_one(post_dict)
            created += 1
        except Exception as e:
            logging.error(f"Bulk import row {row_num} error: {e}")
            errors.append({"row": row_num, "message": str(e)})

    return {"created": created, "skipped": len(errors), "errors": errors}

# ==================== MEDIA LIBRARY ====================

@api_router.post("/media", status_code=201)
async def create_media_asset(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Upload a file to the user's persistent media library."""
    try:
        file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else 'bin'
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        content = await file.read()
        size_bytes = len(content)

        firebase_bucket = os.environ.get('FIREBASE_STORAGE_BUCKET')
        if firebase_bucket:
            from firebase_admin import storage as fb_storage
            bucket = fb_storage.bucket()
            blob = bucket.blob(f"media/{current_user.user_id}/{unique_filename}")
            blob.upload_from_string(content, content_type=file.content_type)
            blob.make_public()
            file_url = blob.public_url
        else:
            file_path = UPLOADS_DIR / unique_filename
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            file_url = f"/uploads/{unique_filename}"

        asset = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "url": file_url,
            "filename": file.filename,
            "content_type": file.content_type or f"image/{file_ext}",
            "size_bytes": size_bytes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.media_assets.insert_one(asset)
        asset.pop("_id", None)
        return asset
    except Exception as e:
        logging.error(f"Media library upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload media")


@api_router.get("/media")
async def list_media_assets(
    media_type: Optional[str] = None,  # "image" or "video"
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Return all media assets for the current user, newest first."""
    query: dict = {"user_id": current_user.user_id}
    if media_type:
        query["content_type"] = {"$regex": f"^{media_type}/", "$options": "i"}
    if search:
        query["filename"] = {"$regex": search, "$options": "i"}
    assets = await db.media_assets.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return assets


@api_router.delete("/media/{asset_id}", status_code=204)
async def delete_media_asset(asset_id: str, current_user: User = Depends(get_current_user)):
    """Delete a media asset from the library (and from local disk if stored locally)."""
    asset = await db.media_assets.find_one(
        {"id": asset_id, "user_id": current_user.user_id}, {"_id": 0}
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Remove local file if applicable
    url = asset.get("url", "")
    if "/uploads/" in url and not url.startswith("http"):
        local_path = ROOT_DIR / url.lstrip("/")
        if local_path.exists():
            try:
                local_path.unlink()
            except Exception:
                pass
    await db.media_assets.delete_one({"id": asset_id, "user_id": current_user.user_id})

# ==================== AI CONTENT GENERATION ====================

@limiter.limit("20/minute")
@api_router.post("/ai/generate-content")
async def generate_content(request: Request, ai_request: AIContentRequest, current_user: User = Depends(get_current_user)):
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")
        
        platform_context = ""
        if ai_request.platform:
            if ai_request.platform == "twitter":
                platform_context = " Keep it under 280 characters for Twitter."
            elif ai_request.platform == "linkedin":
                platform_context = " Make it professional for LinkedIn."
            elif ai_request.platform == "instagram":
                platform_context = " Make it engaging for Instagram with relevant hashtags."
        
        system_message = f"You are a social media content expert. Generate engaging social media posts.{platform_context}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"content-gen-{current_user.user_id}-{uuid.uuid4()}",
            system_message=system_message
        ).with_model("openai", "gpt-5.2")
        
        user_message = UserMessage(text=ai_request.prompt)
        response = await chat.send_message(user_message)
        
        return {"content": response}
    except Exception as e:
        logging.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

@limiter.limit("20/minute")
@api_router.post("/ai/generate-image")
async def generate_image(http_request: Request, request: dict, current_user: User = Depends(get_current_user)):
    """
    Generate an image from a text prompt using the Emergent LLM / DALL-E API.
    Returns a URL to the generated image.
    """
    prompt = (request.get("prompt") or "").strip()
    size   = request.get("size", "1024x1024")   # 1024x1024 | 1024x1792 | 1792x1024
    style  = request.get("style", "vivid")       # vivid | natural

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")

    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            # Emergent API proxies to OpenAI images endpoint
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                json={
                    "model":   "dall-e-3",
                    "prompt":  prompt,
                    "n":       1,
                    "size":    size,
                    "style":   style,
                    "quality": "standard",
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
            )
            if response.status_code != 200:
                logging.error(f"[AI Image] OpenAI error: {response.text}")
                raise HTTPException(status_code=500, detail="Image generation failed")
            data = response.json()
            image_url = data["data"][0]["url"]
            revised_prompt = data["data"][0].get("revised_prompt", prompt)
            return {"url": image_url, "revised_prompt": revised_prompt}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[AI Image] generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

# ==================== SOCIAL ACCOUNTS ====================

# ==================== OAUTH ENDPOINTS ====================


@api_router.get("/oauth/twitter/authorize")
async def twitter_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Twitter OAuth 2.0 flow"""
    tw_auth = TwitterAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    
    # Twitter requires PKCE
    code_verifier, code_challenge = tw_auth.generate_pkce()
    
    # Store code_verifier in user's document temporarily or in a dedicated collection
    # For simplicity, we'll store it in the user's document for now
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"twitter_code_verifier": code_verifier}}
    )
    
    auth_url = tw_auth.get_auth_url(state, code_challenge)
    logging.info(f"[Twitter] Authorize for user {current_user.user_id}, state={state[:20]}...")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/twitter/callback")
async def twitter_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Twitter OAuth callback"""
    if error or not code:
        error_msg = error or "No authorization code provided"
        logging.error(f"Twitter OAuth error: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

    user_id_from_state, return_to = _parse_oauth_state(state or "")
    if not user_id_from_state:
        logging.error("Twitter OAuth callback: Invalid state")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

    user_doc = await db.users.find_one({"user_id": user_id_from_state})
    if not user_doc:
        logging.error(f"Twitter OAuth: User {user_id_from_state} not found")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

    code_verifier = user_doc.get("twitter_code_verifier")
    if not code_verifier:
        logging.error(f"Twitter OAuth: Missing code_verifier for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=pkce_failed")

    try:
        tw_auth = TwitterAuth()
        token_data = await tw_auth.exchange_code_for_token(code, code_verifier)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 7200)

        # Clear code_verifier
        await db.users.update_one(
            {"user_id": user_id_from_state},
            {"$unset": {"twitter_code_verifier": ""}}
        )

        # Get profile
        tw_profile = await tw_auth.get_user_profile(access_token)
        
        tw_account = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_from_state,
            "platform": "twitter",
            "platform_user_id": str(tw_profile['id']),
            "username": tw_profile.get('name', 'Twitter User'),
            "platform_username": tw_profile.get('username', 'twitter_user'),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": tw_profile.get('profile_image_url'),
            "is_active": True
        }

        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "twitter", "platform_user_id": str(tw_profile['id'])},
            {"$set": tw_account},
            upsert=True
        )

        logging.info(f"[Twitter] Connected: {tw_profile.get('username')} for user {user_id_from_state}")

        # Redirect back to the frontend using the original FRONTEND_URL (localhost).
        # Do NOT replace localhost→127.0.0.1 here — localStorage is origin-scoped,
        # so switching origins would lose the JWT token and log the user out.
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platform=twitter")

    except Exception as e:
        logging.error(f"Twitter OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed")


# ==================== SOCIAL ACCOUNTS ====================

@api_router.post("/social-accounts", response_model=SocialAccount)
async def connect_social_account(account_data: SocialAccountConnect, current_user: User = Depends(get_current_user)):
    existing = await db.social_accounts.find_one({
        "user_id": current_user.user_id,
        "platform": account_data.platform
    })
    
    if existing:
        raise HTTPException(status_code=400, detail=f"{account_data.platform} already connected")
    
    account = SocialAccount(
        user_id=current_user.user_id,
        platform=account_data.platform,
        platform_username=account_data.platform_username
    )
    
    account_dict = account.model_dump()
    account_dict['connected_at'] = account_dict['connected_at'].isoformat()
    
    await db.social_accounts.insert_one(account_dict)
    return account

@api_router.get("/social-accounts", response_model=List[SocialAccount])
async def get_social_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.social_accounts.find({"user_id": current_user.user_id}, {"_id": 0}).to_list(100)

    tw_auth = TwitterAuth()
    now_utc = datetime.now(timezone.utc)

    for account in accounts:
        if isinstance(account.get('connected_at'), str):
            account['connected_at'] = datetime.fromisoformat(account['connected_at'])
        if account.get('token_expiry') and isinstance(account['token_expiry'], str):
            account['token_expiry'] = datetime.fromisoformat(account['token_expiry'])

        # ── Auto-refresh Twitter tokens that are expiring within 30 minutes ──
        if account.get('platform') == 'twitter' and account.get('refresh_token'):
            expiry = account.get('token_expiry')
            if expiry:
                expiry_dt = expiry if isinstance(expiry, datetime) else datetime.fromisoformat(str(expiry))
                if not expiry_dt.tzinfo:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                minutes_left = (expiry_dt - now_utc).total_seconds() / 60
                if minutes_left < 30:
                    try:
                        new_tokens = await tw_auth.refresh_token(account['refresh_token'])
                        new_access = new_tokens.get('access_token')
                        new_refresh = new_tokens.get('refresh_token', account['refresh_token'])
                        new_expires_in = new_tokens.get('expires_in', 7200)
                        new_expiry = now_utc + timedelta(seconds=new_expires_in)

                        await db.social_accounts.update_one(
                            {"id": account['id']},
                            {"$set": {
                                "access_token": new_access,
                                "refresh_token": new_refresh,
                                "token_expiry": new_expiry.isoformat(),
                            }}
                        )
                        account['access_token'] = new_access
                        account['refresh_token'] = new_refresh
                        account['token_expiry'] = new_expiry
                        logging.info(f"[Twitter] Auto-refreshed token for account {account.get('platform_username')}")
                    except Exception as refresh_err:
                        logging.warning(f"[Twitter] Auto-refresh failed for {account.get('platform_username')}: {refresh_err}")

    return accounts

@api_router.delete("/social-accounts/{account_id}")
async def disconnect_social_account(account_id: str, current_user: User = Depends(get_current_user)):
    result = await db.social_accounts.delete_one({"id": account_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account disconnected"}

# ==================== PUBLISH FEED ====================

@api_router.get("/publish/feed")
async def get_publish_feed(
    account_id: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """
    Fetch recent published posts from connected social accounts.
    Optionally filter by account_id or platform.
    Returns posts sorted by published_at descending.
    """
    query: Dict[str, Any] = {"user_id": current_user.user_id, "is_active": True}
    if account_id:
        query["id"] = account_id
    if platform:
        query["platform"] = platform

    accounts = await db.social_accounts.find(query, {"_id": 0}).to_list(100)
    if not accounts:
        return {"posts": [], "accounts_fetched": 0, "total": 0}

    ig_auth = InstagramAuth()
    fb_auth = FacebookAuth()
    tw_auth = TwitterAuth()
    li_auth = LinkedInAuth()
    yt_auth = GoogleAuth()
    threads_auth = ThreadsAuth()
    reddit_auth = RedditAuth()
    pinterest_auth = PinterestAuth()
    tiktok_auth = TikTokAuth()
    bluesky_auth = BlueskyAuth()
    snapchat_auth = SnapchatAuth()

    all_posts = []
    warnings = []  # surface per-account errors to the frontend

    for account in accounts:
        plat = account.get("platform")
        token = account.get("access_token")
        username = account.get("platform_username", plat)

        if not token:
            warnings.append({"platform": plat, "username": username, "reason": "No access token stored. Please reconnect this account."})
            continue

        try:
            posts = []

            if plat == "instagram":
                uid = account.get("platform_user_id", "me")
                posts = await ig_auth.fetch_media(token, uid, limit)
                if not posts:
                    warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Token may be expired or account may not be a Business/Creator account."})

            elif plat == "facebook":
                page_id = account.get("platform_user_id")
                if page_id:
                    posts = await fb_auth.fetch_page_posts(token, page_id, limit)
                    if not posts:
                        warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Token may be expired or insufficient permissions."})
                else:
                    warnings.append({"platform": plat, "username": username, "reason": "No Page ID stored. Please reconnect this account."})

            elif plat == "twitter":
                uid = account.get("platform_user_id")
                if uid:
                    posts = await tw_auth.fetch_user_tweets(token, uid, limit)
                    if not posts:
                        warnings.append({"platform": plat, "username": username, "reason": "No tweets returned. Token may be expired."})
                else:
                    warnings.append({"platform": plat, "username": username, "reason": "No user ID stored. Please reconnect this account."})

            elif plat == "linkedin":
                person_urn = account.get("platform_user_id")
                if person_urn:
                    posts = await li_auth.fetch_posts(token, person_urn, limit)
                    if not posts:
                        warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Token may be expired."})
                else:
                    warnings.append({"platform": plat, "username": username, "reason": "No person URN stored. Please reconnect this account."})

            elif plat == "youtube":
                # Auto-refresh YouTube token if a refresh_token is stored
                refresh_tok = account.get("refresh_token")
                if refresh_tok:
                    try:
                        new_tokens = await yt_auth.refresh_access_token(refresh_tok)
                        token = new_tokens.get("access_token", token)
                    except Exception as refresh_err:
                        logging.warning(f"[publish/feed] YouTube token refresh failed: {refresh_err}")
                        warnings.append({"platform": plat, "username": username, "reason": "Token refresh failed. Please reconnect this account."})
                posts = await yt_auth.fetch_channel_videos(token, limit)
                if not posts:
                    warnings.append({"platform": plat, "username": username, "reason": "No videos returned. Token may be expired."})

            elif plat == "threads":
                uid = account.get("platform_user_id", "me")
                posts = await threads_auth.fetch_posts(token, uid, limit)
                if not posts:
                    warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Token may be expired."})

            elif plat == "reddit":
                reddit_username = account.get("platform_username")
                if reddit_username:
                    posts = await reddit_auth.fetch_user_posts(token, reddit_username, limit)
                    if not posts:
                        warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Token may be expired."})
                else:
                    warnings.append({"platform": plat, "username": username, "reason": "No username stored. Please reconnect this account."})

            elif plat == "pinterest":
                posts = await pinterest_auth.fetch_pins(token, limit)
                if not posts:
                    warnings.append({"platform": plat, "username": username, "reason": "No pins returned. Token may be expired."})

            elif plat == "tiktok":
                posts = await tiktok_auth.fetch_posts(token, limit)
                if not posts:
                    warnings.append({"platform": plat, "username": username, "reason": "No videos returned. Token may be expired."})

            elif plat == "bluesky":
                handle = account.get("platform_username")
                if handle:
                    posts = await bluesky_auth.fetch_posts(token, handle, limit)
                    if not posts:
                        warnings.append({"platform": plat, "username": username, "reason": "No posts returned. Session may be expired."})
                else:
                    warnings.append({"platform": plat, "username": username, "reason": "No handle stored. Please reconnect this account."})

            elif plat == "snapchat":
                posts = await snapchat_auth.fetch_posts(token, limit)

            # Attach account metadata to each post
            for post in posts:
                post["account_id"] = account.get("id")
                post["platform"] = plat
                post["account_username"] = account.get("platform_username", plat)
                post["account_picture"] = account.get("picture_url")

            all_posts.extend(posts)

        except Exception as e:
            err_msg = str(e)
            logging.error(f"[publish/feed] Error fetching from {plat} ({username}): {err_msg}")
            warnings.append({"platform": plat, "username": username, "reason": f"API error: {err_msg[:120]}"})
            continue

    # Sort by published_at descending (newest first)
    def parse_date(p):
        val = p.get("published_at")
        if not val:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    all_posts.sort(key=parse_date, reverse=True)

    return {
        "posts": all_posts,
        "accounts_fetched": len(accounts),
        "total": len(all_posts),
        "warnings": warnings,
    }

# ==================== PAYMENTS ====================

PRICING = {
    "monthly": {"amount": 500.0, "currency": "INR", "duration": 30},
    "yearly": {"amount": 3000.0, "currency": "INR", "duration": 365},
    "creator": {"amount": 2400.0, "currency": "INR", "duration": 30},
    "pro": {"amount": 4100.0, "currency": "INR", "duration": 30}
}

class PaymentCheckoutResponse(BaseModel):
    session_id: str
    url: Optional[str] = None
    order_id: Optional[str] = None
    razorpay_key: Optional[str] = None
    approval_url: Optional[str] = None
    checkout_url: Optional[str] = None

@api_router.post("/payments/checkout", response_model=PaymentCheckoutResponse)
async def create_checkout(checkout_req: CheckoutRequest, request: Request, current_user: User = Depends(get_current_user)):
    if checkout_req.plan not in PRICING:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    plan_info = PRICING[checkout_req.plan]
    origin_url = request.headers.get("origin", FRONTEND_URL)
    
    if checkout_req.payment_method == "stripe":
        try:
            webhook_url = f"{origin_url}/api/webhook/stripe"
            stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
            
            success_url = f"{origin_url}/billing?session_id={{CHECKOUT_SESSION_ID}}"
            cancel_url = f"{origin_url}/billing"
            
            checkout_request = CheckoutSessionRequest(
                amount=plan_info["amount"],
                currency=plan_info["currency"].lower(),
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": current_user.user_id,
                    "plan": checkout_req.plan,
                    "email": current_user.email
                }
            )
            
            session = await stripe_checkout.create_checkout_session(checkout_request)
            
            transaction = PaymentTransaction(
                user_id=current_user.user_id,
                session_id=session.session_id,
                amount=plan_info["amount"],
                currency=plan_info["currency"],
                plan=checkout_req.plan,
                payment_method="stripe",
                payment_status="pending"
            )
            
            trans_dict = transaction.model_dump()
            trans_dict['created_at'] = trans_dict['created_at'].isoformat()
            trans_dict['updated_at'] = trans_dict['updated_at'].isoformat()
            
            await db.payment_transactions.insert_one(trans_dict)
            
            return PaymentCheckoutResponse(
                session_id=session.session_id,
                checkout_url=session.checkout_url,
                url=session.checkout_url
            )
        except Exception as e:
            logging.error(f"Stripe checkout error: {e}")
            raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")
    
    elif checkout_req.payment_method == "razorpay":
        if not razorpay_client:
            raise HTTPException(status_code=400, detail="Razorpay not configured. Add keys to backend/.env")
        
        try:
            amount_paise = int(plan_info["amount"] * 100)
            order_data = {
                "amount": amount_paise,
                "currency": plan_info["currency"],
                "payment_capture": 1
            }
            order = razorpay_client.order.create(data=order_data)
            
            transaction = PaymentTransaction(
                user_id=current_user.user_id,
                session_id=order['id'],
                amount=plan_info["amount"],
                currency=plan_info["currency"],
                plan=checkout_req.plan,
                payment_method="razorpay",
                payment_status="pending",
                metadata={"order_id": order['id']}
            )
            
            trans_dict = transaction.model_dump()
            trans_dict['created_at'] = trans_dict['created_at'].isoformat()
            trans_dict['updated_at'] = trans_dict['updated_at'].isoformat()
            
            await db.payment_transactions.insert_one(trans_dict)
            
            return PaymentCheckoutResponse(
                session_id=order['id'],
                order_id=order['id'],
                razorpay_key=razorpay_key_id
            )
        except Exception as e:
            logging.error(f"Razorpay order error: {e}")
            raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")
    
    elif checkout_req.payment_method == "paypal":
        if not paypal_client:
            raise HTTPException(status_code=400, detail="PayPal not configured. Add keys to backend/.env")
        
        try:
            request_obj = OrdersCreateRequest()
            request_obj.prefer('return=representation')
            request_obj.request_body = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": current_user.user_id,
                    "amount": {
                        "currency_code": "USD",
                        "value": str(round(plan_info["amount"] / 83, 2))
                    }
                }],
                "application_context": {
                    "return_url": f"{origin_url}/billing?session_id=PAYPAL",
                    "cancel_url": f"{origin_url}/billing"
                }
            }
            
            response = await asyncio.to_thread(paypal_client.execute, request_obj)
            
            order_id = response.result.id
            approve_url = None
            for link in response.result.links:
                if link.rel == "approve":
                    approve_url = link.href
                    break
            
            transaction = PaymentTransaction(
                user_id=current_user.user_id,
                session_id=order_id,
                amount=plan_info["amount"],
                currency=plan_info["currency"],
                plan=checkout_req.plan,
                payment_method="paypal",
                payment_status="pending"
            )
            
            trans_dict = transaction.model_dump()
            trans_dict['created_at'] = trans_dict['created_at'].isoformat()
            trans_dict['updated_at'] = trans_dict['updated_at'].isoformat()
            
            await db.payment_transactions.insert_one(trans_dict)
            
            return PaymentCheckoutResponse(
                session_id=order_id,
                approval_url=approve_url,
                url=approve_url
            )
        except Exception as e:
            logging.error(f"PayPal checkout error: {e}")
            raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")
    
    raise HTTPException(status_code=400, detail="Invalid payment method")

@api_router.get("/payments/status/{session_id}", response_model=CheckoutStatusResponse)
async def get_payment_status(session_id: str, current_user: User = Depends(get_current_user)):
    transaction = await db.payment_transactions.find_one({"session_id": session_id, "user_id": current_user.user_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction['payment_method'] == "stripe":
        try:
            webhook_url = ""
            stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
            status_response = await stripe_checkout.get_checkout_status(session_id)
            
            if status_response.payment_status == "paid" and transaction['payment_status'] != "paid":
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
                
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$set": {
                        "subscription_status": "active",
                        "subscription_plan": transaction['plan'],
                        "subscription_end_date": end_date.isoformat()
                    }}
                )
                
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            
            return status_response
        except Exception as e:
            logging.error(f"Stripe status check error: {e}")
            raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")
    
    return CheckoutStatusResponse(
        status=transaction['payment_status'],
        payment_status=transaction['payment_status'],
        amount_total=int(transaction['amount'] * 100),
        currency=transaction['currency'],
        metadata=transaction.get('metadata', {})
    )

@api_router.post("/payments/verify-razorpay")
async def verify_razorpay_payment(verify_req: RazorpayVerifyRequest, current_user: User = Depends(get_current_user)):
    if not razorpay_client:
        raise HTTPException(status_code=400, detail="Razorpay not configured")
        
    try:
        # Verify signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': verify_req.order_id,
            'razorpay_payment_id': verify_req.payment_id,
            'razorpay_signature': verify_req.signature
        })
        
        # Update transaction
        transaction = await db.payment_transactions.find_one({"session_id": verify_req.order_id})
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")
            
        if transaction['payment_status'] != "paid":
            plan_info = PRICING[transaction['plan']]
            end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
            
            await db.users.update_one(
                {"user_id": current_user.user_id},
                {"$set": {
                    "subscription_status": "active",
                    "subscription_plan": transaction['plan'],
                    "subscription_start_date": datetime.now(timezone.utc).isoformat(),
                    "subscription_end_date": end_date.isoformat()
                }}
            )
            
            await db.payment_transactions.update_one(
                {"session_id": verify_req.order_id},
                {"$set": {
                    "payment_status": "paid",
                    "payment_id": verify_req.payment_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
        return {"status": "success"}
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logging.error(f"Razorpay verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/payments/capture-paypal")
async def capture_paypal_payment(capture_req: PayPalCaptureBody, current_user: User = Depends(get_current_user)):
    if not paypal_client:
        raise HTTPException(status_code=400, detail="PayPal not configured")
        
    try:
        request = OrdersCaptureRequest(capture_req.order_id)
        response = await asyncio.to_thread(paypal_client.execute, request)
        
        if response.result.status == "COMPLETED":
            transaction = await db.payment_transactions.find_one({"session_id": capture_req.order_id})
            if transaction and transaction['payment_status'] != "paid":
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
                
                await db.users.update_one(
                    {"user_id": current_user.user_id},
                    {"$set": {
                        "subscription_status": "active",
                        "subscription_plan": transaction['plan'],
                        "subscription_start_date": datetime.now(timezone.utc).isoformat(),
                        "subscription_end_date": end_date.isoformat()
                    }}
                )
                
                await db.payment_transactions.update_one(
                    {"session_id": capture_req.order_id},
                    {"$set": {
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            return {"status": "success"}
        else:
            raise HTTPException(status_code=400, detail=f"Payment not completed. Status: {response.result.status}")
            
    except Exception as e:
        logging.error(f"PayPal capture error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    try:
        body = await request.body()
        signature = request.headers.get("Stripe-Signature", "")
        
        webhook_url = ""
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
        
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.event_type == "checkout.session.completed":
            session_id = webhook_response.session_id
            
            transaction = await db.payment_transactions.find_one({"session_id": session_id})
            if transaction and transaction['payment_status'] != "paid":
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
                
                await db.users.update_one(
                    {"user_id": transaction['user_id']},
                    {"$set": {
                        "subscription_status": "active",
                        "subscription_plan": transaction['plan'],
                        "subscription_start_date": datetime.now(timezone.utc).isoformat(),
                        "subscription_end_date": end_date.isoformat()
                    }}
                )
                
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
        
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}
# ==================== SUPPORT ROUTES ====================

@api_router.post("/support")
async def contact_support(
    to: str = Form(...),
    cc: Optional[str] = Form(None),
    subject: str = Form(...),
    body: str = Form(...),
    attachment: Optional[UploadFile] = File(None)
):
    """
    Handle support contact form with attachment.
    """
    logging.info(f"Support Request from User:")
    logging.info(f"To: {to}")
    logging.info(f"CC: {cc}")
    logging.info(f"Subject: {subject}")
    
    file_info = "No attachment"
    if attachment:
        file_info = await attachment.read()
        logging.info(f"Attachment: {attachment.filename} ({len(file_info)} bytes)")
    
    # Simulate email sending delay
    await asyncio.sleep(1)
    
    # If using Resend (and configured):
    if RESEND_API_KEY:
        try:
            email_params = {
                "from": SENDER_EMAIL,
                "to": ["support@socialentangler.com"],
                "subject": f"Support: {subject}",
                "html": f"<p><strong>CC:</strong> {cc}</p><p><strong>Body:</strong></p><pre>{body}</pre>"
            }
            
            # Note: Resend Python SDK attachments handling logic would go here
            # For now we just log it as we are likely in a dev env without real sending capability
                 
            await asyncio.to_thread(resend.Emails.send, email_params)
        except Exception as e:
            logging.error(f"Failed to send support email via Resend: {e}")
            
    return {"message": "Support request sent"}

# ==================== NOTIFICATIONS ====================

@api_router.get("/notifications", response_model=List[dict])
async def get_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    notifications = await db.notifications.find(
        {"user_id": current_user.user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return notifications

@api_router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": current_user.user_id},
        {"$set": {"read": True}}
    )
    return {"success": result.modified_count > 0}

@api_router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    result = await db.notifications.delete_one(
        {"notification_id": notification_id, "user_id": current_user.user_id}
    )
    return {"success": result.deleted_count > 0}

# ==================== SOCIAL ACCOUNTS ====================

@api_router.get("/stats")
async def get_stats(current_user: User = Depends(get_current_user)):
    total_posts = await db.posts.count_documents({"user_id": current_user.user_id})
    scheduled_posts = await db.posts.count_documents({"user_id": current_user.user_id, "status": "scheduled"})
    published_posts = await db.posts.count_documents({"user_id": current_user.user_id, "status": "published"})
    connected_accounts = await db.social_accounts.count_documents({
        "user_id": current_user.user_id, 
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]
    })
    
    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "connected_accounts": connected_accounts
    }

# ==================== API KEY MANAGEMENT ====================

@api_router.get("/keys")
async def list_api_keys(current_user: User = Depends(get_current_user)):
    keys = await db.api_keys.find({"user_id": current_user.user_id}).to_list(100)
    return [{
        "id": k["id"],
        "name": k["name"],
        "created_at": k["created_at"],
        "last_used_at": k.get("last_used_at")
    } for k in keys]

@api_router.post("/keys")
async def create_api_key(request: ApiKeyCreate, current_user: User = Depends(get_current_user)):
    raw_key = generate_api_key()
    new_key = ApiKey(
        user_id=current_user.user_id,
        name=request.name,
        key_hash=hash_api_key(raw_key)
    )
    await db.api_keys.insert_one(new_key.model_dump())
    return {
        "id": new_key.id,
        "name": new_key.name,
        "api_key": raw_key  # ONLY SHOWN ONCE
    }

@api_router.delete("/keys/{key_id}")
async def delete_api_key(key_id: str, current_user: User = Depends(get_current_user)):
    result = await db.api_keys.delete_one({"id": key_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"message": "API Key deleted"}

# ==================== HEADLESS AGENT API ====================

@api_router.get("/agent/channels")
async def agent_list_channels(current_user: User = Depends(get_api_key_user)):
    accounts = await db.social_accounts.find({"user_id": current_user.user_id}).to_list(100)
    return [{
        "id": acc["id"],
        "platform": acc["platform"],
        "name": acc["username"],
        "platform_username": acc.get("platform_username")
    } for acc in accounts]

@api_router.post("/agent/upload")
async def agent_upload_media(file: UploadFile = File(...), current_user: User = Depends(get_api_key_user)):
    url = await _handle_upload(file)
    return {"url": url, "filename": file.filename}

@api_router.post("/agent/posts")
async def agent_create_post(
    channel_id: str = Form(...),
    content: str = Form(...),
    media_urls: Optional[str] = Form(None), # Comma separated URLs
    scheduled_at: Optional[str] = Form(None),
    current_user: User = Depends(get_api_key_user)
):
    # Lookup account
    acc = await db.social_accounts.find_one({"id": channel_id, "user_id": current_user.user_id})
    if not acc:
        raise HTTPException(status_code=404, detail="Social account not found")

    post_id = str(uuid.uuid4())
    
    # Parse media_urls
    media_list = []
    if media_urls:
        media_list = [u.strip() for u in media_urls.split(",") if u.strip()]

    # Parse scheduled_time
    scheduled_time = None
    if scheduled_at:
        try:
             scheduled_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        except:
             pass

    post_data = {
        "id": post_id,
        "user_id": current_user.user_id,
        "content": content,
        "platforms": [acc["platform"]],
        "accounts": [channel_id],
        "media_urls": media_list,
        "scheduled_time": scheduled_time,
        "status": "scheduled" if scheduled_time else "published",
        "created_at": datetime.now(timezone.utc),
        "ai_generated": True
    }
    
    await db.posts.insert_one(post_data)
    
    # If not scheduled, trigger background publishing?
    # For now, let's assume the scheduler will pick it up or it's just "recorded"
    
    return {"success": True, "post_id": post_id}

# ==================== PUBLIC API v1 ====================
# Mirrors the Postiz-compatible public API under /api/public/v1/
# Authentication: X-API-Key header (same as agent endpoints)

public_router = APIRouter(prefix="/api/public/v1")

class PublicPostCreate(BaseModel):
    integration_id: str
    content: str
    media_urls: Optional[List[str]] = []
    scheduled_at: Optional[str] = None  # ISO 8601 UTC

@public_router.get("/is-connected")
async def public_is_connected(current_user: User = Depends(get_api_key_user)):
    """Verify that your API key is valid and active."""
    return {"connected": True}

@public_router.get("/integrations")
async def public_list_integrations(current_user: User = Depends(get_api_key_user)):
    """List all connected social media channels (integrations)."""
    accounts = await db.social_accounts.find({"user_id": current_user.user_id}).to_list(100)
    return [{
        "id": acc["id"],
        "name": acc.get("username", ""),
        "identifier": acc["platform"],
        "picture": acc.get("profile_picture_url"),
        "disabled": not acc.get("is_active", True),
        "profile": acc.get("platform_username", ""),
    } for acc in accounts]

@public_router.post("/upload")
async def public_upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_api_key_user)
):
    """Upload a media file (multipart/form-data). Returns id and path for use in posts."""
    url = await _handle_upload(file)
    media_id = str(uuid.uuid4())
    return {
        "id": media_id,
        "name": file.filename,
        "path": url,
    }

@public_router.post("/posts")
async def public_create_post(
    body: PublicPostCreate,
    current_user: User = Depends(get_api_key_user)
):
    """Create or schedule a post. Pass scheduled_at (ISO 8601 UTC) to schedule, or omit for immediate queue."""
    acc = await db.social_accounts.find_one({"id": body.integration_id, "user_id": current_user.user_id})
    if not acc:
        raise HTTPException(status_code=404, detail="Integration not found")

    post_id = str(uuid.uuid4())

    scheduled_time = None
    if body.scheduled_at:
        try:
            scheduled_time = datetime.fromisoformat(body.scheduled_at.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid scheduled_at format. Use ISO 8601 UTC.")

    post_data = {
        "id": post_id,
        "user_id": current_user.user_id,
        "content": body.content,
        "platforms": [acc["platform"]],
        "accounts": [body.integration_id],
        "media_urls": body.media_urls or [],
        "scheduled_time": scheduled_time,
        "status": "scheduled" if scheduled_time else "queue",
        "created_at": datetime.now(timezone.utc),
        "ai_generated": True,
    }
    await db.posts.insert_one(post_data)
    return {"postId": post_id, "integration": body.integration_id}

@public_router.get("/posts")
async def public_list_posts(
    startDate: str,
    endDate: str,
    current_user: User = Depends(get_api_key_user)
):
    """List posts within a date range. startDate and endDate must be ISO 8601 UTC strings."""
    try:
        start = datetime.fromisoformat(startDate.replace("Z", "+00:00"))
        end = datetime.fromisoformat(endDate.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 UTC.")

    posts = await db.posts.find({
        "user_id": current_user.user_id,
        "created_at": {"$gte": start, "$lte": end},
    }, {"_id": 0}).to_list(500)

    result = []
    for p in posts:
        result.append({
            "id": p["id"],
            "content": p.get("content", ""),
            "publishDate": p["scheduled_time"].isoformat() if p.get("scheduled_time") else p["created_at"].isoformat(),
            "releaseURL": p.get("release_url"),
            "state": p.get("status", "QUEUE").upper(),
            "integration": {
                "id": p["accounts"][0] if p.get("accounts") else None,
                "providerIdentifier": p["platforms"][0] if p.get("platforms") else None,
            },
        })
    return {"posts": result}

@public_router.delete("/posts/{post_id}")
async def public_delete_post(
    post_id: str,
    current_user: User = Depends(get_api_key_user)
):
    """Delete a post by its ID."""
    result = await db.posts.delete_one({"id": post_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"id": post_id}

# ==================== NOTIFICATIONS ====================

@api_router.get("/notifications")
async def get_notifications(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    notifications = await db.notifications.find(
        {"user_id": current_user.user_id}, 
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    for n in notifications:
        if isinstance(n.get('created_at'), str):
            n['created_at'] = datetime.fromisoformat(n['created_at'])
            
    return notifications

@api_router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    await db.notifications.update_one(
        {"id": notification_id, "user_id": current_user.user_id},
        {"$set": {"is_read": True}}
    )
    return {"message": "Marked as read"}

@api_router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    await db.notifications.delete_one(
        {"id": notification_id, "user_id": current_user.user_id}
    )
    return {"message": "Notification deleted"}

# ==================== CONTENT PAGES ====================

@api_router.get("/pages/terms")
async def get_terms():
    return {"content": "Terms of Service - SocialEntangler provides social media scheduling services..."}

@api_router.get("/pages/privacy")
async def get_privacy():
    return {"content": "Privacy Policy - We respect your privacy and protect your data..."}

@api_router.get("/oauth/youtube/authorize")
async def youtube_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate YouTube OAuth flow"""
    google_auth = GoogleAuth()
    
    # Generate random state and append return_to path
    base_state = str(uuid.uuid4())
    state = f"{base_state}:{returnTo}"
    
    auth_url = google_auth.get_auth_url(state)
    
    return {"authorization_url": auth_url, "state": state}

@api_router.post("/oauth/youtube/callback")
async def youtube_callback(request: Request, current_user: User = Depends(get_current_user)):
    """Handle YouTube OAuth callback"""
    try:
        body = await request.json()
        code = body.get('code')
        state = body.get('state')
        
        logging.info(f"[YouTube] Callback received for user {current_user.user_id}, state={state}")
        
        if not code:
            raise HTTPException(status_code=400, detail="No authorization code provided")
        
        google_auth = GoogleAuth()
        
        # 1. Exchange code for token
        logging.info(f"[YouTube] Exchanging code for token...")
        token_data = await google_auth.exchange_code_for_token(code, redirect_uri=google_auth.youtube_redirect_uri)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        if not access_token:
            logging.error(f"[YouTube] No access token returned from Google")
            raise HTTPException(status_code=400, detail="Failed to get access token from Google")
            
        # 2. Get Channel Info
        logging.info(f"[YouTube] Fetching channel info for user {current_user.user_id}...")
        channel_info = await google_auth.get_channel_info(access_token)
        channel_id = channel_info['id']
        snippet = channel_info['snippet']
        channel_title = snippet['title']
        picture_url = snippet.get('thumbnails', {}).get('default', {}).get('url')
        
        logging.info(f"[YouTube] Successfully fetched channel: {channel_title} ({channel_id})")
        
        # 3. Save to database
        account = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "platform": "youtube",
            "platform_user_id": channel_id,
            "platform_username": channel_title,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "picture_url": picture_url,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
        }

        await db.social_accounts.update_one(
            {"user_id": current_user.user_id, "platform": "youtube", "platform_user_id": channel_id},
            {"$set": account},
            upsert=True
        )

        # Patch any existing YouTube accounts that were saved without is_active
        await db.social_accounts.update_many(
            {"user_id": current_user.user_id, "platform": "youtube", "is_active": {"$exists": False}},
            {"$set": {"is_active": True}}
        )
        
        return {
            "success": True,
            "connected_accounts": [{"platform": "youtube", "name": channel_title}],
            "return_to": state.split(':')[-1] if state and ':' in state else 'accounts'
        }
            
    except Exception as e:
        logging.error(f"[YouTube] OAuth error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")

# ==================== FACEBOOK & INSTAGRAM OAUTH ====================

# State format: "userId|nonce|returnTo" — user_id embedded directly, no DB needed

def _make_oauth_state(user_id: str, return_to: str = "accounts") -> str:
    """Encode user_id + nonce into the state string so callbacks can identify the user"""
    nonce = str(uuid.uuid4()).replace("-", "")[:16]
    return f"{user_id}|{nonce}|{return_to}"

def _parse_oauth_state(state: str) -> tuple:
    """Parse state string → (user_id, return_to). Returns (None, 'accounts') on failure."""
    try:
        parts = state.split("|")
        if len(parts) >= 3:
            return parts[0], parts[2]
        # Legacy fallback (old uuid:returnTo format)
        if ":" in state:
            return None, state.split(":", 1)[-1]
    except Exception:
        pass
    return None, "accounts"

@api_router.get("/oauth/facebook/authorize")
async def facebook_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Facebook OAuth flow"""
    fb_auth = FacebookAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = fb_auth.get_auth_url(state)
    logging.info(f"[Facebook] Authorize for user {current_user.user_id}, state={state[:20]}...")
    return {"authorization_url": auth_url, "state": state}


@api_router.get("/oauth/instagram/authorize")
async def instagram_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Instagram Business Login (standalone)"""
    ig_auth = InstagramAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = ig_auth.get_auth_url(state)
    logging.info(f"[Instagram] Authorize for user {current_user.user_id}, state={state[:20]}...")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/facebook/callback")
async def facebook_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Facebook/Instagram OAuth callback (GET redirect from Meta)"""
    
    # If Meta returned an error, redirect to frontend with error
    if error or not code:
        error_msg = error or "No authorization code provided"
        logging.error(f"Facebook OAuth error from Meta: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")
    
    # --- Identify user from state string (user_id embedded directly) ---
    current_user = None
    user_id_from_state, return_to = _parse_oauth_state(state or "")
    logging.info(f"[Facebook] Callback state parsed: user_id={user_id_from_state}, return_to={return_to}")
    
    if user_id_from_state:
        user_doc = await db.users.find_one({"user_id": user_id_from_state}, {"_id": 0})
        if user_doc:
            if isinstance(user_doc.get("created_at"), str):
                user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
            if user_doc.get("subscription_end_date") and isinstance(user_doc["subscription_end_date"], str):
                user_doc["subscription_end_date"] = datetime.fromisoformat(user_doc["subscription_end_date"])
            try:
                current_user = User(**{k: v for k, v in user_doc.items() if k not in ["password", "_id"]})
            except Exception as e:
                logging.error(f"User model error: {e}")

    if not current_user:
        logging.error(f"Facebook OAuth callback: No authenticated user found for state={state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")
    
    fb_auth = FacebookAuth()
    
    try:
        logging.info(f"[Facebook] Exchanging code for token... Code length: {len(code)}")
        # 1. Exchange code for short-lived token
        token_data = await fb_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logging.error(f"[Facebook] No access token returned from Meta: {token_data}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=no_token")
        
        logging.info(f"[Facebook] Exchanging for long-lived token...")
        # 2. Get Long-Lived User Token (60 days)
        long_lived_data = await fb_auth.get_long_lived_token(access_token)
        long_lived_token = long_lived_data.get('access_token', access_token)
        
        logging.info(f"[Facebook] Fetching user profile...")
        # 3. Get personal Facebook profile (always saved as connected account)
        fb_profile = await fb_auth.get_user_profile(long_lived_token)
        fb_picture = fb_profile.get('picture', {}).get('data', {}).get('url') if isinstance(fb_profile.get('picture'), dict) else fb_profile.get('picture')
        
        logging.info(f"[Facebook] User profile fetched: {fb_profile.get('name')} (ID: {fb_profile.get('id')})")
        
        personal_account = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "platform": "facebook",
            "platform_user_id": fb_profile['id'],
            "username": fb_profile.get('name', 'Facebook User'),
            "platform_username": fb_profile.get('name', 'Facebook User'),
            "access_token": long_lived_token,
            "refresh_token": None,
            "token_expiry": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": fb_picture,
            "is_active": True,
            "account_type": "personal"
        }
        await db.social_accounts.update_one(
            {"user_id": current_user.user_id, "platform": "facebook", "platform_user_id": fb_profile['id']},
            {"$set": personal_account},
            upsert=True
        )
        connected_accounts = [{"platform": "facebook", "name": fb_profile.get('name', 'Facebook User')}]
        logging.info(f"[Facebook] Saved personal profile. Fetching pages...")

        # 4. Also get Pages and linked Instagram Business Accounts
        accounts_data = await fb_auth.get_accounts(long_lived_token)
        
        for acc in accounts_data:
            # Facebook Page
            picture_url = acc.get('picture', {}).get('data', {}).get('url')
            page_account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user.user_id,
                "platform": "facebook",
                "platform_user_id": acc['id'],
                "username": acc['name'],
                "platform_username": acc['name'],
                "access_token": acc['access_token'],
                "refresh_token": None,
                "token_expiry": None,
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "picture_url": picture_url,
                "is_active": True,
                "account_type": "page"
            }
            await db.social_accounts.update_one(
                {"user_id": current_user.user_id, "platform": "facebook", "platform_user_id": acc['id']},
                {"$set": page_account},
                upsert=True
            )
            connected_accounts.append({"platform": "facebook", "name": acc['name']})
            
            # Check for linked Instagram Business Account
            if 'instagram_business_account' in acc and acc['instagram_business_account']:
                ig_info = acc['instagram_business_account']
                ig_account = {
                    "id": str(uuid.uuid4()),
                    "user_id": current_user.user_id,
                    "platform": "instagram",
                    "platform_user_id": ig_info['id'],
                    "username": ig_info.get('username', 'Instagram User'),
                    "platform_username": ig_info.get('username', 'Instagram User'),
                    "access_token": acc['access_token'],
                    "refresh_token": None,
                    "token_expiry": None, 
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                    "picture_url": ig_info.get('profile_picture_url'),
                    "is_active": True
                }
                await db.social_accounts.update_one(
                    {"user_id": current_user.user_id, "platform": "instagram", "platform_user_id": ig_info['id']},
                    {"$set": ig_account},
                    upsert=True
                )
                connected_accounts.append({"platform": "instagram", "name": ig_info.get('username', 'Instagram User')})

        logging.info(f"Facebook OAuth success for user {current_user.user_id}: {connected_accounts}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms={','.join(c['platform'] for c in connected_accounts)}")
            
    except Exception as e:
        logging.error(f"Facebook OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== INSTAGRAM STANDALONE OAUTH ====================

@api_router.get("/oauth/instagram/callback")
async def instagram_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Instagram Business Login callback (standalone, no Facebook Page required)"""
    
    if error or not code:
        error_msg = error or "No authorization code provided"
        logging.error(f"Instagram OAuth error from Meta: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")
    
    # Identify user directly from state string
    current_user = None
    user_id_from_state, return_to = _parse_oauth_state(state or "")
    logging.info(f"[Instagram] Callback state parsed: user_id={user_id_from_state}, return_to={return_to}")
    
    if user_id_from_state:
        user_doc = await db.users.find_one({"user_id": user_id_from_state}, {"_id": 0})
        if user_doc:
            if isinstance(user_doc.get("created_at"), str):
                user_doc["created_at"] = datetime.fromisoformat(user_doc["created_at"])
            if user_doc.get("subscription_end_date") and isinstance(user_doc["subscription_end_date"], str):
                user_doc["subscription_end_date"] = datetime.fromisoformat(user_doc["subscription_end_date"])
            try:
                current_user = User(**{k: v for k, v in user_doc.items() if k not in ["password", "_id"]})
            except Exception as e:
                logging.error(f"User model error in Instagram callback: {e}")
    
    if not current_user:
        logging.error(f"Instagram callback: No authenticated user for state={state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")
    
    ig_auth = InstagramAuth()
    
    try:
        # 1. Exchange code for short-lived token
        token_data = await ig_auth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        ig_user_id = token_data.get("user_id") or token_data.get("id")
        
        if not access_token:
            logging.error(f"[Instagram] No access token in response: {token_data}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=no_token")
        
        # 2. Exchange for long-lived token (60 days)
        long_lived = await ig_auth.get_long_lived_token(access_token)
        long_lived_token = long_lived.get("access_token", access_token)
        
        # 3. Get user profile
        profile = await ig_auth.get_user_profile(long_lived_token)
        username = profile.get("username") or profile.get("name", "Instagram User")
        platform_user_id = profile.get("id") or str(ig_user_id)
        picture_url = profile.get("profile_picture_url")
        
        # 4. Save to DB
        ig_account = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "platform": "instagram",
            "platform_user_id": platform_user_id,
            "username": username,
            "platform_username": username,
            "access_token": long_lived_token,
            "refresh_token": None,
            "token_expiry": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": picture_url,
            "is_active": True,
            "account_type": "standalone"
        }
        
        await db.social_accounts.update_one(
            {"user_id": current_user.user_id, "platform": "instagram", "platform_user_id": platform_user_id},
            {"$set": ig_account},
            upsert=True
        )
        
        # Parse return_to from state
        return_to = "accounts"
        if state and ":" in state:
            return_to = state.split(":", 1)[-1]
        
        logging.info(f"Instagram standalone OAuth success for user {current_user.user_id}: @{username}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=instagram")
        
    except Exception as e:
        logging.error(f"Instagram standalone OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== LINKEDIN OAUTH ====================

@api_router.get("/oauth/linkedin/authorize")
async def linkedin_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate LinkedIn OAuth flow"""
    li_auth = LinkedInAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = li_auth.get_auth_url(state)
    logging.info(f"[LinkedIn] Authorize for user {current_user.user_id}, state={state[:20]}...")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/linkedin/callback")
async def linkedin_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle LinkedIn OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code provided"
            logging.error(f"[LinkedIn] OAuth error: {error_msg}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        # Identify user directly from state string
        user_id_from_state, return_to = _parse_oauth_state(state or "")
        logging.info(f"[LinkedIn] Callback received, user_id={user_id_from_state}, return_to={return_to}")
        
        if not user_id_from_state:
            logging.error(f"[LinkedIn] No user found in state: {state}")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")
            
        li_auth = LinkedInAuth()
        
        # 1. Exchange code for token
        logging.info(f"[LinkedIn] Exchanging code for token...")
        token_data = await li_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logging.error(f"[LinkedIn] No access token returned from LinkedIn: {token_data}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=no_token")
        
        # 2. Get User Profile
        logging.info(f"[LinkedIn] Fetching profile for user {user_id_from_state}...")
        profile = await li_auth.get_user_profile(access_token)
        
        # Handle profile data (LinkedIn returns 'sub' for OIDC, 'id' for legacy)
        li_user_id = profile.get('sub') or profile.get('id')
        if not li_user_id:
            logging.error(f"[LinkedIn] Profile missing ID: {profile}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=invalid_profile")
            
        user_name = profile.get('name') or f"{profile.get('given_name', '')} {profile.get('family_name', '')}".strip() or "LinkedIn User"
        picture_url = profile.get('picture')
        
        logging.info(f"[LinkedIn] Successfully fetched profile for: {user_name} ({li_user_id})")

        # 3. Save Account
        li_account = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_from_state,
            "platform": "linkedin",
            "platform_user_id": li_user_id,
            "username": user_name,
            "platform_username": user_name,
            "access_token": access_token,
            "refresh_token": token_data.get('refresh_token'),
            "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": picture_url,
            "is_active": True
        }
        
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "linkedin", "platform_user_id": li_user_id},
            {"$set": li_account},
            upsert=True
        )

        logging.info(f"[LinkedIn] Personal account saved for user {user_id_from_state}")

        # 4. Auto-save any LinkedIn Pages the user selected during OAuth
        # LinkedIn shows a native page selector when w_organization_social is requested.
        # After the user picks their pages there, we auto-save them — no extra modal needed.
        org_list = []
        try:
            org_list = await li_auth.fetch_organizations(access_token)
            logging.info(f"[LinkedIn] Found {len(org_list)} org page(s) for user {user_id_from_state}")
        except Exception as org_err:
            logging.warning(f"[LinkedIn] fetch_organizations error (non-fatal): {org_err}")

        connected_names = [li_account["platform_username"]]
        for org in org_list:
            org_account = {
                "id": str(uuid.uuid4()),
                "user_id": user_id_from_state,
                "platform": "linkedin",
                "platform_user_id": org["org_urn"],
                "platform_username": org["name"],
                "account_type": "page",
                "access_token": access_token,
                "refresh_token": token_data.get("refresh_token"),
                "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat(),
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "picture_url": org.get("logo_url"),
                "is_active": True,
            }
            await db.social_accounts.update_one(
                {"user_id": user_id_from_state, "platform": "linkedin", "platform_user_id": org["org_urn"]},
                {"$set": org_account},
                upsert=True,
            )
            connected_names.append(org["name"])
            logging.info(f"[LinkedIn] Auto-saved page: {org['name']} for user {user_id_from_state}")

        platform_label = ", ".join(connected_names) if len(connected_names) > 1 else "linkedin"
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms={platform_label}")
            
    except Exception as e:
        logging.error(f"[LinkedIn] Callback general error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ── LinkedIn Pages / Organizations ────────────────────────────────────────────

@api_router.get("/oauth/linkedin/pending-orgs")
async def linkedin_pending_orgs(current_user: User = Depends(get_current_user)):
    """Return LinkedIn org list stored during OAuth callback (if any)."""
    user_doc = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    orgs = user_doc.get("pending_linkedin_orgs", []) if user_doc else []
    return {"orgs": orgs}


class LinkedInOrgSave(BaseModel):
    org_ids: List[str]


@api_router.post("/oauth/linkedin/save-orgs")
async def linkedin_save_orgs(payload: LinkedInOrgSave, current_user: User = Depends(get_current_user)):
    """Save user-selected LinkedIn organization pages as social_accounts."""
    user_doc = await db.users.find_one({"user_id": current_user.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    all_orgs = user_doc.get("pending_linkedin_orgs", [])
    token = user_doc.get("pending_linkedin_token")
    selected = [o for o in all_orgs if o["org_id"] in payload.org_ids]

    for org in selected:
        org_account = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "platform": "linkedin",
            "platform_user_id": org["org_urn"],
            "platform_username": org["name"],
            "account_type": "page",
            "access_token": token,
            "refresh_token": None,
            "token_expiry": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": org.get("logo_url"),
            "is_active": True,
        }
        await db.social_accounts.update_one(
            {"user_id": current_user.user_id, "platform": "linkedin", "platform_user_id": org["org_urn"]},
            {"$set": org_account},
            upsert=True,
        )
        logging.info(f"[LinkedIn] Saved org page: {org['name']} for user {current_user.user_id}")

    # Clear pending state from user document
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$unset": {"pending_linkedin_orgs": "", "pending_linkedin_token": ""}}
    )
    return {"saved": len(selected)}


class LinkedInPageManual(BaseModel):
    page_id: str          # LinkedIn Company Page ID or vanity URL
    page_name: str        # Display name the user provides


@api_router.post("/oauth/linkedin/add-page")
async def linkedin_add_page_manually(payload: LinkedInPageManual, current_user: User = Depends(get_current_user)):
    """
    Manually add a LinkedIn Company Page account.
    The user provides their page ID/vanity name and we save it using
    their existing LinkedIn personal account token (w_organization_social scope).
    """
    # Find the user's existing LinkedIn personal account for the access token
    li_personal = await db.social_accounts.find_one(
        {"user_id": current_user.user_id, "platform": "linkedin", "account_type": {"$ne": "page"}},
        {"_id": 0}
    )
    if not li_personal:
        raise HTTPException(status_code=400, detail="Connect your LinkedIn personal account first.")

    access_token = li_personal.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="LinkedIn access token missing. Please reconnect.")

    # Normalise page_id: extract numeric ID from URL if user pasted a URL
    # e.g. https://www.linkedin.com/company/mycompany/ → "mycompany"
    page_id = payload.page_id.strip().rstrip("/")
    if "linkedin.com/company/" in page_id:
        page_id = page_id.split("linkedin.com/company/")[-1].split("/")[0]

    # Build the org URN
    org_urn = f"urn:li:organization:{page_id}" if page_id.isdigit() else f"urn:li:organizationBrand:{page_id}"

    page_account = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.user_id,
        "platform": "linkedin",
        "platform_user_id": org_urn,
        "platform_username": payload.page_name or f"LinkedIn Page ({page_id})",
        "account_type": "page",
        "access_token": access_token,
        "refresh_token": None,
        "token_expiry": None,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "picture_url": None,
        "is_active": True,
    }
    await db.social_accounts.update_one(
        {"user_id": current_user.user_id, "platform": "linkedin", "platform_user_id": org_urn},
        {"$set": page_account},
        upsert=True,
    )
    logging.info(f"[LinkedIn] Manually added page {page_id} ({payload.page_name}) for user {current_user.user_id}")
    return {"success": True, "page_id": page_id, "name": payload.page_name}


# ==================== THREADS OAUTH ====================

@api_router.get("/oauth/threads/authorize")
async def threads_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Threads OAuth flow"""
    th_auth = ThreadsAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = th_auth.get_auth_url(state)
    logging.info(f"[Threads] Authorize for user {current_user.user_id}")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/threads/callback")
async def threads_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Threads OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code provided"
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        user_id_from_state, return_to = _parse_oauth_state(state or "")
        if not user_id_from_state:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

        th_auth = ThreadsAuth()
        token_data = await th_auth.exchange_code_for_token(code)
        short_token = token_data.get("access_token")

        # Exchange for long-lived token
        long_token_data = await th_auth.get_long_lived_token(short_token)
        access_token = long_token_data.get("access_token", short_token)

        profile = await th_auth.get_user_profile(access_token)
        th_account = {
            "id":               str(uuid.uuid4()),
            "user_id":          user_id_from_state,
            "platform":         "threads",
            "platform_user_id": str(profile.get("id", "")),
            "username":         profile.get("name") or profile.get("username", "Threads User"),
            "platform_username": profile.get("username") or profile.get("name", "threads_user"),
            "access_token":     access_token,
            "refresh_token":    None,
            "connected_at":     datetime.now(timezone.utc).isoformat(),
            "picture_url":      profile.get("threads_profile_picture_url"),
            "is_active":        True,
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "threads", "platform_user_id": th_account["platform_user_id"]},
            {"$set": th_account},
            upsert=True,
        )
        logging.info(f"[Threads] Connected: {th_account['platform_username']} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=threads")

    except Exception as e:
        logging.error(f"[Threads] Callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== REDDIT OAUTH ====================

@api_router.get("/oauth/reddit/authorize")
async def reddit_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Reddit OAuth flow"""
    rd_auth = RedditAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = rd_auth.get_auth_url(state)
    logging.info(f"[Reddit] Authorize for user {current_user.user_id}")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/reddit/callback")
async def reddit_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Reddit OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code provided"
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        user_id_from_state, return_to = _parse_oauth_state(state or "")
        if not user_id_from_state:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

        rd_auth = RedditAuth()
        token_data = await rd_auth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        profile = await rd_auth.get_user_profile(access_token)
        rd_account = {
            "id":               str(uuid.uuid4()),
            "user_id":          user_id_from_state,
            "platform":         "reddit",
            "platform_user_id": str(profile.get("id", "")),
            "username":         profile.get("name", "Reddit User"),
            "platform_username": profile.get("name", "reddit_user"),
            "access_token":     access_token,
            "refresh_token":    refresh_token,
            "connected_at":     datetime.now(timezone.utc).isoformat(),
            "picture_url":      profile.get("icon_img", "").split("?")[0] or None,
            "is_active":        True,
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "reddit", "platform_user_id": rd_account["platform_user_id"]},
            {"$set": rd_account},
            upsert=True,
        )
        logging.info(f"[Reddit] Connected: {rd_account['platform_username']} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=reddit")

    except Exception as e:
        logging.error(f"[Reddit] Callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== PINTEREST OAUTH ====================

@api_router.get("/oauth/pinterest/authorize")
async def pinterest_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Pinterest OAuth flow"""
    pt_auth = PinterestAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = pt_auth.get_auth_url(state)
    logging.info(f"[Pinterest] Authorize for user {current_user.user_id}")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/pinterest/callback")
async def pinterest_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Pinterest OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code provided"
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        user_id_from_state, return_to = _parse_oauth_state(state or "")
        if not user_id_from_state:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

        pt_auth = PinterestAuth()
        token_data = await pt_auth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        profile = await pt_auth.get_user_profile(access_token)
        pt_account = {
            "id":               str(uuid.uuid4()),
            "user_id":          user_id_from_state,
            "platform":         "pinterest",
            "platform_user_id": str(profile.get("id", "")),
            "username":         profile.get("username", "Pinterest User"),
            "platform_username": profile.get("username", "pinterest_user"),
            "access_token":     access_token,
            "refresh_token":    refresh_token,
            "token_expiry": (datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat(),
            "connected_at":     datetime.now(timezone.utc).isoformat(),
            "picture_url":      profile.get("profile_image"),
            "is_active":        True,
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "pinterest", "platform_user_id": pt_account["platform_user_id"]},
            {"$set": pt_account},
            upsert=True,
        )
        logging.info(f"[Pinterest] Connected: {pt_account['platform_username']} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=pinterest")

    except Exception as e:
        logging.error(f"[Pinterest] Callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== SNAPCHAT OAUTH ====================

@api_router.get("/oauth/snapchat/authorize")
async def snapchat_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate Snapchat OAuth flow"""
    sc_auth = SnapchatAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    auth_url = sc_auth.get_auth_url(state)
    logging.info(f"[Snapchat] Authorize for user {current_user.user_id}")
    return {"authorization_url": auth_url, "state": state}

@api_router.get("/oauth/snapchat/callback")
async def snapchat_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Snapchat OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code provided"
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        user_id_from_state, return_to = _parse_oauth_state(state or "")
        if not user_id_from_state:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

        sc_auth = SnapchatAuth()
        token_data = await sc_auth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        profile = await sc_auth.get_user_profile(access_token)
        sc_account = {
            "id":               str(uuid.uuid4()),
            "user_id":          user_id_from_state,
            "platform":         "snapchat",
            "platform_user_id": str(profile.get("id", "")),
            "username":         profile.get("name", "Snapchat User"),
            "platform_username": profile.get("username") or profile.get("name", "snapchat_user"),
            "access_token":     access_token,
            "refresh_token":    refresh_token,
            "connected_at":     datetime.now(timezone.utc).isoformat(),
            "picture_url":      profile.get("picture_url"),
            "is_active":        True,
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "snapchat", "platform_user_id": sc_account["platform_user_id"]},
            {"$set": sc_account},
            upsert=True,
        )
        logging.info(f"[Snapchat] Connected: {sc_account['platform_username']} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=snapchat")

    except Exception as e:
        logging.error(f"[Snapchat] Callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== TIKTOK OAUTH ====================

@api_router.get("/oauth/tiktok/authorize")
async def tiktok_authorize(returnTo: Optional[str] = "accounts", current_user: User = Depends(get_current_user)):
    """Initiate TikTok OAuth flow (returns URL + PKCE verifier)"""
    tt_auth = TikTokAuth()
    state = _make_oauth_state(current_user.user_id, returnTo)
    result = tt_auth.get_auth_url(state)
    # Store PKCE verifier in a short-lived DB record
    await db.oauth_pkce.update_one(
        {"user_id": current_user.user_id, "platform": "tiktok"},
        {"$set": {"verifier": result["verifier"], "created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"authorization_url": result["url"], "state": state}

@api_router.get("/oauth/tiktok/callback")
async def tiktok_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle TikTok OAuth callback"""
    try:
        if error or not code:
            error_msg = error or "No authorization code"
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

        user_id_from_state, return_to = _parse_oauth_state(state or "")
        if not user_id_from_state:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

        pkce_doc = await db.oauth_pkce.find_one({"user_id": user_id_from_state, "platform": "tiktok"})
        verifier = pkce_doc.get("verifier", "") if pkce_doc else ""

        tt_auth = TikTokAuth()
        token_data = await tt_auth.exchange_code_for_token(code, verifier)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        open_id = token_data.get("open_id", "")

        profile = await tt_auth.get_user_profile(access_token)
        tt_account = {
            "id":                str(uuid.uuid4()),
            "user_id":           user_id_from_state,
            "platform":          "tiktok",
            "platform_user_id":  open_id or profile.get("id", ""),
            "username":          profile.get("username", "TikTok User"),
            "platform_username": profile.get("username", "tiktok_user"),
            "access_token":      access_token,
            "refresh_token":     refresh_token,
            "connected_at":      datetime.now(timezone.utc).isoformat(),
            "picture_url":       profile.get("picture_url"),
            "is_active":         True,
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "tiktok", "platform_user_id": tt_account["platform_user_id"]},
            {"$set": tt_account},
            upsert=True,
        )
        await db.oauth_pkce.delete_one({"user_id": user_id_from_state, "platform": "tiktok"})
        logging.info(f"[TikTok] Connected: {tt_account['platform_username']} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=tiktok")

    except Exception as e:
        logging.error(f"[TikTok] Callback error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== BLUESKY AUTH ====================

class BlueskyConnectRequest(BaseModel):
    handle: str      # e.g. user.bsky.social
    app_password: str

@api_router.post("/oauth/bluesky/connect")
async def bluesky_connect(body: BlueskyConnectRequest, current_user: User = Depends(get_current_user)):
    """Connect a Bluesky account via handle + app password."""
    bs_auth = BlueskyAuth()
    try:
        session = await bs_auth.create_session(body.handle, body.app_password)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    did = session.get("did", "")
    access_token = session.get("accessJwt", "")
    refresh_token = session.get("refreshJwt", "")

    profile = await bs_auth.get_user_profile(access_token, did)

    bs_account = {
        "id":                str(uuid.uuid4()),
        "user_id":           current_user.user_id,
        "platform":          "bluesky",
        "platform_user_id":  did,
        "username":          profile.get("username", body.handle),
        "platform_username": profile.get("username", body.handle),
        "access_token":      access_token,
        "refresh_token":     refresh_token,
        "connected_at":      datetime.now(timezone.utc).isoformat(),
        "picture_url":       profile.get("picture_url"),
        "is_active":         True,
    }
    await db.social_accounts.update_one(
        {"user_id": current_user.user_id, "platform": "bluesky", "platform_user_id": did},
        {"$set": bs_account},
        upsert=True,
    )
    logging.info(f"[Bluesky] Connected: {bs_account['platform_username']} for user {current_user.user_id}")
    bs_account.pop("_id", None)
    return {"ok": True, "account": bs_account}

# ==================== TEAM MEMBERS ====================

class TeamInviteCreate(BaseModel):
    email: str
    role: str = "member"   # owner | admin | member | viewer

@api_router.get("/team/members")
async def get_team_members(current_user: User = Depends(get_current_user)):
    members = await db.team_members.find(
        {"owner_user_id": current_user.user_id}, {"_id": 0}
    ).sort("invited_at", -1).to_list(100)
    return members

class AcceptInviteRequest(BaseModel):
    token: str

@api_router.post("/team/invite", status_code=201)
async def invite_team_member(body: TeamInviteCreate, current_user: User = Depends(get_current_user)):
    existing = await db.team_members.find_one(
        {"owner_user_id": current_user.user_id, "email": body.email.lower(), "status": "pending"}
    )
    if existing:
        raise HTTPException(status_code=400, detail="A pending invite already exists for this email")
    now = datetime.now(timezone.utc)
    invite_token = str(uuid.uuid4())
    expires_at = now + timedelta(days=7)
    member = {
        "id":                   str(uuid.uuid4()),
        "owner_user_id":        current_user.user_id,
        "email":                body.email.lower().strip(),
        "role":                 body.role,
        "status":               "pending",
        "invited_at":           now.isoformat(),
        "accepted_at":          None,
        "invite_token":         invite_token,
        "expires_at":           expires_at.isoformat(),
        "can_approve":          False,
        "assigned_account_ids": [],
    }
    await db.team_members.insert_one(member)
    member.pop("_id", None)
    # Send invitation email (non-fatal)
    email_sent = await send_team_invite_email(
        invite_email=body.email.lower().strip(),
        owner_name=current_user.name,
        role=body.role,
        invite_token=invite_token,
        expires_at=expires_at,
    )
    return {**member, "email_sent": email_sent}

@api_router.patch("/team/members/{member_id}")
async def update_team_member(member_id: str, body: dict, current_user: User = Depends(get_current_user)):
    update = {}
    if "role" in body:
        update["role"] = body["role"]
    if "can_approve" in body:
        update["can_approve"] = bool(body["can_approve"])
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    result = await db.team_members.update_one(
        {"id": member_id, "owner_user_id": current_user.user_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"ok": True}

@api_router.delete("/team/members/{member_id}")
async def remove_team_member(member_id: str, current_user: User = Depends(get_current_user)):
    await db.team_members.delete_one(
        {"id": member_id, "owner_user_id": current_user.user_id}
    )
    return {"ok": True}

@api_router.get("/team/check-invite")
async def check_invite_token(token: str):
    """Public endpoint — returns invite details for the AcceptInvite page (no auth required)."""
    invite_doc = await db.team_members.find_one({"invite_token": token}, {"_id": 0, "invite_token": 0})
    if not invite_doc:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    if invite_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is {invite_doc.get('status', 'invalid')}")
    # Check expiry
    expires_at_raw = invite_doc.get("expires_at")
    if expires_at_raw:
        expires_at = datetime.fromisoformat(expires_at_raw) if isinstance(expires_at_raw, str) else expires_at_raw
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invite has expired")
    # Look up owner name
    owner_doc = await db.users.find_one({"user_id": invite_doc["owner_user_id"]}, {"name": 1, "email": 1})
    owner_name = owner_doc.get("name", "Someone") if owner_doc else "Someone"
    # Check if invitee already has an account
    existing_user = await db.users.find_one({"email": invite_doc["email"]})
    return {
        "email":      invite_doc["email"],
        "role":       invite_doc["role"],
        "owner_name": owner_name,
        "expires_at": expires_at_raw,
        "user_exists": existing_user is not None,
    }

@api_router.post("/auth/accept-invite")
async def accept_invite(body: AcceptInviteRequest, current_user: User = Depends(get_current_user)):
    """Authenticated — called after login/signup on the AcceptInvite page."""
    invite_doc = await db.team_members.find_one({"invite_token": body.token})
    if not invite_doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is already {invite_doc.get('status', 'invalid')}")
    # Enforce email match
    if invite_doc["email"].lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="This invite was sent to a different email address")
    # Check expiry
    expires_at_raw = invite_doc.get("expires_at")
    if expires_at_raw:
        expires_at = datetime.fromisoformat(expires_at_raw) if isinstance(expires_at_raw, str) else expires_at_raw
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invite has expired")
    now = datetime.now(timezone.utc)
    await db.team_members.update_one(
        {"invite_token": body.token},
        {"$set": {
            "status":         "accepted",
            "accepted_at":    now.isoformat(),
            "member_user_id": current_user.user_id,
        }}
    )
    return {
        "message":            "Invite accepted",
        "workspace_owner_id": invite_doc["owner_user_id"],
        "role":               invite_doc["role"],
    }

@api_router.patch("/team/members/{member_id}/accounts")
async def assign_member_accounts(member_id: str, body: dict, current_user: User = Depends(get_current_user)):
    """Owner assigns which social accounts a team member can access."""
    account_ids = body.get("account_ids", [])
    if not isinstance(account_ids, list):
        raise HTTPException(status_code=400, detail="account_ids must be a list")
    # Verify all provided account IDs actually belong to the owner
    if account_ids:
        owned = await db.social_accounts.find(
            {"user_id": current_user.user_id, "id": {"$in": account_ids}},
            {"id": 1}
        ).to_list(200)
        owned_ids = {a["id"] for a in owned}
        invalid = [a for a in account_ids if a not in owned_ids]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Some account IDs do not belong to you: {invalid}")
    result = await db.team_members.update_one(
        {"id": member_id, "owner_user_id": current_user.user_id},
        {"$set": {"assigned_account_ids": account_ids}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Team member not found")
    return {"ok": True, "assigned_account_ids": account_ids}

@api_router.post("/team/resend-invite/{invite_id}")
async def resend_team_invite(invite_id: str, current_user: User = Depends(get_current_user)):
    """Owner resends an existing invite — generates a new token and resets the 7-day expiry."""
    invite_doc = await db.team_members.find_one({"id": invite_id, "owner_user_id": current_user.user_id})
    if not invite_doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite_doc.get("status") == "accepted":
        raise HTTPException(status_code=400, detail="Cannot resend an accepted invite")
    new_token = str(uuid.uuid4())
    new_expires = datetime.now(timezone.utc) + timedelta(days=7)
    await db.team_members.update_one(
        {"id": invite_id},
        {"$set": {
            "invite_token": new_token,
            "expires_at":   new_expires.isoformat(),
            "status":       "pending",
            "invited_at":   datetime.now(timezone.utc).isoformat(),
        }}
    )
    email_sent = await send_team_invite_email(
        invite_email=invite_doc["email"],
        owner_name=current_user.name,
        role=invite_doc["role"],
        invite_token=new_token,
        expires_at=new_expires,
    )
    return {"ok": True, "message": "Invite resent", "email_sent": email_sent}

# ==================== SCHEDULED POST PROCESSOR ====================

async def process_scheduled_posts():
    """Background job to publish scheduled posts and expire overdue pending-review posts."""
    try:
        now = datetime.now(timezone.utc)

        # Mark pending-review posts whose scheduled_time has passed as expired_approval
        expired_reviews = await db.posts.find({
            "status": "pending_review",
            "scheduled_time": {"$lte": now.isoformat(), "$ne": None},
        }, {"id": 1}).to_list(100)
        if expired_reviews:
            expired_ids = [p["id"] for p in expired_reviews]
            await db.posts.update_many(
                {"id": {"$in": expired_ids}},
                {"$set": {"status": "expired_approval"}},
            )
            logging.info(f"Marked {len(expired_ids)} posts as expired_approval")

        posts = await db.posts.find({
            "status": "scheduled",
            "scheduled_time": {"$lte": now.isoformat()}
        }).to_list(100)
        
        fb_auth = FacebookAuth()
        google_auth = GoogleAuth()
        tw_auth = TwitterAuth()
        li_auth = LinkedInAuth()
        
        for post_doc in posts:
            post_id = post_doc['id']
            user_id = post_doc['user_id']

            # Idempotency: skip if already published (guard against double-processing)
            if post_doc.get("status") == "published":
                logging.info(f"Post {post_id} already published, skipping (idempotency guard)")
                continue

            # Atomic claim: set status to "processing" to prevent duplicate execution
            claim_result = await db.posts.update_one(
                {"id": post_id, "status": "scheduled"},  # only claim if still scheduled
                {"$set": {"status": "processing", "processing_started_at": datetime.now(timezone.utc).isoformat()}}
            )
            if claim_result.modified_count == 0:
                # Another worker already claimed this post
                logging.info(f"Post {post_id} already claimed by another worker, skipping")
                continue

            media_url = post_doc.get('media_urls', [])[0] if post_doc.get('media_urls') else None
            # IMPORTANT: For local files, we need the absolute path for YouTube
            # For FB/IG, we need a public URL. 
            # If media_url starts with '/', it's a local path.
            # We need to construct a public URL if possible (e.g. using ngrok or the server's public IP)
            # OR for this MVP, we assume the user has configured the server to serve static files.
            
            # Assuming backend is serving static files from /uploads
            # public_media_url = f"{process.env.BACKEND_URL}{media_url}" 
            # This part is tricky without a real domain.
            # But let's proceed assuming we have basic logic.
            
            # Only support single media for now
            if not media_url:
                continue

            # Media URL is now likely a Firebase Storage URL (Public)
            # No need to construct public URL manually if it starts with http
            if media_url.startswith("http"):
                public_url = media_url
            else:
                 # Legacy/Local fallback
                 service_url = os.environ.get("SERVICE_URL", "https://postflow-25.preview.emergentagent.com")
                 public_url = f"{service_url}{media_url}"


            accounts = post_doc.get('accounts', [])
            has_error = False
            error_details = []

            # Per-platform independent results tracking
            platform_results = post_doc.get("platform_results") or {}
            platform_errors = {}
            platform_successes = {}

            for account_id in accounts:
                # Fetch full account details to get token
                account = await db.social_accounts.find_one({"id": account_id})
                if not account:
                    platform_errors[account_id] = "Account not found"
                    continue

                platform = account['platform']
                token = account['access_token']
                platform_user_id = account['platform_user_id']

                # Skip if this platform already published successfully (idempotency)
                if platform_results.get(platform, {}).get("status") == "published":
                    platform_successes[platform] = platform_results[platform]
                    continue

                try:
                    # Download file locally if it's a remote URL (Firebase) and we need to upload FILE (YouTube/LinkedIn)
                    temp_file_path = None
                    cover_temp_path = None
                    local_cover_path = None
                    local_file_path = None
                    if media_url and platform in ['youtube', 'linkedin']:
                         if media_url.startswith("http"):
                             import tempfile
                             
                             if "localhost:" in media_url or "127.0.0.1:" in media_url:
                                 from urllib.parse import urlparse
                                 parsed_url = urlparse(media_url)
                                 local_file_path = os.path.join(ROOT_DIR, parsed_url.path.lstrip("/"))
                             else:
                                 import httpx
                                 # Download to temp file asynchronously
                                 with tempfile.NamedTemporaryFile(delete=False, suffix=f".{media_url.split('?')[0].split('.')[-1]}") as tmp:
                                     async with httpx.AsyncClient() as client:
                                         response = await client.get(media_url)
                                         tmp.write(response.content)
                                     temp_file_path = tmp.name
                                     local_file_path = tmp.name
                         else:
                             local_file_path = os.path.join(ROOT_DIR, media_url.lstrip("/"))
                         
                         # Download cover image if present
                         cover_url = post_doc.get("cover_image_url")
                         if cover_url and cover_url.startswith("http"):
                             if "localhost:" in cover_url or "127.0.0.1:" in cover_url:
                                 from urllib.parse import urlparse
                                 parsed_cover = urlparse(cover_url)
                                 local_cover_path = os.path.join(ROOT_DIR, parsed_cover.path.lstrip("/"))
                             else:
                                 import httpx
                                 with tempfile.NamedTemporaryFile(delete=False, suffix=f".{cover_url.split('?')[0].split('.')[-1]}") as img_tmp:
                                     async with httpx.AsyncClient() as client:
                                         img_resp = await client.get(cover_url)
                                         img_tmp.write(img_resp.content)
                                     cover_temp_path = img_tmp.name
                                     local_cover_path = img_tmp.name
                    if platform == 'facebook':
                        fb_caption = post_doc.get('platform_specific_content', {}).get('facebook', post_doc.get('content', ''))
                        logging.info(f"Publishing to FB: {platform_user_id} with url {public_url}")
                        await fb_auth.publish_to_facebook(
                            access_token=token,
                            page_id=platform_user_id,
                            media_url=public_url,
                            message=fb_caption,
                            media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                        )
                    elif platform == 'instagram':
                        ig_caption = post_doc.get('platform_specific_content', {}).get('instagram', post_doc.get('content', ''))
                        logging.info(f"Publishing to IG: {platform_user_id} with url {public_url}")
                        
                        if account.get('account_type') == 'standalone':
                            from app.social.instagram import InstagramAuth
                            ig_auth = InstagramAuth()
                            await ig_auth.publish_to_instagram(
                                access_token=token,
                                ig_user_id=platform_user_id,
                                media_url=public_url,
                                caption=ig_caption,
                                media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                            )
                        else:
                            try:
                                await fb_auth.publish_to_instagram(
                                    access_token=token,
                                    ig_user_id=platform_user_id,
                                    media_url=public_url,
                                    caption=ig_caption,
                                    media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                                )
                            except Exception as e:
                                logging.info(f"Fallback to standalone IG API: {e}")
                                from app.social.instagram import InstagramAuth
                                ig_auth = InstagramAuth()
                                await ig_auth.publish_to_instagram(
                                    access_token=token,
                                    ig_user_id=platform_user_id,
                                    media_url=public_url,
                                    caption=ig_caption,
                                    media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                                )
                    elif platform == 'youtube':
                        if local_file_path and os.path.exists(local_file_path):
                            try:
                                raw_title = post_doc.get('youtube_title') or post_doc.get('video_title') or post_doc.get('content') or 'New Video'
                                safe_title = raw_title[:100] if isinstance(raw_title, str) else 'New Video'
                                await google_auth.upload_video(
                                    access_token=token,
                                    file_path=local_file_path,
                                    title=safe_title,
                                    description=post_doc.get('content') or '',
                                    privacy_status=post_doc.get('youtube_privacy') or 'public',
                                    cover_image_path=local_cover_path
                                )
                            except ValueError as e:
                                if "AuthError" in str(e) and account.get('refresh_token'):
                                    logging.info(f"YouTube token expired for account {account_id}, attempting refresh...")
                                    try:
                                        # Refresh token
                                        new_token_data = await google_auth.refresh_access_token(account['refresh_token'])
                                        new_access_token = new_token_data['access_token']
                                        
                                        # Save new token to DB
                                        await db.social_accounts.update_one(
                                            {"id": account_id},
                                            {"$set": {"access_token": new_access_token}}
                                        )
                                        
                                        # Retry upload immediately
                                        await google_auth.upload_video(
                                            access_token=new_access_token,
                                            file_path=local_file_path,
                                            title=safe_title,
                                            description=post_doc.get('content') or '',
                                            privacy_status=post_doc.get('youtube_privacy') or 'public',
                                            cover_image_path=local_cover_path
                                        )
                                    except Exception as refresh_err:
                                        raise Exception(f"Token refresh and seamless retry failed: {str(refresh_err)}")
                                else:
                                    raise e
                            # Clean up temp file
                            if temp_file_path:
                                os.unlink(temp_file_path)
                            if cover_temp_path:
                                os.unlink(cover_temp_path)
                        else:
                            logging.error(f"Cannot upload to YouTube: Local file not found {local_file_path}")
                    elif platform == 'twitter':
                        tw_caption = post_doc.get('platform_specific_content', {}).get('twitter', post_doc.get('content', ''))
                        await tw_auth.publish_tweet(
                            access_token=token,
                            text=tw_caption,
                            media_urls=[public_url] if media_url else None
                        )
                    elif platform == 'linkedin':
                        li_caption = post_doc.get('platform_specific_content', {}).get('linkedin', post_doc.get('content', ''))
                        await li_auth.publish_post(
                            access_token=token,
                            person_urn=platform_user_id,
                            text=li_caption,
                            media_urls=[public_url] if media_url else None,
                            local_file_path=local_file_path if media_url else None
                        )

                    # Record per-platform success
                    platform_successes[platform] = {
                        "status": "published",
                        "account_id": account_id,
                        "published_at": datetime.now(timezone.utc).isoformat(),
                    }
                    platform_results[platform] = platform_successes[platform]

                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Failed to publish to {platform}: {error_msg}")
                    has_error = True
                    error_details.append(f"{platform}: {error_msg}")
                    platform_errors[platform] = error_msg
                    platform_results[platform] = {
                        "status": "failed",
                        "account_id": account_id,
                        "error": error_msg[:500],
                        "retry_count": post_doc.get("retry_count", 0) + 1,
                    }
                    # Continue attempting next account
            
            # Evaluate attempt success and manage retries/notifications
            # Stage 1.6: per-platform independent execution — partial success counts as published
            now_iso = datetime.now(timezone.utc).isoformat()
            if platform_successes and platform_errors:
                # Partial success — at least one platform published; treat as success
                logging.warning(
                    f"Post {post_id}: partial publish. "
                    f"Success: {list(platform_successes)}, Failed: {list(platform_errors)}"
                )
                has_error = False
            if has_error:
                retry_count = post_doc.get("retry_count", 0) + 1
                if retry_count >= 3:
                    # Definitive failure after 3 attempts
                    status_history_entry = {
                        "status": "failed",
                        "at": now_iso,
                        "note": f"Attempt {retry_count}/3 failed: {' | '.join(error_details)[:200]}",
                    }
                    await db.posts.update_one(
                        {"id": post_id},
                        {
                            "$set": {
                                "status": "failed",
                                "retry_count": retry_count,
                                "error": " | ".join(error_details),
                                "platform_results": platform_results,
                            },
                            "$push": {"status_history": status_history_entry},
                        }
                    )
                    # Create Error Notification
                    await db.notifications.insert_one(Notification(
                        user_id=user_id,
                        post_id=post_id,
                        type="error",
                        message=f"Post failed after 3 attempts: {' | '.join(error_details)}"
                    ).model_dump())
                    logging.info(f"Post {post_id} definitively failed. Cleaning up.")
                    # File Cleanup
                    if media_url and "/uploads/" in media_url:
                        from urllib.parse import urlparse
                        local_path = os.path.join(ROOT_DIR, urlparse(media_url).path.lstrip("/"))
                        if os.path.exists(local_path):
                            try: os.remove(local_path)
                            except: pass

                    cover_url = post_doc.get("cover_image_url")
                    if cover_url and "/uploads/" in cover_url:
                        from urllib.parse import urlparse
                        local_cover_path = os.path.join(ROOT_DIR, urlparse(cover_url).path.lstrip("/"))
                        if os.path.exists(local_cover_path):
                            try: os.remove(local_cover_path)
                            except: pass
                else:
                    # Schedule a retry 5 minutes from now
                    next_attempt = now + timedelta(minutes=5)
                    status_history_entry = {
                        "status": "retry_scheduled",
                        "at": now_iso,
                        "note": f"Attempt {retry_count}/3 failed: {' | '.join(error_details)[:200]}",
                    }
                    await db.posts.update_one(
                        {"id": post_id},
                        {
                            "$set": {
                                "status": "scheduled",
                                "retry_count": retry_count,
                                "scheduled_time": next_attempt.isoformat(),
                                "platform_results": platform_results,
                            },
                            "$push": {"status_history": status_history_entry},
                        }
                    )
                    logging.info(f"Post {post_id} failed attempt {retry_count}. Retrying at {next_attempt.isoformat()}.")
            else:
                # Definitive Success (all platforms or partial — at least one published)
                published_platforms = list(platform_successes.keys()) or post_doc.get("platforms", [])
                status_history_entry = {
                    "status": "published",
                    "at": now_iso,
                    "note": f"Published to {', '.join(published_platforms)}",
                }
                await db.posts.update_one(
                    {"id": post_id},
                    {
                        "$set": {
                            "status": "published",
                            "published_at": now_iso,
                            "platform_results": platform_results,
                        },
                        "$push": {"status_history": status_history_entry},
                    }
                )
                # Create Success Notification
                platforms_str = ", ".join([p.capitalize() for p in published_platforms])
                if not platforms_str:
                    platforms_str = "connected platforms"
                    
                await db.notifications.insert_one(Notification(
                    user_id=user_id,
                    post_id=post_id,
                    type="success",
                    message=f"Post successfully published to {platforms_str}."
                ).model_dump())
                logging.info(f"Processed post {post_id} successfully.")
                # File Cleanup 
                if media_url and "/uploads/" in media_url:
                    from urllib.parse import urlparse
                    local_path = os.path.join(ROOT_DIR, urlparse(media_url).path.lstrip("/"))
                    if os.path.exists(local_path):
                        try: os.remove(local_path)
                        except: pass
                        
                cover_url = post_doc.get("cover_image_url")
                if cover_url and "/uploads/" in cover_url:
                    from urllib.parse import urlparse
                    local_cover_path = os.path.join(ROOT_DIR, urlparse(cover_url).path.lstrip("/"))
                    if os.path.exists(local_cover_path):
                        try: os.remove(local_cover_path)
                        except: pass
            
    except Exception as e:
        logging.error(f"Scheduled post processing error: {e}")

# ==================== STARTUP & SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(process_scheduled_posts, 'interval', minutes=1)
    scheduler.start()
    logging.info("Scheduler started")
    # Team member invite indexes
    await db.team_members.create_index([("invite_token", 1)], unique=True, sparse=True)
    await db.team_members.create_index([("owner_user_id", 1), ("status", 1)])
    await db.team_members.create_index([("email", 1)])
    # Warn loudly if email sending is not configured
    if not RESEND_API_KEY:
        logging.warning("=" * 70)
        logging.warning("EMAIL DISABLED: RESEND_API_KEY is not set in .env")
        logging.warning("Team invitations, approval notifications, and @mention")
        logging.warning("emails will NOT be sent until you add your Resend API key.")
        logging.warning("Get a free key at https://resend.com and set RESEND_API_KEY in .env")
        logging.warning("=" * 70)
    else:
        logging.info(f"Email configured — sender: {SENDER_EMAIL}")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    client.close()
    logging.info("Application shutdown")

# ==================== UPLOADS ====================

# Ensure uploads directory exists
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

@limiter.limit("30/minute")
@api_router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...), 
    current_user: User = Depends(get_current_user)
):
    """
    Upload a media file (image/video) to Firebase Cloud Storage (or fallback to local server)
    Returns the public URL to access the file
    """
    # ── Backpressure: per-user concurrent upload limit ────────────────────────
    user_limit = _get_upload_limit(current_user)
    current_count = _upload_counters.get(current_user.user_id, 0)
    if current_count >= user_limit:
        raise api_error(
            429, StructuredErrorCode.UPLOAD_USER_LIMIT,
            "Concurrent upload limit reached. Please wait for current uploads to finish.",
            {"retry_after": 30}
        )

    # ── Backpressure: global queue depth ──────────────────────────────────────
    if _get_global_queue_depth() >= GLOBAL_QUEUE_LIMIT:
        raise api_error(
            503, StructuredErrorCode.UPLOAD_SYSTEM_BUSY,
            "System is processing a high volume of uploads. Please try again in 2 minutes.",
            {"retry_after": 120}
        )

    _increment_upload_counter(current_user.user_id)
    try:
        # Read file content first so we can validate before storing
        content = await file.read()

        # ── Media validation (Stage 2.4) ──────────────────────────────────────
        try:
            validate_upload(
                filename=file.filename,
                file_size_bytes=len(content),
                platforms=None,  # global check; platform-specific check at publish time
            )
        except MediaValidationError as e:
            raise HTTPException(status_code=400, detail={"error": str(e), "code": e.error_code})

        # Create unique filename
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
        unique_filename = f"{uuid.uuid4()}.{file_ext}"

        firebase_bucket = os.environ.get('FIREBASE_STORAGE_BUCKET')

        if firebase_bucket:
            from firebase_admin import storage
            bucket = storage.bucket()
            blob = bucket.blob(f"uploads/{unique_filename}")

            blob.upload_from_string(content, content_type=file.content_type)
            blob.make_public()

            file_url = blob.public_url
            logging.info(f"Uploaded file to Firebase: {file_url}")
        else:
            # Fallback: Save file to local uploads directory
            file_path = UPLOADS_DIR / unique_filename
            with open(file_path, "wb") as buffer:
                buffer.write(content)

            # Using a relative path that the frontend can prefix
            file_url = f"/uploads/{unique_filename}"
            logging.info(f"Uploaded file to local disk: {file_url}")

        return {
            "success": True,
            "url": file_url,
            "filename": file.filename,
            "content_type": file.content_type
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")
    finally:
        _decrement_upload_counter(current_user.user_id)

# Include routers
app.include_router(api_router)
app.include_router(public_router)

# ==================== HEALTH CHECKS ====================
@app.get("/health")
async def health_check():
    """Liveness probe — is the process alive?"""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/ready")
async def readiness_check():
    """Readiness probe — are all dependencies connected?"""
    checks = {}
    all_ok = True

    # MongoDB check
    try:
        await client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as e:
        checks["mongodb"] = f"error: {str(e)}"
        all_ok = False

    # Redis check (optional — only if Redis is configured)
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(redis_url, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {str(e)}"
            all_ok = False
    else:
        checks["redis"] = "not_configured"

    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={"status": "ready" if all_ok else "not_ready", "checks": checks, "timestamp": datetime.now(timezone.utc).isoformat()},
        status_code=status_code
    )

# Add static files serving for uploads
from fastapi.staticfiles import StaticFiles
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# CORS already configured above via _cors_origins (Stage 3 — environment-aware).
# Additional known preview origins merged here to avoid duplicate middleware.
_extra_origins = [
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "https://postflow-25.preview.emergentagent.com",
]
for _o in _extra_origins:
    if _o not in _cors_origins:
        _cors_origins.append(_o)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer() if os.environ.get("ENV") != "production" else structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger(__name__)

