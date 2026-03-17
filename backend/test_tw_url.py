import httpx
import logging

async def test_twitter_auth():
    async with httpx.AsyncClient() as client:
        # We need a token to call /api/oauth/twitter/authorize
        # But we can just see if it fails with 401 or works
        # Actually I can just call the helper class directly
        import os
        from dotenv import load_dotenv
        from pathlib import Path
        
        ROOT_DIR = Path(__file__).parent.resolve()
        env_path = ROOT_DIR / '.env'
        load_dotenv(env_path, override=True)
        
        from app.social.twitter import TwitterAuth
        tw = TwitterAuth()
        verifier, challenge = tw.generate_pkce()
        url = tw.get_auth_url("test_state", challenge)
        print(f"GENERATED URL: {url}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_twitter_auth())
