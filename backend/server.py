from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header, Cookie, UploadFile, File, Form
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse, RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any, Set
import uuid
from datetime import datetime, timezone, timedelta
import jwt
from passlib.context import CryptContext
import firebase_admin
from firebase_admin import credentials as firebase_credentials, auth as firebase_auth
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
    _emergent_available = True
except ImportError:
    _emergent_available = False
    logging.warning("emergentintegrations not available — AI/Stripe features disabled")
import razorpay
import resend
import httpx
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment
from paypalcheckoutsdk.orders import OrdersCreateRequest, OrdersCaptureRequest
import random
import shutil
import subprocess
import hashlib
import tempfile
import re
import time
import json as _json
import asyncio as _asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Redis URL for SSE pub/sub (20.4)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 720))

# Frontend URL
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Firebase Admin SDK initialization
_firebase_initialized = False
_service_account_path = ROOT_DIR / 'serviceAccountKey.json'
if _service_account_path.exists():
    try:
        _cred = firebase_credentials.Certificate(str(_service_account_path))
        firebase_admin.initialize_app(_cred)
        _firebase_initialized = True
        logging.info("Firebase Admin SDK initialized from serviceAccountKey.json")
    except Exception as _e:
        logging.warning(f"Firebase Admin SDK init failed: {_e}")
else:
    logging.warning("serviceAccountKey.json not found — Firebase ID token verification disabled")

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
    environment = SandboxEnvironment(client_id=paypal_client_id, client_secret=paypal_secret)
    paypal_client = PayPalHttpClient(environment)


# ==================== RATE LIMITER (in-memory token bucket) ====================
# Key: "{platform}:{user_id}" → {"tokens": N, "reset_at": float_timestamp}
_rate_limit_buckets: Dict[str, Dict] = {}
# Key: "{platform}:{user_id}" → pause_until float_timestamp (after 429)
_rate_limit_paused: Dict[str, float] = {}

# Platform hourly post limits (conservative — below actual limits to be safe)
PLATFORM_HOURLY_LIMITS = {
    "instagram": 25, "facebook": 25, "twitter": 50,
    "linkedin": 100, "youtube": 10, "tiktok": 20,
    "bluesky": 100, "threads": 25, "default": 50,
}

# Exponential backoff delays in minutes: attempt 1,2,3,4 → DLQ
BACKOFF_MINUTES = [5, 15, 60, 180]
MAX_RETRIES = 5  # 5 attempts before DLQ


def check_rate_limit(user_id: str, platform: str) -> bool:
    """Returns True if OK to call platform API, False if rate limited."""
    key = f"{platform}:{user_id}"
    now_ts = datetime.now(timezone.utc).timestamp()

    # Check if paused due to 429
    if key in _rate_limit_paused:
        if now_ts < _rate_limit_paused[key]:
            return False
        del _rate_limit_paused[key]

    bucket = _rate_limit_buckets.get(key)
    if not bucket or now_ts > bucket["reset_at"]:
        limit = PLATFORM_HOURLY_LIMITS.get(platform, PLATFORM_HOURLY_LIMITS["default"])
        _rate_limit_buckets[key] = {"tokens": limit, "reset_at": now_ts + 3600}
        bucket = _rate_limit_buckets[key]

    if bucket["tokens"] <= 0:
        return False

    bucket["tokens"] -= 1
    return True


def record_rate_limit_hit(user_id: str, platform: str, retry_after_seconds: int = 3600):
    """Record a 429 response — pause this (user, platform) pair."""
    key = f"{platform}:{user_id}"
    _rate_limit_paused[key] = datetime.now(timezone.utc).timestamp() + retry_after_seconds
    logging.warning(f"Rate limit recorded for {platform}:{user_id}, paused for {retry_after_seconds}s")


def get_next_retry_at(retry_count: int) -> datetime:
    """Exponential backoff: 5min → 15min → 60min → 180min."""
    idx = min(retry_count, len(BACKOFF_MINUTES) - 1)
    return datetime.now(timezone.utc) + timedelta(minutes=BACKOFF_MINUTES[idx])

# Create the main app
app = FastAPI(title="Social Scheduler API")
api_router = APIRouter(prefix="/api")

# ==================== PLAN LIMITS ====================
PLAN_MONTHLY_POST_LIMITS = {
    "free": 30,        # 30 posts/month on free plan (Starter tier per architecture)
    "active": None,    # unlimited on paid plans
}

# EC23: Content type × platform compatibility matrix.
# post_type values: "text", "image", "video", "reel", "story", "gif"
# Any platform not listed here accepts all types.
PLATFORM_CONTENT_COMPAT: Dict[str, Set[str]] = {
    "twitter":   {"text", "image", "video", "gif"},
    "instagram": {"image", "video", "reel", "story", "mixed"},   # no plain text-only posts; mixed = carousel with images+videos
    "facebook":  {"text", "image", "video", "reel", "story", "mixed"},
    "linkedin":  {"text", "image", "video"},
    "youtube":   {"video"},                              # YouTube is video-only
    "tiktok":    {"video"},                              # TikTok is video-only
    "threads":   {"text", "image", "video", "mixed"},   # Threads supports mixed media carousels
}

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
    name: str = ""
    picture: Optional[str] = None
    email_verified: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    subscription_status: str = "free"
    subscription_plan: Optional[str] = None
    subscription_end_date: Optional[datetime] = None
    is_admin: bool = False  # 20.10: Admin panel access

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
    media_urls: Optional[List[str]] = []
    thumbnail_urls: Optional[List[str]] = []  # 22: permanent thumbnails (set after media cleanup)
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    video_size_mb: Optional[float] = None  # 17.3: used to calculate dynamic pre_upload window
    scheduled_time: Optional[datetime] = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    media_cleaned_at: Optional[datetime] = None  # 22: set when media lifecycle cleanup completes
    # 17.5 — two-phase publishing fields
    pre_upload_status: Optional[str] = None          # pending | uploading | ready | failed | timeout
    pre_upload_start_time: Optional[datetime] = None  # when pre_upload_task was triggered
    pre_upload_started_at: Optional[datetime] = None  # actual worker start time
    pre_upload_completed_at: Optional[datetime] = None
    pre_upload_error: Optional[str] = None
    estimated_upload_duration: Optional[int] = None   # seconds estimated at schedule time (17.3)
    actual_upload_duration: Optional[int] = None      # seconds measured — feeds future estimates
    platform_container_ids: Optional[dict] = None     # {instagram: container_id, youtube: video_id}
    platform_post_urls: Optional[dict] = None         # {instagram: url, youtube: url} set after publish
    ai_generated: bool = False
    version: int = 1  # EC3 + EC25: optimistic locking version field

class PostCreate(BaseModel):
    content: str
    post_type: str = "text"
    platforms: List[str]
    media_urls: Optional[List[str]] = []
    media_types: Optional[List[str]] = []  # parallel to media_urls: 'image' | 'video' per item (used for mixed posts)
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    video_size_mb: Optional[float] = None  # 17.3: client passes this after upload to enable dynamic window
    scheduled_time: Optional[str] = None

class PostUpdate(BaseModel):
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[str] = None
    version: Optional[int] = None  # EC25: client must send current version to detect conflicts
    status: Optional[str] = None

class AIContentRequest(BaseModel):
    prompt: str
    platform: Optional[str] = None
    tone: Optional[str] = None   # casual | professional | fun | promotional

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

    # Auto-expire subscription if end_date has passed
    if (user_doc.get('subscription_status') == 'active' and
        user_doc.get('subscription_end_date') and
        user_doc['subscription_end_date'] < datetime.now(timezone.utc)):
        user_doc['subscription_status'] = 'expired'
        await db.users.update_one(
            {"user_id": user_doc["user_id"]},
            {"$set": {"subscription_status": "expired"}}
        )
        # EC15: Cancel all queued/scheduled posts when subscription expires
        await _cancel_queued_posts_on_expiry(user_doc["user_id"])

    return User(**user_doc)

async def _cancel_queued_posts_on_expiry(user_id: str) -> None:
    """EC15: Mark all scheduled/queued posts as cancelled when subscription expires."""
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.posts.update_many(
        {"user_id": user_id, "status": {"$in": ["scheduled", "queued"]}},
        {"$set": {
            "status": "cancelled",
            "cancel_reason": "subscription_expired",
            "updated_at": now_iso,
        }}
    )
    if result.modified_count:
        logging.info(f"EC15: Cancelled {result.modified_count} queued posts for user {user_id} — subscription expired")

async def _resolve_user_doc(user_id: str) -> dict:
    """Fetch user doc from MongoDB and auto-expire subscription if needed."""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if user_doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])

    # Auto-expire subscription if end_date has passed
    if (user_doc.get('subscription_status') == 'active' and
        user_doc.get('subscription_end_date') and
        user_doc['subscription_end_date'] < datetime.now(timezone.utc)):
        user_doc['subscription_status'] = 'expired'
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"subscription_status": "expired"}}
        )
        # EC15: Cancel all queued/scheduled posts when subscription expires
        await _cancel_queued_posts_on_expiry(user_id)
    return user_doc


async def _get_or_create_user_from_firebase(decoded_token: dict) -> str:
    """Return user_id for a verified Firebase token, creating the MongoDB user if needed."""
    email = decoded_token.get("email", "")
    firebase_uid = decoded_token.get("uid", "")

    # Look up by email first, then by firebase_uid
    user_doc = await db.users.find_one(
        {"$or": [{"email": email}, {"firebase_uid": firebase_uid}]},
        {"_id": 0}
    )

    if user_doc:
        # Keep firebase_uid synced
        if not user_doc.get("firebase_uid"):
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"firebase_uid": firebase_uid}}
            )
        return user_doc["user_id"]

    # New user — create MongoDB record from Firebase data
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    name = decoded_token.get("name") or email.split("@")[0]
    picture = decoded_token.get("picture")
    new_user = {
        "user_id": user_id,
        "firebase_uid": firebase_uid,
        "email": email,
        "name": name,
        "picture": picture,
        "email_verified": decoded_token.get("email_verified", True),
        "subscription_status": "free",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(new_user)
    logging.info(f"Created new user from Firebase login: {user_id} ({email})")
    return user_id


async def get_current_user(session_token: Optional[str] = Cookie(None), authorization: Optional[str] = Header(None)) -> User:
    # Try cookie first
    if session_token:
        return await get_current_user_from_cookie(session_token)

    # Fallback to Authorization header
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.replace("Bearer ", "")

    # 1. Try Firebase ID token verification first (Google Sign-In)
    if _firebase_initialized:
        try:
            decoded = firebase_auth.verify_id_token(token)
            user_id = await _get_or_create_user_from_firebase(decoded)
            user_doc = await _resolve_user_doc(user_id)
            return User(**user_doc)
        except firebase_auth.ExpiredIdTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        except firebase_auth.InvalidIdTokenError:
            pass  # Not a Firebase token — fall through to custom JWT
        except Exception as e:
            logging.debug(f"Firebase token check failed (may be custom JWT): {e}")

    # 2. Fall back to custom JWT (email/password login)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except (jwt.PyJWTError, Exception):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_doc = await _resolve_user_doc(user_id)
    return User(**user_doc)


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """20.10: Dependency that enforces admin-only access."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


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
        "subject": "Verify your email - SocialSync",
        "html": html_content
    }
    
    try:
        await asyncio.to_thread(resend.Emails.send, params)
        logging.info(f"Verification email sent to {email}")
    except Exception as e:
        logging.error(f"Failed to send verification email: {e}")

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/signup", response_model=Token)
async def signup(user_data: UserSignup):
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
@api_router.post("/auth/google/callback")
async def google_auth_callback(callback_data: GoogleAuthCallback):
    """Process Google OAuth session_id"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": callback_data.session_id}
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid session")
            
            data = response.json()
            
            # Check if user exists
            user_doc = await db.users.find_one({"email": data["email"]}, {"_id": 0})
            
            if user_doc:
                # Update existing user
                user_id = user_doc["user_id"]
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "name": data.get("name", user_doc.get("name")),
                        "picture": data.get("picture", user_doc.get("picture")),
                        "email_verified": True
                    }}
                )
            else:
                # Create new user
                user_id = f"user_{uuid.uuid4().hex[:12]}"
                new_user = {
                    "user_id": user_id,
                    "email": data["email"],
                    "name": data.get("name", "User"),
                    "picture": data.get("picture"),
                    "email_verified": True,
                    "subscription_status": "free",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.users.insert_one(new_user)
            
            # Create session
            session_token = data["session_token"]
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            
            await db.user_sessions.insert_one({
                "user_id": user_id,
                "session_token": session_token,
                "expires_at": expires_at.isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Get user data
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
            if isinstance(user_doc.get('created_at'), str):
                user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
            if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
                user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
            
            return {
                "session_token": session_token,
                "user": user_doc
            }
    except Exception as e:
        logging.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user_doc = await db.users.find_one({"email": credentials.email})
    if not user_doc:
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
    return current_user

@api_router.post("/auth/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    return {"message": "Logged out successfully"}

# Continued in next part...

# ==================== POST ROUTES ====================

@api_router.post("/posts", response_model=Post)
async def create_post(post_data: PostCreate, current_user: User = Depends(get_current_user)):
    if post_data.scheduled_time and current_user.subscription_status != "active":
        raise HTTPException(status_code=403, detail="Scheduling requires active subscription")

    # Plan enforcement: monthly post limit for free users
    if current_user.subscription_status != "active":
        from datetime import timezone
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_count = await db.posts.count_documents({
            "user_id": current_user.user_id,
            "created_at": {"$gte": month_start.isoformat()}
        })
        limit = PLAN_MONTHLY_POST_LIMITS.get("free", 10)
        if monthly_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Monthly post limit of {limit} reached. Upgrade to continue posting."
            )

    # EC23: Validate content type is compatible with every target platform
    post_type = post_data.post_type or "text"
    incompatible = [
        p for p in post_data.platforms
        if p in PLATFORM_CONTENT_COMPAT and post_type not in PLATFORM_CONTENT_COMPAT[p]
    ]
    if incompatible:
        raise HTTPException(
            status_code=422,
            detail=(
                f"post_type '{post_type}' is not supported on: {', '.join(incompatible)}. "
                f"Supported types — "
                + ", ".join(
                    f"{p}: {sorted(PLATFORM_CONTENT_COMPAT[p])}"
                    for p in incompatible
                )
            )
        )

    scheduled_time = None
    status = "draft"
    if post_data.scheduled_time:
        scheduled_time = datetime.fromisoformat(post_data.scheduled_time.replace('Z', '+00:00'))
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        # EC19: Reject posts scheduled more than 5 minutes in the past
        grace_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        if scheduled_time < grace_cutoff:
            raise HTTPException(
                status_code=422,
                detail=f"scheduled_time is in the past. Please choose a future time."
            )
        status = "scheduled"
    
    # 20.11: Schedule density check — warn if posting too frequently to avoid shadow-banning
    density_warnings = []
    if scheduled_time:
        try:
            from utils.schedule_density import check_schedule_density
            import sys as _sys
            _sys.path.insert(0, str(ROOT_DIR.parent / "utils"))
            density_warnings = await check_schedule_density(
                db,
                workspace_id=current_user.user_id,
                platforms=post_data.platforms,
                proposed_time=scheduled_time,
            )
        except Exception as _de:
            logging.warning("Schedule density check failed (non-blocking): %s", _de)

    post = Post(
        user_id=current_user.user_id,
        content=post_data.content,
        post_type=post_data.post_type,
        platforms=post_data.platforms,
        media_urls=post_data.media_urls or [],
        video_url=post_data.video_url,
        cover_image_url=post_data.cover_image_url,
        video_title=post_data.video_title,
        scheduled_time=scheduled_time,
        status=status
    )
    
    post_dict = post.model_dump()
    post_dict['created_at'] = post_dict['created_at'].isoformat()
    if post_dict.get('scheduled_time'):
        post_dict['scheduled_time'] = post_dict['scheduled_time'].isoformat()
    
    await db.posts.insert_one(post_dict)

    # 20.11: Attach density warnings to response (post still created — warnings only)
    post_response = post.model_dump()
    post_response['schedule_warnings'] = [
        {"platform": w.platform, "message": w.message, "post_count": w.post_count, "recommended_max": w.recommended_max}
        for w in density_warnings
    ]
    if density_warnings:
        logging.warning("Schedule density warnings for user %s: %s", current_user.user_id,
                        [w.message for w in density_warnings])
    return JSONResponse(content=post_response, status_code=201)

# ==================== MEDIA PROCESSING ====================

# File size limits
MAX_IMAGE_SIZE_MB = 50
MAX_VIDEO_SIZE_MB = 500
MAX_IMAGE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
MAX_VIDEO_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

# Allowed extensions
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "bmp"}
ALLOWED_VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm", "m4v", "3gp", "flv"}
ALLOWED_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_VIDEO_EXTS

# Platform format requirements
# Instagram/TikTok/Threads require MP4 H.264; most platforms accept jpg/png
PLATFORMS_REQUIRING_MP4 = {"instagram", "tiktok", "threads", "youtube"}

FFMPEG_PATH = shutil.which("ffmpeg") or shutil.which("ffmpeg3")


async def _transcode_to_mp4(input_path: str, output_path: str) -> bool:
    """
    Convert video to MP4 H.264 + AAC audio using FFmpeg.
    Returns True if successful, False if FFmpeg not available or failed.
    """
    if not FFMPEG_PATH:
        logging.warning("FFmpeg not found — skipping transcoding")
        return False

    cmd = [
        FFMPEG_PATH, "-i", input_path,
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",         # maximum compatibility
        "-movflags", "+faststart",     # web-optimised (moov atom at start)
        "-map_metadata", "-1",         # strip unnecessary metadata
        "-y", output_path
    ]

    try:
        result = await asyncio.to_thread(
            subprocess.run, cmd,
            capture_output=True, timeout=300
        )
        if result.returncode != 0:
            logging.error(f"FFmpeg failed: {result.stderr.decode()[:500]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logging.error("FFmpeg transcoding timed out after 300s")
        return False
    except Exception as e:
        logging.error(f"FFmpeg error: {e}")
        return False


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """
    Upload media with validation + FFmpeg transcoding.
    - Images: max 50MB, allowed formats validated
    - Videos: max 500MB, .mov/.avi etc. converted to MP4 H.264
    - Returns: {success, url, filename, media_type, transcoded}
    """
    import mimetypes

    # --- 1. Extension validation ---
    original_filename = file.filename or "upload"
    file_ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if not file_ext or file_ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{file_ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTS))}"
        )

    is_video = file_ext in ALLOWED_VIDEO_EXTS
    media_type = "video" if is_video else "image"

    # --- 2. Read content + size validation ---
    content = await file.read()
    file_size = len(content)

    if is_video and file_size > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video too large: {file_size // (1024*1024)}MB. Maximum is {MAX_VIDEO_SIZE_MB}MB."
        )
    if not is_video and file_size > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large: {file_size // (1024*1024)}MB. Maximum is {MAX_IMAGE_SIZE_MB}MB."
        )

    # --- 3. FFmpeg transcoding for videos ---
    transcoded = False
    final_ext = file_ext
    final_content = content

    if is_video:
        needs_conversion = file_ext != "mp4"
        if needs_conversion or FFMPEG_PATH:
            # Write original to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_in:
                tmp_in.write(content)
                tmp_in_path = tmp_in.name

            tmp_out_path = tmp_in_path.replace(f".{file_ext}", "_transcoded.mp4")

            try:
                transcoded = await _transcode_to_mp4(tmp_in_path, tmp_out_path)
                if transcoded:
                    with open(tmp_out_path, "rb") as f:
                        final_content = f.read()
                    final_ext = "mp4"
                    logging.info(f"Transcoded {file_ext} → mp4 for user {current_user.user_id} ({file_size // 1024}KB → {len(final_content) // 1024}KB)")
            finally:
                for p in [tmp_in_path, tmp_out_path]:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    # --- 4. Generate safe filename ---
    file_id = uuid.uuid4().hex[:16]
    safe_filename = f"{file_id}.{final_ext}"

    # --- 5. Upload to R2 or local ---
    storage_backend = os.environ.get("STORAGE_BACKEND", "local")
    file_url = None

    if storage_backend == "r2":
        try:
            import boto3
            from botocore.client import Config
            import io

            r2_endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
            r2_access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
            r2_secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
            r2_bucket = os.environ.get("CLOUDFLARE_R2_BUCKET_NAME", "socialentangler-media")
            cdn_domain = os.environ.get("CLOUDFLARE_CDN_DOMAIN", "")

            s3 = boto3.client(
                "s3",
                endpoint_url=r2_endpoint,
                aws_access_key_id=r2_access_key,
                aws_secret_access_key=r2_secret_key,
                config=Config(signature_version="s3v4"),
                region_name="auto"
            )

            content_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            object_key = f"uploads/{current_user.user_id}/{safe_filename}"

            s3.upload_fileobj(
                io.BytesIO(final_content),
                r2_bucket,
                object_key,
                ExtraArgs={"ContentType": content_type}
            )

            file_url = (
                f"https://{cdn_domain}/{object_key}" if cdn_domain
                else f"{r2_endpoint}/{r2_bucket}/{object_key}"
            )
        except Exception as e:
            logging.warning(f"R2 upload failed, falling back to local: {e}")

    if not file_url:
        # Local filesystem fallback
        upload_dir = Path("/app/uploads")
        upload_dir.mkdir(exist_ok=True, parents=True)
        file_path = upload_dir / safe_filename
        file_path.write_bytes(final_content)
        file_url = f"/uploads/{safe_filename}"

    return {
        "success": True,
        "url": file_url,
        "filename": original_filename,
        "media_type": media_type,
        "transcoded": transcoded,
        "original_format": file_ext,
        "final_format": final_ext,
        "size_bytes": len(final_content),
    }

@api_router.get("/posts", response_model=List[Post])
async def get_posts(current_user: User = Depends(get_current_user), status: Optional[str] = None):
    query = {"user_id": current_user.user_id}
    if status:
        query["status"] = status
    
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

    # EC25: Optimistic locking — reject stale writes to prevent last-write-wins data loss
    if post_data.version is not None and post.get("version", 1) != post_data.version:
        raise HTTPException(
            status_code=409,
            detail=f"Post was modified by another request (version mismatch: expected {post.get('version', 1)}, got {post_data.version}). Refresh and try again."
        )

    update_dict = {k: v for k, v in post_data.model_dump(exclude_unset=True).items() if v is not None}
    update_dict.pop("version", None)  # don't store the client-sent version as a field value

    if 'scheduled_time' in update_dict and update_dict['scheduled_time']:
        new_st = datetime.fromisoformat(update_dict['scheduled_time'].replace('Z', '+00:00'))
        if new_st.tzinfo is None:
            new_st = new_st.replace(tzinfo=timezone.utc)
        # EC19: Also validate scheduled_time on updates
        if new_st < datetime.now(timezone.utc) - timedelta(minutes=5):
            raise HTTPException(status_code=422, detail="scheduled_time is in the past.")
        update_dict['scheduled_time'] = new_st.isoformat()

    if update_dict:
        # EC3: Increment version so in-flight workers detect stale data
        await db.posts.update_one({"id": post_id}, {"$set": update_dict, "$inc": {"version": 1}})
    
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

@api_router.get("/posts/failed")
async def get_failed_posts(current_user: User = Depends(get_current_user)):
    """Get posts with any failed platforms (DLQ view) — includes 'failed' and 'partial' status"""
    posts = await db.posts.find(
        {"user_id": current_user.user_id, "status": {"$in": ["failed", "partial"]}},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(100)

    for post in posts:
        for field in ('created_at', 'scheduled_time', 'published_at', 'updated_at'):
            if post.get(field) and isinstance(post[field], str):
                try:
                    post[field] = datetime.fromisoformat(post[field])
                except Exception:
                    pass

    return posts

@api_router.post("/posts/{post_id}/retry")
async def retry_failed_post(post_id: str, current_user: User = Depends(get_current_user), platform: Optional[str] = None):
    """
    Retry failed platforms for a post.
    - If `platform` param given: retry only that platform
    - If no param: retry ALL permanently_failed platforms
    Succeeded platforms are NEVER retried (no duplicates).
    """
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get('status') not in ('failed', 'partial'):
        raise HTTPException(status_code=400, detail="Only failed/partial posts can be retried")

    platform_results = post.get('platform_results', {})
    retried_platforms = []

    if platform:
        # Retry single platform
        pr = platform_results.get(platform)
        if not pr:
            raise HTTPException(status_code=400, detail=f"Platform '{platform}' not found on this post")
        if pr.get('status') != 'permanently_failed':
            raise HTTPException(status_code=400, detail=f"Platform '{platform}' is not in failed state (current: {pr.get('status')})")
        pr['status'] = 'pending'
        pr['retries'] = 0
        pr['error'] = None
        platform_results[platform] = pr
        retried_platforms.append(platform)
    else:
        # Retry ALL permanently failed platforms
        for p, pr in platform_results.items():
            if pr.get('status') == 'permanently_failed':
                pr['status'] = 'pending'
                pr['retries'] = 0
                pr['error'] = None
                platform_results[p] = pr
                retried_platforms.append(p)

    if not retried_platforms:
        raise HTTPException(status_code=400, detail="No failed platforms to retry")

    now = datetime.now(timezone.utc)
    retry_time = now + timedelta(minutes=1)

    await db.posts.update_one(
        {"id": post_id},
        {"$set": {
            "status": "publishing",
            "scheduled_time": retry_time.isoformat(),
            "platform_results": platform_results,
            "failure_reason": None,
            "updated_at": now.isoformat()
        }}
    )
    return {
        "message": f"Retrying {len(retried_platforms)} platform(s): {', '.join(retried_platforms)}",
        "retried_platforms": retried_platforms,
        "scheduled_time": retry_time.isoformat()
    }

# ==================== AI CONTENT GENERATION ====================

def _build_system_message(platform: Optional[str], tone: Optional[str]) -> str:
    """Build a rich system prompt based on platform and tone."""
    base = "You are an expert social media copywriter. Write only the post content — no labels, no explanations, no quotes around the output."

    platform_rules = {
        "twitter":   "Platform: Twitter/X. Maximum 280 characters. Start with a strong hook. Be punchy and direct.",
        "linkedin":  "Platform: LinkedIn. Professional and insightful tone. Use short paragraphs. Can be up to 3000 characters. End with a call-to-action.",
        "instagram": "Platform: Instagram. Engaging and visual storytelling style. Include 5-10 relevant hashtags at the end. Use emoji naturally.",
        "facebook":  "Platform: Facebook. Conversational and shareable. Can be longer form. Include a call-to-action.",
        "tiktok":    "Platform: TikTok. Energetic, trendy, use popular phrases. Keep it short and punchy. Include relevant hashtags.",
        "discord":   "Platform: Discord. Casual, community-friendly, conversational. Like you are talking to friends in a server.",
        "bluesky":   "Platform: Bluesky. Maximum 300 characters. Thoughtful and conversational.",
        "youtube":   "Platform: YouTube. Write an engaging video description with keywords. Include timestamps placeholder if relevant.",
    }

    tone_rules = {
        "casual":       "Tone: Casual and friendly — like talking to a friend.",
        "professional": "Tone: Professional and polished — authoritative yet approachable.",
        "fun":          "Tone: Fun and playful — use humor, energy, and enthusiasm.",
        "promotional":  "Tone: Promotional — highlight benefits, create urgency, drive action.",
    }

    parts = [base]
    if platform and platform in platform_rules:
        parts.append(platform_rules[platform])
    if tone and tone in tone_rules:
        parts.append(tone_rules[tone])

    return " ".join(parts)


async def _ai_waterfall(system_message: str, prompt: str) -> str:
    """
    Try each AI provider in order. On rate-limit / quota errors move to the next.
    Non-rate-limit errors propagate immediately (don't try other providers).
    Order: Gemini 2.0 Flash Lite → Groq LLaMA 3.3 → Cohere Command R → OpenRouter Gemma → EMERGENT fallback
    """
    rate_limit_errors: list[str] = []

    def _is_rate_limit(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "429" in msg or "quota" in msg or "rate limit" in msg
            or "too many requests" in msg or "resource_exhausted" in msg.lower()
            or type(exc).__name__ in ("ResourceExhausted", "RateLimitError")
        )

    # ── 1. Google Gemini 2.0 Flash Lite ───────────────────────────────────
    google_key = os.environ.get("GOOGLE_AI_KEY")
    if google_key:
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=google_key)
            model = genai.GenerativeModel(
                "gemini-2.0-flash-lite",
                system_instruction=system_message,
            )
            result = model.generate_content(prompt)
            return result.text
        except Exception as exc:
            if _is_rate_limit(exc):
                logging.warning(f"[AI waterfall] Gemini rate-limited: {exc} — trying Groq")
                rate_limit_errors.append(f"Gemini: {exc}")
            else:
                raise

    # ── 2. Groq — llama-3.3-70b-versatile ────────────────────────────────
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import AsyncGroq  # type: ignore
            client = AsyncGroq(api_key=groq_key)
            resp = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=1024,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            if _is_rate_limit(exc):
                logging.warning(f"[AI waterfall] Groq rate-limited: {exc} — trying Cohere")
                rate_limit_errors.append(f"Groq: {exc}")
            else:
                raise

    # ── 3. Cohere Command R ───────────────────────────────────────────────
    cohere_key = os.environ.get("COHERE_API_KEY")
    if cohere_key:
        try:
            import cohere  # type: ignore
            co = cohere.AsyncClientV2(api_key=cohere_key)
            resp = await co.chat(
                model="command-r",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user",   "content": prompt},
                ],
            )
            return resp.message.content[0].text
        except Exception as exc:
            if _is_rate_limit(exc):
                logging.warning(f"[AI waterfall] Cohere rate-limited: {exc} — trying OpenRouter")
                rate_limit_errors.append(f"Cohere: {exc}")
            else:
                raise

    # ── 4. OpenRouter — google/gemma-3-12b:free ───────────────────────────
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://socialentangler.com",
                        "X-Title": "SocialEntangler AI",
                    },
                    json={
                        "model": "google/gemma-3-12b:free",
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user",   "content": prompt},
                        ],
                    },
                )
                if r.status_code == 429:
                    logging.warning(f"[AI waterfall] OpenRouter rate-limited — trying EMERGENT")
                    rate_limit_errors.append("OpenRouter: 429")
                else:
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                rate_limit_errors.append(f"OpenRouter: {exc}")
            else:
                raise
        except Exception as exc:
            if _is_rate_limit(exc):
                rate_limit_errors.append(f"OpenRouter: {exc}")
            else:
                raise

    # ── 5. EMERGENT_LLM_KEY — existing paid fallback ──────────────────────
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if emergent_key:
        chat = LlmChat(
            api_key=emergent_key,
            session_id=f"content-gen-{uuid.uuid4()}",
            system_message=system_message,
        ).with_model("openai", "gpt-4o-mini")
        response = await chat.send_message(UserMessage(text=prompt))
        return response

    # All providers exhausted
    if rate_limit_errors:
        raise HTTPException(
            status_code=429,
            detail=f"All AI providers are rate-limited. Try again in a moment. Details: {'; '.join(rate_limit_errors)}",
        )
    raise HTTPException(status_code=503, detail="No AI provider configured. Add GOOGLE_AI_KEY, GROQ_API_KEY, COHERE_API_KEY, or OPENROUTER_API_KEY to your .env file.")


@api_router.post("/ai/generate-content")
async def generate_content(request: AIContentRequest, current_user: User = Depends(get_current_user)):
    try:
        system_message = _build_system_message(request.platform, request.tone)
        content = await _ai_waterfall(system_message, request.prompt)
        return {"content": content}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

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
    
    for account in accounts:
        if isinstance(account.get('connected_at'), str):
            account['connected_at'] = datetime.fromisoformat(account['connected_at'])
        if account.get('token_expiry') and isinstance(account['token_expiry'], str):
            account['token_expiry'] = datetime.fromisoformat(account['token_expiry'])
    
    return accounts

@api_router.get("/social-accounts/{account_id}/disconnect-impact")
async def get_disconnect_impact(account_id: str, current_user: User = Depends(get_current_user)):
    """EC7: Pre-disconnect impact check — tell user how many queued posts will be affected."""
    account = await db.social_accounts.find_one({"id": account_id, "user_id": current_user.user_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    platform = account.get("platform", "")
    queued_count = await db.posts.count_documents({
        "user_id": current_user.user_id,
        "platforms": platform,
        "status": {"$in": ["scheduled", "publishing"]},
    })
    return {
        "account_id": account_id,
        "platform": platform,
        "queued_posts_affected": queued_count,
        "warning": (
            f"Disconnecting this account will cause {queued_count} scheduled post(s) to fail on {platform}."
            if queued_count > 0 else None
        ),
    }


@api_router.delete("/social-accounts/{account_id}")
async def disconnect_social_account(account_id: str, current_user: User = Depends(get_current_user)):
    # EC7: Cancel queued posts on this platform when account is disconnected
    account = await db.social_accounts.find_one({"id": account_id, "user_id": current_user.user_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    platform = account.get("platform", "")
    result = await db.social_accounts.delete_one({"id": account_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")

    # EC16: Mark account inactive instead of full delete + cascade fail queued posts
    affected = await db.posts.count_documents({
        "user_id": current_user.user_id,
        "platforms": platform,
        "status": {"$in": ["scheduled", "publishing"]},
    })
    if affected > 0:
        # Mark platform result as permanently_failed for in-flight posts
        await db.posts.update_many(
            {"user_id": current_user.user_id, "platforms": platform, "status": {"$in": ["scheduled", "publishing"]}},
            {"$set": {f"platform_results.{platform}.status": "permanently_failed",
                      f"platform_results.{platform}.error": "Social account disconnected by user"}}
        )
        logging.warning(f"EC7/EC16: {affected} queued posts on {platform} marked failed after account disconnect")

    return {"message": "Account disconnected", "posts_affected": affected}


# ==================== OAUTH SOCIAL ACCOUNTS ====================

def _create_oauth_state(user_id: str, platform: str) -> str:
    """Create a short-lived signed state token encoding user identity."""
    payload = {"user_id": user_id, "platform": platform,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=15)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def _verify_oauth_state(state: str) -> dict:
    """Decode and verify a state token; raises HTTPException on failure."""
    try:
        return jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="OAuth state expired — please try connecting again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

async def _save_oauth_account(user_id: str, platform: str, access_token: str,
                               refresh_token: Optional[str], platform_user_id: str,
                               platform_username: str, token_expiry: Optional[datetime] = None):
    """Upsert the social account record for a user."""
    existing = await db.social_accounts.find_one({"user_id": user_id, "platform": platform})
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id, "platform": platform,
        "platform_user_id": platform_user_id,
        "platform_username": platform_username,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expiry": token_expiry.isoformat() if token_expiry else None,
        "is_active": True,
        "connected_at": now.isoformat(),
    }
    if existing:
        await db.social_accounts.update_one({"user_id": user_id, "platform": platform}, {"$set": doc})
    else:
        doc["id"] = str(uuid.uuid4())
        await db.social_accounts.insert_one(doc)

@api_router.get("/oauth/{platform}/authorize")
async def oauth_authorize(platform: str, current_user: User = Depends(get_current_user)):
    """Generate OAuth authorization URL for the given platform."""
    state = _create_oauth_state(current_user.user_id, platform)
    try:
        if platform == "facebook":
            from app.social.facebook import FacebookAuth
            url = FacebookAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform == "instagram":
            from app.social.instagram import InstagramAuth
            url = InstagramAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform == "twitter":
            from app.social.twitter import TwitterAuth
            auth = TwitterAuth()
            verifier, challenge = auth.generate_pkce()
            url = auth.get_auth_url(state, challenge)
            return {"authorization_url": url, "code_verifier": verifier}
        elif platform == "linkedin":
            from app.social.linkedin import LinkedInAuth
            url = LinkedInAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform in ("youtube", "google"):
            from app.social.google import GoogleAuth
            url = GoogleAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform == "reddit":
            from app.social.reddit import RedditAuth
            url = RedditAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform == "tiktok":
            from app.social.tiktok import TikTokAuth
            result = TikTokAuth().get_auth_url(state)
            if isinstance(result, dict):
                return result
            return {"authorization_url": result}
        elif platform == "pinterest":
            from app.social.pinterest import PinterestAuth
            url = PinterestAuth().get_auth_url(state)
            return {"authorization_url": url}
        elif platform == "snapchat":
            from app.social.snapchat import SnapchatAuth
            url = SnapchatAuth().get_auth_url(state)
            return {"authorization_url": url}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[OAuth] authorize error for {platform}: {e}")
        raise HTTPException(status_code=500, detail=f"{platform} credentials not configured")

class OAuthCallbackBody(BaseModel):
    code: str
    state: Optional[str] = None
    code_verifier: Optional[str] = None

async def _process_oauth_callback(platform: str, code: str, state: str,
                                   code_verifier: Optional[str] = None) -> dict:
    """Exchange OAuth code for token, fetch profile, save account. Returns account info."""
    claims = _verify_oauth_state(state)
    user_id = claims["user_id"]

    try:
        if platform == "facebook":
            from app.social.facebook import FacebookAuth
            auth = FacebookAuth()
            token_data = await auth.exchange_code_for_token(code)
            short_token = token_data.get("access_token")
            ll = await auth.get_long_lived_token(short_token)
            access_token = ll.get("access_token", short_token)
            expiry = datetime.now(timezone.utc) + timedelta(days=60)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id", ""))
            username = profile.get("name") or profile.get("email") or platform_user_id

        elif platform == "instagram":
            from app.social.instagram import InstagramAuth
            auth = InstagramAuth()
            token_data = await auth.exchange_code_for_token(code)
            short_token = token_data.get("access_token")
            ll = await auth.get_long_lived_token(short_token)
            access_token = ll.get("access_token", short_token)
            expiry = datetime.now(timezone.utc) + timedelta(days=60)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id", token_data.get("user_id", "")))
            username = profile.get("username") or profile.get("name") or platform_user_id

        elif platform == "twitter":
            from app.social.twitter import TwitterAuth
            auth = TwitterAuth()
            if not code_verifier:
                raise HTTPException(status_code=400, detail="Twitter requires code_verifier")
            token_data = await auth.exchange_code_for_token(code, code_verifier)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 7200)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id", ""))
            username = profile.get("username") or profile.get("name") or platform_user_id
            await _save_oauth_account(user_id, platform, access_token, refresh_token,
                                       platform_user_id, username, expiry)
            return {"platform": platform, "username": username}

        elif platform == "linkedin":
            from app.social.linkedin import LinkedInAuth
            auth = LinkedInAuth()
            token_data = await auth.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 5184000)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id") or profile.get("sub", ""))
            username = profile.get("name") or profile.get("localizedFirstName", "") + " " + profile.get("localizedLastName", "")
            username = username.strip() or platform_user_id

        elif platform in ("youtube", "google"):
            from app.social.google import GoogleAuth
            auth = GoogleAuth()
            token_data = await auth.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            channel = await auth.get_channel_info(access_token)
            platform_user_id = channel.get("id", "")
            username = channel.get("title") or platform_user_id
            platform = "youtube"
            await _save_oauth_account(user_id, platform, access_token, refresh_token,
                                       platform_user_id, username, expiry)
            return {"platform": platform, "username": username}

        elif platform == "reddit":
            from app.social.reddit import RedditAuth
            auth = RedditAuth()
            token_data = await auth.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id", ""))
            username = profile.get("name") or platform_user_id

        elif platform == "tiktok":
            from app.social.tiktok import TikTokAuth
            auth = TikTokAuth()
            verifier = code_verifier or ""
            token_data = await auth.exchange_code_for_token(code, verifier)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 86400)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("open_id") or profile.get("union_id", ""))
            username = profile.get("display_name") or profile.get("nickname") or platform_user_id

        elif platform == "pinterest":
            from app.social.pinterest import PinterestAuth
            auth = PinterestAuth()
            token_data = await auth.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 2592000)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("id") or profile.get("username", ""))
            username = profile.get("username") or profile.get("business_name") or platform_user_id

        elif platform == "snapchat":
            from app.social.snapchat import SnapchatAuth
            auth = SnapchatAuth()
            token_data = await auth.exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            profile = await auth.get_user_profile(access_token)
            platform_user_id = str(profile.get("sub") or profile.get("id", ""))
            username = profile.get("display_name") or profile.get("name") or platform_user_id

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

        refresh_token = locals().get("refresh_token")
        expiry_dt = locals().get("expiry")
        await _save_oauth_account(user_id, platform, access_token, refresh_token,
                                   platform_user_id, username, expiry_dt)
        return {"platform": platform, "username": username}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[OAuth] callback processing error for {platform}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to connect {platform}: {str(e)}")

@api_router.get("/oauth/{platform}/callback")
async def oauth_callback_get(platform: str, request: Request,
                              code: Optional[str] = None,
                              state: Optional[str] = None,
                              error: Optional[str] = None):
    """Handle platform redirect-based OAuth callback (backend redirect_uri flow)."""
    import urllib.parse
    frontend_base = FRONTEND_URL
    if error:
        return RedirectResponse(url=f"{frontend_base}/oauth/callback?error={urllib.parse.quote(str(error))}&platform={platform}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{frontend_base}/oauth/callback?error=missing_params&platform={platform}", status_code=302)
    code_verifier = request.query_params.get("code_verifier")
    try:
        await _process_oauth_callback(platform, code, state, code_verifier)
        return RedirectResponse(url=f"{frontend_base}/oauth/callback?success=true&platform={platform}", status_code=302)
    except HTTPException as e:
        return RedirectResponse(url=f"{frontend_base}/oauth/callback?error={urllib.parse.quote(str(e.detail))}&platform={platform}", status_code=302)
    except Exception as e:
        logging.error(f"[OAuth] GET callback unhandled error for {platform}: {e}", exc_info=True)
        return RedirectResponse(url=f"{frontend_base}/oauth/callback?error=server_error&platform={platform}", status_code=302)

@api_router.post("/oauth/{platform}/callback")
async def oauth_callback_post(platform: str, body: OAuthCallbackBody,
                               current_user: User = Depends(get_current_user)):
    """Handle frontend-posted OAuth callback (frontend redirect_uri flow, e.g. YouTube)."""
    # When frontend posts the code, generate a fresh state with the authenticated user
    state = body.state or _create_oauth_state(current_user.user_id, platform)
    # Overwrite state claims with the authenticated user so we trust the right user_id
    state = _create_oauth_state(current_user.user_id, platform)
    result = await _process_oauth_callback(platform, body.code, state, body.code_verifier)
    return {"success": True, "platform": result["platform"], "username": result.get("username")}


# ==================== PAYMENTS ====================

PRICING = {
    "monthly": {"amount": 500.0, "currency": "INR", "duration": 30},
    "yearly": {"amount": 3000.0, "currency": "INR", "duration": 365}
}

@api_router.post("/payments/checkout", response_model=CheckoutSessionResponse)
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
            
            return session
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
            
            return CheckoutSessionResponse(
                url=f"{origin_url}/razorpay-checkout?order_id={order['id']}",
                session_id=order['id']
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
            
            return CheckoutSessionResponse(url=approve_url, session_id=order_id)
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

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    try:
        body = await request.body()
        sig_header = request.headers.get("Stripe-Signature", "")

        # EC13: Replay attack protection — reject if webhook timestamp > 5 minutes old
        ts_match = re.search(r"t=(\d+)", sig_header)
        if ts_match:
            webhook_ts = int(ts_match.group(1))
            if abs(time.time() - webhook_ts) > 300:
                logging.warning("Stripe webhook rejected — timestamp too old (possible replay attack)")
                raise HTTPException(status_code=400, detail="Webhook timestamp too old — possible replay attack")

        webhook_url = ""
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)

        webhook_response = await stripe_checkout.handle_webhook(body, sig_header)

        if webhook_response.event_type == "checkout.session.completed":
            session_id = webhook_response.session_id

            # EC28: Idempotent webhook — skip if already processed
            already_processed = await db.processed_webhooks.find_one({"event_id": session_id})
            if already_processed:
                logging.info(f"Stripe webhook already processed: {session_id}")
                return {"status": "already_processed"}

            transaction = await db.payment_transactions.find_one({"session_id": session_id})
            if transaction and transaction['payment_status'] != "paid":
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])

                # 20.8: Handle plan change (upgrade/downgrade) via billing util
                try:
                    from utils.billing import handle_plan_change, handle_payment_success
                    user_doc = await db.users.find_one({"user_id": transaction['user_id']}, {"plan": 1})
                    old_plan = (user_doc or {}).get("plan", "free")
                    new_plan = transaction['plan']
                    if old_plan != new_plan:
                        await handle_plan_change(db, transaction['user_id'], old_plan, new_plan)
                    # Clear any prior payment failure state and resume paused posts
                    await handle_payment_success(db, transaction['user_id'])
                except ImportError:
                    pass

                await db.users.update_one(
                    {"user_id": transaction['user_id']},
                    {"$set": {
                        "subscription_status": "active",
                        "subscription_plan": new_plan,
                        "subscription_end_date": end_date.isoformat()
                    }}
                )

                # Section 20.8: trigger plan change cascade (upgrade/downgrade)
                try:
                    from utils.billing import handle_plan_change, handle_payment_success
                    await handle_plan_change(db, transaction['user_id'], old_plan, new_plan)
                    await handle_payment_success(db, transaction['user_id'])
                except Exception as billing_exc:
                    logging.warning(f"Billing cascade error (non-fatal): {billing_exc}")

                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {
                        "payment_status": "paid",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )

            # EC28: Record this webhook as processed to prevent double-grants
            await db.processed_webhooks.insert_one({
                "event_id": session_id,
                "event_type": webhook_response.event_type,
                "processed_at": datetime.now(timezone.utc).isoformat()
            })

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ==================== GDPR & USER ACCOUNT (20.3) ====================

@api_router.post("/user/data-export")
async def request_data_export(current_user: User = Depends(get_current_user)):
    """20.3 GDPR Article 20 — Request a ZIP export of all user data."""
    export_id = str(uuid.uuid4())
    await db.data_exports.insert_one({
        "_id": export_id,
        "user_id": current_user.user_id,
        "status": "pending",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        from celery_workers.tasks.gdpr import generate_data_export
        generate_data_export.apply_async(
            kwargs={
                "user_id": current_user.user_id,
                "workspace_id": current_user.user_id,
                "export_id": export_id,
            },
            queue="default",
        )
    except ImportError:
        logging.warning("GDPR export task not available")
    return {"status": "queued", "export_id": export_id, "message": "Export will be emailed when ready (up to 15 minutes)."}


@api_router.delete("/user/account")
async def delete_account(current_user: User = Depends(get_current_user)):
    """20.3 GDPR Article 17 — Right to erasure. Enqueues full data deletion."""
    await db.users.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"deletion_requested_at": datetime.now(timezone.utc).isoformat(), "status": "deletion_pending"}},
    )
    try:
        from celery_workers.tasks.gdpr import process_erasure_request
        process_erasure_request.apply_async(
            kwargs={"user_id": current_user.user_id, "workspace_id": current_user.user_id},
            queue="default",
        )
    except ImportError:
        logging.warning("GDPR erasure task not available")
    return {"status": "queued", "message": "Account deletion has been queued. All data will be removed within 30 days."}


@api_router.get("/user/notification-preferences")
async def get_notification_preferences(current_user: User = Depends(get_current_user)):
    """20.12 — Get user notification preferences."""
    try:
        from utils.notification_prefs import get_user_prefs
        prefs = await get_user_prefs(db, current_user.user_id)
        return {"preferences": prefs}
    except ImportError:
        return {"preferences": {}}


@api_router.patch("/user/notification-preferences")
async def update_notification_preferences(
    preferences: Dict[str, Any],
    current_user: User = Depends(get_current_user),
):
    """20.12 — Update user notification preferences."""
    await db.notification_prefs.update_one(
        {"user_id": current_user.user_id},
        {"$set": {"prefs": preferences, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"status": "updated", "preferences": preferences}


# ==================== SSE REAL-TIME UPDATES (20.4) ====================

from fastapi.responses import StreamingResponse as _StreamingResponse

@api_router.get("/stream/status")
async def stream_user_status(current_user: User = Depends(get_current_user)):
    """
    20.4: Server-Sent Events stream for real-time post status updates.
    Browser connects once; Celery workers push updates via Redis pub/sub.
    Channel: user:{user_id}:updates
    Falls back to 30s client-side polling if SSE is not supported.
    """
    channel = f"user:{current_user.user_id}:updates"

    async def event_generator():
        import redis.asyncio as _aioredis
        r = _aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            # Send a connection confirmation heartbeat
            yield f"data: {_json.dumps({'type': 'connected', 'channel': channel})}\n\n"
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
                # Heartbeat every ~30s to keep connection alive through proxies
                await _asyncio.sleep(0)
        except _asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    return _StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@api_router.get("/stream/post/{post_id}")
async def stream_post_status(post_id: str, current_user: User = Depends(get_current_user)):
    """
    20.4: SSE stream for a single post's status updates.
    Channel: post:{post_id}:updates
    """
    # Verify post belongs to user
    post_doc = await db.posts.find_one({"id": post_id, "user_id": current_user.user_id}, {"_id": 0, "status": 1})
    if not post_doc:
        raise HTTPException(status_code=404, detail="Post not found")

    channel = f"post:{post_id}:updates"

    async def event_generator():
        import redis.asyncio as _aioredis
        r = _aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield f"data: {_json.dumps({'type': 'connected', 'post_id': post_id, 'current_status': post_doc.get('status')})}\n\n"
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
                await _asyncio.sleep(0)
        except _asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    return _StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ==================== ADMIN PANEL (20.10) ====================

@api_router.get("/admin/users")
async def admin_list_users(
    page: int = 1,
    limit: int = 50,
    email: Optional[str] = None,
    plan: Optional[str] = None,
    admin_user: User = Depends(get_admin_user),
):
    """20.10: List all users with optional filters. Admin only."""
    query: Dict[str, Any] = {}
    if email:
        query["email"] = {"$regex": email, "$options": "i"}
    if plan:
        query["subscription_plan"] = plan
    skip = (page - 1) * limit
    users = await db.users.find(query, {"_id": 0, "password": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db.users.count_documents(query)
    return {"users": users, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@api_router.get("/admin/users/{user_id}")
async def admin_get_user(user_id: str, admin_user: User = Depends(get_admin_user)):
    """20.10: Get full user profile including subscription and post stats. Admin only."""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    post_counts = {
        s: await db.posts.count_documents({"user_id": user_id, "status": s})
        for s in ["scheduled", "published", "failed", "draft"]
    }
    social_accounts = await db.social_accounts.find({"user_id": user_id}, {"_id": 0}).to_list(20)
    return {"user": user_doc, "post_counts": post_counts, "social_accounts": social_accounts}


@api_router.patch("/admin/users/{user_id}/subscription")
async def admin_update_subscription(
    user_id: str,
    plan: str,
    status: str,
    days: int = 30,
    admin_user: User = Depends(get_admin_user),
):
    """20.10: Manually set a user's subscription plan and status. Admin only."""
    end_date = datetime.now(timezone.utc) + timedelta(days=days)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "subscription_plan": plan,
            "subscription_status": status,
            "subscription_end_date": end_date.isoformat(),
            "admin_overridden_at": datetime.now(timezone.utc).isoformat(),
            "admin_overridden_by": admin_user.user_id,
        }},
    )
    return {"status": "updated", "user_id": user_id, "plan": plan, "subscription_status": status}


@api_router.get("/admin/posts/{post_id}")
async def admin_get_post(post_id: str, admin_user: User = Depends(get_admin_user)):
    """20.10: Inspect any post with full platform_results. Admin only."""
    post_doc = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not post_doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return post_doc


@api_router.get("/admin/dlq")
async def admin_list_dlq(
    page: int = 1,
    limit: int = 50,
    admin_user: User = Depends(get_admin_user),
):
    """20.10: List posts in dead-letter queue (permanently failed). Admin only."""
    query = {"status": {"$in": ["failed", "permanently_failed"]}, "dlq_reason": {"$exists": True}}
    skip = (page - 1) * limit
    posts = await db.posts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.posts.count_documents(query)
    return {"posts": posts, "total": total, "page": page}


@api_router.post("/admin/dlq/{post_id}/retry")
async def admin_retry_dlq_post(post_id: str, admin_user: User = Depends(get_admin_user)):
    """20.10: Re-queue a DLQ post for retry. Admin only."""
    post_doc = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not post_doc:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.posts.update_one(
        {"id": post_id},
        {"$set": {"status": "scheduled", "dlq_reason": None, "admin_retry_by": admin_user.user_id,
                  "admin_retry_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"claimed_at": ""}},
    )
    return {"status": "requeued", "post_id": post_id}


@api_router.get("/admin/queue/stats")
async def admin_queue_stats(admin_user: User = Depends(get_admin_user)):
    """20.10: Queue depth and status distribution. Admin only."""
    statuses = ["scheduled", "processing", "published", "failed", "permanently_failed", "draft", "paused"]
    counts = {s: await db.posts.count_documents({"status": s}) for s in statuses}
    dlq_count = await db.posts.count_documents({"dlq_reason": {"$exists": True, "$ne": None}})
    return {"status_counts": counts, "dlq_count": dlq_count}


# ==================== STATS ====================

@api_router.get("/stats")
async def get_stats(current_user: User = Depends(get_current_user)):
    total_posts = await db.posts.count_documents({"user_id": current_user.user_id})
    scheduled_posts = await db.posts.count_documents({"user_id": current_user.user_id, "status": "scheduled"})
    published_posts = await db.posts.count_documents({"user_id": current_user.user_id, "status": "published"})
    connected_accounts = await db.social_accounts.count_documents({"user_id": current_user.user_id, "is_active": True})
    failed_posts = await db.posts.count_documents({"user_id": current_user.user_id, "status": {"$in": ["failed", "partial"]}})

    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "connected_accounts": connected_accounts,
        "failed_posts": failed_posts
    }


# ==================== CONTENT PAGES ====================

@api_router.get("/pages/terms")
async def get_terms():
    return {"content": "Terms of Service - SocialSync provides social media scheduling services..."}

@api_router.get("/pages/privacy")
async def get_privacy():
    return {"content": "Privacy Policy - We respect your privacy and protect your data..."}

# ==================== SCHEDULED POST PROCESSOR ====================

async def _download_url_to_temp(url: str, suffix: str = ".mp4") -> Optional[str]:
    """Download a URL to a temp file, return local path. Caller must delete."""
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")
        return None


async def publish_to_platform(platform: str, account: dict, post_doc: dict, trace_id: str) -> dict:
    """
    Publish content to a single platform.
    Returns:
      {"status": "success", "platform_post_id": "..."}
      {"status": "awaiting_ig_processing", "container_id": "..."}  — Instagram video
      {"status": "failed", "error": "...", "rate_limited": True, "retry_after_seconds": N}
      {"status": "failed", "error": "..."}
    """
    access_token = account.get("access_token", "")
    content = post_doc.get("content", "")
    media_urls = post_doc.get("media_urls", [])
    video_url = post_doc.get("video_url")
    media_url = media_urls[0] if media_urls else video_url

    def is_rate_limit_error(error_str: str) -> bool:
        s = error_str.lower()
        return any(k in s for k in ["429", "rate limit", "too many requests", "quota", "ratelimit"])

    def extract_retry_after(error_str: str) -> int:
        import re
        m = re.search(r"retry.after[:\s]+(\d+)", error_str, re.IGNORECASE)
        return int(m.group(1)) if m else 3600

    try:
        if platform == "twitter":
            from app.social.twitter import TwitterAuth
            twitter = TwitterAuth()
            result = await twitter.publish_tweet(access_token, content, media_urls or [])
            return {"status": "success", "platform_post_id": str(result or "")}

        elif platform == "instagram":
            from app.social.instagram import InstagramAuth
            ig = InstagramAuth()
            ig_user_id = account.get("platform_user_id", "")

            if video_url:
                # Non-blocking: create container only, return container_id
                # check_instagram_containers() will poll status and publish
                container_id = await ig.create_video_container(access_token, ig_user_id, video_url, content)
                return {"status": "awaiting_ig_processing", "container_id": container_id}
            else:
                pub_url = media_url or ""
                result = await ig.publish_to_instagram(access_token, ig_user_id, pub_url, content, "IMAGE")
                return {"status": "success", "platform_post_id": str(result)}

        elif platform == "facebook":
            from app.social.facebook import FacebookAuth
            fb = FacebookAuth()
            page_id = account.get("platform_user_id", "")
            page_token = account.get("page_access_token", access_token)
            if media_url:
                result = await fb.publish_to_facebook(page_token, page_id, media_url, content)
            else:
                async with httpx.AsyncClient() as http_client:
                    _fb_api_version = os.environ.get("FACEBOOK_API_VERSION", "v21.0")
                    resp = await http_client.post(
                        f"https://graph.facebook.com/{_fb_api_version}/{page_id}/feed",
                        data={"message": content, "access_token": page_token}
                    )
                    resp.raise_for_status()
                    result = resp.json().get("id", "")
            return {"status": "success", "platform_post_id": str(result)}

        elif platform == "linkedin":
            from app.social.linkedin import LinkedInAuth
            li = LinkedInAuth()
            person_urn = account.get("platform_user_id", "")
            result = await li.publish_post(access_token, person_urn, content, media_urls)
            return {"status": "success", "platform_post_id": str(result)}

        elif platform == "youtube":
            from app.social.google import GoogleAuth
            yt = GoogleAuth()
            if not video_url:
                return {"status": "failed", "error": "YouTube requires a video file"}

            title = post_doc.get("video_title") or "Untitled"
            cover_image = post_doc.get("cover_image_url")
            tmp_path = None

            try:
                # YouTube needs local file path — download from R2/URL to /tmp/
                ext = video_url.rsplit(".", 1)[-1].lower() if "." in video_url.split("/")[-1] else "mp4"
                tmp_path = await _download_url_to_temp(video_url, suffix=f".{ext}")
                if not tmp_path:
                    return {"status": "failed", "error": "Failed to download video for YouTube upload"}

                result = await yt.upload_video(access_token, tmp_path, title, content, cover_image_path=cover_image)
                return {"status": "success", "platform_post_id": str(result)}
            finally:
                # Always clean up temp file
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        elif platform == "tiktok":
            return {"status": "failed", "error": "TikTok publishing not yet configured — add credentials"}

        elif platform in ("bluesky", "threads"):
            return {"status": "failed", "error": f"{platform.title()} publishing not yet configured"}

        else:
            return {"status": "failed", "error": f"Unknown platform: {platform}"}

    except Exception as e:
        error_str = str(e)
        logging.error(f"[{trace_id}] Platform {platform} publish error: {error_str}")

        if is_rate_limit_error(error_str):
            return {
                "status": "failed",
                "error": error_str,
                "rate_limited": True,
                "retry_after_seconds": extract_retry_after(error_str)
            }
        return {"status": "failed", "error": error_str}



async def send_dlq_notification(user_doc: dict, post_doc: dict, failed_platforms: dict, trace_id: str, platform_results: dict):
    """
    Send email showing per-platform results.
    Only reports on platforms that permanently failed, and shows which succeeded.
    """
    if not RESEND_API_KEY:
        return

    # Section 20.12: respect notification preferences
    user_id = user_doc.get("user_id", "")
    if user_id:
        try:
            from utils.notification_prefs import should_notify
            if not await should_notify(db, user_id, "post.dlq", "email"):
                logging.info(f"DLQ notification suppressed by user prefs for {user_id}")
                return
        except Exception:
            pass  # never block notification on pref lookup failure

    email = user_doc.get('email')
    name = user_doc.get('name', 'there')
    content_preview = (post_doc.get('content', '') or '')[:100]

    # Build per-platform status rows
    platform_rows = ""
    for platform, pr in platform_results.items():
        if pr["status"] == "success":
            platform_rows += f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td><td style="padding:8px;border-bottom:1px solid #eee;color:#16A34A;">✓ Published</td></tr>'
        elif pr["status"] == "permanently_failed":
            err = pr.get("error", "Unknown error")[:120]
            platform_rows += f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td><td style="padding:8px;border-bottom:1px solid #eee;color:#DC2626;">✗ Failed after 3 attempts: {err}</td></tr>'
        else:
            platform_rows += f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td><td style="padding:8px;border-bottom:1px solid #eee;color:#D97706;">⟳ Retrying ({pr.get("retries", 0)}/3)</td></tr>'

    failed_count = len(failed_platforms)
    total_count = len(platform_results)
    succeeded_count = sum(1 for pr in platform_results.values() if pr["status"] == "success")

    subject_line = (
        f"Post failed on {failed_count} platform{'s' if failed_count > 1 else ''} - SocialEntangler"
        if succeeded_count > 0
        else "Post failed to publish - SocialEntangler"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .alert {{ background: #FEF2F2; border-left: 4px solid #EF4444; padding: 16px; border-radius: 4px; margin: 16px 0; }}
            .success {{ background: #F0FDF4; border-left: 4px solid #16A34A; padding: 16px; border-radius: 4px; margin: 16px 0; }}
            .code {{ background: #F3F4F6; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 12px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Publishing Report</h2>
            <p>Hi {name},</p>
            <p>Your post was published to <strong>{succeeded_count}/{total_count}</strong> platforms.
               {f'{failed_count} platform{"s" if failed_count > 1 else ""} failed after 3 retry attempts.' if failed_count else ''}</p>

            <div class="alert">
                <p><strong>Content:</strong> {content_preview}{'...' if len(post_doc.get('content', '')) > 100 else ''}</p>
                <p><strong>Trace ID:</strong> <span class="code">{trace_id}</span></p>
            </div>

            <h3>Platform Results</h3>
            <table>
                <thead><tr><th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Platform</th><th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Status</th></tr></thead>
                <tbody>{platform_rows}</tbody>
            </table>

            <p>You can retry failed platforms from your <a href="{FRONTEND_URL}/content">Content Library</a>.</p>
            <p style="color:#888;font-size:12px;">If this keeps happening, contact support with Trace ID: <span class="code">{trace_id}</span></p>
        </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [email],
            "subject": subject_line,
            "html": html_content
        }
        await asyncio.to_thread(resend.Emails.send, params)
        logging.info(f"DLQ notification sent to {email} for post {post_doc.get('id')}")
    except Exception as e:
        logging.error(f"Failed to send DLQ notification: {e}")

# ==================== STARTUP & SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    # MongoDB indexes — critical for scheduler performance at scale
    try:
        await db.posts.create_index([("user_id", 1), ("status", 1), ("scheduled_time", 1)])
        await db.posts.create_index([("status", 1), ("scheduled_time", 1)])
        await db.posts.create_index([("user_id", 1), ("created_at", -1)])
        await db.social_accounts.create_index([("user_id", 1), ("platform", 1), ("is_active", 1)])
        await db.users.create_index([("email", 1)], unique=True)
        await db.users.create_index([("user_id", 1)], unique=True)
        logging.info("MongoDB indexes created")
    except Exception as e:
        # Index may already exist with same or different name — continue startup
        logging.info(f"MongoDB index creation completed (some may already exist): {str(e)[:100]}")

@app.on_event("shutdown")
async def shutdown_event():
    client.close()
    logging.info("Application shutdown")

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

