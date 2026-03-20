import requests
import sys
import json
from datetime import datetime, timedelta
import time

class SocialSchedulerAPITester:
    def __init__(self, base_url="https://social-queue-3.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.user_data = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_user_email = "tester@example.com"
        self.test_user_password = "testpass123"
        self.test_user_name = "Test User"

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")

    def make_request(self, method, endpoint, data=None, authenticated=True):
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if authenticated and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None

    def test_auth_signup(self):
        """Test user signup"""
        print("\n🔍 Testing User Signup...")
        
        # Use timestamped email to avoid conflicts
        timestamp = int(time.time())
        signup_email = f"test_{timestamp}@example.com"
        
        response = self.make_request('POST', 'auth/signup', {
            "email": signup_email,
            "password": self.test_user_password,
            "name": self.test_user_name
        }, authenticated=False)
        
        if response and response.status_code == 200:
            data = response.json()
            if 'access_token' in data and 'user' in data:
                # Store token and user data for subsequent tests
                self.token = data['access_token']
                self.user_data = data['user']
                self.test_user_email = signup_email  # Update for other tests
                self.log_test("User Signup", True, f"- Created user: {signup_email}")
                return True
        
        self.log_test("User Signup", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_auth_login(self):
        """Test user login"""
        print("\n🔍 Testing User Login...")
        
        response = self.make_request('POST', 'auth/login', {
            "email": self.test_user_email,
            "password": self.test_user_password
        }, authenticated=False)
        
        if response and response.status_code == 200:
            data = response.json()
            if 'access_token' in data and 'user' in data:
                self.token = data['access_token']
                self.user_data = data['user']
                self.log_test("User Login", True, f"- User: {data['user']['email']}")
                return True
        
        self.log_test("User Login", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_auth_me(self):
        """Test get current user"""
        print("\n🔍 Testing Get Current User...")
        
        response = self.make_request('GET', 'auth/me')
        
        if response and response.status_code == 200:
            data = response.json()
            if 'email' in data and data['email'] == self.test_user_email:
                self.log_test("Get Current User", True, f"- User: {data['email']}")
                return True
        
        self.log_test("Get Current User", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_create_post(self):
        """Test creating a post"""
        print("\n🔍 Testing Create Post...")
        
        post_data = {
            "content": "Test post content for social media scheduling",
            "platforms": ["twitter", "linkedin"],
            "scheduled_time": None
        }
        
        response = self.make_request('POST', 'posts', post_data)
        
        if response and response.status_code == 200:
            data = response.json()
            if 'id' in data and 'content' in data:
                self.created_post_id = data['id']
                self.log_test("Create Post", True, f"- Post ID: {data['id']}")
                return True
        
        self.log_test("Create Post", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_get_posts(self):
        """Test getting user posts"""
        print("\n🔍 Testing Get Posts...")
        
        response = self.make_request('GET', 'posts')
        
        if response and response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                self.log_test("Get Posts", True, f"- Found {len(data)} posts")
                return True
        
        self.log_test("Get Posts", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_ai_content_generation(self):
        """Test AI content generation"""
        print("\n🔍 Testing AI Content Generation...")
        
        response = self.make_request('POST', 'ai/generate-content', {
            "prompt": "Write a short post about productivity tips",
            "platform": "twitter"
        })
        
        if response and response.status_code == 200:
            data = response.json()
            if 'content' in data and len(data['content']) > 0:
                self.log_test("AI Content Generation", True, f"- Generated {len(data['content'])} characters")
                return True
        
        self.log_test("AI Content Generation", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_social_accounts(self):
        """Test social account connections"""
        print("\n🔍 Testing Social Account Connection...")
        
        # Test connecting an account
        response = self.make_request('POST', 'social-accounts', {
            "platform": "twitter",
            "platform_username": "test_twitter_user"
        })
        
        if response and response.status_code == 200:
            data = response.json()
            if 'id' in data and 'platform' in data:
                self.connected_account_id = data['id']
                self.log_test("Connect Social Account", True, f"- Platform: {data['platform']}")
                
                # Test getting connected accounts
                response = self.make_request('GET', 'social-accounts')
                if response and response.status_code == 200:
                    accounts = response.json()
                    if isinstance(accounts, list) and len(accounts) > 0:
                        self.log_test("Get Social Accounts", True, f"- Found {len(accounts)} accounts")
                        return True
        
        self.log_test("Social Account Connection", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_stats(self):
        """Test dashboard stats"""
        print("\n🔍 Testing Dashboard Stats...")
        
        response = self.make_request('GET', 'stats')
        
        if response and response.status_code == 200:
            data = response.json()
            expected_keys = ['total_posts', 'scheduled_posts', 'published_posts', 'connected_accounts']
            if all(key in data for key in expected_keys):
                self.log_test("Dashboard Stats", True, f"- Posts: {data['total_posts']}, Connected: {data['connected_accounts']}")
                return True
        
        self.log_test("Dashboard Stats", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def test_stripe_checkout(self):
        """Test Stripe checkout session creation"""
        print("\n🔍 Testing Stripe Checkout...")
        
        response = self.make_request('POST', 'payments/checkout', {
            "plan": "monthly",
            "payment_method": "stripe"
        })
        
        if response and response.status_code == 200:
            data = response.json()
            if 'url' in data and 'session_id' in data:
                self.stripe_session_id = data['session_id']
                self.log_test("Stripe Checkout", True, f"- Session created: {data['session_id']}")
                return True
        
        self.log_test("Stripe Checkout", False, f"- Status: {response.status_code if response else 'No response'}")
        return False

    def run_all_tests(self):
        """Run comprehensive API tests"""
        print("🚀 Starting Social Scheduler API Tests\n")
        print(f"Testing against: {self.base_url}")
        
        # Authentication tests
        if not self.test_auth_signup():
            print("\n❌ Signup failed - cannot continue with authenticated tests")
            return False
            
        self.test_auth_login()
        self.test_auth_me()
        
        # Core functionality tests
        self.test_create_post()
        self.test_get_posts()
        self.test_ai_content_generation()
        self.test_social_accounts()
        self.test_stats()
        
        # Payment tests
        self.test_stripe_checkout()
        
        # Summary
        print(f"\n📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = SocialSchedulerAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())