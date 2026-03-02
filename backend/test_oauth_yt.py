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

import uuid
token = create_access_token({"sub": str(uuid.uuid4()), "email": "test@test.com"})

print("\nTesting YouTube...")
res = requests.get("http://localhost:8001/api/oauth/youtube/authorize", headers={"Authorization": f"Bearer {token}"})
print("STATUS:", res.status_code)
print("BODY:", res.json())

print("\nTesting LinkedIn...")
res = requests.get("http://localhost:8001/api/oauth/linkedin/authorize", headers={"Authorization": f"Bearer {token}"})
print("STATUS:", res.status_code)
print("BODY:", res.json())
