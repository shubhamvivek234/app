from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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
import asyncio

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

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()

# Stripe
stripe_api_key = os.environ.get('STRIPE_API_KEY')

# Razorpay (user needs to add their keys)
razorpay_key_id = os.environ.get('RAZORPAY_KEY_ID', '')
razorpay_key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
razorpay_client = None
if razorpay_key_id and razorpay_key_secret:
    razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    subscription_status: str = "free"  # free, active, expired
    subscription_plan: Optional[str] = None  # monthly, yearly
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
    platforms: List[str]  # ["twitter", "instagram", "linkedin"]
    media_urls: Optional[List[str]] = []
    scheduled_time: Optional[datetime] = None
    status: str = "draft"  # draft, scheduled, published, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None
    ai_generated: bool = False

class PostCreate(BaseModel):
    content: str
    platforms: List[str]
    media_urls: Optional[List[str]] = []
    scheduled_time: Optional[str] = None  # ISO format string

class PostUpdate(BaseModel):
    content: Optional[str] = None
    platforms: Optional[List[str]] = None
    media_urls: Optional[List[str]] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None

class AIContentRequest(BaseModel):
    prompt: str
    platform: Optional[str] = None

class SocialAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    platform: str  # twitter, instagram, linkedin
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
    # In production, you'd handle OAuth flow here

class PaymentTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    session_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount: float
    currency: str
    plan: str  # monthly, yearly
    payment_method: str  # stripe, razorpay
    payment_status: str = "pending"  # pending, paid, failed, expired
    metadata: Optional[Dict[str, Any]] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CheckoutRequest(BaseModel):
    plan: str  # monthly, yearly
    payment_method: str  # stripe, razorpay

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

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user_doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
    
    return User(**user_doc)

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/signup", response_model=Token)
async def signup(user_data: UserSignup):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=user_data.email,
        name=user_data.name
    )
    user_dict = user.model_dump()
    user_dict['password'] = hash_password(user_data.password)
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    
    await db.users.insert_one(user_dict)
    
    # Create token
    access_token = create_access_token({"sub": user.id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user=user.model_dump(mode='json')
    )

@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user_doc = await db.users.find_one({"email": credentials.email})
    if not user_doc:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if not verify_password(credentials.password, user_doc['password']):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    # Parse dates
    if isinstance(user_doc.get('created_at'), str):
        user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
    if user_doc.get('subscription_end_date') and isinstance(user_doc['subscription_end_date'], str):
        user_doc['subscription_end_date'] = datetime.fromisoformat(user_doc['subscription_end_date'])
    
    user = User(**{k: v for k, v in user_doc.items() if k != 'password'})
    access_token = create_access_token({"sub": user.id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user=user.model_dump(mode='json')
    )

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# ==================== POST ROUTES ====================

@api_router.post("/posts", response_model=Post)
async def create_post(post_data: PostCreate, current_user: User = Depends(get_current_user)):
    # Check subscription for scheduling
    if post_data.scheduled_time and current_user.subscription_status != "active":
        raise HTTPException(status_code=403, detail="Scheduling requires active subscription")
    
    scheduled_time = None
    status = "draft"
    if post_data.scheduled_time:
        scheduled_time = datetime.fromisoformat(post_data.scheduled_time.replace('Z', '+00:00'))
        status = "scheduled"
    
    post = Post(
        user_id=current_user.id,
        content=post_data.content,
        platforms=post_data.platforms,
        media_urls=post_data.media_urls or [],
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
    query = {"user_id": current_user.id}
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
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.id}, {"_id": 0})
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
    post = await db.posts.find_one({"id": post_id, "user_id": current_user.id})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    update_dict = {k: v for k, v in post_data.model_dump(exclude_unset=True).items() if v is not None}
    
    if 'scheduled_time' in update_dict:
        if update_dict['scheduled_time']:
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
    result = await db.posts.delete_one({"id": post_id, "user_id": current_user.id})
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
            session_id=f"content-gen-{current_user.id}-{uuid.uuid4()}",
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
    # Check if already connected
    existing = await db.social_accounts.find_one({
        "user_id": current_user.id,
        "platform": account_data.platform
    })
    
    if existing:
        raise HTTPException(status_code=400, detail=f"{account_data.platform} already connected")
    
    # In production, implement OAuth flow here
    account = SocialAccount(
        user_id=current_user.id,
        platform=account_data.platform,
        platform_username=account_data.platform_username,
        # OAuth tokens would be stored here
    )
    
    account_dict = account.model_dump()
    account_dict['connected_at'] = account_dict['connected_at'].isoformat()
    
    await db.social_accounts.insert_one(account_dict)
    return account

@api_router.get("/social-accounts", response_model=List[SocialAccount])
async def get_social_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.social_accounts.find({"user_id": current_user.id}, {"_id": 0}).to_list(100)
    
    for account in accounts:
        if isinstance(account.get('connected_at'), str):
            account['connected_at'] = datetime.fromisoformat(account['connected_at'])
        if account.get('token_expiry') and isinstance(account['token_expiry'], str):
            account['token_expiry'] = datetime.fromisoformat(account['token_expiry'])
    
    return accounts

@api_router.delete("/social-accounts/{account_id}")
async def disconnect_social_account(account_id: str, current_user: User = Depends(get_current_user)):
    result = await db.social_accounts.delete_one({"id": account_id, "user_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account disconnected"}

# ==================== PAYMENTS - STRIPE ====================

PRICING = {
    "monthly": {"amount": 500.0, "currency": "INR", "duration": 30},
    "yearly": {"amount": 3000.0, "currency": "INR", "duration": 365}
}

@api_router.post("/payments/checkout", response_model=CheckoutSessionResponse)
async def create_checkout(checkout_req: CheckoutRequest, request: Request, current_user: User = Depends(get_current_user)):
    if checkout_req.plan not in PRICING:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    plan_info = PRICING[checkout_req.plan]
    origin_url = request.headers.get("origin", "http://localhost:3000")
    
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
                    "user_id": current_user.id,
                    "plan": checkout_req.plan,
                    "email": current_user.email
                }
            )
            
            session = await stripe_checkout.create_checkout_session(checkout_request)
            
            # Create transaction record
            transaction = PaymentTransaction(
                user_id=current_user.id,
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
            raise HTTPException(status_code=400, detail="Razorpay not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env")
        
        try:
            # Create Razorpay order
            amount_paise = int(plan_info["amount"] * 100)
            order_data = {
                "amount": amount_paise,
                "currency": plan_info["currency"],
                "payment_capture": 1
            }
            order = razorpay_client.order.create(data=order_data)
            
            # Create transaction record
            transaction = PaymentTransaction(
                user_id=current_user.id,
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
    
    raise HTTPException(status_code=400, detail="Invalid payment method")

@api_router.get("/payments/status/{session_id}", response_model=CheckoutStatusResponse)
async def get_payment_status(session_id: str, current_user: User = Depends(get_current_user)):
    transaction = await db.payment_transactions.find_one({"session_id": session_id, "user_id": current_user.id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if transaction['payment_method'] == "stripe":
        try:
            webhook_url = ""  # Not needed for status check
            stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
            status_response = await stripe_checkout.get_checkout_status(session_id)
            
            # Update transaction if status changed
            if status_response.payment_status == "paid" and transaction['payment_status'] != "paid":
                # Update user subscription
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
                
                await db.users.update_one(
                    {"id": current_user.id},
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
        
        webhook_url = ""  # Not needed for webhook handling
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
        
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.event_type == "checkout.session.completed":
            session_id = webhook_response.session_id
            
            transaction = await db.payment_transactions.find_one({"session_id": session_id})
            if transaction and transaction['payment_status'] != "paid":
                # Update subscription
                plan_info = PRICING[transaction['plan']]
                end_date = datetime.now(timezone.utc) + timedelta(days=plan_info['duration'])
                
                await db.users.update_one(
                    {"id": transaction['user_id']},
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
    total_posts = await db.posts.count_documents({"user_id": current_user.id})
    scheduled_posts = await db.posts.count_documents({"user_id": current_user.id, "status": "scheduled"})
    published_posts = await db.posts.count_documents({"user_id": current_user.id, "status": "published"})
    connected_accounts = await db.social_accounts.count_documents({"user_id": current_user.id, "is_active": True})
    
    return {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "connected_accounts": connected_accounts
    }

# ==================== SCHEDULED POST PROCESSOR ====================

async def process_scheduled_posts():
    """Background job to publish scheduled posts"""
    try:
        now = datetime.now(timezone.utc)
        
        # Find posts that should be published
        posts = await db.posts.find({
            "status": "scheduled",
            "scheduled_time": {"$lte": now.isoformat()}
        }).to_list(100)
        
        for post_doc in posts:
            # In production, implement actual posting to social media platforms
            # For now, mark as published
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
    # Start scheduler
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
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)