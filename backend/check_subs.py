import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def run():
    client = AsyncIOMotorClient(os.getenv('MONGO_URL', 'mongodb://localhost:27017'))
    db = client[os.getenv('DB_NAME', 'social_scheduler')]
    
    print("--- Users Subscriptions ---")
    async for user in db.users.find({}, {"email": 1, "subscription_status": 1, "subscription_plan": 1}):
        print(f"Email: {user.get('email')}, Status: {user.get('subscription_status')}, Plan: {user.get('subscription_plan')}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(run())
