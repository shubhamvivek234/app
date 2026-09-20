import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaRobot,
  FaPlus,
  FaPaperPlane,
  FaScissors,
  FaCalendarDays,
  FaPenToSquare,
  FaTrash,
  FaSpinner,
  FaShieldHalved,
  FaWandMagicSparkles,
  FaImage,
  FaCircle,
  FaComments,
  FaYoutube,
} from 'react-icons/fa6';
import {
  SiX,
  SiLinkedin,
  SiFacebook,
  SiInstagram,
  SiYoutube,
  SiTiktok,
  SiThreads,
  SiBluesky,
} from 'react-icons/si';

import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import {
  getAgentSessions,
  createAgentSession,
  getAgentSession,
  deleteAgentSession,
  sendAgentMessage,
  getSocialAccounts,
} from '@/lib/api';
import VideoClipperModal from '@/components/clipping/VideoClipperModal';

const PLATFORM_ICONS = {
  twitter: SiX,
  linkedin: SiLinkedin,
  facebook: SiFacebook,
  instagram: SiInstagram,
  youtube: SiYoutube,
  tiktok: SiTiktok,
  threads: SiThreads,
  bluesky: SiBluesky,
};

const SUGGESTED_PROMPTS = [
  '🚀 Draft a launch announcement for our new feature across X and LinkedIn',
  '📅 Propose 3 high-converting post ideas for this week',
  '🔥 Turn this YouTube link into 3 viral vertical shorts: https://youtube.com/...',
  '🎨 Generate an editorial graphic banner for a blog post about AI productivity',
];

export default function AgentHub() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedChannels, setSelectedChannels] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [showClipper, setShowClipper] = useState(false);

  const messagesEndRef = useRef(null);

  useEffect(() => {
    initData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const initData = async () => {
    setLoadingSessions(true);
    try {
      const [sessRes, accRes] = await Promise.all([
        getAgentSessions(),
        getSocialAccounts(),
      ]);
      setSessions(sessRes || []);
      const accs = Array.isArray(accRes) ? accRes : [];
      setAccounts(accs);
      setSelectedChannels(accs.map((a) => a.id));

      if (sessRes && sessRes.length > 0) {
        selectSession(sessRes[0].id);
      } else {
        await handleNewSession();
      }
    } catch {
      toast.error('Failed to load AI Agent workspace');
    } finally {
      setLoadingSessions(false);
    }
  };

  const selectSession = async (sessionId) => {
    setCurrentSessionId(sessionId);
    setLoadingChat(true);
    try {
      const data = await getAgentSession(sessionId);
      setMessages(data.messages || []);
      if (data.session?.channel_ids && data.session.channel_ids.length > 0) {
        setSelectedChannels(data.session.channel_ids);
      }
    } catch {
      toast.error('Failed to load session messages');
    } finally {
      setLoadingChat(false);
    }
  };

  const handleNewSession = async () => {
    try {
      const newSess = await createAgentSession({
        title: 'New Strategy Thread',
        channel_ids: selectedChannels,
      });
      setSessions((prev) => [newSess, ...prev]);
      setCurrentSessionId(newSess.id);
      selectSession(newSess.id);
      toast.success('Started new AI Agent thread');
    } catch {
      toast.error('Failed to create new session');
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    try {
      await deleteAgentSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      toast.success('Session deleted');
      if (currentSessionId === sessionId) {
        if (remaining.length > 0) {
          selectSession(remaining[0].id);
        } else {
          handleNewSession();
        }
      }
    } catch {
      toast.error('Failed to delete session');
    }
  };

  const handleSendMessage = async (customPrompt) => {
    const text = customPrompt || inputText;
    if (!text.trim() || sending || !currentSessionId) return;

    const optimisticUserMsg = {
      id: `temp_${Date.now()}`,
      sender: 'user',
      text: text.trim(),
      cards: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticUserMsg]);
    setInputText('');
    setSending(true);

    try {
      const res = await sendAgentMessage(currentSessionId, {
        message: text.trim(),
        channel_ids: selectedChannels,
      });

      const assistantMsg = {
        id: `ast_${Date.now()}`,
        sender: 'assistant',
        text: res.reply,
        cards: res.cards || [],
        created_at: res.created_at || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Refresh sessions to get updated title & timestamp
      const updatedSess = await getAgentSessions();
      setSessions(updatedSess || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Agent response failed');
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleOpenInComposer = (card) => {
    const draftContent = card.payload?.content || '';
    const platforms = card.payload?.platforms || [];
    navigate('/composer', {
      state: {
        prefillContent: draftContent,
        prefillPlatforms: platforms,
      },
    });
  };

  return (
    <DashboardLayout>
      <VideoClipperModal
        open={showClipper}
        onClose={() => setShowClipper(false)}
        accounts={accounts}
      />

      <div className="flex h-[calc(100vh-6rem)] rounded-3xl border border-gray-200 bg-white overflow-hidden shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {/* ── LEFT PANE: Channel Guardrail ────────────────────────────────── */}
        <aside className="w-64 border-r border-gray-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 flex flex-col shrink-0 hidden md:flex">
          <div className="p-4 border-b border-gray-100 dark:border-slate-800 space-y-1">
            <div className="flex items-center gap-2">
              <FaShieldHalved className="text-indigo-600 text-sm" />
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Channel Guardrail
              </h2>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Only checked accounts can be acted upon or proposed by the Agent.
            </p>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
            <div className="flex items-center justify-between pb-2 px-1 text-[11px] text-slate-500 font-medium">
              <span>Connected Channels ({accounts.length})</span>
              <button
                type="button"
                onClick={() =>
                  setSelectedChannels(
                    selectedChannels.length === accounts.length
                      ? []
                      : accounts.map((a) => a.id)
                  )
                }
                className="text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                {selectedChannels.length === accounts.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            {accounts.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-400">
                No accounts connected.
              </div>
            ) : (
              accounts.map((acc) => {
                const checked = selectedChannels.includes(acc.id);
                const Icon = PLATFORM_ICONS[acc.platform?.toLowerCase()] || FaComments;
                return (
                  <div
                    key={acc.id}
                    onClick={() =>
                      setSelectedChannels((prev) =>
                        checked ? prev.filter((id) => id !== acc.id) : [...prev, acc.id]
                      )
                    }
                    className={`flex items-center gap-2.5 p-2.5 rounded-xl cursor-pointer transition-all border ${
                      checked
                        ? 'border-indigo-500/50 bg-indigo-50/60 dark:bg-indigo-950/40 text-slate-900 dark:text-white font-medium'
                        : 'border-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {}}
                      className="rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    <Icon className="text-sm shrink-0" />
                    <span className="text-xs truncate">
                      {acc.platform_username || acc.account_name || acc.platform}
                    </span>
                  </div>
                );
              })
            )}
          </div>

          <div className="p-3 border-t border-gray-100 dark:border-slate-800 bg-white dark:bg-slate-900 text-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowClipper(true)}
              className="w-full text-xs gap-1.5 border-purple-200 text-purple-700 hover:bg-purple-50 dark:border-purple-800 dark:text-purple-300"
            >
              <FaScissors className="text-xs" />
              Open Video Clipper
            </Button>
          </div>
        </aside>

        {/* ── CENTER PANE: Conversation & Action Cards ───────────────────── */}
        <main className="flex-1 flex flex-col min-w-0 bg-white dark:bg-slate-900">
          {/* Header */}
          <div className="h-16 border-b border-gray-100 dark:border-slate-800 px-6 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="p-2 rounded-2xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/20">
                <FaRobot className="text-base" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="text-sm font-bold text-slate-900 dark:text-white truncate">
                    {sessions.find((s) => s.id === currentSessionId)?.title || 'AI Agent Hub'}
                  </h1>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                    <FaCircle className="text-[6px]" /> Live
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Guardrail: {selectedChannels.length} active channel{selectedChannels.length !== 1 ? 's' : ''}
                </p>
              </div>
            </div>

            <Button
              size="sm"
              variant="outline"
              onClick={handleNewSession}
              className="text-xs gap-1.5"
            >
              <FaPlus className="text-xs" /> New Chat
            </Button>
          </div>

          {/* Messages Stream */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {loadingChat ? (
              <div className="p-12 text-center text-sm text-slate-400">
                <FaSpinner className="animate-spin inline mr-2" /> Loading chat thread...
              </div>
            ) : messages.length === 0 ? (
              <div className="p-12 text-center text-sm text-slate-400">
                Say hello to start the conversation!
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.sender === 'assistant' && (
                    <div className="h-8 w-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0 text-xs shadow-xs">
                      <FaRobot />
                    </div>
                  )}

                  <div className={`space-y-3 max-w-xl ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                    <div
                      className={`p-4 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                        msg.sender === 'user'
                          ? 'bg-indigo-600 text-white rounded-br-none shadow-sm'
                          : 'bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-bl-none border border-slate-100 dark:border-slate-700/60'
                      }`}
                    >
                      {msg.text}
                    </div>

                    {/* Action Cards */}
                    {msg.cards && msg.cards.length > 0 && (
                      <div className="space-y-2.5 w-full">
                        {msg.cards.map((card, cIdx) => (
                          <div
                            key={cIdx}
                            className="p-4 rounded-2xl border border-indigo-200 bg-indigo-50/50 dark:border-indigo-900/60 dark:bg-indigo-950/30 space-y-3 shadow-xs"
                          >
                            <div className="flex items-center justify-between">
                              <span className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-950 dark:text-indigo-200">
                                {card.card_type === 'draft_post' && <FaPenToSquare className="text-indigo-600" />}
                                {card.card_type === 'clipping_job' && <FaScissors className="text-purple-600" />}
                                {card.card_type === 'image_generation' && <FaImage className="text-emerald-600" />}
                                {card.title}
                              </span>
                              {card.payload?.platforms && (
                                <div className="flex gap-1">
                                  {card.payload.platforms.map((p) => {
                                    const PIcon = PLATFORM_ICONS[p.toLowerCase()] || FaComments;
                                    return <PIcon key={p} className="text-xs text-slate-500" />;
                                  })}
                                </div>
                              )}
                            </div>

                            {card.summary && (
                              <p className="text-xs text-slate-600 dark:text-slate-300">
                                {card.summary}
                              </p>
                            )}

                            {card.payload?.image_url && (
                              <img
                                src={card.payload.image_url}
                                alt="Generated visual banner"
                                className="w-full h-40 object-cover rounded-xl border border-indigo-100 dark:border-indigo-900"
                              />
                            )}

                            {/* Card Actions */}
                            <div className="flex flex-wrap gap-2 pt-1">
                              {card.card_type === 'draft_post' && (
                                <Button
                                  size="sm"
                                  onClick={() => handleOpenInComposer(card)}
                                  className="text-xs bg-indigo-600 text-white hover:bg-indigo-700"
                                >
                                  <FaPenToSquare className="mr-1.5 text-xs" />
                                  Open in Composer
                                </Button>
                              )}
                              {card.card_type === 'clipping_job' && (
                                <Button
                                  size="sm"
                                  onClick={() => setShowClipper(true)}
                                  className="text-xs bg-purple-600 text-white hover:bg-purple-700"
                                >
                                  <FaScissors className="mr-1.5 text-xs" />
                                  Clip Shorts Now
                                </Button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}

            {sending && (
              <div className="flex gap-3 items-center text-xs text-slate-400">
                <div className="h-8 w-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                  <FaSpinner className="animate-spin text-xs" />
                </div>
                <span>Unravler AI is thinking and formulating actions...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompts */}
          {messages.length <= 2 && (
            <div className="px-6 py-2 flex flex-wrap gap-2">
              {SUGGESTED_PROMPTS.map((prompt, pIdx) => (
                <button
                  key={pIdx}
                  type="button"
                  onClick={() => handleSendMessage(prompt)}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-800/60 dark:hover:bg-slate-800 text-[11px] text-slate-700 dark:text-slate-300 transition-colors text-left"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}

          {/* Input Bar */}
          <div className="p-4 border-t border-gray-100 dark:border-slate-800">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="flex items-end gap-2 p-2 rounded-2xl border border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-800/60 focus-within:border-indigo-500 focus-within:bg-white dark:focus-within:bg-slate-800 transition-all"
            >
              <textarea
                rows={2}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask the AI agent to draft posts, analyze strategy, generate banners, or clip a YouTube video... (Enter to send)"
                className="w-full bg-transparent resize-none border-none outline-none text-xs p-2 text-slate-900 dark:text-white placeholder:text-slate-400"
              />
              <Button
                type="submit"
                disabled={sending || !inputText.trim()}
                className="bg-indigo-600 text-white hover:bg-indigo-700 h-9 w-9 p-0 shrink-0 rounded-xl"
              >
                {sending ? <FaSpinner className="animate-spin text-xs" /> : <FaPaperPlane className="text-xs" />}
              </Button>
            </form>
          </div>
        </main>

        {/* ── RIGHT PANE: Chat Sessions History ───────────────────────────── */}
        <aside className="w-64 border-l border-gray-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 flex flex-col shrink-0 hidden lg:flex">
          <div className="p-4 border-b border-gray-100 dark:border-slate-800 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Threads History
            </h2>
            <button
              type="button"
              onClick={handleNewSession}
              className="text-xs text-indigo-600 dark:text-indigo-400 font-semibold hover:underline"
            >
              + New
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
            {loadingSessions ? (
              <div className="p-4 text-center text-xs text-slate-400">Loading threads...</div>
            ) : sessions.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-400">No threads yet.</div>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  className={`group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all border ${
                    currentSessionId === s.id
                      ? 'border-indigo-500/60 bg-white dark:bg-slate-800 text-slate-900 dark:text-white font-semibold shadow-xs'
                      : 'border-transparent hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400'
                  }`}
                >
                  <div className="min-w-0 pr-2">
                    <p className="text-xs truncate">{s.title || 'Untitled Thread'}</p>
                    <p className="text-[10px] text-slate-400 font-normal">
                      {new Date(s.updated_at || s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 transition-opacity p-1"
                  >
                    <FaTrash className="text-[10px]" />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </DashboardLayout>
  );
}
