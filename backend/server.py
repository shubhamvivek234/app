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

# Create the main app
app = FastAPI(title="Social Scheduler API")
api_router = APIRouter(prefix="/api")

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
