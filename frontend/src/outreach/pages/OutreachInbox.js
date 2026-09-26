import React, { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';

const THREAD_PAGE_SIZE = 50;

const inboxFetch = (url, options = {}) => {
  const token = localStorage.getItem('token');
  return fetch(url, {
    ...options,
    credentials: 'include',
    headers: { Authorization: token ? `Bearer ${token}` : '', ...options.headers },
  });
};

async function waitForInboxJob(jobId) {
  for (let attempt = 0; attempt < 45; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const response = await inboxFetch(`/api/v1/outreach/inbox/jobs/${jobId}`);
    if (!response.ok) throw new Error('Could not check inbox job status');
    const job = await response.json();
    if (job.status === 'completed') return job;
    if (job.status === 'failed') throw new Error(job.error || 'Inbox action failed');
  }
  throw new Error('Still processing in the background. Refresh the inbox shortly.');
}
import {
  Search,
  ChevronDown,
  ChevronUp,
  Mail,
  Send,
  RefreshCw,
  Sparkles,
  CheckCircle2,
  ExternalLink,
  User,
  Clock,
  Tag,
  Bookmark,
  Check,
  Plus,
  Trash2,
  Calendar,
  FileText,
  X,
} from 'lucide-react';

export default function OutreachInbox() {
  const [threads, setThreads] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(true); // Open by default matching media_1790103710555.png
  const [selectedThread, setSelectedThread] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMoreThreads, setHasMoreThreads] = useState(false);
  const [filterSource, setFilterSource] = useState('all'); // 'all' | 'outreach'
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [loadingAi, setLoadingAi] = useState(false);

  // Unravler AI Parity: Reminders, Snippets & Tags State
  const [remindersOpen, setRemindersOpen] = useState(false);
  const [remindersList, setRemindersList] = useState([]);
  const [reminderNote, setReminderNote] = useState('');
  const [reminderDate, setReminderDate] = useState('');
  const [loadingReminders, setLoadingReminders] = useState(false);

  const [snippetsOpen, setSnippetsOpen] = useState(false);
  const [snippetsList, setSnippetsList] = useState([]);
  const [snippetSearch, setSnippetSearch] = useState('');
  const [showCreateSnippet, setShowCreateSnippet] = useState(false);
  const [newSnippetTitle, setNewSnippetTitle] = useState('');
  const [newSnippetBody, setNewSnippetBody] = useState('');
  const [newSnippetShortcut, setNewSnippetShortcut] = useState('');

  const [tagsOpen, setTagsOpen] = useState(false);
  const [tagsList, setTagsList] = useState([]);
  const [newTagName, setNewTagName] = useState('');
  const [newTagColor, setNewTagColor] = useState('#3b82f6');
  const [showCreateTag, setShowCreateTag] = useState(false);

  const messagesEndRef = useRef(null);
  const threadsRequestId = useRef(0);
  const selectedThreadId = useRef(null);

  const fetchAccounts = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch('/api/v1/outreach/accounts', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        const activeAccounts = (data || []).filter((account) => account.status === 'active');
        setAccounts(activeAccounts);
        if (selectedAccountId !== 'all' && !activeAccounts.some((account) => account.id === selectedAccountId)) {
          setSelectedAccountId('all');
        }
      } else {
        toast.error('Could not load sender accounts');
      }
    } catch (err) {
      console.error('Failed to load accounts:', err);
    }
  };

  const fetchThreads = async (offset = 0) => {
    const requestId = ++threadsRequestId.current;
    if (offset) setLoadingMore(true);
    else { setLoading(true); setLoadError(''); }
    try {
      const token = localStorage.getItem('token');
      let url = `/api/v1/outreach/inbox?account_id=${selectedAccountId}&skip=${offset}&limit=${THREAD_PAGE_SIZE}`;
      if (filterSource === 'outreach') {
        url += '&source=outreach';
      }
      if (searchQuery.trim()) {
        url += `&search=${encodeURIComponent(searchQuery.trim())}`;
      }
      const res = await inboxFetch(url, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error('Could not load conversations');
      const data = await res.json();
      if (requestId !== threadsRequestId.current) return;
      setThreads((previous) => offset ? [...previous, ...data] : data);
      setHasMoreThreads(data.length === THREAD_PAGE_SIZE);
      if (offset) return;
      const updated = data.find((t) => t.id === selectedThreadId.current);
      if (updated) setSelectedThread(updated);
      else if (data.length) {
        handleSelectThread(data[0]);
      } else {
        selectedThreadId.current = null;
        setSelectedThread(null);
        setRemindersList([]);
      }
    } catch (err) {
      console.error('Failed to load threads:', err);
      if (requestId === threadsRequestId.current) {
        if (!offset) {
          setThreads([]);
          setSelectedThread(null);
          selectedThreadId.current = null;
          setHasMoreThreads(false);
          setLoadError(err.message || 'Could not load conversations');
        }
        toast.error(err.message || 'Could not load conversations');
      }
    } finally {
      if (requestId === threadsRequestId.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    fetchAccounts();
    fetchSnippets();
    fetchTags();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Hotkey listener for [S] Reminders, [C] Snippets, [T] Tags, [Escape] Close
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        setRemindersOpen((prev) => !prev);
      } else if (e.key === 'c' || e.key === 'C') {
        e.preventDefault();
        setSnippetsOpen((prev) => !prev);
      } else if (e.key === 't' || e.key === 'T') {
        e.preventDefault();
        setTagsOpen((prev) => !prev);
      } else if (e.key === 'Escape') {
        setRemindersOpen(false);
        setSnippetsOpen(false);
        setTagsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const fetchReminders = async (threadId) => {
    if (!threadId) return;
    setLoadingReminders(true);
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${threadId}/reminders`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        if (selectedThreadId.current === threadId) setRemindersList(data || []);
      }
    } catch (err) {
      console.error('Failed to load reminders:', err);
    } finally {
      setLoadingReminders(false);
    }
  };

  const handleSetReminder = async (quickDays = null) => {
    if (!selectedThread) return;
    try {
      const token = localStorage.getItem('token');
      let targetDate;
      if (quickDays !== null) {
        const d = new Date();
        d.setDate(d.getDate() + quickDays);
        d.setHours(9, 0, 0, 0);
        targetDate = d.toISOString();
      } else if (reminderDate) {
        targetDate = new Date(reminderDate).toISOString();
      } else {
        const d = new Date();
        d.setDate(d.getDate() + 1);
        d.setHours(9, 0, 0, 0);
        targetDate = d.toISOString();
      }

      const res = await inboxFetch(`/api/v1/outreach/inbox/${selectedThread.id}/reminders`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          remind_at: targetDate,
          note: reminderNote.trim() || 'Follow up on conversation',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setRemindersList((prev) => [data.reminder, ...prev]);
        setSelectedThread((prev) => ({
          ...prev,
          remind_at: targetDate,
          reminder_note: reminderNote.trim(),
        }));
        setReminderNote('');
        setReminderDate('');
        setRemindersOpen(false);
        toast.success('Follow-up reminder scheduled');
      } else {
        toast.error('Failed to schedule reminder');
      }
    } catch (err) {
      console.error('Failed to set reminder:', err);
      toast.error('Failed to schedule reminder');
    }
  };

  const handleDeleteReminder = async (remId) => {
    if (!remId) return;
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/reminders/${remId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setRemindersList((prev) => prev.filter((r) => r.id !== remId));
        setSelectedThread((prev) => prev && ({
          ...prev,
          remind_at: data.next_reminder?.remind_at || null,
          reminder_note: data.next_reminder?.note || null,
        }));
        toast.success('Reminder dismissed');
      } else {
        toast.error('Failed to dismiss reminder');
      }
    } catch (err) {
      console.error('Failed to delete reminder:', err);
      toast.error('Failed to dismiss reminder');
    }
  };

  const fetchSnippets = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch('/api/v1/outreach/inbox/snippets/list', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setSnippetsList(data || []);
      }
    } catch (err) {
      console.error('Failed to load snippets:', err);
    }
  };

  const handleCreateSnippet = async () => {
    if (!newSnippetTitle.trim() || !newSnippetBody.trim()) return;
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch('/api/v1/outreach/inbox/snippets', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          title: newSnippetTitle.trim(),
          body: newSnippetBody.trim(),
          shortcut: newSnippetShortcut.trim(),
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setSnippetsList((prev) => [created, ...prev]);
        setNewSnippetTitle('');
        setNewSnippetBody('');
        setNewSnippetShortcut('');
        setShowCreateSnippet(false);
        toast.success('Saved reply snippet created');
      } else {
        toast.error('Failed to create snippet');
      }
    } catch (err) {
      console.error('Failed to create snippet:', err);
      toast.error('Failed to create snippet');
    }
  };

  const handleDeleteSnippet = async (id) => {
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/snippets/${id}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setSnippetsList((prev) => prev.filter((s) => s.id !== id));
        toast.success('Snippet removed');
      } else {
        toast.error('Failed to delete snippet');
      }
    } catch (err) {
      console.error('Failed to delete snippet:', err);
      toast.error('Failed to delete snippet');
    }
  };

  const handleInsertSnippet = (snippet) => {
    setReplyText((prev) => (prev ? `${prev}\n${snippet.body}` : snippet.body));
    setSnippetsOpen(false);
  };

  const fetchTags = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch('/api/v1/outreach/inbox/tags/list', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setTagsList(data || []);
      }
    } catch (err) {
      console.error('Failed to load tags:', err);
    }
  };

  const handleToggleTag = async (tagName) => {
    if (!selectedThread) return;
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${selectedThread.id}/tags`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ tag_name: tagName }),
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedThread((prev) => ({ ...prev, tags: data.tags }));
        setThreads((prev) =>
          prev.map((t) => (t.id === selectedThread.id ? { ...t, tags: data.tags } : t))
        );
        toast.success('Tags updated');
      } else {
        toast.error('Failed to update tag');
      }
    } catch (err) {
      console.error('Failed to toggle tag:', err);
      toast.error('Failed to update tag');
    }
  };

  const handleCreateTag = async () => {
    if (!newTagName.trim()) return;
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch('/api/v1/outreach/inbox/tags', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: newTagName.trim(),
          color: newTagColor,
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setTagsList((prev) => [...prev, created]);
        setNewTagName('');
        setShowCreateTag(false);
        toast.success('Tag created');
      } else {
        toast.error('Failed to create tag');
      }
    } catch (err) {
      console.error('Failed to create tag:', err);
      toast.error('Failed to create tag');
    }
  };


  useEffect(() => {
    const timer = setTimeout(() => fetchThreads(), searchQuery ? 250 : 0);
    return () => { clearTimeout(timer); threadsRequestId.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccountId, filterSource, searchQuery]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedThread?.messages]);

  const handleSelectThread = async (thread) => {
    selectedThreadId.current = thread.id;
    setSelectedThread(thread);
    setAiSuggestions([]);
    setRemindersList([]);
    fetchReminders(thread.id);
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${thread.id}`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const full = await res.json();
        if (selectedThreadId.current !== thread.id) return;
        setSelectedThread(full);
        setThreads((prev) =>
          prev.map((t) => (t.id === thread.id ? { ...t, unread_count: 0 } : t))
        );
      }
    } catch (err) {
      console.error('Failed to fetch thread detail:', err);
      toast.error('Could not load conversation details');
    }
  };

  const handleSendReply = async () => {
    if (!replyText.trim() || !selectedThread || isSending) return;
    const thread = selectedThread;
    const body = replyText.trim();
    setIsSending(true);
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${selectedThread.id}/reply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ body }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.status !== 'queued' || !data.job_id) throw new Error('Reply was not queued');
        const job = await waitForInboxJob(data.job_id);
        if (selectedThreadId.current === thread.id) {
          setSelectedThread((prev) => prev && ({
            ...prev,
            last_message_snippet: body,
            messages: [...(prev.messages || []), job.result.message],
          }));
          setReplyText('');
        }
        await fetchThreads();
        toast.success('Reply dispatched');
      } else {
        const errData = await res.json().catch(() => ({}));
        toast.error(errData.detail || 'Failed to dispatch reply');
      }
    } catch (err) {
      console.error('Reply failed:', err);
      toast.error(err.message || 'Failed to dispatch reply');
    } finally {
      setIsSending(false);
    }
  };

  const handleLoadAiReplies = async () => {
    if (!selectedThread) return;
    const threadId = selectedThread.id;
    setLoadingAi(true);
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${threadId}/ai-reply`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        if (selectedThreadId.current === threadId) setAiSuggestions(data.suggestions || []);
      } else {
        toast.error('Failed to load AI suggestions');
      }
    } catch (err) {
      console.error('AI reply generation failed:', err);
      toast.error('Failed to load AI suggestions');
    } finally {
      setLoadingAi(false);
    }
  };

  const handleSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    try {
      const token = localStorage.getItem('token');
      const url =
        selectedAccountId !== 'all'
          ? `/api/v1/outreach/inbox/sync?account_id=${selectedAccountId}`
          : '/api/v1/outreach/inbox/sync';
      const res = await inboxFetch(url, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status !== 'queued' || !data.job_id) throw new Error('Sync was not queued');
        const job = await waitForInboxJob(data.job_id);
        toast.success(`Inbox synchronized: ${job.result?.synced_threads ?? job.result?.total_threads_synced ?? 0} conversations`);
        await fetchThreads();
      } else {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Sync failed');
      }
    } catch (err) {
      console.error('Sync error:', err);
      toast.error(err.message || 'Sync error occurred');
    } finally {
      setIsSyncing(false);
    }
  };

  const handleUpdateIntent = async (newIntent) => {
    if (!selectedThread) return;
    try {
      const token = localStorage.getItem('token');
      const res = await inboxFetch(`/api/v1/outreach/inbox/${selectedThread.id}/intent`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ intent_tag: newIntent }),
      });
      if (res.ok) {
        setSelectedThread((prev) => ({ ...prev, intent_tag: newIntent }));
        fetchThreads();
        toast.success('Lead status updated');
      } else {
        toast.error('Failed to update status');
      }
    } catch (err) {
      console.error('Intent update failed:', err);
      toast.error('Failed to update status');
    }
  };

  const selectedAccountObj = accounts.find((a) => a.id === selectedAccountId);

  return (
    <div className="h-full max-h-full min-h-0 flex bg-white overflow-hidden">
      {/* Left Column: Conversation List matching media_1790103710555.png */}
      <div className="w-[380px] border-r border-gray-200/90 flex flex-col shrink-0 bg-white">
        {/* Header with Title & Filter Switcher */}
        <div className="p-4 border-b border-gray-100 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Inbox</h1>
              <button
                type="button"
                onClick={handleSync}
                disabled={isSyncing}
                title="Sync conversations with LinkedIn"
                className="p-1.5 text-gray-400 hover:text-[#5145cd] hover:bg-gray-100 rounded-lg transition-colors cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-[#5145cd]' : ''}`} />
              </button>
            </div>
            {/* Pill Switcher: [ Unravler | All ] matching media_1790103710555.png */}
            <div className="inline-flex items-center bg-[#f4f4f5] p-1 rounded-xl gap-0.5 text-xs font-semibold text-gray-500">
              <button
                type="button"
                onClick={() => setFilterSource('outreach')}
                className={`px-3 py-1 rounded-lg transition-all ${
                  filterSource === 'outreach'
                    ? 'bg-white text-gray-900 shadow-2xs font-bold'
                    : 'text-gray-500 hover:text-gray-900'
                }`}
              >
                Unravler
              </button>
              <button
                type="button"
                onClick={() => setFilterSource('all')}
                className={`px-3 py-1 rounded-lg transition-all ${
                  filterSource === 'all'
                    ? 'bg-white text-gray-900 shadow-2xs font-bold'
                    : 'text-gray-500 hover:text-gray-900'
                }`}
              >
                All
              </button>
            </div>
          </div>

          {/* Search Conversations Input matching media_1790103710555.png */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3.5 top-3" />
            <input
              type="text"
              placeholder="Search conversations"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3.5 py-2 text-xs bg-[#f4f4f5] border border-transparent rounded-xl placeholder:text-gray-400 text-gray-900 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 focus:bg-white focus:border-gray-200 transition-all shadow-2xs"
            />
          </div>

          {/* Accounts Selector Dropdown Button matching media_1790103710555.png */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsAccountDropdownOpen(!isAccountDropdownOpen)}
              className="w-full flex items-center justify-between px-3.5 py-2 text-xs font-medium text-gray-800 bg-white border border-gray-200 rounded-xl hover:bg-gray-50/80 transition-colors shadow-2xs cursor-pointer"
            >
              <div className="flex items-center gap-2.5 truncate">
                <Mail className="w-3.5 h-3.5 text-[#5145cd]" />
                <span className="font-semibold text-xs text-gray-800 truncate">
                  {selectedAccountId === 'all'
                    ? 'All accounts'
                    : selectedAccountObj?.account_name || 'Selected account'}
                </span>
              </div>
              {isAccountDropdownOpen ? (
                <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
              )}
            </button>

            {/* Dropdown Card matching media_1790103710555.png */}
            {isAccountDropdownOpen && (
              <div className="mt-2 p-2 bg-white border border-gray-200 rounded-2xl shadow-xl space-y-1.5 text-left z-30 transition-all">
                {/* Option: All accounts */}
                <button
                  type="button"
                  onClick={() => {
                    setSelectedAccountId('all');
                    setIsAccountDropdownOpen(false);
                  }}
                  className={`w-full p-3 rounded-xl border text-left transition-all cursor-pointer ${
                    selectedAccountId === 'all'
                      ? 'border-indigo-100 bg-[#f5f6ff]'
                      : 'border-gray-100 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Mail className="w-3.5 h-3.5 text-[#5145cd]" />
                      <span className="text-xs font-bold text-[#5145cd]">All accounts</span>
                    </div>
                    {selectedAccountId === 'all' && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#5145cd]" />
                    )}
                  </div>
                  {accounts.length === 0 && (
                    <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">
                      No connected accounts. Connect one in Settings to see conversations.
                    </p>
                  )}
                </button>

                {/* Individual Accounts if connected */}
                {accounts.map((acc) => (
                  <button
                    key={acc.id}
                    type="button"
                    onClick={() => {
                      setSelectedAccountId(acc.id);
                      setIsAccountDropdownOpen(false);
                    }}
                    className={`w-full p-2.5 rounded-xl border text-left transition-all cursor-pointer flex items-center justify-between ${
                      selectedAccountId === acc.id
                        ? 'border-indigo-100 bg-[#f5f6ff]'
                        : 'border-gray-100 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      {acc.avatar_url ? (
                        <img
                          src={acc.avatar_url}
                          alt=""
                          className="w-5 h-5 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-5 h-5 rounded-full bg-indigo-100 text-[#5145cd] flex items-center justify-center font-bold text-[9px]">
                          {(acc.account_name || 'U').charAt(0).toUpperCase()}
                        </div>
                      )}
                      <span className="text-xs font-semibold text-gray-800 truncate">
                        {acc.account_name}
                      </span>
                    </div>
                    {selectedAccountId === acc.id && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#5145cd]" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Conversation List / Centered Empty State matching media_1790103710555.png */}
        <div className="flex-1 overflow-y-auto divide-y divide-gray-100 flex flex-col justify-start">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <RefreshCw className="h-5 w-5 animate-spin" />
            </div>
          ) : loadError ? (
            <div className="my-auto px-4 py-12 text-center text-xs text-red-700">
              <p>{loadError}</p>
              <button type="button" onClick={() => fetchThreads()} className="mt-3 rounded-lg border border-red-200 px-3 py-1.5 font-semibold">Retry</button>
            </div>
          ) : threads.length === 0 ? (
            <div className="my-auto py-24 text-center px-4 space-y-3">
              <p className="text-xs text-gray-400 font-normal">No conversations yet.</p>
              <div className="flex flex-col items-center gap-2 pt-1">
                {accounts.length > 0 && (
                  <button
                    type="button"
                    onClick={handleSync}
                    disabled={isSyncing}
                    className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 font-medium hover:underline cursor-pointer"
                  >
                    <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin' : ''}`} />
                    Check for new messages
                  </button>
                )}
              </div>
            </div>
          ) : (
            threads.map((t) => {
              const isSelected = selectedThread?.id === t.id;
              return (
                <div
                  key={t.id}
                  onClick={() => handleSelectThread(t)}
                  className={`p-4 cursor-pointer transition-colors ${
                    isSelected ? 'bg-indigo-50/70 border-r-2 border-[#5145cd]' : 'hover:bg-gray-50/80'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`text-xs font-bold truncate ${
                        isSelected ? 'text-[#5145cd]' : 'text-gray-900'
                      }`}
                    >
                      {t.lead_name}
                    </span>
                    <span className="text-[10px] text-gray-400 shrink-0 font-mono">
                      {t.last_message_at
                        ? new Date(t.last_message_at).toLocaleDateString([], {
                            month: 'short',
                            day: 'numeric',
                          })
                        : ''}
                    </span>
                  </div>

                  <p className="text-xs text-gray-500 truncate mb-2">
                    {t.last_message_snippet || 'No message snippet'}
                  </p>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {t.intent_tag && (
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize ${
                            t.intent_tag === 'interested'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : t.intent_tag === 'not_interested'
                              ? 'bg-rose-50 text-rose-700 border border-rose-200'
                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                          }`}
                        >
                          {t.intent_tag.replace('_', ' ')}
                        </span>
                      )}
                      {t.campaign_name && (
                        <span className="text-[10px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full font-medium truncate max-w-[120px]">
                          {t.campaign_name}
                        </span>
                      )}
                    </div>
                    {t.unread_count > 0 && (
                      <span className="w-2 h-2 rounded-full bg-[#5145cd] inline-block" />
                    )}
                  </div>
                </div>
              );
            })
          )}
          {hasMoreThreads && !loading && (
            <button
              type="button"
              onClick={() => fetchThreads(threads.length)}
              disabled={loadingMore}
              className="w-full px-4 py-3 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
            >
              {loadingMore ? 'Loading…' : 'Load more conversations'}
            </button>
          )}
        </div>
      </div>

      {/* Right Column: Conversation View or Empty State matching media_1790103710555.png */}
      <div className="flex-1 flex flex-col bg-white overflow-hidden">
        {selectedThread ? (
          <>
            {/* Conversation Header */}
            <div className="h-16 px-6 border-b border-gray-200 flex items-center justify-between bg-white shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-indigo-50 text-[#5145cd] flex items-center justify-center font-bold text-sm">
                  {(selectedThread.lead_name || 'U').charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-gray-900 leading-tight">
                      {selectedThread.lead_name}
                    </h3>
                    <a
                      href={selectedThread.lead_profile_url?.startsWith('https://www.linkedin.com/in/') || selectedThread.lead_profile_url?.startsWith('https://linkedin.com/in/')
                        ? selectedThread.lead_profile_url
                        : `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(selectedThread.lead_name)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-400 hover:text-indigo-600 transition-colors"
                      title="View on LinkedIn"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <p className="text-[11px] text-gray-400">
                      {selectedThread.lead_headline || selectedThread.lead_title || 'LinkedIn Prospect'}
                    </p>
                    {/* Active Lead Tags */}
                    {(selectedThread.tags || []).map((tName) => {
                      const tagDef = tagsList.find((t) => t.name === tName);
                      return (
                        <span
                          key={tName}
                          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded-full text-[9px] font-bold border shadow-2xs"
                          style={{
                            backgroundColor: `${tagDef?.color || '#6366f1'}15`,
                            borderColor: `${tagDef?.color || '#6366f1'}40`,
                            color: tagDef?.color || '#6366f1',
                          }}
                        >
                          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: tagDef?.color || '#6366f1' }} />
                          {tName}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Action Tools & Status matching Unravler (unravler_inbox_reminders.jpg) */}
              <div className="flex items-center gap-2">
                {/* Reminders Button [S] */}
                <button
                  type="button"
                  onClick={() => setRemindersOpen(!remindersOpen)}
                  className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border text-xs font-semibold transition-all shadow-2xs ${
                    selectedThread.remind_at
                      ? 'bg-amber-50 text-amber-700 border-amber-300'
                      : 'bg-white hover:bg-gray-50 text-gray-700 border-gray-200'
                  }`}
                  title="Schedule Follow-up Reminder (Press S)"
                >
                  <Clock className={`w-3.5 h-3.5 ${selectedThread.remind_at ? 'text-amber-600' : 'text-gray-400'}`} />
                  <span>Reminders</span>
                  <kbd className="text-[9px] px-1 bg-gray-100 rounded text-gray-500 font-mono">S</kbd>
                </button>

                {/* Snippets Button [C] */}
                <button
                  type="button"
                  onClick={() => setSnippetsOpen(!snippetsOpen)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold transition-all shadow-2xs"
                  title="Saved Reply Snippets (Press C)"
                >
                  <Bookmark className="w-3.5 h-3.5 text-gray-400" />
                  <span>Snippets</span>
                  <kbd className="text-[9px] px-1 bg-gray-100 rounded text-gray-500 font-mono">C</kbd>
                </button>

                {/* Tags Button [T] */}
                <button
                  type="button"
                  onClick={() => setTagsOpen(!tagsOpen)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold transition-all shadow-2xs"
                  title="Assign Tags (Press T)"
                >
                  <Tag className="w-3.5 h-3.5 text-gray-400" />
                  <span>Tags</span>
                  <kbd className="text-[9px] px-1 bg-gray-100 rounded text-gray-500 font-mono">T</kbd>
                </button>

                {/* Status / Intent Selector */}
                <select
                  value={selectedThread.intent_tag || ''}
                  onChange={(e) => handleUpdateIntent(e.target.value)}
                  className="text-xs border border-gray-200 rounded-xl px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white shadow-2xs font-semibold"
                >
                  <option value="">No status tag</option>
                  <option value="interested">Interested</option>
                  <option value="objection">Question / Objection</option>
                  <option value="not_interested">Not Interested</option>
                </select>
              </div>
            </div>

            {/* Reminder Alert Banner */}
            {selectedThread.remind_at && (
              <div className="px-6 py-2 bg-amber-50/80 border-b border-amber-200/60 flex items-center justify-between text-xs text-amber-900 shrink-0">
                <div className="flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  <span>
                    Reminder: <strong>{new Date(selectedThread.remind_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</strong>
                    {selectedThread.reminder_note && ` — "${selectedThread.reminder_note}"`}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteReminder(remindersList.find((rem) => rem.remind_at === selectedThread.remind_at)?.id || remindersList[0]?.id)}
                  disabled={!remindersList.length}
                  className="text-amber-700 hover:text-amber-900 text-[11px] font-semibold underline"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Messages Scroll Area */}
            <div className="flex-1 p-6 overflow-y-auto space-y-4 bg-gray-50/40">
              {(selectedThread.messages || []).map((msg, idx) => {
                const isUser = msg.sender_type === 'user';
                return (
                  <div
                    key={msg.id || idx}
                    className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    <div className="flex items-center gap-1.5 mb-1 px-1">
                      <span className="text-[10px] font-semibold text-gray-500">
                        {isUser ? 'You' : selectedThread.lead_name}
                      </span>
                      <span className="text-[10px] text-gray-400 font-mono">
                        {new Date(msg.timestamp).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>

                    <div
                      className={`max-w-md rounded-2xl px-4 py-2.5 text-xs leading-relaxed shadow-2xs ${
                        isUser
                          ? 'bg-[#5145cd] text-white rounded-br-xs'
                          : 'bg-white border border-gray-200/80 text-gray-800 rounded-bl-xs'
                      }`}
                    >
                      {msg.is_voice_note && (
                        msg.audio_url?.startsWith('https://') ? (
                          <audio controls preload="none" src={msg.audio_url} className="mb-2 max-w-full" aria-label="Voice note" />
                        ) : <p className="mb-2 text-[10px]">Voice note audio unavailable</p>
                      )}
                      <p className="whitespace-pre-wrap">{msg.body}</p>
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Smart Suggestions & Composer */}
            <div className="p-4 border-t border-gray-200 bg-white space-y-2">
              {/* AI Quick Reply Triggers */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1">
                <button
                  type="button"
                  onClick={handleLoadAiReplies}
                  disabled={loadingAi}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 text-[#5145cd] text-[11px] font-semibold hover:bg-indigo-100 transition-colors shrink-0 shadow-2xs"
                >
                  <Sparkles className={`w-3 h-3 ${loadingAi ? 'animate-spin' : ''}`} />
                  AI suggestions
                </button>
                <button
                  type="button"
                  onClick={() => setSnippetsOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-[11px] font-semibold transition-colors shrink-0 shadow-2xs"
                >
                  <Bookmark className="w-3 h-3 text-gray-500" />
                  Snippets (C)
                </button>
                {aiSuggestions.map((sug, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setReplyText(sug)}
                    className="px-3 py-1 rounded-full bg-gray-100 hover:bg-gray-200/80 text-gray-700 text-[11px] font-medium truncate max-w-xs transition-colors shrink-0"
                  >
                    "{sug.slice(0, 45)}..."
                  </button>
                ))}
              </div>

              {/* Textarea Composer */}
              <div className="flex items-end gap-2 bg-[#f8f9fa] border border-gray-200 rounded-2xl p-2.5 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-[#5145cd] focus-within:bg-white transition-all shadow-2xs">
                <textarea
                  rows={2}
                  placeholder={`Reply to ${selectedThread.lead_name}...`}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendReply();
                    }
                  }}
                  className="flex-1 bg-transparent border-0 resize-none text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none p-1"
                />
                <button
                  onClick={handleSendReply}
                  disabled={isSending || !replyText.trim()}
                  className="p-2.5 bg-[#5145cd] hover:bg-[#4338ca] text-white rounded-xl disabled:opacity-40 transition-colors shrink-0 shadow-2xs"
                  title="Send message"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </>
        ) : (
          /* Empty State exactly matching media_1790103710555.png */
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-neutral-50/20">
            {/* Lavender Squircle Icon Box */}
            <div className="w-12 h-12 rounded-2xl bg-[#f5f6ff] border border-indigo-100/70 text-[#5145cd] flex items-center justify-center mb-3 shadow-2xs">
              <Mail className="w-5 h-5 stroke-[1.75]" />
            </div>
            <h3 className="font-bold text-gray-900 text-base">Select a conversation</h3>
            <p className="text-xs text-gray-400 max-w-sm mt-1 leading-normal">
              Choose a thread from the list to read the conversation and reply.
            </p>
          </div>
        )}
      </div>

      {/* ── REMINDERS MODAL (unravler_inbox_reminders.jpg) ──────────────────── */}
      {remindersOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        >
          <div className="relative w-full max-w-md rounded-2xl bg-white shadow-2xl border border-gray-100 p-5 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-amber-50 text-amber-600">
                  <Clock className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 text-sm">Schedule Follow-up</h3>
                  <p className="text-[11px] text-gray-400">Set a reminder for {selectedThread?.lead_name}</p>
                </div>
              </div>
              <button
                onClick={() => setRemindersOpen(false)}
                className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Quick Timing Pills */}
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                Quick Options
              </label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => handleSetReminder(1)}
                  className="py-2 px-2.5 rounded-xl border border-gray-200 hover:border-amber-500 hover:bg-amber-50/20 text-xs font-semibold text-gray-700 text-center transition-all shadow-2xs"
                >
                  Tomorrow
                </button>
                <button
                  type="button"
                  onClick={() => handleSetReminder(3)}
                  className="py-2 px-2.5 rounded-xl border border-gray-200 hover:border-amber-500 hover:bg-amber-50/20 text-xs font-semibold text-gray-700 text-center transition-all shadow-2xs"
                >
                  In 3 Days
                </button>
                <button
                  type="button"
                  onClick={() => handleSetReminder(7)}
                  className="py-2 px-2.5 rounded-xl border border-gray-200 hover:border-amber-500 hover:bg-amber-50/20 text-xs font-semibold text-gray-700 text-center transition-all shadow-2xs"
                >
                  In 1 Week
                </button>
              </div>
            </div>

            {/* Custom Datetime & Note */}
            <div className="space-y-3 pt-1">
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1">
                  Or Pick Custom Date & Time
                </label>
                <input
                  type="datetime-local"
                  value={reminderDate}
                  onChange={(e) => setReminderDate(e.target.value)}
                  className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 text-gray-700 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1">
                  Reminder Note (Optional)
                </label>
                <input
                  type="text"
                  value={reminderNote}
                  onChange={(e) => setReminderNote(e.target.value)}
                  placeholder="e.g. Send enterprise pricing sheet"
                  className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 text-gray-700 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
              </div>
            </div>

            {/* Existing Reminders */}
            {remindersList.length > 0 && (
              <div className="pt-2 border-t border-gray-100 space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Active Reminders
                </span>
                {remindersList.map((rem) => (
                  <div
                    key={rem.id}
                    className="flex items-center justify-between p-2 rounded-lg bg-amber-50/50 border border-amber-200/50 text-xs"
                  >
                    <div>
                      <p className="font-semibold text-amber-900">{rem.note || 'Follow up'}</p>
                      <span className="text-[10px] text-amber-700 font-mono">
                        {new Date(rem.remind_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteReminder(rem.id)}
                      className="p-1 text-amber-600 hover:text-amber-800"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="pt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRemindersOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-gray-500 hover:text-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleSetReminder()}
                className="px-5 py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-xl shadow-xs transition-colors"
              >
                Set Reminder
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── SNIPPETS DRAWER (unravler_inbox_snippets.jpg) ────────────────────── */}
      {snippetsOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-[420px] max-w-[95vw] h-full max-h-full bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col overflow-hidden animate-slide-left"
        >
          <div className="flex items-center justify-between p-4 border-b border-gray-100 shrink-0">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-indigo-50 text-[#5145cd]">
                <Bookmark className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-gray-900 text-sm">Saved Reply Snippets</h3>
                <p className="text-[11px] text-gray-400">Insert high-converting responses with 1-click</p>
              </div>
            </div>
            <button
              onClick={() => setSnippetsOpen(false)}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Search & Actions */}
          <div className="p-4 border-b border-gray-100 space-y-3 shrink-0 bg-gray-50/50">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                value={snippetSearch}
                onChange={(e) => setSnippetSearch(e.target.value)}
                placeholder="Search snippets (e.g. cal, pricing)..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-gray-200 focus:border-[#5145cd] focus:ring-1 focus:ring-[#5145cd] bg-white"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                {snippetsList.length} Snippets
              </span>
              <button
                type="button"
                onClick={() => setShowCreateSnippet(!showCreateSnippet)}
                className="text-xs font-semibold text-[#5145cd] hover:underline"
              >
                {showCreateSnippet ? '– Cancel' : '+ New Saved Reply'}
              </button>
            </div>

            {showCreateSnippet && (
              <div className="p-3 bg-white rounded-xl border border-indigo-200 space-y-2.5 shadow-2xs">
                <div>
                  <label className="text-[10px] font-bold text-gray-700 block mb-0.5">Snippet Title</label>
                  <input
                    type="text"
                    value={newSnippetTitle}
                    onChange={(e) => setNewSnippetTitle(e.target.value)}
                    placeholder="e.g. Calendly Link"
                    className="w-full text-xs rounded-lg border border-gray-200 px-2.5 py-1 focus:border-[#5145cd]"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-700 block mb-0.5">Quick Shortcut (Optional)</label>
                  <input
                    type="text"
                    value={newSnippetShortcut}
                    onChange={(e) => setNewSnippetShortcut(e.target.value)}
                    placeholder="e.g. cal"
                    className="w-full text-xs rounded-lg border border-gray-200 px-2.5 py-1 focus:border-[#5145cd]"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-700 block mb-0.5">Message Body</label>
                  <textarea
                    rows={3}
                    value={newSnippetBody}
                    onChange={(e) => setNewSnippetBody(e.target.value)}
                    placeholder="Write the response template..."
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 focus:border-[#5145cd] resize-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleCreateSnippet}
                  disabled={!newSnippetTitle.trim() || !newSnippetBody.trim()}
                  className="w-full py-1.5 bg-[#5145cd] hover:bg-[#4338ca] text-white font-bold text-xs rounded-lg shadow-2xs disabled:opacity-50"
                >
                  Save Snippet
                </button>
              </div>
            )}
          </div>

          {/* Snippets List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
            {snippetsList
              .filter(
                (s) =>
                  !snippetSearch ||
                  s.title.toLowerCase().includes(snippetSearch.toLowerCase()) ||
                  s.body.toLowerCase().includes(snippetSearch.toLowerCase()) ||
                  (s.shortcut && s.shortcut.toLowerCase().includes(snippetSearch.toLowerCase()))
              )
              .map((snip) => (
                <div
                  key={snip.id}
                  className="p-3.5 rounded-xl border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/20 bg-white transition-all space-y-2 text-left"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-xs text-gray-900">{snip.title}</span>
                      {snip.shortcut && (
                        <span className="text-[10px] font-mono bg-gray-100 text-gray-600 px-1.5 py-0.2 rounded">
                          /{snip.shortcut}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteSnippet(snip.id)}
                      className="p-1 text-gray-300 hover:text-rose-600 rounded transition-colors"
                      title="Delete snippet"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>

                  <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed bg-gray-50/70 p-2 rounded-lg font-sans">
                    {snip.body}
                  </p>

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      onClick={() => handleInsertSnippet(snip)}
                      className="inline-flex items-center gap-1 px-3 py-1 bg-[#5145cd] hover:bg-[#4338ca] text-white font-bold text-xs rounded-lg shadow-2xs transition-colors"
                    >
                      Insert into Reply
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* ── TAGS POPOVER (unravler_inbox_tags.jpg) ──────────────────────────── */}
      {tagsOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        >
          <div className="relative w-full max-w-sm rounded-2xl bg-white shadow-2xl border border-gray-100 p-5 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-blue-50 text-blue-600">
                  <Tag className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 text-sm">Thread Tags</h3>
                  <p className="text-[11px] text-gray-400">Classify lead stage & interest</p>
                </div>
              </div>
              <button
                onClick={() => setTagsOpen(false)}
                className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Tag Items */}
            <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
              {tagsList.map((tag) => {
                const isChecked = (selectedThread?.tags || []).includes(tag.name);
                return (
                  <label
                    key={tag.id || tag.name}
                    className="flex items-center justify-between p-2 rounded-xl hover:bg-gray-50 cursor-pointer border border-transparent hover:border-gray-200 transition-all"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="w-3 h-3 rounded-full shrink-0 shadow-2xs" style={{ backgroundColor: tag.color }} />
                      <span className="text-xs font-semibold text-gray-800">{tag.name}</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => handleToggleTag(tag.name)}
                      className="rounded border-gray-300 text-[#5145cd] focus:ring-[#5145cd]"
                    />
                  </label>
                );
              })}
            </div>

            {/* Create Tag Toggle */}
            <div className="pt-2 border-t border-gray-100">
              {showCreateTag ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={newTagColor}
                      onChange={(e) => setNewTagColor(e.target.value)}
                      className="w-7 h-7 rounded border-0 cursor-pointer p-0 shrink-0"
                    />
                    <input
                      type="text"
                      value={newTagName}
                      onChange={(e) => setNewTagName(e.target.value)}
                      placeholder="Tag label..."
                      className="flex-1 text-xs rounded-lg border border-gray-200 px-2.5 py-1 focus:border-[#5145cd]"
                    />
                  </div>
                  <div className="flex justify-end gap-1.5">
                    <button
                      type="button"
                      onClick={() => setShowCreateTag(false)}
                      className="px-2.5 py-1 text-xs text-gray-500 hover:text-gray-800"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleCreateTag}
                      disabled={!newTagName.trim()}
                      className="px-3 py-1 bg-[#5145cd] text-white text-xs font-bold rounded-lg shadow-2xs disabled:opacity-50"
                    >
                      Save Tag
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowCreateTag(true)}
                  className="text-xs font-semibold text-[#5145cd] hover:underline flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> Create New Tag
                </button>
              )}
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setTagsOpen(false)}
                className="px-5 py-2 bg-gray-900 hover:bg-black text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
