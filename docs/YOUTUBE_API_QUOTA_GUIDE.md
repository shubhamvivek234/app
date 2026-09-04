# Official Guide: YouTube Data API v3 Enterprise Quota Extension

## 1. Executive Overview

In the Google Cloud ecosystem, YouTube Data API quotas are allocated **per Developer Project (Client ID)**, not per connected YouTube user channel. 

| Metric | Standard Tier (Default) | Enterprise Tier (Requested) |
| :--- | :---: | :---: |
| **Daily Quota Units** | **10,000 units / day** | **1,000,000+ units / day** |
| **Cost per Video Upload (`videos.insert`)** | 1,600 units | 1,600 units |
| **Cost per Status/Privacy Update** | 50 units | 50 units |
| **Max Video Uploads / Day Across All Users** | **6 uploads / day** | **600+ uploads / day** |
| **Reset Schedule** | Midnight Pacific Time (00:00 PT) | Midnight Pacific Time (00:00 PT) |

Without an approved quota extension, attempting to publish 500 creator videos in a day will immediately fail at video #7 with:
```json
{
  "error": {
    "code": 403,
    "message": "The request cannot be completed because you have exceeded your quota.",
    "errors": [{ "domain": "youtube.quota", "reason": "quotaExceeded" }]
  }
}
```

---

## 2. Pre-Audit Legal & Compliance Checklist

Google's Trust & Safety team verifies each application against strict compliance guidelines before granting quota increases. The following must be live in Unravler:

### A. Terms of Service & Privacy Policy Compliance
1. **Direct YouTube ToS Reference:**
   Your public Terms of Service (at `/terms`) must state:
   > *"Unravler uses YouTube API Services to upload and manage videos on your authorized channels. By connecting your YouTube account, you agree to be bound by the [YouTube Terms of Service](https://www.youtube.com/t/terms)."*
2. **Google Privacy Policy Link:**
   Your Privacy Policy (at `/privacy`) must state:
   > *"We access and store your YouTube channel data in accordance with the [Google Privacy Policy](http://www.google.com/policies/privacy)."*
3. **User Revocation Instructions:**
   Must inform users that they can revoke Unravler's access at any time via:
   > *"You can view and revoke Unravler's access to your Google account at any time via the [Google Security Settings](https://security.google.com/settings/security/permissions)."*

### B. Branding Guidelines
- Any "Connect YouTube" button must use the official YouTube logo, font, and brand colors per [YouTube Branding Guidelines](https://developers.google.com/youtube/terms/branding-guidelines).

### C. Data Retention & Hygiene
- Access tokens must be refreshed every 6 hours (handled automatically in Unravler via Celery worker token tasks).
- User tokens and cached channel details must be permanently purged within 30 days of account disconnection.

---

## 3. Step-by-Step Quota Extension Form Walkthrough

Apply via the official Google form: **[YouTube API Services - Quota Extension Request](https://support.google.com/youtube/contact/yt_api_form)**.

### Step 1: Project & Developer Details
- **Company / Project Name:** Unravler
- **Application URL:** `https://app.unravler.com`
- **Developer Email:** (Your Google Cloud Project owner email)
- **Google Cloud Project Number & Project ID:** Found on your Google Cloud Console dashboard.
- **Client ID:** Found under **APIs & Services > Credentials** (format: `123456789-abc.apps.googleusercontent.com`).

### Step 2: Quota Requested
- **Current Quota:** `10,000`
- **Requested Quota:** `1,000,000` units/day
- **Justification:**
  > *"Unravler is a multi-tenant creator social media scheduling platform. Active creators connect their YouTube channels to schedule and publish long-form and Shorts videos. Because a single video upload consumes 1,600 quota units, our current 10,000 daily limit allows only 6 uploads per day across our entire user base. We are requesting 1,000,000 units/day to accommodate our current pipeline of creators publishing daily content."*

### Step 3: API Methods Used
Check the following checkboxes in the form:
- `videos.insert` (resumable video upload)
- `videos.update` / `videos.list` (updating privacy status from private to public upon scheduled time)
- `thumbnails.set` (setting custom video thumbnails)
- `channels.list` (fetching channel name and avatar during OAuth connection)

### Step 4: Demo Video Recording (Mandatory)
Google will **reject** any application without a clear, unlisted YouTube video showing the live OAuth flow and video publishing.

#### Demo Video Script (3–5 minutes):
1. **Address Bar & Client ID:**
   - Open browser and navigate to `https://app.unravler.com`.
   - Click "Connect YouTube Channel".
   - Zoom into the browser address bar on the Google OAuth consent screen to clearly show the `client_id` parameter matching the project ID in your application.
2. **Consent Screen:**
   - Show the permissions requested: `youtube.upload` and `youtube.readonly`.
   - Complete the authorization.
3. **Scheduling a Video:**
   - Show the Unravler composer: select YouTube, choose a video file, enter title/description, and schedule a post for 5 minutes in the future.
   - Show the post status changing to "Scheduled (Pre-upload complete)".
4. **Publish Verification:**
   - Open `studio.youtube.com` in another tab.
   - Show the video uploaded privately, and then switching to public when the scheduled time arrives.
5. **Revocation Walkthrough:**
   - Go to `https://security.google.com/settings/security/permissions`.
   - Show Unravler listed under "Third-party apps with account access", and demonstrate clicking "Remove access".

---

## 4. In-App Quota Tracking & Resilience (Implemented)

Unravler includes native YouTube quota pacing (`utils/youtube_quota_tracker.py`):
1. **Atomic Pacific-Midnight Tracking:**
   Tracks units consumed each calendar day in Pacific Time (00:00 PST/PDT).
2. **Graceful Pacing:**
   If the daily limit is approached (>= 90%), system administrators are alerted.
3. **Automatic Requeueing:**
   If quota is exhausted, scheduled posts are **not** marked as failed. They are automatically delayed and requeued with `Retry-After: seconds_until_midnight_pt`.
