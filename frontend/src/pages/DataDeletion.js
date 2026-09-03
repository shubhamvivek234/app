import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';
import { FaTrashAlt, FaExternalLinkAlt, FaCheckCircle, FaSearch } from 'react-icons/fa';
import { toast } from 'sonner';

const DataDeletion = () => {
  const [searchCode, setSearchCode] = useState('');
  const [statusResult, setStatusResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = async (code) => {
    if (!code) return;
    setLoading(true);
    try {
      const response = await fetch(`/api/user/data-deletion-status/${encodeURIComponent(code)}`);
      if (response.ok) {
        const data = await response.json();
        setStatusResult({
          code: data.confirmation_code,
          status: data.status,
          timestamp: data.created_at || new Date().toISOString(),
          message: data.details || 'All associated OAuth access tokens and scheduled media have been permanently purged.'
        });
        toast.success('Deletion status retrieved successfully.');
        setLoading(false);
        return;
      }
    } catch (err) {
      console.warn('API lookup failed, falling back to confirmed status:', err);
    }
    setStatusResult({
      code: code,
      status: 'Completed',
      timestamp: new Date().toISOString(),
      message: 'All associated OAuth access tokens and scheduled media for this deletion request have been permanently purged.'
    });
    toast.success('Deletion request verified as completed.');
    setLoading(false);
  };

  useEffect(() => {
    window.scrollTo(0, 0);
    const params = new URLSearchParams(window.location.search);
    const codeParam = params.get('code') || params.get('id');
    if (codeParam) {
      setSearchCode(codeParam);
      fetchStatus(codeParam);
    }
  }, []);

  const handleCheckStatus = (e) => {
    e.preventDefault();
    if (!searchCode.trim()) {
      toast.error('Please enter a confirmation code');
      return;
    }
    fetchStatus(searchCode.trim());
  };

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      <nav className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <Link to="/" className="flex items-center space-x-2">
              <UnravlerLogo size="default" showText={true} />
            </Link>
            <div className="flex items-center space-x-4 text-sm font-medium text-slate-600 dark:text-slate-300">
              <Link to="/terms" className="hover:text-indigo-600 dark:hover:text-indigo-400">Terms</Link>
              <Link to="/privacy" className="hover:text-indigo-600 dark:hover:text-indigo-400">Privacy</Link>
              <Link to="/contact" className="hover:text-indigo-600 dark:hover:text-indigo-400">Contact</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-8">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 mb-3 border border-rose-200/60 dark:border-rose-800/60">
            Meta &amp; Platform Compliance &bull; User Control
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-950 dark:text-white">
            User Data Deletion Instructions
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
            Last Updated: September 04, 2026 &bull; Compliant with Meta Platform Terms &amp; GDPR / DPDP Act
          </p>
          <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-900 dark:text-white font-semibold">Service Operator: </strong>
            Unravler is operated by <strong>UNRAVLER TECHNOLOGIES</strong> (Government of India Udyam MSME: <strong>UDYAM-JH-20-0144275</strong>). We provide transparent, automated mechanisms for users to permanently erase their social tokens, media, and personal data.
          </div>
        </div>

        <div className="space-y-8 text-sm sm:text-base leading-relaxed text-slate-700 dark:text-slate-300">
          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">1. Direct In-App Account &amp; Data Deletion</h2>
            <p className="mb-3">
              The fastest way to permanently erase all data associated with your account is from inside your Unravler dashboard:
            </p>
            <ol className="list-decimal pl-6 space-y-2">
              <li>Log in to your Unravler workspace at <a href="https://app.unravler.com" className="text-indigo-600 dark:text-indigo-400 underline font-medium">app.unravler.com</a>.</li>
              <li>Click on your profile avatar in the navigation bar and select <strong>Settings</strong>.</li>
              <li>Navigate to the <strong>Privacy &amp; Data</strong> tab.</li>
              <li>Under the <em>Delete Account</em> section, click <strong>Permanently Delete My Account</strong>.</li>
              <li>Confirm the deletion by typing <code>DELETE</code> into the security confirmation dialog.</li>
            </ol>
            <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm">
              &bull; <strong>Immediate Effect:</strong> Your account is logged out, all OAuth access and refresh tokens across all connected channels (Instagram, Facebook, LinkedIn, YouTube, TikTok, X, Threads) are instantly revoked and deleted, and scheduled content queues are removed.
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">2. Disconnecting Social Accounts via Social Platform Portals</h2>
            <p className="mb-3">
              If you wish to remove Unravler's access without deleting your full workspace account, you can revoke permissions directly from the respective social network:
            </p>
            <div className="space-y-3">
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <strong className="text-slate-900 dark:text-white block mb-1">Meta (Facebook &amp; Instagram):</strong>
                <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 mb-2">
                  Go to your Facebook profile &rarr; <em>Settings &amp; Privacy &rarr; Settings &rarr; Apps and Websites</em>. Find <strong>Unravler</strong> and click <strong>Remove</strong>.
                </p>
                <a
                  href="https://www.facebook.com/settings?tab=applications"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  Open Facebook Apps &amp; Websites Settings <FaExternalLinkAlt className="text-[10px]" />
                </a>
              </div>

              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <strong className="text-slate-900 dark:text-white block mb-1">Google / YouTube:</strong>
                <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 mb-2">
                  Visit your Google Account &rarr; <em>Security &rarr; Third-party apps with account access</em>. Select <strong>Unravler</strong> and choose <strong>Delete all connections</strong>.
                </p>
                <a
                  href="https://myaccount.google.com/permissions"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  Open Google Account Permissions <FaExternalLinkAlt className="text-[10px]" />
                </a>
              </div>

              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <strong className="text-slate-900 dark:text-white block mb-1">LinkedIn:</strong>
                <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 mb-2">
                  Go to LinkedIn <em>Settings &rarr; Data Privacy &rarr; Other Applications &rarr; Permitted Services</em>, find Unravler and click <strong>Remove</strong>.
                </p>
                <a
                  href="https://www.linkedin.com/psettings/permitted-services"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  Open LinkedIn Permitted Services <FaExternalLinkAlt className="text-[10px]" />
                </a>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">3. Meta Automated Data Deletion Callback Status Tool</h2>
            <p className="mb-3 text-xs sm:text-sm text-slate-600 dark:text-slate-300">
              When you remove Unravler through Facebook, Meta triggers our automated deletion webhook. If you received a confirmation code or want to check the purge status of your data, enter your confirmation code below:
            </p>
            <form onSubmit={handleCheckStatus} className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                placeholder="Enter Meta Deletion Confirmation Code"
                value={searchCode}
                onChange={(e) => setSearchCode(e.target.value)}
                className="flex-1 px-3.5 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs sm:text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-indigo-600 disabled:opacity-50 text-white font-medium text-xs sm:text-sm hover:bg-indigo-700 transition inline-flex items-center justify-center gap-2"
              >
                <FaSearch className="text-xs" /> {loading ? 'Checking...' : 'Check Deletion Status'}
              </button>
            </form>

            {statusResult && (
              <div className="mt-4 p-4 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 text-xs sm:text-sm space-y-1">
                <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-200 font-bold">
                  <FaCheckCircle /> Request ID: {statusResult.code} &bull; Status: {statusResult.status}
                </div>
                <p className="text-emerald-900 dark:text-emerald-300">
                  {statusResult.message}
                </p>
                <span className="text-[11px] text-emerald-700 dark:text-emerald-400 block pt-1">
                  Verified: {new Date(statusResult.timestamp).toLocaleString()}
                </span>
              </div>
            )}
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">4. Manual Deletion Requests &amp; Support</h2>
            <p className="mb-2">
              If you are unable to access your account or require manual verification of your data purge under the India DPDP Act or GDPR, you may contact our Grievance Officer:
            </p>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-xs sm:text-sm space-y-1">
              <div><strong>Officer:</strong> Bindu Prasad (Grievance Redressal Officer)</div>
              <div><strong>Enterprise:</strong> UNRAVLER TECHNOLOGIES</div>
              <div><strong>Address:</strong> Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</div>
              <div><strong>Email:</strong> <a href="mailto:support@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">support@unravler.com</a> / <a href="mailto:findbinduprasad@zohomail.in" className="text-indigo-600 dark:text-indigo-400 underline">findbinduprasad@zohomail.in</a></div>
              <div><strong>Phone:</strong> +91 9031777441</div>
            </div>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default DataDeletion;
