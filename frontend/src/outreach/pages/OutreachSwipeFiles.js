import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Bookmark,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  ExternalLink,
  Copy,
  Check,
  X,
  Loader2,
  FileText,
} from 'lucide-react';
import { toast } from 'sonner';

const PAGE_SIZE = 30;

async function swipeFetch(url, options = {}) {
  const token = localStorage.getItem('token');
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: { Authorization: token ? `Bearer ${token}` : '', ...options.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Request failed');
  }
  return response.json();
}

export default function OutreachSwipeFiles() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const requestId = useRef(0);
  const [search, setSearch] = useState('');
  const [selectedTag, setSelectedTag] = useState('all');

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [newAuthor, setNewAuthor] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newTag, setNewTag] = useState('Outbound Hooks');
  const [newUrl, setNewUrl] = useState('');

  // Repurpose modal
  const [repurposeItem, setRepurposeItem] = useState(null);
  const [targetFormat, setTargetFormat] = useState('outbound_hook'); // 'outbound_hook' | 'connection_note' | 'post'
  const [writingStyles, setWritingStyles] = useState([]);
  const [writingStyleId, setWritingStyleId] = useState('');
  const [customInstructions, setCustomInstructions] = useState('');
  const [repurposeLoading, setRepurposeLoading] = useState(false);
  const [repurposedText, setRepurposedText] = useState('');
  const [copied, setCopied] = useState(false);

  const fetchSwipeItems = useCallback(async (offset = 0) => {
    const currentRequest = ++requestId.current;
    if (offset) setLoadingMore(true);
    else { setLoading(true); setLoadError(''); }
    try {
      const params = new URLSearchParams();
      if (selectedTag !== 'all') params.append('tag', selectedTag);
      if (search.trim()) params.append('search', search.trim());
      params.set('skip', String(offset));
      params.set('limit', String(PAGE_SIZE));
      const data = await swipeFetch(`/api/v1/outreach/swipe?${params.toString()}`);
      if (currentRequest !== requestId.current) return;
      setItems((previous) => offset ? [...previous, ...data] : data);
      setHasMore(data.length === PAGE_SIZE);
    } catch (error) {
      if (currentRequest === requestId.current) {
        if (!offset) {
          setItems([]);
          setHasMore(false);
          setLoadError(error.message || 'Failed to load swipe files');
        }
        toast.error(error.message || 'Failed to load swipe files');
      }
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [selectedTag, search]);

  useEffect(() => {
    const timer = setTimeout(() => fetchSwipeItems(), 250);
    return () => { clearTimeout(timer); requestId.current += 1; };
  }, [fetchSwipeItems]);

  useEffect(() => {
    if (!repurposeItem) return;
    let mounted = true;
    swipeFetch('/api/v1/outreach/styles')
      .then((data) => {
        if (mounted) {
          setWritingStyles(data || []);
          setWritingStyleId((data || []).find((style) => style.is_default)?.id || '');
        }
      })
      .catch(() => { if (mounted) toast.error('Could not load writing styles'); });
    return () => { mounted = false; };
  }, [repurposeItem]);


  const handleCreateSwipeItem = async (e) => {
    e.preventDefault();
    if (!newContent.trim()) return;

    if (saving) return;
    setSaving(true);
    try {
      await swipeFetch('/api/v1/outreach/swipe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_name: newAuthor.trim() || 'Unknown Creator',
          content_text: newContent.trim(),
          tags: [newTag],
          post_url: newUrl.trim(),
        }),
      });
      toast.success('Saved to swipe files!');
      setShowAddModal(false);
      setNewAuthor('');
      setNewContent('');
      setNewUrl('');
      fetchSwipeItems();
    } catch (error) {
      toast.error(error.message || 'Failed to save swipe item');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteItem = async (id) => {
    if (deletingId) return;
    if (!window.confirm('Delete this swipe item?')) return;
    setDeletingId(id);
    try {
      await swipeFetch(`/api/v1/outreach/swipe/${id}`, {
        method: 'DELETE',
      });
      toast.success('Swipe file removed');
      fetchSwipeItems();
    } catch (error) {
      toast.error(error.message || 'Failed to delete item');
    } finally {
      setDeletingId(null);
    }
  };

  const handleRepurpose = async () => {
    if (!repurposeItem) return;
    setRepurposeLoading(true);
    setRepurposedText('');

    try {
      const data = await swipeFetch(`/api/v1/outreach/swipe/${repurposeItem.id}/repurpose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_format: targetFormat,
          custom_instructions: customInstructions.trim(),
          writing_style_id: writingStyleId || null,
        }),
      });
      setRepurposedText(data.repurposed_text);
      toast.success('Repurposed with AI!');
    } catch (error) {
      toast.error(error.message || 'Repurposing failed');
    } finally {
      setRepurposeLoading(false);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success('Copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    } catch (_) {
      toast.error('Could not copy. Please select and copy the text manually.');
    }
  };

  return (
    <div className="flex-1 h-full overflow-y-auto bg-neutral-50/50 p-6 md:p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-gray-200/80">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Swipe Files</h1>
              <span className="text-[11px] font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-md">
                Inspiration Hub
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              Organize your creative process and build a gallery of inspiration and good ideas with a social media swipe file.
            </p>
          </div>

          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all shrink-0 active:scale-95"
          >
            <Plus className="w-4 h-4" /> Add Swipe File
          </button>
        </div>

        {/* Filter & Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search swipe files…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full text-xs pl-8 pr-3 py-1.5 rounded-xl border border-gray-200 bg-white focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <select
              value={selectedTag}
              onChange={(e) => setSelectedTag(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-gray-700 focus:border-indigo-500 focus:outline-none"
            >
              <option value="all">All Tags</option>
              <option value="Outbound Hooks">Outbound Hooks</option>
              <option value="LinkedIn">LinkedIn</option>
              <option value="Storytelling">Storytelling</option>
              <option value="SaaS & Tech">SaaS & Tech</option>
            </select>
          </div>

          <span className="text-xs text-gray-400 self-end sm:self-auto">
            {items.length} swiped idea{items.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Cards Grid */}
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-gray-400 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
            <p className="text-xs">Loading swipe cards…</p>
          </div>
        ) : loadError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center text-xs text-red-800">
            <p>{loadError}</p>
            <button type="button" onClick={() => fetchSwipeItems()} className="mt-3 rounded-lg bg-white px-3 py-1.5 font-semibold">Retry</button>
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white border border-dashed border-gray-300 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto text-2xl">
              🔖
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900">Your Swipe File is Empty</h3>
              <p className="text-xs text-gray-500 mt-1 max-w-sm mx-auto">
                Save viral posts, high-converting outbound messages, or hooks that inspire you. Use 1-click AI to repurpose them into your own voice.
              </p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm"
            >
              <Plus className="w-4 h-4" /> Add First Swipe
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 items-start">
            {items.map((item) => (
              <div
                key={item.id}
                className="bg-white rounded-2xl border border-gray-200/90 shadow-xs hover:shadow-md transition-all p-5 flex flex-col justify-between space-y-4"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 pb-3 border-b border-gray-100">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-xs shrink-0">
                        {item.author_name.charAt(0)}
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-xs font-bold text-gray-900 truncate">{item.author_name}</h4>
                        <span className="text-[10px] text-gray-400">Author</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      {item.post_url && (
                        <a
                          href={item.post_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-gray-400 hover:text-indigo-600 p-1"
                          title="Original Link"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      <button
                        onClick={() => handleDeleteItem(item.id)}
                        disabled={deletingId === item.id}
                        className="text-gray-300 hover:text-red-500 p-1"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 text-xs text-gray-800 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto pr-1">
                    {item.content_text}
                  </div>
                </div>

                <div className="pt-3 border-t border-gray-100 space-y-3">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {item.tags?.map((tag, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] font-semibold bg-neutral-100 text-gray-600 px-2 py-0.5 rounded-md"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  {/* 1-Click Repurpose Button */}
                  <button
                    onClick={() => {
                      setRepurposeItem(item);
                      setRepurposedText('');
                    }}
                    className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold transition-all shadow-xs group"
                  >
                    <RefreshCw className="w-3.5 h-3.5 text-indigo-600 group-hover:rotate-180 transition-transform duration-500" />
                    Repurpose with AI
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {hasMore && !loading && (
          <button
            type="button"
            onClick={() => fetchSwipeItems(items.length)}
            disabled={loadingMore}
            className="mx-auto flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs font-semibold text-gray-700 disabled:opacity-50"
          >
            {loadingMore && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Load more swipe files
          </button>
        )}
      </div>

      {/* ── Modal: Add Swipe File ────────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-gray-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <h3 className="text-base font-bold text-gray-900">Add to Swipe Files</h3>
              <button onClick={() => setShowAddModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateSwipeItem} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-700">Author Name</label>
                <input
                  type="text"
                  placeholder="e.g. Justin Welsh, Lara Acosta"
                  value={newAuthor}
                  onChange={(e) => setNewAuthor(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700">Post Content / Hook Text</label>
                <textarea
                  rows={4}
                  placeholder="Paste the inspiring post, hook, or cold email body here…"
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none resize-none"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-gray-700">Category Tag</label>
                  <select
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="Outbound Hooks">Outbound Hooks</option>
                    <option value="LinkedIn">LinkedIn</option>
                    <option value="Storytelling">Storytelling</option>
                    <option value="SaaS & Tech">SaaS & Tech</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-700">Original Link (Optional)</label>
                  <input
                    type="url"
                    placeholder="https://linkedin.com/posts/..."
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-neutral-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm disabled:opacity-50"
                >
                  {saving ? 'Saving…' : 'Save Swipe File'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: 1-Click Repurposer ────────────────────────────────────── */}
      {repurposeItem && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-gray-200 max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Sparkles className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold text-gray-900">1-Click AI Repurposer</h3>
              </div>
              <button onClick={() => setRepurposeItem(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Original content snippet */}
            <div className="bg-neutral-50 p-3 rounded-xl border border-gray-200 text-xs text-gray-600 max-h-24 overflow-y-auto">
              <span className="font-bold text-gray-900 block mb-0.5">Original by {repurposeItem.author_name}:</span>
              {repurposeItem.content_text}
            </div>

            {/* Target format */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-gray-700">Transform Into</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: 'outbound_hook', label: '⚡ Outbound Hook' },
                  { id: 'connection_note', label: '🤝 Connection Note' },
                  { id: 'post', label: '📝 LinkedIn Post' },
                ].map((fmt) => (
                  <button
                    key={fmt.id}
                    onClick={() => setTargetFormat(fmt.id)}
                    className={`py-2 text-xs font-semibold rounded-xl border transition-all text-center ${
                      targetFormat === fmt.id
                        ? 'border-indigo-600 bg-indigo-50 text-indigo-700 shadow-xs'
                        : 'border-gray-200 text-gray-600 hover:bg-neutral-50'
                    }`}
                  >
                    {fmt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom Focus */}
            <div>
              <label className="text-xs font-semibold text-gray-700">Writing Style</label>
              <select
                value={writingStyleId}
                onChange={(event) => setWritingStyleId(event.target.value)}
                className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
              >
                <option value="">Default conversational style</option>
                {writingStyles.map((style) => <option key={style.id} value={style.id}>{style.name}</option>)}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700">Custom Focus / Context (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Apply to B2B outbound, emphasize speed to lead…"
                value={customInstructions}
                onChange={(e) => setCustomInstructions(e.target.value)}
                className="mt-1 w-full text-xs p-2.5 border border-gray-200 rounded-xl focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              onClick={handleRepurpose}
              disabled={repurposeLoading}
              className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 active:scale-95"
            >
              {repurposeLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {repurposeLoading ? 'Rewriting with AI…' : 'Generate Repurposed Copy'}
            </button>

            {/* Output */}
            {repurposedText && (
              <div className="space-y-2 pt-2 border-t border-gray-100">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                    Repurposed Output:
                  </span>
                  <button
                    onClick={() => copyToClipboard(repurposedText)}
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
                  >
                    {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <div className="p-3.5 rounded-xl bg-indigo-50/40 border border-indigo-100 text-xs text-gray-900 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                  {repurposedText}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
