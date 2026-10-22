import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';
import { toast } from 'sonner';
import {
  FaMapMarkerAlt,
  FaEnvelope,
  FaClock,
  FaShieldAlt,
  FaPaperPlane,
  FaCheckCircle,
} from 'react-icons/fa';

const TOPICS = [
  'Pilot & Dedicated IPs',
  'Product & Sequences',
  'Billing & Invoices',
  'Security & Privacy',
  'General Inquiry',
];

const Contact = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    topic: 'Pilot & Dedicated IPs',
    seats: '',
    country: '',
    message: '',
    acknowledged_terms: true,
    honeypot: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submittedData, setSubmittedData] = useState(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.email.trim() || formData.message.trim().length < 10) {
      toast.error('Please enter your name, email, and a message of at least 10 characters.');
      return;
    }
    if (!formData.acknowledged_terms) {
      toast.error('Please agree to the Terms of Service and Privacy Policy.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch('/api/v1/support/public-contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Could not dispatch your message right now.');
      }
      setSubmittedData(data);
      toast.success('Your message has been delivered to contact@unravler.com!');
    } catch (err) {
      toast.error(err.message || 'Could not dispatch message. Please email contact@unravler.com.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      <nav className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <Link to="/" className="flex items-center space-x-2">
              <UnravlerLogo size="default" showText={true} />
            </Link>
            <div className="flex items-center space-x-4 text-sm font-medium text-slate-600 dark:text-slate-300">
              <Link to="/terms" className="hover:text-indigo-600 dark:hover:text-indigo-400">Terms</Link>
              <Link to="/privacy" className="hover:text-indigo-600 dark:hover:text-indigo-400">Privacy</Link>
              <Link to="/refund" className="hover:text-indigo-600 dark:hover:text-indigo-400">Billing &amp; Refunds</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-10 text-center">
          <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 mb-4 border border-emerald-200/60 dark:border-emerald-800/60">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Direct Dispatch to contact@unravler.com &bull; Under 24h Response
          </span>
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-slate-950 dark:text-white">
            Let&rsquo;s build your next conversation
          </h1>
          <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 mt-3 max-w-2xl mx-auto">
            Ask about country-matched dedicated ISP sender seats ($59/sender/mo), visual sequence engineering, billing, or compliance. Every inquiry routes directly to <a href="mailto:contact@unravler.com" className="text-indigo-600 underline font-semibold">contact@unravler.com</a>.
          </p>
        </div>

        <div className="grid lg:grid-cols-12 gap-8 lg:gap-12">
          {/* Left Column: Specialist Desks & Corporate Details */}
          <div className="lg:col-span-5 space-y-6">
            <div className="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-5 shadow-2xs">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Corporate &amp; Support Desk
              </h2>

              <div className="space-y-4 text-xs sm:text-sm">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0 mt-0.5">
                    <FaMapMarkerAlt className="text-sm" />
                  </div>
                  <div>
                    <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Registered Office</span>
                    <strong className="text-slate-900 dark:text-white block mt-0.5 font-semibold">UNRAVLER TECHNOLOGIES</strong>
                    <p className="text-slate-600 dark:text-slate-300 mt-0.5 leading-relaxed">
                      Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India
                    </p>
                    <span className="text-[11px] text-slate-400 font-mono block mt-1">Udyam Reg: UDYAM-JH-20-0144275</span>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0 mt-0.5">
                    <FaEnvelope className="text-sm" />
                  </div>
                  <div>
                    <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Electronic Support</span>
                    <a href="mailto:contact@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline font-medium block mt-0.5">
                      contact@unravler.com
                    </a>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-950 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0 mt-0.5">
                    <FaClock className="text-sm" />
                  </div>
                  <div>
                    <span className="text-xs uppercase font-bold tracking-wider text-slate-400 block">Business Hours</span>
                    <span className="text-slate-800 dark:text-slate-200 block mt-0.5 font-medium">
                      Monday – Saturday: 9:00 AM – 6:00 PM IST
                    </span>
                    <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium block mt-0.5">
                      &bull; Average Response Time: &lt; 24 Hours
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/50 dark:bg-indigo-950/30 space-y-2">
              <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-bold text-xs uppercase tracking-wider">
                <FaShieldAlt /> Grievance &amp; Privacy Desk
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                Appointed in compliance with the Information Technology Act, 2000, GDPR, and DPDP Act, 2023:
              </p>
              <div className="text-xs text-slate-800 dark:text-slate-200 font-medium space-y-0.5 pt-1">
                <div><strong>Officer:</strong> Bindu Prasad (Proprietor)</div>
                <div><strong>Email:</strong> <a href="mailto:contact@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">contact@unravler.com</a></div>
              </div>
            </div>
          </div>

          {/* Right Column: Interactive Contact Form */}
          <div className="lg:col-span-7">
            <div className="p-6 sm:p-8 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-1">
                Send a message to contact@unravler.com
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mb-6">
                Select a topic and share your details below. Our team will respond directly via email.
              </p>

              {submittedData ? (
                <div className="py-12 text-center space-y-4">
                  <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto text-2xl">
                    <FaCheckCircle />
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                    Message Delivered to contact@unravler.com
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 max-w-md mx-auto">
                    {submittedData.message || 'We have received your message and will respond within 24 hours.'}
                  </p>
                  {submittedData.ticket_id && (
                    <div className="inline-block px-3.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 text-xs font-mono font-bold border border-emerald-200 dark:border-emerald-800">
                      Reference ID: {submittedData.ticket_id}
                    </div>
                  )}
                  <div>
                    <button
                      type="button"
                      onClick={() => {
                        setSubmittedData(null);
                        setFormData({ ...formData, message: '' });
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/60 rounded-xl hover:bg-indigo-100 transition"
                    >
                      Send another message
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                      Topic
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {TOPICS.map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => setFormData({ ...formData, topic: t })}
                          className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                            formData.topic === t
                              ? 'bg-indigo-600 text-white shadow-xs'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-indigo-50'
                          }`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Your Full Name <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="e.g. Alex Morgan"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Work Email <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="email"
                        required
                        placeholder="alex@company.com"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Company / Workspace
                      </label>
                      <input
                        type="text"
                        placeholder="Acme Growth"
                        value={formData.company}
                        onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                        className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Sender Seats
                      </label>
                      <input
                        type="text"
                        placeholder="1-5 seats ($59/mo)"
                        value={formData.seats}
                        onChange={(e) => setFormData({ ...formData, seats: e.target.value })}
                        className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                        Proxy Country
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. US, UK, IN"
                        value={formData.country}
                        onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                        className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Your Message <span className="text-rose-500">*</span>
                    </label>
                    <textarea
                      required
                      rows={5}
                      placeholder="How can our team help you today?"
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition resize-y"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 text-white font-semibold text-sm hover:bg-indigo-700 transition shadow-sm active:scale-95 disabled:opacity-50"
                  >
                    <FaPaperPlane className="text-xs" />
                    {submitting ? 'Sending to contact@unravler.com...' : 'Send Message'}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default Contact;
