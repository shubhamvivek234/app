# Unravler.io Feature Video Recording & Generation Guide
> Practical recording workflows, software recommendations, and click-by-click scripts matching the Unravler Outreach app.

---

## 1. Quick Overview & Recommended Production Tools

Every feature page on `unravler.io` features a modern browser frame with a high-definition video player (`.hero-video-frame`). To replace the current placeholder clips with genuine product walkthroughs, you can either record your screen manually with specialized capture software or automate the recording with a headless script.

### Option A: Screen Studio (Recommended for macOS — Highest Quality & Lowest Effort)
- **Why it's the industry standard:** [Screen Studio](https://www.screen.studio/) is used by Linear, Raycast, and top SaaS teams. It automatically tracks your mouse pointer, zooms in seamlessly on interactive elements (inputs, dropdowns, buttons), renders smooth motion blur, and outputs professional 60fps video with zero manual keyframing.
- **Settings:**
  - Aspect Ratio: 16:9 or 16:10.
  - Background: Transparent or clean neutral (#0F172A).
  - Cursor size: 1.5× with smooth follow.
  - Window frame: Can be turned off inside Screen Studio because our site UI already provides the macOS window chrome (`.video-browser-bar`).

### Option B: Automated Playwright Headless Recording (100% Deterministic & Code-Driven)
- If you don't want to record manually or want repeatable videos that update whenever UI changes, use Playwright to launch Chromium at 1920×1080, execute scripted clicks and typing at human speed, and record directly to an `.mp4` file.
- See **Section 4** below for a ready-to-run automation script.

### Option C: CleanShot X or OBS Studio
- If using CleanShot X, record at fixed 1920×1080, enable mouse highlight rings, and keep cursor movements deliberate and steady.

---

## 2. Technical Asset Specifications

When saving your recordings, place them in `outreach-site/assets/videos/`:

| Feature Page | Target MP4 File | Target Poster Image | Video Browser URL Pill |
| :--- | :--- | :--- | :--- |
| **All Features Hub** | `demo-hub.mp4` | `poster-hub.png` | `unravler.io/outreach/overview` |
| **Multichannel Sequences** | `demo-sequences.mp4` | `poster-sequences.png` | `unravler.io/outreach/sequences` |
| **LinkedIn Lead Gen** | `demo-leads.mp4` | `poster-leads.png` | `unravler.io/outreach/leads` |
| **Engage & Social Warm-Up** | `demo-engage.mp4` | `poster-engage.png` | `unravler.io/outreach/engage` |
| **Hyper-Personalization** | `demo-personalization.mp4` | `poster-personalization.png` | `unravler.io/outreach/personalization` |
| **Unified Outreach Inbox** | `demo-inbox.mp4` | `poster-inbox.png` | `unravler.io/outreach/inbox` |
| **Dedicated Proxies & Safety** | `demo-safety.mp4` | `poster-safety.png` | `unravler.io/outreach/safety` |
| **LinkedIn Analytics** | `demo-analytics.mp4` | `poster-analytics.png` | `unravler.io/outreach/analytics` |
| **Multi-Sender & Teams** | `demo-teams.mp4` | `poster-teams.png` | `unravler.io/outreach/teams` |

### Recommended Encoding:
- **Format:** MP4 (`video/mp4`) with `h264` video codec and `yuv420p` pixel format.
- **Duration:** 18 to 28 seconds per video.
- **Audio:** No audio track (silent demonstration).
- **Web Optimization:** Fast-start / moov atom at beginning of file.
- **CLI Compression Command:**
  ```bash
  ffmpeg -i raw_capture.mov -c:v libx264 -profile:v high -level 4.0 -pix_fmt yuv420p -crf 22 -preset slow -movflags +faststart -an demo-<slug>.mp4
  ffmpeg -ss 00:00:02 -i demo-<slug>.mp4 -vframes 1 -q:v 2 poster-<slug>.png
  ```

---

## 3. Step-by-Step Recording Scripts (App-Exact Workflows)

Ensure your local app is running (`npm start` in `frontend/`, backend API active) or use staging. Clean sample demo data (realistic prospect names, companies, and post snippets) ensures the video looks credible.

---

### 1. Multichannel Sequences (`feature-sequences.html`)
- **Page in App:** `/outreach/campaigns` → Click **"New Campaign"** (or open an existing campaign) → Navigate to **Step 2: Sequence Canvas** (`SequenceCanvas.js`).
- **Goal:** Showcase visual drag-and-drop branching logic, timing delays, and conditional steps.
- **Click-by-Click Script (20–25s):**
  1. **(0–4s):** Start with an empty canvas or standard 3-step DAG. Drag a **"Profile Visit"** node onto the canvas. Connect it to the "Start" node.
  2. **(4–9s):** Add a **"Delay"** block (set to `1 day`). From the delay output, add a **"Connection Request"** node.
  3. **(9–15s):** Click the Connection Request node to open the right-side configuration drawer. Click the note field and insert the `{first_name}` variable pill. Type: `Loved your recent post on distributed systems!`.
  4. **(15–20s):** Drag a **"Condition: If Invite Accepted"** branching node. Point the **"Yes"** branch to a **"Send LinkedIn Message"** node (Delay: 2 days), and the **"No"** branch to an **"InMail / Check Post"** fallback.
  5. **(20–24s):** Zoom out slightly using canvas zoom controls to show the complete, elegant decision tree.

---

### 2. LinkedIn Lead Generation (`feature-leads.html`)
- **Page in App:** `/outreach/leads` (`OutreachLeads.js`).
- **Goal:** Show frictionless prospect list building, CSV import with column mapping, and duplicate prevention.
- **Click-by-Click Script (18–22s):**
  1. **(0–4s):** Open the Leads page showing an existing list with status pills (`New`, `Enriched`, `In Campaign`).
  2. **(4–9s):** Click the primary **"Import Leads"** button. The modal opens (`ImportLeadsModal.js`). Select the **"CSV / Paste"** tab.
  3. **(9–14s):** Paste or upload a list of 10–20 prospects (e.g., `Shubham Vivek, CTO, SocialEntangler, https://linkedin.com/in/...`). The auto-mapping table confirms `First Name`, `Last Name`, `Company`, and `Profile URL`.
  4. **(14–18s):** Toggle on **"Deduplicate against active campaigns"** and add the tag `FinTech Leaders Q4`.
  5. **(18–22s):** Click **"Import Prospects"**. The progress bar completes, and the new leads appear highlighted in the table with tags.

---

### 3. Engage & Social Warm-Up (`feature-engage.html`)
- **Page in App:** `/outreach/engage` (`OutreachEngage.js`).
- **Goal:** Show pre-outreach post scraping, AI-crafted comment suggestions, and human-in-the-loop review.
- **Click-by-Click Script (20–25s):**
  1. **(0–5s):** Open the Engage dashboard. Select a prospect from the left list. The center panel loads the prospect's real recent LinkedIn post (e.g. an insight on engineering team scaling).
  2. **(5–10s):** Click **"Suggest AI Comment"**. Watch the AI generate 2 tailored draft options (one insightful observation, one question-led hook).
  3. **(10–16s):** Click **"Edit Draft"**. Make a quick 1-sentence tweak in the composer to demonstrate human curation.
  4. **(16–20s):** Click **"Copy Draft & Open on LinkedIn"**. A toast notification confirms the comment is copied.
  5. **(20–24s):** Click **"Mark Completed"**. Notice the engagement counter updates to 100% and unlocks the campaign auto-launch gate.

---

### 4. Hyper-Personalized Outreach (`feature-personalization.html`)
- **Page in App:** `/outreach/voice` or Campaign Wizard Step 2 / Message Editor.
- **Goal:** Show dynamic merge tags, AI opening icebreakers, and real-time desktop/mobile message preview.
- **Click-by-Click Script (18–22s):**
  1. **(0–4s):** In the message editor, show a connection message template with curly-brace variable pills.
  2. **(4–10s):** Click the **"Insert Variable"** dropdown to show `{first_name}`, `{company_name}`, `{job_title}`, and `{mutual_connection}`.
  3. **(10–15s):** Click **"Generate AI Icebreaker"**. The AI generates an opening referencing the prospect's company announcement.
  4. **(15–20s):** Switch the preview tab from **"Template"** to **"Live Lead Simulator"**. Select different prospects from the dropdown to show how the message dynamically resolves names, company context, and tone for each recipient.
  5. **(20–22s):** Highlight the character counter indicator staying strictly within LinkedIn's 300-character limit.

---

### 5. Unified Outreach Inbox (`feature-inbox.html`)
- **Page in App:** `/outreach/inbox` (`OutreachInbox.js`).
- **Goal:** Show managing multi-account replies in one place with quick canned snippets and status updates.
- **Click-by-Click Script (18–24s):**
  1. **(0–4s):** Show the 3-column inbox layout: Account/Filter sidebar on the left, conversation threads in the middle, active chat on the right.
  2. **(4–8s):** Click on a thread with a positive prospect reply (`"Thanks for reaching out, let's talk next Tuesday"`).
  3. **(8–13s):** Click the **"Quick Snippets"** icon above the reply composer. Select the canned template: `Demo Calendar Link`. The full message with Calendly link populates instantly.
  4. **(13–18s):** Change the Lead Status dropdown in the right panel from `In Sequence` to `Meeting Booked`. The status pill turns green.
  5. **(18–22s):** Click **"Snooze / Reminder"** and set a reminder for 2 days. The reminder badge appears on the thread.

---

### 6. Dedicated Proxies & Safety Architecture (`feature-safety.html`)
- **Page in App:** `/outreach/accounts` (`OutreachAccounts.js`) & `/outreach/settings` (`OutreachSettings.js`).
- **Goal:** Demonstrate enterprise-grade 1:1 dedicated residential proxy leases, encrypted credentials, and working hours limits.
- **Click-by-Click Script (18–22s):**
  1. **(0–5s):** Navigate to the Accounts tab. Show connected sender cards with green **"Proxy Healthy"** badges and assigned static IP addresses with country flags (e.g. `US · 198.51.100.24`).
  2. **(5–10s):** Open the **"Connect Account"** modal. Show the country selector (`United States`, `United Kingdom`, `Canada`) and the notice explaining 1:1 dedicated residential ISP proxy leasing.
  3. **(10–16s):** Go to **Settings → Working Hours & Safety Limits**. Adjust the slider for `Max connection requests/day` (set safely to 25) and `Working Hours Window` (09:00 - 18:00 EST).
  4. **(16–22s):** Point out the security explanation note: session tokens are stored encrypted using AES/Fernet and never logged in plaintext.

---

### 7. LinkedIn Analytics & Reports (`feature-analytics.html`)
- **Page in App:** `/outreach/analytics` (`OutreachAnalytics.js`) or a Campaign Detail page.
- **Goal:** Show honest, verifiable conversion funnel metrics and one-click PDF report generation.
- **Click-by-Click Script (18–22s):**
  1. **(0–5s):** Display the top KPI summary tiles: `Total Prospects (240)`, `Connection Sent (180)`, `Accepted (38%)`, `Replies (22%)`.
  2. **(5–10s):** Scroll smoothly down to the **Sequence Funnel Chart**, showing drop-off and conversion rates at each step.
  3. **(10–15s):** Click on the **"Event Activity Stream"** to show immutable, verifiable timestamps for every recorded action.
  4. **(15–20s):** Click the prominent **"Print / Save as PDF"** button. The clean, professionally formatted print stylesheet opens with header logo and data tables ready for export.
  5. **(20–22s):** Close the print preview dialog, returning cleanly to the dashboard.

---

### 8. Multi-Sender & Teams Workspace (`feature-teams.html`)
- **Page in App:** `/outreach/accounts` (`OutreachAccounts.js`) and Campaign Sender Assignment.
- **Goal:** Show connecting multiple senders, dedicated proxy isolation per seat, and campaign sender distribution.
- **Click-by-Click Script (18–22s):**
  1. **(0–5s):** View the Accounts table showing 3 active sender seats (e.g., `Alex Miller - Sales Lead`, `Sarah Chen - SDR`, `Jordan Taylor - Founder`).
  2. **(5–10s):** Highlight that each sender has an independent proxy lease and individual daily limit counters.
  3. **(10–16s):** Go to **Campaigns → Edit Campaign → Sender Settings**. Show the sender dropdown allowing assignment of either a single sender or distributing leads evenly across the team.
  4. **(16–22s):** Return to Accounts view and demonstrate one-click pause/resume controls for individual sender seats.

---

### 9. Platform Overview Hub (`features.html`)
- **Page in App:** Full journey across the Unravler Outreach workspace.
- **Goal:** Provide a fast, energetic 24-second montage of the entire platform workflow.
- **Click-by-Click Script (24–28s):**
  1. **(0–4s):** Quick shot of the Leads list and CSV import.
  2. **(4–10s):** Cut to the visual Sequence Canvas zooming out on a multi-step branch.
  3. **(10–15s):** Cut to Engage dashboard showing an AI post comment suggestion.
  4. **(15–20s):** Cut to Unified Inbox sending a canned Calendly reply.
  5. **(20–25s):** End on the Analytics dashboard showing conversion metrics and the green "Active Pilot" indicator.

---

## 4. Automated Recording with Playwright (Script Template)

If you prefer automated, pixel-perfect captures without manual mouse recording, you can run this script using Node.js and Playwright.

### Setup:
```bash
npm install -D playwright
```

### Script (`record-demo.js`):
```javascript
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    headless: false, // Set to true if you don't need visual preview
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: path.join(__dirname, 'raw-recordings'),
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();

  // Navigate to local Unravler app
  await page.goto('http://localhost:3000/outreach/campaigns');
  await page.waitForTimeout(2000);

  // Click Sequence Builder
  const newCampaignBtn = page.locator('text=New Campaign');
  if (await newCampaignBtn.isVisible()) {
    await newCampaignBtn.click();
    await page.waitForTimeout(1500);
  }

  // Smooth mouse movement and interaction
  await page.mouse.move(500, 300, { steps: 25 });
  await page.waitForTimeout(1000);

  // Close context to finish writing MP4
  await context.close();
  await browser.close();

  console.log('Recording completed in ./raw-recordings');
})();
```

---

## 5. Verification Checklist After Adding New Videos

Once you replace any `.mp4` file or `.png` poster in `outreach-site/assets/videos/`:

1. **Verify File Names:** Make sure the filenames match the table in **Section 2** exactly (e.g. `demo-sequences.mp4`, `poster-sequences.png`).
2. **Run Site Test Suite:**
   ```bash
   npm test --prefix outreach-site
   ```
   All link validators and public page assertions must pass without warnings.
3. **Check In Browser:**
   - Open any feature page (e.g. `feature-sequences.html`).
   - The hero card should display the custom bright theme color.
   - The video should display your poster thumbnail with the frosted-glass play button.
   - Clicking play should start the video and smoothly hide the overlay button.
   - Pausing or reaching video completion should gracefully restore the play button.
   - Scrolling down past 40px should smoothly transition the top header into the fixed white bar with dark logo and navigation links.
