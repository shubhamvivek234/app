
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import bcrypt
from datetime import datetime, timezone, timedelta
import uuid

load_dotenv('backend/.env')

async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    print(f"Connecting to {mongo_url}, DB: {db_name}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Test User Details
    email = "test@example.com"
    password = "password123"
    # Hashing with bcrypt directly
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    user_data = {
        "user_id": str(uuid.uuid4()),
        "email": email,
        "name": "Test User",
        "password": hashed_password,
        "picture": "https://api.dicebear.com/7.x/avataaars/svg?seed=test",
        "email_verified": True,
        "created_at": datetime.now(timezone.utc),
        "subscription_status": "active",
        "subscription_plan": "monthly",
        "subscription_end_date": datetime.now(timezone.utc) + timedelta(days=30),
        "user_type": "founder",
        "onboarding_completed": True  # KEY: This bypasses onboarding
    }
    
    # Check if user exists and replace, or insert new
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        await db.users.replace_one({"email": email}, user_data)
        print(f"Updated existing test user: {email}")
    else:
        await db.users.insert_one(user_data)
        print(f"Created new test user: {email}")
        
    print("\nCredentials:")
    print(f"Email: {email}")
    print(f"Password: {password}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
