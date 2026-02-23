import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from app.social.google import GoogleAuth

async def debug_upload():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["social_scheduler"]
    
    account = await db.social_accounts.find_one({"platform": "youtube"})
    
    google_auth = GoogleAuth()
    
    # Let's test with the real file
    test_file_path = "/Users/shubham/app/backend/uploads/d0ebc922-27a0-4b17-81c5-d004daa9ae58.mp4"
        
    print(f"Uploading file {test_file_path} of size {os.path.getsize(test_file_path)}")
    try:
        new_token_data = await google_auth.refresh_access_token(account['refresh_token'])
        new_token = new_token_data['access_token']
        
        video_id = await google_auth.upload_video(
            access_token=new_token,
            file_path=test_file_path,
            title="Real File API Test",
            description="Testing YouTube API with the real mp4",
            privacy_status="private"
        )
        print(f"SUCCESS after refresh! Video ID: {video_id}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"UPLOAD FAILED: {repr(e)}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join('/Users/shubham/app/backend', '.env'))
    asyncio.run(debug_upload())
