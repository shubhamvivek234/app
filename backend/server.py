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
import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionResponse, CheckoutStatusResponse, CheckoutSessionRequest
import razorpay
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import resend
import httpx
from app.social.facebook import FacebookAuth
from app.social.instagram import InstagramAuth
from app.social.google import GoogleAuth
from app.social.twitter import TwitterAuth
from app.social.linkedin import LinkedInAuth
# from paypal_checkout_sdk.core import PayPalHttpClient, SandboxEnvironment
# from paypal_checkout_sdk.orders import OrdersCreateRequest, OrdersCaptureRequest

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
client = AsyncIOMotorClient(mongo_url)
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

# CORS Configuration
origins = [
    "http://localhost:3000",
    "http://localhost:9500",
    "http://127.0.0.1:9500",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:9500",
    "http://0.0.0.0:3000",
    "null", # Logic sometimes sends null origin for local files or redirects
    FRONTEND_URL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow ALL for development to eliminate CORS as a variable
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin
try:
    cred = credentials.Certificate(os.path.join(ROOT_DIR, 'serviceAccountKey.json'))
    firebase_admin.initialize_app(cred)
    logging.info("Firebase Admin initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize Firebase Admin: {e}")
    # In production, this should probably crash the app if auth is critical


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

class PostCreate(BaseModel):
    content: str
    post_type: str = "text"
    platforms: List[str]
    accounts: List[str] = []
    media_urls: Optional[List[str]] = []
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_privacy: Optional[str] = "public"
    cover_image: Optional[str] = None
    scheduled_time: Optional[str] = None

class PostUpdate(BaseModel):
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    accounts: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    video_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    video_title: Optional[str] = None
    youtube_title: Optional[str] = None
    youtube_privacy: Optional[str] = None
    cover_image: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None

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
    
    try:
        # 2. Verify Firebase ID Token
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        
        if not email:
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: No email")

        # 3. Sync User to MongoDB
        user_doc = await db.users.find_one({"user_id": uid})
        
        if not user_doc:
            # Fallback: check if they exist by email (e.g., from mock flow)
            user_doc = await db.users.find_one({"email": email})
            
            if user_doc:
                # Merge existing legacy user to the new Firebase UID
                logging.info(f"Merging legacy user {user_doc['user_id']} with new Firebase UID {uid} for email {email}")
                await db.users.update_one(
                    {"email": email},
                    {"$set": {"user_id": uid}}
                )
                
                # Also update related tables to maintain referential integrity
                await db.posts.update_many({"user_id": user_doc["user_id"]}, {"$set": {"user_id": uid}})
                await db.social_accounts.update_many({"user_id": user_doc["user_id"]}, {"$set": {"user_id": uid}})
                await db.payment_transactions.update_many({"user_id": user_doc["user_id"]}, {"$set": {"user_id": uid}})
                
                # Refresh local user_doc
                user_doc["user_id"] = uid
            else:
                # Truly a new user
                new_user = {
                    "user_id": uid,
                    "email": email,
                    "name": decoded_token.get('name', 'User'),
                    "picture": decoded_token.get('picture'),
                    "email_verified": decoded_token.get('email_verified', False),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "subscription_status": "free",
                    "onboarding_completed": False
                }
                await db.users.insert_one(new_user)
                user_doc = new_user
        else:
             # Optional: Update existing user info if needed?
             pass

        # 4. Check Subscription Status (Logic from previous implementation)
        # ... reusing existing subscription checking logic ...
        
        if isinstance(user_doc.get('created_at'), str):
             user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
             
        # ... (rest of date parsing) ... 

        return User(**user_doc)

    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token")
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except Exception as e:
        logging.error(f"Auth Error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")
    
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
            # Update existing user
            user_id = user_doc["user_id"]
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "name": user_info.get("name", user_doc.get("name")),
                    "picture": user_info.get("picture", user_doc.get("picture")),
                    "email_verified": True
                }}
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
        
        # 4. Create Session
        session_token = str(uuid.uuid4()) # Simple session token
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # 5. Redirect to Frontend with Token
        redirect_url = f"{FRONTEND_URL}/auth/callback?token={session_token}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logging.error(f"Google auth error: {e}")
        # Redirect to login with error
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_failed")


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

@api_router.patch("/auth/me", response_model=User)
async def update_me(
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update current user profile"""
    # Filter allowed fields
    allowed_fields = ['user_type', 'onboarding_completed', 'name']
    update_fields = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not update_fields:
        return current_user
    
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
        status=status
    )
    
    post_dict = post.model_dump()
    post_dict['created_at'] = post_dict['created_at'].isoformat()
    if post_dict.get('scheduled_time'):
        post_dict['scheduled_time'] = post_dict['scheduled_time'].isoformat()
    
    await db.posts.insert_one(post_dict)
    return post



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

# ==================== OAUTH ENDPOINTS ====================

@api_router.get("/oauth/facebook/authorize")
async def facebook_authorize():
    """Initiate Facebook OAuth flow (for both FB Pages and Instagram)"""
    fb_auth = FacebookAuth()
    
    # Generate random state
    state = str(uuid.uuid4())
    
    # Store state in cookie or DB? For now just return URL
    auth_url = fb_auth.get_auth_url(state)
    
    return {"authorization_url": auth_url}

@api_router.post("/oauth/facebook/callback")
async def facebook_callback(request: Request, current_user: User = Depends(get_current_user)):
    """Handle Facebook OAuth callback"""
    body = await request.json()
    code = body.get('code')
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    fb_auth = FacebookAuth()
    
    try:
        # 1. Exchange code for short-lived token
        token_data = await fb_auth.exchange_code_for_token(code)
        short_token = token_data.get('access_token')
        
        # 2. Exchange for long-lived token (60 days)
        long_token_data = await fb_auth.get_long_lived_token(short_token)
        access_token = long_token_data.get('access_token')
        expires_in = long_token_data.get('expires_in', 5184000) # Default 60 days
        
        # 3. Get User Profile (optional, for logging)
        # user_profile = await fb_auth.get_user_profile(access_token)
        
        # 4. Get Accounts (Pages and Instagram)
        accounts_data = await fb_auth.get_accounts(access_token)
        
        connected_accounts = []
        
        for item in accounts_data:
            # Facebook Page
            page_id = item.get('id')
            page_name = item.get('name')
            page_token = item.get('access_token')
            
            # Save Facebook Page
            fb_account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user.user_id,
                "platform": "facebook",
                "platform_user_id": page_id,
                "username": page_name,
                "access_token": page_token, # Page access token
                "token_expires_at": None, # Page tokens last indefinitely if user token is valid?
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert (update if exists)
            await db.social_accounts.update_one(
                {"user_id": current_user.user_id, "platform": "facebook", "platform_user_id": page_id},
                {"$set": fb_account},
                upsert=True
            )
            connected_accounts.append({"platform": "facebook", "name": page_name})
            
            # Instagram Business Account (if linked)
            ig_data = item.get('instagram_business_account')
            if ig_data:
                ig_id = ig_data.get('id')
                ig_username = ig_data.get('username')
                
                ig_account = {
                    "id": str(uuid.uuid4()),
                    "user_id": current_user.user_id,
                    "platform": "instagram",
                    "platform_user_id": ig_id,
                    "username": ig_username,
                    "access_token": page_token, # IG Graph API uses the Page Token!
                    "token_expires_at": None,
                    "connected_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db.social_accounts.update_one(
                    {"user_id": current_user.user_id, "platform": "instagram", "platform_user_id": ig_id},
                    {"$set": ig_account},
                    upsert=True
                )
                connected_accounts.append({"platform": "instagram", "name": ig_username})

        return {
            "success": True,
            "connected_accounts": connected_accounts
        }
            
    except Exception as e:
        logging.error(f"Facebook OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")



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
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
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
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platform=twitter")

    except Exception as e:
        logging.error(f"Twitter OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed")

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
    if error or not code:
        error_msg = error or "No authorization code provided"
        logging.error(f"LinkedIn OAuth error: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

    user_id_from_state, return_to = _parse_oauth_state(state or "")
    if not user_id_from_state:
        logging.error("LinkedIn OAuth callback: Invalid state")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")

    try:
        li_auth = LinkedInAuth()
        token_data = await li_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 5184000) # Default 60 days

        # Get profile
        li_profile = await li_auth.get_user_profile(access_token)
        
        # OIDC info returns 'sub' as ID
        platform_user_id = li_profile.get('sub')
        
        li_account = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_from_state,
            "platform": "linkedin",
            "platform_user_id": platform_user_id,
            "username": li_profile.get('name', 'LinkedIn User'),
            "platform_username": li_profile.get('given_name', 'linkedin_user'),
            "access_token": access_token,
            "refresh_token": None, # LinkedIn doesn't always return refresh token for member tokens
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": li_profile.get('picture'),
            "is_active": True
        }

        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "linkedin", "platform_user_id": platform_user_id},
            {"$set": li_account},
            upsert=True
        )

        logging.info(f"[LinkedIn] Connected: {li_profile.get('name')} for user {user_id_from_state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platform=linkedin")

    except Exception as e:
        logging.error(f"LinkedIn OAuth error: {e}")
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
async def youtube_authorize(returnTo: Optional[str] = "accounts"):
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
    body = await request.json()
    code = body.get('code')
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    google_auth = GoogleAuth()
    
    try:
        # 1. Exchange code for token
        # IMPORTANT: Use the YOUTUBE redirect URI, not the default login one
        token_data = await google_auth.exchange_code_for_token(code, redirect_uri=google_auth.youtube_redirect_uri)
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token') # Important for offline access
        expires_in = token_data.get('expires_in', 3600)
        
        # 2. Get Channel Info
        channel_info = await google_auth.get_channel_info(access_token)
        channel_id = channel_info['id']
        snippet = channel_info['snippet']
        channel_title = snippet['title']
        
        # 3. Save to database
        picture_url = snippet.get('thumbnails', {}).get('default', {}).get('url')
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
            "connected_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert
        await db.social_accounts.update_one(
            {"user_id": current_user.user_id, "platform": "youtube", "platform_user_id": channel_id},
            {"$set": account},
            upsert=True
        )
        
        return {
            "success": True,
            "connected_accounts": [{"platform": "youtube", "name": channel_title}],
            "return_to": body.get('state', '').split(':')[-1] if ':' in body.get('state', '') else 'accounts'
        }
            
    except Exception as e:
        logging.error(f"YouTube OAuth error: {e}")
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
        # 1. Exchange code for short-lived token
        token_data = await fb_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logging.error(f"No access token returned from Meta: {token_data}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=no_token")
        
        # 2. Get Long-Lived User Token (60 days)
        long_lived_data = await fb_auth.get_long_lived_token(access_token)
        long_lived_token = long_lived_data.get('access_token', access_token)
        
        # 3. Get personal Facebook profile (always saved as connected account)
        fb_profile = await fb_auth.get_user_profile(long_lived_token)
        fb_picture = fb_profile.get('picture', {}).get('data', {}).get('url') if isinstance(fb_profile.get('picture'), dict) else fb_profile.get('picture')
        personal_account = {
            "id": str(uuid.uuid4()),
            "user_id": current_user.user_id,
            "platform": "facebook",
            "platform_user_id": fb_profile['id'],
            "username": fb_profile.get('name', 'Facebook User'),
            "platform_username": fb_profile.get('name', 'Facebook User'),
            "access_token": long_lived_token,
            "refresh_token": None,
            "token_expires_at": None,
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
        logging.info(f"[Facebook] Saved personal profile: {fb_profile.get('name')} (ID: {fb_profile['id']})")

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
                "token_expires_at": None,
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
                    "token_expires_at": None, 
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
            "token_expires_at": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": picture_url,
            "is_active": True
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
    if error or not code:
        error_msg = error or "No authorization code provided"
        logging.error(f"LinkedIn OAuth error: {error_msg}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={error_msg}")

    # Identify user directly from state string
    current_user = None
    user_id_from_state, return_to = _parse_oauth_state(state or "")
    logging.info(f"[LinkedIn] Callback state parsed: user_id={user_id_from_state}, return_to={return_to}")
    
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
                logging.error(f"User model error in LinkedIn callback: {e}")

    if not current_user:
        logging.error(f"LinkedIn OAuth callback: No authenticated user found for state={state}")
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_required")
    
    li_auth = LinkedInAuth()
    
    try:
        # 1. Exchange code for token
        token_data = await li_auth.exchange_code_for_token(code)
        access_token = token_data.get('access_token')
        
        if not access_token:
            logging.error(f"No access token returned from LinkedIn: {token_data}")
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=no_token")
        
        # 2. Get User Profile
        profile = await li_auth.get_user_profile(access_token)
        
        # 3. Save Account
        li_account = {
            "id": str(uuid.uuid4()),
            "user_id": user_id_from_state,
            "platform": "linkedin",
            "platform_user_id": profile['sub'], # OIDC 'sub' is the unique ID
            "username": profile.get('name', 'LinkedIn User'),
            "platform_username": profile.get('name', 'LinkedIn User'),
            "access_token": access_token,
            "refresh_token": token_data.get('refresh_token'),
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat(),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": profile.get('picture'),
            "is_active": True
        }
        await db.social_accounts.update_one(
            {"user_id": user_id_from_state, "platform": "linkedin", "platform_user_id": profile['sub']},
            {"$set": li_account},
            upsert=True
        )
        
        logging.info(f"LinkedIn OAuth success for user {user_id_from_state}: {profile.get('name')}")
        return RedirectResponse(url=f"{FRONTEND_URL}/{return_to}?connected=true&platforms=linkedin")
            
    except Exception as e:
        logging.error(f"LinkedIn OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?error=oauth_failed&message={str(e)}")

# ==================== SCHEDULED POST PROCESSOR ====================

async def process_scheduled_posts():
    """Background job to publish scheduled posts"""
    try:
        now = datetime.now(timezone.utc)
        
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
            
            for account_id in accounts:
                # Fetch full account details to get token
                account = await db.social_accounts.find_one({"id": account_id})
                if not account:
                    continue
                    
                platform = account['platform']
                token = account['access_token']
                platform_user_id = account['platform_user_id']
                
                try:
                    # Download file locally if it's a remote URL (Firebase) and we need to upload FILE (YouTube)
                    temp_file_path = None
                    cover_temp_path = None
                    local_cover_path = None
                    if media_url.startswith("http") and platform == 'youtube':
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
                        await fb_auth.publish_to_facebook(
                            access_token=token,
                            page_id=platform_user_id,
                            media_url=media_url, # Now using direct Firebase URL (Public)
                            message=post_doc.get('caption', ''),
                            media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                        )
                    elif platform == 'instagram':
                        await fb_auth.publish_to_instagram(
                            access_token=token,
                            ig_user_id=platform_user_id,
                            media_url=media_url, # Now using direct Firebase URL (Public)
                            caption=post_doc.get('caption', ''),
                            media_type="VIDEO" if "video" in post_doc.get('post_type', 'text') else "IMAGE"
                        )
                    elif platform == 'youtube':
                        if local_file_path and os.path.exists(local_file_path):
                            try:
                                raw_title = post_doc.get('youtube_title') or post_doc.get('video_title') or post_doc.get('caption') or 'New Video'
                                safe_title = raw_title[:100] if isinstance(raw_title, str) else 'New Video'
                                await google_auth.upload_video(
                                    access_token=token,
                                    file_path=local_file_path,
                                    title=safe_title,
                                    description=post_doc.get('caption') or '',
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
                                            description=post_doc.get('caption') or '',
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
                        await tw_auth.publish_tweet(
                            access_token=token,
                            text=post_doc.get('caption', ''),
                            media_urls=[media_url] if media_url else None
                        )
                    elif platform == 'linkedin':
                        await li_auth.publish_post(
                            access_token=token,
                            person_urn=platform_user_id,
                            text=post_doc.get('caption', ''),
                            media_urls=[media_url] if media_url else None
                        )

                            
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Failed to publish to {platform}: {error_msg}")
                    has_error = True
                    error_details.append(f"{platform}: {error_msg}")
                    # Continue attempting next account
            
            # Evaluate attempt success and manage retries/notifications
            if has_error:
                retry_count = post_doc.get("retry_count", 0) + 1
                if retry_count >= 3:
                    # Definitive failure after 3 attempts
                    await db.posts.update_one(
                        {"id": post_id},
                        {"$set": {
                            "status": "failed",
                            "retry_count": retry_count,
                            "error": " | ".join(error_details)
                        }}
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
                    await db.posts.update_one(
                        {"id": post_id},
                        {"$set": {
                            "status": "scheduled",
                            "retry_count": retry_count,
                            "scheduled_time": next_attempt.isoformat()
                        }}
                    )
                    logging.info(f"Post {post_id} failed attempt {retry_count}. Retrying at {next_attempt.isoformat()}.")
            else:
                # Definitive Success
                await db.posts.update_one(
                    {"id": post_id},
                    {"$set": {
                        "status": "published",
                        "published_at": now.isoformat()
                    }}
                )
                # Create Success Notification
                platforms_str = ", ".join([p.capitalize() for p in post_doc.get("platforms", [])])
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

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    client.close()
    logging.info("Application shutdown")

# ==================== UPLOADS ====================

# Ensure uploads directory exists
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

@api_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...), 
    current_user: User = Depends(get_current_user)
):
    """
    Upload a media file (image/video) to the local server
    Returns the public URL to access the file
    """
    try:
        # Create unique filename
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'bin'
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        
        # Save file to uploads directory
        file_path = UPLOADS_DIR / unique_filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        # Return URL (assuming backend is running on 8001 or using NGROK)
        # Using a relative path that the frontend can prefix with the backend URL
        file_url = f"/uploads/{unique_filename}"
        
        return {
            "success": True,
            "url": file_url,
            "filename": file.filename,
            "content_type": file.content_type
        }
    except Exception as e:
        logging.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file")

# Include router
app.include_router(api_router)

# Add static files serving for uploads
from fastapi.staticfiles import StaticFiles
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

origins = [
    "http://localhost:3000", 
    "http://localhost:9500",
    "https://postflow-25.preview.emergentagent.com"
]

# Add origins from environment variable
if os.environ.get("CORS_ORIGINS"):
    origins.extend(os.environ.get("CORS_ORIGINS").split(","))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

