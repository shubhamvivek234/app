import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getInbox, updateInboxMessage, deleteInboxMessage, getInboxStats } from '@/lib/api';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  FaInbox, FaComment, FaEnvelope, FaReply, FaTrash,
  FaCheck, FaCheckDouble, FaFilter,
  FaInstagram, FaFacebook, FaYoutube, FaTiktok, FaReddit, FaLinkedin,
} from 'react-icons/fa';
import { FaXTwitter } from 'react-icons/fa6';
import { SiThreads, SiBluesky } from 'react-icons/si';

const PLATFORM_ICONS = {
  twitter:   <FaXTwitter   className="text-black" />,
  instagram: <FaInstagram  className="text-pink-500" />,
  facebook:  <FaFacebook   className="text-blue-600" />,
  linkedin:  <FaLinkedin   className="text-blue-700" />,
  youtube:   <FaYoutube    className="text-red-600" />,
  tiktok:    <FaTiktok     className="text-black" />,
  threads:   <SiThreads    className="text-gray-800" />,
  bluesky:   <SiBluesky    className="text-sky-500" />,
  reddit:    <FaReddit     className="text-orange-500" />,
};

const FILTER_TABS = [
  { key: 'all',      label: 'All' },
  { key: 'unread',   label: 'Unread' },
  { key: 'comment',  label: 'Comments', typeFilter: true },
  { key: 'dm',       label: 'DMs',      typeFilter: true },
  { key: 'replied',  label: 'Replied' },
];

const AvatarPlaceholder = ({ name, className = '' }) => {
  const colors = ['bg-pink-400','bg-blue-400','bg-green-400','bg-purple-400','bg-orange-400','bg-teal-400'];
  const bg = colors[(name?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`rounded-full flex items-center justify-center text-white font-semibold text-sm flex-shrink-0 ${bg} ${className}`}>
      {name?.[0]?.toUpperCase() || '?'}
    </div>
  );
};

const Inbox = () => {
  const [messages, setMessages]     = useState([]);
  const [stats, setStats]           = useState({ total: 0, unread: 0, replied: 0 });
  const [loading, setLoading]       = useState(true);
  const [activeTab, setActiveTab]   = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [replyText, setReplyText]   = useState('');
  const [replying, setReplying]     = useState(false);
  const replyRef = useRef(null);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const tab = FILTER_TABS.find((t) => t.key === activeTab);
      const params = {};
      if (tab?.typeFilter) params.type = activeTab;
      else if (activeTab !== 'all') params.status = activeTab;

      const [msgs, st] = await Promise.all([getInbox(params), getInboxStats()]);
      setMessages(msgs);
      setStats(st);
    } catch {
      toast.error('Failed to load inbox');
    } finally {
      setLoading(false);
    }
  };

  const selected = messages.find((m) => m.id === selectedId) || null;

  const markRead = async (id) => {
    try {
      await updateInboxMessage(id, { status: 'read' });
      setMessages((prev) => prev.map((m) => m.id === id ? { ...m, status: 'read' } : m));
      setStats((s) => ({ ...s, unread: Math.max(0, s.unread - 1) }));
    } catch { /* silent */ }
  };

  const handleSelect = (msg) => {
    setSelectedId(msg.id);
    setReplyText('');
    if (msg.status === 'unread') markRead(msg.id);
  };

  const handleReply = async () => {
    if (!replyText.trim() || !selectedId) return;
    setReplying(true);
    try {
      await updateInboxMessage(selectedId, { reply: replyText.trim() });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === selectedId
            ? { ...m, reply: replyText.trim(), status: 'replied', replied_at: new Date().toISOString() }
            : m
        )
      );
      setReplyText('');
      toast.success('Reply saved');
    } catch {
      toast.error('Failed to save reply');
    } finally {
      setReplying(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteInboxMessage(id);
      setMessages((prev) => prev.filter((m) => m.id !== id));
      if (selectedId === id) setSelectedId(null);
      toast.success('Message deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  const statusBadge = (status) => {
    if (status === 'unread')   return <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />;
    if (status === 'replied')  return <FaCheckDouble className="text-emerald-500 text-xs flex-shrink-0" />;
    return <FaCheck className="text-gray-300 text-xs flex-shrink-0" />;
  };

  return (
    <DashboardLayout>
      <div className="flex h-[calc(100vh-64px)] overflow-hidden">

        {/* ── Left panel — message list ── */}
        <div className="w-80 flex-shrink-0 border-r border-gray-200 flex flex-col bg-offwhite">
          {/* Header */}
          <div className="px-4 pt-5 pb-3 border-b border-gray-100">
            <div className="flex items-center gap-2 mb-3">
              <FaInbox className="text-gray-600" />
              <h1 className="text-base font-semibold text-gray-900">Inbox</h1>
              {stats.unread > 0 && (
                <span className="ml-auto text-xs font-bold bg-blue-500 text-white px-2 py-0.5 rounded-full">
                  {stats.unread}
                </span>
              )}
            </div>
            {/* Filter tabs */}
            <div className="flex gap-1 flex-wrap">
              {FILTER_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => { setActiveTab(tab.key); setSelectedId(null); }}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors
                    ${activeTab === tab.key
                      ? 'bg-gray-900 text-white'
                      : 'bg-offwhite border border-gray-200 text-gray-600 hover:bg-gray-50'}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Message list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-center px-4">
                <FaInbox className="text-4xl text-gray-200 mb-2" />
                <p className="text-sm text-gray-400">No messages here yet.</p>
                <p className="text-xs text-gray-300 mt-1">Comments and DMs will appear here once synced.</p>
              </div>
            ) : (
              messages.map((msg) => (
                <button
                  key={msg.id}
                  onClick={() => handleSelect(msg)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors
                    ${selectedId === msg.id ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}
                    ${msg.status === 'unread' ? 'bg-blue-50/40' : ''}`}
                >
                  <div className="flex items-start gap-2.5">
                    {msg.author_avatar
                      ? <img src={msg.author_avatar} alt="" className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
                      : <AvatarPlaceholder name={msg.author_name} className="w-8 h-8" />
                    }
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="text-xs font-semibold text-gray-800 truncate">{msg.author_name}</span>
                        <span className="flex-shrink-0">{PLATFORM_ICONS[msg.platform] || null}</span>
                        <span className="ml-auto text-[10px] text-gray-400 flex-shrink-0">
                          {msg.received_at ? format(parseISO(msg.received_at), 'MMM d') : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {msg.type === 'dm'
                          ? <FaEnvelope className="text-[10px] text-gray-400 flex-shrink-0" />
                          : <FaComment  className="text-[10px] text-gray-400 flex-shrink-0" />
                        }
                        <p className="text-xs text-gray-500 truncate">{msg.content}</p>
                        <span className="ml-auto">{statusBadge(msg.status)}</span>
                      </div>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* ── Right panel — message detail ── */}
        <div className="flex-1 flex flex-col bg-offwhite overflow-hidden">
          {!selected ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <FaInbox className="text-5xl text-gray-200 mb-3" />
              <p className="text-gray-400 font-medium">Select a message to read</p>
            </div>
          ) : (
            <>
              {/* Message header */}
              <div className="px-6 py-4 bg-offwhite border-b border-gray-200 flex items-center gap-3">
                {selected.author_avatar
                  ? <img src={selected.author_avatar} alt="" className="w-10 h-10 rounded-full object-cover" />
                  : <AvatarPlaceholder name={selected.author_name} className="w-10 h-10" />
                }
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900">{selected.author_name}</p>
                  <div className="flex items-center gap-1.5 text-xs text-gray-500">
                    <span className="capitalize">{selected.platform}</span>
                    <span>·</span>
                    <span className="capitalize">{selected.type}</span>
                    {selected.received_at && (
                      <>
                        <span>·</span>
                        <span>{format(parseISO(selected.received_at), 'MMM d, h:mm a')}</span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(selected.id)}
                  className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  title="Delete"
                >
                  <FaTrash className="text-xs" />
                </button>
              </div>

              {/* Message body */}
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
                {/* Original message */}
                <div className="flex gap-3">
                  {selected.author_avatar
                    ? <img src={selected.author_avatar} alt="" className="w-8 h-8 rounded-full object-cover flex-shrink-0" />
                    : <AvatarPlaceholder name={selected.author_name} className="w-8 h-8" />
                  }
                  <div className="bg-offwhite rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100 max-w-lg">
                    <p className="text-sm text-gray-800 leading-relaxed">{selected.content}</p>
                  </div>
                </div>

                {/* Existing reply */}
                {selected.reply && (
                  <div className="flex gap-3 justify-end">
                    <div className="bg-blue-500 rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg">
                      <p className="text-sm text-white leading-relaxed">{selected.reply}</p>
                      {selected.replied_at && (
                        <p className="text-[10px] text-blue-200 mt-1 text-right">
                          {format(parseISO(selected.replied_at), 'MMM d, h:mm a')}
                        </p>
                      )}
                    </div>
                    <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                      You
                    </div>
                  </div>
                )}
              </div>

              {/* Reply box */}
              <div className="px-6 py-4 bg-offwhite border-t border-gray-200">
                <div className="flex gap-2 items-end">
                  <textarea
                    ref={replyRef}
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleReply();
                    }}
                    placeholder={`Reply to ${selected.author_name}…`}
                    rows={2}
                    className="flex-1 resize-none border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 placeholder:text-gray-300"
                  />
                  <button
                    onClick={handleReply}
                    disabled={replying || !replyText.trim()}
                    className="p-2.5 rounded-xl bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-40 transition-colors flex-shrink-0"
                    title="Send reply (⌘+Enter)"
                  >
                    <FaReply />
                  </button>
                </div>
                <p className="text-[10px] text-gray-300 mt-1.5">
                  Note: replies are saved locally. To publish to {selected.platform}, you'll need platform API credentials.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Inbox;
