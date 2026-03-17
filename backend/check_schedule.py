import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import datetime

load_dotenv()

async def run():
    db = AsyncIOMotorClient(os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')).social_scheduler
    post = await db.posts.find_one({'platforms': 'instagram'}, sort=[('created_at', -1)])
    
    if post:
        print(f"Scheduled Time: {post.get('scheduled_time')}")
        print(f"Status: {post.get('status')}")
        print(f"Retry Count: {post.get('retry_count')}")
        print(f"Current UTC Time: {datetime.datetime.now(datetime.timezone.utc)}")
    else:
        print("No IG Post Found")

if __name__ == '__main__':
    asyncio.run(run())
