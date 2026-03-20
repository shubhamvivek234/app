import React from 'react';
import { Link } from 'react-router-dom';

const Privacy = () => {
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
        <h1 className="text-4xl font-semibold tracking-tight text-slate-900 mb-8">Privacy Policy</h1>
        
        <div className="prose prose-slate max-w-none">
          <p className="text-lg text-slate-600 mb-8">Last updated: February 10, 2026</p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">1. Information We Collect</h2>
          <p className="text-slate-700 mb-4">
            We collect information you provide directly to us, including:
          </p>
          <ul className="list-disc pl-6 text-slate-700 mb-4">
            <li>Account information (name, email, password)</li>
            <li>Social media account credentials and access tokens</li>
            <li>Content you create and schedule through our platform</li>
            <li>Payment information (processed securely by Stripe, Razorpay, or PayPal)</li>
          </ul>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">2. How We Use Your Information</h2>
          <p className="text-slate-700 mb-4">
            We use the information we collect to:
          </p>
          <ul className="list-disc pl-6 text-slate-700 mb-4">
            <li>Provide, maintain, and improve our services</li>
            <li>Process your transactions</li>
            <li>Send you technical notices and support messages</li>
            <li>Communicate with you about products, services, and events</li>
            <li>Monitor and analyze trends and usage</li>
          </ul>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">3. Information Sharing</h2>
          <p className="text-slate-700 mb-4">
            We do not sell your personal information. We may share your information with:
          </p>
          <ul className="list-disc pl-6 text-slate-700 mb-4">
            <li>Social media platforms (Twitter/X, Instagram, LinkedIn) to post content on your behalf</li>
            <li>Payment processors to handle transactions</li>
            <li>Service providers who assist in operating our platform</li>
            <li>Law enforcement when required by law</li>
          </ul>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">4. Data Security</h2>
          <p className="text-slate-700 mb-4">
            We implement appropriate technical and organizational measures to protect your personal information. However, no method of transmission over the Internet is 100% secure.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">5. Social Media Access</h2>
          <p className="text-slate-700 mb-4">
            When you connect your social media accounts, we request the minimum permissions necessary to post content on your behalf. You can revoke these permissions at any time through your social media account settings.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">6. Cookies</h2>
          <p className="text-slate-700 mb-4">
            We use cookies and similar tracking technologies to track activity on our service and store certain information. You can instruct your browser to refuse all cookies or to indicate when a cookie is being sent.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">7. Data Retention</h2>
          <p className="text-slate-700 mb-4">
            We retain your personal information for as long as necessary to provide our services and comply with legal obligations. You can request deletion of your account and data at any time.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">8. Your Rights</h2>
          <p className="text-slate-700 mb-4">
            You have the right to:
          </p>
          <ul className="list-disc pl-6 text-slate-700 mb-4">
            <li>Access and receive a copy of your personal data</li>
            <li>Correct inaccurate or incomplete data</li>
            <li>Request deletion of your data</li>
            <li>Object to or restrict processing of your data</li>
            <li>Data portability</li>
          </ul>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">9. Children's Privacy</h2>
          <p className="text-slate-700 mb-4">
            Our service is not directed to children under 13. We do not knowingly collect personal information from children under 13.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">10. Changes to Privacy Policy</h2>
          <p className="text-slate-700 mb-4">
            We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page and updating the "Last updated" date.
          </p>
          
          <h2 className="text-2xl font-semibold text-slate-900 mt-8 mb-4">11. Contact Us</h2>
          <p className="text-slate-700 mb-4">
            If you have any questions about this Privacy Policy, please contact us at privacy@socialsync.com.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Privacy;