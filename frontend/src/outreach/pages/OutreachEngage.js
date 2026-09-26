import React, { useState, useEffect, useCallback, useRef } from 'react';

import {
  Sparkles,
  Plus,
  ThumbsUp,
  X,
  ExternalLink,
  RefreshCw,
  Trash2,
  ArrowLeft,
  Users,
  Check,
  Smile,
  Send,
  Loader2,
  TrendingUp,
  MessageCircle,
  FileText,
  Upload,
  Download,
  Clock3,
} from 'lucide-react';
import { toast } from 'sonner';
import './OutreachEngageReport.css';

const authHeaders = (json = false) => ({
  ...(json ? { 'Content-Type': 'application/json' } : {}),
  Authorization: localStorage.getItem('token') ? `Bearer ${localStorage.getItem('token')}` : '',
});

const readError = async (res, fallback) => {
  const body = await res.json().catch(() => ({}));
  return body.detail || body.error || fallback;
};

const postAge = (value) => {
  if (!value) return { label: 'Date unavailable', old: false };
  const raw = Number(value);
  const date = Number.isFinite(raw) && raw > 0
    ? new Date(raw > 1e12 ? raw : raw * 1000)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return { label: String(value), old: false };
  const days = Math.max(0, (Date.now() - date.getTime()) / 86400000);
  const label = days < 1 / 24 ? 'Just now' : days < 1 ? `${Math.floor(days * 24)}h ago`
    : days < 2 ? 'Yesterday' : `${Math.floor(days)} days ago`;
  return { label, old: days > 7 };
};

export default function OutreachEngage() {
  const [lists, setLists] = useState([]);
  const [loadingLists, setLoadingLists] = useState(true);
  const [activeList, setActiveList] = useState(null);
  const [activeTab, setActiveTab] = useState('posts'); // 'posts' | 'contacts' | 'drafts'
  const [posts, setPosts] = useState([]);
  const [loadingPosts, setLoadingPosts] = useState(false);
  const [statusFilter, setStatusFilter] = useState('pending'); // 'pending' | 'commented' | 'all'

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newListName, setNewListName] = useState('');
  const [newListEmoji, setNewListEmoji] = useState('🎯');
  const [newListDesc, setNewListDesc] = useState('');

  const [showAddContactsModal, setShowAddContactsModal] = useState(false);
  const [contactUrlInput, setContactUrlInput] = useState('');
  const [contactUrlsList, setContactUrlsList] = useState([]);
  const [csvText, setCsvText] = useState('');

  // AI Comment Modal
  const [aiModalPost, setAiModalPost] = useState(null);
  const [aiTone, setAiTone] = useState('insightful');
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiComments, setAiComments] = useState([]);

  // In-line comment draft state per post: { [postId]: { text: string, autoLike: boolean, posting: boolean } }
  const [commentDrafts, setCommentDrafts] = useState({});
  // Track per-post like loading state: { [postId]: true }
  const [likingPosts, setLikingPosts] = useState({});
  // Bulk selection for batch actions
  const [selectedPosts, setSelectedPosts] = useState(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  // Pagination
  const [totalPosts, setTotalPosts] = useState(0);
  const [stats, setStats] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [draftPendingCount, setDraftPendingCount] = useState(0);
  const [draftEdits, setDraftEdits] = useState({});
  const [draftBusy, setDraftBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [styles, setStyles] = useState([]);
  const [selectedStyleId, setSelectedStyleId] = useState('');
  const [campaigns, setCampaigns] = useState([]);
  const [historyContact, setHistoryContact] = useState(null);
  const [historyPosts, setHistoryPosts] = useState([]);
  const [activePostIndex, setActivePostIndex] = useState(0);
  const likingLock = useRef(new Set());
  const shortcutActions = useRef({});
  const activeListId = activeList?.id;
  const fetchStatus = activeList?.fetch_status;
  const enrichmentStatus = activeList?.enrichment_status;

  const fetchLists = useCallback(async () => {
    setLoadingLists(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/lists', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setLists(data || []);
      } else toast.error(await readError(res, 'Failed to load engagement lists'));
    } catch (_) {
      toast.error('Failed to load engagement lists');
    } finally {
      setLoadingLists(false);
    }
  }, []);

  const fetchPosts = useCallback(async (listId, filter = 'pending', append = false, skipOffset = 0) => {
    if (!append) setLoadingPosts(true);
    try {
      const token = localStorage.getItem('token');
      const PAGE_SIZE = 20;
      const res = await fetch(`/api/v1/outreach/engage/lists/${listId}/posts?status_filter=${filter}&skip=${skipOffset}&limit=${PAGE_SIZE}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        const newPosts = data.posts || [];
        if (append) {
          setPosts((prev) => [...prev, ...newPosts]);
        } else {
          setPosts(newPosts);
        }
        setTotalPosts(data.total || 0);
      } else toast.error(await readError(res, 'Failed to load prospect posts'));
    } catch (_) {
      toast.error('Failed to load prospect posts');
    } finally {
      setLoadingPosts(false);
    }
  }, []);

  const fetchStats = useCallback(async (listId) => {
    try {
      const res = await fetch(`/api/v1/outreach/engage/lists/${listId}/stats`, {
        credentials: 'include', headers: authHeaders(),
      });
      if (res.ok) setStats(await res.json());
    } catch (_) { /* Feed remains usable without summary stats. */ }
  }, []);

  const fetchListDetail = useCallback(async (listId) => {
    const res = await fetch(`/api/v1/outreach/engage/lists/${listId}`, {
      credentials: 'include', headers: authHeaders(),
    });
    if (!res.ok) throw new Error(await readError(res, 'Could not load list details'));
    const data = await res.json();
    setActiveList((previous) => previous?.id === listId ? data : previous);
    return data;
  }, []);

  const waitForPostAction = async (postId, expectedStatus) => {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/action`, {
        credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await readError(res, 'Could not check LinkedIn action status'));
      const data = await res.json();
      if (data.action_error) throw new Error(data.action_error);
      if (data.status === expectedStatus) return data;
      if (!data.action_queued_at && !data.action_claimed_at) {
        throw new Error('LinkedIn did not confirm this action. Please refresh the feed.');
      }
    }
    throw new Error('Action is still processing. Refresh the feed to check its final status.');
  };

  const openList = async (list) => {
    setActiveList(list);
    setActiveTab('posts');
    setSelectedPosts(new Set());
    setStats(null);
    setDrafts([]);
    setDraftPendingCount(0);
    try { await fetchListDetail(list.id); }
    catch (error) { toast.error(error.message); }
  };

  useEffect(() => {
    fetchLists();
  }, [fetchLists]);

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [accountRes, styleRes, campaignRes] = await Promise.all([
          fetch('/api/v1/outreach/engage/accounts', { credentials: 'include', headers: authHeaders() }),
          fetch('/api/v1/outreach/styles', { credentials: 'include', headers: authHeaders() }),
          fetch('/api/v1/outreach/campaigns', { credentials: 'include', headers: authHeaders() }),
        ]);
        if (accountRes.ok) {
          const data = await accountRes.json();
          setAccounts(data);
          setSelectedAccountId((current) => data.some((account) => account.id === current) ? current : data[0]?.id || '');
        }
        if (styleRes.ok) {
          const data = await styleRes.json();
          setStyles(data);
          setSelectedStyleId(data.find((style) => style.is_default)?.id || '');
        }
        if (campaignRes.ok) setCampaigns(await campaignRes.json());
      } catch (_) { /* Account and style actions surface their own errors. */ }
    };
    loadOptions();
  }, []);

  useEffect(() => {
    if (activeListId) {
      fetchPosts(activeListId, statusFilter);
      fetchStats(activeListId);
    }
  }, [activeListId, statusFilter, fetchPosts, fetchStats]);

  const fetchDrafts = useCallback(async (listId) => {
    try {
      const res = await fetch(`/api/v1/outreach/engage/lists/${listId}/drafts`, {
        credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await readError(res, 'Could not load comment drafts'));
      const data = await res.json();
      setDrafts(data.drafts || []);
      setDraftPendingCount(data.pending_count || 0);
      setDraftEdits(Object.fromEntries((data.drafts || []).map((draft) => [draft.id, draft.comment_text])));
    } catch (error) { toast.error(error.message); }
  }, []);

  useEffect(() => {
    if (activeListId) fetchDrafts(activeListId);
  }, [activeListId, fetchDrafts]);

  useEffect(() => {
    if (!activeListId || !['queued', 'running'].includes(fetchStatus) &&
      !['queued', 'running'].includes(enrichmentStatus)) return undefined;
    const listId = activeListId;
    const timer = window.setInterval(async () => {
      try {
        const updated = await fetchListDetail(listId);
        if (['queued', 'running'].includes(fetchStatus) && ['complete', 'failed'].includes(updated.fetch_status)) {
          fetchPosts(listId, statusFilter);
          fetchStats(listId);
          fetchLists();
          if (updated.fetch_status === 'failed') toast.error(updated.fetch_error || 'Post fetch failed');
          else if (updated.fetch_failed_contacts_last_run || updated.fetch_unverified_contacts_last_run) {
            toast.warning(`Fetched ${updated.posts_fetched_last_run || 0} new posts; ${
              (updated.fetch_failed_contacts_last_run || 0) + (updated.fetch_unverified_contacts_last_run || 0)
            } contacts need attention.`);
          } else toast.success(`Fetched ${updated.posts_fetched_last_run || 0} new posts`);
        }
        if (['queued', 'running'].includes(enrichmentStatus) &&
          updated.enrichment_status === 'complete') fetchStats(listId);
      } catch (_) { /* Retry on next poll. */ }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [activeListId, fetchStatus, enrichmentStatus, fetchListDetail, fetchLists, fetchPosts, fetchStats, statusFilter]);

  const handleCreateList = async (e) => {

    e.preventDefault();
    if (!newListName.trim()) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/lists', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: newListName.trim(),
          emoji: newListEmoji,
          description: newListDesc.trim(),
        }),
      });
      if (res.ok) {
        const created = await res.json();
        toast.success(`Created list "${created.name}"`);
        setShowCreateModal(false);
        setNewListName('');
        setNewListDesc('');
        fetchLists();
      } else toast.error(await readError(res, 'Failed to create engagement list'));
    } catch (_) {
      toast.error('Failed to create engagement list');
    }
  };

  const handleDeleteList = async (listId) => {
    if (!window.confirm('Delete this engagement list and all cached posts?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/lists/${listId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('List deleted');
        if (activeList?.id === listId) setActiveList(null);
        fetchLists();
      } else toast.error(await readError(res, 'Failed to delete list'));
    } catch (_) {
      toast.error('Failed to delete list');
    }
  };

  const handleFetchLatestPosts = async () => {
    if (!activeList) return;
    if (!selectedAccountId) { toast.error('Connect a LinkedIn sender before fetching posts'); return; }
    setLoadingPosts(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/fetch?sender_account_id=${encodeURIComponent(selectedAccountId)}`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'empty') toast.info(data.message);
        else toast.info(data.status === 'already_running' ? 'Post fetch is already running' : 'Post fetch queued. Results will appear shortly.');
        await fetchListDetail(activeList.id);
      } else {
        toast.error(await readError(res, 'Could not queue post fetch'));
      }
    } catch (_) {
      toast.error('Error fetching prospect posts');
    } finally {
      setLoadingPosts(false);
    }
  };

  const handleAddContacts = async () => {
    if (!activeList) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/contacts`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          profile_urls: contactUrlsList,
          csv_text: csvText || null,
          sender_account_id: selectedAccountId,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Added ${data.added_count} contacts!`);
        if (data.invalid_count) toast.warning(`${data.invalid_count} invalid LinkedIn profile URLs were skipped.`);
        if (data.enrichment_status === 'waiting_for_sender') toast.info('Connect a LinkedIn sender to verify these profiles.');
        setShowAddContactsModal(false);
        setContactUrlsList([]);
        setCsvText('');
        setContactUrlInput('');
        fetchLists();
        // Refresh active list details
        await fetchListDetail(activeList.id);
        fetchStats(activeList.id);
      } else {
        toast.error(await readError(res, 'Could not add contacts'));
      }
    } catch (_) {
      toast.error('Failed to add contacts');
    }
  };

  const handleLikePost = async (postId) => {
    if (!selectedAccountId) { toast.error('Select a LinkedIn sender first'); return; }
    if (likingLock.current.has(postId)) return;
    likingLock.current.add(postId);
    setLikingPosts((prev) => ({ ...prev, [postId]: true }));
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/like`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ sender_account_id: selectedAccountId || null }),
      });
      if (res.ok) {
        await waitForPostAction(postId, 'liked');
        toast.success('Liked post on LinkedIn!');
        setPosts((prev) =>
          statusFilter === 'pending' ? prev.filter((p) => p.id !== postId)
            : prev.map((p) => (p.id === postId ? { ...p, status: 'liked', action_queued_at: null, reactions_count: p.reactions_count + 1 } : p))
        );
        if (statusFilter === 'pending') setTotalPosts((total) => Math.max(0, total - 1));
        setSelectedPosts((current) => new Set([...current].filter((id) => id !== postId)));
        fetchStats(activeList.id);
        fetchLists();
      } else if (res.status === 429) {
        toast.error('Daily like limit reached. Try again tomorrow.');
      } else if (res.status === 400) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'No active LinkedIn account connected.');
      } else if (res.status === 503) {
        toast.error('LinkedIn restriction detected — account paused for safety.');
      } else {
        toast.error(await readError(res, 'LinkedIn did not confirm the like'));
      }
    } catch (error) {
      toast.error(error.message || 'Failed to like post');
      if (activeList) fetchPosts(activeList.id, statusFilter);
    } finally {
      likingLock.current.delete(postId);
      setLikingPosts((prev) => {
        const updated = { ...prev };
        delete updated[postId];
        return updated;
      });
    }
  };

  const handleDiscardPost = async (postId) => {
    if (!window.confirm('Dismiss this post from your feed? You can find it later under the "discarded" filter.')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/discard`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Dismissed post from feed');
        setPosts((prev) => statusFilter === 'all'
          ? prev.map((p) => p.id === postId ? { ...p, status: 'discarded' } : p)
          : prev.filter((p) => p.id !== postId));
        if (statusFilter !== 'all') setTotalPosts((total) => Math.max(0, total - 1));
        fetchStats(activeList.id);
        fetchLists();
      } else {
        toast.error(await readError(res, 'Failed to discard post'));
      }
    } catch (_) {
      toast.error('Failed to discard post');
    }
  };

  const handleSendComment = async (postId) => {
    if (!selectedAccountId) { toast.error('Select a LinkedIn sender first'); return; }
    const draft = commentDrafts[postId];
    if (!draft || !draft.text?.trim()) {
      toast.error('Please write a comment first');
      return;
    }

    setCommentDrafts((prev) => ({
      ...prev,
      [postId]: { ...prev[postId], posting: true },
    }));

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/comment`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          comment_text: draft.text.trim(),
          auto_like: draft.autoLike ?? true,
          sender_account_id: selectedAccountId || null,
        }),
      });
      if (res.ok) {
        const priorPost = posts.find((post) => post.id === postId);
        const data = await waitForPostAction(postId, 'commented');
        toast.success(draft.autoLike && priorPost?.status === 'pending' && data.liked_at
          ? 'Comment posted & post liked on LinkedIn!' : 'Comment posted to LinkedIn!');
        setPosts((prev) => statusFilter === 'all'
          ? prev.map((p) => p.id === postId ? { ...p, status: 'commented', action_queued_at: null, user_comment: draft.text.trim() } : p)
          : prev.filter((p) => p.id !== postId));
        if (statusFilter !== 'all') setTotalPosts((total) => Math.max(0, total - 1));
        setCommentDrafts((prev) => {
          const updated = { ...prev };
          delete updated[postId];
          return updated;
        });
        fetchStats(activeList.id);
        fetchLists();
      } else if (res.status === 429) {
        toast.error('Daily comment limit reached. Try again tomorrow.');
      } else if (res.status === 400) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'No active LinkedIn account connected.');
      } else if (res.status === 503) {
        toast.error('LinkedIn restriction detected — account paused for safety.');
      } else {
        toast.error(await readError(res, 'LinkedIn did not confirm the comment'));
      }
    } catch (error) {
      toast.error(error.message || 'Failed to post comment');
      if (activeList) fetchPosts(activeList.id, statusFilter);
    } finally {
      setCommentDrafts((prev) => ({
        ...prev,
        [postId]: { ...prev[postId], posting: false },
      }));
    }
  };

  const handleGenerateAIComments = async (post, tone = aiTone, prompt = aiPrompt) => {
    setAiModalPost(post);
    setAiComments([]);
    setAiLoading(true);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/ai-comment', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          post_text: post.content_text,
          author_headline: post.author_headline,
          tone,
          custom_prompt: prompt,
          writing_style_id: selectedStyleId || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setAiComments(data.comments || []);
      } else toast.error(await readError(res, 'AI comment generation failed'));
    } catch (_) {
      toast.error('AI comment generation failed');
    } finally {
      setAiLoading(false);
    }
  };

  const openAiModal = (post) => {
    setAiPrompt('');
    setAiTone('insightful');
    handleGenerateAIComments(post, 'insightful', '');
  };

  const selectAiComment = (commentText) => {
    if (!aiModalPost) return;
    setCommentDrafts((prev) => ({
      ...prev,
      [aiModalPost.id]: {
        ...(prev[aiModalPost.id] || { autoLike: true }),
        text: commentText,
      },
    }));
    setAiModalPost(null);
    toast.success('Inserted AI comment into composer!');
  };

  // ── Bulk Actions ──────────────────────────────────────────────────────
  const togglePostSelection = (postId) => {
    setSelectedPosts((prev) => {
      const next = new Set(prev);
      if (next.has(postId)) next.delete(postId);
      else next.add(postId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const selectable = posts.filter((post) => post.status === 'pending' && !post.action_queued_at);
    if (selectedPosts.size === selectable.length) {
      setSelectedPosts(new Set());
    } else {
      setSelectedPosts(new Set(selectable.map((p) => p.id)));
    }
  };

  const handleBulkLike = async () => {
    if (selectedPosts.size === 0) return;
    if (!selectedAccountId) { toast.error('Select a LinkedIn sender first'); return; }
    setBulkLoading(true);
    const token = localStorage.getItem('token');
    let successCount = 0;
    let rateLimited = false;
    let stoppedForSafety = false;
    const ids = [...selectedPosts];
    for (const [index, postId] of ids.entries()) {
      try {
        const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/like`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
          body: JSON.stringify({ sender_account_id: selectedAccountId }),
        });
        if (res.ok) {
          await waitForPostAction(postId, 'liked');
          successCount++;
          setPosts((prev) => prev.filter((p) => p.id !== postId));
          setTotalPosts((total) => Math.max(0, total - 1));
        } else if (res.status === 429) {
          rateLimited = true;
          break;
        } else if (res.status === 503 || res.status === 400) {
          stoppedForSafety = true;
          break;
        }
      } catch (error) {
        toast.error(error.message || 'A bulk like failed');
        stoppedForSafety = true;
        break;
      }
      // Space live actions so a bulk click does not create an instant burst.
      if (index < ids.length - 1) await new Promise((r) => setTimeout(r, 2500 + Math.random() * 5500));
    }
    setSelectedPosts(new Set());
    setBulkLoading(false);
    fetchStats(activeList.id);
    fetchLists();
    if (stoppedForSafety) {
      toast.error(`Stopped after ${successCount} likes because the sender is unavailable or restricted.`);
    } else if (rateLimited) {
      toast.error(`Liked ${successCount} posts before hitting daily limit.`);
    } else {
      toast.success(`Liked ${successCount} post${successCount !== 1 ? 's' : ''} on LinkedIn!`);
    }
  };

  const handleBulkDiscard = async () => {
    if (selectedPosts.size === 0) return;
    if (!window.confirm(`Dismiss ${selectedPosts.size} selected post${selectedPosts.size !== 1 ? 's' : ''}?`)) return;
    setBulkLoading(true);
    const token = localStorage.getItem('token');
    let successCount = 0;
    for (const postId of selectedPosts) {
      try {
        const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/discard`, {
          method: 'POST',
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          successCount++;
          setPosts((prev) => prev.filter((p) => p.id !== postId));
          setTotalPosts((total) => Math.max(0, total - 1));
        }
      } catch (_) {}
    }
    setSelectedPosts(new Set());
    setBulkLoading(false);
    fetchStats(activeList.id);
    fetchLists();
    toast.success(`Dismissed ${successCount} post${successCount !== 1 ? 's' : ''}`);
  };

  const handleDeleteContact = async (contact) => {
    if (!window.confirm(`Remove ${contact.full_name || contact.profile_url} and their cached posts from this list?`)) return;
    const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/contacts/${contact.id}`, {
      method: 'DELETE', credentials: 'include', headers: authHeaders(),
    }).catch(() => null);
    if (!res?.ok) { toast.error(res ? await readError(res, 'Could not remove contact') : 'Network error removing contact'); return; }
    await fetchListDetail(activeList.id);
    fetchStats(activeList.id);
    fetchPosts(activeList.id, statusFilter);
    fetchLists();
    toast.success('Contact removed');
  };

  const openContactHistory = async (contact) => {
    setHistoryContact(contact);
    setHistoryPosts([]);
    const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/contacts/${contact.id}/history`, {
      credentials: 'include', headers: authHeaders(),
    }).catch(() => null);
    if (res?.ok) setHistoryPosts((await res.json()).events || []);
    else toast.error('Could not load contact history');
  };

  const handleExport = async () => {
    const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/export.csv`, {
      credentials: 'include', headers: authHeaders(),
    }).catch(() => null);
    if (!res?.ok) { toast.error('Could not export engagement report'); return; }
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = `engage-${activeList.name.replace(/[^a-z0-9-]/gi, '-').toLowerCase()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const saveReviewDraft = async (postId, commentText) => {
    if (!commentText?.trim() || !activeList) return;
    setDraftBusy(true);
    try {
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/drafts`, {
        method: 'POST', credentials: 'include', headers: authHeaders(true),
        body: JSON.stringify({ post_id: postId, comment_text: commentText.trim() }),
      });
      if (!res.ok) throw new Error(await readError(res, 'Could not save review draft'));
      await fetchDrafts(activeList.id);
      toast.success('Saved to Draft & Review. Nothing was published.');
      setAiModalPost(null);
    } catch (error) { toast.error(error.message); }
    finally { setDraftBusy(false); }
  };

  const updateReviewDraft = async (draftId, changes) => {
    setDraftBusy(true);
    try {
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/drafts/${draftId}`, {
        method: 'PATCH', credentials: 'include', headers: authHeaders(true),
        body: JSON.stringify(changes),
      });
      if (!res.ok) throw new Error(await readError(res, 'Could not update review draft'));
      await fetchDrafts(activeList.id);
      toast.success(changes.status === 'completed' ? 'Marked done manually (not verified engagement)' : 'Draft updated');
    } catch (error) { toast.error(error.message); }
    finally { setDraftBusy(false); }
  };

  const openPrintReport = async () => {
    setReportLoading(true);
    try {
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/report`, {
        credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await readError(res, 'Could not load engagement report'));
      setReport(await res.json());
    } catch (error) { toast.error(error.message); }
    finally { setReportLoading(false); }
  };

  const saveListSettings = async (campaignId, hours = activeList.warmup_hours || 24) => {
    const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/settings`, {
      method: 'PATCH', credentials: 'include', headers: authHeaders(true),
      body: JSON.stringify({ campaign_id: campaignId || null, warmup_hours: Number(hours) }),
    }).catch(() => null);
    if (!res?.ok) { toast.error(res ? await readError(res, 'Could not save warm-up settings') : 'Network error saving settings'); return; }
    await fetchListDetail(activeList.id);
    toast.success(campaignId ? 'Campaign warm-up linked' : 'Campaign unlinked');
  };

  shortcutActions.current = { like: handleLikePost, discard: handleDiscardPost };

  useEffect(() => {
    if (!activeList || activeTab !== 'posts' || aiModalPost || showAddContactsModal || showCreateModal) return undefined;
    const onKeyDown = (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey ||
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const next = Math.max(0, Math.min(posts.length - 1, activePostIndex + (event.key === 'ArrowDown' ? 1 : -1)));
        setActivePostIndex(next);
        document.querySelectorAll('[data-engage-post]')[next]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
      const post = posts[activePostIndex];
      if (!post) return;
      if (event.key.toLowerCase() === 'l' && post.status === 'pending') shortcutActions.current.like(post.id);
      if (event.key.toLowerCase() === 'd' && post.status === 'pending') shortcutActions.current.discard(post.id);
      if (event.key.toLowerCase() === 'c') document.querySelectorAll('[data-engage-post]')[activePostIndex]?.querySelector('textarea')?.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeList, activeTab, aiModalPost, showAddContactsModal, showCreateModal, posts, activePostIndex, selectedAccountId]);

  return (
    <div className="flex-1 h-full overflow-y-auto bg-neutral-50/50 p-6 md:p-8">
      {/* ── View 1: Lists Overview ────────────────────────────────────────── */}
      {!activeList && (
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Top Banner */}
          <div className="bg-gradient-to-r from-indigo-50 via-sky-50 to-indigo-50/30 border border-indigo-100 rounded-2xl p-4 md:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xs">
            <div className="flex items-center gap-3.5">
              <div className="w-10 h-10 rounded-full bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shadow-sm">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900">Pre-Outreach Social Warm-up</h3>
                  <span className="text-[10px] bg-indigo-600 text-white font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">
                    Pre-Outreach
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">
                  Build context before outreach with genuine, relevant engagement. Review every comment before posting.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all shrink-0 active:scale-95"
            >
              <Plus className="w-4 h-4" /> Create New List
            </button>
          </div>

          {/* Heading */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Engage & Grow</h1>
              <p className="text-xs text-gray-500 mt-0.5">
                Be the first to engage with your target accounts and favorite LinkedIn profiles without opening 50 tabs.
              </p>
            </div>
          </div>

          {/* Lists Grid */}
          {loadingLists ? (
            <div className="py-20 flex flex-col items-center justify-center text-gray-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
              <p className="text-xs">Loading engagement lists…</p>
            </div>
          ) : lists.length === 0 ? (
            <div className="bg-white border border-dashed border-gray-300 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-4">
              <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto text-2xl">
                🎯
              </div>
              <div>
                <h3 className="text-base font-bold text-gray-900">No Engagement Lists Yet</h3>
                <p className="text-xs text-gray-500 mt-1 max-w-sm mx-auto">
                  Create your first list (e.g. "Dream 50 SaaS Founders" or "Agency Prospects") to start warming up target leads.
                </p>
              </div>
              <button
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
              >
                <Plus className="w-4 h-4" /> Create First List
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {lists.map((l) => (
                <div
                  key={l.id}
                  onClick={() => openList(l)}
                  className="bg-white rounded-2xl border border-gray-200/90 hover:border-indigo-400 hover:shadow-md transition-all p-5 cursor-pointer group flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="w-10 h-10 rounded-xl bg-neutral-100 flex items-center justify-center text-xl shadow-xs group-hover:scale-110 transition-transform">
                        {l.emoji || '🎯'}
                      </div>
                      <div className="flex items-center gap-2">
                        {l.pending_posts_count > 0 && (
                          <span className="text-[11px] font-bold bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                            {l.pending_posts_count} new posts
                          </span>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteList(l.id);
                          }}
                          className="text-gray-300 hover:text-red-500 p-1 rounded-lg transition-colors"
                          title="Delete List"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">
                        {l.name}
                      </h3>
                      {l.description && (
                        <p className="text-xs text-gray-500 line-clamp-1 mt-0.5">{l.description}</p>
                      )}
                    </div>
                  </div>
                  <div className="pt-4 border-t border-gray-100 mt-4 flex items-center justify-between text-xs text-gray-500">
                    <span className="flex items-center gap-1.5 font-medium">
                      <Users className="w-3.5 h-3.5 text-gray-400" />
                      {l.contacts_count} contacts
                    </span>
                    <span className="text-indigo-600 font-semibold group-hover:translate-x-0.5 transition-transform flex items-center gap-1">
                      Open Feed →
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── View 2: List Feed & In-Line Commenting ────────────────────────── */}
      {activeList && (
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-gray-200/80">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setActiveList(null)}
                className="w-9 h-9 rounded-xl border border-gray-200 bg-white hover:bg-neutral-100 text-gray-600 flex items-center justify-center transition-colors"
                title="Back to lists"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-3">
                <span className="text-2xl">{activeList.emoji || '🎯'}</span>
                <div>
                  <h1 className="text-xl font-bold text-gray-900 tracking-tight">{activeList.name}</h1>
                  <p className="text-xs text-gray-500">Engage with your target prospect list</p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              {/* Tabs */}
              <div className="flex bg-neutral-100 p-1 rounded-xl text-xs font-semibold text-gray-600">
                <button
                  onClick={() => setActiveTab('posts')}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    activeTab === 'posts' ? 'bg-white text-gray-900 shadow-xs' : 'hover:text-gray-900'
                  }`}
                >
                  Posts Feed
                </button>
                <button
                  onClick={() => setActiveTab('contacts')}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    activeTab === 'contacts' ? 'bg-white text-gray-900 shadow-xs' : 'hover:text-gray-900'
                  }`}
                >
                  Contacts ({activeList.contacts_count || activeList.contacts?.length || 0})
                </button>
                <button
                  onClick={() => setActiveTab('drafts')}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    activeTab === 'drafts' ? 'bg-white text-gray-900 shadow-xs' : 'hover:text-gray-900'
                  }`}
                >
                  Draft & Review ({draftPendingCount})
                </button>
              </div>

              <button
                onClick={() => setShowAddContactsModal(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-neutral-50 transition-colors shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" /> Add Contacts
              </button>

              <button
                onClick={handleFetchLatestPosts}
                disabled={loadingPosts || ['queued', 'running'].includes(activeList.fetch_status) || !selectedAccountId}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingPosts ? 'animate-spin' : ''}`} />
                {['queued', 'running'].includes(activeList.fetch_status) ? 'Fetching Posts…' : 'Fetch Latest Posts'}
              </button>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl p-3 flex flex-wrap items-center gap-3 text-xs">
            <label className="font-semibold text-gray-600" htmlFor="engage-sender">LinkedIn sender</label>
            <select id="engage-sender" value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}
              className="border border-gray-200 rounded-lg px-2 py-1.5 text-gray-800 min-w-[170px]">
              {accounts.length === 0 && <option value="">No active account</option>}
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name || account.vanity_name || account.id}</option>)}
            </select>
            <label className="font-semibold text-gray-600" htmlFor="engage-campaign">Warm up campaign</label>
            <select id="engage-campaign" value={activeList.campaign_id || ''}
              onChange={(event) => saveListSettings(event.target.value)}
              className="border border-gray-200 rounded-lg px-2 py-1.5 text-gray-800 min-w-[170px]">
              <option value="">None</option>
              {campaigns.filter((campaign) => campaign.status === 'draft' || campaign.id === activeList.campaign_id)
                .map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
            </select>
            {activeList.campaign_id && (
              <label className="flex items-center gap-1 text-gray-600">
                Delay first action
                <select value={activeList.warmup_hours || 24}
                  onChange={(event) => saveListSettings(activeList.campaign_id, event.target.value)}
                  className="border border-gray-200 rounded-lg px-2 py-1.5">
                  <option value={24}>24 hours</option><option value={48}>48 hours</option>
                </select>
              </label>
            )}
            <button onClick={handleExport} className="ml-auto inline-flex items-center gap-1 text-indigo-600 font-semibold hover:text-indigo-800">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            <button onClick={openPrintReport} disabled={reportLoading} className="inline-flex items-center gap-1 text-indigo-600 font-semibold hover:text-indigo-800 disabled:opacity-50">
              <FileText className="w-3.5 h-3.5" /> Print / Save as PDF
            </button>
            {activeList.fetch_status === 'failed' && <span className="w-full text-red-600">{activeList.fetch_error || 'Post fetch failed'}</span>}
            {activeList.campaign_id && <span className="w-full text-gray-500">Launching the linked campaign requires confirmed engagement for every lead within the past seven days; its first outreach action waits for the selected warm-up period.</span>}
            {['queued', 'running'].includes(activeList.enrichment_status) && <span className="w-full text-gray-500">Verifying added LinkedIn profiles…</span>}
            {activeList.enrichment_status === 'failed' && <span className="w-full text-red-600">Profile verification failed. Check the sender connection, then retry Fetch Latest Posts.</span>}
            {activeList.enrichment_status === 'waiting_for_sender' && <span className="w-full text-gray-500">Profiles are saved but unverified. Connect a sender, then fetch posts to verify them.</span>}
          </div>

          {/* Posts Feed Tab */}
          {activeTab === 'posts' && (
            <div className="space-y-4">
              {/* Engagement Analytics Bar */}
              {activeList && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  {[
                    { label: 'Total Posts', value: stats?.total ?? '—', icon: <FileText className="w-3.5 h-3.5" />, color: 'text-gray-600 bg-gray-50' },
                    { label: 'Liked', value: stats?.liked ?? '—', icon: <ThumbsUp className="w-3.5 h-3.5" />, color: 'text-blue-600 bg-blue-50' },
                    { label: 'Commented', value: stats?.commented ?? '—', icon: <MessageCircle className="w-3.5 h-3.5" />, color: 'text-emerald-600 bg-emerald-50' },
                    { label: 'Discarded', value: stats?.discarded ?? '—', icon: <X className="w-3.5 h-3.5" />, color: 'text-amber-600 bg-amber-50' },
                    { label: 'Contacts', value: stats?.contacts ?? '—', icon: <Users className="w-3.5 h-3.5" />, color: 'text-purple-600 bg-purple-50' },
                  ].map((stat) => (
                    <div key={stat.label} className="bg-white border border-gray-200 rounded-xl px-3 py-2.5 flex items-center gap-2.5">
                      <div className={`w-7 h-7 rounded-lg ${stat.color} flex items-center justify-center`}>
                        {stat.icon}
                      </div>
                      <div>
                        <div className="text-[11px] text-gray-400 font-medium">{stat.label}</div>
                        <div className="text-sm font-bold text-gray-900">{stat.value}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* Filter controls */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {['pending', 'liked', 'commented', 'discarded', 'all'].map((st) => (
                    <button
                      key={st}
                      onClick={() => { setStatusFilter(st); setSelectedPosts(new Set()); }}
                      className={`text-xs px-3 py-1 rounded-lg font-medium capitalize transition-colors ${
                        statusFilter === st
                          ? 'bg-gray-900 text-white'
                          : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {st === 'pending' ? 'Pending' : st}
                    </button>
                  ))}
                </div>
                <span className="text-xs text-gray-400">
                  {totalPosts} {statusFilter} post{totalPosts !== 1 ? 's' : ''} · Shortcuts: ↑/↓ navigate, L like, D dismiss, C comment
                </span>
              </div>

              {/* Bulk Action Bar */}
              {posts.length > 0 && statusFilter === 'pending' && (
                <div className="flex items-center justify-between bg-white border border-gray-200 rounded-xl px-4 py-2">
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-gray-600">
                    <input
                      type="checkbox"
                      checked={selectedPosts.size === posts.filter((post) => post.status === 'pending' && !post.action_queued_at).length && selectedPosts.size > 0}
                      onChange={toggleSelectAll}
                      className="w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    {selectedPosts.size > 0 ? `${selectedPosts.size} selected` : 'Select all'}
                  </label>
                  {selectedPosts.size > 0 && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleBulkLike}
                        disabled={bulkLoading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-semibold border border-blue-200 hover:bg-blue-100 transition-colors disabled:opacity-50"
                      >
                        {bulkLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ThumbsUp className="w-3 h-3" />}
                        Like All
                      </button>
                      <button
                        onClick={handleBulkDiscard}
                        disabled={bulkLoading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 text-red-600 text-xs font-semibold border border-red-200 hover:bg-red-100 transition-colors disabled:opacity-50"
                      >
                        <X className="w-3 h-3" /> Dismiss All
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* 2-Column Responsive Feed */}
              {loadingPosts ? (
                <div className="py-20 flex flex-col items-center justify-center text-gray-400 gap-3">
                  <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
                  <p className="text-xs">Fetching and formatting prospect updates…</p>
                </div>
              ) : posts.length === 0 ? (
                <div className="bg-white border border-gray-200 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-3">
                  <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto text-xl">
                    🎉
                  </div>
                  <h3 className="text-sm font-bold text-gray-900">All Caught Up!</h3>
                  <p className="text-xs text-gray-500 max-w-sm mx-auto">
                    No {statusFilter} posts found in this list. Click "Fetch Latest Posts" or add more contacts to populate fresh feed updates.
                  </p>
                  <button
                    onClick={handleFetchLatestPosts}
                    className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Check for New Posts
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
                  {posts.map((post) => {
                    const draft = commentDrafts[post.id] || { text: '', autoLike: true };
                    const age = postAge(post.published_at);
                    return (
                      <div
                        key={post.id}
                        data-engage-post={post.id}
                        onClick={() => setActivePostIndex(posts.findIndex((item) => item.id === post.id))}
                        className={`bg-white rounded-2xl border shadow-xs hover:shadow-md transition-shadow p-5 flex flex-col justify-between space-y-4 ${posts[activePostIndex]?.id === post.id ? 'border-indigo-300' : 'border-gray-200'}`}
                      >
                        {/* Author Header */}
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            {statusFilter === 'pending' && (
                              <input
                                type="checkbox"
                                checked={selectedPosts.has(post.id)}
                                disabled={Boolean(post.action_queued_at)}
                                onChange={() => togglePostSelection(post.id)}
                                className="w-3.5 h-3.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 shrink-0 mt-0.5"
                              />
                            )}
                            <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center shrink-0 text-sm">
                              {post.author_avatar ? (
                                <img
                                  src={post.author_avatar}
                                  alt={post.author_name}
                                  className="w-full h-full rounded-full object-cover"
                                />
                              ) : (
                                (post.author_name || 'LinkedIn Member').charAt(0)
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <h4 className="text-xs font-bold text-gray-900 truncate">
                                  {post.author_name || 'LinkedIn Member'}
                                </h4>
                                <span className="w-4 h-4 bg-[#0A66C2] text-white rounded text-[9px] font-bold flex items-center justify-center shrink-0">
                                  in
                                </span>
                              </div>
                              <p className="text-[11px] text-gray-500 truncate">{post.author_headline}</p>
                              <span className="text-[10px] text-gray-400">Published {age.label}</span>
                              {age.old && <span className="block text-[10px] text-amber-700"><Clock3 className="w-3 h-3 inline" /> Older than 7 days — consider whether commenting is timely</span>}
                            </div>
                          </div>

                          <div className="flex items-center gap-1 shrink-0">
                            {post.post_url && (
                              <a
                                href={post.post_url}
                                target="_blank"
                                rel="noreferrer"
                                className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-neutral-50 transition-colors"
                                title="Open on LinkedIn"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            )}
                          </div>
                        </div>

                        {/* Post Content */}
                        <div className="text-xs text-gray-800 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto pr-1">
                          {post.content_text}
                        </div>

                        {/* Post Media */}
                        {post.media_urls && post.media_urls.length > 0 && (
                          <div className={`rounded-xl overflow-hidden ${post.media_urls.length > 1 ? 'grid grid-cols-2 gap-1' : ''}`}>
                            {post.media_urls.slice(0, 2).map((url, idx) => (
                              <div key={idx} className="relative bg-gray-100">
                                {/\.(pdf|docx?|pptx?)(\?|$)/i.test(url) || /\/article\/|\/document\//i.test(url) ? (
                                  <a href={url} target="_blank" rel="noreferrer" className="h-32 flex flex-col items-center justify-center gap-2 text-indigo-600 bg-indigo-50 text-xs font-semibold">
                                    <FileText className="w-6 h-6" /> Open article or document
                                  </a>
                                ) : (
                                  <img src={url} alt={`Post media ${idx + 1}`} className="w-full h-32 object-cover" loading="lazy"
                                    onError={(e) => { e.target.style.display = 'none'; }} />
                                )}
                                {idx === 1 && post.media_urls.length > 2 && (
                                  <div className="absolute inset-0 bg-black/40 flex items-center justify-center text-white text-sm font-bold">
                                    +{post.media_urls.length - 2}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Social Metric Bar */}
                        <div className="flex items-center justify-between text-[11px] text-gray-500 pt-2 border-t border-gray-100">
                          <span className="flex items-center gap-1">
                            👍 💡 ❤️ {post.reactions_count} reactions
                          </span>
                          <span>{post.comments_count} comments</span>
                        </div>

                        {/* Quick Actions (Like / Discard) */}
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            onClick={() => handleLikePost(post.id)}
                            disabled={likingPosts[post.id] || Boolean(post.action_queued_at) || post.status !== 'pending' || !selectedAccountId}
                            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-xl border text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                              post.status === 'liked'
                                ? 'border-blue-200 bg-blue-50 text-blue-600'
                                : 'border-gray-200 text-gray-700 hover:bg-neutral-50'
                            }`}
                          >
                            {likingPosts[post.id] ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-600" />
                            ) : (
                              <ThumbsUp className="w-3.5 h-3.5 text-blue-600" />
                            )}
                            {post.status === 'liked' ? 'Liked ✓' : post.action_queued_at ? 'Queued…' : 'Like Post'}
                          </button>
                          <button
                            onClick={() => handleDiscardPost(post.id)}
                            disabled={post.status !== 'pending' || Boolean(post.action_queued_at)}
                            className="flex items-center justify-center gap-1.5 py-1.5 rounded-xl border border-gray-200 text-xs font-semibold text-gray-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors disabled:opacity-50"
                          >
                            <X className="w-3.5 h-3.5" /> Discard
                          </button>
                        </div>

                        <div className="relative flex py-1 items-center">
                          <div className="flex-grow border-t border-gray-100"></div>
                          <span className="flex-shrink mx-2 text-[10px] text-gray-400 font-bold uppercase tracking-wider">
                            OR COMMENT
                          </span>
                          <div className="flex-grow border-t border-gray-100"></div>
                        </div>

                        {/* In-Line Comment Composer */}
                        <div className="space-y-2.5">
                          <div className="relative">
                            <textarea
                              rows={3}
                              disabled={!['pending', 'liked'].includes(post.status)}
                              placeholder="Write a thoughtful comment to warm up this prospect…"
                              value={draft.text}
                              onChange={(e) =>
                                setCommentDrafts((prev) => ({
                                  ...prev,
                                  [post.id]: { ...draft, text: e.target.value },
                                }))
                              }
                              className="w-full text-xs text-gray-800 p-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none resize-none transition-all placeholder:text-gray-400"
                            />
                            {/* AI Comment Trigger Button */}
                            <button
                              onClick={() => openAiModal(post)}
                              disabled={!['pending', 'liked'].includes(post.status)}
                              className="absolute bottom-3 right-3 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-semibold transition-colors shadow-xs"
                              title="Generate AI comments"
                            >
                              <Sparkles className="w-3 h-3 text-indigo-600" /> AI Assist
                            </button>
                          </div>

                          <div className="flex items-center justify-between">
                            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-600 select-none">
                              <input
                                type="checkbox"
                                checked={draft.autoLike}
                                onChange={(e) =>
                                  setCommentDrafts((prev) => ({
                                    ...prev,
                                    [post.id]: { ...draft, autoLike: e.target.checked },
                                  }))
                                }
                                className="rounded text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
                              />
                              <span>Auto-like post on comment</span>
                            </label>

                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => saveReviewDraft(post.id, draft.text)}
                                disabled={draftBusy || !draft.text?.trim() || !['pending', 'liked'].includes(post.status)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-indigo-200 text-indigo-700 text-xs font-semibold disabled:opacity-50"
                              >
                                Save for Review
                              </button>
                              <button
                                onClick={() => handleSendComment(post.id)}
                                disabled={draft.posting || Boolean(post.action_queued_at) || !draft.text?.trim() || !selectedAccountId || !['pending', 'liked'].includes(post.status)}
                                className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all disabled:opacity-50 active:scale-95"
                              >
                                {draft.posting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                                Post Comment
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Load More */}
              {!loadingPosts && posts.length > 0 && posts.length < totalPosts && (
                <div className="flex justify-center pt-2">
                  <button
                    onClick={() => fetchPosts(activeList.id, statusFilter, true, posts.length)}
                    className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl bg-white border border-gray-200 text-gray-600 text-xs font-semibold hover:bg-gray-50 transition-colors shadow-xs"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Load More ({totalPosts - posts.length} remaining)
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Manual draft queue: no LinkedIn write occurs here. */}
          {activeTab === 'drafts' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-xs text-indigo-900">
                Review and edit suggestions here, then copy and publish them yourself on LinkedIn. Marking a draft done is self-reported and never counts as confirmed engagement or unlocks campaign warm-up.
              </div>
              {drafts.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
                  No pending drafts. Save a comment from a post or an AI suggestion to review it here.
                </div>
              ) : drafts.map((draft) => (
                <div key={draft.id} className="rounded-2xl border border-gray-200 bg-white p-5 space-y-3">
                  <div className="text-xs text-gray-600">
                    <strong className="text-gray-900">{draft.author_name || 'LinkedIn Member'}</strong>
                    <p className="mt-1 line-clamp-3">{draft.post_excerpt || 'Post content unavailable'}</p>
                  </div>
                  <label className="block text-xs font-semibold text-gray-700" htmlFor={`draft-${draft.id}`}>Your draft</label>
                  <textarea id={`draft-${draft.id}`} rows={3} value={draftEdits[draft.id] ?? draft.comment_text}
                    onChange={(event) => setDraftEdits((previous) => ({ ...previous, [draft.id]: event.target.value }))}
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs text-gray-800" />
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <button disabled={draftBusy || !draftEdits[draft.id]?.trim()} onClick={() => updateReviewDraft(draft.id, { comment_text: draftEdits[draft.id] })}
                      className="rounded-lg border border-indigo-200 px-3 py-1.5 font-semibold text-indigo-700 disabled:opacity-50">Save edit</button>
                    <button disabled={draftBusy || !draftEdits[draft.id]?.trim()} onClick={async () => {
                      try { await navigator.clipboard.writeText(draftEdits[draft.id]); toast.success('Copied. Publish it yourself on LinkedIn.'); }
                      catch (_) { toast.error('Could not copy draft. Select and copy the text manually.'); }
                    }} className="rounded-lg border border-gray-200 px-3 py-1.5 font-semibold text-gray-700 disabled:opacity-50">Copy text</button>
                    {draft.post_url?.startsWith('https://www.linkedin.com/') && (
                      <a href={draft.post_url} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-gray-200 px-3 py-1.5 font-semibold text-gray-700">Open on LinkedIn ↗</a>
                    )}
                    <button disabled={draftBusy} onClick={() => updateReviewDraft(draft.id, { comment_text: draftEdits[draft.id], status: 'completed' })}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 font-semibold text-white disabled:opacity-50">Mark done manually</button>
                    <button disabled={draftBusy} onClick={() => updateReviewDraft(draft.id, { status: 'dismissed' })}
                      className="rounded-lg px-3 py-1.5 font-semibold text-gray-500 disabled:opacity-50">Dismiss</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Contacts Tab */}
          {activeTab === 'contacts' && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-xs overflow-hidden">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">List Contacts</h3>
                  <p className="text-xs text-gray-500">Profiles monitored for recent LinkedIn activity</p>
                </div>
                <button
                  onClick={() => setShowAddContactsModal(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Profile URL
                </button>
              </div>

              {!activeList.contacts || activeList.contacts.length === 0 ? (
                <div className="p-12 text-center text-gray-400 space-y-2">
                  <Users className="w-8 h-8 mx-auto text-gray-300" />
                  <p className="text-xs">No contacts in this list yet.</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {activeList.contacts.map((c) => (
                    <div key={c.id} className="p-4 flex items-center justify-between hover:bg-neutral-50/50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-xs">
                          {c.avatar_url ? <img src={c.avatar_url} alt="" className="w-full h-full rounded-full object-cover" /> : c.full_name?.charAt(0) || 'L'}
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-gray-900">{c.full_name || 'Unverified LinkedIn profile'}</h4>
                          <p className="text-[11px] text-gray-500">{c.headline || (c.enrichment_status === 'pending' ? 'Verification pending' : c.profile_url)}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <button onClick={() => openContactHistory(c)} className="text-xs text-indigo-600 font-semibold hover:text-indigo-800">History</button>
                        <a href={c.profile_url} target="_blank" rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                          Profile <ExternalLink className="w-3 h-3" />
                        </a>
                        <button onClick={() => handleDeleteContact(c)} title="Remove contact" className="text-gray-400 hover:text-red-600">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Modal: Create List ────────────────────────────────────────────── */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-gray-200 max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <h3 className="text-base font-bold text-gray-900">Create Engagement List</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateList} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-700">List Name</label>
                <input
                  type="text"
                  placeholder="e.g. SaaS Founders BIP, Dream 50 Prospects"
                  value={newListName}
                  onChange={(e) => setNewListName(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700">Emoji Icon</label>
                <div className="flex gap-2 mt-1">
                  {['🎯', '💼', '🚀', '⭐', '🔥', '💡', '👑', '🤝'].map((em) => (
                    <button
                      type="button"
                      key={em}
                      onClick={() => setNewListEmoji(em)}
                      className={`w-9 h-9 rounded-xl border text-base flex items-center justify-center transition-all ${
                        newListEmoji === em ? 'border-indigo-600 bg-indigo-50 scale-105' : 'border-gray-200 hover:bg-neutral-50'
                      }`}
                    >
                      {em}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700">Description (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Pre-warming accounts before Q3 sequence launch"
                  value={newListDesc}
                  onChange={(e) => setNewListDesc(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
                >
                  Create List
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Add Contacts ──────────────────────────────────────────── */}
      {showAddContactsModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-gray-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <h3 className="text-base font-bold text-gray-900">
                Add Contacts to "{activeList?.name}"
              </h3>
              <button onClick={() => setShowAddContactsModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-700">LinkedIn Profile URL</label>
                <div className="flex gap-2 mt-1">
                  <input
                    type="url"
                    placeholder="https://www.linkedin.com/in/satyanadella/"
                    value={contactUrlInput}
                    onChange={(e) => setContactUrlInput(e.target.value)}
                    className="flex-1 text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (contactUrlInput.trim()) {
                        setContactUrlsList([...contactUrlsList, contactUrlInput.trim()]);
                        setContactUrlInput('');
                      }
                    }}
                    className="px-3.5 py-2 rounded-xl bg-neutral-100 hover:bg-neutral-200 text-xs font-bold text-gray-700"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {contactUrlsList.length > 0 && (
                <div className="max-h-28 overflow-y-auto space-y-1 bg-neutral-50 p-2.5 rounded-xl border border-gray-200">
                  {contactUrlsList.map((u, i) => (
                    <div key={i} className="flex items-center justify-between text-[11px] text-gray-700">
                      <span className="truncate max-w-[340px]">{u}</span>
                      <button
                        onClick={() => setContactUrlsList(contactUrlsList.filter((_, idx) => idx !== i))}
                        className="text-gray-400 hover:text-red-500"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-gray-700">Or Paste CSV / Bulk URLs</label>
                  <span className="text-[10px] text-gray-400">1 column with LinkedIn profile links</span>
                </div>
                <textarea
                  rows={3}
                  placeholder="https://linkedin.com/in/prospect1&#10;https://linkedin.com/in/prospect2"
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowAddContactsModal(false)}
                  className="px-4 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-neutral-50"
                >
                  Discard
                </button>
                <button
                  onClick={handleAddContacts}
                  className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
                >
                  Add Contacts
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: AI Comments Generator ─────────────────────────────────── */}
      {aiModalPost && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-gray-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Sparkles className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold text-gray-900">AI-Generated Comments</h3>
              </div>
              <button onClick={() => setAiModalPost(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Post snippet */}
            <div className="bg-neutral-50 p-3 rounded-xl border border-gray-200 text-xs text-gray-600 max-h-24 overflow-y-auto">
              <span className="font-bold text-gray-900 block mb-0.5">{aiModalPost.author_name}:</span>
              {aiModalPost.content_text}
            </div>

            {/* Tone Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-gray-700">Select Tone</label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  { id: 'insightful', label: '💡 Insightful' },
                  { id: 'supportive', label: '🤝 Supportive' },
                  { id: 'questioning', label: '❓ Questioning' },
                  { id: 'challenger', label: '⚡ Challenger' },
                  { id: 'humorous', label: '😄 Humorous' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setAiTone(t.id)}
                    className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-all ${
                      aiTone === t.id
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'bg-neutral-100 text-gray-600 hover:bg-neutral-200'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom instruction */}
            <div>
              <label className="text-xs font-semibold text-gray-700">Writing Style</label>
              <select value={selectedStyleId} onChange={(event) => setSelectedStyleId(event.target.value)}
                className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl">
                <option value="">No saved style</option>
                {styles.map((style) => <option key={style.id} value={style.id}>{style.name}{style.is_default ? ' (default)' : ''}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700">Add Instructions (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Focus on speed to lead, mention our experiment…"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              onClick={() => handleGenerateAIComments(aiModalPost)}
              disabled={aiLoading}
              className="w-full py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all flex items-center justify-center gap-1.5 disabled:opacity-50"
            >
              {aiLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {aiLoading ? 'Generating High-Value Comments…' : 'Regenerate Comments'}
            </button>

            {/* Generated Options */}
            {aiComments.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-gray-100">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                  Select a comment to insert:
                </span>
                {aiComments.map((com, idx) => (
                  <div
                    key={idx}
                    onClick={() => selectAiComment(com)}
                    className="p-3 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/30 text-xs text-gray-800 leading-relaxed cursor-pointer transition-all flex items-start justify-between gap-3 group"
                  >
                    <p>{com}</p>
                    <div className="flex shrink-0 items-center gap-1">
                      <button onClick={(event) => { event.stopPropagation(); saveReviewDraft(aiModalPost.id, com); }} disabled={draftBusy}
                        className="text-[10px] font-bold text-indigo-600 bg-white px-2 py-0.5 rounded border border-indigo-200 disabled:opacity-50">
                        Save to Drafts
                      </button>
                      <button className="text-[10px] font-bold text-indigo-600 bg-white px-2 py-0.5 rounded border border-indigo-200">Use</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {report && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 p-4 md:p-10" role="dialog" aria-modal="true" aria-label="Engagement report">
          <section id="engage-print-report" className="mx-auto max-w-2xl rounded-2xl bg-white p-8 shadow-xl">
            <div className="engage-no-print mb-6 flex items-center justify-end gap-3">
              <button onClick={() => window.print()} className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white">Print / Save as PDF</button>
              <button onClick={() => setReport(null)} className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-semibold text-gray-700">Close</button>
            </div>
            <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">Engage & Grow</p>
            <h2 className="mt-1 text-2xl font-bold text-gray-900">{report.list_name}</h2>
            <p className="mt-1 text-xs text-gray-500">Recorded engagement summary · Generated {new Date(report.generated_at || Date.now()).toLocaleString()}</p>
            <div className="mt-8 grid grid-cols-2 gap-4 border-y border-gray-200 py-6">
              {[
                ['Contacts in list', report.contacts],
                ['Cached posts', report.posts_fetched],
                ['Confirmed likes sent', report.likes_sent],
                ['Confirmed comments published', report.comments_published],
                ['Contacts engaged', report.contacts_engaged],
                ['Posts dismissed', report.posts_discarded],
              ].map(([label, value]) => <div key={label} className="rounded-xl bg-gray-50 p-4">
                <div className="text-2xl font-bold text-gray-900">{value ?? 0}</div>
                <div className="mt-1 text-xs text-gray-600">{label}</div>
              </div>)}
            </div>
            <p className="mt-5 text-xs leading-relaxed text-gray-500">
              Only timestamped LinkedIn-confirmed likes and comments are included. Drafts marked done manually are excluded. Likes and comments can overlap on the same post.
              {report.limited_to_recent_10000_posts && ' This summary covers the first 10,000 cached posts.'}
            </p>
          </section>
        </div>
      )}

      {historyContact && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-gray-200 max-w-lg w-full p-5 shadow-xl space-y-3 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center">
              <h3 className="text-sm font-bold text-gray-900">Engagement with {historyContact.full_name || historyContact.profile_url}</h3>
              <button onClick={() => setHistoryContact(null)} aria-label="Close history"><X className="w-4 h-4" /></button>
            </div>
            {historyPosts.length === 0 ? <p className="text-xs text-gray-500">No confirmed engagement on cached posts yet.</p> :
              historyPosts.map((event, index) => <div key={`${event.post_id}-${event.action}-${index}`} className="border-l-2 border-indigo-200 pl-3 py-2 text-xs text-gray-700">
                <div className="font-semibold capitalize">{event.action} · {event.at ? postAge(event.at).label : 'Date unavailable'}</div>
                {event.comment && <p className="mt-1">“{event.comment}”</p>}
                {event.post_url && <a href={event.post_url} target="_blank" rel="noreferrer" className="text-indigo-600">View post ↗</a>}
              </div>)}
          </div>
        </div>
      )}
    </div>
  );
}
