import React, { useState } from 'react';
import { createShareReviewLink } from '@/lib/api';
import { toast } from 'sonner';
import { FaShareAlt, FaCopy, FaTimes, FaCheck, FaLock } from 'react-icons/fa';

export default function ShareReviewModal({ isOpen, onClose }) {
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [allowComments, setAllowComments] = useState(true);
  const [shareUrl, setShareUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const data = await createShareReviewLink({
        expires_in_days: Number(expiresInDays),
        allow_comments: allowComments,
      });
      setShareUrl(data.share_url);
      toast.success('Magic review link created!');
    } catch (err) {
      toast.error('Failed to generate review link');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    toast.success('Link copied to clipboard!');
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-xl border border-slate-100 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <FaShareAlt className="text-sm" />
            </div>
            <h3 className="text-base font-bold text-slate-900">Share Client Review Link</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 p-1 rounded-lg">
            <FaTimes />
          </button>
        </div>

        <p className="text-xs text-slate-500 mb-5 leading-relaxed">
          Generate a secure, frictionless review link for your client. Clients can approve posts or request revisions from any phone or browser without logging into an account.
        </p>

        {!shareUrl ? (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Link Expiration
              </label>
              <select
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl outline-hidden bg-slate-50 focus:ring-2 focus:ring-indigo-500"
              >
                <option value={1}>Expires in 24 hours</option>
                <option value={3}>Expires in 3 days</option>
                <option value={7}>Expires in 7 days</option>
                <option value={14}>Expires in 14 days</option>
                <option value={30}>Expires in 30 days</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="allowCommentsCheck"
                checked={allowComments}
                onChange={(e) => setAllowComments(e.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded-md border-slate-300 focus:ring-indigo-500"
              />
              <label htmlFor="allowCommentsCheck" className="text-xs text-slate-700 font-medium cursor-pointer">
                Allow clients to leave revision comments
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={handleGenerate}
                disabled={loading}
                className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 disabled:opacity-50"
              >
                {loading ? 'Generating...' : 'Create Magic Link'}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-3 flex items-center justify-between gap-2">
              <span className="text-xs font-mono text-indigo-600 truncate flex-1">{shareUrl}</span>
              <button
                onClick={handleCopy}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shrink-0 flex items-center gap-1 shadow-xs"
              >
                {copied ? <FaCheck /> : <FaCopy />} {copied ? 'Copied' : 'Copy'}
              </button>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={onClose}
                className="px-5 py-2 text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
