
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

async def main():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'social_scheduler')
    
    print(f"Connecting to {mongo_url}, DB: {db_name}")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Reset test user to pre-onboarding, free status
    # This simulates a fresh Google Sign-up context
    result = await db.users.update_one(
        {"email": "test@example.com"},
        {"$set": {
            "onboarding_completed": False, 
            "subscription_status": "free",
            "subscription_plan": None,
            "subscription_end_date": None
        }}
    )
    
    if result.modified_count > 0:
        print("Successfully reset test user 'test@example.com' to pre-onboarding state.")
    else:
        print("User not found or already in desired state.")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
