import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid

async def create_mock_notifications():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["social_scheduler"]
    
    # We grab ANY user
    user = await db.users.find_one({})
    if not user:
        print("No users found in database.")
        return
        
    user_id = user["user_id"]
    
    docs = [
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "post_id": "mock_post_1",
            "type": "error",
            "message": "Post failed after 3 attempts: youtube: Quota Execeded",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "post_id": "mock_post_2",
            "type": "success",
            "message": "Post successfully published to Facebook, Instagram.",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.notifications.insert_many(docs)
    print(f"Inserted mock DB notifications successfully for user {user['email']}.")
    
if __name__ == "__main__":
    asyncio.run(create_mock_notifications())
