import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def run():
    db = AsyncIOMotorClient(os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')).social_scheduler
    post = await db.posts.find_one({'platforms': 'instagram'}, sort=[('created_at', -1)])
    
    if post:
        print(f"Media URLs: {post.get('media_urls')}")
    else:
        print("No IG Post Found")

if __name__ == '__main__':
    asyncio.run(run())
