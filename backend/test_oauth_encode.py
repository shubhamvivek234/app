import sys
import os
import urllib.parse

# Set environment variables for testing
os.environ['FACEBOOK_APP_ID'] = '683141334860463'
os.environ['FACEBOOK_APP_SECRET'] = '5820178c9505c4cc3e8665897bb60ea8'
os.environ['FACEBOOK_REDIRECT_URI'] = 'http://localhost:8001/api/oauth/facebook/callback'
os.environ['INSTAGRAM_APP_ID'] = '1605428207159677'
os.environ['INSTAGRAM_APP_SECRET'] = '12846cfbcc8697cdb885b23e5f3d37ac'
os.environ['INSTAGRAM_REDIRECT_URI'] = 'http://localhost:8001/api/oauth/instagram/callback'

params = {
    'client_id': os.environ['FACEBOOK_APP_ID'],
    'redirect_uri': os.environ['FACEBOOK_REDIRECT_URI'],
    'state': 'test_state_123',
    'scope': 'email,public_profile,pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights,business_management',
    'response_type': 'code'
}

print("Properly encoded Facebook URL:")
print("https://www.facebook.com/v19.0/dialog/oauth?" + urllib.parse.urlencode(params))
