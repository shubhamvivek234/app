import React from 'react';
import { Link } from 'react-router-dom';

const Terms = () => {
  return (
    <div className="min-h-screen bg-white">
      <nav className="border-b border-border backdrop-blur-md bg-white/80 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="text-2xl font-semibold text-slate-900">SocialSync</Link>
            <Link to="/" className="text-slate-600 hover:text-slate-900">Back to Home</Link>
          </div>
        </div>
      </nav>
      
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-4xl font-semibold tracking-tight text-slate-900 mb-8">Terms of Service</h1>
        
        <div className="prose prose-slate max-w-none">
          <p className="text-lg text-slate-600 mb-8">Last updated: February 10, 2026</p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">1. Acceptance of Terms</h2>
          <p className="text-slate-700 mb-4">
            By accessing or using SocialSync, you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our service.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">2. Description of Service</h2>
          <p className="text-slate-700 mb-4">
            SocialSync provides a social media scheduling platform that allows users to manage and schedule posts across multiple social media platforms including Twitter/X, Instagram, and LinkedIn.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">3. User Accounts</h2>
          <p className="text-slate-700 mb-4">
            You are responsible for maintaining the confidentiality of your account credentials and for all activities that occur under your account. You must immediately notify us of any unauthorized use of your account.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">4. Subscription and Billing</h2>
          <p className="text-slate-700 mb-4">
            Subscriptions are billed in advance on a monthly or yearly basis. All fees are non-refundable except as required by law. You can cancel your subscription at any time through your account settings.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">5. Content Guidelines</h2>
          <p className="text-slate-700 mb-4">
            You are solely responsible for the content you post through SocialSync. You must not post content that is illegal, offensive, or violates the terms of service of the social media platforms you are posting to.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">6. Social Media Platform Compliance</h2>
          <p className="text-slate-700 mb-4">
            You agree to comply with all terms of service and policies of the social media platforms (Twitter/X, Instagram, LinkedIn) that you connect to SocialSync. We are not responsible for any violations or consequences arising from your use of these platforms.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">7. Service Modifications</h2>
          <p className="text-slate-700 mb-4">
            We reserve the right to modify or discontinue the service at any time with or without notice. We will not be liable to you or any third party for any modification, suspension, or discontinuance of the service.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">8. Limitation of Liability</h2>
          <p className="text-slate-700 mb-4">
            SocialSync is provided "as is" without warranties of any kind. We shall not be liable for any damages arising from your use of the service, including but not limited to direct, indirect, incidental, or consequential damages.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">9. Termination</h2>
          <p className="text-slate-700 mb-4">
            We reserve the right to terminate or suspend your account at any time for any reason, including violation of these Terms of Service.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">10. Contact Information</h2>
          <p className="text-slate-700 mb-4">
            If you have any questions about these Terms of Service, please contact us at support@socialsync.com.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Terms;