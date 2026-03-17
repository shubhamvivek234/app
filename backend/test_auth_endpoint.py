import requests
import json

# Login first
res = requests.post("http://localhost:8001/api/auth/login", json={"email": "shubhamtest@gmail.com", "password": "password123"})
if res.status_code == 200:
    token = res.json().get("access_token")
    # Hit authorize
    auth_res = requests.get("http://localhost:8001/api/oauth/facebook/authorize", headers={"Authorization": f"Bearer {token}"})
    print("STATUS:", auth_res.status_code)
    print("BODY:", auth_res.json())
else:
    print("Login failed:", res.status_code, res.text)
