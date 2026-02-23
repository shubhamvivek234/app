"""
Script to manually add an Instagram account to MongoDB using an access token.
Fetches the profile from graph.instagram.com and saves to social_accounts.
"""
import asyncio
import httpx
import uuid
import sys
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("backend/.env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
DB_NAME = os.environ.get("DB_NAME", "social_scheduler")
GRAPH_URL = "https://graph.instagram.com/v19.0"

async def add_instagram_account(access_token: str, user_email: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # 1. Find the user by email
    user = await db.users.find_one({"email": user_email})
    if not user:
        print(f"❌ User not found with email: {user_email}")
        return

    user_id = user["user_id"]
    print(f"✅ Found user: {user.get('email')} (ID: {user_id})")

    # 2. Fetch Instagram profile
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{GRAPH_URL}/me",
            params={
                "fields": "id,name,username,profile_picture_url,followers_count",
                "access_token": access_token,
            }
        )
        print(f"\n📡 API Response ({resp.status_code}): {resp.text[:500]}")

        if resp.status_code != 200:
            print(f"❌ Failed to fetch profile: {resp.text}")
            return

        profile = resp.json()
        username = profile.get("username") or profile.get("name", "tee_theory")
        platform_user_id = profile.get("id")
        picture_url = profile.get("profile_picture_url")

        print(f"\n✅ Instagram profile: @{username} (ID: {platform_user_id})")

    # 3. Save/update in MongoDB
    account = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "platform": "instagram",
        "platform_user_id": platform_user_id,
        "username": username,
        "platform_username": username,
        "access_token": access_token,
        "refresh_token": None,
        "token_expires_at": None,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "picture_url": picture_url,
        "is_active": True
    }

    result = await db.social_accounts.update_one(
        {"user_id": user_id, "platform": "instagram"},
        {"$set": account},
        upsert=True
    )

    if result.upserted_id or result.modified_count:
        print(f"\n🎉 Successfully saved @{username} to database!")
        print(f"   → Refresh http://localhost:9500/accounts to see it appear")
    else:
        print("\n⚠️  No changes made to database")

    client.close()

if __name__ == "__main__":
    TOKEN = "IGAAW0IOIACX1BZAGI2M2VIekhoc3RwZAURoeFh2cm1wa0xES3o4ZA3MwUHVDLWc5YnlldFVHNkQ1V2N6UWlJR3YzTjNScTRWcksxaHRxZA1N0NUNjNEZAaLV8wT200bXh3LVp5WTlJRFJfTmRaSFdJR0NJd3BzSDk5SDZAUYmRKd3ZAwUQZDZD"
    EMAIL = "findshubhamkumar@gmail.com"
    asyncio.run(add_instagram_account(TOKEN, EMAIL))
