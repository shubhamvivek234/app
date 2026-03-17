from fastapi.testclient import TestClient
from server import app, get_current_user, User
import os

def mock_get_current_user():
    return User(
        user_id="mock_user_123",
        email="mock@example.com",
        name="Mock User"
    )

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app)

print("Testing Facebook...")
res = client.get("/api/oauth/facebook/authorize")
print("STATUS:", res.status_code)
print("BODY:", res.json())

print("\nTesting Instagram...")
res = client.get("/api/oauth/instagram/authorize")
print("STATUS:", res.status_code)
print("BODY:", res.json())

print("\nTesting Twitter...")
res = client.get("/api/oauth/twitter/authorize")
print("STATUS:", res.status_code)
print("BODY:", res.json())

print("\nTesting LinkedIn...")
res = client.get("/api/oauth/linkedin/authorize")
print("STATUS:", res.status_code)
print("BODY:", res.json())
