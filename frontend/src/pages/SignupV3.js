import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import UnravlerLogo from '@/components/UnravlerLogo';

/* ─────────────────────────────────────────────────────────────────────────
   SignupV3 — Netflix red left panel + clean white right form
───────────────────────────────────────────────────────────────────────── */
const SignupV3 = () => {
  const navigate = useNavigate();
  const { signup, loginWithGoogle } = useAuth();
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
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
      await signup(formData.email, formData.password, formData.name);
      toast.success('Account created successfully!');
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || 'Signup failed');
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
    try {
      setLoading(true);
      await loginWithGoogle();
      toast.success('Welcome to Unravler!');
      navigate('/dashboard');
    } catch (_) {
      setLoading(false);
    }
  };

  const inp = (field) => ({
    width: '100%',
    padding: '10px 14px',
    border: `1.5px solid ${focusField === field ? '#E50914' : '#d1d5db'}`,
    borderRadius: '7px',
    fontSize: '14.5px',
    color: '#111827',
    outline: 'none',
    background: '#fff',
    transition: 'border-color .18s, box-shadow .18s',
    boxSizing: 'border-box',
    boxShadow: focusField === field ? '0 0 0 3px rgba(229,9,20,0.1)' : 'none',
  });

  return (
    <>
      <style>{`
        @keyframes sv3badge {
          0%, 100% { transform: scale(1); }
          50%       { transform: scale(1.06); }
        }
      `}</style>

      <div style={{
        display: 'flex', minHeight: '100vh',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
        position: 'fixed', inset: 0, zIndex: 50, overflow: 'hidden',
      }}>
        {/* ══════════════════════════════════════════════════════
            LEFT PANEL — Netflix red
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
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none',
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }} />
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
            animation: 'sv3badge 2.4s ease-in-out infinite',
          }}>
            GET STARTED
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
            Publish & grow your brand<br />across all platforms
          </h2>

          <p style={{
            fontFamily: "'Caveat', cursive",
            fontSize: '27px', fontWeight: '600',
            color: 'rgba(255,255,255,0.82)',
            transform: 'rotate(-2deg)', display: 'inline-block',
            marginTop: '6px', marginBottom: '28px',
            position: 'relative', zIndex: 2,
          }}>
            start your free trial in 30 seconds ↗
          </p>

          {/* Features pills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', maxWidth: '520px', position: 'relative', zIndex: 2 }}>
            {[
              'Multi-platform scheduling',
              'Auto-publish to Reels & TikTok',
              'Analytics & Insights',
              'Collaborative approval queues',
              'AI Caption & Hashtag generator',
            ].map((feat) => (
              <div key={feat} style={{
                background: 'rgba(255,255,255,0.12)',
                border: '1px solid rgba(255,255,255,0.2)',
                borderRadius: '20px',
                padding: '7px 16px',
                color: '#fff',
                fontSize: '13px',
                fontWeight: '500',
                backdropFilter: 'blur(8px)',
              }}>
                ✓ {feat}
              </div>
            ))}
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════
            RIGHT PANEL — clean white signup form
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
          {/* Logo */}
          <div style={{ position: 'absolute', top: '36px', left: '52px', right: '52px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <UnravlerLogo />
            <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" /></svg>
              Back to home
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', maxWidth: '340px', width: '100%', marginTop: '30px' }}>
            <h1 style={{ fontSize: '26px', fontWeight: '700', color: '#111827', marginBottom: '4px', letterSpacing: '-0.5px', lineHeight: 1.25 }}>
              Create an account
            </h1>
            <p style={{ fontSize: '13.5px', color: '#6b7280', marginBottom: '20px' }}>
              Start scheduling and growing today.
            </p>

            {/* Google Signup */}
            <button onClick={handleGoogleSignup} disabled={loading}
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
              Sign up with Google
            </button>

            {/* Divider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px', color: '#d1d5db', fontSize: '11px', letterSpacing: '.06em', textTransform: 'uppercase' }}>
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }} />
              or continue with email
              <div style={{ flex: 1, height: '1px', background: '#e5e7eb' }} />
            </div>

            <form onSubmit={handleSubmit} autoComplete="on">
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '5px' }}>Full Name</label>
                <input
                  type="text" autoComplete="name" required
                  placeholder="John Doe"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  onFocus={() => setFocusField('name')}
                  onBlur={() => setFocusField(null)}
                  style={inp('name')}
                />
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '5px' }}>Email Address</label>
                <input
                  type="email" autoComplete="email" required
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  onFocus={() => setFocusField('email')}
                  onBlur={() => setFocusField(null)}
                  style={inp('email')}
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '5px' }}>Password</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPw ? 'text' : 'password'}
                    autoComplete="new-password" required
                    placeholder="Min. 6 characters"
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
                {loading ? 'Creating account…' : 'Create Account'}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: '16px' }}>
              <span style={{ fontSize: '13px', color: '#6b7280' }}>Already have an account? </span>
              <Link to="/login" style={{ fontSize: '13px', color: '#E50914', textDecoration: 'none', fontWeight: '600' }}
                onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                onMouseLeave={(e) => e.target.style.textDecoration = 'none'}>
                Sign in
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
          </div>
        </div>
      </div>
    </>
  );
};

export default SignupV3;
