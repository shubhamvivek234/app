import os
from dotenv import load_dotenv

# Force load to get current env
load_dotenv(override=True)

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from social.facebook import FacebookAuth
from social.instagram import InstagramAuth

def test():
    fb = FacebookAuth()
    print("=== FACEBOOK ===")
    print(f"App ID: {fb.app_id}")
    print(f"Redirect URI (Configured): {fb.redirect_uri}")
    print(f"Auth URL: {fb.get_auth_url('test_state')}\n")

    ig = InstagramAuth()
    print("=== INSTAGRAM ===")
    print(f"App ID: {ig.app_id}")
    print(f"Redirect URI (Configured): {ig.redirect_uri}")
    print(f"Auth URL: {ig.get_auth_url('test_state')}")

if __name__ == "__main__":
    test()
