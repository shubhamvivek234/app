import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from '@/components/ui/sonner';
import '@/App.css';
import { AuthProvider, useAuth } from '@/context/AuthContext';

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
import Onboarding from '@/pages/Onboarding';
import OnboardingConnect from '@/pages/OnboardingConnect';
import OnboardingPricing from '@/pages/OnboardingPricing';
import SubscriptionExpired from '@/pages/SubscriptionExpired';
import ApiKeys from '@/pages/ApiKeys';
import AgentDocs from '@/pages/AgentDocs';
import HashtagGroups from '@/pages/HashtagGroups';
import PublicCalendar from '@/pages/PublicCalendar';
import Analytics from '@/pages/Analytics';
import MediaLibrary from '@/pages/MediaLibrary';
import RecurringPosts from '@/pages/RecurringPosts';
import BulkUpload from '@/pages/BulkUpload';
import ApprovalQueue from '@/pages/ApprovalQueue';
import ThreadBuilder from '@/pages/ThreadBuilder';
import InstagramGridPlanner from '@/pages/InstagramGridPlanner';
import Inbox from '@/pages/Inbox';
import TeamMembers from '@/pages/TeamMembers';
import AcceptInvite from '@/pages/AcceptInvite';
import CookieConsent from '@/components/CookieConsent';

const PrivateRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
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
  if (!user.onboarding_completed) {
    // Allow them to be on onboarding pages
    if (path.startsWith('/onboarding')) {
      return children;
    }
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

  // If onboarding not completed, redirect to onboarding
  if (!user.onboarding_completed) {
    return <Navigate to="/onboarding" />;
  }

  return children;
};

const PublicRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  if (!user) {
    return children;
  }

  // If user is authenticated
  if (user) {
    if (user.onboarding_completed) {
      if (user.subscription_status === 'free') {
        return <Navigate to="/onboarding/pricing" />;
      }
      return <Navigate to="/dashboard" />;
    } else {
      return <Navigate to="/onboarding" />;
    }
  }

  return children;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="App">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/agent-docs" element={<AgentDocs />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/oauth/callback" element={<OAuthCallback />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/accept-invite" element={<AcceptInvite />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route
              path="/onboarding"
              element={
                <PrivateRoute>
                  <Onboarding />
                </PrivateRoute>
              }
            />
            <Route
              path="/onboarding/connect"
              element={
                <PrivateRoute>
                  <OnboardingConnect />
                </PrivateRoute>
              }
            />
            <Route
              path="/onboarding/pricing"
              element={
                <PrivateRoute>
                  <OnboardingPricing />
                </PrivateRoute>
              }
            />
            <Route
              path="/login"
              element={
                <PublicRoute>
                  <Login />
                </PublicRoute>
              }
            />
            <Route
              path="/signup"
              element={
                <PublicRoute>
                  <Signup />
                </PublicRoute>
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
              path="/create"
              element={
                <PrivateRoute>
                  <CreatePost />
                </PrivateRoute>
              }
            />
            <Route
              path="/create/:type"
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
              path="/content"
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
              path="/subscription-expired"
              element={
                <PrivateRoute>
                  <SubscriptionExpired />
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
              path="/settings"
              element={
                <PrivateRoute>
                  <Settings />
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
              path="/hashtags"
              element={
                <PrivateRoute>
                  <HashtagGroups />
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
              path="/media"
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
              path="/approvals"
              element={
                <PrivateRoute>
                  <ApprovalQueue />
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
              path="/tools/instagram-grid"
              element={
                <PrivateRoute>
                  <InstagramGridPlanner />
                </PrivateRoute>
              }
            />
            {/* Public route — no auth required */}
            <Route path="/calendar/public/:token" element={<PublicCalendar />} />
          </Routes>
          <Toaster />
          <CookieConsent />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;