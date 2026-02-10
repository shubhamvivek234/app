import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const VerifyEmail = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('verifying'); // verifying, success, error

  useEffect(() => {
    const verifyEmail = async () => {
      const token = searchParams.get('token');
      
      if (!token) {
        setStatus('error');
        return;
      }

      try {
        await axios.get(`${BACKEND_URL}/api/auth/verify-email?token=${token}`);
        setStatus('success');
        toast.success('Email verified successfully!');
      } catch (error) {
        setStatus('error');
        toast.error(error.response?.data?.detail || 'Verification failed');
      }
    };

    verifyEmail();
  }, [searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="max-w-md w-full bg-white p-8 rounded-lg border border-border shadow-sm text-center">
        {status === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">Verifying your email...</h2>
            <p className="text-slate-600">Please wait while we verify your email address.</p>
          </>
        )}
        
        {status === 'success' && (
          <>
            <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">Email Verified!</h2>
            <p className="text-slate-600 mb-6">Your email has been successfully verified. You can now access all features.</p>
            <Button onClick={() => navigate('/dashboard')} className="w-full" data-testid="go-to-dashboard">
              Go to Dashboard
            </Button>
          </>
        )}
        
        {status === 'error' && (
          <>
            <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold text-slate-900 mb-2">Verification Failed</h2>
            <p className="text-slate-600 mb-6">The verification link is invalid or has expired.</p>
            <Button onClick={() => navigate('/login')} variant="outline" className="w-full" data-testid="back-to-login">
              Back to Login
            </Button>
          </>
        )}
      </div>
    </div>
  );
};

export default VerifyEmail;