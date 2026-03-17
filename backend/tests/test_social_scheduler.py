"""
Backend API Tests for Social Media Scheduler
Tests: Auth, Posts, Social Accounts endpoints
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://postflow-25.preview.emergentagent.com')

# Test credentials
TEST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzJmNzQxNGFhYjUyMyIsImVtYWlsIjoidGVzdGRlbW9AZXhhbXBsZS5jb20iLCJleHAiOjE3NzMzNTc1MDZ9.fCNICZfzfWZLmCx7ysFJ_PF1saIj9dBr4cj08WWWLc8"

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture
def authenticated_client(api_client):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {TEST_TOKEN}"})
    return api_client


class TestAuthEndpoints:
    """Authentication endpoint tests"""
    
    def test_get_current_user(self, authenticated_client):
        """Test GET /api/auth/me - Get current user"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert data["email"] == "testdemo@example.com"
        print(f"✓ Current user: {data['email']}")
    
    def test_login_invalid_credentials(self, api_client):
        """Test POST /api/auth/login with invalid credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 400
        print("✓ Invalid login returns 400")
    
    def test_unauthorized_access(self, api_client):
        """Test accessing protected endpoint without auth"""
        response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ Unauthorized access returns 401")


class TestPostsEndpoints:
    """Posts CRUD endpoint tests"""
    
    def test_get_posts(self, authenticated_client):
        """Test GET /api/posts - List all posts"""
        response = authenticated_client.get(f"{BASE_URL}/api/posts")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/posts returned {len(data)} posts")
    
    def test_create_post_draft(self, authenticated_client):
        """Test POST /api/posts - Create a draft post"""
        post_data = {
            "content": f"TEST_post_{datetime.now().isoformat()}",
            "post_type": "text",
            "platforms": ["twitter", "facebook"]
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/posts", json=post_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert data["content"] == post_data["content"]
        assert data["status"] == "draft"
        assert data["platforms"] == post_data["platforms"]
        print(f"✓ Created draft post: {data['id']}")
        
        return data["id"]
    
    def test_create_video_post(self, authenticated_client):
        """Test POST /api/posts - Create a video post"""
        post_data = {
            "content": f"TEST_video_post_{datetime.now().isoformat()}",
            "post_type": "video",
            "platforms": ["youtube", "tiktok"],
            "video_title": "Test Video Title"
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/posts", json=post_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["post_type"] == "video"
        assert data["video_title"] == "Test Video Title"
        print(f"✓ Created video post: {data['id']}")
    
    def test_get_posts_by_status(self, authenticated_client):
        """Test GET /api/posts?status=draft - Filter posts by status"""
        response = authenticated_client.get(f"{BASE_URL}/api/posts?status=draft")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        # All returned posts should be drafts
        for post in data:
            assert post["status"] == "draft"
        print(f"✓ GET /api/posts?status=draft returned {len(data)} draft posts")
    
    def test_post_crud_flow(self, authenticated_client):
        """Test full CRUD flow: Create -> Read -> Update -> Delete"""
        # CREATE
        post_data = {
            "content": f"TEST_crud_post_{datetime.now().isoformat()}",
            "post_type": "text",
            "platforms": ["linkedin"]
        }
        
        create_response = authenticated_client.post(f"{BASE_URL}/api/posts", json=post_data)
        assert create_response.status_code == 200
        created_post = create_response.json()
        post_id = created_post["id"]
        print(f"✓ Created post: {post_id}")
        
        # READ
        get_response = authenticated_client.get(f"{BASE_URL}/api/posts/{post_id}")
        assert get_response.status_code == 200
        fetched_post = get_response.json()
        assert fetched_post["id"] == post_id
        assert fetched_post["content"] == post_data["content"]
        print(f"✓ Read post: {post_id}")
        
        # UPDATE
        update_data = {"content": "Updated content for test"}
        update_response = authenticated_client.patch(f"{BASE_URL}/api/posts/{post_id}", json=update_data)
        assert update_response.status_code == 200
        updated_post = update_response.json()
        assert updated_post["content"] == "Updated content for test"
        print(f"✓ Updated post: {post_id}")
        
        # DELETE
        delete_response = authenticated_client.delete(f"{BASE_URL}/api/posts/{post_id}")
        assert delete_response.status_code == 200
        print(f"✓ Deleted post: {post_id}")
        
        # VERIFY DELETION
        verify_response = authenticated_client.get(f"{BASE_URL}/api/posts/{post_id}")
        assert verify_response.status_code == 404
        print(f"✓ Verified post deletion: {post_id}")


class TestSocialAccountsEndpoints:
    """Social Accounts endpoint tests"""
    
    def test_get_social_accounts(self, authenticated_client):
        """Test GET /api/social-accounts - List connected accounts"""
        response = authenticated_client.get(f"{BASE_URL}/api/social-accounts")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/social-accounts returned {len(data)} accounts")
    
    def test_connect_social_account(self, authenticated_client):
        """Test POST /api/social-accounts - Connect a new account (MOCKED)"""
        # Note: This is a mock connection, not real OAuth
        account_data = {
            "platform": "test_platform",
            "platform_username": f"test_user_{datetime.now().timestamp()}"
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/social-accounts", json=account_data)
        
        # Could be 200 (success) or 400 (already connected)
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert data["platform"] == account_data["platform"]
            print(f"✓ Connected account: {data['id']}")
            
            # Cleanup - disconnect the test account
            disconnect_response = authenticated_client.delete(f"{BASE_URL}/api/social-accounts/{data['id']}")
            assert disconnect_response.status_code == 200
            print(f"✓ Disconnected test account: {data['id']}")
        else:
            print("✓ Account already connected (expected behavior)")


class TestStatsEndpoint:
    """Stats endpoint tests"""
    
    def test_get_stats(self, authenticated_client):
        """Test GET /api/stats - Get user statistics"""
        response = authenticated_client.get(f"{BASE_URL}/api/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_posts" in data
        assert "scheduled_posts" in data
        assert "published_posts" in data
        assert "connected_accounts" in data
        
        # Verify data types
        assert isinstance(data["total_posts"], int)
        assert isinstance(data["scheduled_posts"], int)
        print(f"✓ Stats: {data}")


class TestContentPages:
    """Content pages endpoint tests"""
    
    def test_get_terms(self, api_client):
        """Test GET /api/pages/terms - Get terms of service"""
        response = api_client.get(f"{BASE_URL}/api/pages/terms")
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
        print("✓ GET /api/pages/terms works")
    
    def test_get_privacy(self, api_client):
        """Test GET /api/pages/privacy - Get privacy policy"""
        response = api_client.get(f"{BASE_URL}/api/pages/privacy")
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
        print("✓ GET /api/pages/privacy works")


# Cleanup test data after all tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_posts():
    """Cleanup TEST_ prefixed posts after all tests"""
    yield
    
    # Cleanup after tests
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TEST_TOKEN}"
    })
    
    # Get all posts and delete TEST_ prefixed ones
    response = session.get(f"{BASE_URL}/api/posts")
    if response.status_code == 200:
        posts = response.json()
        for post in posts:
            if post.get("content", "").startswith("TEST_"):
                session.delete(f"{BASE_URL}/api/posts/{post['id']}")
                print(f"Cleaned up test post: {post['id']}")
