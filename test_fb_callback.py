"""
Direct test of the Facebook OAuth callback logic.
Simulates exactly what the facebook_callback endpoint does, step by step.
Use this to test if the Facebook token exchange and /me API works correctly.
"""
import asyncio
import httpx
import uuid
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("backend/.env")

APP_ID = os.environ.get("FACEBOOK_APP_ID", "").strip('"')
APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "").strip('"')
REDIRECT_URI = os.environ.get("FACEBOOK_REDIRECT_URI", "").strip('"')
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DB_NAME = os.environ.get("DB_NAME", "social_scheduler")
BASE_URL = "https://graph.facebook.com/v19.0"

print(f"App ID: {APP_ID}")
print(f"App Secret: {APP_SECRET[:6]}...")
print(f"Redirect URI: {REDIRECT_URI}")
print()

async def test_with_code(auth_code: str):
    """Simulate the full facebook_callback with a fresh auth code."""
    async with httpx.AsyncClient() as client:
        # Step 1: Exchange code for token
        print("=== Step 1: Exchange code for short-lived token ===")
        resp = await client.get(f"{BASE_URL}/oauth/access_token", params={
            "client_id": APP_ID,
            "redirect_uri": REDIRECT_URI,
            "client_secret": APP_SECRET,
            "code": auth_code
        })
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:300]}")
        if resp.status_code != 200:
            print("❌ Token exchange FAILED — this is likely the root issue")
            return
        
        token_data = resp.json()
        access_token = token_data.get("access_token")
        print(f"✅ Got short-lived token: {access_token[:20]}...")
        
        # Step 2: Exchange for long-lived token
        print("\n=== Step 2: Get long-lived token ===")
        resp2 = await client.get(f"{BASE_URL}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "fb_exchange_token": access_token
        })
        print(f"Status: {resp2.status_code}")
        print(f"Response: {resp2.text[:300]}")
        long_token = resp2.json().get("access_token", access_token) if resp2.status_code == 200 else access_token
        print(f"✅ Got long-lived token: {long_token[:20]}...")
        
        # Step 3: Get FB profile
        print("\n=== Step 3: Get /me profile ===")
        resp3 = await client.get(f"{BASE_URL}/me", params={
            "fields": "id,name,email,picture",
            "access_token": long_token
        })
        print(f"Status: {resp3.status_code}")
        print(f"Response: {resp3.text[:500]}")
        
        if resp3.status_code == 200:
            profile = resp3.json()
            print(f"\n✅ Profile: {profile.get('name')} (ID: {profile.get('id')})")
            
            # Step 4: Save to DB
            print("\n=== Step 4: Save to MongoDB ===")
            client_db = AsyncIOMotorClient(MONGO_URL)
            db = client_db[DB_NAME]
            
            result = await db.social_accounts.update_one(
                {"user_id": "ZCthsNe1nWTQMygSomMRMtExlQ03", "platform": "facebook", "platform_user_id": profile["id"]},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "user_id": "ZCthsNe1nWTQMygSomMRMtExlQ03",
                    "platform": "facebook",
                    "platform_user_id": profile["id"],
                    "username": profile.get("name", "Facebook User"),
                    "platform_username": profile.get("name", "Facebook User"),
                    "access_token": long_token,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                    "is_active": True
                }},
                upsert=True
            )
            print(f"✅ DB save result: upserted={result.upserted_id is not None}, modified={result.modified_count}")
            print("✅ Facebook account saved! Refresh /accounts page to see it.")
            client_db.close()
        else:
            print("❌ /me profile FAILED")

async def test_without_code():
    """Test if we can get the authorization URL correctly."""
    print("=== Testing Authorization URL Generation ===")
    user_id = "ZCthsNe1nWTQMygSomMRMtExlQ03"
    nonce = str(uuid.uuid4()).replace("-", "")[:16]
    state = f"{user_id}|{nonce}|accounts"
    
    from urllib.parse import quote
    scope = "email,public_profile,pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights,business_management"
    auth_url = (
        f"https://www.facebook.com/v19.0/dialog/oauth"
        f"?client_id={APP_ID}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&state={quote(state, safe='')}"
        f"&scope={scope}"
        f"&response_type=code"
    )
    print(f"\nAuthorization URL:\n{auth_url}")
    print(f"\nState format: {state}")
    print(f"\nClick the URL above to authorize, then copy the 'code' from the redirect URL")
    print(f"and run: python3 test_fb_callback.py <auth_code>")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        asyncio.run(test_with_code(sys.argv[1]))
    else:
        asyncio.run(test_without_code())
