import React from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';

const Privacy = () => {
  return (
    <div className="min-h-screen bg-white">
      <nav className="bg-white border-b border-gray-100">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">P</span>
              </div>
              <span className="text-xl font-semibold text-gray-900">post bridge</span>
            </Link>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">Privacy Policy</h1>
        
        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last updated: February 10, 2026</p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Introduction</h2>
            <p className="text-gray-700 leading-relaxed">
              post bridge ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, and share information about you when you use our service.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Information We Collect</h2>
            <h3 className="text-xl font-semibold text-gray-900 mb-3 mt-4">Information You Provide</h3>
            <ul className="list-disc pl-6 space-y-2 text-gray-700 mb-4">
              <li>Account information (name, email, password)</li>
              <li>Social media account credentials and tokens</li>
              <li>Content you create and schedule through our service</li>
              <li>Payment information (processed securely through Stripe, Razorpay, or PayPal)</li>
            </ul>
            <h3 className="text-xl font-semibold text-gray-900 mb-3 mt-4">Information We Collect Automatically</h3>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>Usage data (pages visited, features used, time spent)</li>
              <li>Device information (browser type, operating system, IP address)</li>
              <li>Cookies and similar tracking technologies</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. How We Use Your Information</h2>
            <p className="text-gray-700 leading-relaxed mb-4">We use the information we collect to:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>Provide, maintain, and improve our service</li>
              <li>Process your transactions and manage your subscriptions</li>
              <li>Send you technical notices, updates, and support messages</li>
              <li>Respond to your comments and questions</li>
              <li>Analyze usage patterns and trends</li>
              <li>Detect, prevent, and address technical issues and fraudulent activity</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. How We Share Your Information</h2>
            <p className="text-gray-700 leading-relaxed mb-4">We may share your information with:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li><strong>Social Media Platforms:</strong> To post content on your behalf as instructed</li>
              <li><strong>Payment Processors:</strong> Stripe, Razorpay, and PayPal for payment processing</li>
              <li><strong>Service Providers:</strong> Third parties who help us operate our service</li>
              <li><strong>Legal Requirements:</strong> When required by law or to protect our rights</li>
            </ul>
            <p className="text-gray-700 leading-relaxed mt-4">
              We do not sell your personal information to third parties.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Cookies and Tracking</h2>
            <p className="text-gray-700 leading-relaxed">
              We use cookies and similar tracking technologies to collect information about your browsing activities. You can control cookies through your browser settings.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Data Security</h2>
            <p className="text-gray-700 leading-relaxed">
              We implement appropriate technical and organizational measures to protect your personal information. However, no method of transmission over the Internet is 100% secure.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Your Rights</h2>
            <p className="text-gray-700 leading-relaxed mb-4">You have the right to:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>Access the personal information we hold about you</li>
              <li>Correct inaccurate or incomplete information</li>
              <li>Request deletion of your personal information</li>
              <li>Object to or restrict certain processing of your information</li>
              <li>Export your data in a portable format</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Data Retention</h2>
            <p className="text-gray-700 leading-relaxed">
              We retain your information for as long as your account is active or as needed to provide you services. You can request deletion of your account at any time.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. International Data Transfers</h2>
            <p className="text-gray-700 leading-relaxed">
              Your information may be transferred to and processed in countries other than your own. We ensure appropriate safeguards are in place for such transfers.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Children's Privacy</h2>
            <p className="text-gray-700 leading-relaxed">
              Our service is not intended for children under 13. We do not knowingly collect personal information from children under 13.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">11. Changes to This Policy</h2>
            <p className="text-gray-700 leading-relaxed">
              We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new policy on this page.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">12. Contact Us</h2>
            <p className="text-gray-700 leading-relaxed">
              If you have any questions about this Privacy Policy, please contact us at privacy@postbridge.com
            </p>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Privacy;