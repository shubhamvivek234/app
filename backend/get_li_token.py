import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')
    client = AsyncIOMotorClient(mongo_uri)
    db = client.social_scheduler
    
    post = await db.posts.find_one({"platforms": "linkedin"}, sort=[("created_at", -1)])
    if not post:
        print("No LinkedIn posts found in DB")
        return
        
    print(f"Post ID: {post.get('id')}")
    print(f"Status: {post.get('status')}")
    print(f"Error: {post.get('error')}")
    print(f"Platforms: {post.get('platforms')}")
    print(f"Target Accounts: {post.get('target_accounts')}")
    
if __name__ == "__main__":
    asyncio.run(main())
