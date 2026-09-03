# Unravler — Master App Verification, Legal & Privacy Plan
*(Updated with Government of India Udyam MSME Registration Certificate Details)*

This document contains the complete technical, legal, and operational blueprint required for production app review and verification across **Meta (Facebook & Instagram)**, **Google (YouTube)**, **LinkedIn**, **TikTok**, and **Payment Gateways (Razorpay & Stripe)**.

---

## 1. Verified Entity Information (Official Government Registration)

All legal and policy pages across Unravler must use the following verified details matching the Government of India Udyam Certificate:

| Field | Official Value |
| :--- | :--- |
| **Legal Entity Name** | **UNRAVLER TECHNOLOGIES** |
| **Organization Type** | Sole Proprietorship (Micro Enterprise - Services) |
| **Udyam Registration No.** | **UDYAM-JH-20-0144275** |
| **Date of Registration** | September 03, 2026 |
| **Proprietor / Owner** | **BINDU PRASAD** |
| **Permanent Account Number (PAN)**| `AKOPP5096M` |
| **Registered Business Address** | **Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India** |
| **Official Contact Number** | `+91 9031777441` |
| **Official Email** | `findbinduprasad@zohomail.in` (Support: `support@unravler.com`) |
| **Designated Grievance Officer** | **Bindu Prasad** (`findbinduprasad@zohomail.in`) |
| **Governing Law & Jurisdiction** | **Courts of Ranchi, Jharkhand, India** |
| **Bank Account** | ICICI Bank (A/C: `017501536141`, IFSC: `ICIC0000175`) |
| **NIC Classification Codes** | `62013` (Software support/maintenance), `62020` (IT consultancy), `62099` (IT services n.e.c), `63122` (Media web portals) |

---

## 2. Technical Implementation Roadmap

### Phase 1: Legal & Merchant Policy Pages (Frontend)

1. **`/privacy` (`frontend/src/pages/Privacy.js`)**:
   - **Entity Identity**: Declare that `unravler.com` is owned and operated by **Unravler Technologies**, Ranchi, Jharkhand, India.
   - **Google API Services Disclosure**: Include exact verbatim clause complying with the *Google API Services User Data Policy*, including Limited Use requirements.
   - **Google Revocation Link**: Link directly to [Google Security Account Permissions](https://myaccount.google.com/permissions).
   - **Meta Graph API Permissions**: Explicitly list requested permissions (`instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_manage_posts`) with justifications.
   - **No-Sale of Data Affirmation**: Strict affirmation: *"We do not sell, rent, trade, or monetize user social media data to data brokers or third parties."*
   - **Encryption & Security**: Detail AES-256 GCM encryption of OAuth tokens at rest and TLS 1.3 in transit.
   - **India DPDP Act (2023) Compliance**: Explicit data principal rights (Access, Rectification, Erasure) and designated Grievance Officer details (**Bindu Prasad**, `findbinduprasad@zohomail.in`, Ranchi, Jharkhand).

2. **`/terms` (`frontend/src/pages/Terms.js`)**:
   - **Entity & Jurisdiction**: Update company name from legacy placeholders to **Unravler Technologies**; change governing law and exclusive jurisdiction to the **Courts of Ranchi, Jharkhand, India**.
   - **Platform Terms Compliance**: Mandatory clauses obligating users to comply with YouTube Terms of Service, Meta Community Standards, X Developer Terms, and LinkedIn User Agreement.
   - **Subscription & Billing**: Clear auto-renewal, tax (GST where applicable), and account cancellation procedures.

3. **`/refund` (`frontend/src/pages/RefundPolicy.js`) [NEW]**:
   - Standalone Refund & Cancellation page (mandatory for Razorpay & Stripe India merchant activations).
   - **Policy**: 7-day money-back guarantee for first-time subscribers; refunds processed back to original source payment method (ICICI Bank / Card / UPI) within 5–7 business days.
   - Instructions on how users can initiate cancellation directly from their Billing settings or via email to `support@unravler.com`.

4. **`/contact` (`frontend/src/pages/Contact.js`) [NEW]**:
   - Standalone Contact Us page required for merchant validation.
   - Displays official enterprise address: `Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand - 834002, India`.
   - Contact phone: `+91 9031777441`, Email: `support@unravler.com` / `findbinduprasad@zohomail.in`.
   - Operating hours and support ticket response SLA (< 24 hours).
   - Grievance Redressal Officer box.

5. **Footer Navigation Updates (`frontend/src/components/Footer.js`)**:
   - Add links to `/refund` and `/contact`.
   - Update copyright text: `Copyright © 2026 Unravler Technologies. All rights reserved.`

---

### Phase 2: Automated Data Deletion & Meta Webhooks (Backend & Frontend)

1. **`/data-deletion` (`frontend/src/pages/DataDeletion.js`)**:
   - Detailed step-by-step instructions on how users can disconnect Unravler directly within Facebook / Instagram / Google / LinkedIn settings.
   - Deletion Status Verification Tool: Input confirmation code to check real-time MongoDB purge status.
2. **Meta Automated Deletion Webhook (`api/routes/webhooks.py`)**:
   - Endpoint: `POST /api/webhooks/facebook/data-deletion`
   - Parses Meta's `signed_request`, schedules immediate hard deletion of user's Facebook/Instagram access tokens and cached media, and returns the signed confirmation response:
     ```json
     {
       "url": "https://www.unravler.com/data-deletion?code=CONFIRMATION_CODE",
       "confirmation_code": "CONFIRMATION_CODE"
     }
     ```
3. **Data Deletion Status API (`api/routes/user.py`)**:
   - Endpoint: `GET /api/user/data-deletion-status/{code}` returning status: `processing` or `deleted`.

---

### Phase 3: In-App User Controls & Verification Readiness

1. **Account Deletion Modal in Settings (`frontend/src/pages/Settings.js`)**:
   - Double-confirmation modal requiring the user to type `DELETE` to irreversibly purge their account, workspaces, scheduled posts, and connected accounts.
2. **Cookie Consent Banner (`frontend/src/components/CookieConsent.js`)**:
   - Verify and ensure non-intrusive compliance for tracking and analytics cookies.

---

## 3. Merchant & Developer Portals Checklist

1. **Razorpay & Stripe India Merchant Activation**:
   - Submit Udyam Certificate `UDYAM-JH-20-0144275`.
   - Linked Bank: ICICI Bank, Account `017501536141`, IFSC `ICIC0000175`.
   - Verify that `/terms`, `/privacy`, `/refund`, and `/contact` links are active in `unravler.com` footer.
2. **Meta Developer App Review**:
   - Business Manager Legal Name: `UNRAVLER TECHNOLOGIES`.
   - Privacy Policy URL: `https://www.unravler.com/privacy`.
   - Data Deletion URL: `https://www.unravler.com/data-deletion`.
   - App Category: Business / Social Media Management.
3. **Google Cloud OAuth Consent Screen Verification**:
   - App Name: `Unravler`.
   - User Support Email: `findbinduprasad@zohomail.in` or `support@unravler.com`.
   - Authorized Domain: `unravler.com`.
   - Application Home Page: `https://www.unravler.com`.
   - Privacy Policy: `https://www.unravler.com/privacy`.
   - Terms of Service: `https://www.unravler.com/terms`.
