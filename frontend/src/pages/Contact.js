import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';
import { toast } from 'sonner';
import { FaPaperPlane, FaCheckCircle, FaPaperclip } from 'react-icons/fa';

const Contact = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    message: '',
    attachment_name: '',
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
        throw new Error(data.detail || 'Could not send your message right now.');
      }
      setSubmittedData(data);
      toast.success('Thank you! Your message has been sent.');
    } catch (err) {
      toast.error(err.message || 'Could not send message right now. Please try again.');
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

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-center mb-12">
          <span className="inline-block px-3.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-50 text-indigo-600 mb-3">
            Get in Touch
          </span>
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-slate-950 dark:text-white">
            Have a question? Let&rsquo;s talk.
          </h1>
          <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 mt-3 max-w-xl mx-auto">
            Whether you are exploring pilot access, need help with a campaign workflow, or have a general question, our team is ready to help.
          </p>
        </div>

        <div className="grid lg:grid-cols-12 gap-10 lg:gap-14 items-center">
          {/* Left Column: Illustration */}
          <div className="lg:col-span-5 flex justify-center">
            <div className="relative w-full max-w-sm p-4">
              <img
                src="/assets/contact-illustration.png"
                alt="Person thinking with question marks"
                width="980"
                height="980"
                className="w-full h-auto object-contain"
              />
            </div>
          </div>

          {/* Right Column: Simple & Elegant Message Form */}
          <div className="lg:col-span-7">
            <div className="p-6 sm:p-9 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-1">
                Send us a message
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mb-6">
                Fill in your details below and our team will reply to you shortly.
              </p>

              {submittedData ? (
                <div className="py-12 text-center space-y-4">
                  <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto text-2xl">
                    <FaCheckCircle />
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                    Message sent
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 max-w-md mx-auto">
                    Thank you for reaching out. Our team has received your message and will get back to you within 24 hours.
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
                        setFormData({ ...formData, message: '', attachment_name: '' });
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
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Full name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="Enter your full name"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Email <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="email"
                      required
                      placeholder="Enter your email"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                      Your message <span className="text-rose-500">*</span>
                    </label>
                    <textarea
                      required
                      rows={5}
                      placeholder="Write your message..."
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition resize-y"
                    />
                  </div>

                  <div>
                    <label className="flex items-center gap-3 px-3.5 py-3 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40 cursor-pointer hover:border-indigo-400 transition">
                      <FaPaperclip className="text-slate-500" />
                      <span className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">
                        {formData.attachment_name ? `Attached: ${formData.attachment_name}` : 'Attach a file (optional)'}
                      </span>
                      <input
                        type="file"
                        className="sr-only"
                        accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.csv"
                        onChange={(e) => {
                          const file = e.target.files && e.target.files[0];
                          setFormData({ ...formData, attachment_name: file ? file.name : '' });
                        }}
                      />
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 text-white font-semibold text-sm hover:bg-indigo-700 transition shadow-sm active:scale-95 disabled:opacity-50"
                  >
                    <FaPaperPlane className="text-xs" />
                    {submitting ? 'Sending...' : 'Send message'}
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
