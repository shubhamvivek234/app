import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FaCheck,
  FaCheckDouble,
  FaClock,
  FaExclamationTriangle,
  FaHistory,
  FaImage,
  FaPaperPlane,
  FaRedo,
  FaTimes,
  FaUserCheck,
  FaVideo,
  FaShareAlt,
} from 'react-icons/fa';
import { toast } from 'sonner';

import DashboardLayout from '@/components/DashboardLayout';
import ShareReviewModal from '@/components/ShareReviewModal';
import { useAuth } from '@/context/AuthContext';
import {
  approvePost,
  bulkApprovePosts,
  bulkRejectPosts,
  getApprovalActivity,
  getApprovalQueue,
  rejectPost,
  resubmitPost,
  returnPostToDraft,
} from '@/lib/api';
import { formatScheduledDateTime, getPostScheduledTimeZone } from '@/lib/scheduledTime';

const PLATFORM_STYLES = {
  instagram: 'border-pink-200 bg-pink-50 text-pink-700',
  facebook: 'border-blue-200 bg-blue-50 text-blue-700',
  youtube: 'border-red-200 bg-red-50 text-red-700',
  twitter: 'border-slate-200 bg-slate-50 text-slate-700',
  linkedin: 'border-sky-200 bg-sky-50 text-sky-700',
  tiktok: 'border-slate-900 bg-slate-900 text-white',
  threads: 'border-slate-300 bg-white text-slate-700',
};

const formatScheduled = (value, timeZone = null) => {
  if (!value) return 'No scheduled time';
  try {
    return formatScheduledDateTime(value, timeZone, { includeTimeZone: Boolean(timeZone) });
  } catch {
    return 'No scheduled time';
  }
};

const relativeTime = (value) => {
  if (!value) return 'recently';
  try {
    return formatDistanceToNow(new Date(value), { addSuffix: true });
  } catch {
    return 'recently';
  }
};

const primaryMedia = (post) => post.thumbnail_urls?.[0] || post.media_urls?.[0] || null;

const ACTIVITY_LABELS = {
  submitted: 'Submitted for review',
  resubmitted: 'Resubmitted',
  approved: 'Approved',
  bulk_approved: 'Approved in bulk',
  changes_requested: 'Changes requested',
  bulk_changes_requested: 'Changes requested in bulk',
  returned: 'Returned to draft',
};

const activityLabel = (action) => ACTIVITY_LABELS[action] || action || 'Approval activity';

const TabButton = ({ active, count, label, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition ${
      active
        ? 'border-slate-900 bg-slate-900 text-white'
        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
    }`}
  >
    {label}
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${active ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-600'}`}>
      {count}
    </span>
  </button>
);

const ApprovalTimeline = ({ post }) => {
  const [expanded, setExpanded] = useState(false);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const latest = post.approval_latest_activity;

  const loadActivity = async () => {
    if (loaded || loading) return;
    setLoading(true);
    try {
      const items = await getApprovalActivity(post.id);
      setActivity(Array.isArray(items) ? items : []);
      setLoaded(true);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to load approval timeline');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      await loadActivity();
    }
  };

  if (!latest && !expanded) {
    return null;
  }

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
          <FaHistory className="text-slate-400" />
          Approval timeline
        </span>
        <span className="text-xs font-medium text-slate-500">
          {expanded ? 'Hide' : 'View all'}
        </span>
      </button>

      {latest ? (
        <div className="mt-3 rounded-md bg-white px-3 py-2 text-sm text-slate-700">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-900">{activityLabel(latest.action)}</span>
            <span className="text-xs text-slate-400">{relativeTime(latest.created_at)}</span>
          </div>
          {latest.reason ? <p className="mt-1 text-xs leading-5 text-slate-500">{latest.reason}</p> : null}
        </div>
      ) : null}

      {expanded ? (
        <div className="mt-3 space-y-2">
          {loading ? (
            <div className="h-16 animate-pulse rounded-md bg-white" />
          ) : activity.length === 0 ? (
            <p className="rounded-md bg-white px-3 py-2 text-xs text-slate-500">No approval activity has been recorded yet.</p>
          ) : (
            activity.map((item) => (
              <div key={item.id || `${item.action}-${item.created_at}`} className="rounded-md bg-white px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{activityLabel(item.action)}</span>
                  <span className="text-xs text-slate-400">{relativeTime(item.created_at)}</span>
                </div>
                {item.reason ? <p className="mt-1 text-xs leading-5 text-slate-500">{item.reason}</p> : null}
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
};

const ApprovalCard = ({
  post,
  mode,
  currentUserId,
  onApprove,
  onReject,
  onResubmit,
  onReturnToDraft,
  onOpenDraft,
  busyId,
  permissions,
  selected,
  highlighted,
}) => {
  const [showReject, setShowReject] = useState(false);
  const [reason, setReason] = useState('');
  const mediaUrl = primaryMedia(post);
  const isVideo = post.post_type === 'video';
  const isOwner = post.user_id === currentUserId;
  const isBusy = busyId === post.id;
  const scheduledTimeZone = getPostScheduledTimeZone(post);
  const canReview = Boolean(permissions?.can_review);
  const canResubmit = Boolean(permissions?.can_resubmit) && isOwner;

  const creatorLabel = post.creator_display_name || post.creator_email || 'Workspace member';
  const reasonText = post.rejection_reason || post.rejection_note;

  return (
    <article className={`rounded-lg border shadow-sm transition-all duration-500 ${
      highlighted
        ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50/5'
        : 'border-slate-200 bg-white'
    }`}>
      <div className="flex flex-col gap-4 p-4 lg:flex-row">
        {mode === 'awaiting' && canReview && onToggleSelected ? (
          <label className="flex items-start pt-1">
            <input
              type="checkbox"
              checked={Boolean(selected)}
              onChange={() => onToggleSelected(post.id)}
              className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
              aria-label={`Select ${creatorLabel} post for bulk review`}
            />
          </label>
        ) : null}

        <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
          {mediaUrl ? (
            <img src={mediaUrl} alt="" className="h-full w-full object-cover" />
          ) : isVideo ? (
            <FaVideo className="text-2xl text-slate-300" />
          ) : (
            <FaImage className="text-2xl text-slate-300" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {(post.platforms || []).map((platform) => (
              <span
                key={`${post.id}-${platform}`}
                className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold capitalize ${PLATFORM_STYLES[platform] || PLATFORM_STYLES.twitter}`}
              >
                {platform}
              </span>
            ))}
            {mode === 'awaiting' ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800">
                Pending approval
              </span>
            ) : null}
            {mode === 'changes_requested' ? (
              <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-700">
                Changes requested
              </span>
            ) : null}
            {mode === 'expired' ? (
              <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700">
                Approval expired
              </span>
            ) : null}
            {post.approval_assigned_to_me ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">
                <FaUserCheck className="text-[10px]" />
                Assigned to you
              </span>
            ) : null}
            {post.approval_overdue ? (
              <span className="rounded-full border border-red-200 bg-red-50 px-2.5 py-1 text-[11px] font-semibold text-red-700">
                Review overdue
              </span>
            ) : null}
            {!post.approval_overdue && post.approval_expiring_soon ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800">
                Due soon
              </span>
            ) : null}
          </div>

          <p className="mt-3 text-sm leading-6 text-slate-800 whitespace-pre-line">
            {post.content || 'No post copy added yet.'}
          </p>

          <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Creator</span>
              <span>{creatorLabel}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Scheduled</span>
              <span>{formatScheduled(post.scheduled_time, scheduledTimeZone)}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Review due</span>
              <span>{formatScheduled(post.approval_due_at, scheduledTimeZone)}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Updated</span>
              <span>{relativeTime(post.updated_at || post.created_at)}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Media</span>
              <span>{post.post_type || ((post.media_urls || []).length ? 'media' : 'text')}</span>
            </div>
          </div>

          {reasonText ? (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {reasonText}
            </div>
          ) : null}

          <ApprovalTimeline post={post} />

          {mode === 'awaiting' && showReject ? (
            <div className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <textarea
                rows={3}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Explain what needs to change before this can go live."
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-slate-300"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onReject(post.id, reason, () => {
                    setShowReject(false);
                    setReason('');
                  })}
                  disabled={isBusy}
                  className="inline-flex h-10 items-center gap-2 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-60"
                >
                  <FaTimes className="text-xs" />
                  {isBusy ? 'Sending…' : 'Request changes'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowReject(false);
                    setReason('');
                  }}
                  className="inline-flex h-10 items-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {mode === 'awaiting' && !showReject ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canReview ? (
                <>
                  <button
                    type="button"
                    onClick={() => onApprove(post.id)}
                    disabled={isBusy}
                    className="inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                  >
                    <FaCheck className="text-xs" />
                    {isBusy ? 'Approving…' : 'Approve'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowReject(true)}
                    disabled={isBusy}
                    className="inline-flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-white px-4 text-sm font-semibold text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                  >
                    <FaTimes className="text-xs" />
                    Request changes
                  </button>
                </>
              ) : (
                <span className="text-sm text-slate-500">
                  Your role can view this queue, but it cannot approve or request changes.
                </span>
              )}
            </div>
          ) : null}

          {mode === 'changes_requested' ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canResubmit ? (
                <>
                  <button
                    type="button"
                    onClick={() => onOpenDraft(post.id)}
                    className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
                  >
                    <FaRedo className="text-xs" />
                    Edit draft
                  </button>
                  <button
                    type="button"
                    onClick={() => onResubmit(post.id)}
                    disabled={isBusy}
                    className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
                  >
                    <FaCheckDouble className="text-xs" />
                    {isBusy ? 'Resubmitting…' : 'Resubmit for review'}
                  </button>
                </>
              ) : (
                <span className="text-sm text-slate-500">Waiting on the creator to update and resubmit this draft.</span>
              )}
            </div>
          ) : null}

          {mode === 'expired' ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canReview ? (
                <button
                  type="button"
                  onClick={() => onReturnToDraft(post.id, { openAfterReturn: isOwner })}
                  disabled={isBusy}
                  className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                >
                  <FaPaperPlane className="text-xs" />
                  {isBusy ? 'Returning…' : isOwner ? 'Return to draft & edit' : 'Return to draft'}
                </button>
              ) : (
                <span className="text-sm text-slate-500">
                  An editor or admin needs to return this item to draft before it can be rescheduled.
                </span>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
};

const EmptyState = ({ icon: Icon, title, description }) => (
  <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center">
    <Icon className="mx-auto text-3xl text-slate-300" />
    <h3 className="mt-4 text-base font-semibold text-slate-900">{title}</h3>
    <p className="mt-2 text-sm text-slate-500">{description}</p>
  </div>
);

const ApprovalQueue = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [queue, setQueue] = useState({ awaiting: [], changes_requested: [], expired: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('awaiting');
  const [busyId, setBusyId] = useState(null);
  const [loadErrorStatus, setLoadErrorStatus] = useState(null);
  const [reviewFilter, setReviewFilter] = useState('all');
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkReason, setBulkReason] = useState('');
  const [showShareModal, setShowShareModal] = useState(false);

  const highlightedPostId = searchParams.get('post_id');

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setLoadErrorStatus(null);
    try {
      const data = await getApprovalQueue();
      setQueue(data);
    } catch (error) {
      setLoadErrorStatus(error?.response?.status || null);
      if (!silent) {
        if (error?.response?.status !== 403) {
          toast.error(error?.response?.data?.detail || 'Failed to load approval queue');
        }
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!highlightedPostId || !queue) return;
    if (queue.awaiting?.some(p => p.id === highlightedPostId)) {
      setActiveTab('awaiting');
    } else if (queue.changes_requested?.some(p => p.id === highlightedPostId)) {
      setActiveTab('changes_requested');
    } else if (queue.expired?.some(p => p.id === highlightedPostId)) {
      setActiveTab('expired');
    }
  }, [highlightedPostId, queue]);

  useEffect(() => {
    setSelectedIds([]);
    setBulkReason('');
  }, [activeTab, reviewFilter]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await load({ silent: true });
    } finally {
      setRefreshing(false);
    }
  };

  const handleApprove = async (postId) => {
    setBusyId(postId);
    try {
      await approvePost(postId);
      await load({ silent: true });
      toast.success('Post approved');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to approve post');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (postId, reason, onDone) => {
    setBusyId(postId);
    try {
      await rejectPost(postId, reason);
      await load({ silent: true });
      setActiveTab('changes_requested');
      onDone?.();
      toast.success('Changes requested');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to request changes');
    } finally {
      setBusyId(null);
    }
  };

  const handleBulkApprove = async () => {
    if (selectedIds.length === 0) return;
    setBusyId('bulk-approve');
    try {
      const result = await bulkApprovePosts(selectedIds);
      await load({ silent: true });
      setSelectedIds([]);
      const errors = result?.errors || [];
      if (errors.length) {
        toast.warning(`${result?.approved?.length || 0} approved, ${errors.length} could not be approved`);
      } else {
        toast.success(`${result?.approved?.length || selectedIds.length} post${selectedIds.length === 1 ? '' : 's'} approved`);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to approve selected posts');
    } finally {
      setBusyId(null);
    }
  };

  const handleBulkReject = async () => {
    const reason = bulkReason.trim();
    if (selectedIds.length === 0) return;
    if (!reason) {
      toast.error('Add a reason before requesting changes in bulk');
      return;
    }
    setBusyId('bulk-reject');
    try {
      const result = await bulkRejectPosts(selectedIds, reason);
      await load({ silent: true });
      setActiveTab('changes_requested');
      setSelectedIds([]);
      setBulkReason('');
      const errors = result?.errors || [];
      if (errors.length) {
        toast.warning(`${result?.rejected?.length || 0} returned, ${errors.length} could not be updated`);
      } else {
        toast.success(`${result?.rejected?.length || selectedIds.length} post${selectedIds.length === 1 ? '' : 's'} returned for changes`);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to request changes for selected posts');
    } finally {
      setBusyId(null);
    }
  };

  const handleResubmit = async (postId) => {
    setBusyId(postId);
    try {
      await resubmitPost(postId, {});
      await load({ silent: true });
      setActiveTab('awaiting');
      toast.success('Post resubmitted for review');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to resubmit post');
    } finally {
      setBusyId(null);
    }
  };

  const handleReturnToDraft = async (postId, { openAfterReturn = false } = {}) => {
    setBusyId(postId);
    try {
      await returnPostToDraft(postId);
      await load({ silent: true });
      toast.success(openAfterReturn ? 'Post returned to draft. Opening the editor…' : 'Post returned to draft');
      if (openAfterReturn) {
        navigate(`/create-post?edit=${encodeURIComponent(postId)}`);
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to return post to draft');
    } finally {
      setBusyId(null);
    }
  };

  const handleOpenDraft = useCallback((postId) => {
    navigate(`/create-post?edit=${encodeURIComponent(postId)}`);
  }, [navigate]);

  const tabs = useMemo(() => ([
    { key: 'awaiting', label: 'Awaiting Review', count: queue.summary?.awaiting || 0 },
    { key: 'changes_requested', label: 'Changes Requested', count: queue.summary?.changes_requested || 0 },
    { key: 'expired', label: 'Expired', count: queue.summary?.expired || 0 },
  ]), [queue.summary]);

  const activeItems = useMemo(() => {
    const activeItemsRaw = queue[activeTab] || [];
    if (activeTab !== 'awaiting') return activeItemsRaw;
    if (reviewFilter === 'mine') return activeItemsRaw.filter((post) => post.approval_assigned_to_me);
    if (reviewFilter === 'overdue') return activeItemsRaw.filter((post) => post.approval_overdue);
    if (reviewFilter === 'soon') return activeItemsRaw.filter((post) => post.approval_expiring_soon && !post.approval_overdue);
    return activeItemsRaw;
  }, [queue, activeTab, reviewFilter]);
  const queuePermissions = queue.permissions || {};
  const selectedVisibleCount = selectedIds.filter((id) => activeItems.some((post) => post.id === id)).length;
  const canBulkReview = activeTab === 'awaiting' && queuePermissions.can_review;

  const toggleSelected = useCallback((postId) => {
    setSelectedIds((current) => (
      current.includes(postId)
        ? current.filter((id) => id !== postId)
        : [...current, postId]
    ));
  }, []);

  const toggleAllVisible = useCallback(() => {
    const visibleIds = activeItems.map((post) => post.id);
    setSelectedIds((current) => {
      const allSelected = visibleIds.length > 0 && visibleIds.every((id) => current.includes(id));
      if (allSelected) {
        return current.filter((id) => !visibleIds.includes(id));
      }
      return Array.from(new Set([...current, ...visibleIds]));
    });
  }, [activeItems]);

  if (!loading && loadErrorStatus === 403) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:px-8">
          <section className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-white">
              <FaCheckDouble className="text-sm" />
            </div>
            <h1 className="mt-5 text-2xl font-semibold text-slate-950">Approval access is limited in this workspace</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Your current workspace role can’t open the Approvals queue. Ask an admin or owner to grant content review access if you need to inspect or approve scheduled posts.
            </p>
          </section>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <FaCheckDouble className="text-sm" />
                </div>
                <div>
                  <h1 className="text-2xl font-semibold text-slate-950">Approvals</h1>
                  <p className="text-sm text-slate-500">Workspace review queue for scheduled content.</p>
                </div>
              </div>
              <p className="max-w-2xl text-sm leading-6 text-slate-600">
                Review pending posts, track requested changes, and pull expired approvals back into draft before they miss the publish window.
              </p>
              <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">
                Current role: {queue.current_user_role || user?.workspace_role || 'viewer'}
                {queuePermissions.can_review ? ' • can review and recover items' : ' • read-only queue access'}
              </p>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setShowShareModal(true)}
                  className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold rounded-xl border border-indigo-200/60 shadow-2xs transition-all active:scale-95"
                >
                  <FaShareAlt className="text-xs" /> Share Client Review Link
                </button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Awaiting</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{queue.summary?.awaiting || 0}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Changes requested</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{queue.summary?.changes_requested || 0}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Expired</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{queue.summary?.expired || 0}</p>
              </div>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            {tabs.map((tab) => (
              <TabButton
                key={tab.key}
                active={activeTab === tab.key}
                count={tab.count}
                label={tab.label}
                onClick={() => setActiveTab(tab.key)}
              />
            ))}
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="ml-auto inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"
            >
              <FaRedo className={`text-xs ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {activeTab === 'awaiting' ? (
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
              {[
                ['all', 'All awaiting'],
                ['mine', 'Assigned to me'],
                ['overdue', 'Overdue'],
                ['soon', 'Due soon'],
              ].map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setReviewFilter(key)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    reviewFilter === key
                      ? 'border-slate-900 bg-slate-900 text-white'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          ) : null}

          {canBulkReview && activeItems.length > 0 ? (
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={toggleAllVisible}
                    className="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
                  >
                    {selectedVisibleCount === activeItems.length ? 'Clear visible' : 'Select visible'}
                  </button>
                  <span className="text-sm text-slate-600">
                    {selectedIds.length} selected for bulk review
                  </span>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    value={bulkReason}
                    onChange={(event) => setBulkReason(event.target.value)}
                    placeholder="Reason for bulk changes"
                    className="h-9 min-w-[15rem] rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-slate-300"
                  />
                  <button
                    type="button"
                    onClick={handleBulkReject}
                    disabled={selectedIds.length === 0 || busyId === 'bulk-reject'}
                    className="inline-flex h-9 items-center justify-center rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                  >
                    {busyId === 'bulk-reject' ? 'Sending…' : 'Request changes'}
                  </button>
                  <button
                    type="button"
                    onClick={handleBulkApprove}
                    disabled={selectedIds.length === 0 || busyId === 'bulk-approve'}
                    className="inline-flex h-9 items-center justify-center rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-60"
                  >
                    {busyId === 'bulk-approve' ? 'Approving…' : 'Approve selected'}
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </section>

        <section className="space-y-4">
          {loading ? (
            <div className="space-y-4">
              {[0, 1, 2].map((index) => (
                <div key={index} className="h-44 animate-pulse rounded-lg border border-slate-200 bg-slate-50" />
              ))}
            </div>
          ) : activeItems.length === 0 ? (
            <>
              {activeTab === 'awaiting' ? (
                <EmptyState
                  icon={FaCheck}
                  title="Nothing is waiting for review"
                  description="Drafts submitted for approval will appear here once a workspace member sends them into review."
                />
              ) : null}
              {activeTab === 'changes_requested' ? (
                <EmptyState
                  icon={FaTimes}
                  title="No drafts are waiting on changes"
                  description="Rejected review items will show up here until their creator resubmits them."
                />
              ) : null}
              {activeTab === 'expired' ? (
                <EmptyState
                  icon={FaClock}
                  title="No approvals have expired"
                  description="Pending approvals with past scheduled times will land here so they can be returned to draft."
                />
              ) : null}
            </>
          ) : (
            activeItems.map((post) => (
              <ApprovalCard
                key={post.id}
                post={post}
                mode={activeTab}
                currentUserId={user?.user_id}
                onApprove={handleApprove}
                onReject={handleReject}
                onResubmit={handleResubmit}
                onReturnToDraft={handleReturnToDraft}
                onOpenDraft={handleOpenDraft}
                busyId={busyId}
                permissions={queuePermissions}
                selected={selectedIds.includes(post.id)}
                onToggleSelected={canBulkReview ? toggleSelected : null}
                highlighted={post.id === highlightedPostId}
              />
            ))
          )}
        </section>
      </div>
      <ShareReviewModal isOpen={showShareModal} onClose={() => setShowShareModal(false)} />
    </DashboardLayout>
  );
};

export default ApprovalQueue;
