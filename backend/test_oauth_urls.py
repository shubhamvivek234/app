import requests
import jwt
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv

load_dotenv(".env")
JWT_SECRET = os.environ.get('JWT_SECRET', 'supersecretkey')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=720)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# Generate token directly
token = create_access_token({"sub": "ZCthsNe1nWTQMygSomMRMtExlQ03", "email": "findshubhamkumar@gmail.com"})
print("Generated token.")

# Hit authorize
auth_res = requests.get("http://localhost:8001/api/oauth/facebook/authorize", headers={"Authorization": f"Bearer {token}"})
print("Facebook Authorize STATUS:", auth_res.status_code)
print("Facebook Authorize BODY:", auth_res.json())

auth_res = requests.get("http://localhost:8001/api/oauth/instagram/authorize", headers={"Authorization": f"Bearer {token}"})
print("Insta Authorize STATUS:", auth_res.status_code)
print("Insta Authorize BODY:", auth_res.json())

auth_res = requests.get("http://localhost:8001/api/oauth/twitter/authorize", headers={"Authorization": f"Bearer {token}"})
print("Twitter Authorize STATUS:", auth_res.status_code)
print("Twitter Authorize BODY:", auth_res.json())
