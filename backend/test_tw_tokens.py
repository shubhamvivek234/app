import httpx
import os
import time
import hmac
import hashlib
import base64
import urllib.parse
import secrets
from dotenv import load_dotenv

async def test_tokens():
    load_dotenv(override=True)
    
    # User's provided tokens
    consumer_key = os.environ.get('TWITTER_CLIENT_ID')
    consumer_secret = os.environ.get('TWITTER_CLIENT_SECRET')
    access_token = "1354172730-3hIzwsvWQ69wmkiLpPYbL0tMzXH7t55JddQkbBO"
    access_token_secret = "0DQdjRn78tBqEgIyImAthcJJvefSFsna739Q5edBMy3rP"
    
    url = "https://api.twitter.com/1.1/account/verify_credentials.json"
    method = "GET"
    
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    
    # Generate signature
    base_params = "&".join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" for k, v in sorted(params.items())])
    base_string = f"{method}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(base_params, safe='')}"
    signing_key = f"{urllib.parse.quote(consumer_secret, safe='')}&{urllib.parse.quote(access_token_secret, safe='')}"
    
    signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = signature
    
    auth_header = "OAuth " + ", ".join([f'{urllib.parse.quote(k)}="{urllib.parse.quote(v)}"' for k, v in sorted(params.items())])
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers={"Authorization": auth_header})
        print(f"STATUS: {response.status_code}")
        print(f"RESPONSE: {response.text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_tokens())
