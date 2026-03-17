"""
Directly add Facebook account to MongoDB using a Graph API token.
Get your token from: https://developers.facebook.com/tools/explorer/
- Select App: SocialEntangler
- Add permissions: public_profile, email
- Click "Generate Access Token"
"""
import asyncio, httpx, uuid, sys, os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("backend/.env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DB_NAME   = os.environ.get("DB_NAME", "social_scheduler")
BASE_URL  = "https://graph.facebook.com/v19.0"
USER_ID   = "ZCthsNe1nWTQMygSomMRMtExlQ03"

async def add_facebook(token: str):
    async with httpx.AsyncClient() as http:
        print("\n=== Fetching /me profile ===")
        resp = await http.get(f"{BASE_URL}/me", params={
            "fields": "id,name,email,picture.type(large)",
            "access_token": token
        })
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")

        if resp.status_code != 200:
            print("❌ Failed to fetch profile. Token may be invalid.")
            return

        profile = resp.json()
        name      = profile.get("name", "Facebook User")
        fb_id     = profile.get("id")
        picture   = profile.get("picture", {}).get("data", {}).get("url")

        print(f"\n✅ Facebook Profile: {name} (ID: {fb_id})")

        # Save to MongoDB
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]

        account = {
            "id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "platform": "facebook",
            "platform_user_id": fb_id,
            "username": name,
            "platform_username": name,
            "access_token": token,
            "refresh_token": None,
            "token_expires_at": None,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "picture_url": picture,
            "is_active": True,
            "account_type": "personal"
        }

        result = await db.social_accounts.update_one(
            {"user_id": USER_ID, "platform": "facebook"},
            {"$set": account},
            upsert=True
        )
        client.close()

        if result.upserted_id or result.modified_count:
            print(f"\n🎉 Facebook account '{name}' saved to database!")
            print("   → Refresh http://localhost:9500/accounts to see it")
        else:
            print("\n⚠️  No changes made (already exists?)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 add_facebook.py <access_token>")
        print()
        print("Get token from:")
        print("  1. Go to https://developers.facebook.com/tools/explorer/")
        print("  2. Select App: SocialEntangler (683141334860463)")
        print("  3. Click 'Generate Access Token'")
        print("  4. Copy the token and run this script")
    else:
        asyncio.run(add_facebook(sys.argv[1]))
