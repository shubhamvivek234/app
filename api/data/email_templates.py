"""
Pre-built starter email templates for Unravler Broadcasts.
Provides responsive, modern HTML templates with clean typography,
call-to-actions, and variable placeholders (e.g. {{name}}, {{creator_name}}).
"""
from typing import Any, Dict, List

EMAIL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "tpl_announcement",
        "name": "Big Announcement / Launch",
        "category": "announcement",
        "badge": "Popular",
        "description": "Bold hero header, exciting release notes, and high-contrast CTA button.",
        "default_subject": "🚀 Something big just dropped: Introducing {product_name}!",
        "preview_text": "We've been working on this behind the scenes for months...",
        "body_markdown": """# 🚀 Big News is Here!

Hey {{name}},

I am thrilled to finally announce what we've been crafting behind the scenes over the past few weeks.

### What’s New:
- **Instant Access:** Unlock the brand new toolkit directly from your profile.
- **Save Hours Weekly:** Automate your repetitive social workflows without friction.
- **Exclusive Early-Bird Access:** Available to our community members first.

Click below to claim your spot before doors open to the general public:

[Explore the Launch Now →](https://unravler.com)

Warmly,  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Announcement</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #18181b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f4f4f5; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.05); border: 1px solid rgba(0,0,0,0.06);">
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 36px 32px; text-align: center;">
              <span style="display: inline-block; background-color: rgba(255,255,255,0.2); color: #ffffff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; padding: 4px 12px; border-radius: 20px; margin-bottom: 12px;">New Launch</span>
              <h1 style="color: #ffffff; font-size: 26px; font-weight: 800; margin: 0; line-height: 1.25;">Something Big Just Landed 🚀</h1>
            </td>
          </tr>
          <!-- Body Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <p style="font-size: 15px; line-height: 1.6; color: #3f3f46; margin: 0 0 16px 0;">Hey <strong>{{name}}</strong>,</p>
              <p style="font-size: 15px; line-height: 1.6; color: #3f3f46; margin: 0 0 20px 0;">We have been heads-down building something special, and today we're opening early access exclusively to our top subscribers and community.</p>
              
              <div style="background-color: #f8fafc; border-left: 4px solid #4f46e5; border-radius: 8px; padding: 16px; margin: 20px 0;">
                <p style="font-size: 14px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0;">✨ Here's what you get:</p>
                <ul style="margin: 0; padding-left: 20px; font-size: 14px; color: #475569; line-height: 1.6;">
                  <li>High-conversion Smart Bio blocks and direct monetization</li>
                  <li>One-click email outreach and instant WhatsApp pipelines</li>
                  <li>Exclusive early creator member benefits</li>
                </ul>
              </div>

              <div style="text-align: center; margin: 32px 0 24px 0;">
                <a href="https://unravler.com" style="display: inline-block; background-color: #4f46e5; color: #ffffff; font-size: 14px; font-weight: 700; text-decoration: none; padding: 14px 32px; border-radius: 12px; box-shadow: 0 2px 10px rgba(79,70,229,0.3);">Claim Your Early Access →</a>
              </div>

              <p style="font-size: 14px; line-height: 1.6; color: #71717a; margin: 24px 0 0 0;">Best regards,<br><strong style="color: #18181b;">{{creator_name}}</strong></p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; text-align: center; font-size: 11px; color: #a1a1aa;">
              <p style="margin: 0 0 4px 0;">Sent with ❤️ via Unravler Smart Bio Broadcast</p>
              <p style="margin: 0;"><a href="#" style="color: #71717a; text-decoration: underline;">Unsubscribe</a> from these updates.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    },
    {
        "id": "tpl_newsletter",
        "name": "Weekly Creator Digest",
        "category": "newsletter",
        "badge": "Editorial",
        "description": "Clean typographic layout for curated insights, article links, and personal notes.",
        "default_subject": "☕ The Weekly Pulse: 3 lessons from this week + tools I love",
        "preview_text": "Grab a coffee: here is your weekly breakdown of what matters...",
        "body_markdown": """# ☕ The Weekly Creator Digest

Hey {{name}},

Happy weekend! Here is your 3-minute digest of actionable insights, tools, and ideas to power your week.

---

### 1. The Power of Distribution Over Creation
Creating content is only 20% of the game. The remaining 80% lies in syndication, smart bios, and multi-channel reach.

### 2. High-ROI Tool Spotlight
Check out our latest workflows for scheduling and audience conversion.

### 3. Quick Action Step for Today
Pick one link on your bio and refresh its CTA button to increase clicks by 30%.

[Read the Full Breakdown →](https://unravler.com)

See you next week!  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Creator Digest</title>
</head>
<body style="margin: 0; padding: 0; background-color: #faf9f6; font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1c1917;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #faf9f6; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e7e5e4;">
          <tr>
            <td style="padding: 32px 32px 16px 32px; border-bottom: 2px solid #f5f5f4;">
              <span style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; color: #78716c;">Issue #24 · Weekly Digest</span>
              <h1 style="font-size: 24px; font-weight: 800; color: #1c1917; margin: 8px 0 0 0;">The Creator's Sunday Coffee ☕</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 28px 32px;">
              <p style="font-size: 15px; line-height: 1.7; color: #44403c;">Hey <strong>{{name}}</strong>,</p>
              <p style="font-size: 15px; line-height: 1.7; color: #44403c;">Here are three high-signal ideas, experiments, and tools that moved the needle for us this week:</p>

              <div style="margin: 24px 0; padding: 18px; background-color: #fdfbf7; border-radius: 12px; border: 1px solid #f4ede2;">
                <h3 style="font-size: 16px; margin: 0 0 6px 0; color: #1c1917;">1. The 80/20 of Audience Conversion</h3>
                <p style="font-size: 14px; line-height: 1.6; color: #57534e; margin: 0;">Treat your bio page like a landing page, not a telephone directory. Keep 3-5 high-priority blocks and eliminate link clutter.</p>
              </div>

              <div style="margin: 24px 0; padding: 18px; background-color: #fdfbf7; border-radius: 12px; border: 1px solid #f4ede2;">
                <h3 style="font-size: 16px; margin: 0 0 6px 0; color: #1c1917;">2. Direct Email Outreach Beats Algorithm Shifts</h3>
                <p style="font-size: 14px; line-height: 1.6; color: #57534e; margin: 0;">Algorithms fluctuate daily. The leads you capture via Smart Bio are the only audience you truly own 100%.</p>
              </div>

              <div style="text-align: center; margin: 32px 0 16px 0;">
                <a href="https://unravler.com" style="display: inline-block; background-color: #1c1917; color: #ffffff; font-size: 13px; font-weight: 700; text-decoration: none; padding: 12px 28px; border-radius: 30px;">Read More on the Hub →</a>
              </div>

              <p style="font-size: 14px; line-height: 1.7; color: #78716c; margin: 28px 0 0 0;">Until next Sunday,<br><strong style="color: #1c1917;">{{creator_name}}</strong></p>
            </td>
          </tr>
          <tr>
            <td style="padding: 20px 32px; background-color: #f5f5f4; text-align: center; font-size: 11px; color: #a8a29e;">
              <p style="margin: 0;">Published with Unravler · <a href="#" style="color: #78716c; text-decoration: underline;">Unsubscribe</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    },
    {
        "id": "tpl_flash_sale",
        "name": "Flash Sale & Limited Discount",
        "category": "promotion",
        "badge": "Monetization",
        "description": "High-urgency promotional format with discount code box, timer reminder, and bold CTA.",
        "default_subject": "⚡ 48-Hour Flash Sale: Get 40% off everything!",
        "preview_text": "This discount disappears Sunday midnight. Don't miss out...",
        "body_markdown": """# ⚡ Flash Sale Alert: 40% Off

Hey {{name}},

For the next 48 hours only, enjoy **40% OFF** our flagship guides, templates, and 1-on-1 consultations!

Use code: **CREATOR40** at checkout.

[Claim Your 40% Discount →](https://unravler.com)

*Note: This flash promotion ends Sunday at midnight. No exceptions!*

Cheers,  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Flash Sale</title>
</head>
<body style="margin: 0; padding: 0; background-color: #09090b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #fafafa;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #09090b; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #18181b; border-radius: 20px; overflow: hidden; border: 1px solid #27272a;">
          <tr>
            <td style="padding: 36px 32px; text-align: center; background: radial-gradient(circle at top, #3b0764 0%, #18181b 80%);">
              <span style="background-color: #e11d48; color: #ffffff; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; padding: 6px 14px; border-radius: 20px;">Limited Window</span>
              <h1 style="font-size: 30px; font-weight: 900; color: #ffffff; margin: 16px 0 8px 0;">⚡ 40% FLASH DISCOUNT</h1>
              <p style="color: #a1a1aa; font-size: 14px; margin: 0;">48 hours only — grab it before it resets to standard pricing.</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 32px;">
              <p style="font-size: 15px; line-height: 1.6; color: #d4d4d8; margin: 0 0 16px 0;">Hey <strong>{{name}}</strong>,</p>
              <p style="font-size: 15px; line-height: 1.6; color: #d4d4d8; margin: 0 0 24px 0;">As a thank-you for being in our community, here is an exclusive 48-hour voucher on all digital products and bookings:</p>

              <!-- Coupon Box -->
              <div style="background-color: #27272a; border: 2px dashed #f43f5e; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
                <p style="font-size: 12px; font-weight: 600; color: #a1a1aa; margin: 0 0 6px 0; text-transform: uppercase; letter-spacing: 1px;">Use Coupon Code at Checkout:</p>
                <span style="font-size: 24px; font-weight: 900; font-family: monospace; color: #ffffff; letter-spacing: 3px; background-color: #09090b; padding: 6px 16px; border-radius: 8px; display: inline-block;">FLASH40</span>
              </div>

              <div style="text-align: center; margin: 32px 0 20px 0;">
                <a href="https://unravler.com" style="display: inline-block; background-color: #f43f5e; color: #ffffff; font-size: 15px; font-weight: 800; text-decoration: none; padding: 15px 36px; border-radius: 12px; box-shadow: 0 4px 20px rgba(244,63,94,0.4);">Redeem 40% Off Now →</a>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 20px 32px; background-color: #09090b; text-align: center; font-size: 11px; color: #71717a;">
              <p style="margin: 0;">Sent to {{name}} via {{creator_name}} · <a href="#" style="color: #a1a1aa; text-decoration: underline;">Unsubscribe</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    },
    {
        "id": "tpl_event_webinar",
        "name": "Live Event / Webinar Invite",
        "category": "event",
        "badge": "Community",
        "description": "Date, time, key discussion topics, speaker profile, and 1-click RSVP action.",
        "default_subject": "🎟️ You're Invited: Live Creator Masterclass this Thursday",
        "preview_text": "Join us live as we break down modern monetization frameworks...",
        "body_markdown": """# 🎟️ Live Masterclass Invitation

Hey {{name}},

You are cordially invited to our exclusive live workshop:

**Mastering Modern Social Monetization**  
🗓️ **Date:** Thursday, 7:00 PM IST  
📍 **Location:** Live Virtual Studio  

### What We Will Cover:
1. Turning bio traffic into recurring buyers.
2. Converting cold social followers into warm email contacts.
3. Setting up instant WhatsApp & UPI checkout funnels.

[RSVP / Reserve Your Seat (Free) →](https://unravler.com)

Looking forward to seeing you live!  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Event Invite</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #cbd5e1; box-shadow: 0 4px 15px rgba(0,0,0,0.04);">
          <tr>
            <td style="padding: 36px 32px 24px 32px; text-align: center; border-bottom: 1px solid #e2e8f0;">
              <span style="font-size: 11px; font-weight: 700; color: #2563eb; background-color: #eff6ff; padding: 4px 12px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px;">Exclusive Webinar</span>
              <h1 style="font-size: 24px; font-weight: 800; color: #0f172a; margin: 12px 0 0 0;">Live Masterclass: Monetizing Your Bio</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 28px 32px;">
              <p style="font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 16px 0;">Hey <strong>{{name}}</strong>,</p>
              <p style="font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 20px 0;">We're hosting an interactive, hands-on session this Thursday to demonstrate how top creators turn casual visitors into paying customers.</p>

              <div style="background-color: #f8fafc; border-radius: 12px; padding: 20px; border: 1px solid #e2e8f0; margin-bottom: 24px;">
                <p style="font-size: 14px; margin: 0 0 8px 0;">🗓️ <strong>When:</strong> Thursday at 7:00 PM IST / 9:30 AM EST</p>
                <p style="font-size: 14px; margin: 0 0 8px 0;">📍 <strong>Where:</strong> Private Virtual Studio</p>
                <p style="font-size: 14px; margin: 0;">⏱️ <strong>Duration:</strong> 45 minutes + Q&amp;A</p>
              </div>

              <div style="text-align: center; margin: 28px 0 20px 0;">
                <a href="https://unravler.com" style="display: inline-block; background-color: #2563eb; color: #ffffff; font-size: 14px; font-weight: 700; text-decoration: none; padding: 14px 32px; border-radius: 10px;">Reserve My Complimentary Spot →</a>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 32px; background-color: #f8fafc; text-align: center; font-size: 11px; color: #94a3b8;">
              <p style="margin: 0;">Hosted by {{creator_name}} on Unravler</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    },
    {
        "id": "tpl_personal_welcome",
        "name": "Personal Warm Welcome",
        "category": "welcome",
        "badge": "High Open Rate",
        "description": "Clean, text-first personal email that builds deep rapport with new subscribers.",
        "default_subject": "👋 Quick hello from {creator_name} (and a gift inside)",
        "preview_text": "Thank you for joining my inner circle...",
        "body_markdown": """Hey {{name}},

I saw that you recently subscribed via my Smart Bio page, and I just wanted to reach out and say a genuine **welcome to the community**!

Every week, I share the exact strategies, workflows, and experiments that I use to scale my business.

As a thank-you for joining, here is a free resource you can check out right away:

[Download the Free Starter Kit →](https://unravler.com)

If you ever have any questions, just hit reply to this email. I read every response.

Warmly,  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome</title>
</head>
<body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #27272a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="padding: 30px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 540px;">
          <tr>
            <td style="font-size: 16px; line-height: 1.7; color: #27272a;">
              <p style="margin: 0 0 16px 0;">Hey <strong>{{name}}</strong>,</p>
              <p style="margin: 0 0 16px 0;">I noticed you joined my newsletter via my Smart Bio page, and I wanted to send a quick personal note to say <strong>welcome</strong>.</p>
              <p style="margin: 0 0 16px 0;">You are now part of our private inner circle. Every week I share unfiltered insights on social growth, direct audience monetization, and behind-the-scenes lessons.</p>
              <p style="margin: 0 0 20px 0;">As a welcome gift, here is a free resource you can use immediately:</p>

              <div style="margin: 24px 0; padding: 16px; background-color: #f4f4f5; border-radius: 10px;">
                <p style="margin: 0; font-size: 15px; font-weight: 600;">🎁 <a href="https://unravler.com" style="color: #4f46e5; text-decoration: underline;">Download the Complete Creator Playbook</a></p>
              </div>

              <p style="margin: 0 0 24px 0;">If you ever have any questions or feedback, simply hit reply to this email — it comes straight to my inbox.</p>
              <p style="margin: 0;">Warm regards,<br><strong>{{creator_name}}</strong></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    },
    {
        "id": "tpl_digital_product",
        "name": "Digital Product Showcase",
        "category": "product",
        "badge": "E-Commerce",
        "description": "Product card showcase with pricing, bulleted deliverables, and immediate checkout.",
        "default_subject": "📦 Get instant access to {product_name}",
        "preview_text": "Everything you need to level up your social workflow in one bundle...",
        "body_markdown": """# 📦 Meet Your New Toolkit

Hey {{name}},

Ready to upgrade your workflow? Get complete instant access to our comprehensive pack today.

### What's Inside:
- 50+ High-Converting Social Post Blueprints
- 10 Bio Layout Presets for instant setup
- Direct Video & Media embedding cheat-sheet

[Unlock Instant Access for ₹499 →](https://unravler.com)

Happy creating,  
{{creator_name}}
""",
        "body_html": """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Digital Product</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f8fafc; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 580px; background-color: #ffffff; border-radius: 18px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
          <tr>
            <td style="padding: 32px 32px 20px 32px; text-align: center;">
              <span style="font-size: 11px; font-weight: 700; color: #059669; background-color: #ecfdf5; padding: 4px 12px; border-radius: 20px; text-transform: uppercase;">Digital Download</span>
              <h1 style="font-size: 26px; font-weight: 800; color: #0f172a; margin: 12px 0 6px 0;">The Creator Toolkit Bundle</h1>
              <p style="font-size: 14px; color: #64748b; margin: 0;">Everything you need to automate &amp; monetize your brand</p>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px 32px 32px 32px;">
              <p style="font-size: 15px; line-height: 1.6; color: #334155; margin: 0 0 20px 0;">Hey <strong>{{name}}</strong>, this pack gives you immediate access to our plug-and-play social frameworks.</p>

              <div style="background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%); border: 1px solid #bbf7d0; border-radius: 14px; padding: 24px; text-align: center; margin-bottom: 24px;">
                <p style="font-size: 12px; font-weight: 700; color: #059669; text-transform: uppercase; margin: 0 0 4px 0;">All-Inclusive License</p>
                <div style="font-size: 36px; font-weight: 900; color: #065f46; margin: 8px 0;">₹499 <span style="font-size: 14px; font-weight: 500; color: #059669;">/ one-time</span></div>
                <ul style="text-align: left; margin: 16px 0 0 0; padding-left: 20px; font-size: 13px; color: #065f46; line-height: 1.6;">
                  <li>Lifetime access to all future updates</li>
                  <li>Works with Instagram, X, LinkedIn, and YouTube</li>
                  <li>Ready to use in under 5 minutes</li>
                </ul>
              </div>

              <div style="text-align: center;">
                <a href="https://unravler.com" style="display: inline-block; background-color: #059669; color: #ffffff; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 12px; box-shadow: 0 4px 15px rgba(5,150,105,0.3);">Download Bundle Now →</a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>""",
    }
]
