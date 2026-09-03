import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const Terms = () => {
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
              <Link to="/privacy" className="hover:text-indigo-600 dark:hover:text-indigo-400">Privacy</Link>
              <Link to="/refund" className="hover:text-indigo-600 dark:hover:text-indigo-400">Refund Policy</Link>
              <Link to="/contact" className="hover:text-indigo-600 dark:hover:text-indigo-400">Contact</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-8">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 mb-3 border border-indigo-200/60 dark:border-indigo-800/60">
            Terms of Service &amp; User Agreement
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-950 dark:text-white">
            Terms and Conditions
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
            Last Updated: September 04, 2026 &bull; Effective Date: September 01, 2026
          </p>
          <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-900 dark:text-white font-semibold">Contracting Entity: </strong>
            These Terms of Service constitute a legally binding agreement between you ("User," "you") and <strong>UNRAVLER TECHNOLOGIES</strong> (Sole Proprietorship registered under Government of India Udyam MSME: <strong>UDYAM-JH-20-0144275</strong>), having its principal office at <em>Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</em>.
          </div>
        </div>

        <div className="space-y-8 text-sm sm:text-base leading-relaxed text-slate-700 dark:text-slate-300">
          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">1. Acceptance of Terms</h2>
            <p className="mb-3">
              By registering an account, connecting a social channel, accessing, or using Unravler (<a href="https://unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">unravler.com</a>, <a href="https://app.unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">app.unravler.com</a>), you acknowledge that you have read, understood, and agree to be bound by these Terms and our <Link to="/privacy" className="text-indigo-600 dark:text-indigo-400 underline font-semibold">Privacy Policy</Link>. If you do not agree to these terms, you must not access or use our services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">2. Description of the Service</h2>
            <p>
              Unravler provides an omnichannel social media scheduling, automation, content calendar, client approval workflow, analytics reporting, and link-in-bio platform. Users can create, adapt, schedule, and dispatch multimedia content across supported third-party social networks.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">3. Compliance with Third-Party Platform Terms</h2>
            <p className="mb-3">
              Unravler enables you to publish content to external networks via authorized APIs. Your use of Unravler is strictly conditional upon your compliance with the policies of each respective platform:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong>YouTube / Google:</strong> Users connecting YouTube agree to be bound by the{' '}
                <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 underline">
                  YouTube Terms of Service
                </a>{' '}
                and the{' '}
                <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 underline">
                  Google Privacy Policy
                </a>.
              </li>
              <li>
                <strong>Meta (Facebook &amp; Instagram):</strong> Users agree to comply with Meta's Community Standards, Commercial Terms, and Platform Terms.
              </li>
              <li>
                <strong>LinkedIn:</strong> Users agree to comply with the LinkedIn User Agreement and Professional Community Policies.
              </li>
              <li>
                <strong>X (formerly Twitter):</strong> Users agree to comply with the X Developer Agreement and Policy and Master Services Agreement.
              </li>
              <li>
                <strong>TikTok:</strong> Users agree to comply with TikTok's Terms of Service and Community Guidelines.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">4. Content Ownership &amp; Intellectual Property</h2>
            <p className="mb-2">
              <strong>Your Content:</strong> You retain 100% ownership of all texts, images, videos, audio, trademarks, and logos that you upload, compose, or publish through Unravler. By uploading content, you grant Unravler Technologies a limited, non-exclusive, worldwide license solely to host, transmit, and format your content as necessary to dispatch it to your selected platforms.
            </p>
            <p>
              <strong>Prohibited Content:</strong> You agree not to upload, schedule, or transmit content that is defamatory, illegal, fraudulent, infringes intellectual property, promotes hate speech, or violates applicable telecommunications or cyber laws.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">5. Subscriptions, Payments &amp; 7-Day Refund Policy</h2>
            <p className="mb-2">
              <strong>Billing:</strong> Paid plans are billed in advance on a recurring monthly or annual basis via our authorized payment partners (e.g. Razorpay, Stripe). Applicable taxes (such as GST in India) are calculated at checkout.
            </p>
            <p className="mb-2">
              <strong>7-Day Money-Back Guarantee:</strong> We offer a 100% money-back guarantee for first-time paid plan subscribers if requested within 7 calendar days of initial purchase. Refunds are processed back to your original payment source (Card / UPI / Netbanking via ICICI Bank gateway) within 5–7 business days.
            </p>
            <p>
              For full terms and step-by-step instructions on requesting a refund, review our dedicated{' '}
              <Link to="/refund" className="text-indigo-600 dark:text-indigo-400 underline font-semibold">
                Refund &amp; Cancellation Policy
              </Link>.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">6. Account Termination &amp; Cancellation</h2>
            <p>
              You may cancel your subscription or delete your account at any time directly through your account dashboard (Settings &rarr; Billing / Privacy &amp; Data). Upon account deletion, all active access tokens and scheduled queues are immediately canceled. Unravler Technologies reserves the right to suspend or terminate accounts that engage in API abuse, spamming, or violation of third-party network policies.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">7. Limitation of Liability</h2>
            <p>
              To the maximum extent permitted under applicable law, Unravler Technologies shall not be liable for any indirect, incidental, punitive, or consequential damages resulting from downtime, social network API outages, account suspensions enacted by third-party social networks, or data loss. In no event shall our aggregate liability exceed the amount paid by you to Unravler in the twelve (12) months preceding the claim.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">8. Governing Law and Dispute Jurisdiction</h2>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
              <p className="font-semibold text-slate-900 dark:text-white mb-1">
                Applicable Jurisdiction:
              </p>
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                These Terms of Service and any contractual or non-contractual disputes arising out of or in connection with the Service shall be governed by and construed in accordance with the <strong>laws of the Republic of India</strong>. The parties irrevocably submit to the exclusive jurisdiction of the competent <strong>Courts in Ranchi, Jharkhand, India</strong> for the adjudication of all matters arising hereunder.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">9. Contact and Notices</h2>
            <p>
              Formal legal notices and inquiries regarding these Terms must be directed to:
            </p>
            <div className="mt-2 text-sm font-medium">
              <strong>UNRAVLER TECHNOLOGIES</strong><br />
              Attn: Legal &amp; Compliance Department<br />
              Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India<br />
              Email: <a href="mailto:support@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">support@unravler.com</a> / <a href="mailto:findbinduprasad@zohomail.in" className="text-indigo-600 dark:text-indigo-400 underline">findbinduprasad@zohomail.in</a><br />
              Phone: +91 9031777441
            </div>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Terms;
