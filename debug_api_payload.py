import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
import httpx

async def test_api():
    # Get a real token from DB for a user
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["social_scheduler"]
    user_doc = await db.users.find_one({})
    
    # Normally we need a JWT, let's just bypass or get it
    # We can use the mock test endpoints if any, or just get the current token
    # Wait, the API requires a Bearer token. 
    # Let me just query the db.posts collection one more time. Wait, if it's the frontend...
    # Let's read the latest post exactly as it was saved.
    
    latest_post = await db.posts.find_one(sort=[("created_at", -1)])
    print(f"LATEST POST RAW DB: {latest_post}")

if __name__ == "__main__":
    asyncio.run(test_api())
