import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add backend directory to path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.social.google import GoogleAuth

import logging
logging.basicConfig(level=logging.INFO)

async def test_upload():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["social_scheduler"]
    
    # Get a user with a connected YouTube account
    account = await db.social_accounts.find_one({"platform": "youtube"})
    if not account:
        print("No YouTube accounts connected.")
        return
        
    token = account["access_token"]
    
    # Create a dummy test file
    test_file_path = os.path.join(os.path.dirname(__file__), "backend", "uploads", "test_video.mp4")
    with open(test_file_path, "wb") as f:
        f.write(b"dummy video content")
        
    google_auth = GoogleAuth()
    
    try:
        print(f"Testing upload with token: {token[:10]}...")
        video_id = await google_auth.upload_video(
            access_token=token,
            file_path=test_file_path,
            title="API Test Video",
            description="Testing YouTube scheduler API",
            privacy_status="private"
        )
        print(f"Success! Video ID: {video_id}")
    except Exception as e:
        print(f"UPLOAD FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_upload())
