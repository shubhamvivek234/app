from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header, Cookie, UploadFile, File, Form
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
from passlib.context import CryptContext
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
import razorpay
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import resend
import httpx
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment
from paypalcheckoutsdk.orders import OrdersCreateRequest, OrdersCaptureRequest
import random
import shutil
import subprocess
import hashlib
import tempfile

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

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

# APScheduler for scheduled posts
scheduler = AsyncIOScheduler()

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
    subscription_end_date: Optional[datetime] = None

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
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    ai_generated: bool = False

class PostCreate(BaseModel):
    content: str
    post_type: str = "text"
    platforms: List[str]
    media_urls: Optional[List[str]] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[str] = None

class PostUpdate(BaseModel):
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None

class AIContentRequest(BaseModel):
    prompt: str
    platform: Optional[str] = None

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
    
    return User(**user_doc)

async def get_current_user(session_token: Optional[str] = Cookie(None), authorization: Optional[str] = Header(None)) -> User:
    # Try cookie first
    if session_token:
        return await get_current_user_from_cookie(session_token)
    
    # Fallback to Authorization header
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if user_doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
    
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
    return post

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

@api_router.post("/ai/generate-content")
async def generate_content(request: AIContentRequest, current_user: User = Depends(get_current_user)):
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="AI service not configured")
        
        platform_context = ""
        if request.platform:
            if request.platform == "twitter":
                platform_context = " Keep it under 280 characters for Twitter."
            elif request.platform == "linkedin":
                platform_context = " Make it professional for LinkedIn."
            elif request.platform == "instagram":
                platform_context = " Make it engaging for Instagram with relevant hashtags."
        
        system_message = f"You are a social media content expert. Generate engaging social media posts.{platform_context}"
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"content-gen-{current_user.user_id}-{uuid.uuid4()}",
            system_message=system_message
        ).with_model("openai", "gpt-5.2")
        
        user_message = UserMessage(text=request.prompt)
        response = await chat.send_message(user_message)
        
        return {"content": response}
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

@api_router.delete("/social-accounts/{account_id}")
async def disconnect_social_account(account_id: str, current_user: User = Depends(get_current_user)):
    result = await db.social_accounts.delete_one({"id": account_id, "user_id": current_user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account disconnected"}

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
                    resp = await http_client.post(
                        f"https://graph.facebook.com/v19.0/{page_id}/feed",
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


async def check_instagram_containers():
    """
    Separate 30s job: check Instagram video containers that are still processing.
    Non-blocking — never holds the thread waiting for Instagram.
    """
    try:
        now = datetime.now(timezone.utc)
        # Find posts with platforms in "awaiting_ig_processing" state
        posts = await db.posts.find(
            {"status": "publishing", "platform_results.instagram.status": "awaiting_ig_processing"},
            {"_id": 0}
        ).to_list(50)

        for post_doc in posts:
            post_id = post_doc["id"]
            trace_id = post_doc.get("trace_id", "")
            platform_results = post_doc.get("platform_results", {})
            ig_pr = platform_results.get("instagram", {})
            container_id = ig_pr.get("container_id")
            access_token = ig_pr.get("access_token_snapshot", "")
            ig_user_id = ig_pr.get("ig_user_id_snapshot", "")

            if not container_id:
                continue

            try:
                from app.social.instagram import InstagramAuth
                ig = InstagramAuth()
                status_code = await ig.check_container_status(access_token, container_id)

                if status_code == "FINISHED":
                    # Publish now
                    publish_result = await ig.publish_container(access_token, ig_user_id, container_id)
                    ig_pr["status"] = "success"
                    ig_pr["platform_post_id"] = publish_result
                    ig_pr["published_at"] = now.isoformat()
                    logging.info(f"[{trace_id}] ✓ Instagram container {container_id} published for post {post_id}")

                elif status_code == "ERROR":
                    ig_pr["retries"] = ig_pr.get("retries", 0) + 1
                    if ig_pr["retries"] >= MAX_RETRIES:
                        ig_pr["status"] = "permanently_failed"
                        ig_pr["error"] = "Instagram video processing failed"
                    else:
                        ig_pr["status"] = "failed"
                        ig_pr["error"] = "Instagram video processing error — will retry"
                        ig_pr["next_retry_at"] = get_next_retry_at(ig_pr["retries"]).isoformat()
                    logging.error(f"[{trace_id}] Instagram container {container_id} ERROR for post {post_id}")

                else:
                    # Still IN_PROGRESS — check again next tick
                    logging.debug(f"[{trace_id}] Instagram container {container_id} still processing ({status_code})")
                    continue

            except Exception as e:
                logging.error(f"[{trace_id}] Instagram container check failed: {e}")
                continue

            platform_results["instagram"] = ig_pr
            await _finalise_post_status(post_id, post_doc, platform_results, now)

    except Exception as e:
        logging.error(f"Instagram container check error: {e}")


async def _finalise_post_status(post_id: str, post_doc: dict, platform_results: dict, now: datetime):
    """
    Compute overall post status from platform_results and write to MongoDB.
    Sends DLQ notification if all terminal and any permanently failed.
    """
    statuses = [pr["status"] for pr in platform_results.values()]
    all_success = all(s == "success" for s in statuses)
    all_terminal = all(s in ("success", "permanently_failed") for s in statuses)
    any_success = any(s == "success" for s in statuses)

    if all_success:
        post_status = "published"
    elif all_terminal and any_success:
        post_status = "partial"
    elif all_terminal and not any_success:
        post_status = "failed"
    else:
        post_status = "publishing"

    update_fields = {
        "platform_results": platform_results,
        "status": post_status,
        "updated_at": now.isoformat(),
    }
    if post_status == "published":
        update_fields["published_at"] = now.isoformat()

    failed_platforms = {
        p: pr.get("error", "Unknown")
        for p, pr in platform_results.items()
        if pr["status"] == "permanently_failed"
    }
    if failed_platforms:
        update_fields["failure_reason"] = "; ".join(f"{p}: {err}" for p, err in failed_platforms.items())

    await db.posts.update_one({"id": post_id}, {"$set": update_fields})

    if post_status in ("failed", "partial") and all_terminal:
        user_doc = await db.users.find_one(
            {"user_id": post_doc["user_id"]},
            {"_id": 0, "email": 1, "name": 1}
        )
        if user_doc and RESEND_API_KEY:
            trace_id = post_doc.get("trace_id", "")
            await send_dlq_notification(user_doc, post_doc, failed_platforms, trace_id, platform_results)


async def process_scheduled_posts():
    """
    Background job (every 30s): per-platform publish with:
    - Atomic claim (findOneAndUpdate) prevents double-enqueue
    - Jitter (0-15s random delay) spreads burst load
    - Exponential backoff (5→15→60→180 min) between retries
    - Rate limit token bucket (skip, not fail, on 429)
    - Instagram video: non-blocking — stores container_id, checked by separate job
    """
    try:
        now = datetime.now(timezone.utc)

        # Atomically claim up to 50 posts due for processing.
        # findOneAndUpdate prevents two scheduler ticks from claiming the same post.
        claimed_posts = []
        for _ in range(50):
            claimed = await db.posts.find_one_and_update(
                {
                    "status": {"$in": ["scheduled", "publishing"]},
                    "scheduled_time": {"$lte": now.isoformat()},
                    # Don't re-claim posts already being processed this tick
                    "$or": [
                        {"claimed_at": {"$exists": False}},
                        {"claimed_at": {"$lte": (now - timedelta(minutes=5)).isoformat()}}
                    ]
                },
                {"$set": {"claimed_at": now.isoformat()}},
                return_document=True
            )
            if not claimed:
                break
            claimed_posts.append(claimed)

        if not claimed_posts:
            return

        logging.info(f"Scheduler claimed {len(claimed_posts)} posts for processing")

        for post_doc in claimed_posts:
            post_id = post_doc["id"]
            user_id = post_doc["user_id"]
            trace_id = post_doc.get("trace_id") or str(uuid.uuid4())[:8]
            platforms = post_doc.get("platforms", [])
            platform_results = post_doc.get("platform_results", {})

            # Initialise missing platform entries
            for p in platforms:
                if p not in platform_results:
                    platform_results[p] = {"status": "pending", "retries": 0}

            # Load user's connected accounts
            user_accounts = await db.social_accounts.find(
                {"user_id": user_id, "is_active": True}, {"_id": 0}
            ).to_list(100)
            accounts_by_platform = {acc["platform"]: acc for acc in user_accounts}

            # Process each platform independently
            for platform in platforms:
                pr = platform_results.get(platform, {"status": "pending", "retries": 0})

                # Skip terminal states
                if pr["status"] in ("success", "permanently_failed"):
                    continue

                # Skip awaiting Instagram container — handled by check_instagram_containers()
                if pr["status"] == "awaiting_ig_processing":
                    continue

                # Respect exponential backoff: skip if next_retry_at is in the future
                next_retry_at = pr.get("next_retry_at")
                if next_retry_at:
                    try:
                        retry_dt = datetime.fromisoformat(next_retry_at)
                        if retry_dt.tzinfo is None:
                            retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                        if retry_dt > now:
                            logging.debug(f"[{trace_id}] {platform}: backoff until {next_retry_at}, skipping")
                            continue
                    except Exception:
                        pass

                # Check retry cap
                if pr.get("retries", 0) >= MAX_RETRIES:
                    pr["status"] = "permanently_failed"
                    platform_results[platform] = pr
                    continue

                # Check rate limit token bucket
                if not check_rate_limit(user_id, platform):
                    logging.warning(f"[{trace_id}] {platform} rate limit — skipping (not a failure)")
                    continue  # Don't count as a retry failure

                # Check connected account exists
                account = accounts_by_platform.get(platform)
                if not account:
                    pr["status"] = "permanently_failed"
                    pr["error"] = f"No connected {platform} account found"
                    platform_results[platform] = pr
                    continue

                # Apply jitter (0-15s) to spread burst load
                jitter_secs = random.uniform(0, 15)
                await asyncio.sleep(jitter_secs)

                logging.info(f"[{trace_id}] Publishing post {post_id} to {platform} (attempt {pr.get('retries', 0) + 1}/{MAX_RETRIES})")
                result = await publish_to_platform(platform, account, post_doc, trace_id)

                if result["status"] == "success":
                    pr["status"] = "success"
                    pr["platform_post_id"] = result.get("platform_post_id", "")
                    pr["published_at"] = now.isoformat()
                    pr.pop("next_retry_at", None)
                    logging.info(f"[{trace_id}] ✓ {platform} succeeded for post {post_id}")

                elif result["status"] == "awaiting_ig_processing":
                    # Non-blocking Instagram video — container created, will check next tick
                    pr["status"] = "awaiting_ig_processing"
                    pr["container_id"] = result.get("container_id")
                    pr["access_token_snapshot"] = account.get("access_token", "")
                    pr["ig_user_id_snapshot"] = account.get("platform_user_id", "")
                    logging.info(f"[{trace_id}] Instagram video container {result.get('container_id')} created — awaiting processing")

                elif result.get("rate_limited"):
                    # 429 from platform — record pause, do NOT count as retry
                    retry_after = result.get("retry_after_seconds", 3600)
                    record_rate_limit_hit(user_id, platform, retry_after)
                    logging.warning(f"[{trace_id}] {platform} 429 — paused {retry_after}s, not counted as retry")

                else:
                    pr["retries"] = pr.get("retries", 0) + 1
                    pr["error"] = result.get("error", "Unknown error")
                    pr["last_attempt"] = now.isoformat()

                    if pr["retries"] >= MAX_RETRIES:
                        pr["status"] = "permanently_failed"
                        logging.error(f"[{trace_id}] ✗ {platform} permanently failed for post {post_id}: {pr['error']}")
                    else:
                        pr["status"] = "failed"
                        pr["next_retry_at"] = get_next_retry_at(pr["retries"]).isoformat()
                        logging.warning(f"[{trace_id}] ✗ {platform} attempt {pr['retries']}/{MAX_RETRIES}, next retry at {pr['next_retry_at']}")

                platform_results[platform] = pr

            # Write final status
            await _finalise_post_status(post_id, post_doc, platform_results, now)

    except Exception as e:
        logging.error(f"Scheduled post processing error: {e}")


async def send_dlq_notification(user_doc: dict, post_doc: dict, failed_platforms: dict, trace_id: str, platform_results: dict):
    """
    Send email showing per-platform results.
    Only reports on platforms that permanently failed, and shows which succeeded.
    """
    if not RESEND_API_KEY:
        return

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
    await db.posts.create_index([("user_id", 1), ("status", 1), ("scheduled_time", 1)])
    await db.posts.create_index([("status", 1), ("scheduled_time", 1)])
    await db.posts.create_index([("user_id", 1), ("created_at", -1)])
    await db.social_accounts.create_index([("user_id", 1), ("platform", 1), ("is_active", 1)])
    await db.users.create_index([("email", 1)], unique=True)
    await db.users.create_index([("user_id", 1)], unique=True)
    logging.info("MongoDB indexes created")

    # Architecture spec: every 30 seconds (not 60)
    scheduler.add_job(process_scheduled_posts, 'interval', seconds=30)
    scheduler.add_job(check_instagram_containers, 'interval', seconds=30)
    scheduler.start()
    logging.info("Scheduler started — 30s interval")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
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

