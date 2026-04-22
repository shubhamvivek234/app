import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const Privacy = () => {
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);
  return (
    <div className="min-h-screen bg-offwhite">
      <nav className="bg-offwhite border-b border-gray-100">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <UnravlerLogo size="small" showText={true} />
            </Link>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">Privacy Policy for Unravler</h1>

        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last Updated: 2026-04-22</p>

          <p className="text-gray-700 leading-relaxed mb-6">
            Thank you for using Unravler ("we," "us," or "our"). This Privacy Policy explains how we collect, use, and share information when you use our websites and services (the "Service"), including:
            https://unravler.com and https://app.unravler.com.
          </p>
          <p className="text-gray-700 leading-relaxed mb-6">
            By accessing or using the Service, you agree to this Privacy Policy. If you do not agree, please do not use the Service.
          </p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Information We Collect</h2>

            <h3 className="text-xl font-semibold text-gray-900 mb-2 mt-4">1.1 Personal Data</h3>
            <p className="text-gray-700 leading-relaxed mb-2">We collect the following personal information from you:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700 mb-4">
              <li><strong>Name:</strong> We collect your name to personalize your experience and communicate with you effectively.</li>
              <li><strong>Email:</strong> We collect your email address to send you important information regarding your account, updates, and communication.</li>
              <li><strong>Billing Details:</strong> Subscription and payment status related to your plan. Payment card details are processed by our payment providers; we do not store full card numbers on our servers.</li>
              <li><strong>Social Account Connection Data:</strong> When you connect a social account (such as Instagram), we receive and store identifiers and access tokens needed to provide posting and account-management features.</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-900 mb-2 mt-4">1.2 Non-Personal Data</h3>
            <p className="text-gray-700 leading-relaxed">
              We may collect usage data such as IP address (approximate), device/browser information, pages viewed, and interactions. We may use cookies or similar technologies to keep you signed in and to understand how the Service is used.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Purpose of Data Collection</h2>
            <p className="text-gray-700 leading-relaxed">
              We use information to operate the Service, including account creation and login, connecting social accounts, publishing content on your behalf, customer support, billing/subscription management, security/fraud prevention, and product analytics and improvements.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. Social Platform Integrations (Including Instagram)</h2>
            <p className="text-gray-700 leading-relaxed">
              If you choose to connect a social media account (for example, Instagram), you authorize us to access and act on that account according to the permissions you grant during the login/authorization flow. We use that access to provide features such as reading basic profile/account details, publishing content, and managing messages/comments where supported.
            </p>
            <p className="text-gray-700 leading-relaxed mt-4">
              You can disconnect a social account at any time from within the Service. Disconnecting stops future actions from Unravler, but it may not revoke previously granted permissions at the platform level. You can also revoke access from within the social platform’s settings.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. YouTube API Services</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler may use YouTube API Services. By using our Service to interact with YouTube, you are also subject to the YouTube Terms of Service (https://www.youtube.com/t/terms) and Google’s Privacy Policy (https://policies.google.com/privacy).
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Data Sharing</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              We share information only as needed to run the Service:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700 mb-4">
              <li><strong>Service Providers:</strong> Hosting, database, analytics, email, and payment processing vendors that help us operate the Service (for example, AWS/Vercel, MongoDB Atlas, PostHog, Resend, and payment processors like Stripe/Razorpay/PayPal).</li>
              <li><strong>Social Platforms:</strong> When you connect an account or publish content, we transmit the necessary data to the platform APIs you choose (for example, Instagram).</li>
              <li><strong>Legal/Safety:</strong> If required by law, or to protect the rights, safety, and security of users and the Service.</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Children's Privacy</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler is not intended for children under 13 (or the minimum age required in your jurisdiction). We do not knowingly collect personal information from children.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Data Retention</h2>
            <p className="text-gray-700 leading-relaxed">
              We keep your information for as long as needed to provide the Service and comply with legal obligations. If you delete your account, we delete or de-identify your data consistent with operational and legal requirements.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Your Choices &amp; Data Deletion</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              You can manage, export, or delete your data from inside the app:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700 mb-4">
              <li><strong>Export:</strong> Go to Settings → Privacy &amp; Data → Export My Data.</li>
              <li><strong>Delete:</strong> Go to Settings → Privacy &amp; Data → Delete Account.</li>
              <li><strong>Disconnect social accounts:</strong> Use Connected Accounts inside the app.</li>
            </ul>
            <p className="text-gray-700 leading-relaxed">
              If you need help with data deletion or account access, contact us at the email below.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Security</h2>
            <p className="text-gray-700 leading-relaxed">
              We use reasonable technical and organizational measures to protect information, including access controls and encryption in transit (TLS). No method of transmission or storage is 100% secure, so we cannot guarantee absolute security.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Updates to the Privacy Policy</h2>
            <p className="text-gray-700 leading-relaxed">
              We may update this Privacy Policy from time to time. The "Last Updated" date above reflects the most recent revision.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">11. Contact Information</h2>
            <p className="text-gray-700 leading-relaxed mb-2">
              If you have any questions, concerns, or requests related to this Privacy Policy, you can contact us at:
            </p>
            <p className="text-gray-700 leading-relaxed font-medium">
              Email: contact@unravler.com
            </p>
          </section>

          <p className="text-gray-700 leading-relaxed mt-8 font-semibold">
            By using Unravler, you consent to the terms of this Privacy Policy.
          </p>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Privacy;
