import React from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';

const Terms = () => {
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
        <h1 className="text-4xl font-bold text-gray-900 mb-8">Terms of Service</h1>
        
        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last updated: February 10, 2026</p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Introduction</h2>
            <p className="text-gray-700 leading-relaxed">
              Welcome to post bridge. By accessing or using our service, you agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our service.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Account Terms</h2>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>You must be 13 years or older to use this service.</li>
              <li>You must provide a valid email address and complete the registration process.</li>
              <li>You are responsible for maintaining the security of your account and password.</li>
              <li>You are responsible for all content posted and activity that occurs under your account.</li>
              <li>You may not use the service for any illegal or unauthorized purpose.</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. Payment Terms</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              If you choose a paid plan, you agree to pay all fees according to the pricing and payment terms in effect at the time.
            </p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>Fees are billed in advance on a monthly or yearly basis.</li>
              <li>All fees are non-refundable except as required by law.</li>
              <li>We reserve the right to change our pricing at any time.</li>
              <li>You can cancel your subscription at any time.</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Acceptable Use</h2>
            <p className="text-gray-700 leading-relaxed mb-4">You agree not to:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700">
              <li>Post content that is illegal, harmful, threatening, abusive, or otherwise objectionable.</li>
              <li>Impersonate any person or entity or misrepresent your affiliation with any person or entity.</li>
              <li>Interfere with or disrupt the service or servers or networks connected to the service.</li>
              <li>Use the service to send spam or other unsolicited communications.</li>
              <li>Attempt to gain unauthorized access to any portion of the service.</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Intellectual Property</h2>
            <p className="text-gray-700 leading-relaxed">
              The service and its original content, features, and functionality are owned by post bridge and are protected by international copyright, trademark, and other intellectual property laws.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Termination</h2>
            <p className="text-gray-700 leading-relaxed">
              We may terminate or suspend your account and access to the service immediately, without prior notice, for any reason, including breach of these Terms.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Disclaimer</h2>
            <p className="text-gray-700 leading-relaxed">
              The service is provided "as is" without warranties of any kind, either express or implied. We do not guarantee that the service will be uninterrupted, secure, or error-free.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Limitation of Liability</h2>
            <p className="text-gray-700 leading-relaxed">
              In no event shall post bridge be liable for any indirect, incidental, special, or consequential damages arising out of or in connection with your use of the service.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Changes to Terms</h2>
            <p className="text-gray-700 leading-relaxed">
              We reserve the right to modify these terms at any time. We will notify you of any changes by posting the new Terms of Service on this page.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Contact Us</h2>
            <p className="text-gray-700 leading-relaxed">
              If you have any questions about these Terms, please contact us at support@postbridge.com
            </p>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Terms;