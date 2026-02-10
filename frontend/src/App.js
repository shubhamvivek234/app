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
import CalendarView from '@/pages/CalendarView';
import ContentLibrary from '@/pages/ContentLibrary';
import ConnectedAccounts from '@/pages/ConnectedAccounts';
import Billing from '@/pages/Billing';
import Settings from '@/pages/Settings';
import Terms from '@/pages/Terms';
import Privacy from '@/pages/Privacy';
import Onboarding from '@/pages/Onboarding';
import OnboardingConnect from '@/pages/OnboardingConnect';

const PrivateRoute = ({ children }) => {
  const { user } = useAuth();
  
  if (!user) {
    return <Navigate to="/login" />;
  }
  
  // Allow access to onboarding pages
  if (window.location.pathname.startsWith('/onboarding')) {
    return children;
  }
  
  // If onboarding not completed, redirect to onboarding
  if (!user.onboarding_completed) {
    return <Navigate to="/onboarding" />;
  }
  
  return children;
};

const PublicRoute = ({ children }) => {
  const { user } = useAuth();
  
  if (!user) {
    return children;
  }
  
  // If user is authenticated, check if onboarding is completed
  if (user.onboarding_completed) {
    return <Navigate to="/dashboard" />;
  } else {
    return <Navigate to="/onboarding" />;
  }
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="App">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/oauth/callback" element={<OAuthCallback />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
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
              path="/settings"
              element={
                <PrivateRoute>
                  <Settings />
                </PrivateRoute>
              }
            />
          </Routes>
          <Toaster />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;