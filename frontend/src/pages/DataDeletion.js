import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const DataDeletion = () => {
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
        <h1 className="text-4xl font-bold text-gray-900 mb-8">User Data Deletion Instructions</h1>

        <div className="prose prose-slate max-w-none">
          <p className="text-gray-600 mb-6">Last Updated: 2026-04-23</p>

          <p className="text-gray-700 leading-relaxed mb-6">
            Unravler lets you request deletion of your account and associated data. The fastest way is from inside the app.
          </p>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Delete Your Account (In-App)</h2>
            <ol className="list-decimal pl-6 space-y-2 text-gray-700 mb-4">
              <li>Log in to Unravler at https://app.unravler.com.</li>
              <li>Open Settings.</li>
              <li>Go to Privacy &amp; Data.</li>
              <li>Select Delete Account and confirm.</li>
            </ol>
            <p className="text-gray-700 leading-relaxed">
              This will permanently delete your Unravler account and remove your stored data in line with operational and legal requirements.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Disconnect Social Accounts</h2>
            <p className="text-gray-700 leading-relaxed mb-4">
              You can also disconnect connected social accounts (such as Instagram) inside the app from Connected Accounts.
              Disconnecting stops future actions from Unravler.
            </p>
            <p className="text-gray-700 leading-relaxed">
              You may additionally revoke Unravler’s access from the social platform’s settings (for example, Meta/Facebook settings for connected apps).
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. Need Help?</h2>
            <p className="text-gray-700 leading-relaxed mb-2">
              If you cannot access your account or need assistance with deletion, email us:
            </p>
            <p className="text-gray-700 leading-relaxed font-medium">
              contact@unravler.com
            </p>
          </section>

          <p className="text-gray-700 leading-relaxed mt-8">
            For more details about how we handle information, see our <Link to="/privacy">Privacy Policy</Link>.
          </p>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default DataDeletion;

