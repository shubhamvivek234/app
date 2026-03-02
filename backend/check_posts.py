import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def run():
    db = AsyncIOMotorClient(os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/')).social_scheduler
    posts = await db.posts.find().sort("created_at", -1).to_list(10)
    for p in posts:
        print(f"Post {p.get('id')}: {p.get('status')} - Platforms: {p.get('platforms')} - Error: {p.get('error')}")

if __name__ == '__main__':
    asyncio.run(run())
