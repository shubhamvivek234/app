import requests

# Try login
try:
    res = requests.post("http://localhost:8001/api/auth/login", json={"email": "findshubhamkumar@gmail.com", "password": "password123"})
    if res.status_code == 200:
        token = res.json().get("access_token")
        print("Got token.")
        # Hit authorize
        auth_res = requests.get("http://localhost:8001/api/oauth/facebook/authorize", headers={"Authorization": f"Bearer {token}"})
        print("Facebook Authorize STATUS:", auth_res.status_code)
        print("Facebook Authorize BODY:", auth_res.json())
        
        auth_res = requests.get("http://localhost:8001/api/oauth/instagram/authorize", headers={"Authorization": f"Bearer {token}"})
        print("Insta Authorize STATUS:", auth_res.status_code)
        print("Insta Authorize BODY:", auth_res.json())
    else:
        print("Login failed:", res.status_code, res.text)
except Exception as e:
    print("Error:", e)
