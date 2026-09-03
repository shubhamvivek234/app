import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const RefundPolicy = () => {
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
              <Link to="/privacy" className="hover:text-indigo-600 dark:hover:text-indigo-400">Privacy</Link>
              <Link to="/contact" className="hover:text-indigo-600 dark:hover:text-indigo-400">Contact</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-8">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 mb-3 border border-indigo-200/60 dark:border-indigo-800/60">
            Payment Transparency &amp; Customer Satisfaction
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-950 dark:text-white">
            Refund &amp; Cancellation Policy
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
            Last Updated: September 04, 2026 &bull; Effective Date: September 01, 2026
          </p>
          <div className="mt-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-900 dark:text-white font-semibold">Service Operator: </strong>
            This policy applies to all subscription and software purchases made on Unravler (<a href="https://unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">unravler.com</a>), operated by <strong>UNRAVLER TECHNOLOGIES</strong> (Government of India Udyam MSME: <strong>UDYAM-JH-20-0144275</strong>), Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India.
          </div>
        </div>

        <div className="space-y-8 text-sm sm:text-base leading-relaxed text-slate-700 dark:text-slate-300">
          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">1. 7-Day 100% Money-Back Guarantee</h2>
            <p className="mb-3">
              We want you to be completely satisfied with Unravler. If you purchase a paid subscription (Starter, Pro, or Agency) and determine that our service does not suit your business workflow, you are eligible for a <strong>100% full refund</strong> if requested within <strong>7 calendar days</strong> from the initial purchase date.
            </p>
            <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200 text-sm">
              &check; <strong>No Hidden Fees:</strong> We do not charge cancellation fees or administrative processing penalties on valid refund requests.
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">2. How to Request a Refund</h2>
            <p className="mb-3">
              To request a refund within your 7-day trial or billing window, choose either of the following methods:
            </p>
            <div className="grid sm:grid-cols-2 gap-4 my-4">
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <span className="font-bold text-slate-900 dark:text-white block mb-1">Option 1: In-App Cancellation</span>
                <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300">
                  Navigate to <strong>Dashboard &rarr; Settings &rarr; Billing</strong>, click <em>Cancel Plan</em>, and select <em>"Request refund under 7-day guarantee"</em>.
                </p>
              </div>
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <span className="font-bold text-slate-900 dark:text-white block mb-1">Option 2: Direct Email</span>
                <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300">
                  Send an email to <a href="mailto:support@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline font-medium">support@unravler.com</a> or <a href="mailto:findbinduprasad@zohomail.in" className="text-indigo-600 dark:text-indigo-400 underline font-medium">findbinduprasad@zohomail.in</a> with your account email address and payment transaction ID.
                </p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">3. Refund Processing Timelines &amp; Methods</h2>
            <p className="mb-3">
              Once approved by our billing team:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li><strong>Source Reversal:</strong> Refunds are remitted strictly back to the original source payment method used during checkout (e.g. Credit Card, Debit Card, Net Banking, or UPI VPA).</li>
              <li><strong>Turnaround Time:</strong> Funds typically reflect in your bank account within <strong>5 to 7 business days</strong>, depending on your card issuer or banking network (e.g. ICICI Bank, Razorpay, Stripe, or clearing house).</li>
              <li><strong>Notification:</strong> You will receive an automated email confirmation from Unravler and the payment gateway containing your refund reference ARN / UTR number.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">4. Renewal Cancellations</h2>
            <p className="mb-2">
              You may cancel your recurring subscription at any time. When you cancel after the initial 7-day guarantee period:
            </p>
            <ul className="list-disc pl-6 space-y-1.5">
              <li>Your subscription will not renew at the end of the current billing cycle.</li>
              <li>You retain full access to your paid features, scheduled posts, and connected social channels until the last day of your current paid period.</li>
              <li>Subsequent recurring charges are stopped automatically.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">5. Exceptions and Fair Use</h2>
            <p className="mb-2">
              Refunds will not be granted in instances where:
            </p>
            <ul className="list-disc pl-6 space-y-1.5">
              <li>A user account was suspended or terminated for verified violations of our Terms of Service (such as automated bot spamming, abusive content, or platform policy breaches).</li>
              <li>A refund request is submitted after the 7-day money-back period has elapsed.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-3">6. Billing Support Contact</h2>
            <p className="mb-2">
              For any billing disputes, invoice requests, or payment queries, please reach out to:
            </p>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-sm font-medium space-y-1">
              <div><strong>UNRAVLER TECHNOLOGIES</strong> &bull; Billing Department</div>
              <div>Address: Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</div>
              <div>Email: <a href="mailto:support@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">support@unravler.com</a></div>
              <div>Phone / WhatsApp: +91 9031777441</div>
              <div>Operating Hours: Monday – Saturday, 9:00 AM – 6:00 PM IST (Response within 24 hours)</div>
            </div>
          </section>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default RefundPolicy;
