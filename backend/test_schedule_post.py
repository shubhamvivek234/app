import urllib.request
import urllib.error
import json
import os
import sys

# Add backend directory to path so we can import server module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient
import jwt

# Get DB config
db_name = os.environ.get('DB_NAME', 'postflow')
client = MongoClient("mongodb://localhost:27017")
db = client[db_name]

# Find a user
user = db.users.find_one()
if not user:
    print("No user found in DB")
    exit(1)

# Generate a JWT token directly
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

payload_jwt = {"sub": user["user_id"], "email": user["email"]}
token = jwt.encode(payload_jwt, JWT_SECRET, algorithm=JWT_ALGORITHM)

print(f"Testing with user: {user.get('email')} (ID: {user.get('user_id')})")

payload = {
    "content": "Test Background Worker",
    "post_type": "video",
    "platforms": ["twitter", "youtube"],
    "accounts": [],
    "media_urls": ["/uploads/dummy.mp4"],
    "cover_image": "/uploads/dummy.jpg",
    "scheduled_time": "2026-03-01T12:00:00Z"
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request("http://localhost:8001/api/posts", data=data)
req.add_header('Authorization', f'Bearer {token}')
req.add_header('Content-Type', 'application/json')

try:
    print("Sending POST request to /api/posts...")
    response = urllib.request.urlopen(req)
    print("Status:", response.status)
    print("Response:", response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
    print("Body:", e.read().decode())
except Exception as e:
    print("Error:", e)
