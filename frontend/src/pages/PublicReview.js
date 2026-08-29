import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicReviewFeed, submitPublicReviewDecision } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaCheckCircle,
  FaTimesCircle,
  FaClock,
  FaCalendarAlt,
  FaLock,
  FaCommentDots,
  FaCheck,
  FaExclamationTriangle,
  FaPaperPlane,
} from 'react-icons/fa';

export default function PublicReview() {
  const { token } = useParams();
  const [feed, setFeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reviewerName, setReviewerName] = useState('Client Reviewer');
  const [changeFeedback, setChangeFeedback] = useState({});
  const [activeTab, setActiveTab] = useState('all');
  const [submitting, setSubmitting] = useState({});

  const loadFeed = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getPublicReviewFeed(token);
      setFeed(data);
    } catch (err) {
      setError(err?.response?.data?.detail || 'This review link is invalid or has expired.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) loadFeed();
  }, [token, loadFeed]);

  const handleDecision = async (postId, decision) => {
    setSubmitting((prev) => ({ ...prev, [postId]: true }));
    try {
      const feedback = changeFeedback[postId] || '';
      await submitPublicReviewDecision(token, {
        post_id: postId,
        decision,
        feedback: feedback || undefined,
        reviewer_name: reviewerName || 'Client Reviewer',
      });
      toast.success(decision === 'approve' ? 'Post Approved!' : 'Feedback submitted for revisions');
      setFeed((prev) => ({
        ...prev,
        posts: prev.posts.filter((p) => p.id !== postId),
      }));
    } catch (err) {
      toast.error('Failed to submit review decision');
    } finally {
      setSubmitting((prev) => ({ ...prev, [postId]: false }));
    }
  };

  const handleApproveAll = async () => {
    if (!feed?.posts?.length) return;
    const confirm = window.confirm(`Approve all ${feed.posts.length} pending posts?`);
    if (!confirm) return;

    for (const post of feed.posts) {
      try {
        await submitPublicReviewDecision(token, {
          post_id: post.id,
          decision: 'approve',
          reviewer_name: reviewerName || 'Client Reviewer',
        });
      } catch (err) {
        // Continue loop
      }
    }
    toast.success('All posts have been approved!');
    loadFeed();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-medium text-slate-600">Loading client review stream...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-3xl p-8 border border-slate-200 shadow-sm text-center space-y-4">
          <div className="w-12 h-12 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center mx-auto text-xl">
            <FaExclamationTriangle />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Review Link Unavailable</h2>
          <p className="text-sm text-slate-500">{error}</p>
        </div>
      </div>
    );
  }

  const posts = feed?.posts || [];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Top Client Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 px-4 py-4 backdrop-blur-md bg-white/90">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-purple-600">
                UNRAVLER
              </span>
              <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full border border-indigo-100/50">
                Client Portal
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Review and approve upcoming social media posts for your brand.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Your Name (e.g. Sarah M.)"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
            {posts.length > 0 && (
              <button
                onClick={handleApproveAll}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5 shrink-0"
              >
                <FaCheck /> Approve All ({posts.length})
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Review Body */}
      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {posts.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-3xl p-12 text-center shadow-xs">
            <div className="w-16 h-16 bg-emerald-50 text-emerald-600 rounded-2xl flex items-center justify-center mx-auto mb-4 text-2xl">
              <FaCheckCircle />
            </div>
            <h2 className="text-xl font-bold text-slate-900">All Posts Approved!</h2>
            <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
              There are no pending posts awaiting your approval at this time. Your agency will notify you when new drafts are ready.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider">
                Pending Posts ({posts.length})
              </h2>
            </div>

            {posts.map((post) => (
              <div
                key={post.id}
                className="bg-white border border-slate-200/80 rounded-3xl p-6 shadow-xs hover:border-slate-300 transition-all space-y-4"
              >
                {/* Post meta */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    {post.platforms?.map((plat) => (
                      <span
                        key={plat}
                        className="capitalize text-xs font-semibold px-2.5 py-1 bg-slate-100 text-slate-700 rounded-lg"
                      >
                        {plat}
                      </span>
                    ))}
                    {post.scheduled_time && (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500 font-medium">
                        <FaClock className="text-[11px] text-slate-400" />{' '}
                        {new Date(post.scheduled_time).toLocaleString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    )}
                  </div>
                </div>

                {/* Content body */}
                <p className="text-sm text-slate-800 whitespace-pre-wrap leading-relaxed font-normal">
                  {post.content}
                </p>

                {/* Media Preview */}
                {post.media_urls?.length > 0 && (
                  <div className="grid grid-cols-2 gap-2 rounded-2xl overflow-hidden max-h-96">
                    {post.media_urls.map((url, idx) => (
                      <img
                        key={idx}
                        src={url}
                        alt="Media Preview"
                        className="w-full h-48 object-cover rounded-xl border border-slate-100"
                        onError={(e) => { e.target.style.display = 'none'; }}
                      />
                    ))}
                  </div>
                )}

                {/* Existing comments */}
                {post.comments?.length > 0 && (
                  <div className="bg-slate-50 rounded-2xl p-3.5 space-y-2 border border-slate-100">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                      <FaCommentDots /> Revision Notes
                    </span>
                    {post.comments.map((c) => (
                      <div key={c.id} className="text-xs text-slate-700">
                        <strong className="text-slate-900">{c.author_name}:</strong> {c.text}
                      </div>
                    ))}
                  </div>
                )}

                {/* Action footer */}
                <div className="pt-2 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex-1">
                    <input
                      type="text"
                      placeholder="Optional feedback or change request..."
                      value={changeFeedback[post.id] || ''}
                      onChange={(e) =>
                        setChangeFeedback((prev) => ({ ...prev, [post.id]: e.target.value }))
                      }
                      className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleDecision(post.id, 'changes_requested')}
                      disabled={submitting[post.id]}
                      className="px-3.5 py-2 text-xs font-semibold bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-xl border border-rose-200/60 transition-all flex items-center gap-1.5"
                    >
                      <FaTimesCircle className="text-xs" /> Request Changes
                    </button>
                    <button
                      onClick={() => handleDecision(post.id, 'approve')}
                      disabled={submitting[post.id]}
                      className="px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5"
                    >
                      <FaCheckCircle className="text-xs" /> Approve Post
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
