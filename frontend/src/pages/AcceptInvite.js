import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import { checkInviteToken, acceptInviteToken } from '@/lib/api';

const ROLE_LABELS = {
  admin:  'Admin',
  member: 'Member',
  viewer: 'Viewer',
};

const ROLE_CAPABILITIES = {
  admin:  'manage team members, connect social accounts, create and publish posts',
  member: 'create, edit, and schedule posts for publication',
  viewer: 'view scheduled posts and analytics',
};

// ── Style constants ──────────────────────────────────────────────────────────
const ctaStyle = {
  width: '100%',
  padding: '13px',
  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
  border: 'none',
  borderRadius: '10px',
  color: '#fff',
  fontSize: '15px',
  fontWeight: 600,
  cursor: 'pointer',
  marginTop: '8px',
};

const inputStyle = {
  width: '100%',
  padding: '10px 14px',
  background: '#f9f9f7',
  border: '1px solid rgba(0,0,0,0.1)',
  borderRadius: '10px',
  fontSize: '14px',
  color: '#1a1a2e',
  outline: 'none',
  boxSizing: 'border-box',
};

const labelStyle = {
  display: 'block',
  fontSize: '13px',
  fontWeight: 500,
  color: '#4a4f66',
  marginBottom: '6px',
};

// ── Sub-components ────────────────────────────────────────────────────────────
const CenteredCard = ({ children }) => (
  <div style={{ minHeight: '100vh', background: '#f5f7f5', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
    <div style={{ width: '100%', maxWidth: '420px', background: '#fff', borderRadius: '16px', border: '1px solid #e5e7eb', padding: '40px', boxShadow: '0 4px 24px rgba(0,0,0,0.06)' }}>
      {children}
    </div>
  </div>
);

const FieldGroup = ({ children }) => <div style={{ marginBottom: '16px' }}>{children}</div>;

// ── Main component ────────────────────────────────────────────────────────────
const AcceptInvite = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, login, signup } = useAuth();

  const token = searchParams.get('token');

  const [pageState, setPageState] = useState('loading'); // loading | preview | accepted | error
  const [invite, setInvite] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [showForm, setShowForm] = useState(null); // null | 'login' | 'signup'
  const [formData, setFormData] = useState({ name: '', email: '', password: '' });
  const [submitting, setSubmitting] = useState(false);

  // ── Step 1: Load invite details ───────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setErrorMsg('No invite token found in this link.');
      setPageState('error');
      return;
    }
    checkInviteToken(token)
      .then((data) => {
        setInvite(data);
        setFormData((prev) => ({ ...prev, email: data.email }));
        // Default form shown based on whether user already has an account
        setShowForm(data.user_exists ? 'login' : 'signup');
        setPageState('preview');
      })
      .catch((err) => {
        setErrorMsg(err.response?.data?.detail || 'This invite link is invalid or has expired.');
        setPageState('error');
      });
  }, [token]);

  // ── Step 2: Accept invite once user is authenticated ─────────────────────
  const handleAccept = useCallback(async () => {
    try {
      await acceptInviteToken(token);
      setPageState('accepted');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to accept invite.');
    }
  }, [token]);

  useEffect(() => {
    if (pageState !== 'preview' || !user || !invite) return;

    if (user.email.toLowerCase() === invite.email.toLowerCase()) {
      // Logged-in user matches invite → auto-accept
      handleAccept();
    } else {
      // Email mismatch
      setErrorMsg(
        `You're logged in as ${user.email}, but this invite is for ${invite.email}. Please log out and use the correct account.`
      );
      setPageState('error');
    }
  }, [pageState, user, invite, handleAccept]);

  // ── Form handlers ─────────────────────────────────────────────────────────
  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(formData.email, formData.password);
      // AuthContext updates `user` → useEffect above fires → handleAccept()
    } catch {
      setSubmitting(false);
    }
  };

  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await signup(formData.email, formData.password, formData.name);
      // Same — auth state change → user → handleAccept()
    } catch {
      setSubmitting(false);
    }
  };

  // ── Render: loading ───────────────────────────────────────────────────────
  if (pageState === 'loading') {
    return (
      <CenteredCard>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
          <div style={{ width: 36, height: 36, border: '3px solid #e5e7eb', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <p style={{ color: '#6b7280', fontSize: '14px' }}>Loading invite…</p>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </CenteredCard>
    );
  }

  // ── Render: error ─────────────────────────────────────────────────────────
  if (pageState === 'error') {
    return (
      <CenteredCard>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
          <svg width="22" height="22" fill="none" stroke="#ef4444" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#1a1a2e', textAlign: 'center', marginBottom: '8px' }}>Invite Unavailable</h2>
        <p style={{ fontSize: '14px', color: '#6b7280', textAlign: 'center', marginBottom: '24px' }}>{errorMsg}</p>
        <Link to="/login" style={{ display: 'block', textAlign: 'center', color: '#6366f1', fontSize: '14px', fontWeight: 500 }}>
          Go to Login →
        </Link>
      </CenteredCard>
    );
  }

  // ── Render: accepted ──────────────────────────────────────────────────────
  if (pageState === 'accepted') {
    return (
      <CenteredCard>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#dcfce7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
          <svg width="22" height="22" fill="none" stroke="#16a34a" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#1a1a2e', textAlign: 'center', marginBottom: '8px' }}>You're in!</h2>
        <p style={{ fontSize: '14px', color: '#6b7280', textAlign: 'center', marginBottom: '28px' }}>
          You've joined <strong>{invite?.owner_name}'s</strong> workspace as{' '}
          <strong>{ROLE_LABELS[invite?.role] || invite?.role}</strong>.
        </p>
        <button onClick={() => navigate('/publish')} style={ctaStyle}>
          Go to Dashboard
        </button>
      </CenteredCard>
    );
  }

  // ── Render: preview (main state) ──────────────────────────────────────────
  const roleLabel = ROLE_LABELS[invite?.role] || invite?.role;
  const roleCap = ROLE_CAPABILITIES[invite?.role] || 'access the workspace';

  return (
    <div style={{ minHeight: '100vh', background: '#f5f7f5', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <div style={{ width: '100%', maxWidth: '460px' }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <span style={{ fontSize: '20px', fontWeight: 700, color: '#1a1a2e', letterSpacing: '-0.5px' }}>
            Social<span style={{ color: '#6366f1' }}>Entangler</span>
          </span>
        </div>

        {/* Invite card */}
        <div style={{ background: '#fff', borderRadius: '16px', border: '1px solid #e5e7eb', padding: '28px 32px', boxShadow: '0 4px 24px rgba(0,0,0,0.06)', marginBottom: '12px' }}>
          <h1 style={{ fontSize: '20px', fontWeight: 700, color: '#1a1a2e', marginBottom: '6px' }}>
            You've been invited
          </h1>
          <p style={{ fontSize: '14px', color: '#6b7280', marginBottom: '20px', lineHeight: 1.6 }}>
            <strong>{invite?.owner_name}</strong> has invited you to collaborate on their workspace.
          </p>

          {/* Role badge */}
          <div style={{ background: '#f8f9ff', border: '1px solid #e5e7fb', borderRadius: '10px', padding: '14px 18px', marginBottom: '24px' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#8a8fa8', marginBottom: '4px' }}>Your role</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span style={{ padding: '3px 12px', background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', color: '#fff', borderRadius: '20px', fontSize: '13px', fontWeight: 600 }}>
                {roleLabel}
              </span>
            </div>
            <div style={{ fontSize: '13px', color: '#6b7280' }}>You can {roleCap}.</div>
          </div>

          {/* Login form */}
          {showForm === 'login' && (
            <form onSubmit={handleLoginSubmit}>
              <FieldGroup>
                <label style={labelStyle}>Email</label>
                <input style={{ ...inputStyle, color: '#6b7280' }} type="email" value={formData.email} readOnly title="Email is pre-filled from the invite" />
              </FieldGroup>
              <FieldGroup>
                <label style={labelStyle}>Password</label>
                <input
                  style={inputStyle}
                  type="password"
                  required
                  placeholder="Enter your password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                />
              </FieldGroup>
              <button type="submit" disabled={submitting} style={{ ...ctaStyle, opacity: submitting ? 0.7 : 1 }}>
                {submitting ? 'Logging in…' : 'Log in & Accept Invite'}
              </button>
              <p style={{ textAlign: 'center', marginTop: '14px', fontSize: '13px', color: '#9ca3af' }}>
                New to SocialEntangler?{' '}
                <button type="button" onClick={() => setShowForm('signup')} style={{ color: '#6366f1', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}>
                  Create account
                </button>
              </p>
            </form>
          )}

          {/* Signup form */}
          {showForm === 'signup' && (
            <form onSubmit={handleSignupSubmit}>
              <FieldGroup>
                <label style={labelStyle}>Full Name</label>
                <input
                  style={inputStyle}
                  type="text"
                  required
                  placeholder="Your full name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </FieldGroup>
              <FieldGroup>
                <label style={labelStyle}>Email</label>
                <input style={{ ...inputStyle, color: '#6b7280' }} type="email" value={formData.email} readOnly title="Email is pre-filled from the invite" />
              </FieldGroup>
              <FieldGroup>
                <label style={labelStyle}>Password</label>
                <input
                  style={inputStyle}
                  type="password"
                  required
                  minLength={6}
                  placeholder="Create a password (min. 6 characters)"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                />
              </FieldGroup>
              <button type="submit" disabled={submitting} style={{ ...ctaStyle, opacity: submitting ? 0.7 : 1 }}>
                {submitting ? 'Creating account…' : 'Create Account & Accept Invite'}
              </button>
              <p style={{ textAlign: 'center', marginTop: '14px', fontSize: '13px', color: '#9ca3af' }}>
                Already have an account?{' '}
                <button type="button" onClick={() => setShowForm('login')} style={{ color: '#6366f1', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}>
                  Log in
                </button>
              </p>
            </form>
          )}
        </div>

        {/* Google note */}
        <p style={{ textAlign: 'center', fontSize: '12px', color: '#9ca3af', marginBottom: '8px' }}>
          Have a Google account?{' '}
          <Link to="/login" style={{ color: '#6366f1' }}>Log in at /login</Link> first, then reopen this invite link.
        </p>

        {/* Expiry */}
        {invite?.expires_at && (
          <p style={{ textAlign: 'center', fontSize: '12px', color: '#9ca3af' }}>
            Invite expires {new Date(invite.expires_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
          </p>
        )}
      </div>
    </div>
  );
};

export default AcceptInvite;
