import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def set_active_subscription(email: str):
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print(f"Updating subscription for {email}...")
    
    result = await db.users.update_one(
        {"email": email},
        {"$set": {
            "subscription_status": "active",
            "subscription_plan": "premium_test",
            "subscription_end_date": "2030-01-01T00:00:00",
            "onboarding_completed": True
        }}
    )
    
    if result.matched_count > 0:
        print(f"Successfully updated user {email} to ACTIVE subscription.")
    else:
        print(f"User {email} not found. Creating it now...")
        new_user = {
            "user_id": f"user_{email.split('@')[0]}",
            "email": email,
            "name": "Test User",
            "picture": None,
            "email_verified": True,
            "subscription_status": "active",
            "subscription_plan": "premium_test",
            "subscription_end_date": "2030-01-01T00:00:00",
            "onboarding_completed": True,
            "created_at": "2024-01-01T00:00:00"
        }
        await db.users.insert_one(new_user)
        print(f"Created new PREMIUM user: {email}")

if __name__ == "__main__":
    email = "shubhamtest@gmail.com"
    asyncio.run(set_active_subscription(email))
