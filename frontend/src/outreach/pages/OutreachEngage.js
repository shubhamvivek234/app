import React, { useState, useEffect, useCallback } from 'react';

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
} from 'lucide-react';
import { toast } from 'sonner';

export default function OutreachEngage() {
  const [lists, setLists] = useState([]);
  const [loadingLists, setLoadingLists] = useState(true);
  const [activeList, setActiveList] = useState(null);
  const [activeTab, setActiveTab] = useState('posts'); // 'posts' | 'contacts'
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

  const fetchLists = useCallback(async () => {
    setLoadingLists(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/lists', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setLists(data || []);
      }
    } catch (_) {
      toast.error('Failed to load engagement lists');
    } finally {
      setLoadingLists(false);
    }
  }, []);

  const fetchPosts = useCallback(async (listId, filter = 'pending') => {
    setLoadingPosts(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/lists/${listId}/posts?status_filter=${filter}`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setPosts(data.posts || []);
      }
    } catch (_) {
      toast.error('Failed to load prospect posts');
    } finally {
      setLoadingPosts(false);
    }
  }, []);

  useEffect(() => {
    fetchLists();
  }, [fetchLists]);

  useEffect(() => {
    if (activeList) {
      fetchPosts(activeList.id, statusFilter);
    }
  }, [activeList, statusFilter, fetchPosts]);

  const handleCreateList = async (e) => {

    e.preventDefault();
    if (!newListName.trim()) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/lists', {
        method: 'POST',
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
      }
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
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('List deleted');
        if (activeList?.id === listId) setActiveList(null);
        fetchLists();
      }
    } catch (_) {
      toast.error('Failed to delete list');
    }
  };

  const handleFetchLatestPosts = async () => {
    if (!activeList) return;
    setLoadingPosts(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}/fetch`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Fetched ${data.posts_fetched} recent posts from contacts!`);
        fetchPosts(activeList.id, statusFilter);
        fetchLists();
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
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          profile_urls: contactUrlsList,
          csv_text: csvText || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Added ${data.added_count} contacts!`);
        setShowAddContactsModal(false);
        setContactUrlsList([]);
        setCsvText('');
        setContactUrlInput('');
        fetchLists();
        // Refresh active list details
        const listRes = await fetch(`/api/v1/outreach/engage/lists/${activeList.id}`, {
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (listRes.ok) setActiveList(await listRes.json());
      }
    } catch (_) {
      toast.error('Failed to add contacts');
    }
  };

  const handleLikePost = async (postId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/like`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        toast.success('Liked post on LinkedIn!');
        setPosts((prev) =>
          prev.map((p) => (p.id === postId ? { ...p, status: 'liked', reactions_count: p.reactions_count + 1 } : p))
        );
      }
    } catch (_) {
      toast.error('Failed to like post');
    }
  };

  const handleDiscardPost = async (postId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/engage/posts/${postId}/discard`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Dismissed post from feed');
        setPosts((prev) => prev.filter((p) => p.id !== postId));
      }
    } catch (_) {
      toast.error('Failed to discard post');
    }
  };

  const handleSendComment = async (postId) => {
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
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          comment_text: draft.text.trim(),
          auto_like: draft.autoLike ?? true,
        }),
      });
      if (res.ok) {
        toast.success('Comment posted to LinkedIn (auto-liked)!');
        setPosts((prev) => prev.filter((p) => p.id !== postId));
        setCommentDrafts((prev) => {
          const updated = { ...prev };
          delete updated[postId];
          return updated;
        });
      }
    } catch (_) {
      toast.error('Failed to post comment');
    } finally {
      setCommentDrafts((prev) => ({
        ...prev,
        [postId]: { ...prev[postId], posting: false },
      }));
    }
  };

  const handleGenerateAIComments = async (post) => {
    setAiModalPost(post);
    setAiComments([]);
    setAiLoading(true);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/engage/ai-comment', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          post_text: post.content_text,
          author_headline: post.author_headline,
          tone: aiTone,
          custom_prompt: aiPrompt,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setAiComments(data.comments || []);
      }
    } catch (_) {
      toast.error('AI comment generation failed');
    } finally {
      setAiLoading(false);
    }
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
                    High Conversion
                  </span>
                </div>
                <p className="text-xs text-gray-600 mt-0.5">
                  Liking and leaving an insightful comment on prospects' posts 24h prior boosts cold connection acceptances from 12% to over 50%.
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
                  onClick={() => setActiveList(l)}
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
              </div>

              <button
                onClick={() => setShowAddContactsModal(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-neutral-50 transition-colors shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" /> Add Contacts
              </button>

              <button
                onClick={handleFetchLatestPosts}
                disabled={loadingPosts}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-xs disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingPosts ? 'animate-spin' : ''}`} />
                Fetch Latest Posts
              </button>
            </div>
          </div>

          {/* Posts Feed Tab */}
          {activeTab === 'posts' && (
            <div className="space-y-4">
              {/* Filter controls */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {['pending', 'commented', 'all'].map((st) => (
                    <button
                      key={st}
                      onClick={() => setStatusFilter(st)}
                      className={`text-xs px-3 py-1 rounded-lg font-medium capitalize transition-colors ${
                        statusFilter === st
                          ? 'bg-gray-900 text-white'
                          : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {st === 'pending' ? 'Pending Posts' : st}
                    </button>
                  ))}
                </div>
                <span className="text-xs text-gray-400">
                  {posts.length} {statusFilter} post{posts.length !== 1 ? 's' : ''}
                </span>
              </div>

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
                    return (
                      <div
                        key={post.id}
                        className="bg-white rounded-2xl border border-gray-200 shadow-xs hover:shadow-md transition-shadow p-5 flex flex-col justify-between space-y-4"
                      >
                        {/* Author Header */}
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center shrink-0 text-sm">
                              {post.author_avatar ? (
                                <img
                                  src={post.author_avatar}
                                  alt={post.author_name}
                                  className="w-full h-full rounded-full object-cover"
                                />
                              ) : (
                                post.author_name.charAt(0)
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <h4 className="text-xs font-bold text-gray-900 truncate">
                                  {post.author_name}
                                </h4>
                                <span className="w-4 h-4 bg-[#0A66C2] text-white rounded text-[9px] font-bold flex items-center justify-center shrink-0">
                                  in
                                </span>
                              </div>
                              <p className="text-[11px] text-gray-500 truncate">{post.author_headline}</p>
                              <span className="text-[10px] text-gray-400">Published {post.published_at}</span>
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
                            className="flex items-center justify-center gap-1.5 py-1.5 rounded-xl border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-neutral-50 transition-colors"
                          >
                            <ThumbsUp className="w-3.5 h-3.5 text-blue-600" /> Like Post
                          </button>
                          <button
                            onClick={() => handleDiscardPost(post.id)}
                            className="flex items-center justify-center gap-1.5 py-1.5 rounded-xl border border-gray-200 text-xs font-semibold text-gray-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
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
                              onClick={() => handleGenerateAIComments(post)}
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

                            <button
                              onClick={() => handleSendComment(post.id)}
                              disabled={draft.posting || !draft.text?.trim()}
                              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all disabled:opacity-50 active:scale-95"
                            >
                              {draft.posting ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Send className="w-3.5 h-3.5" />
                              )}
                              Post Comment
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
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
                          {c.full_name?.charAt(0) || 'L'}
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-gray-900">{c.full_name}</h4>
                          <p className="text-[11px] text-gray-500">{c.headline}</p>
                        </div>
                      </div>
                      <a
                        href={c.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        Profile <ExternalLink className="w-3 h-3" />
                      </a>
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
                    <button className="opacity-0 group-hover:opacity-100 text-[10px] font-bold text-indigo-600 shrink-0 bg-white px-2 py-0.5 rounded border border-indigo-200 shadow-xs">
                      Use
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
