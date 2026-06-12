import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import {
  FaCheck,
  FaCheckDouble,
  FaClock,
  FaExclamationTriangle,
  FaImage,
  FaPaperPlane,
  FaRedo,
  FaTimes,
  FaVideo,
} from 'react-icons/fa';
import { toast } from 'sonner';

import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import {
  approvePost,
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
    <article className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-4 p-4 lg:flex-row">
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
          </div>

          <p className="mt-3 text-sm leading-6 text-slate-800 whitespace-pre-line">
            {post.content || 'No post copy added yet.'}
          </p>

          <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Creator</span>
              <span>{creatorLabel}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-[0.12em] text-slate-400">Scheduled</span>
              <span>{formatScheduled(post.scheduled_time, scheduledTimeZone)}</span>
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
  const [queue, setQueue] = useState({ awaiting: [], changes_requested: [], expired: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('awaiting');
  const [busyId, setBusyId] = useState(null);
  const [loadErrorStatus, setLoadErrorStatus] = useState(null);

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

  const activeItems = queue[activeTab] || [];
  const queuePermissions = queue.permissions || {};

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
              />
            ))
          )}
        </section>
      </div>
    </DashboardLayout>
  );
};

export default ApprovalQueue;
