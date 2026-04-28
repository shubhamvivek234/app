import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import UnravlerLogo from '@/components/UnravlerLogo';
import TurnstileWidget from '@/components/TurnstileWidget';

const LoginV1 = () => {
  const navigate = useNavigate();
  const { login, loginWithGoogle } = useAuth();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [loading, setLoading] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState(null);

  // Add Google Fonts
  useEffect(() => {
    const link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);

    try {
      await login(formData.email, formData.password, turnstileToken);
      toast.success('Welcome back!');
    } catch (error) {
      let errorMessage = 'Login failed';
      if (error.code) {
        switch (error.code) {
          case 'auth/invalid-email':
            errorMessage = 'Invalid email address.';
            break;
          case 'auth/user-disabled':
            errorMessage = 'User account is disabled.';
            break;
          case 'auth/user-not-found':
            errorMessage = 'No user found with this email.';
            break;
          case 'auth/wrong-password':
            errorMessage = 'Incorrect password.';
            break;
          default:
            errorMessage = error.message;
        }
      }
      toast.error(errorMessage);
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);
      await loginWithGoogle();
      // Don't reset loading here - let onAuthStateChanged handle it
      // toast.success is shown after backend profile loads
    } catch (error) {
      setLoading(false);
      // Error is already handled and toasted in AuthContext
    }
  };

  return (
    <div className="login-root">
      <style>{`
        .login-root {
          font-family: 'Plus Jakarta Sans', sans-serif;
          background: #fff;
          color: #1a1a2e;
          min-height: 100vh;
          display: flex;
          overflow: hidden;
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 50;
        }

        .login-root *, .login-root *::before, .login-root *::after {
          box-sizing: border-box;
        }

        /* ── LEFT ── */
        .left {
          flex: 0 0 46%;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 48px;
          background: #fff;
          position: relative;
          z-index: 2;
        }

        .form-wrap {
          width: 100%;
          max-width: 360px;
        }

        .brand-container {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 40px;
          width: 100%;
        }

        .back-home {
          font-size: 13px;
          font-weight: 500;
          color: #8a8fa8;
          display: flex;
          align-items: center;
          gap: 6px;
          text-decoration: none;
          transition: color 0.2s;
          background: none;
          border: none;
          padding: 0;
          cursor: pointer;
        }

        .back-home:hover {
          color: #5b6ef5;
        }

        .login-root h1 {
          font-family: 'Sora', sans-serif;
          font-size: 26px;
          font-weight: 600;
          letter-spacing: -0.5px;
          margin-bottom: 8px;
          color: #1a1a2e;
        }

        .sub {
          color: #8a8fa8;
          font-size: 14px;
          margin-bottom: 32px;
        }

        .btn-google {
          width: 100%;
          padding: 12px 16px;
          background: #f9f9f7;
          border: 1px solid rgba(0,0,0,0.08);
          border-radius: 10px;
          color: #1a1a2e;
          font-family: inherit;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          transition: border-color .2s, background .2s;
          margin-bottom: 24px;
        }

        .btn-google:hover {
          border-color: rgba(0,0,0,.18);
          background: #f0f0eb;
        }

        .divider {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 24px;
          color: #8a8fa8;
          font-size: 12px;
          letter-spacing: .05em;
          text-transform: uppercase;
        }

        .divider::before, .divider::after {
          content: '';
          flex: 1;
          height: 1px;
          background: rgba(0,0,0,0.08);
        }

        .field {
          margin-bottom: 16px;
        }

        .login-root label {
          display: block;
          font-size: 13px;
          font-weight: 500;
          color: #4a4f66;
          margin-bottom: 7px;
        }

        .login-root input[type="email"], .login-root input[type="password"] {
          width: 100%;
          padding: 11px 14px;
          background: #f9f9f7;
          border: 1px solid rgba(0,0,0,0.08);
          border-radius: 10px;
          color: #1a1a2e;
          font-family: inherit;
          font-size: 14px;
          outline: none;
          transition: border-color .2s, box-shadow .2s;
        }

        .login-root input:focus {
          border-color: #5b6ef5;
          box-shadow: 0 0 0 3px rgba(91,110,245,.15);
        }

        .login-root input::placeholder {
          color: #8a8fa8;
        }

        .forgot {
          display: block;
          text-align: right;
          font-size: 12px;
          color: #5b6ef5;
          text-decoration: none;
          margin-top: 6px;
          opacity: .85;
        }

        .btn-submit {
          width: 100%;
          padding: 13px;
          background: linear-gradient(135deg, #5b6ef5, #8b5cf6);
          border: none;
          border-radius: 10px;
          color: #fff;
          font-family: inherit;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          margin-top: 20px;
          transition: opacity .2s, transform .15s;
        }

        .btn-submit:hover:not(:disabled) {
          opacity: .9;
          transform: translateY(-1px);
        }
        
        .btn-submit:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .signup-line {
          text-align: center;
          font-size: 13px;
          color: #8a8fa8;
          margin-top: 20px;
        }

        .signup-line a {
          color: #5b6ef5;
          text-decoration: none;
          font-weight: 500;
        }

        /* ── RIGHT ── */
        .right {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: #fff;
          position: relative;
          overflow: hidden;
        }

        .tagline {
          font-family: 'Sora', sans-serif;
          font-size: 21px;
          font-weight: 600;
          letter-spacing: -0.4px;
          color: #1a1a2e;
          margin-bottom: 6px;
          z-index: 10;
          text-align: center;
        }

        .tagline-sub {
          color: #8a8fa8;
          font-size: 13px;
          margin-bottom: 48px;
          z-index: 10;
          text-align: center;
        }

        /* ── ORBIT ── */
        .orbit-wrap {
          position: relative;
          width: 552px;
          height: 552px;
          z-index: 10;
        }

        .center-bolt {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%,-50%);
          display: flex;
          align-items: center;
          justify-content: center;
          line-height: 1;
          z-index: 20;
          width: 92px;
          height: 72px;
          filter: drop-shadow(0 10px 22px rgba(12,65,79,.14));
          user-select: none;
        }

        .center-bolt .brand-center-mark {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
        }

        .ring-track {
          position: absolute;
          top: 50%;
          left: 50%;
          border: none;
        }

        .ring-outer {
          width: 480px;
          height: 480px;
          margin-left: -240px;
          margin-top: -240px;
          animation: CW 80s linear infinite;
        }

        .ring-inner {
          width: 276px;
          height: 276px;
          margin-left: -138px;
          margin-top: -138px;
          animation: CCW 60s linear infinite;
        }

        @keyframes CW  { to { transform: rotate(360deg); } }
        @keyframes CCW { to { transform: rotate(-360deg); } }

        .ring-svg {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          overflow: visible;
          pointer-events: none;
        }

        .icon-pivot {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 0;
          height: 0;
        }

        .ring-outer .icon-wrap {
          position: absolute;
          width: 52px;
          height: 52px;
          top: -26px;
          left: 214px;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: CCW 80s linear infinite;
        }

        .ring-outer .icon-wrap svg {
          width: 52px;
          height: 52px;
          display: block;
          position: relative;
          z-index: 1;
        }

        .ring-inner .icon-wrap {
          position: absolute;
          width: 24px;
          height: 24px;
          top: -12px;
          left: 126px;
          display: flex;
          align-items: center;
          justify-content: center;
          animation: CW 60s linear infinite;
        }

        .ring-inner .icon-wrap svg {
          width: 24px;
          height: 24px;
          display: block;
          position: relative;
          z-index: 1;
        }

        .icon-mask {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%,-50%);
          border-radius: 50%;
          background: #fff;
          z-index: 0;
        }

        .ring-outer .icon-mask { width: 64px; height: 64px; }
        .ring-inner .icon-mask { width: 32px; height: 32px; }

        .ring-outer .p1 { transform: rotate(35deg); }
        .ring-outer .p2 { transform: rotate(80deg); }
        .ring-outer .p3 { transform: rotate(125deg); }
        .ring-outer .p4 { transform: rotate(170deg); }
        .ring-outer .p5 { transform: rotate(215deg); }
        .ring-outer .p6 { transform: rotate(260deg); }
        .ring-outer .p7 { transform: rotate(305deg); }
        .ring-outer .p8 { transform: rotate(350deg); }

        .ring-inner .p1 { transform: rotate(77deg); }
        .ring-inner .p2 { transform: rotate(167deg); }
        .ring-inner .p3 { transform: rotate(257deg); }
        .ring-inner .p4 { transform: rotate(347deg); }

        @keyframes snapGlow {
          0%, 100% { filter: drop-shadow(0 0 6px rgba(255,255,255,0.95)) drop-shadow(0 0 14px rgba(255,255,255,0.6)); }
          50%       { filter: none; }
        }
        @keyframes snapFill {
          0%, 100% { fill: #fff; }
          50%       { fill: #000; }
        }
        .snap-glow  { animation: snapGlow 2s ease-in-out infinite; }
        .snap-ghost { animation: snapFill 2s ease-in-out infinite; }
      `}</style>

      {/* ── LEFT PANEL ── */}
      <div className="left">
        <div className="form-wrap">
          <div className="brand-container">
            <UnravlerLogo />
            <button onClick={() => navigate('/')} className="back-home">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
              Back to home
            </button>
          </div>
          <h1>Welcome back</h1>
          <p className="sub">Sign in to your account to continue</p>

          <button className="btn-google" onClick={handleGoogleLogin}>
            <svg width="18" height="18" viewBox="0 0 48 48">
              <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.5 30.2 0 24 0 14.7 0 6.7 5.5 2.7 13.5l7.8 6C12.5 13.1 17.8 9.5 24 9.5z" />
              <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.5 2.9-2.2 5.4-4.7 7.1l7.4 5.7c4.3-4 6.1-9.9 6.1-16.8z" />
              <path fill="#FBBC05" d="M10.5 28.5a14.9 14.9 0 010-9.1l-7.8-6A24 24 0 000 24c0 3.9.9 7.5 2.7 10.6l7.8-6.1z" />
              <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.4-5.7c-2 1.4-4.6 2.2-7.8 2.2-6.2 0-11.5-3.6-13.5-9l-7.8 6C6.7 42.5 14.7 48 24 48z" />
            </svg>
            Continue with Google
          </button>

          <div className="divider">or continue with email</div>

          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                type="email"
                id="email"
                placeholder="you@example.com"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                type="password"
                id="password"
                placeholder="••••••••"
                required
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              />
              <Link to="/forgot-password" style={{ display: 'block', textAlign: 'right', fontSize: '12px', color: '#5b6ef5', textDecoration: 'none', marginTop: '6px', opacity: '.85' }}>
                Forgot password?
              </Link>
            </div>
            <TurnstileWidget onVerify={setTurnstileToken} />
            <button type="submit" className="btn-submit" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
            <p className="signup-line">Don't have an account? <Link to="/signup">Sign up free</Link></p>
          </form>
        </div>
      </div>

      {/* ── RIGHT PANEL ── */}
      <div className="right">
        <p className="tagline">Connect to all your Platform from one place</p>
        <p className="tagline-sub">Schedule, publish &amp; analyze across every platform</p>

        <div className="orbit-wrap">
          <div className="center-bolt" style={{ marginTop: '0' }}>
            <UnravlerLogo className="brand-center-mark" size="xl" showText={false} darkText />
          </div>

          {/* ════════ OUTER RING (CW 34s) ════════ */}
          <div className="ring-track ring-outer">
            <svg className="ring-svg" viewBox="0 0 400 400">
              <circle cx="200" cy="200" r="199" fill="none"
                stroke="rgba(190,195,215,0.8)" strokeWidth="1.5"
                strokeDasharray="89 68" strokeLinecap="round" />
            </svg>

            <div className="icon-pivot p1"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 0 1 .083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z" fill="#E60023" /></svg>
            </div></div>

            <div className="icon-pivot p2"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z" fill="#000" /></svg>
            </div></div>

            <div className="icon-pivot p3"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" fill="#0077B5" /></svg>
            </div></div>

            <div className="icon-pivot p4"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z" fill="#000" /></svg>
            </div></div>

            <div className="icon-pivot p5"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" fill="#FF0000" /></svg>
            </div></div>

            <div className="icon-pivot p6"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" fill="#1877F2" /></svg>
            </div></div>

            <div className="icon-pivot p7"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24">
                <defs><radialGradient id="ig" cx="30%" cy="107%" r="150%"><stop offset="0%" stopColor="#fdf497" /><stop offset="45%" stopColor="#fd5949" /><stop offset="60%" stopColor="#d6249f" /><stop offset="90%" stopColor="#285AEB" /></radialGradient></defs>
                <path fill="url(#ig)" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
              </svg>
            </div></div>

            <div className="icon-pivot p8"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg className="snap-glow" viewBox="0 0 24 24">
                <rect width="24" height="24" rx="5" fill="#FFFC00" />
                <path className="snap-ghost" transform="translate(4.8 4.8) scale(0.6)" d="M12.206.793c.99 0 4.347.276 5.93 3.821.529 1.193.403 3.219.299 4.847l-.003.06c-.012.18-.022.345-.03.51.075.045.203.09.401.09.3-.016.659-.12 1.033-.301.165-.088.344-.104.464-.104.182 0 .359.029.509.09.45.149.734.479.734.838.015.449-.39.839-1.213 1.168-.089.029-.209.075-.344.119-.45.135-1.139.36-1.333.81-.09.224-.061.524.12.868l.015.015c.06.136 1.526 3.475 4.791 4.014.255.044.435.27.42.509 0 .075-.015.149-.045.225-.24.569-1.273.988-3.146 1.271-.059.091-.12.375-.164.57-.029.179-.074.36-.134.553-.076.271-.27.405-.555.405h-.03c-.135 0-.313-.031-.538-.074-.36-.075-.765-.135-1.273-.135-.3 0-.599.015-.913.074-.6.104-1.123.464-1.723.884-.853.599-1.826 1.288-3.294 1.288-.06 0-.119-.015-.18-.015h-.149c-1.468 0-2.427-.675-3.279-1.288-.599-.42-1.107-.779-1.707-.884-.314-.045-.629-.074-.928-.074-.54 0-.958.089-1.288.149-.195.045-.36.074-.51.074-.42 0-.523-.224-.583-.42-.061-.192-.09-.389-.135-.567-.046-.181-.105-.494-.166-.57-1.918-.222-2.95-.642-3.189-1.226-.031-.063-.052-.15-.055-.225-.015-.243.165-.465.42-.509 3.264-.54 4.73-3.879 4.791-4.02l.016-.029c.18-.345.224-.645.119-.869-.195-.434-.884-.658-1.332-.809-.121-.029-.24-.074-.346-.119-1.107-.435-1.257-.9-1.197-1.169.09-.479.674-.793 1.168-.793.135 0 .27.029.405.074.42.194.826.299 1.168.299.234 0 .384-.06.465-.105l-.046-.569c-.098-1.626-.225-3.651.304-4.837C7.392 1.077 10.739.807 11.729.807l.419-.015h.06z" />
              </svg>
            </div></div>
          </div>

          {/* ════════ INNER RING (CCW 24s) ════════ */}
          <div className="ring-track ring-inner">
            <svg className="ring-svg" viewBox="0 0 230 230">
              <circle cx="115" cy="115" r="114" fill="none"
                stroke="rgba(190,195,215,0.8)" strokeWidth="1.5"
                strokeDasharray="130 51" strokeLinecap="round" />
            </svg>

            <div className="icon-pivot p1"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zm-9.67-4.148a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .785 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.15-1.668zm-1.25-9.817a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0L4.176 14.11a4.501 4.501 0 0 1-1.836-5.645zm16.554 3.855l-5.843-3.369 2.02-1.168a.076.076 0 0 1 .071 0l4.642 2.685a4.501 4.501 0 0 1-.694 8.115v-5.678a.79.79 0 0 0-.196-.585zm2.008-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.64-2.68a4.496 4.496 0 0 1 6.677 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.496 4.496 0 0 1 7.375-3.453l-.142.08-4.778 2.758a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z" fill="#10a37f" /></svg>
            </div></div>

            <div className="icon-pivot p2"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="12" fill="#00C4CC" />
                <text x="12" y="17" textAnchor="middle" fontFamily="Georgia,serif" fontWeight="bold" fontSize="16" fill="white">C</text>
              </svg>
            </div></div>

            <div className="icon-pivot p3"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24"><path d="M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19.01 7.38 20 6.18 20C4.98 20 4 19.01 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1z" fill="#F26522" /></svg>
            </div></div>

            <div className="icon-pivot p4"><div className="icon-wrap">
              <div className="icon-mask"></div>
              <svg viewBox="0 0 24 24">
                <path d="M12 12c0-3.314-2.686-6-6-6h6v6z" fill="#EA4335" />
                <path d="M12 12c3.314 0 6-2.686 6-6v6h-6z" fill="#4285F4" />
                <path d="M12 12c0 3.314 2.686 6 6 6h-6v-6z" fill="#FBBC05" />
                <path d="M12 12c-3.314 0-6 2.686-6 6v-6h6z" fill="#34A853" />
              </svg>
            </div></div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginV1;
