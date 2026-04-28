import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import UnravlerLogo from '@/components/UnravlerLogo';

/* ─────────────────────────────────────────────────────────────────────────
   Mock data for the app preview card
───────────────────────────────────────────────────────────────────────── */
const MOCK_POSTS = [
  {
    time: '9:00 AM',
    platform: (
      <svg viewBox="0 0 24 24" fill="#E1306C" width="13" height="13">
        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
      </svg>
    ),
    text: 'Golden hour vibes ✨ Swipe to see all the photos from our shoot today…',
    hasImg: true,
    imgColor: 'linear-gradient(135deg,#fde68a,#f59e0b)',
  },
  {
    time: '1:30 PM',
    platform: (
      <svg viewBox="0 0 24 24" fill="#1d9bf0" width="13" height="13">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
    ),
    text: 'Just dropped our latest blog post on social media trends for 2026 🔥 Thread below…',
    hasImg: false,
  },
  {
    time: '5:00 PM',
    platform: (
      <svg viewBox="0 0 24 24" fill="#0A66C2" width="13" height="13">
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
      </svg>
    ),
    text: "Excited to announce we've hit 10K followers! Thank you to our amazing community…",
    hasImg: false,
  },
  {
    time: '8:00 PM',
    platform: (
      <svg viewBox="0 0 24 24" fill="#FF0000" width="13" height="13">
        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
      </svg>
    ),
    text: 'New YouTube video is live! Watch our full breakdown of content strategy for Q2 2026…',
    hasImg: true,
    imgColor: 'linear-gradient(135deg,#fee2e2,#ef4444)',
  },
];

const CHANNELS = [
  { name: 'All Channels', count: 29, dot: '#6366f1', active: true },
  { name: 'Creator Studio', count: 5,  dot: '#E1306C', active: false },
  { name: 'Tech News',      count: 7,  dot: '#1d9bf0', active: false },
  { name: 'Marketing',      count: 12, dot: '#0A66C2', active: false },
  { name: 'Personal',       count: 2,  dot: '#000',    active: false },
];

/* ─────────────────────────────────────────────────────────────────────────
   LoginV3 — Netflix red left panel + clean white right form
───────────────────────────────────────────────────────────────────────── */
const LoginV3 = () => {
  const navigate = useNavigate();
  const { login, loginWithGoogle } = useAuth();
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [focusField, setFocusField] = useState(null);

  /* Load fonts */
  useEffect(() => {
    const link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Caveat:wght@600;700&family=Inter:wght@400;500;600;700;800&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
    return () => { try { document.head.removeChild(link); } catch (_) {} };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      await login(formData.email, formData.password);
      toast.success('Welcome back!');
    } catch (error) {
      let msg = 'Login failed';
      if (error.code) {
        switch (error.code) {
          case 'auth/invalid-email':  msg = 'Invalid email address.'; break;
          case 'auth/user-disabled':  msg = 'User account is disabled.'; break;
          case 'auth/user-not-found': msg = 'No account found with this email.'; break;
          case 'auth/wrong-password': msg = 'Incorrect password.'; break;
          default:                    msg = error.message;
        }
      }
      toast.error(msg);
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);
      await loginWithGoogle();
      toast.success('Welcome back!');
    } catch (_) { setLoading(false); }
  };

  const inp = (field) => ({
    width: '100%', padding: '10px 14px',
    border: `1.5px solid ${focusField === field ? '#E50914' : '#d1d5db'}`,
    borderRadius: '7px', fontSize: '14.5px', color: '#111827',
    outline: 'none', background: '#fff', transition: 'border-color .18s, box-shadow .18s',
    boxSizing: 'border-box',
    boxShadow: focusField === field ? '0 0 0 3px rgba(229,9,20,0.1)' : 'none',
  });

  return (
    <>
      {/* ── Keyframe animations ── */}
      <style>{`
        @keyframes lv3badge {
          0%, 100% { transform: scale(1); }
          50%       { transform: scale(1.06); }
        }
        @keyframes lv3row {
          0%   { opacity: 0; transform: translateX(-12px); }
          100% { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      <div style={{
        display: 'flex', minHeight: '100vh',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
        position: 'fixed', inset: 0, zIndex: 50, overflow: 'hidden',
      }}>

        {/* ══════════════════════════════════════════════════════
            LEFT PANEL — Netflix red, headline + animated card
        ══════════════════════════════════════════════════════ */}
        <div style={{
          flex: '0 0 60%',
          background: 'linear-gradient(145deg, #E50914 0%, #b0060f 100%)',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          padding: '48px 56px 40px',
          boxSizing: 'border-box',
        }}>
          {/* Subtle noise texture overlay */}
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none',
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }} />
          {/* Dark vignette on right edge for depth */}
          <div style={{
            position: 'absolute', top: 0, right: 0, bottom: 0, width: '120px', pointerEvents: 'none',
            background: 'linear-gradient(to right, transparent, rgba(0,0,0,0.18))',
          }} />

          {/* NEW badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', alignSelf: 'flex-start',
            background: '#fff', color: '#E50914',
            border: 'none', borderRadius: '6px',
            padding: '5px 16px', fontSize: '11px', fontWeight: '800',
            letterSpacing: '0.14em', marginBottom: '22px',
            position: 'relative', zIndex: 2,
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            animation: 'lv3badge 2.4s ease-in-out infinite',
          }}>
            NEW
          </div>

          {/* Headline */}
          <h2 style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: '40px', fontWeight: '800',
            color: '#fff', lineHeight: 1.18,
            letterSpacing: '-1.2px', marginBottom: '6px',
            maxWidth: '560px', position: 'relative', zIndex: 2,
            textShadow: '0 2px 12px rgba(0,0,0,0.18)',
          }}>
            Schedule posts across<br />your favorite platforms
          </h2>

          {/* Handwriting accent */}
          <p style={{
            fontFamily: "'Caveat', cursive",
            fontSize: '27px', fontWeight: '600',
            color: 'rgba(255,255,255,0.82)',
            transform: 'rotate(-2deg)', display: 'inline-block',
            marginTop: '6px', marginBottom: '28px',
            position: 'relative', zIndex: 2,
          }}>
            and grow your audience ↗
          </p>

          {/* ── STATIC APP MOCKUP CARD — bottom-right of red panel ── */}
          <div style={{
            position: 'absolute', bottom: 0, right: 0, width: '80%', zIndex: 2,
          }}>
            <div style={{
              background: '#fff',
              borderRadius: '16px 16px 0 0',
              overflow: 'hidden',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              maxHeight: '380px',
              border: '1px solid rgba(255,255,255,0.15)',
              boxShadow: '0 -12px 48px rgba(0,0,0,0.2)',
            }}>

              {/* Window chrome bar */}
              <div style={{ display: 'flex', alignItems: 'center', padding: '10px 16px', background: '#f8f9fa', borderBottom: '1px solid #f0f0f0', gap: '6px' }}>
                <div style={{ width: '11px', height: '11px', borderRadius: '50%', background: '#ff5f57' }} />
                <div style={{ width: '11px', height: '11px', borderRadius: '50%', background: '#febc2e' }} />
                <div style={{ width: '11px', height: '11px', borderRadius: '50%', background: '#28c840' }} />
                <div style={{ flex: 1, height: '20px', background: '#ececec', borderRadius: '4px', marginLeft: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <span style={{ fontSize: '9px', color: '#9ca3af', fontWeight: '500' }}>app.socialentangle.io</span>
                </div>
              </div>

              {/* Tabs */}
              <div style={{ display: 'flex', gap: '2px', padding: '8px 16px 0', borderBottom: '1px solid #f3f4f6', background: '#fafafa' }}>
                {['Queue', 'Calendar', 'Analytics', 'Community', 'Ideas'].map((tab, i) => (
                  <div key={tab} style={{
                    padding: '6px 13px', fontSize: '12px',
                    fontWeight: i === 3 ? '600' : '400',
                    color: i === 3 ? '#E50914' : '#9ca3af',
                    borderBottom: i === 3 ? '2px solid #E50914' : '2px solid transparent',
                    cursor: 'pointer', marginBottom: '-1px', userSelect: 'none',
                    whiteSpace: 'nowrap',
                  }}>{tab}</div>
                ))}
              </div>

              {/* Body */}
              <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

                {/* Channel sidebar */}
                <div style={{ width: '190px', flexShrink: 0, borderRight: '1px solid #f3f4f6', padding: '10px 8px', overflowY: 'auto' }}>
                  {CHANNELS.map((ch, i) => (
                    <div key={ch.name} style={{
                      display: 'flex', alignItems: 'center', gap: '8px',
                      padding: '7px 8px', borderRadius: '7px',
                      background: ch.active ? '#fff1f1' : 'transparent',
                      cursor: 'pointer', marginBottom: '2px',
                      animation: `lv3row ${0.3 + i * 0.08}s ease-out both`,
                    }}>
                      <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: ch.dot, flexShrink: 0 }} />
                      <span style={{ fontSize: '12px', fontWeight: ch.active ? '600' : '400', color: ch.active ? '#E50914' : '#4b5563', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ch.name}
                      </span>
                      <span style={{ fontSize: '10px', background: ch.active ? '#fee2e2' : '#f3f4f6', color: ch.active ? '#E50914' : '#6b7280', borderRadius: '10px', padding: '1px 6px', flexShrink: 0 }}>
                        {ch.count}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Post feed */}
                <div style={{ flex: 1, padding: '12px 14px', overflowY: 'auto' }}>
                  {/* Channel header */}
                  <div style={{ display: 'flex', alignItems: 'center', marginBottom: '12px', gap: '10px' }}>
                    <div style={{ width: '34px', height: '34px', background: 'linear-gradient(135deg,#E50914,#ff6b6b)', borderRadius: '50%', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: '600', color: '#111827' }}>Creator Studio</div>
                      <div style={{ fontSize: '10.5px', color: '#9ca3af' }}>4 posts scheduled today</div>
                    </div>
                    <div style={{ marginLeft: 'auto', background: '#dcfce7', color: '#15803d', fontSize: '10px', fontWeight: '700', padding: '3px 10px', borderRadius: '12px' }}>Active</div>
                  </div>

                  {/* Posts */}
                  {MOCK_POSTS.map((post, i) => (
                    <div key={i} style={{
                      display: 'flex', gap: '10px',
                      padding: '8px 0',
                      borderTop: i === 0 ? 'none' : '1px solid #f5f5f5',
                      alignItems: 'flex-start',
                      animation: `lv3row ${0.4 + i * 0.1}s ease-out both`,
                    }}>
                      <div style={{ fontSize: '10px', color: '#9ca3af', width: '44px', flexShrink: 0, paddingTop: '1px' }}>{post.time}</div>
                      <div style={{ marginTop: '1px', flexShrink: 0 }}>{post.platform}</div>
                      <div style={{ flex: 1, fontSize: '11.5px', color: '#374151', lineHeight: 1.45 }}>{post.text}</div>
                      {post.hasImg && (
                        <div style={{ width: '38px', height: '38px', background: post.imgColor, borderRadius: '6px', flexShrink: 0 }} />
                      )}
                    </div>
                  ))}

                  {/* CTA button */}
                  <button style={{
                    width: '100%', marginTop: '12px', padding: '9px',
                    background: '#E50914', color: '#fff', border: 'none',
                    borderRadius: '7px', fontSize: '12.5px', fontWeight: '600',
                    cursor: 'pointer', letterSpacing: '0.01em',
                    boxShadow: '0 3px 10px rgba(229,9,20,0.35)',
                  }}>
                    + Schedule a Post
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════
            RIGHT PANEL — clean white login form
        ══════════════════════════════════════════════════════ */}
        <div style={{
          flex: '0 0 40%',
          background: '#fffffb',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '36px 52px 28px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          position: 'relative',
        }}>
          {/* Logo — pinned to top so form is truly centered */}
          <div style={{ position: 'absolute', top: '36px', left: '52px', right: '52px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <UnravlerLogo />
            <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" /></svg>
              Back to home
            </button>
          </div>

          {/* Form — centered in full panel height */}
          <div style={{ display: 'flex', flexDirection: 'column', maxWidth: '340px', width: '100%' }}>
            <h1 style={{ fontSize: '26px', fontWeight: '700', color: '#111827', marginBottom: '20px', letterSpacing: '-0.5px', lineHeight: 1.25 }}>
              Log in
            </h1>

            {/* Google — at top like V1 */}
            <button onClick={handleGoogleLogin} disabled={loading}
              style={{ width: '100%', padding: '10px 14px', background: '#fff', border: '1.5px solid #d1d5db', borderRadius: '7px', color: '#374151', fontSize: '14px', fontWeight: '500', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', transition: 'border-color .18s, box-shadow .18s', marginBottom: '16px' }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#E50914'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(229,9,20,0.08)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#d1d5db'; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <svg width="17" height="17" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.5 30.2 0 24 0 14.7 0 6.7 5.5 2.7 13.5l7.8 6C12.5 13.1 17.8 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.5 2.9-2.2 5.4-4.7 7.1l7.4 5.7c4.3-4 6.1-9.9 6.1-16.8z"/>
                <path fill="#FBBC05" d="M10.5 28.5a14.9 14.9 0 010-9.1l-7.8-6A24 24 0 000 24c0 3.9.9 7.5 2.7 10.6l7.8-6.1z"/>
                <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.4-5.7c-2 1.4-4.6 2.2-7.8 2.2-6.2 0-11.5-3.6-13.5-9l-7.8 6C6.7 42.5 14.7 48 24 48z"/>
              </svg>
              Continue with Google
            </button>

            {/* Divider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px', color: '#d1d5db', fontSize: '11px', letterSpacing: '.06em', textTransform: 'uppercase' }}>
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }} />
              or
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }} />
            </div>

            <form onSubmit={handleSubmit} autoComplete="on">
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Email Address</label>
                <input
                  type="email" autoComplete="email" required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  onFocus={() => setFocusField('email')}
                  onBlur={() => setFocusField(null)}
                  style={inp('email')}
                />
              </div>

              <div style={{ marginBottom: '22px' }}>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Password</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPw ? 'text' : 'password'}
                    autoComplete="current-password" required
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    onFocus={() => setFocusField('pw')}
                    onBlur={() => setFocusField(null)}
                    style={{ ...inp('pw'), paddingRight: '40px' }}
                  />
                  <button type="button" onClick={() => setShowPw(v => !v)}
                    style={{ position: 'absolute', right: '11px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 0, display: 'flex', alignItems: 'center' }}>
                    {showPw
                      ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                      : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    }
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading}
                style={{
                  width: '100%', padding: '11px',
                  background: '#E50914', border: 'none', borderRadius: '7px',
                  color: '#fff', fontSize: '15px', fontWeight: '600',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.7 : 1,
                  transition: 'background .2s, box-shadow .2s',
                  boxShadow: '0 4px 14px rgba(229,9,20,0.4)',
                  letterSpacing: '0.01em',
                }}
                onMouseEnter={(e) => { if (!loading) { e.target.style.background = '#c0070f'; e.target.style.boxShadow = '0 6px 18px rgba(229,9,20,0.5)'; } }}
                onMouseLeave={(e) => { e.target.style.background = '#E50914'; e.target.style.boxShadow = '0 4px 14px rgba(229,9,20,0.4)'; }}
              >
                {loading ? 'Signing in…' : 'Log In'}
              </button>
            </form>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '14px' }}>
              <Link to="/signup" style={{ fontSize: '13px', color: '#4b5563', textDecoration: 'none' }}
                onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                onMouseLeave={(e) => e.target.style.textDecoration = 'none'}>
                Create an account
              </Link>
              <Link to="/forgot-password" style={{ fontSize: '13px', color: '#4b5563', textDecoration: 'none' }}
                onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                onMouseLeave={(e) => e.target.style.textDecoration = 'none'}>
                Forgot your password?
              </Link>
            </div>

          </div>

          {/* Footer */}
          <div style={{ display: 'flex', gap: '14px', fontSize: '11.5px', color: '#9ca3af', marginTop: '24px', flexWrap: 'wrap' }}>
            <Link to="/terms" style={{ color: '#9ca3af', textDecoration: 'none' }}
              onMouseEnter={(e) => e.target.style.color = '#6b7280'}
              onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Terms of Service</Link>
            <span>·</span>
            <Link to="/privacy" style={{ color: '#9ca3af', textDecoration: 'none' }}
              onMouseEnter={(e) => e.target.style.color = '#6b7280'}
              onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Privacy Policy</Link>
            <span>·</span>
            <Link to="/security" style={{ color: '#9ca3af', textDecoration: 'none' }}
              onMouseEnter={(e) => e.target.style.color = '#6b7280'}
              onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Security</Link>
          </div>
        </div>

      </div>
    </>
  );
};

export default LoginV3;
