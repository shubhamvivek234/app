from app.social.twitter import TwitterAuth
import os
from dotenv import load_dotenv

load_dotenv()

def test_twitter():
    tw = TwitterAuth()
    print(f"Client ID: {tw.client_id}")
    print(f"Redirect URI: {tw.redirect_uri}")
    
    verifier, challenge = tw.generate_pkce()
    url = tw.get_auth_url("test_state", challenge)
    print(f"Auth URL: {url}")

if __name__ == "__main__":
    test_twitter()
