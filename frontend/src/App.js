import React, { Component } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import '@/App.css';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { ThemeProvider, useTheme } from '@/context/ThemeContext';
import BrandMarkLoader from '@/components/BrandMarkLoader';

// Pages
import LandingPage from '@/pages/LandingPage';
import Login from '@/pages/Login';
import Signup from '@/pages/Signup';
import AuthCallback from '@/pages/AuthCallback';
import OAuthCallback from '@/pages/OAuthCallback';
import VerifyEmail from '@/pages/VerifyEmail';
import Dashboard from '@/pages/Dashboard';
import CreatePost from '@/pages/CreatePost';
import CreatePostForm from '@/pages/CreatePostForm';
import Publish from '@/pages/Publish';
import CalendarView from '@/pages/CalendarView';
import ContentLibrary from '@/pages/ContentLibrary';
import ConnectedAccounts from '@/pages/ConnectedAccounts';
import Billing from '@/pages/Billing';
import PaymentPage from '@/pages/PaymentPage';
import Settings from '@/pages/Settings';
import Terms from '@/pages/Terms';
import Privacy from '@/pages/Privacy';
import DataDeletion from '@/pages/DataDeletion';
import Onboarding from '@/pages/Onboarding';
import OnboardingConnect from '@/pages/OnboardingConnect';
import OnboardingPricing from '@/pages/OnboardingPricing';
import SubscriptionExpired from '@/pages/SubscriptionExpired';
import ApiKeys from '@/pages/ApiKeys';
import AgentDocs from '@/pages/AgentDocs';
import McpDocs from '@/pages/McpDocs';
import HashtagGroups from '@/pages/HashtagGroups';
import PublicCalendar from '@/pages/PublicCalendar';
import Analytics from '@/pages/Analytics';
import MediaLibrary from '@/pages/MediaLibrary';
import RecurringPosts from '@/pages/RecurringPosts';
import BulkUpload from '@/pages/BulkUpload';
import BulkVideoUpload from '@/pages/BulkVideoUpload';
import BulkUploadGuide from '@/pages/BulkUploadGuide';
import Timeslots from '@/pages/Timeslots';
import ApprovalQueue from '@/pages/ApprovalQueue';
import ThreadBuilder from '@/pages/ThreadBuilder';
import SocialTools from '@/pages/SocialTools';
import Inbox from '@/pages/Inbox';
import TeamMembers from '@/pages/TeamMembers';
import AcceptInvite from '@/pages/AcceptInvite';
import SocialMediaImageGuide from '@/pages/SocialMediaImageGuide';
import SocialMediaVideoGuide from '@/pages/SocialMediaVideoGuide';
import BulkCSVUpload from '@/pages/BulkCSVUpload';
import CookieConsent from '@/components/CookieConsent';

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

const PrivateRoute = ({ children, bypassOnboardingCheck = false }) => {
  const { user, loading, firebaseUser, token, authIssue } = useAuth();
  const hasPendingSession = Boolean((firebaseUser || token) && !user);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <BrandMarkLoader />
      </div>
    );
  }

  if (hasPendingSession && authIssue) {
    return <AuthRecoveryScreen />;
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  // Allow access to onboarding, payment, billing, and subscription-expired pages
  const path = window.location.pathname;
  if (path.startsWith('/onboarding') ||
    path.startsWith('/payment') ||
    path.startsWith('/billing') ||
    path === '/subscription-expired') {
    return children;
  }

  // Check subscription status
  if (user.subscription_status === 'expired') {
    return <Navigate to="/subscription-expired" />;
  }

  // Active subscribers always have full access — skip onboarding checks
  if (user.subscription_status === 'active') {
    return children;
  }

  // If onboarding not completed, redirect to main onboarding flow first
  if (!user.onboarding_completed && !bypassOnboardingCheck) {
    return <Navigate to="/onboarding" />;
  }

  // Redirect free users to pricing if they have completed onboarding but are still 'free'
  // and NOT already on the pricing or payment page
  if (user.subscription_status === 'free' && user.onboarding_completed) {
    if (path.startsWith('/onboarding/pricing') || path.startsWith('/payment')) {
      return children;
    }
    return <Navigate to="/onboarding/pricing" />;
  }

  return children;
};

const PublicRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <BrandMarkLoader />
      </div>
    );
  }

  if (!user) {
    return children;
  }

  // If user is authenticated, honour returnTo if present (e.g. from /mcp)
  const returnTo = location.state?.returnTo;
  if (user) {
    if (returnTo) {
      return <Navigate to={returnTo} />;
    }
    if (user.onboarding_completed) {
      if (user.subscription_status === 'free') {
        return <Navigate to="/onboarding/pricing" />;
      }
      return <Navigate to="/dashboard" />;
    }
    return <Navigate to="/onboarding" />;
  }

  return children;
};

const ThemeApplier = () => {
  const { isDarkMode } = useTheme();
  const { pathname } = useLocation();

  React.useEffect(() => {
    const publicRoutes = ['/login', '/signup', '/verify-email', '/terms', '/privacy', '/data-deletion', '/auth/callback', '/oauth/callback', '/accept-invite', '/resources/social-media-image-guide', '/resources/social-media-video-guide'];
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
            <Routes>
              {/* Public routes — redirect authenticated users to dashboard */}
              <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
              <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
              <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/data-deletion" element={<DataDeletion />} />
              <Route path="/resources/social-media-image-guide" element={<SocialMediaImageGuide />} />
              <Route path="/resources/social-media-video-guide" element={<SocialMediaVideoGuide />} />
              <Route path="/mcp" element={<McpDocs />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/oauth/callback" element={<OAuthCallback />} />
              <Route path="/accept-invite/:token" element={<AcceptInvite />} />

              {/* Private routes */}
              <Route
                path="/onboarding"
                element={
                  <PrivateRoute bypassOnboardingCheck={true}>
                    <Onboarding />
                  </PrivateRoute>
                }
              />
              <Route
                path="/onboarding/connect"
                element={
                  <PrivateRoute bypassOnboardingCheck={true}>
                    <OnboardingConnect />
                  </PrivateRoute>
                }
              />
              <Route
                path="/onboarding/pricing"
                element={
                  <PrivateRoute bypassOnboardingCheck={true}>
                    <OnboardingPricing />
                  </PrivateRoute>
                }
              />
              <Route
                path="/subscription-expired"
                element={
                  <PrivateRoute bypassOnboardingCheck={true}>
                    <SubscriptionExpired />
                  </PrivateRoute>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <PrivateRoute>
                    <Dashboard />
                  </PrivateRoute>
                }
              />
              <Route
                path="/analytics"
                element={
                  <PrivateRoute>
                    <Analytics />
                  </PrivateRoute>
                }
              />
              <Route
                path="/create-post"
                element={
                  <PrivateRoute>
                    <CreatePost />
                  </PrivateRoute>
                }
              />
              <Route
                path="/create-post/new"
                element={
                  <PrivateRoute>
                    <CreatePostForm />
                  </PrivateRoute>
                }
              />
              <Route
                path="/publish"
                element={
                  <PrivateRoute>
                    <Publish />
                  </PrivateRoute>
                }
              />
              <Route
                path="/calendar"
                element={
                  <PrivateRoute>
                    <CalendarView />
                  </PrivateRoute>
                }
              />
              <Route
                path="/content-library"
                element={
                  <PrivateRoute>
                    <ContentLibrary />
                  </PrivateRoute>
                }
              />
              <Route
                path="/accounts"
                element={
                  <PrivateRoute>
                    <ConnectedAccounts />
                  </PrivateRoute>
                }
              />
              <Route
                path="/billing"
                element={
                  <PrivateRoute>
                    <Billing />
                  </PrivateRoute>
                }
              />
              <Route
                path="/payment"
                element={
                  <PrivateRoute>
                    <PaymentPage />
                  </PrivateRoute>
                }
              />
              <Route
                path="/api-keys"
                element={
                  <PrivateRoute>
                    <ApiKeys />
                  </PrivateRoute>
                }
              />
              <Route
                path="/settings"
                element={
                  <PrivateRoute>
                    <Settings />
                  </PrivateRoute>
                }
              />
              <Route
                path="/agent-docs"
                element={
                  <PrivateRoute>
                    <AgentDocs />
                  </PrivateRoute>
                }
              />
              <Route
                path="/hashtags"
                element={
                  <PrivateRoute>
                    <HashtagGroups />
                  </PrivateRoute>
                }
              />
              <Route
                path="/media-library"
                element={
                  <PrivateRoute>
                    <MediaLibrary />
                  </PrivateRoute>
                }
              />
              <Route
                path="/recurring"
                element={
                  <PrivateRoute>
                    <RecurringPosts />
                  </PrivateRoute>
                }
              />
              <Route
                path="/bulk-upload"
                element={
                  <PrivateRoute>
                    <BulkUpload />
                  </PrivateRoute>
                }
              />
              <Route
                path="/bulk-video"
                element={
                  <PrivateRoute>
                    <BulkVideoUpload />
                  </PrivateRoute>
                }
              />
              <Route
                path="/bulk-upload-guide"
                element={
                  <PrivateRoute>
                    <BulkUploadGuide />
                  </PrivateRoute>
                }
              />
              <Route
                path="/bulk-csv"
                element={
                  <PrivateRoute>
                    <BulkCSVUpload />
                  </PrivateRoute>
                }
              />
              <Route
                path="/timeslots"
                element={
                  <PrivateRoute>
                    <Timeslots />
                  </PrivateRoute>
                }
              />
              <Route
                path="/approvals"
                element={
                  <PrivateRoute>
                    <ApprovalQueue />
                  </PrivateRoute>
                }
              />
              <Route
                path="/threads"
                element={
                  <PrivateRoute>
                    <ThreadBuilder />
                  </PrivateRoute>
                }
              />
              <Route
                path="/team"
                element={
                  <PrivateRoute>
                    <TeamMembers />
                  </PrivateRoute>
                }
              />
              <Route
                path="/inbox"
                element={
                  <PrivateRoute>
                    <Inbox />
                  </PrivateRoute>
                }
              />
              <Route
                path="/social-tools"
                element={
                  <PrivateRoute>
                    <SocialTools />
                  </PrivateRoute>
                }
              />
              {/* Public route — no auth required */}
              <Route path="/calendar/public/:token" element={<PublicCalendar />} />
              
              {/* Fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
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
