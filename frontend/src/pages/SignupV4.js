import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import SocialEntanglerLogo from '@/components/SocialEntanglerLogo';

/* ─────────────────────────────────────────────────────────────────────────
   Pupil — dark dot that tracks the mouse
───────────────────────────────────────────────────────────────────────── */
const Pupil = ({ size = 12, maxDistance = 5, pupilColor = '#2D2D2D', forceLookX, forceLookY }) => {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const ref = useRef(null);

  useEffect(() => {
    const handleMove = (e) => {
      if (!ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const angle = Math.atan2(e.clientY - cy, e.clientX - cx);
      const dist = Math.min(maxDistance, Math.hypot(e.clientX - cx, e.clientY - cy) * 0.15);
      setOffset({ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist });
    };
    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, [maxDistance]);

  const dx = forceLookX !== undefined ? Math.max(-maxDistance, Math.min(maxDistance, forceLookX)) : offset.x;
  const dy = forceLookY !== undefined ? Math.max(-maxDistance, Math.min(maxDistance, forceLookY)) : offset.y;

  return (
    <div ref={ref} style={{
      width: size, height: size, borderRadius: '50%', background: pupilColor,
      transform: `translate(${dx}px, ${dy}px)`,
      transition: forceLookX !== undefined ? 'transform 0.3s ease' : 'none',
      flexShrink: 0,
    }} />
  );
};

/* ─────────────────────────────────────────────────────────────────────────
   EyeBall — white circle with a tracking pupil
───────────────────────────────────────────────────────────────────────── */
const EyeBall = ({
  size = 48, pupilSize = 16, maxDistance = 10,
  eyeColor = 'white', pupilColor = '#2D2D2D',
  isBlinking = false, forceLookX, forceLookY,
}) => {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const ref = useRef(null);

  useEffect(() => {
    const handleMove = (e) => {
      if (!ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const angle = Math.atan2(e.clientY - cy, e.clientX - cx);
      const dist = Math.min(maxDistance, Math.hypot(e.clientX - cx, e.clientY - cy) * 0.2);
      setOffset({ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist });
    };
    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, [maxDistance]);

  const dx = forceLookX !== undefined ? Math.max(-maxDistance, Math.min(maxDistance, forceLookX)) : offset.x;
  const dy = forceLookY !== undefined ? Math.max(-maxDistance, Math.min(maxDistance, forceLookY)) : offset.y;

  return (
    <div ref={ref} style={{
      width: size, height: isBlinking ? 2 : size,
      borderRadius: '50%', background: eyeColor,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden', transition: 'height 0.06s ease', flexShrink: 0,
    }}>
      {!isBlinking && (
        <div style={{
          width: pupilSize, height: pupilSize, borderRadius: '50%', background: pupilColor,
          transform: `translate(${dx}px, ${dy}px)`,
          transition: forceLookX !== undefined ? 'transform 0.3s ease' : 'none',
          flexShrink: 0,
        }} />
      )}
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────
   SignupV4 — animated character mascots + signup form
───────────────────────────────────────────────────────────────────────── */
const SignupV4 = () => {
  const navigate = useNavigate();
  const { signup, loginWithGoogle } = useAuth();
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [focusField, setFocusField] = useState(null);

  /* Character states */
  const [isPurpleBlinking, setIsPurpleBlinking] = useState(false);
  const [isBlackBlinking, setIsBlackBlinking] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isPurpleHiding, setIsPurpleHiding] = useState(false);
  const [isPurplePeeking, setIsPurplePeeking] = useState(false);

  const [mouse, setMouse] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMove = (e) => setMouse({ x: e.clientX, y: e.clientY });
    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, []);

  /* Purple random blink */
  useEffect(() => {
    let t;
    const scheduleBlink = () => {
      t = setTimeout(() => {
        setIsPurpleBlinking(true);
        setTimeout(() => { setIsPurpleBlinking(false); scheduleBlink(); }, 150);
      }, 3000 + Math.random() * 4000);
    };
    scheduleBlink();
    return () => clearTimeout(t);
  }, []);

  /* Black random blink */
  useEffect(() => {
    let t;
    const scheduleBlink = () => {
      t = setTimeout(() => {
        setIsBlackBlinking(true);
        setTimeout(() => { setIsBlackBlinking(false); scheduleBlink(); }, 150);
      }, 4000 + Math.random() * 5000);
    };
    scheduleBlink();
    return () => clearTimeout(t);
  }, []);

  /* Typing state */
  const typingTimerRef = useRef(null);
  const handleFieldFocus = (field) => {
    setFocusField(field);
    setIsTyping(true);
  };
  const handleFieldBlur = () => {
    setFocusField(null);
    setIsTyping(false);
  };
  const handleTyping = (field, val) => {
    setFormData(f => ({ ...f, [field]: val }));
    setIsTyping(true);
    clearTimeout(typingTimerRef.current);
    typingTimerRef.current = setTimeout(() => setIsTyping(false), 800);
  };

  /* Password — purple hides/peeks */
  const handlePasswordFocus = () => {
    setFocusField('pw');
    setIsPurpleHiding(true);
    setIsPurplePeeking(false);
  };
  const handlePasswordBlur = () => {
    setFocusField(null);
    setIsPurpleHiding(false);
    setIsPurplePeeking(false);
  };
  const handleTogglePassword = () => {
    const next = !showPw;
    setShowPw(next);
    if (next) { setIsPurplePeeking(true); setIsPurpleHiding(false); }
    else       { setIsPurplePeeking(false); setIsPurpleHiding(true); }
  };

  /* Body lean */
  const leftWidth = window.innerWidth * 0.55;
  const dx = mouse.x - leftWidth / 2;
  const bodySkew = Math.max(-6, Math.min(6, -dx / 120));
  const faceOffsetX = Math.max(-15, Math.min(15, dx / 20));

  /* Submit */
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      await signup(formData.email, formData.password, formData.name);
      toast.success('Account created! Welcome to SocialEntangler.');
    } catch (error) {
      let msg = 'Signup failed';
      if (error.code) {
        switch (error.code) {
          case 'auth/email-already-in-use': msg = 'Email is already in use.'; break;
          case 'auth/invalid-email':        msg = 'Invalid email address.'; break;
          case 'auth/weak-password':        msg = 'Password should be at least 6 characters.'; break;
          default:                          msg = error.message;
        }
      }
      toast.error(msg);
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
    try { setLoading(true); await loginWithGoogle(); toast.success('Account created!'); }
    catch (_) { setLoading(false); }
  };

  const inp = (field) => ({
    width: '100%', padding: '10px 14px',
    border: `1.5px solid ${focusField === field ? '#6C3FF5' : '#d1d5db'}`,
    borderRadius: '7px', fontSize: '14px', color: '#111827',
    outline: 'none', background: '#fff', transition: 'border-color .18s, box-shadow .18s',
    boxSizing: 'border-box',
    boxShadow: focusField === field ? '0 0 0 3px rgba(108,63,245,0.12)' : 'none',
  });

  const purpleHeight = isPurplePeeking ? 330 : isPurpleHiding ? 80 : 370;
  const purpleTranslateX = isPurpleHiding ? 40 : 0;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50,
      display: 'flex',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      overflow: 'hidden', background: '#fff',
    }}>

      {/* ══ LEFT PANEL — white + animated characters ══ */}
      <div style={{
        flex: '0 0 55%', background: '#fffffb',
        position: 'relative', display: 'flex',
        flexDirection: 'column', overflow: 'hidden',
      }}>
        {/* Characters stage */}
        <div style={{
          position: 'absolute', bottom: 56, left: '52%',
          transform: 'translateX(-50%) scale(1.44)',
          transformOrigin: 'bottom center',
          width: 640, height: 420,
        }}>
          {/* Orange semi-circle */}
          <div style={{
            position: 'absolute', bottom: 0, left: 0, zIndex: 4,
            width: 258, height: 218, background: '#FF9B6B',
            borderRadius: '129px 129px 0 0',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 18, paddingTop: 28,
          }}>
            <div style={{ display: 'flex', gap: 26 }}>
              <Pupil size={16} maxDistance={7} pupilColor="#2D2D2D"
                forceLookX={isTyping ? 9 : undefined} forceLookY={isTyping ? -3 : undefined} />
              <Pupil size={16} maxDistance={7} pupilColor="#2D2D2D"
                forceLookX={isTyping ? 9 : undefined} forceLookY={isTyping ? -3 : undefined} />
            </div>
            <div style={{ width: 46, height: 3, background: 'rgba(255,255,255,0.65)', borderRadius: 2 }} />
          </div>

          {/* Purple rectangle */}
          <div style={{
            position: 'absolute', bottom: 0, left: 148, zIndex: 1,
            width: 195, height: purpleHeight, background: '#6C3FF5',
            borderRadius: '22px 22px 0 0',
            transition: 'height 0.4s cubic-bezier(.4,0,.2,1), transform 0.4s cubic-bezier(.4,0,.2,1)',
            transform: `translateX(${purpleTranslateX}px) skewX(${bodySkew}deg)`,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'flex-start', paddingTop: 32, overflow: 'hidden',
          }}>
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `translateX(${faceOffsetX * 0.3}px)`, transition: 'transform 0.1s ease',
            }}>
              <div style={{ display: 'flex', gap: 18, marginBottom: 13 }}>
                <EyeBall size={40} pupilSize={15} maxDistance={9}
                  eyeColor="white" pupilColor="#2D2D2D" isBlinking={isPurpleBlinking}
                  forceLookX={isTyping ? 12 : isPurplePeeking ? 5 : undefined}
                  forceLookY={isTyping ? -5 : isPurplePeeking ? -10 : undefined} />
                <EyeBall size={40} pupilSize={15} maxDistance={9}
                  eyeColor="white" pupilColor="#2D2D2D" isBlinking={isPurpleBlinking}
                  forceLookX={isTyping ? 12 : isPurplePeeking ? 5 : undefined}
                  forceLookY={isTyping ? -5 : isPurplePeeking ? -10 : undefined} />
              </div>
              <div style={{ width: 40, height: 3, background: 'rgba(255,255,255,0.5)', borderRadius: 2 }} />
            </div>
          </div>

          {/* Black rectangle */}
          <div style={{
            position: 'absolute', bottom: 0, left: 308, zIndex: 2,
            width: 132, height: 318, background: '#2D2D2D',
            borderRadius: '18px 18px 0 0',
            display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 36,
          }}>
            <div style={{ display: 'flex', gap: 14, marginBottom: 11 }}>
              <EyeBall size={32} pupilSize={12} maxDistance={7}
                eyeColor="white" pupilColor="#6C3FF5" isBlinking={isBlackBlinking}
                forceLookX={isTyping ? -10 : undefined} forceLookY={isTyping ? -3 : undefined} />
              <EyeBall size={32} pupilSize={12} maxDistance={7}
                eyeColor="white" pupilColor="#6C3FF5" isBlinking={isBlackBlinking}
                forceLookX={isTyping ? -10 : undefined} forceLookY={isTyping ? -3 : undefined} />
            </div>
            <div style={{ width: 30, height: 2, background: 'rgba(255,255,255,0.25)', borderRadius: 1 }} />
          </div>

          {/* Yellow rounded rectangle */}
          <div style={{
            position: 'absolute', bottom: 0, left: 415, zIndex: 3,
            width: 165, height: 248, background: '#E8D754',
            borderRadius: '83px 83px 0 0',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'flex-start', paddingTop: 42, gap: 15,
          }}>
            <div style={{ display: 'flex', gap: 20 }}>
              <Pupil size={15} maxDistance={6} pupilColor="#2D2D2D"
                forceLookX={isTyping ? -7 : undefined} forceLookY={isTyping ? -2 : undefined} />
              <Pupil size={15} maxDistance={6} pupilColor="#2D2D2D"
                forceLookX={isTyping ? -7 : undefined} forceLookY={isTyping ? -2 : undefined} />
            </div>
            <div style={{ width: 38, height: 3, background: 'rgba(45,45,45,0.3)', borderRadius: 2 }} />
          </div>
        </div>

        {/* Footer links */}
        <div style={{
          position: 'absolute', bottom: 16, left: 0, right: 0,
          display: 'flex', justifyContent: 'center', gap: 20,
          fontSize: '11.5px', color: '#9ca3af',
        }}>
          <Link to="/terms" style={{ color: '#9ca3af', textDecoration: 'none' }}
            onMouseEnter={(e) => e.target.style.color = '#6b7280'}
            onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Terms</Link>
          <Link to="/privacy" style={{ color: '#9ca3af', textDecoration: 'none' }}
            onMouseEnter={(e) => e.target.style.color = '#6b7280'}
            onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Privacy</Link>
          <Link to="/security" style={{ color: '#9ca3af', textDecoration: 'none' }}
            onMouseEnter={(e) => e.target.style.color = '#6b7280'}
            onMouseLeave={(e) => e.target.style.color = '#9ca3af'}>Security</Link>
        </div>
      </div>

      {/* ══ RIGHT PANEL — white signup form ══ */}
      <div style={{
        flex: '0 0 45%', background: '#fffffb',
        display: 'flex', flexDirection: 'column',
        justifyContent: 'center', alignItems: 'center',
        padding: '40px 64px',
        boxSizing: 'border-box', overflowY: 'auto',
        position: 'relative',
      }}>
        {/* Logo — pinned to top so form is truly centered */}
        <div style={{ position: 'absolute', top: '40px', left: '64px', right: '64px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <SocialEntanglerLogo />
          <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" /></svg>
            Back to home
          </button>
        </div>

        <div style={{ maxWidth: '360px', width: '100%' }}>

          <h1 style={{ fontSize: '26px', fontWeight: '700', color: '#111827', marginBottom: '6px', letterSpacing: '-0.5px' }}>
            Create your account
          </h1>
          <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '20px' }}>
            Start scheduling your content today
          </p>

          {/* Google at top */}
          <button onClick={handleGoogleSignup} disabled={loading}
            style={{ width: '100%', padding: '10px 14px', background: '#fff', border: '1.5px solid #d1d5db', borderRadius: '7px', color: '#374151', fontSize: '14px', fontWeight: '500', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', transition: 'border-color .18s, box-shadow .18s', marginBottom: '16px' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#6C3FF5'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(108,63,245,0.08)'; }}
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
            {/* Name */}
            <div style={{ marginBottom: '14px' }}>
              <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Full Name</label>
              <input type="text" autoComplete="name" required placeholder="John Doe"
                value={formData.name}
                onChange={(e) => handleTyping('name', e.target.value)}
                onFocus={() => handleFieldFocus('name')}
                onBlur={handleFieldBlur}
                style={inp('name')}
              />
            </div>

            {/* Email */}
            <div style={{ marginBottom: '14px' }}>
              <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Email</label>
              <input type="email" autoComplete="email" required placeholder="you@example.com"
                value={formData.email}
                onChange={(e) => handleTyping('email', e.target.value)}
                onFocus={() => handleFieldFocus('email')}
                onBlur={handleFieldBlur}
                style={inp('email')}
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '13.5px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>Password</label>
              <div style={{ position: 'relative' }}>
                <input type={showPw ? 'text' : 'password'} autoComplete="new-password" required placeholder="Min. 6 characters"
                  value={formData.password}
                  onChange={(e) => handleTyping('password', e.target.value)}
                  onFocus={handlePasswordFocus}
                  onBlur={handlePasswordBlur}
                  style={{ ...inp('pw'), paddingRight: '40px' }}
                />
                <button type="button" onClick={handleTogglePassword}
                  style={{ position: 'absolute', right: '11px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 0, display: 'flex', alignItems: 'center' }}>
                  {showPw
                    ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  }
                </button>
              </div>
            </div>

            {/* Submit */}
            <button type="submit" disabled={loading}
              style={{
                width: '100%', padding: '11px',
                background: '#6C3FF5', border: 'none', borderRadius: '7px',
                color: '#fff', fontSize: '15px', fontWeight: '600',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
                transition: 'background .2s, box-shadow .2s',
                boxShadow: '0 4px 14px rgba(108,63,245,0.4)',
                marginBottom: '16px',
              }}
              onMouseEnter={(e) => { if (!loading) { e.target.style.background = '#5a32d4'; e.target.style.boxShadow = '0 6px 18px rgba(108,63,245,0.5)'; } }}
              onMouseLeave={(e) => { e.target.style.background = '#6C3FF5'; e.target.style.boxShadow = '0 4px 14px rgba(108,63,245,0.4)'; }}
            >
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p style={{ textAlign: 'center', fontSize: '13.5px', color: '#6b7280' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: '#6C3FF5', fontWeight: '600', textDecoration: 'none' }}
              onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
              onMouseLeave={(e) => e.target.style.textDecoration = 'none'}>
              Sign in
            </Link>
          </p>

        </div>
      </div>
    </div>
  );
};

export default SignupV4;
