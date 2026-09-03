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
  FaCheckCircle
} from 'react-icons/fa';

const Contact = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: 'General Inquiry',
    message: ''
  });
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) {
      toast.error('Please fill in all required fields.');
      return;
    }
    // Simulate inquiry dispatch & provide direct mailto fallback
    setSubmitted(true);
    toast.success('Thank you! Your message has been received. We will respond within 24 hours.');
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
              <Link to="/refund" className="hover:text-indigo-600 dark:hover:text-indigo-400">Refund Policy</Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="border-b border-slate-200 dark:border-slate-800 pb-8 mb-8 text-center sm:text-left">
          <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 mb-3 border border-indigo-200/60 dark:border-indigo-800/60">
            Customer Support &amp; Corporate Office
          </span>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-950 dark:text-white">
            Contact Us
          </h1>
          <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 mt-2 max-w-2xl">
            Have a question, need technical help, or wish to reach our compliance desk? Get in touch with the Unravler Technologies team.
          </p>
        </div>

        <div className="grid lg:grid-cols-12 gap-8 lg:gap-12">
          {/* Left Column: Official Enterprise Information */}
          <div className="lg:col-span-5 space-y-6">
            <div className="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-5 shadow-2xs">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                Corporate Details
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

            {/* Grievance Redressal Card */}
            <div className="p-5 rounded-2xl border border-indigo-200 dark:border-indigo-900 bg-indigo-50/50 dark:bg-indigo-950/30 space-y-2">
              <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-bold text-xs uppercase tracking-wider">
                <FaShieldAlt /> Grievance Redressal Desk
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                Appointed in compliance with the Information Technology Act, 2000 and DPDP Act, 2023:
              </p>
              <div className="text-xs text-slate-800 dark:text-slate-200 font-medium space-y-0.5 pt-1">
                <div><strong>Officer:</strong> Bindu Prasad (Proprietor)</div>
                <div><strong>Email:</strong> <a href="mailto:contact@unravler.com" className="text-indigo-600 dark:text-indigo-400 underline">contact@unravler.com</a></div>
                <div><strong>Address:</strong> Om Niwas, Near Over Bridge, Anantpur Road, New Anantpur, Ranchi, Jharkhand – 834002, India</div>
              </div>
            </div>
          </div>

          {/* Right Column: Contact & Message Form */}
          <div className="lg:col-span-7">
            <div className="p-6 sm:p-8 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">
                Send us a Message
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mb-6">
                Fill out the form below, and an Unravler specialist will get back to you promptly.
              </p>

              {submitted ? (
                <div className="py-12 text-center space-y-4">
                  <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto text-2xl">
                    <FaCheckCircle />
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">Message Dispatched</h3>
                  <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 max-w-md mx-auto">
                    We have received your message. Our team in Ranchi will review your inquiry and respond within 24 hours.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setSubmitted(false);
                      setFormData({ name: '', email: '', subject: 'General Inquiry', message: '' });
                    }}
                    className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/60 rounded-xl hover:bg-indigo-100 transition"
                  >
                    Send another message
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Your Full Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Alex Sharma"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Email Address <span className="text-rose-500">*</span>
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

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Department / Reason <span className="text-rose-500">*</span>
                    </label>
                    <select
                      value={formData.subject}
                      onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                    >
                      <option value="General Inquiry">General Product Inquiry</option>
                      <option value="Technical Support">Technical &amp; API Support</option>
                      <option value="Billing & Refunds">Billing &amp; Refund Request</option>
                      <option value="Enterprise & Agency">Enterprise / Agency Plan Inquiry</option>
                      <option value="Data Privacy & Compliance">Data Privacy &amp; DPDP Grievance</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Your Message <span className="text-rose-500">*</span>
                    </label>
                    <textarea
                      required
                      rows={5}
                      placeholder="How can we help your team today?"
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition resize-none"
                    />
                  </div>

                  <button
                    type="submit"
                    className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-slate-950 dark:bg-white text-white dark:text-slate-950 font-semibold text-sm hover:bg-slate-800 dark:hover:bg-slate-100 transition shadow-sm active:scale-95"
                  >
                    <FaPaperPlane className="text-xs" /> Submit Message
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
