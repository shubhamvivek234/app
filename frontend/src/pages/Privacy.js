import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const Privacy = () => {
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

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
              <Link to="/refund" className="hover:text-indigo-600 dark:hover:text-indigo-400">Refund Policy</Link>
              <Link to="/contact" className="hover:text-indigo-600 dark:hover:text-indigo-400">Contact</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-8">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 mb-3 border border-indigo-200/60 dark:border-indigo-800/60">
            Legal Transparency &amp; DPDP Act Compliance
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-950 dark:text-white">
            Privacy Policy
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
            Last Updated: September 04, 2026 &bull; Effective Date: September 01, 2026
          </p>
          <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-900 dark:text-white font-semibold">Entity Declaration: </strong>
            This Service (<a href="https://unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">unravler.com</a> and its subdomains) is owned, operated, and provided by <strong>UNRAVLER TECHNOLOGIES</strong> (Sole Proprietorship registered under Government of India Udyam MSME: <strong>UDYAM-JH-20-0144275</strong>), with its principal place of business at <em>Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</em>.
          </div>
        </div>

        <div className="space-y-8 text-sm sm:text-base leading-relaxed text-slate-700 dark:text-slate-300">
          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">1. Overview and Core Philosophy</h2>
            <p className="mb-3">
              At <strong>Unravler Technologies</strong> ("Unravler," "we," "us," or "our"), we respect your privacy and are committed to protecting personal and business data. This Privacy Policy details the exact types of information collected, processed, and secured when you access our cross-platform publishing platform, mobile-responsive bio pages, social CRM inbox, and analytics dashboard.
            </p>
            <div className="p-4 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200 font-medium">
              &check; <strong>Our Non-Negotiable Commitment:</strong> We do not sell, rent, trade, monetize, or lease your personal information, customer contacts, or social media tokens to data brokers, marketing agencies, or any third parties. Your data is used strictly to provide and operate the Unravler services you authorize.
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">2. Information We Collect</h2>
            <h3 className="font-semibold text-slate-900 dark:text-white mt-3 mb-1">2.1 User-Supplied Information</h3>
            <ul className="list-disc pl-6 space-y-1.5 mb-4">
              <li><strong>Account Credentials:</strong> Full name, verified email address, workspace name, and password hashes (stored strictly via one-way bcrypt hashing; plaintext passwords are never saved).</li>
              <li><strong>Billing &amp; Transaction Details:</strong> Name, billing address, and payment confirmation status. Full credit/debit card numbers, UPI VPAs, and bank credentials are handled directly by PCI-DSS certified payment gateways (e.g. Razorpay, Stripe); Unravler never stores card numbers on its servers.</li>
              <li><strong>User Content:</strong> Text captions, hashtags, images, videos, audio mixes, and scheduling timestamps uploaded for publishing.</li>
            </ul>

            <h3 className="font-semibold text-slate-900 dark:text-white mt-3 mb-1">2.2 Social Network OAuth Data</h3>
            <p className="mb-2">
              When you connect third-party platforms (including Instagram, Facebook, LinkedIn, YouTube, TikTok, X, Threads, and Bluesky), we receive scoped OAuth 2.0 access tokens. We collect:
            </p>
            <ul className="list-disc pl-6 space-y-1.5">
              <li>Public profile data: Username, profile handle, avatar image URL, and platform user ID.</li>
              <li>Encrypted OAuth access and refresh tokens necessary to post content and read performance analytics on your behalf.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">3. Google API Services &amp; YouTube Limited Use Disclosure</h2>
            <p className="mb-3">
              Unravler integrates with Google API Services and the YouTube API Services to allow you to upload and schedule video content to your connected YouTube channels.
            </p>
            <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-2">
              <p className="font-medium text-slate-900 dark:text-white">
                Google API Services User Data Policy Compliance:
              </p>
              <p className="italic text-slate-800 dark:text-slate-200">
                "Unravler's use and transfer to any other app of information received from Google APIs will adhere to the{' '}
                <a
                  href="https://developers.google.com/terms/api-services-user-data-policy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-600 dark:text-indigo-400 underline font-semibold"
                >
                  Google API Services User Data Policy
                </a>
                , including the Limited Use requirements."
              </p>
            </div>
            <p className="mt-3">
              By connecting your YouTube account, you also agree to be bound by the{' '}
              <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 underline">
                YouTube Terms of Service
              </a>{' '}
              and the{' '}
              <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 underline">
                Google Privacy Policy
              </a>.
            </p>
            <p className="mt-2">
              You can view and revoke Unravler's access to your Google account at any time via the{' '}
              <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 underline font-medium">
                Google Security Account Permissions Page
              </a>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">4. Meta (Facebook &amp; Instagram) Permissions</h2>
            <p className="mb-2">
              For Facebook Pages and Instagram Professional/Creator accounts, Unravler requests the following explicit Meta Graph API permissions:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li><code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-indigo-600 dark:text-indigo-400">instagram_basic</code>: Used to retrieve profile identifiers, username, and account profile picture.</li>
              <li><code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-indigo-600 dark:text-indigo-400">instagram_content_publish</code>: Used to schedule, validate, and publish photos, Reels, and carousels directly to your Instagram account.</li>
              <li><code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-indigo-600 dark:text-indigo-400">pages_show_list</code>: Used to list Facebook Pages you administer so you can select which pages to connect.</li>
              <li><code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-indigo-600 dark:text-indigo-400">pages_manage_posts</code>: Used to dispatch scheduled posts, stories, and videos to your chosen Facebook Pages.</li>
            </ul>
            <p className="mt-3">
              We provide automated data erasure for Meta users in accordance with Meta Platform Terms. Please visit our{' '}
              <Link to="/data-deletion" className="text-indigo-600 dark:text-indigo-400 underline font-semibold">
                User Data Deletion Instructions page
              </Link>{' '}
              for instant deauthorization steps and confirmation status checks.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">5. Data Security &amp; Encryption Standards</h2>
            <p className="mb-2">
              We employ industry-grade physical, technical, and procedural safeguards:
            </p>
            <ul className="list-disc pl-6 space-y-1.5">
              <li><strong>Encryption at Rest:</strong> All OAuth tokens, refresh keys, and sensitive access tokens are encrypted using AES-256-GCM prior to storage in our databases.</li>
              <li><strong>Encryption in Transit:</strong> All HTTP traffic to and from Unravler APIs is enforced over TLS 1.3 encryption.</li>
              <li><strong>Access Controls:</strong> Server infrastructure and databases operate with least-privilege role boundaries and IP-restricted firewalls.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">6. Digital Personal Data Protection (DPDP) Act Compliance &amp; Grievance Redressal</h2>
            <p className="mb-3">
              In full compliance with India's Digital Personal Data Protection (DPDP) Act, 2023 and the Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011, Indian Data Principals have the right to access, rectify, erase, or withdraw consent for processing their personal data.
            </p>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
              <h4 className="font-bold text-slate-950 dark:text-white text-base mb-2">Designated Grievance Redressal Officer</h4>
              <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300">
                In accordance with Rule 5(9) of the IT Rules and DPDP statutory requirements, the details of our Grievance Officer are:
              </p>
              <div className="mt-3 space-y-1 text-xs sm:text-sm font-medium">
                <div><span className="text-slate-500">Name:</span> <strong className="text-slate-900 dark:text-white">Bindu Prasad</strong></div>
                <div><span className="text-slate-500">Designation:</span> Proprietor &amp; Grievance Redressal Officer</div>
                <div><span className="text-slate-500">Enterprise:</span> Unravler Technologies (UDYAM-JH-20-0144275)</div>
                <div><span className="text-slate-500">Physical Address:</span> Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</div>
                <div><span className="text-slate-500">Official Email:</span> <a href="mailto:contact@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">contact@unravler.com</a></div>
                <div><span className="text-slate-500">Response SLA:</span> Acknowledgment within 24 hours; resolution within 15 business days.</div>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">7. Data Retention and Account Erasure</h2>
            <p className="mb-2">
              We retain your account data and post history for as long as your workspace remains active. When you cancel or delete your account:
            </p>
            <ul className="list-disc pl-6 space-y-1.5">
              <li>All active OAuth tokens across all platforms are permanently invalidated and deleted.</li>
              <li>Your drafts, scheduled queues, and cached analytics are purged from our primary database within 30 days.</li>
              <li>You can trigger immediate erasure via <strong>Settings &rarr; Delete Account</strong> or by following our <Link to="/data-deletion" className="text-indigo-600 dark:text-indigo-400 underline font-semibold">Data Deletion Guide</Link>.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">8. Contact Us</h2>
            <p>
              If you have any questions, inquiries, or privacy requests regarding this Privacy Policy, please contact our support desk or visit our <Link to="/contact" className="text-indigo-600 dark:text-indigo-400 underline font-semibold">Contact Page</Link>:
            </p>
            <p className="mt-2 font-medium">
              <strong>UNRAVLER TECHNOLOGIES</strong><br />
              Email: <a href="mailto:contact@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">contact@unravler.com</a><br />
              Address: Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India
            </p>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Privacy;
