# Social Media Integration Guide

This application requires connections to YouTube and Instagram (via Facebook) APIs to enable video scheduling and uploading.

## 1. YouTube Integration

### Google Cloud Console Setup
1.  Go to [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select the existing one used for Google Login.
3.  **Enable APIs**:
    *   Search for "YouTube Data API v3" and Enable it.
4.  **Credentials**:
    *   Go to "Credentials".
    *   Use the existing OAuth 2.0 Client ID (Web application).
    *   **Authorized Redirect URIs**: Ensure you have added:
        *   `http://localhost:8001/api/oauth/youtube/callback` (for local dev)
        *   `https://your-production-domain.com/api/oauth/youtube/callback`
5.  **Scopes**:
    *   In the OAuth Consent Screen configuration, add the following scope:
    *   `https://www.googleapis.com/auth/youtube.upload` (Manage your YouTube videos)
    *   `https://www.googleapis.com/auth/youtube.readonly` (View your YouTube account)

### Implementation Details
*   **Backend**: `server.py` already includes `/oauth/youtube/authorize` and `/callback`.
*   **Token Storage**: Tokens (Access & Refresh) are stored in MongoDB `social_accounts`.
*   **Quota**: YouTube API has a daily quota (10,000 units). Uploading a video costs ~1600 units.

---

## 2. Instagram Integration (via Facebook Graph API)

Instagram posting is done through the **Instagram Graph API**, which requires a Facebook App.

### Meta for Developers Setup
1.  Go to [Meta for Developers](https://developers.facebook.com/).
2.  **Create App**:
    *   Type: **Business** (or "Other" > "Business").
3.  **Add Products**:
    *   **Instagram Graph API**: Click "Set Up".
    *   **Facebook Login for Business**: Click "Set Up".
4.  **Facebook Login Settings**:
    *   Valid OAuth Redirect URIs:
        *   `http://localhost:8001/api/oauth/facebook/callback`
        *   `https://your-production-domain.com/api/oauth/facebook/callback`
5.  **App Review / Permissions** (For Production):
    *   You will need "Advanced Access" for these permissions to work for public users. For dev users (you), "Standard Access" works.
    *   Required Permissions:
        *   `instagram_basic`
        *   `instagram_content_publish`
        *   `pages_show_list`
        *   `pages_read_engagement`
6.  **User Requirements**:
    *   The Instagram account **MUST** be a **Professional Account** (Business or Creator).
    *   It **MUST** be linked to a **Facebook Page**.

---

## 3. Automation Logic (The Scheduler)

The `server.py` contains a `process_scheduled_posts` function (currently a placeholder/partially implemented).

### How it works:
1.  **Frontend**: User creates a post, selects "YouTube" and "Instagram", uploads a video, sets a time.
    *   Post is saved to MongoDB with `status: "scheduled"`.
2.  **Scheduler**:
    *   A background task runs every minute.
    *   Finds posts where `status: "scheduled"` AND `scheduled_time <= now`.
3.  **Execution**:
    *   Iterates through selected platforms.
    *   **YouTube**:
        *   Uses `google-api-python-client`.
        *   Calls `youtube.videos().insert(part="snippet,status", body={...}, media_body=MediaFileUpload(...))`.
    *   **Instagram**:
        *   **Step 1**: Initialize Upload (`POST /{ig-user-id}/media?media_type=VIDEO&video_url={public_url}`).
        *   **Step 2**: Check Status (`GET /{container-id}`). Wait for `FINISHED`.
        *   **Step 3**: Publish (`POST /{ig-user-id}/media_publish?creation_id={container-id}`).

### Important Restriction for Instagram
*   Instagram API requires the video URL to be **Publicly Accessible** on the internet.
*   For `localhost` development, you must use a tool like **ngrok** to expose your local `/uploads` folder, OR upload the file to a cloud storage (like Firebase Storage or AWS S3) first.
*   **Current Plan**: We will use Firebase Storage (since we just added Firebase) for media uploads. This solves the public URL issue!

## 4. Next Steps for implementation
1.  Implement `Firebase Storage` upload in Frontend (`CreatePostForm.js`).
2.  Update Backend `process_scheduled_posts` to handle Firebase URLs.
3.  Complete the OAuth handlers in `server.py`.

