import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  ChevronDown,
  ChevronUp,
  Mail,
  Send,
  RefreshCw,
  User,
  Sparkles,
  CheckCircle2,
  Tag,
  Volume2,
} from 'lucide-react';

export default function OutreachInbox() {
  const [threads, setThreads] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [selectedThread, setSelectedThread] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filterMode, setFilterMode] = useState('all'); // 'all' | 'outreach'

  const messagesEndRef = useRef(null);

  const fetchAccounts = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data || []);
      }
    } catch (err) {
      console.error('Failed to load accounts:', err);
    }
  };

  const fetchThreads = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `/api/v1/outreach/inbox?account_id=${selectedAccountId}`;
      if (searchQuery.trim()) {
        url += `&search=${encodeURIComponent(searchQuery.trim())}`;
      }
      const res = await fetch(url, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setThreads(data || []);
        if (selectedThread) {
          const updated = data.find((t) => t.id === selectedThread.id);
          if (updated) setSelectedThread(updated);
        }
      }
    } catch (err) {
      console.error('Failed to load threads:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccountId, searchQuery]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedThread?.messages]);

  const handleSelectThread = async (thread) => {
    setSelectedThread(thread);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/inbox/${thread.id}`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const full = await res.json();
        setSelectedThread(full);
        setThreads((prev) =>
          prev.map((t) => (t.id === thread.id ? { ...t, unread_count: 0 } : t))
        );
      }
    } catch (err) {
      console.error('Failed to fetch thread detail:', err);
    }
  };

  const handleSendReply = async () => {
    if (!replyText.trim() || !selectedThread) return;
    setIsSending(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/inbox/${selectedThread.id}/reply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ body: replyText.trim() }),
      });

      if (res.ok) {
        const data = await res.json();
        setSelectedThread((prev) => ({
          ...prev,
          last_message_snippet: replyText.trim(),
          messages: [...(prev.messages || []), data.message],
        }));
        setReplyText('');
        fetchThreads();
      }
    } catch (err) {
      console.error('Reply failed:', err);
    } finally {
      setIsSending(false);
    }
  };

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      const token = localStorage.getItem('token');
      const url =
        selectedAccountId !== 'all'
          ? `/api/v1/outreach/inbox/sync?account_id=${selectedAccountId}`
          : '/api/v1/outreach/inbox/sync';
      await fetch(url, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      await fetchThreads();
    } catch (err) {
      console.error('Sync error:', err);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleUpdateIntent = async (newIntent) => {
    if (!selectedThread) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/inbox/${selectedThread.id}/intent`, {
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
      }
    } catch (err) {
      console.error('Intent update failed:', err);
    }
  };

  const selectedAccountObj = accounts.find((a) => a.id === selectedAccountId);

  return (
    <div className="h-full max-h-full min-h-0 flex bg-white overflow-hidden">
      {/* Left Panel: Conversation Thread List matching media_1790103710555.png */}
      <div className="w-80 md:w-96 border-r border-gray-200/90 flex flex-col shrink-0 bg-white">
        {/* Header with Title & Filter Pill */}
        <div className="p-4 border-b border-gray-100 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">Inbox</h1>
            <div className="flex items-center gap-1 bg-gray-100/80 p-0.5 rounded-lg text-xs font-semibold text-gray-500">
              <button
                type="button"
                onClick={() => setFilterMode('outreach')}
                className={`px-3 py-1 rounded-md transition-all ${
                  filterMode === 'outreach' ? 'bg-white shadow-2xs text-gray-900 font-bold' : 'hover:text-gray-900'
                }`}
              >
                Prosp
              </button>
              <button
                type="button"
                onClick={() => setFilterMode('all')}
                className={`px-3 py-1 rounded-md transition-all ${
                  filterMode === 'all' ? 'bg-white shadow-2xs text-gray-900 font-bold' : 'hover:text-gray-900'
                }`}
              >
                All
              </button>
            </div>
          </div>

          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3.5 top-3" />
            <input
              type="text"
              placeholder="Search conversations"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3.5 py-2 text-xs bg-gray-100/70 border-0 rounded-xl placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-indigo-500/30 focus:bg-white transition-all"
            />
          </div>

          {/* Account Selector Accordion / Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsAccountDropdownOpen(!isAccountDropdownOpen)}
              className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-gray-800 bg-white border border-gray-200 rounded-xl hover:bg-gray-50/80 transition-colors shadow-2xs"
            >
              <div className="flex items-center gap-2 truncate">
                <Mail className="w-3.5 h-3.5 text-indigo-600" />
                <span className="font-semibold text-xs text-gray-800 truncate">
                  {selectedAccountId === 'all'
                    ? 'All accounts'
                    : selectedAccountObj?.name || 'Selected Account'}
                </span>
              </div>
              {isAccountDropdownOpen ? (
                <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
              )}
            </button>

            {isAccountDropdownOpen && (
              <div className="mt-2 p-3 bg-white border border-gray-200 rounded-xl shadow-lg space-y-2 text-left z-20">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedAccountId('all');
                    setIsAccountDropdownOpen(false);
                  }}
                  className="w-full p-2.5 rounded-lg border border-indigo-200 bg-indigo-50/50 text-left transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Mail className="w-3.5 h-3.5 text-indigo-600" />
                      <span className="text-xs font-bold text-indigo-900">All accounts</span>
                    </div>
                    {selectedAccountId === 'all' && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600" />}
                  </div>
                  {accounts.length === 0 && (
                    <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">
                      No connected accounts. Connect one in Settings to see conversations.
                    </p>
                  )}
                </button>

                {accounts.map((acc) => (
                  <button
                    key={acc.id}
                    type="button"
                    onClick={() => {
                      setSelectedAccountId(acc.id);
                      setIsAccountDropdownOpen(false);
                    }}
                    className={`w-full p-2.5 rounded-lg border text-left transition-all ${
                      selectedAccountId === acc.id
                        ? 'border-indigo-200 bg-indigo-50/50'
                        : 'border-gray-100 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-gray-800 truncate">{acc.name}</span>
                      {selectedAccountId === acc.id && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600" />}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Thread List / Empty State */}
        <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
          {loading ? (
            <div className="py-12 text-center text-xs text-gray-400">Loading inbox...</div>
          ) : threads.length === 0 ? (
            <div className="py-16 px-4 text-center">
              <p className="text-xs text-gray-400 font-medium">No conversations yet.</p>
              <button
                onClick={handleSync}
                disabled={isSyncing}
                className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-indigo-600 font-medium hover:bg-indigo-50 rounded-lg transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
                Sync with LinkedIn
              </button>
            </div>
          ) : (
            threads.map((t) => {
              const isSelected = selectedThread?.id === t.id;
              return (
                <div
                  key={t.id}
                  onClick={() => handleSelectThread(t)}
                  className={`p-3.5 cursor-pointer transition-colors ${
                    isSelected ? 'bg-indigo-50/80 border-r-2 border-indigo-600' : 'hover:bg-gray-50/80'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`text-xs font-semibold truncate ${
                        isSelected ? 'text-indigo-900' : 'text-gray-900'
                      }`}
                    >
                      {t.lead_name}
                    </span>
                    <span className="text-[10px] text-gray-400 shrink-0">
                      {new Date(t.last_message_at).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </div>

                  <p className="text-xs text-gray-500 truncate mb-1.5">
                    {t.last_message_snippet || 'No message snippet'}
                  </p>

                  <div className="flex items-center gap-1.5">
                    {t.unread_count > 0 && (
                      <span className="w-2 h-2 rounded-full bg-indigo-600 inline-block" />
                    )}
                    {t.intent_tag && (
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          t.intent_tag === 'interested'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : t.intent_tag === 'not_interested'
                            ? 'bg-rose-50 text-rose-700 border border-rose-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {t.intent_tag}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right Panel: Conversation View or Empty State matching Part 3 Image 1 */}
      <div className="flex-1 flex flex-col bg-white">
        {selectedThread ? (
          <>
            {/* Thread Header */}
            <div className="h-16 px-6 border-b border-gray-200 flex items-center justify-between bg-white shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs">
                  {selectedThread.lead_name.charAt(0)}
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900 leading-tight">
                    {selectedThread.lead_name}
                  </h3>
                  <p className="text-xs text-gray-400">
                    {selectedThread.lead_headline || 'LinkedIn Prospect'}
                  </p>
                </div>
              </div>

              {/* Intent Tag Dropdown */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Intent:</span>
                <select
                  value={selectedThread.intent_tag || ''}
                  onChange={(e) => handleUpdateIntent(e.target.value)}
                  className="text-xs border border-gray-200 rounded-lg px-2.5 py-1 text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">None</option>
                  <option value="interested">Interested</option>
                  <option value="objection">Question / Objection</option>
                  <option value="not_interested">Not Interested</option>
                </select>
              </div>
            </div>

            {/* Messages Scroll Area */}
            <div className="flex-1 p-6 overflow-y-auto space-y-4 bg-stone-50/40">
              {(selectedThread.messages || []).map((msg, idx) => {
                const isUser = msg.sender_type === 'user';
                return (
                  <div
                    key={msg.id || idx}
                    className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    <div className="flex items-center gap-1.5 mb-1 px-1">
                      <span className="text-[11px] font-medium text-gray-600">
                        {isUser ? 'You' : selectedThread.lead_name}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {new Date(msg.timestamp).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </div>

                    <div
                      className={`max-w-md rounded-2xl px-4 py-2.5 text-xs leading-relaxed shadow-xs ${
                        isUser
                          ? 'bg-indigo-600 text-white rounded-br-xs'
                          : 'bg-white border border-gray-200/80 text-gray-800 rounded-bl-xs'
                      }`}
                    >
                      {msg.is_voice_note && (
                        <div className="flex items-center gap-2 mb-1.5 text-indigo-200 text-xs font-semibold">
                          <Volume2 className="w-3.5 h-3.5" />
                          <span>Voice Note</span>
                        </div>
                      )}
                      <p className="whitespace-pre-wrap">{msg.body}</p>
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Bottom Composer */}
            <div className="p-4 border-t border-gray-200 bg-white">
              <div className="flex items-end gap-2 bg-gray-50 border border-gray-200 rounded-xl p-2 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-600 focus-within:bg-white">
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
                  className="flex-1 bg-transparent border-0 resize-none text-xs text-gray-800 focus:outline-none p-1"
                />
                <button
                  onClick={handleSendReply}
                  disabled={isSending || !replyText.trim()}
                  className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 transition-colors shrink-0"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        ) : (
          /* Empty State exactly matching media_1790103710555.png */
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-neutral-50/10">
            <div className="w-14 h-14 rounded-full bg-indigo-50/80 border border-indigo-100/60 text-indigo-500 flex items-center justify-center mb-4 shadow-2xs">
              <Mail className="w-6 h-6 stroke-[1.75]" />
            </div>
            <h3 className="font-bold text-gray-900 text-base">Select a conversation</h3>
            <p className="text-xs text-gray-400 max-w-sm mt-1">
              Choose a thread from the list to read the conversation and reply.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
