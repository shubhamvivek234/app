"""
Facebook API Diagnostic Script
Paste a user access token (from Meta Graph API Explorer) to test the API calls
that our backend makes during the OAuth callback.
"""
import asyncio
import httpx
import os
import sys
from dotenv import load_dotenv

load_dotenv("backend/.env")

APP_ID = os.environ.get("FACEBOOK_APP_ID")
APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET")
BASE_URL = "https://graph.facebook.com/v19.0"

async def test_token(user_access_token: str):
    async with httpx.AsyncClient() as client:
        print("\n=== 1. Testing /me ===")
        r = await client.get(f"{BASE_URL}/me", params={
            "fields": "id,name,email",
            "access_token": user_access_token
        })
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")
        
        print("\n=== 2. Getting long-lived token ===")
        r = await client.get(f"{BASE_URL}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "fb_exchange_token": user_access_token
        })
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Response: {r.text[:200]}")
        long_lived = data.get("access_token", user_access_token)
        
        print("\n=== 3. Testing /me/accounts (Facebook Pages) ===")
        r = await client.get(f"{BASE_URL}/me/accounts", params={
            "fields": "id,name,access_token,instagram_business_account{id,username,profile_picture_url}",
            "access_token": long_lived
        })
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")
        data = r.json()
        pages = data.get("data", [])
        print(f"\nFound {len(pages)} Facebook Page(s):")
        for p in pages:
            print(f"  - Page: {p.get('name')} (ID: {p.get('id')})")
            ig = p.get("instagram_business_account")
            if ig:
                print(f"    ✅ Linked Instagram: @{ig.get('username')} (ID: {ig.get('id')})")
            else:
                print(f"    ❌ No Instagram Business Account linked")
        
        if not pages:
            print("\n⚠️  No Facebook Pages found!")
            print("   This means either:")
            print("   1. This Facebook account has no Pages")
            print("   2. The Instagram account is NOT linked to a Facebook Page")
            print("")
            print("To fix: The Instagram account (tee_theory) must be:")
            print("  a) A Business or Creator account (not personal)")
            print("  b) Linked to a Facebook Page in Instagram Settings → Account → Linked Accounts")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_fb_api.py <user_access_token>")
        print("")
        print("Get a token from: https://developers.facebook.com/tools/explorer/")
        print("  1. Select app: SocialEntangler")
        print("  2. Add permissions: pages_show_list, instagram_basic")
        print("  3. Click 'Generate Access Token'")
        print("  4. Copy the token and paste it here")
        sys.exit(1)
    
    asyncio.run(test_token(sys.argv[1]))
