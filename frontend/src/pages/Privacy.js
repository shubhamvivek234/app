import React from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';

const Privacy = () => {
  return (
    <div className="min-h-screen bg-offwhite">
      <nav className="bg-offwhite border-b border-gray-100">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">C</span>
              </div>
              <span className="text-xl font-semibold text-gray-900">Unravler</span>
            </Link>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">Privacy Policy for Unravler</h1>

        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last Updated: 2026-02-11</p>

          <p className="text-gray-700 leading-relaxed mb-6">
            Thank you for using Unravler ("we," "us," or "our"). This Privacy Policy outlines how we collect, use, and protect your personal and non-personal information when you use our website located at https://crosspost.com (the "Website").
          </p>
          <p className="text-gray-700 leading-relaxed mb-6">
            By accessing or using the Website, you agree to the terms of this Privacy Policy. If you do not agree with the practices described in this policy, please do not use the Website.
          </p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Information We Collect</h2>

            <h3 className="text-xl font-semibold text-gray-900 mb-2 mt-4">1.1 Personal Data</h3>
            <p className="text-gray-700 leading-relaxed mb-2">We collect the following personal information from you:</p>
            <ul className="list-disc pl-6 space-y-2 text-gray-700 mb-4">
              <li><strong>Name:</strong> We collect your name to personalize your experience and communicate with you effectively.</li>
              <li><strong>Email:</strong> We collect your email address to send you important information regarding your account, updates, and communication.</li>
              <li><strong>Payment Information:</strong> We collect payment details to process your orders securely.</li>
              <li><strong>Social Media Authentication Access Keys:</strong> We collect these to enable cross-posting functionality to your social media accounts.</li>
            </ul>

            <h3 className="text-xl font-semibold text-gray-900 mb-2 mt-4">1.2 Non-Personal Data</h3>
            <p className="text-gray-700 leading-relaxed">
              We use web cookies to collect non-personal information such as your IP address, browser type, device information, and browsing patterns. This information helps us to enhance your browsing experience, analyze trends, and improve our services.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Purpose of Data Collection</h2>
            <p className="text-gray-700 leading-relaxed">
              We collect and use your personal data for order processing and social media posting. This includes processing your orders, enabling cross-posting functionality, sending confirmations, providing customer support, and keeping you updated about the status of your account and posts.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. YouTube API Services</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler uses YouTube API Services to enable cross-posting functionality to YouTube. By using our service to interact with YouTube, you are also subject to the YouTube Terms of Service (https://www.youtube.com/t/terms).
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Google Privacy Policy</h2>
            <p className="text-gray-700 leading-relaxed">
              As we use YouTube API Services, your data may also be subject to Google's Privacy Policy. For more information on how Google collects and processes data, please refer to the Google Privacy Policy at http://www.google.com/policies/privacy.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Data Sharing</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              We do not share your personal data with any other parties except as required for order processing and social media posting functionality. This may include sharing necessary data with the social media platforms you choose to post to, including YouTube through the YouTube API Services.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Children's Privacy</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler is not intended for children, and we do not collect any data from children.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Updates to the Privacy Policy</h2>
            <p className="text-gray-700 leading-relaxed">
              We may update this Privacy Policy from time to time. Users will be notified of any changes via email.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Contact Information</h2>
            <p className="text-gray-700 leading-relaxed mb-2">
              If you have any questions, concerns, or requests related to this Privacy Policy, you can contact us at:
            </p>
            <p className="text-gray-700 leading-relaxed font-medium">
              Email: support@crosspost.com
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Data Protection Mechanisms</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              We take the protection of your sensitive data seriously and have implemented the following security measure:
            </p>
            <p className="text-gray-700 leading-relaxed mb-4">
              <strong>a) Encryption:</strong> Your Google OAuth access keys are encrypted using industry-standard encryption protocols both in transit and at rest.
            </p>
            <p className="text-gray-700 leading-relaxed">
              While we implement this security measure to protect your sensitive information, please be aware that no method of transmission over the Internet or method of electronic storage is 100% secure. We strive to use commercially acceptable means to protect your personal information, but we cannot guarantee its absolute security.
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