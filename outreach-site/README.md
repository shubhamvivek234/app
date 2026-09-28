# Unravler Outreach site

This is the standalone, dependency-free marketing site intended for a future `unravler.io` domain. It does not share the existing `unravler.com` scheduler app's routing or authentication gate.

## Local preview

From this directory:

```bash
npm test
npm run preview
```

Open `http://localhost:4173/`. The hosting project can serve this directory as a static root with no build command. Links use relative `.html` paths, so a custom rewrite is not required.

## Current pilot boundaries

- Public CTA opens the visitor's email application from `contact.html`; there is no public signup or payment form.
- Standard pilot price is **$59 per connected sender per month**, with 1–5 seats, one requested country per workspace, operator-reviewed inventory, and a verified external invoice. Existing scheduler customers can request a separate bundle quote; no automatic discount is advertised.
- Live LinkedIn actions remain disabled pending product/legal approval and a real sender/proxy smoke test. The page must not promise an active automated service or guaranteed outcomes until those gates change.
- Outreach privacy, terms, billing/cancellation, cookie, and data-deletion pages are draft public copy. They require legal review and reconciliation with the final signed order terms before publication.
- Before pointing `unravler.io` to this site, confirm the final DNS/hosting project, support mailbox, brand/entity details, source-of-truth pricing, and legal review. Add a canonical URL, sitemap, and social-share image only once the domain and routes are final.

## Site Architecture & Feature Pages

- **Interactive Mega Menu**: The navbar features a Dripify-style mega menu dropdown on desktop and accordion drawer on mobile. Clicking or hovering "Features" reveals a floating menu with 8 core outreach features, use cases, safety notes, and pilot CTA.
- **Dedicated Feature Pages**: Each item in the mega menu links to an individual, fully detailed feature page:
  - `features.html` (All Features Hub & Capability Directory)
  - `feature-sequences.html` (Multichannel Branching Sequences)
  - `feature-leads.html` (LinkedIn Lead Generation & Import)
  - `feature-engage.html` (Engage & Social Warm-Up)
  - `feature-personalization.html` (Hyper-Personalized Outreach & AI Icebreakers)
  - `feature-inbox.html` (Unified Multi-Sender Inbox)
  - `feature-safety.html` (Dedicated 1:1 Proxies & Safety Architecture)
  - `feature-analytics.html` (LinkedIn Analytics & Activity Reports)
  - `feature-teams.html` (Multi-Sender Seats & Workspace Collaboration)
- **Pilot Compliance**: All pages maintain strict pilot transparency (operator-gated pilot, manual billing, session disclosures, and no unsubstantiated automation guarantees).

The black Unravler logo asset is reused from `frontend/public/`. The icon was supplied by the user. Ribbon artwork was generated for this site and optimized as JPEG for page delivery.
