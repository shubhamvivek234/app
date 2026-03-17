import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def force_activate_test_user(email: str):
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Update ALL documents matching this email to ensure both legacy and new records are updated
    print(f"Forcing subscription update for {email}...")
    
    result = await db.users.update_many(
        {"email": email},
        {"$set": {
            "subscription_status": "active",
            "subscription_plan": "premium_test",
            "subscription_end_date": "2030-01-01T00:00:00",
            "onboarding_completed": True
        }}
    )
    
    if result.matched_count > 0:
        print(f"Updated {result.matched_count} user record(s) for {email} to ACTIVE.")
    else:
        print(f"No user found with email {email}. Please ensure you have logged in via Firebase at least once.")

if __name__ == "__main__":
    email = "shubhamtest@gmail.com"
    asyncio.run(force_activate_test_user(email))
