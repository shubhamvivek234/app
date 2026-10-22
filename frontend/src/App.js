import React, { Component } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import '@/App.css';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { ThemeProvider, useTheme } from '@/context/ThemeContext';
import BrandMarkLoader from '@/components/BrandMarkLoader';

// Pages (Outreach + Auth + Legal/Workspace only; legacy social-scheduler pages hidden)
import Login from '@/pages/Login';
import Signup from '@/pages/Signup';
import ForgotPassword from '@/pages/ForgotPassword';
import AuthCallback from '@/pages/AuthCallback';
import OAuthCallback from '@/pages/OAuthCallback';
import VerifyEmail from '@/pages/VerifyEmail';
import Terms from '@/pages/Terms';
import Privacy from '@/pages/Privacy';
import DataDeletion from '@/pages/DataDeletion';
import RefundPolicy from '@/pages/RefundPolicy';
import Contact from '@/pages/Contact';
import AcceptInvite from '@/pages/AcceptInvite';
import MagicLogin from '@/pages/MagicLogin';
import CookieConsent from '@/components/CookieConsent';

const OutreachApp = React.lazy(() => import('@/outreach/OutreachApp'));

// FE-4: Catch render errors so the entire app doesn't crash to a white screen
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error('App error boundary caught:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen text-center p-8">
          <h1 className="text-2xl font-semibold mb-2">Something went wrong</h1>
          <p className="text-muted-foreground mb-4">Please refresh the page or contact support if the problem persists.</p>
          <button className="underline text-sm" onClick={() => this.setState({ hasError: false, error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const AuthRecoveryScreen = () => {
  const { authIssue, retryProfileSync, loading } = useAuth();

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background text-center p-8">
      <h1 className="text-2xl font-semibold mb-2">We are reconnecting your session</h1>
      <p className="text-muted-foreground mb-6 max-w-md">
        {authIssue?.message || 'You are signed in, but the app server is taking a moment to catch up.'}
      </p>
      <button
        className="px-4 py-2 rounded-md bg-foreground text-background text-sm font-medium disabled:opacity-60"
        disabled={loading}
        onClick={() => retryProfileSync()}
      >
        {loading ? 'Retrying...' : 'Retry now'}
      </button>
    </div>
  );
};

const PrivateRoute = ({ children }) => {
  const { user, loading, firebaseUser, token, authIssue } = useAuth();
  const hasPendingSession = Boolean((firebaseUser || token) && !user);

  if (loading || hasPendingSession) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <BrandMarkLoader />
      </div>
    );
  }

  if (authIssue) {
    return <AuthRecoveryScreen />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

const PublicRoute = ({ children }) => {
  const { user, loading, firebaseUser, token, authIssue } = useAuth();
  const location = useLocation();
  const hasPendingSession = Boolean((firebaseUser || token) && !user);

  if (loading || hasPendingSession) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <BrandMarkLoader />
      </div>
    );
  }

  if (authIssue) {
    return <AuthRecoveryScreen />;
  }

  if (!user) {
    return children;
  }

  const returnTo = location.state?.returnTo;
  if (typeof returnTo === 'string' && (returnTo.startsWith('/outreach') || returnTo.startsWith('/accept-invite'))) {
    return <Navigate to={returnTo} replace />;
  }
  return <Navigate to="/outreach" replace />;
};

const ThemeApplier = () => {
  const { isDarkMode } = useTheme();
  const { pathname } = useLocation();

  React.useEffect(() => {
    const publicRoutes = ['/login', '/signup', '/forgot-password', '/verify-email', '/terms', '/privacy', '/data-deletion', '/refund', '/contact', '/auth/callback', '/oauth/callback', '/accept-invite', '/magic-login', '/resources/social-media-image-guide', '/resources/social-media-video-guide'];
    const isPublicRoute = pathname === '/' || 
                        publicRoutes.some(route => pathname === route || pathname.startsWith(route + '/'));

    if (isDarkMode && !isPublicRoute) {
      document.documentElement.classList.add('dark');
      document.body.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.body.classList.remove('dark');
    }
  }, [isDarkMode, pathname]);

  return null;
}

function App() {
  return (
<ErrorBoundary>
        <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ThemeApplier />
          <div className="App flex flex-col min-h-screen bg-background text-foreground transition-colors duration-300">
            <React.Suspense fallback={<BrandMarkLoader />}>
            <Routes>
              {/* Root & Auth routes — redirect authenticated users to /outreach */}
              <Route path="/" element={<Navigate to="/outreach" replace />} />
              <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
              <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
              <Route path="/forgot-password" element={<PublicRoute><ForgotPassword /></PublicRoute>} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/refund" element={<RefundPolicy />} />
              <Route path="/contact" element={<Contact />} />
              <Route path="/data-deletion" element={<DataDeletion />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/oauth/callback" element={<OAuthCallback />} />
              <Route path="/accept-invite/:token" element={<AcceptInvite />} />
              <Route path="/magic-login/:token" element={<MagicLogin />} />

              {/* Outreach application routes */}
              <Route
                path="/outreach/*"
                element={
                  <PrivateRoute>
                    <OutreachApp />
                  </PrivateRoute>
                }
              />

              {/* Convenience Outreach deep-link aliases; all legacy social-scheduler routes hidden */}
              <Route path="/campaigns" element={<Navigate to="/outreach/campaigns" replace />} />
              <Route path="/leads" element={<Navigate to="/outreach/leads" replace />} />
              <Route path="/inbox" element={<Navigate to="/outreach/inbox" replace />} />
              <Route path="/analytics" element={<Navigate to="/outreach/analytics" replace />} />
              <Route path="/settings" element={<Navigate to="/outreach/settings" replace />} />
              <Route path="/billing" element={<Navigate to="/outreach/settings?tab=billing" replace />} />
              <Route path="/team" element={<Navigate to="/outreach/settings?tab=team" replace />} />
              <Route path="/accounts" element={<Navigate to="/outreach/settings?tab=senders" replace />} />

              {/* Catch-all: hide any legacy social-scheduler paths by redirecting to /outreach */}
              <Route path="*" element={<Navigate to="/outreach" replace />} />
            </Routes>
            </React.Suspense>
            <Toaster />
            <CookieConsent />
          </div>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
    </ErrorBoundary>
  );
}
export default App;
