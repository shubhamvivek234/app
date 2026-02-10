# Frontend Integration Guide

This guide shows how to add the enhanced backend features to your frontend UI.

## Table of Contents
1. [Google OAuth Integration](#google-oauth-integration)
2. [Email Verification](#email-verification)
3. [PayPal Payment Integration](#paypal-payment-integration)
4. [Video/Image Upload UI](#videoimage-upload-ui)
5. [Terms & Privacy Pages](#terms--privacy-pages)

---

## Google OAuth Integration

### 1. Update Login Page

Add Google sign-in button to `src/pages/Login.js`:

```javascript
import { FaGoogle } from 'react-icons/fa';

const Login = () => {
  // ... existing code ...

  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/auth/callback';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="...">
      {/* Add before email/password form */}
      <Button
        variant="outline"
        className="w-full"
        onClick={handleGoogleLogin}
        data-testid="google-login-button"
      >
        <FaGoogle className="mr-2" />
        Sign in with Google
      </Button>

      {/* Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t border-border" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-white px-2 text-slate-500">Or continue with email</span>
        </div>
      </div>

      {/* Rest of existing form */}
    </div>
  );
};
```

### 2. Update Signup Page

Add same Google button to `src/pages/Signup.js`:

```javascript
const handleGoogleSignup = () => {
  const redirectUrl = window.location.origin + '/auth/callback';
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};
```

### 3. Create Auth Callback Component

Create `src/pages/AuthCallback.js`:

```javascript
import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import Cookies from 'js-cookie';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AuthCallback = () => {
  const navigate = useNavigate();
  const { setUser, setToken } = useAuth();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const processCallback = async () => {
      const sessionId = searchParams.get('session_id');
      
      if (!sessionId) {
        toast.error('Invalid authentication response');
        navigate('/login');
        return;
      }

      try {
        const response = await axios.post(`${BACKEND_URL}/api/auth/google/callback`, {
          session_id: sessionId
        });

        const { session_token, user } = response.data;
        
        // Set cookie (expires in 7 days)
        Cookies.set('session_token', session_token, { expires: 7 });
        
        // Update auth context
        setToken(session_token);
        setUser(user);
        
        toast.success('Welcome!');
        navigate('/dashboard');
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error('Authentication failed');
        navigate('/login');
      }
    };

    processCallback();
  }, [searchParams, navigate, setUser, setToken]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
        <p className="text-slate-600">Completing sign in...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
```

### 4. Update AuthContext

Update `src/context/AuthContext.js` to support cookies:

```javascript
import Cookies from 'js-cookie';

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(
    localStorage.getItem('token') || Cookies.get('session_token')
  );

  const fetchUser = async () => {
    try {
      const sessionToken = Cookies.get('session_token');
      const headers = sessionToken
        ? {} // Cookie sent automatically
        : { Authorization: `Bearer ${token}` };
      
      const response = await axios.get(`${API}/auth/me`, {
        headers,
        withCredentials: true
      });
      setUser(response.data);
    } catch (error) {
      logout();
    }
  };

  const logout = async () => {
    await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    localStorage.removeItem('token');
    Cookies.remove('session_token');
    setToken(null);
    setUser(null);
  };

  // ... rest of code
};
```

### 5. Add Route

Update `src/App.js`:

```javascript
import AuthCallback from '@/pages/AuthCallback';

function App() {
  return (
    <Routes>
      <Route path="/auth/callback" element={<AuthCallback />} />
      {/* ... other routes */}
    </Routes>
  );
}
```

### 6. Install Dependencies

```bash
cd /app/frontend
yarn add js-cookie
```

---

## Email Verification

### 1. Create Verification Page

Create `src/pages/VerifyEmail.js`:

```javascript
import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const VerifyEmail = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('verifying');

  useEffect(() => {
    const verify = async () => {
      const token = searchParams.get('token');
      if (!token) {
        setStatus('error');
        return;
      }

      try {
        await axios.get(`${BACKEND_URL}/api/auth/verify-email?token=${token}`);
        setStatus('success');
        toast.success('Email verified!');
      } catch (error) {
        setStatus('error');
        toast.error('Verification failed');
      }
    };

    verify();
  }, [searchParams]);

  if (status === 'verifying') {
    return <div>Verifying...</div>;
  }

  if (status === 'success') {
    return (
      <div>
        <h2>Email Verified!</h2>
        <Button onClick={() => navigate('/dashboard')}>
          Go to Dashboard
        </Button>
      </div>
    );
  }

  return (
    <div>
      <h2>Verification Failed</h2>
      <Button onClick={() => navigate('/login')}>Back to Login</Button>
    </div>
  );
};
```

### 2. Add Route

```javascript
<Route path="/verify-email" element={<VerifyEmail />} />
```

### 3. Show Verification Notice

In Dashboard or Settings, show if email not verified:

```javascript
{!user?.email_verified && (
  <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
    <p className="text-amber-800">
      Please verify your email. Check your inbox for verification link.
    </p>
  </div>
)}
```

---

## PayPal Payment Integration

### 1. Update Billing Page

Add PayPal button alongside Stripe/Razorpay:

```javascript
// In src/pages/Billing.js

<div className="space-y-2">
  {/* Existing Stripe button */}
  <Button
    className="w-full"
    onClick={() => handleSubscribe('monthly', 'stripe')}
    disabled={loading || user?.subscription_status === 'active'}
  >
    <FaCreditCard className="mr-2" />
    Pay with Stripe
  </Button>

  {/* Existing Razorpay button */}
  <Button
    variant="outline"
    className="w-full"
    onClick={() => handleSubscribe('monthly', 'razorpay')}
    disabled={loading || user?.subscription_status === 'active'}
  >
    Pay with Razorpay
  </Button>

  {/* NEW: PayPal button */}
  <Button
    variant="outline"
    className="w-full"
    onClick={() => handleSubscribe('monthly', 'paypal')}
    disabled={loading || user?.subscription_status === 'active'}
    data-testid="subscribe-monthly-paypal"
  >
    Pay with PayPal
  </Button>
</div>
```

Do the same for yearly plan buttons.

### 2. PayPal Flow

The `handleSubscribe` function already supports PayPal:

```javascript
const handleSubscribe = async (plan, paymentMethod) => {
  setLoading(true);
  try {
    const response = await createCheckout(plan, paymentMethod);
    // Redirects to PayPal, Stripe, or Razorpay
    window.location.href = response.url;
  } catch (error) {
    toast.error(error.response?.data?.detail || 'Checkout failed');
  } finally {
    setLoading(false);
  }
};
```

---

## Video/Image Upload UI

### 1. Install Dependencies

```bash
yarn add react-dropzone
```

### 2. Update CreatePost Component

```javascript
import { useDropzone } from 'react-dropzone';
import axios from 'axios';

const CreatePost = () => {
  const [postType, setPostType] = useState('text'); // text, image, video
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [videoUrl, setVideoUrl] = useState('');
  const [coverImageUrl, setCoverImageUrl] = useState('');
  const [videoTitle, setVideoTitle] = useState('');

  const onDrop = useCallback(async (acceptedFiles) => {
    for (const file of acceptedFiles) {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await axios.post(
          `${BACKEND_URL}/api/upload`,
          formData,
          {
            headers: {
              'Content-Type': 'multipart/form-data',
              Authorization: `Bearer ${token}`,
            },
          }
        );

        setUploadedFiles(prev => [...prev, {
          name: file.name,
          url: response.data.url
        }]);

        if (postType === 'video') {
          setVideoUrl(response.data.url);
        }

        toast.success('File uploaded!');
      } catch (error) {
        toast.error('Upload failed');
      }
    }
  }, [token, postType]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: postType === 'video' 
      ? { 'video/*': ['.mp4', '.mov'] }
      : { 'image/*': ['.png', '.jpg', '.jpeg'] }
  });

  return (
    <div>
      {/* Post Type Selector */}
      <div className="grid grid-cols-3 gap-4">
        <button onClick={() => setPostType('text')}>Text</button>
        <button onClick={() => setPostType('image')}>Image</button>
        <button onClick={() => setPostType('video')}>Video</button>
      </div>

      {/* File Upload (for image/video) */}
      {(postType === 'image' || postType === 'video') && (
        <div
          {...getRootProps()}
          className="border-2 border-dashed p-8 cursor-pointer"
        >
          <input {...getInputProps()} />
          {isDragActive ? (
            <p>Drop files here...</p>
          ) : (
            <p>Drag & drop or click to upload</p>
          )}
        </div>
      )}

      {/* Video Title (for video only) */}
      {postType === 'video' && (
        <Input
          placeholder="Video title"
          value={videoTitle}
          onChange={(e) => setVideoTitle(e.target.value)}
        />
      )}

      {/* Video Cover Image */}
      {postType === 'video' && (
        <Input
          placeholder="Cover image URL"
          value={coverImageUrl}
          onChange={(e) => setCoverImageUrl(e.target.value)}
        />
      )}

      {/* Submit */}
      <Button onClick={handleSubmit}>Create Post</Button>
    </div>
  );
};
```

### 3. Update handleSubmit

```javascript
const handleSubmit = async () => {
  const postData = {
    content,
    post_type: postType,
    platforms,
    scheduled_time: scheduledTime || null,
  };

  if (postType === 'image') {
    postData.media_urls = uploadedFiles.map(f => f.url);
  } else if (postType === 'video') {
    postData.video_url = videoUrl;
    postData.cover_image_url = coverImageUrl;
    postData.video_title = videoTitle;
  }

  await createPost(postData);
};
```

---

## Terms & Privacy Pages

### 1. Create Terms Page

Create `src/pages/Terms.js`:

```javascript
import React from 'react';
import { Link } from 'react-router-dom';

const Terms = () => {
  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b">
        <div className="max-w-4xl mx-auto px-4 py-4 flex justify-between">
          <Link to="/" className="text-2xl font-semibold">SocialSync</Link>
          <Link to="/">Back to Home</Link>
        </div>
      </nav>
      
      <div className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-4xl font-semibold mb-8">Terms of Service</h1>
        
        <div className="prose">
          <h2>1. Acceptance of Terms</h2>
          <p>By using SocialSync, you agree to these terms...</p>
          
          {/* Add full terms content */}
        </div>
      </div>
    </div>
  );
};

export default Terms;
```

### 2. Create Privacy Page

Create `src/pages/Privacy.js` (similar structure to Terms).

### 3. Add Routes

```javascript
<Route path="/terms" element={<Terms />} />
<Route path="/privacy" element={<Privacy />} />
```

### 4. Update Footer

In `src/pages/LandingPage.js`:

```javascript
<footer className="border-t py-12">
  <div className="max-w-7xl mx-auto px-4 text-center">
    <div className="flex justify-center gap-6 mb-4">
      <Link to="/terms" className="hover:text-slate-900">
        Terms of Service
      </Link>
      <Link to="/privacy" className="hover:text-slate-900">
        Privacy Policy
      </Link>
      <a href="mailto:support@socialsync.com">Contact</a>
    </div>
    <p>© 2026 SocialSync. All rights reserved.</p>
  </div>
</footer>
```

---

## Complete Integration Checklist

### Authentication
- [ ] Add Google OAuth button to Login page
- [ ] Add Google OAuth button to Signup page
- [ ] Create AuthCallback component
- [ ] Update AuthContext for cookie support
- [ ] Create VerifyEmail page
- [ ] Add email verification notice in Dashboard

### Payments
- [ ] Add PayPal buttons to Billing page (monthly)
- [ ] Add PayPal buttons to Billing page (yearly)
- [ ] Test payment flow for all 3 gateways

### Post Creation
- [ ] Add post type selector (Text/Image/Video)
- [ ] Implement file upload with react-dropzone
- [ ] Add video title input field
- [ ] Add cover image input for videos
- [ ] Update createPost API call with new fields
- [ ] Display uploaded files list

### Content Pages
- [ ] Create Terms of Service page
- [ ] Create Privacy Policy page
- [ ] Update LandingPage footer with links
- [ ] Add routes for /terms and /privacy

### Testing
- [ ] Test Google OAuth flow end-to-end
- [ ] Test email verification flow
- [ ] Test PayPal payment (sandbox)
- [ ] Test file upload (image and video)
- [ ] Test post creation with all types
- [ ] Verify Terms/Privacy pages load correctly

---

## Environment Setup

### Backend
Add to `/app/backend/.env`:

```bash
# Email Verification (optional but recommended)
RESEND_API_KEY=your_resend_api_key
SENDER_EMAIL=noreply@yourdomain.com

# PayPal (optional, for PayPal payments)
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_SECRET=your_paypal_secret

# Frontend URL (for redirects)
FRONTEND_URL=http://localhost:3000
```

Get API keys:
- Resend: https://resend.com/api-keys
- PayPal Sandbox: https://developer.paypal.com/dashboard/applications/sandbox

---

## Testing Backend Features

### Test Email Verification
```bash
# 1. Sign up a new user
curl -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","name":"Test"}'

# 2. Check logs for verification token
tail -f /var/log/supervisor/backend.err.log

# 3. Verify email with token
curl http://localhost:8001/api/auth/verify-email?token=TOKEN_FROM_LOG
```

### Test File Upload
```bash
TOKEN="your_jwt_token"

curl -X POST http://localhost:8001/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/image.jpg"
```

### Test PayPal Checkout
```bash
TOKEN="your_jwt_token"

curl -X POST http://localhost:8001/api/payments/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan":"monthly","payment_method":"paypal"}'
```

---

## Common Issues & Solutions

### Google OAuth Issues
**Issue:** OAuth callback fails
**Solution:** Do NOT hardcode redirect URL, always use current origin

### File Upload Issues
**Issue:** Files not uploading
**Solution:** 
- Check file size (default limit: 16MB)
- Verify Authorization header is sent
- Check `/app/uploads/` directory exists and is writable

### PayPal Issues
**Issue:** "PayPal not configured" error
**Solution:** Add PAYPAL_CLIENT_ID and PAYPAL_SECRET to backend/.env

### Email Verification Issues
**Issue:** Verification emails not sending
**Solution:**
- Add RESEND_API_KEY to backend/.env
- Verify domain on Resend dashboard for production
- Check backend logs for email sending errors

---

## Production Deployment Tips

### Security
- Use HTTPS for all OAuth redirects
- Store uploaded files in S3/CloudFlare R2, not local filesystem
- Implement file upload size limits
- Scan uploaded files for malware
- Rate limit file uploads (5 per minute recommended)

### Performance
- Use CDN for uploaded files
- Implement image optimization (resize, compress)
- Cache Terms/Privacy pages
- Add loading states for OAuth redirects

### Monitoring
- Track OAuth success/failure rates
- Monitor file upload success rates
- Track payment conversion by gateway
- Alert on failed email deliveries

---

## Next Steps

1. **Implement Social Media OAuth**
   - Twitter/X API setup
   - Instagram Graph API
   - LinkedIn API
   - Store access tokens securely

2. **Enhance File Management**
   - Move to cloud storage (S3/R2)
   - Add image resizing/optimization
   - Implement file type validation
   - Add progress indicators

3. **Advanced Features**
   - Bulk post scheduling (CSV import)
   - Analytics dashboard
   - Team collaboration
   - Post templates
   - Content calendar

For detailed API documentation, see `/app/API_DOCUMENTATION.md`
