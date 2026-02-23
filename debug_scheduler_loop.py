import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
# Import directly from server so we run EXACTLY the same logic
from server import process_scheduled_posts, db, client

import logging
logging.basicConfig(level=logging.INFO)

async def trigger_scheduler():
    print("Resetting the last post back to 'scheduled' state to force a retry...")
    post = await db.posts.find_one({"post_type": "video"}, sort=[("created_at", -1)])
    if not post:
        print("No post found.")
        return
        
    print(f"Testing post {post['id']}...")
    await db.posts.update_one({"id": post['id']}, {"$set": {
        "status": "scheduled",
        "scheduled_time": "2000-01-01T00:00:00+00:00",
        "retry_count": 0
    }})
    
    print("Running process_scheduled_posts()...")
    try:
        await process_scheduled_posts()
        print("Done.")
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        client.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join('/Users/shubham/app/backend', '.env'))
    asyncio.run(trigger_scheduler())
