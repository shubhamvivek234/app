import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts, approvePost, rejectPost, resubmitPost } from '@/lib/api';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  FaCheckDouble, FaCheck, FaTimes, FaClock, FaImage, FaVideo,
  FaTwitter, FaInstagram, FaFacebook, FaLinkedin, FaYoutube,
  FaRedo, FaExclamationTriangle,
} from 'react-icons/fa';

const PLATFORM_ICONS = {
  twitter: FaTwitter, instagram: FaInstagram, facebook: FaFacebook,
  linkedin: FaLinkedin, youtube: FaYoutube,
};
const PLATFORM_COLORS = {
  twitter: 'text-sky-500', instagram: 'text-pink-500', facebook: 'text-blue-600',
  linkedin: 'text-blue-700', youtube: 'text-red-500',
};

const truncate = (s, n = 160) => (!s ? '' : s.length > n ? s.slice(0, n) + '…' : s);

const formatScheduled = (t) => {
  try { return format(parseISO(t), 'MMM d, yyyy · h:mm a') + ' UTC'; }
  catch { return t || '—'; }
};

// ── Shared card shell ─────────────────────────────────────────────────────────
const CardShell = ({ post, bannerContent, actionBar, children }) => {
  const hasMedia = (post.media_urls || []).length > 0;
  const isVideo  = post.post_type === 'video';

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {bannerContent}
      <div className="p-4">
        <div className="flex gap-4">
          {hasMedia && (
            <div className="w-20 h-20 rounded-lg overflow-hidden bg-gray-50 flex-shrink-0 border border-gray-200">
              {isVideo ? (
                <div className="w-full h-full flex items-center justify-center">
                  <FaVideo className="text-gray-300 text-2xl" />
                </div>
              ) : (
                <img src={post.media_urls[0]} alt="" className="w-full h-full object-cover"
                  onError={(e) => { e.target.style.display = 'none'; }} />
              )}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-line">
              {truncate(post.content)}
            </p>
            <div className="flex items-center gap-2 mt-2.5 flex-wrap">
              {(post.platforms || []).map((p) => {
                const Icon = PLATFORM_ICONS[p];
                return (
                  <span key={p} className={`flex items-center gap-1 text-xs font-medium capitalize ${PLATFORM_COLORS[p] || 'text-gray-500'}`}>
                    {Icon && <Icon className="text-sm" />}{p}
                  </span>
                );
              })}
              {hasMedia && (
                <span className="text-xs text-gray-400 ml-auto flex items-center gap-1">
                  {isVideo ? <FaVideo /> : <FaImage />}
                  {post.media_urls.length} {isVideo ? 'video' : `image${post.media_urls.length !== 1 ? 's' : ''}`}
                </span>
              )}
            </div>
          </div>
        </div>
        {children}
        {actionBar}
      </div>
    </div>
  );
};

// ── Awaiting Review card ───────────────────────────────────────────────────────
const AwaitingCard = ({ post, onApprove, onReject }) => {
  const [rejecting, setRejecting] = useState(false);
  const [note,      setNote]      = useState('');
  const [busy,      setBusy]      = useState(false);

  const handleApprove = async () => {
    setBusy(true);
    try { await onApprove(post.id); }
    finally { setBusy(false); }
  };

  const handleReject = async () => {
    setBusy(true);
    try { await onReject(post.id, note); }
    finally { setBusy(false); setRejecting(false); setNote(''); }
  };

  const banner = (
    <div className="bg-amber-50 border-b border-amber-100 px-4 py-2 flex items-center gap-2">
      <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
      <span className="text-xs font-semibold text-amber-700">Pending Review</span>
      {post.scheduled_time && (
        <span className="ml-auto text-xs text-amber-600 flex items-center gap-1">
          <FaClock className="text-[10px]" />{formatScheduled(post.scheduled_time)}
        </span>
      )}
    </div>
  );

  const actionBar = !rejecting && (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
      <button onClick={handleApprove} disabled={busy}
        className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg disabled:opacity-60 transition-colors">
        <FaCheck className="text-[10px]" />{busy ? 'Approving…' : 'Approve'}
      </button>
      <button onClick={() => setRejecting(true)} disabled={busy}
        className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold border border-red-200 text-red-500 hover:bg-red-50 rounded-lg disabled:opacity-60 transition-colors">
        <FaTimes className="text-[10px]" />Reject
      </button>
    </div>
  );

  return (
    <CardShell post={post} bannerContent={banner} actionBar={actionBar}>
      {rejecting && (
        <div className="mt-3 space-y-2">
          <textarea rows={2} placeholder="Reason for rejection (optional)…"
            value={note} onChange={(e) => setNote(e.target.value)}
            className="w-full text-sm border border-red-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-red-300 placeholder:text-gray-300" />
          <div className="flex items-center gap-2">
            <button onClick={handleReject} disabled={busy}
              className="px-3 py-1.5 text-xs font-semibold bg-red-500 hover:bg-red-600 text-white rounded-lg disabled:opacity-60 transition-colors">
              {busy ? 'Rejecting…' : 'Confirm Reject'}
            </button>
            <button onClick={() => { setRejecting(false); setNote(''); }}
              className="px-3 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}
    </CardShell>
  );
};

// ── Not Approved card ─────────────────────────────────────────────────────────
const RejectedCard = ({ post, onResubmit }) => {
  const [busy, setBusy] = useState(false);

  const handleResubmit = async () => {
    setBusy(true);
    try { await onResubmit(post.id); }
    finally { setBusy(false); }
  };

  const banner = (
    <div className="bg-red-50 border-b border-red-100 px-4 py-2 flex items-center gap-2">
      <div className="w-2 h-2 rounded-full bg-red-400" />
      <span className="text-xs font-semibold text-red-700">Not Approved</span>
    </div>
  );

  const actionBar = (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
      <button onClick={handleResubmit} disabled={busy}
        className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-gray-800 hover:bg-gray-700 text-white rounded-lg disabled:opacity-60 transition-colors">
        <FaRedo className="text-[10px]" />{busy ? 'Moving…' : 'Move to Draft'}
      </button>
    </div>
  );

  return (
    <CardShell post={post} bannerContent={banner} actionBar={actionBar}>
      {post.rejection_note && (
        <div className="mt-3 px-3 py-2.5 bg-red-50 border border-red-100 rounded-lg">
          <p className="text-xs text-red-500 font-semibold mb-0.5">Rejection reason</p>
          <p className="text-xs text-red-700">{post.rejection_note}</p>
        </div>
      )}
    </CardShell>
  );
};

// ── Expired Approval card ─────────────────────────────────────────────────────
const ExpiredCard = ({ post, onResubmit }) => {
  const [busy, setBusy] = useState(false);

  const handleResubmit = async () => {
    setBusy(true);
    try { await onResubmit(post.id); }
    finally { setBusy(false); }
  };

  const banner = (
    <div className="bg-gray-100 border-b border-gray-200 px-4 py-2 flex items-center gap-2">
      <FaExclamationTriangle className="text-gray-400 text-xs" />
      <span className="text-xs font-semibold text-gray-500">Approval Expired</span>
      {post.scheduled_time && (
        <span className="ml-auto text-xs text-gray-400 flex items-center gap-1">
          Was: {formatScheduled(post.scheduled_time)}
        </span>
      )}
    </div>
  );

  const actionBar = (
    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
      <button onClick={handleResubmit} disabled={busy}
        className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-gray-800 hover:bg-gray-700 text-white rounded-lg disabled:opacity-60 transition-colors">
        <FaRedo className="text-[10px]" />{busy ? 'Moving…' : 'Move to Draft'}
      </button>
    </div>
  );

  return <CardShell post={post} bannerContent={banner} actionBar={actionBar} />;
};

// ── Tab pill ──────────────────────────────────────────────────────────────────
const TabPill = ({ label, count, active, color = 'amber', onClick }) => {
  const activeColors = {
    amber: 'bg-amber-100 text-amber-800 border-amber-300',
    red:   'bg-red-100 text-red-700 border-red-300',
    gray:  'bg-gray-200 text-gray-600 border-gray-300',
  };
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
        active ? activeColors[color] : 'border-transparent text-gray-400 hover:text-gray-600 hover:bg-gray-100'
      }`}
    >
      {label}
      {count > 0 && (
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${active ? 'bg-offwhite bg-opacity-70' : 'bg-gray-200 text-gray-500'}`}>
          {count}
        </span>
      )}
    </button>
  );
};

// ── Empty state ───────────────────────────────────────────────────────────────
const EmptyState = ({ icon: Icon, iconColor, title, subtitle }) => (
  <div className="flex flex-col items-center justify-center py-20 text-center bg-offwhite rounded-xl border border-dashed border-gray-200">
    <Icon className={`text-4xl ${iconColor} mb-3`} />
    <p className="text-sm font-semibold text-gray-600">{title}</p>
    <p className="text-xs text-gray-400 mt-1 max-w-xs">{subtitle}</p>
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────
const ApprovalQueue = () => {
  const [awaiting,  setAwaiting]  = useState([]);
  const [rejected,  setRejected]  = useState([]);
  const [expired,   setExpired]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [activeTab, setActiveTab] = useState('awaiting');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [aw, rj, ex] = await Promise.all([
        getPosts({ status: 'pending_review' }),
        getPosts({ status: 'rejected' }),
        getPosts({ status: 'expired_approval' }),
      ]);
      setAwaiting(Array.isArray(aw) ? aw : []);
      setRejected(Array.isArray(rj) ? rj : []);
      setExpired(Array.isArray(ex) ? ex : []);
    } catch {
      if (!silent) toast.error('Failed to load approval queue');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (postId) => {
    try {
      const result = await approvePost(postId);
      // Optimistic update
      setAwaiting((prev) => prev.filter((p) => p.id !== postId));
      toast.success(result.status === 'scheduled' ? 'Post approved and scheduled ✓' : 'Post approved ✓');
      // Silent refresh to sync server state
      load(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to approve');
    }
  };

  const handleReject = async (postId, note) => {
    try {
      await rejectPost(postId, note);
      // Optimistic update
      const post = awaiting.find((p) => p.id === postId);
      setAwaiting((prev) => prev.filter((p) => p.id !== postId));
      if (post) setRejected((prev) => [{ ...post, status: 'rejected', rejection_note: note || null }, ...prev]);
      setActiveTab('rejected');
      toast.success('Post rejected — moved to Not Approved');
      // Silent refresh to sync server state
      load(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to reject');
    }
  };

  const handleResubmit = async (postId, from) => {
    try {
      await resubmitPost(postId);
      // Optimistic update
      if (from === 'rejected') setRejected((prev) => prev.filter((p) => p.id !== postId));
      if (from === 'expired')  setExpired((prev)  => prev.filter((p) => p.id !== postId));
      toast.success('Post moved to drafts — edit and resubmit when ready');
      // Silent refresh to sync server state
      load(true);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to move post');
    }
  };

  const tabs = [
    { key: 'awaiting', label: 'Awaiting Review', count: awaiting.length, color: 'amber' },
    { key: 'rejected', label: 'Not Approved',    count: rejected.length, color: 'red' },
    { key: 'expired',  label: 'Expired',          count: expired.length,  color: 'gray' },
  ];

  const renderContent = () => {
    if (loading) {
      return (
        <div className="space-y-4">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-40 animate-pulse" />
          ))}
        </div>
      );
    }

    if (activeTab === 'awaiting') {
      if (!awaiting.length) return (
        <EmptyState icon={FaCheckDouble} iconColor="text-green-300"
          title="All clear — nothing to review"
          subtitle="Posts submitted for review will appear here. Submit a draft from the Content Library." />
      );
      return (
        <div className="space-y-4">
          {awaiting.map((post) => (
            <AwaitingCard key={post.id} post={post} onApprove={handleApprove} onReject={handleReject} />
          ))}
        </div>
      );
    }

    if (activeTab === 'rejected') {
      if (!rejected.length) return (
        <EmptyState icon={FaTimes} iconColor="text-red-200"
          title="No rejected posts"
          subtitle="Posts that are rejected will appear here. Move them back to Draft to edit and resubmit." />
      );
      return (
        <div className="space-y-4">
          {rejected.map((post) => (
            <RejectedCard key={post.id} post={post} onResubmit={(id) => handleResubmit(id, 'rejected')} />
          ))}
        </div>
      );
    }

    if (activeTab === 'expired') {
      if (!expired.length) return (
        <EmptyState icon={FaClock} iconColor="text-gray-300"
          title="No expired approvals"
          subtitle="Posts that weren't approved before their scheduled time will appear here." />
      );
      return (
        <div className="space-y-4">
          {expired.map((post) => (
            <ExpiredCard key={post.id} post={post} onResubmit={(id) => handleResubmit(id, 'expired')} />
          ))}
        </div>
      );
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <FaCheckDouble className="text-green-500" />
              Approval Queue
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {loading ? 'Loading…' : `${awaiting.length + rejected.length + expired.length} total posts`}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-5 bg-gray-50 rounded-xl p-1 w-fit">
          {tabs.map((tab) => (
            <TabPill key={tab.key} label={tab.label} count={tab.count}
              active={activeTab === tab.key} color={tab.color}
              onClick={() => setActiveTab(tab.key)} />
          ))}
        </div>

        {/* Content */}
        {renderContent()}
      </div>
    </DashboardLayout>
  );
};

export default ApprovalQueue;
