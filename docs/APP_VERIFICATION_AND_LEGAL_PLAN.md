# Unravler — Master App Verification, Legal & Privacy Plan

This document contains the complete technical, legal, and operational blueprint required for production app review and verification across **Meta (Facebook & Instagram)**, **Google (YouTube)**, **LinkedIn**, **TikTok**, and **Payment Gateways (Razorpay & Stripe)**.

---

## 1. Information Checklist to Collect from Founder

Before executing the changes in this plan, collect the following details:
1. **Legal Business Entity Name**: (e.g., Sole Proprietorship name registered on Udyam / MSME).
2. **Business Operating Address**: (Street, City, State, PIN Code, India).
3. **Official Support Email**: (`support@unravler.com` or `contact@unravler.com`).
4. **Governing Law Jurisdiction**: (e.g., Courts in New Delhi / Bengaluru, India).
5. **Grievance Redressal Officer**: Name & Email (Mandatory under India IT Rules & DPDP Act 2023).
6. **Refund & Cancellation Policy Terms**: (e.g., 24–48 hours standard refund window).

---

## 2. Technical Implementation Roadmap

### Phase 1: Legal & Merchant Policy Pages (Frontend)
- **`/privacy` (`frontend/src/pages/Privacy.js`)**:
  - Exact Google API Services Limited Use compliance disclosure.
  - Direct link to Google Security Permissions revocation.
  - Explicit Meta Graph API permissions enumeration (`instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_manage_posts`).
  - Strict affirmation: *"We do not sell, rent, or trade social media data to data brokers or third parties."*
  - LinkedIn, TikTok, and X OAuth 2.0 token encryption and data retention disclosures.
  - India DPDP Act (2023) compliance with Grievance Officer details and response windows.
- **`/terms` (`frontend/src/pages/Terms.js`)**:
  - Update governing law from Canada to **India**.
  - Compliance clause with third-party platform rules (YouTube ToS, Meta Community Standards).
  - Transparent subscription, auto-renewal, and cancellation terms.
- **`/refund` (`frontend/src/pages/RefundPolicy.js`)**:
  - Standalone Refund & Cancellation page (mandatory for Razorpay & Stripe merchant approvals).
- **`/contact` (`frontend/src/pages/Contact.js`)**:
  - Contact Us page with operating address in India, support email, operating hours, and Grievance Officer details.

### Phase 2: Automated Data Deletion & Meta Webhooks (Backend & Frontend)
- **`/data-deletion` (`frontend/src/pages/DataDeletion.js`)**:
  - Public instructions for in-app account deletion and revoking permissions directly from Facebook, Google, and LinkedIn settings.
  - Real-time Deletion Status Check tool using confirmation codes.
- **Meta Automated Data Deletion Webhook (`api/routes/webhooks.py`)**:
  - Add `POST /api/webhooks/facebook/data-deletion` & `POST /api/webhooks/facebook/deauthorize`.
  - Parse Meta `signed_request`, trigger erasure job, and return JSON `{ "url": "https://www.unravler.com/data-deletion?code=...", "confirmation_code": "..." }`.
- **Status Lookup API (`api/routes/user.py`)**:
  - Add `GET /api/user/data-deletion-status/{code}` endpoint.

### Phase 3: In-App User Privacy & Controls (Frontend)
- **Account Deletion Modal (`frontend/src/pages/Settings.js`)**:
  - Add double-confirmation modal requiring typing `DELETE` or re-authenticating before irreversible data wipe.
- **Cookie Consent Banner (`frontend/src/components/CookieConsentBanner.js`)**:
  - Lightweight, non-intrusive cookie consent banner for GDPR/DPDP/CCPA compliance.

---

## 3. External Setup & Developer Portals Checklist (Manual / DNS)

1. **Domain Proof**: Verify `unravler.com` in Google Search Console via DNS TXT record.
2. **Email Deliverability**: Add Resend SPF, DKIM, and DMARC DNS records to ensure reviewer test emails never land in spam.
3. **Developer Console Consistency**:
   - Meta App Name: `Unravler` (Category: Business/Social, 512x512 App Icon).
   - Google Cloud OAuth Consent: App Name `Unravler`, Support Email `support@unravler.com`.
   - LinkedIn: Link verified Unravler LinkedIn Company Page.
4. **Payment Gateways**:
   - Razorpay: Submit Udyam Certificate, Bank Current Account, and ensure `/terms`, `/privacy`, `/refund`, and `/contact` are live in footer.
   - Stripe India: Complete export / SaaS billing profile with IEC & PAN.
