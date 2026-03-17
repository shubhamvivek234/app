import React, { useEffect, useState, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getAnalyticsFeed, getPostComments, replyToComment,
  getConversations, sendDmReply, getSocialAccounts
} from '@/lib/api';
import { toast } from 'sonner';
import { format } from 'date-fns';
import {
  FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaTiktok, FaGlobe,
  FaComment, FaReply, FaEnvelope, FaSync, FaChevronDown, FaChevronUp, FaHeart, FaPaperPlane
} from 'react-icons/fa';

const PLATFORM_ICONS = {
  instagram: FaInstagram, facebook: FaFacebook, twitter: FaTwitter,
  linkedin: FaLinkedin, youtube: FaYoutube, tiktok: FaTiktok,
};

const PLATFORM_COLORS = {
  instagram: '#E4405F', facebook: '#1877F2', twitter: '#1DA1F2',
  linkedin: '#0A66C2', youtube: '#FF0000', tiktok: '#000000',
};

const COMMENT_PLATFORMS = new Set(['instagram', 'facebook', 'youtube']);
const REPLY_PLATFORMS = new Set(['instagram', 'facebook']);
const DM_PLATFORMS = new Set(['instagram', 'facebook']);

const Publish = () => {
  const [activeTab, setActiveTab] = useState('feed');
  const [feed, setFeed] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [loading, setLoading] = useState(true);

  // Comments state per post
  const [commentsMap, setCommentsMap] = useState({});
  const [commentsLoading, setCommentsLoading] = useState({});
  const [expandedComments, setExpandedComments] = useState({});
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [replySending, setReplySending] = useState(false);

  // DM / Inbox state
  const [conversations, setConversations] = useState([]);
  const [dmLoading, setDmLoading] = useState(false);
  const [dmPlatform, setDmPlatform] = useState('instagram');
  const [dmReplyText, setDmReplyText] = useState('');
  const [dmSending, setDmSending] = useState(false);
  const [selectedConv, setSelectedConv] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getSocialAccounts();
        setAccounts(data);
      } catch { /* ignore */ }
    };
    load();
  }, []);

  const platforms = [...new Set(accounts.map(a => a.platform))];

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAnalyticsFeed(selectedPlatform, 50);
      setFeed(data.posts || []);
    } catch {
      toast.error('Failed to load feed');
    } finally {
      setLoading(false);
    }
  }, [selectedPlatform]);

  useEffect(() => {
    if (activeTab === 'feed') fetchFeed();
  }, [activeTab, fetchFeed]);

  // Fetch comments for a post
  const handleFetchComments = async (post) => {
    const key = `${post.platform}:${post.id}`;
    if (expandedComments[key]) {
      setExpandedComments(prev => ({ ...prev, [key]: false }));
      return;
    }

    setCommentsLoading(prev => ({ ...prev, [key]: true }));
    try {
      const data = await getPostComments(post.platform, post.id);
      setCommentsMap(prev => ({ ...prev, [key]: data.comments || [] }));
      setExpandedComments(prev => ({ ...prev, [key]: true }));
    } catch {
      toast.error('Failed to load comments');
    } finally {
      setCommentsLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  // Reply to comment
  const handleReply = async (post, comment) => {
    if (!replyText.trim()) return;
    setReplySending(true);
    try {
      await replyToComment(post.platform, comment.id, {
        text: replyText,
        accountId: post.account_id,
      });
      toast.success('Reply sent!');
      setReplyText('');
      setReplyingTo(null);
      // Refresh comments
      const key = `${post.platform}:${post.id}`;
      const data = await getPostComments(post.platform, post.id);
      setCommentsMap(prev => ({ ...prev, [key]: data.comments || [] }));
    } catch (err) {
      toast.error('Failed to send reply');
    } finally {
      setReplySending(false);
    }
  };

  // Fetch DMs
  const handleSyncDMs = async () => {
    setDmLoading(true);
    try {
      const data = await getConversations(dmPlatform);
      setConversations(data.conversations || []);
    } catch {
      toast.error(`Failed to load ${dmPlatform} conversations`);
    } finally {
      setDmLoading(false);
    }
  };

  // Send DM reply
  const handleSendDm = async () => {
    if (!dmReplyText.trim() || !selectedConv) return;
    setDmSending(true);
    try {
      await sendDmReply(dmPlatform, selectedConv.id, {
        text: dmReplyText,
        accountId: selectedConv.account_id,
      });
      toast.success('Message sent!');
      setDmReplyText('');
      handleSyncDMs();
    } catch {
      toast.error('Failed to send message');
    } finally {
      setDmSending(false);
    }
  };

  const renderPostCard = (post, idx) => {
    const Icon = PLATFORM_ICONS[post.platform] || FaGlobe;
    const color = PLATFORM_COLORS[post.platform] || '#6b7280';
    const key = `${post.platform}:${post.id}`;
    const comments = commentsMap[key] || [];
    const isExpanded = expandedComments[key];
    const isLoadingComments = commentsLoading[key];
    const canFetchComments = COMMENT_PLATFORMS.has(post.platform);

    return (
      <div key={post.id || idx} className="bg-white rounded-lg border overflow-hidden">
        {/* Post header */}
        <div className="p-4 flex items-center gap-3 border-b border-gray-50">
          <Icon style={{ color }} className="text-lg" />
          <div>
            <span className="text-sm font-medium text-gray-900">{post.account_name || post.platform}</span>
            <span className="text-xs text-gray-400 ml-2 capitalize">{post.platform}</span>
          </div>
          {post.timestamp && (
            <span className="ml-auto text-xs text-gray-400">
              {format(new Date(post.timestamp), 'MMM d, h:mm a')}
            </span>
          )}
        </div>

        {/* Media */}
        {post.media_url && (
          <div className="aspect-video bg-gray-100 overflow-hidden">
            <img
              src={post.media_url}
              alt=""
              className="w-full h-full object-cover"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          </div>
        )}

        {/* Content */}
        <div className="p-4">
          <p className="text-sm text-gray-800 whitespace-pre-wrap line-clamp-4">{post.content || '(No caption)'}</p>
        </div>

        {/* Metrics */}
        <div className="px-4 pb-3 flex items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1"><FaHeart className="text-red-400" /> {post.likes || 0}</span>
          <span className="flex items-center gap-1"><FaComment /> {post.comments_count || 0}</span>
          {post.views !== undefined && <span>{post.views.toLocaleString()} views</span>}
          {post.permalink && (
            <a href={post.permalink} target="_blank" rel="noopener noreferrer" className="ml-auto text-blue-500 hover:underline">View</a>
          )}
        </div>

        {/* Comments section */}
        {canFetchComments && (
          <div className="border-t border-gray-100">
            <button
              onClick={() => handleFetchComments(post)}
              disabled={isLoadingComments}
              className="w-full px-4 py-2.5 flex items-center gap-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <FaComment className="text-xs" />
              {isLoadingComments ? 'Loading...' : isExpanded ? 'Hide Comments' : `View Comments (${post.comments_count || 0})`}
              {isExpanded ? <FaChevronUp className="ml-auto text-xs" /> : <FaChevronDown className="ml-auto text-xs" />}
            </button>

            {isExpanded && (
              <div className="border-t border-gray-50 max-h-80 overflow-y-auto">
                {comments.length === 0 ? (
                  <p className="px-4 py-3 text-xs text-gray-400">No comments yet.</p>
                ) : (
                  comments.map((comment) => (
                    <div key={comment.id} className="px-4 py-3 border-b border-gray-50 last:border-0">
                      <div className="flex items-start gap-2">
                        {comment.author_avatar ? (
                          <img src={comment.author_avatar} alt="" className="w-6 h-6 rounded-full" />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500">
                            {comment.author_name?.[0]?.toUpperCase() || '?'}
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium text-gray-900">{comment.author_name}</span>
                            <span className="text-xs text-gray-400">
                              {comment.timestamp ? format(new Date(comment.timestamp), 'MMM d') : ''}
                            </span>
                            {comment.likes > 0 && (
                              <span className="text-xs text-gray-400 flex items-center gap-0.5">
                                <FaHeart className="text-red-300" /> {comment.likes}
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-700 mt-0.5">{comment.content}</p>
                          {comment.can_reply && REPLY_PLATFORMS.has(post.platform) && (
                            <button
                              onClick={() => setReplyingTo(replyingTo === comment.id ? null : comment.id)}
                              className="text-xs text-blue-500 hover:underline mt-1 flex items-center gap-1"
                            >
                              <FaReply className="text-[10px]" /> Reply
                            </button>
                          )}
                          {/* Reply composer */}
                          {replyingTo === comment.id && (
                            <div className="mt-2 flex gap-2">
                              <input
                                value={replyText}
                                onChange={(e) => setReplyText(e.target.value)}
                                onKeyDown={(e) => {
                                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleReply(post, comment);
                                }}
                                placeholder="Write a reply..."
                                className="flex-1 text-sm border rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-green-500"
                                disabled={replySending}
                              />
                              <button
                                onClick={() => handleReply(post, comment)}
                                disabled={replySending || !replyText.trim()}
                                className="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 disabled:opacity-50"
                              >
                                {replySending ? '...' : 'Send'}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderFeed = () => {
    if (loading) {
      return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg border p-6 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/3 mb-4" />
              <div className="h-32 bg-gray-200 rounded mb-4" />
              <div className="h-3 bg-gray-200 rounded w-2/3" />
            </div>
          ))}
        </div>
      );
    }

    if (!feed.length) {
      return (
        <div className="text-center py-12 text-gray-500">
          <FaComment className="text-3xl mx-auto mb-3 text-gray-300" />
          <p>No posts found. Connect social accounts and they'll appear here.</p>
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {feed.map((post, idx) => renderPostCard(post, idx))}
      </div>
    );
  };

  const renderInbox = () => {
    const dmPlatforms = platforms.filter(p => DM_PLATFORMS.has(p));

    return (
      <div className="space-y-4">
        {/* DM Platform Selector */}
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-sm font-medium text-gray-700">Platform:</span>
            {dmPlatforms.length === 0 ? (
              <span className="text-sm text-gray-400">No DM-capable platforms connected (Instagram, Facebook Page)</span>
            ) : (
              dmPlatforms.map(p => {
                const Icon = PLATFORM_ICONS[p] || FaGlobe;
                return (
                  <button
                    key={p}
                    onClick={() => setDmPlatform(p)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors ${
                      dmPlatform === p ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    <Icon className="text-xs" />
                    <span className="capitalize">{p}</span>
                  </button>
                );
              })
            )}
            <button
              onClick={handleSyncDMs}
              disabled={dmLoading || dmPlatforms.length === 0}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              <FaSync className={dmLoading ? 'animate-spin' : ''} /> Sync DMs
            </button>
          </div>
        </div>

        {/* Conversations */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Conversation list */}
          <div className="lg:col-span-1 bg-white rounded-lg border overflow-hidden">
            <div className="p-3 border-b bg-gray-50">
              <h3 className="text-sm font-medium text-gray-700">Conversations</h3>
            </div>
            {conversations.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-400">
                {dmLoading ? 'Loading...' : 'Click "Sync DMs" to fetch conversations'}
              </div>
            ) : (
              <div className="divide-y max-h-96 overflow-y-auto">
                {conversations.map((conv) => (
                  <button
                    key={conv.id}
                    onClick={() => setSelectedConv(conv)}
                    className={`w-full text-left p-3 hover:bg-gray-50 transition-colors ${
                      selectedConv?.id === conv.id ? 'bg-green-50' : ''
                    }`}
                  >
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {conv.participants?.join(', ') || 'Unknown'}
                    </p>
                    <p className="text-xs text-gray-500 truncate mt-0.5">{conv.last_message || 'No messages'}</p>
                    {conv.last_message_time && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {format(new Date(conv.last_message_time), 'MMM d, h:mm a')}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Message area */}
          <div className="lg:col-span-2 bg-white rounded-lg border overflow-hidden flex flex-col">
            <div className="p-3 border-b bg-gray-50">
              <h3 className="text-sm font-medium text-gray-700">
                {selectedConv ? (selectedConv.participants?.join(', ') || 'Conversation') : 'Select a conversation'}
              </h3>
            </div>
            <div className="flex-1 p-4 min-h-[200px] flex items-center justify-center">
              {selectedConv ? (
                <div className="text-center text-sm text-gray-500">
                  <FaEnvelope className="text-2xl mx-auto mb-2 text-gray-300" />
                  <p>Last message: {selectedConv.last_message || 'No messages'}</p>
                  <p className="text-xs text-gray-400 mt-1">Full conversation history requires the Conversations API permission</p>
                </div>
              ) : (
                <p className="text-sm text-gray-400">Select a conversation to view and reply</p>
              )}
            </div>
            {selectedConv && (
              <div className="p-3 border-t flex gap-2">
                <input
                  value={dmReplyText}
                  onChange={(e) => setDmReplyText(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSendDm();
                  }}
                  placeholder="Type a message..."
                  className="flex-1 text-sm border rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-green-500"
                  disabled={dmSending}
                />
                <button
                  onClick={handleSendDm}
                  disabled={dmSending || !dmReplyText.trim()}
                  className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-1.5"
                >
                  <FaPaperPlane className="text-xs" />
                  {dmSending ? 'Sending...' : 'Send'}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const tabItems = [
    { id: 'feed', label: 'Feed & Comments', icon: FaComment },
    { id: 'inbox', label: 'Messages / DMs', icon: FaEnvelope },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Publish</h1>
          <p className="text-base text-slate-600 mt-1">View posts, reply to comments, and manage DMs.</p>
        </div>

        {/* Platform Filter */}
        {activeTab === 'feed' && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setSelectedPlatform(null)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                !selectedPlatform ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              All
            </button>
            {platforms.map((p) => {
              const Icon = PLATFORM_ICONS[p] || FaGlobe;
              return (
                <button
                  key={p}
                  onClick={() => setSelectedPlatform(p)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    selectedPlatform === p ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  <Icon className="text-xs" />
                  <span className="capitalize">{p}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Tabs */}
        <div className="border-b border-gray-200">
          <nav className="flex gap-6">
            {tabItems.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`pb-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                    activeTab === tab.id
                      ? 'border-green-600 text-green-700'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Icon className="text-xs" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Content */}
        {activeTab === 'feed' && renderFeed()}
        {activeTab === 'inbox' && renderInbox()}
      </div>
    </DashboardLayout>
  );
};

export default Publish;
