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

@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Upload media files (images/videos)"""
    file_ext = file.filename.split('.')[-1]
    file_id = uuid.uuid4().hex[:12]
    file_url = f"/uploads/{file_id}.{file_ext}"
    
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / f"{file_id}.{file_ext}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"url": file_url, "filename": file.filename}

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

@api_router.get("/oauth/instagram/authorize")
async def instagram_authorize():
    """Initiate Instagram OAuth flow"""
    app_id = os.environ.get('INSTAGRAM_APP_ID')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not app_id:
        raise HTTPException(status_code=500, detail="Instagram App ID not configured")
    
    auth_url = (
        f"https://api.instagram.com/oauth/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user_profile,user_media"
        f"&response_type=code"
        f"&state=instagram"
    )
    
    return {"authorization_url": auth_url}

@api_router.post("/oauth/instagram/callback")
async def instagram_callback(request: Request, current_user: dict = Depends(get_current_user)):
    """Handle Instagram OAuth callback"""
    body = await request.json()
    code = body.get('code')
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    app_id = os.environ.get('INSTAGRAM_APP_ID')
    app_secret = os.environ.get('INSTAGRAM_APP_SECRET')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not all([app_id, app_secret]):
        raise HTTPException(status_code=500, detail="Instagram credentials not configured")
    
    try:
        # Exchange code for short-lived token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            user_id = token_data.get('user_id')
            
            # Get user profile
            profile_response = await client.get(
                f"https://graph.instagram.com/me",
                params={
                    "fields": "id,username",
                    "access_token": access_token
                }
            )
            
            if profile_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch Instagram profile")
            
            profile = profile_response.json()
            
            # Save to database
            account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['user_id'],
                "platform": "instagram",
                "platform_user_id": user_id,
                "username": profile.get('username'),
                "access_token": access_token,
                "token_expires_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.social_accounts.insert_one(account)
            
            return {
                "success": True,
                "platform": "instagram",
                "username": profile.get('username')
            }
            
    except Exception as e:
        logging.error(f"Instagram OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")

@api_router.get("/oauth/youtube/authorize")
async def youtube_authorize():
    """Initiate YouTube OAuth flow"""
    client_id = os.environ.get('YOUTUBE_CLIENT_ID')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not client_id:
        raise HTTPException(status_code=500, detail="YouTube Client ID not configured")
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
        f"&access_type=offline"
        f"&state=youtube"
    )
    
    return {"authorization_url": auth_url}

@api_router.post("/oauth/youtube/callback")
async def youtube_callback(request: Request, current_user: dict = Depends(get_current_user)):
    """Handle YouTube OAuth callback"""
    body = await request.json()
    code = body.get('code')
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    client_id = os.environ.get('YOUTUBE_CLIENT_ID')
    client_secret = os.environ.get('YOUTUBE_CLIENT_SECRET')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not all([client_id, client_secret]):
        raise HTTPException(status_code=500, detail="YouTube credentials not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            
            # Get channel info
            channel_response = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={
                    "part": "snippet",
                    "mine": "true"
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if channel_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch YouTube channel")
            
            channel_data = channel_response.json()
            if not channel_data.get('items'):
                raise HTTPException(status_code=404, detail="No YouTube channel found")
            
            channel = channel_data['items'][0]
            channel_id = channel['id']
            channel_title = channel['snippet']['title']
            
            # Save to database
            account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['user_id'],
                "platform": "youtube",
                "platform_user_id": channel_id,
                "username": channel_title,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.social_accounts.insert_one(account)
            
            return {
                "success": True,
                "platform": "youtube",
                "username": channel_title
            }
            
    except Exception as e:
        logging.error(f"YouTube OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")

@api_router.get("/oauth/facebook/authorize")
async def facebook_authorize():
    """Initiate Facebook OAuth flow"""
    app_id = os.environ.get('FACEBOOK_APP_ID')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not app_id:
        raise HTTPException(status_code=500, detail="Facebook App ID not configured")
    
    auth_url = (
        f"https://www.facebook.com/v18.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=pages_show_list,pages_read_engagement,pages_manage_posts"
        f"&response_type=code"
        f"&state=facebook"
    )
    
    return {"authorization_url": auth_url}

@api_router.post("/oauth/facebook/callback")
async def facebook_callback(request: Request, current_user: dict = Depends(get_current_user)):
    """Handle Facebook OAuth callback"""
    body = await request.json()
    code = body.get('code')
    
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    
    app_id = os.environ.get('FACEBOOK_APP_ID')
    app_secret = os.environ.get('FACEBOOK_APP_SECRET')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not all([app_id, app_secret]):
        raise HTTPException(status_code=500, detail="Facebook credentials not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "redirect_uri": redirect_uri,
                    "code": code
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            
            # Get user's Facebook pages
            pages_response = await client.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                params={"access_token": access_token}
            )
            
            if pages_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch Facebook pages")
            
            pages_data = pages_response.json()
            pages = pages_data.get('data', [])
            
            if not pages:
                raise HTTPException(status_code=404, detail="No Facebook pages found")
            
            # Use first page
            page = pages[0]
            
            # Save to database
            account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['user_id'],
                "platform": "facebook",
                "platform_user_id": page['id'],
                "username": page['name'],
                "access_token": page['access_token'],  # Page access token
                "token_expires_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.social_accounts.insert_one(account)
            
            return {
                "success": True,
                "platform": "facebook",
                "username": page['name']
            }
            
    except Exception as e:
        logging.error(f"Facebook OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")

@api_router.get("/oauth/twitter/authorize")
async def twitter_authorize():
    """Initiate Twitter OAuth 2.0 flow"""
    client_id = os.environ.get('TWITTER_CLIENT_ID')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not client_id:
        raise HTTPException(status_code=500, detail="Twitter Client ID not configured")
    
    # Generate PKCE code challenge
    import secrets
    import hashlib
    import base64
    
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')
    
    auth_url = (
        f"https://twitter.com/i/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=tweet.read tweet.write users.read offline.access"
        f"&state=twitter"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    
    # Store code_verifier in session or return it
    return {
        "authorization_url": auth_url,
        "code_verifier": code_verifier  # Frontend should store this temporarily
    }

@api_router.post("/oauth/twitter/callback")
async def twitter_callback(request: Request, current_user: dict = Depends(get_current_user)):
    """Handle Twitter OAuth callback"""
    body = await request.json()
    code = body.get('code')
    code_verifier = body.get('code_verifier')
    
    if not code or not code_verifier:
        raise HTTPException(status_code=400, detail="Missing code or code_verifier")
    
    client_id = os.environ.get('TWITTER_CLIENT_ID')
    client_secret = os.environ.get('TWITTER_CLIENT_SECRET')
    redirect_uri = os.environ.get('OAUTH_REDIRECT_URI')
    
    if not all([client_id, client_secret]):
        raise HTTPException(status_code=500, detail="Twitter credentials not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for token
            token_response = await client.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier
                },
                auth=(client_id, client_secret)
            )
            
            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to exchange code for token")
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            
            # Get user info
            user_response = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if user_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch Twitter user")
            
            user_data = user_response.json()
            twitter_user = user_data['data']
            
            # Save to database
            account = {
                "id": str(uuid.uuid4()),
                "user_id": current_user['user_id'],
                "platform": "twitter",
                "platform_user_id": twitter_user['id'],
                "username": twitter_user['username'],
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                "connected_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.social_accounts.insert_one(account)
            
            return {
                "success": True,
                "platform": "twitter",
                "username": twitter_user['username']
            }
            
    except Exception as e:
        logging.error(f"Twitter OAuth error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")

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
    
    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "connected_accounts": connected_accounts
    }

# ==================== CONTENT PAGES ====================

@api_router.get("/pages/terms")
async def get_terms():
    return {"content": "Terms of Service - SocialSync provides social media scheduling services..."}

@api_router.get("/pages/privacy")
async def get_privacy():
    return {"content": "Privacy Policy - We respect your privacy and protect your data..."}

# ==================== SCHEDULED POST PROCESSOR ====================

async def process_scheduled_posts():
    """Background job to publish scheduled posts"""
    try:
        now = datetime.now(timezone.utc)
        
        posts = await db.posts.find({
            "status": "scheduled",
            "scheduled_time": {"$lte": now.isoformat()}
        }).to_list(100)
        
        for post_doc in posts:
            await db.posts.update_one(
                {"id": post_doc['id']},
                {"$set": {
                    "status": "published",
                    "published_at": now.isoformat()
                }}
            )
            logging.info(f"Published post {post_doc['id']}")
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

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["http://localhost:3000", "https://code-repair-98.preview.emergentagent.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

