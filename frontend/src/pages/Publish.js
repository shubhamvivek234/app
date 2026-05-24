import React, { useEffect, useState, useCallback } from 'react';
import { toast } from 'sonner';
import DashboardLayout from '@/components/DashboardLayout';
import PostCard from '@/components/publish/PostCard';
import {
  getSocialAccounts,
  getPublishFeed,
  getInbox,
  updateInboxMessage,
  getPostComments,
  replyToComment,
  sendDmReply,
  syncInboxConversations,
} from '@/lib/api';
import {
  FaTwitter, FaInstagram, FaLinkedin, FaFacebook,
  FaTiktok, FaYoutube, FaPinterest, FaPlus, FaSync,
  FaInbox, FaRss, FaReply,
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

// ── Platform metadata ─────────────────────────────────────────────────────────
const PLATFORM_META = {
  facebook:  { icon: FaFacebook,  color: 'text-blue-600',  ring: '#1877F2', label: 'Facebook' },
  twitter:   { icon: FaTwitter,   color: 'text-sky-500',   ring: '#1DA1F2', label: 'X (Twitter)' },
  linkedin:  { icon: FaLinkedin,  color: 'text-blue-700',  ring: '#0A66C2', label: 'LinkedIn' },
  instagram: { icon: FaInstagram, color: 'text-pink-500',  ring: '#E1306C', label: 'Instagram' },
  pinterest: { icon: FaPinterest, color: 'text-red-600',   ring: '#E60023', label: 'Pinterest' },
  youtube:   { icon: FaYoutube,   color: 'text-red-500',   ring: '#FF0000', label: 'YouTube' },
  tiktok:    { icon: FaTiktok,    color: 'text-gray-900',  ring: '#010101', label: 'TikTok' },
  bluesky:   { icon: SiBluesky,   color: 'text-blue-500',  ring: '#0085FF', label: 'Bluesky' },
  threads:   { icon: SiThreads,   color: 'text-gray-900',  ring: '#101010', label: 'Threads' },
};

const AVATAR_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
  'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
];
const avatarColor = (name = '') =>
  AVATAR_COLORS[(name.charCodeAt(0) || 0) % AVATAR_COLORS.length];

const DM_REPLY_PLATFORMS = new Set(['instagram', 'facebook', 'bluesky']);
const COMMENT_REPLY_PLATFORMS = new Set(['instagram', 'facebook', 'reddit', 'youtube', 'bluesky']);

// ── Group posts by calendar date ──────────────────────────────────────────────
const groupByDate = (posts) => {
  const groups = {};
  for (const post of posts) {
    const raw = post.published_at;
    let label = 'Unknown date';
    if (raw) {
      try {
        label = new Date(raw).toLocaleDateString('en-GB', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        });
      } catch {
        label = raw;
      }
    }
    if (!groups[label]) groups[label] = [];
    groups[label].push(post);
  }
  return Object.entries(groups); // [[label, posts[]], ...]
};

// ── Format relative time ──────────────────────────────────────────────────────
const formatRelative = (isoString) => {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  } catch {
    return '';
  }
};

// ── Account pill in the connected-accounts strip ──────────────────────────────
const AccountPill = ({ account, selected, onClick }) => {
  const meta = PLATFORM_META[account.platform] || {};
  const Icon = meta.icon;
  const ringColor = meta.ring || '#3B82F6';
  const name = account.platform_username || account.platform;

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2.5 px-3 py-2 rounded-xl border transition-all text-sm font-medium ${
        selected
          ? 'border-green-400 bg-green-50 text-green-800 shadow-sm'
          : 'border-gray-200 bg-offwhite text-gray-700 hover:border-green-200 hover:bg-green-50/50'
      }`}
    >
      {/* Avatar */}
      <div className="relative flex-shrink-0">
        {account.picture_url ? (
          <img
            src={account.picture_url}
            alt={name}
            className="w-8 h-8 rounded-full object-cover"
            style={{ boxShadow: selected ? `0 0 0 2px white, 0 0 0 3px ${ringColor}` : undefined }}
          />
        ) : (
          <div
            className={`w-8 h-8 rounded-full ${avatarColor(name)} flex items-center justify-center text-white text-xs font-bold`}
            style={{ boxShadow: selected ? `0 0 0 2px white, 0 0 0 3px ${ringColor}` : undefined }}
          >
            {name.charAt(0).toUpperCase()}
          </div>
        )}
        {Icon && (
          <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-offwhite border border-gray-100 flex items-center justify-center shadow-sm">
            <Icon className={`text-[9px] ${meta.color}`} />
          </div>
        )}
      </div>
      <span className="max-w-[100px] truncate">{name}</span>
    </button>
  );
};

// ── Skeleton card ─────────────────────────────────────────────────────────────
const SkeletonPostCard = () => (
  <div className="bg-offwhite rounded-xl border border-gray-100 p-4 animate-pulse flex gap-4">
    <div className="w-16 flex-shrink-0">
      <div className="h-3 bg-gray-50 rounded w-10 ml-auto" />
    </div>
    <div className="flex-1 space-y-3">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-full bg-gray-50 flex-shrink-0" />
        <div className="space-y-1">
          <div className="h-3 bg-gray-50 rounded w-24" />
          <div className="h-2.5 bg-gray-50 rounded w-16" />
        </div>
      </div>
      <div className="space-y-1.5">
        <div className="h-3 bg-gray-50 rounded w-full" />
        <div className="h-3 bg-gray-50 rounded w-3/4" />
      </div>
      <div className="flex gap-4">
        <div className="h-3 bg-gray-50 rounded w-12" />
        <div className="h-3 bg-gray-50 rounded w-12" />
        <div className="h-3 bg-gray-50 rounded w-12" />
      </div>
    </div>
    <div className="w-20 h-20 rounded-lg bg-gray-50 flex-shrink-0" />
  </div>
);

// ── Main page ─────────────────────────────────────────────────────────────────
const Publish = () => {
  // ── Tab state ──
  const [activeTab, setActiveTab] = useState('feed'); // 'feed' | 'inbox'

  // ── Feed state ──
  const [accounts, setAccounts]               = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [activePlatform, setActivePlatform]   = useState('');
  const [posts, setPosts]                     = useState([]);
  const [feedLoading, setFeedLoading]         = useState(false);
  const [feedError, setFeedError]             = useState(null);
  const [feedWarnings, setFeedWarnings]       = useState([]);

  // ── Inbox state ──
  const [inboxPlatform, setInboxPlatform]   = useState('');
  const [inboxType, setInboxType]           = useState(''); // '' | 'comment' | 'dm'
  const [inboxMessages, setInboxMessages]   = useState([]);
  const [inboxCapabilities, setInboxCapabilities] = useState({});
  const [inboxSelected, setInboxSelected]   = useState(null);
  const [inboxReply, setInboxReply]         = useState('');
  const [inboxLoading, setInboxLoading]     = useState(false);
  const [inboxSending, setInboxSending]     = useState(false);
  const [syncing, setSyncing]               = useState(false);

  // ── Load connected accounts ──
  useEffect(() => {
    getSocialAccounts()
      .then((data) => setAccounts(data || []))
      .catch(() => setAccounts([]))
      .finally(() => setAccountsLoading(false));
  }, []);

  // ── Fetch feed ──
  const fetchFeed = useCallback(async () => {
    setFeedLoading(true);
    setFeedError(null);
    try {
      const params = { limit: 50 };
      if (activePlatform) params.platform = activePlatform;
      if (selectedAccounts.length === 1) params.accountId = selectedAccounts[0];
      const data = await getPublishFeed(params);
      setPosts(data.posts || []);
      setFeedWarnings(data.warnings || []);
    } catch (err) {
      setFeedError('Failed to load posts. Please try again.');
      setPosts([]);
      setFeedWarnings([]);
    } finally {
      setFeedLoading(false);
    }
  }, [activePlatform, selectedAccounts]);

  useEffect(() => {
    if (!accountsLoading) fetchFeed();
  }, [accountsLoading, fetchFeed]);

  // ── Fetch inbox ──
  const fetchInbox = useCallback(async () => {
    setInboxLoading(true);
    try {
      const data = await getInbox({
        platform: inboxPlatform || undefined,
        type: inboxType || undefined,
      });
      setInboxMessages(Array.isArray(data) ? data : (data.messages || []));
      setInboxCapabilities(Array.isArray(data) ? {} : (data.capabilities || {}));
    } catch {
      setInboxCapabilities({});
      toast.error('Failed to load messages');
    } finally {
      setInboxLoading(false);
    }
  }, [inboxPlatform, inboxType]);

  useEffect(() => {
    if (activeTab === 'inbox') fetchInbox();
  }, [activeTab, fetchInbox]);

  useEffect(() => {
    if (!inboxSelected) return;
    const freshSelected = inboxMessages.find((message) => message.id === inboxSelected.id);
    if (!freshSelected) {
      setInboxSelected(null);
      return;
    }
    if (freshSelected !== inboxSelected) {
      setInboxSelected(freshSelected);
    }
  }, [inboxMessages, inboxSelected]);

  useEffect(() => {
    if (!inboxPlatform) return;
    const caps = inboxCapabilities[inboxPlatform];
    if (!caps) {
      setInboxPlatform('');
      setInboxSelected(null);
      return;
    }
    if (inboxType === 'dm' && !caps.supports_dm_inbox) {
      setInboxPlatform('');
      setInboxSelected(null);
      return;
    }
    if (inboxType === 'comment' && !caps.supports_comment_inbox) {
      setInboxPlatform('');
      setInboxSelected(null);
    }
  }, [inboxCapabilities, inboxPlatform, inboxType]);

  // ── Sync supported inbox items from platforms into cache ──
  const handleSyncDMs = async () => {
    setSyncing(true);
    try {
      const selectedInboxAccountId = (
        inboxPlatform &&
        activePlatform === inboxPlatform &&
        selectedAccounts.length === 1
      ) ? selectedAccounts[0] : undefined;

      const result = await syncInboxConversations({
        ...(inboxPlatform ? { platform: inboxPlatform } : {}),
        ...(inboxType ? { type: inboxType } : {}),
        ...(selectedInboxAccountId ? { accountId: selectedInboxAccountId } : {}),
      });

      const syncedTotal = Number(result?.synced_dms || 0) + Number(result?.synced_comments || 0);
      if (syncedTotal > 0) {
        toast.success(`Synced ${syncedTotal} inbox item${syncedTotal !== 1 ? 's' : ''}`);
      } else if (result?.errors?.length) {
        toast.error('Inbox sync completed with errors');
      } else {
        toast.info('No new inbox items to sync');
      }
      await fetchInbox();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Inbox sync failed');
    } finally {
      setSyncing(false);
    }
  };

  // ── Select platform (clears account selection) ──
  const handlePlatformSelect = (plat) => {
    setActivePlatform((prev) => {
      const next = prev === plat ? '' : plat;
      setSelectedAccounts([]);
      return next;
    });
  };

  // ── Toggle account pill ──
  const toggleAccount = (accountId) => {
    setSelectedAccounts((prev) =>
      prev.includes(accountId)
        ? prev.filter((id) => id !== accountId)
        : [...prev, accountId]
    );
  };

  // ── Fetch comments for a post ──
  const handleFetchComments = async (post) => {
    try {
      return await getPostComments(post.platform, post.platform_post_id, post.account_id);
    } catch (err) {
      toast.error('Failed to load comments');
      return { comments: [] };
    }
  };

  // ── Reply to a comment on a post ──
  const handleReplyToComment = async (post, comment, text) => {
    try {
      const data = {
        text,
        account_id: post.account_id,
        post_id: post.platform_post_id,
      };
      // For Bluesky, pass extra threading info
      if (post.platform === 'bluesky' && comment) {
        data.parent_cid = comment.cid || comment.comment_cid;
        data.root_uri = comment.root_uri;
        data.root_cid = comment.root_cid;
      }
      await replyToComment(post.platform, post.platform_post_id, comment.id, data);
      toast.success('Reply posted!');
    } catch (err) {
      toast.error('Failed to post reply: ' + (err?.response?.data?.detail || err.message));
    }
  };

  // ── Reply to inbox message ──
  const handleInboxReply = async () => {
    if (!inboxReply.trim() || !inboxSelected || inboxSending) return;
    setInboxSending(true);
    const trimmedReply = inboxReply.trim();
    const caps = inboxCapabilities[inboxSelected.platform] || {};
    const canReplyOnPlatform = inboxSelected.type === 'dm'
      ? DM_REPLY_PLATFORMS.has(inboxSelected.platform) && Boolean(caps.supports_dm_reply)
      : COMMENT_REPLY_PLATFORMS.has(inboxSelected.platform) && Boolean(caps.supports_comment_reply);

    if (!canReplyOnPlatform) {
      toast.error('Replies are not supported for this platform in Publish right now.');
      setInboxSending(false);
      return;
    }

    try {
      if (inboxSelected.type === 'comment') {
        await replyToComment(
          inboxSelected.platform,
          inboxSelected.post_id,
          inboxSelected.platform_message_id,
          {
            text: trimmedReply,
            account_id: inboxSelected.account_id,
            post_id: inboxSelected.post_id,
            parent_cid: inboxSelected.comment_cid,
            root_uri: inboxSelected.root_uri,
            root_cid: inboxSelected.root_cid,
          }
        );
      } else if (inboxSelected.type === 'dm') {
        await sendDmReply(inboxSelected.platform, inboxSelected.conversation_id, {
          text: trimmedReply,
          account_id: inboxSelected.account_id,
          recipient_id: inboxSelected.recipient_id || inboxSelected.author_id,
        });
      }

      const repliedAt = new Date().toISOString();
      const updated = await updateInboxMessage(inboxSelected.id, {
        reply: trimmedReply,
        reply_status: 'sent',
        replied_at: repliedAt,
        platform_reply_error: null,
        status: 'replied',
      });
      setInboxSelected(updated);
      setInboxMessages((prev) =>
        prev.map((m) => (m.id === inboxSelected.id ? updated : m))
      );
      setInboxReply('');
      toast.success('Reply posted to platform!');
    } catch (err) {
      const failureMessage = err?.response?.data?.detail || err.message || 'Failed to send reply';
      try {
        const failed = await updateInboxMessage(inboxSelected.id, {
          reply: trimmedReply,
          reply_status: 'failed',
          platform_reply_error: failureMessage,
          status: inboxSelected.status === 'unread' ? 'read' : inboxSelected.status,
        });
        setInboxSelected(failed);
        setInboxMessages((prev) =>
          prev.map((m) => (m.id === inboxSelected.id ? failed : m))
        );
      } catch {
        // Best-effort persistence only.
      }
      toast.error(failureMessage);
    } finally {
      setInboxSending(false);
    }
  };

  // ── Derived ──
  const platforms  = [...new Set(accounts.map((a) => a.platform))];
  const dateGroups = groupByDate(posts);

  const unreadCount = inboxMessages.filter((m) => m.status === 'unread').length;
  const inboxPlatformOptions = Object.values(inboxCapabilities)
    .filter((entry) => {
      if (inboxType === 'dm') return entry.supports_dm_inbox;
      if (inboxType === 'comment') return entry.supports_comment_inbox;
      return entry.supports_dm_inbox || entry.supports_comment_inbox;
    })
    .sort((a, b) => (a.label || a.platform).localeCompare(b.label || b.platform));
  const selectedInboxSupportsReply = inboxSelected
    ? (inboxSelected.type === 'dm'
      ? DM_REPLY_PLATFORMS.has(inboxSelected.platform) && Boolean(inboxCapabilities[inboxSelected.platform]?.supports_dm_reply)
      : COMMENT_REPLY_PLATFORMS.has(inboxSelected.platform) && Boolean(inboxCapabilities[inboxSelected.platform]?.supports_comment_reply))
    : false;

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto">

        {/* ── Page header ── */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Publish</h1>
            <p className="text-sm text-gray-500 mt-1">
              View your published posts and manage messages across connected accounts.
            </p>
          </div>
          {activeTab === 'feed' && (
            <button
              onClick={fetchFeed}
              disabled={feedLoading}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 bg-offwhite border border-gray-200 hover:border-gray-300 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
            >
              <FaSync className={`text-xs ${feedLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}
          {activeTab === 'inbox' && (
            <button
              onClick={fetchInbox}
              disabled={inboxLoading}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 bg-offwhite border border-gray-200 hover:border-gray-300 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
            >
              <FaSync className={`text-xs ${inboxLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}
        </div>

        {/* ── Platform + Account selector ── */}
        <div className="bg-offwhite rounded-2xl border border-gray-200 p-4 mb-4 space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">Select Platform &amp; Account</h2>
              {!accountsLoading && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {accounts.length} account{accounts.length !== 1 ? 's' : ''} connected
                </p>
              )}
            </div>
            <a
              href="/accounts"
              className="flex items-center gap-1.5 text-xs font-medium text-green-600 hover:text-green-700 bg-green-50 hover:bg-green-100 px-3 py-1.5 rounded-lg transition-colors"
            >
              <FaPlus className="text-[10px]" />
              Add account
            </a>
          </div>

          {accountsLoading ? (
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 w-28 rounded-xl bg-gray-50 animate-pulse" />
              ))}
            </div>
          ) : accounts.length === 0 ? (
            <div className="py-4 text-center">
              <p className="text-sm text-gray-500">No accounts connected yet.</p>
              <a href="/accounts" className="text-sm text-green-600 hover:text-green-700 font-medium underline mt-1 inline-block">
                Connect an account →
              </a>
            </div>
          ) : (
            <>
              {/* Row 1: Platform pills */}
              <div className="flex flex-wrap gap-2">
                {platforms.map((plat) => {
                  const meta = PLATFORM_META[plat] || {};
                  const Icon = meta.icon;
                  const isActive = activePlatform === plat;
                  const accountCount = accounts.filter((a) => a.platform === plat).length;
                  return (
                    <button
                      key={plat}
                      onClick={() => handlePlatformSelect(plat)}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-sm font-medium transition-all ${
                        isActive
                          ? 'border-green-400 bg-green-50 text-green-800 shadow-sm'
                          : 'border-gray-200 bg-offwhite text-gray-600 hover:border-green-200 hover:bg-green-50/50'
                      }`}
                    >
                      {Icon && <Icon className={`text-sm ${isActive ? 'text-green-600' : meta.color}`} />}
                      <span>{meta.label || plat}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                        isActive ? 'bg-green-200 text-green-700' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {accountCount}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Row 2: Account pills for selected platform */}
              {activePlatform && (
                <div className="pt-1 border-t border-gray-100">
                  <p className="text-[11px] text-gray-400 mb-2 font-medium uppercase tracking-wide">
                    {PLATFORM_META[activePlatform]?.label || activePlatform} accounts — select to filter feed
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {accounts
                      .filter((a) => a.platform === activePlatform)
                      .map((account) => (
                        <AccountPill
                          key={account.id}
                          account={account}
                          selected={selectedAccounts.includes(account.id)}
                          onClick={() => toggleAccount(account.id)}
                        />
                      ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Tab bar: Feed / Inbox ── */}
        <div className="flex gap-1 border-b border-gray-200 mb-4">
          <button
            onClick={() => setActiveTab('feed')}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === 'feed'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <FaRss className="text-xs" />
            Feed
          </button>
          <button
            onClick={() => setActiveTab('inbox')}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === 'inbox'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <FaInbox className="text-xs" />
            Inbox / DMs
            {unreadCount > 0 && (
              <span className="bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                {unreadCount}
              </span>
            )}
          </button>
        </div>

        {/* ══════════════════════════════════════════════════════════════════════
            FEED TAB
        ══════════════════════════════════════════════════════════════════════ */}
        {activeTab === 'feed' && (
          <>
            {/* ── Warnings (token expired, API errors, etc.) ── */}
            {feedWarnings.length > 0 && !feedLoading && (
              <div className="mb-4 bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2">
                <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">⚠ Some accounts could not load posts</p>
                {feedWarnings.map((w, i) => {
                  const meta = PLATFORM_META[w.platform] || {};
                  const Icon = meta.icon;
                  return (
                    <div key={i} className="flex items-start gap-2 text-xs text-amber-800">
                      {Icon && <Icon className={`mt-0.5 flex-shrink-0 ${meta.color}`} />}
                      <span><strong>{w.username}</strong> ({meta.label || w.platform}): {w.reason}</span>
                    </div>
                  );
                })}
                <p className="text-[11px] text-amber-600 mt-1">
                  Go to <a href="/accounts" className="underline font-medium">Accounts</a> to reconnect.
                </p>
              </div>
            )}

            {/* Post feed */}
            {feedLoading ? (
              <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => <SkeletonPostCard key={i} />)}
              </div>
            ) : feedError ? (
              <div className="bg-offwhite rounded-2xl border border-red-100 p-8 text-center">
                <p className="text-sm text-red-600 font-medium">{feedError}</p>
                <button
                  onClick={fetchFeed}
                  className="mt-3 text-sm text-green-600 hover:text-green-700 underline"
                >
                  Try again
                </button>
              </div>
            ) : posts.length === 0 ? (
              <div className="bg-offwhite rounded-2xl border border-gray-200 p-12 flex flex-col items-center justify-center text-center">
                <div className="w-14 h-14 rounded-full bg-offwhite border border-gray-200 flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </div>
                <p className="text-sm font-semibold text-gray-700">No posts found</p>
                <p className="text-xs text-gray-400 mt-1 max-w-xs">
                  {accounts.length === 0
                    ? 'Connect your social accounts to see your published posts here.'
                    : 'No published posts were found for the selected accounts or platform.'}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {dateGroups.map(([dateLabel, datePosts]) => (
                  <div key={dateLabel}>
                    <div className="flex items-center gap-3 mb-3">
                      <div className="h-px flex-1 bg-gray-50" />
                      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-2">
                        {dateLabel}
                      </span>
                      <div className="h-px flex-1 bg-gray-50" />
                    </div>
                    <div className="space-y-3">
                      {datePosts.map((post, idx) => (
                        <PostCard
                          key={post.platform_post_id || idx}
                          post={post}
                          onFetchComments={handleFetchComments}
                          onReplyToComment={handleReplyToComment}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════════════════════════
            INBOX / DMs TAB
        ══════════════════════════════════════════════════════════════════════ */}
        {activeTab === 'inbox' && (
          <div className="bg-offwhite rounded-2xl border border-gray-200 overflow-hidden" style={{ minHeight: '500px' }}>

            {/* ── Filter bar ── */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 bg-gray-50/60 flex-wrap">
              <select
                value={inboxPlatform}
                onChange={(e) => { setInboxPlatform(e.target.value); setInboxSelected(null); }}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-offwhite focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                <option value="">All platforms</option>
                {inboxPlatformOptions.map((entry) => (
                  <option key={entry.platform} value={entry.platform}>{entry.label}</option>
                ))}
              </select>
              <select
                value={inboxType}
                onChange={(e) => { setInboxType(e.target.value); setInboxSelected(null); }}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-offwhite focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                <option value="">All types</option>
                <option value="comment">Comments</option>
                <option value="dm">DMs</option>
              </select>
              <button
                onClick={handleSyncDMs}
                disabled={syncing}
                className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50 ml-auto"
              >
                <FaSync className={`text-[10px] ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing…' : 'Sync Inbox'}
              </button>
              <span className="text-xs text-gray-400">
                {inboxMessages.length} message{inboxMessages.length !== 1 ? 's' : ''}
                {unreadCount > 0 && ` · ${unreadCount} unread`}
              </span>
            </div>

            {/* ── Two-column layout ── */}
            <div className="flex" style={{ minHeight: '460px' }}>

              {/* Left: message list */}
              <div className="w-72 shrink-0 border-r border-gray-100 overflow-y-auto">
                {inboxLoading ? (
                  <div className="p-4 space-y-3">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="animate-pulse">
                        <div className="h-4 bg-gray-100 rounded w-3/4 mb-1" />
                        <div className="h-3 bg-gray-100 rounded w-full mb-1" />
                        <div className="h-2.5 bg-gray-100 rounded w-1/2" />
                      </div>
                    ))}
                  </div>
                ) : inboxMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
                    <FaInbox className="text-3xl text-gray-200 mb-3" />
                    <p className="text-sm text-gray-400 font-medium">No messages found</p>
                    <p className="text-xs text-gray-300 mt-1">
                      {inboxPlatform || inboxType
                        ? 'Try removing filters'
                        : 'Comments and DMs will appear here'}
                    </p>
                  </div>
                ) : (
                  inboxMessages.map((msg) => {
                    const meta = PLATFORM_META[msg.platform] || {};
                    const PIcon = meta.icon;
                    return (
                      <button
                        key={msg.id}
                        onClick={() => { setInboxSelected(msg); setInboxReply(''); }}
                        className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                          inboxSelected?.id === msg.id ? 'bg-indigo-50 border-l-2 border-l-indigo-500' : ''
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2 mb-0.5">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-sm font-semibold text-gray-800 truncate">
                              {msg.author_name}
                            </span>
                            {msg.status === 'unread' && (
                              <span className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />
                            )}
                          </div>
                          <span className="text-[10px] text-gray-400 flex-shrink-0">
                            {formatRelative(msg.received_at)}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 truncate mb-1">{msg.content}</p>
                        <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                          {PIcon && <PIcon className={meta.color} style={{ fontSize: 10 }} />}
                          <span className="capitalize">{msg.platform}</span>
                          <span>·</span>
                          <span className="capitalize">{msg.type}</span>
                          {msg.status === 'replied' && (
                            <>
                              <span>·</span>
                              <span className="text-green-500">Replied</span>
                            </>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              {/* Right: message detail + reply */}
              <div className="flex-1 flex flex-col">
                {inboxSelected ? (
                  <>
                    {/* Message detail */}
                    <div className="p-5 flex-1 overflow-y-auto">
                      <div className="mb-4">
                        {/* Platform + type badge */}
                        <div className="flex items-center gap-2 mb-3">
                          {(() => {
                            const meta = PLATFORM_META[inboxSelected.platform] || {};
                            const PIcon = meta.icon;
                            return PIcon ? (
                              <PIcon className={`${meta.color} text-base`} />
                            ) : null;
                          })()}
                          <span className="text-xs text-gray-400 uppercase tracking-wide font-medium">
                            {PLATFORM_META[inboxSelected.platform]?.label || inboxSelected.platform}
                            {' · '}
                            {inboxSelected.type === 'dm' ? 'Direct Message' : 'Comment'}
                          </span>
                        </div>

                        {/* Author */}
                        <div className="flex items-center gap-2 mb-3">
                          <div className={`w-8 h-8 rounded-full ${avatarColor(inboxSelected.author_name)} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}>
                            {(inboxSelected.author_name || '?').charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-800">{inboxSelected.author_name}</p>
                            <p className="text-[11px] text-gray-400">
                              {formatRelative(inboxSelected.received_at)}
                            </p>
                          </div>
                        </div>

                        {/* Message content */}
                        <div className="bg-gray-50 rounded-xl px-4 py-3 text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                          {inboxSelected.content}
                        </div>
                      </div>

                      {/* Existing reply */}
                      {inboxSelected.reply && (
                        <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 mb-4">
                          <div className="flex items-center gap-1.5 mb-1">
                            <FaReply className="text-indigo-400 text-xs" />
                            <p className="text-xs font-semibold text-indigo-500 uppercase tracking-wide">Your reply</p>
                          </div>
                          <p className="text-sm text-indigo-800 whitespace-pre-wrap">{inboxSelected.reply}</p>
                        </div>
                      )}
                    </div>

                    {/* Reply composer */}
                    <div className="border-t border-gray-100 p-4 bg-gray-50/40">
                      <textarea
                        value={inboxReply}
                        onChange={(e) => setInboxReply(e.target.value)}
                        onKeyDown={(e) => {
                          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleInboxReply();
                        }}
                        placeholder="Write a reply… (⌘↵ to send)"
                        rows={3}
                        className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2.5 resize-none bg-offwhite focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent placeholder-gray-400"
                      />
                      <div className="flex items-center justify-between mt-2">
                        <p className="text-[11px] text-gray-400">
                          {selectedInboxSupportsReply
                            ? `Reply will be posted directly to ${PLATFORM_META[inboxSelected.platform]?.label || inboxSelected.platform}`
                            : 'Replies are not supported for this platform in Publish right now.'
                          }
                        </p>
                        <button
                          onClick={handleInboxReply}
                          disabled={!inboxReply.trim() || inboxSending || !selectedInboxSupportsReply}
                          className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {inboxSending ? (
                            <>
                              <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                              Sending…
                            </>
                          ) : (
                            <>
                              <FaReply className="text-xs" />
                              Send Reply
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full py-20 text-center px-6">
                    <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                      <FaInbox className="text-gray-300 text-lg" />
                    </div>
                    <p className="text-sm font-medium text-gray-500">Select a message</p>
                    <p className="text-xs text-gray-400 mt-1">
                      Click a message on the left to view and reply
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
};

export default Publish;
