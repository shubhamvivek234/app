import React from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';

const Terms = () => {
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
        <h1 className="text-4xl font-bold text-gray-900 mb-8">Terms and Conditions for Unravler</h1>

        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last Updated: 2026-02-11</p>

          <p className="text-gray-700 leading-relaxed mb-6">Welcome to Unravler!</p>

          <p className="text-gray-700 leading-relaxed mb-6">
            These Terms of Service ("Terms") govern your use of the Unravler website at https://crosspost.com ("Website") and the services provided by Unravler. By using our Website and services, you agree to these Terms.
          </p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Description of Unravler</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler is a tool that allows users to cross-post and upload content to all social media platforms from one place.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. YouTube Terms of Service</h2>
            <p className="text-gray-700 leading-relaxed">
              By using Unravler to interact with YouTube services, you also agree to be bound by the YouTube Terms of Service (https://www.youtube.com/t/terms). This includes any use of the YouTube API services through our platform.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. User Data and Privacy</h2>
            <p className="text-gray-700 leading-relaxed">
              We collect and store user data, including name, email, payment information, and social media authentication access keys, as necessary to provide our services. For details on how we handle your data, please refer to our Privacy Policy at https://crosspost.com/privacy-policy.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Non-Personal Data Collection</h2>
            <p className="text-gray-700 leading-relaxed">
              We use web cookies to collect non-personal data for the purpose of improving our services and user experience.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Ownership and Usage Rights</h2>
            <p className="text-gray-700 leading-relaxed">
              When you purchase a package from Unravler, you can sign in to your social media accounts and authorize access to your data to post to the platforms connected to the Unravler app. You retain ownership of your content, but grant us the necessary rights to post on your behalf.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Refund Policy</h2>
            <p className="text-gray-700 leading-relaxed">
              We offer a full refund within 24 hours after the purchase. To request a refund, please contact us at support@crosspost.com.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Children's Privacy</h2>
            <p className="text-gray-700 leading-relaxed">
              Unravler is not intended for use by children, and we do not knowingly collect any data from children.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Updates to the Terms</h2>
            <p className="text-gray-700 leading-relaxed">
              We may update these Terms from time to time. Users will be notified of any changes via email.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Governing Law</h2>
            <p className="text-gray-700 leading-relaxed">
              These Terms are governed by the laws of Canada.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Contact Information</h2>
            <p className="text-gray-700 leading-relaxed">
              For any questions or concerns regarding these Terms of Service, please contact us at support@crosspost.com.
            </p>
          </section>

          <p className="text-gray-700 leading-relaxed mt-8 font-semibold">
            Thank you for using Unravler!
          </p>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Terms;