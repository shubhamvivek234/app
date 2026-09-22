import React, { useState, useEffect, useRef } from 'react';
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
  Volume2,
  Play,
  Pause,
  User,
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
  const [filterSource, setFilterSource] = useState('all'); // 'all' | 'outreach'
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [loadingAi, setLoadingAi] = useState(false);
  const [playingVoiceId, setPlayingVoiceId] = useState(null);

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
      if (filterSource === 'outreach') {
        url += '&source=outreach';
      }
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
  }, [selectedAccountId, filterSource, searchQuery]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedThread?.messages]);

  const handleSelectThread = async (thread) => {
    setSelectedThread(thread);
    setAiSuggestions([]);
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

  const handleLoadAiReplies = async () => {
    if (!selectedThread) return;
    setLoadingAi(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/inbox/${selectedThread.id}/ai-reply`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setAiSuggestions(data.suggestions || []);
      }
    } catch (err) {
      console.error('AI reply generation failed:', err);
    } finally {
      setLoadingAi(false);
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
      {/* Left Column: Conversation List matching media_1790103710555.png */}
      <div className="w-[380px] border-r border-gray-200/90 flex flex-col shrink-0 bg-white">
        {/* Header with Title & Filter Switcher */}
        <div className="p-4 border-b border-gray-100 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Inbox</h1>
            {/* Pill Switcher: [ Prosp | All ] matching media_1790103710555.png */}
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
                Prosp
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
          ) : threads.length === 0 ? (
            <div className="my-auto py-24 text-center px-4">
              <p className="text-xs text-gray-400 font-normal">No conversations yet.</p>
              {accounts.length > 0 && (
                <button
                  onClick={handleSync}
                  disabled={isSyncing}
                  className="mt-2.5 inline-flex items-center gap-1.5 text-xs text-[#5145cd] font-semibold hover:underline"
                >
                  <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin' : ''}`} />
                  Check for new messages
                </button>
              )}
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
                      {new Date(t.last_message_at).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      })}
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
                  {selectedThread.lead_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-gray-900 leading-tight">
                      {selectedThread.lead_name}
                    </h3>
                    <a
                      href={`https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(
                        selectedThread.lead_name
                      )}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-400 hover:text-indigo-600 transition-colors"
                      title="View on LinkedIn"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    {selectedThread.lead_headline || selectedThread.lead_title || 'LinkedIn Prospect'}
                  </p>
                </div>
              </div>

              {/* Status / Intent Selector */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 font-medium">Status:</span>
                <select
                  value={selectedThread.intent_tag || ''}
                  onChange={(e) => handleUpdateIntent(e.target.value)}
                  className="text-xs border border-gray-200 rounded-xl px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white shadow-2xs font-semibold"
                >
                  <option value="">No tag</option>
                  <option value="interested">Interested</option>
                  <option value="objection">Question / Objection</option>
                  <option value="not_interested">Not Interested</option>
                </select>
              </div>
            </div>

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
                        <div className="flex items-center gap-2 mb-2 p-2 rounded-xl bg-indigo-500/20 text-white text-xs">
                          <button
                            type="button"
                            onClick={() =>
                              setPlayingVoiceId(playingVoiceId === msg.id ? null : msg.id)
                            }
                            className="p-1 rounded-full bg-white text-[#5145cd]"
                          >
                            {playingVoiceId === msg.id ? (
                              <Pause className="w-3 h-3" />
                            ) : (
                              <Play className="w-3 h-3" />
                            )}
                          </button>
                          <div className="flex-1 flex items-center gap-1">
                            <span className="text-[10px] font-semibold">Voice Note</span>
                            <div className="h-1 flex-1 bg-white/40 rounded-full mx-1" />
                            <span className="text-[10px] opacity-80">0:15</span>
                          </div>
                        </div>
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
    </div>
  );
}
