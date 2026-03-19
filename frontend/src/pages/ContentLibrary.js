import React, { useEffect, useState, useMemo } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts, deletePost, getSocialAccounts, duplicatePost, submitPostForReview, addInternalNote, deleteInternalNote } from '@/lib/api';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { format, isToday, isTomorrow, isThisWeek, isThisMonth } from 'date-fns';
import { FaEdit, FaTrash, FaPlus, FaYoutube, FaInstagram, FaFacebook, FaTiktok, FaUser, FaCopy, FaSearch, FaPaperPlane, FaExclamationCircle, FaStickyNote, FaTimes } from 'react-icons/fa';
import { FaXTwitter } from 'react-icons/fa6';

const platformIcons = {
  youtube: <FaYoutube className="text-red-500" />,
  instagram: <FaInstagram className="text-pink-500" />,
  facebook: <FaFacebook className="text-blue-500" />,
  tiktok: <FaTiktok className="text-black" />,
  twitter: <FaXTwitter className="text-black" />
};

const ContentLibrary = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialStatus = queryParams.get('status') || 'all';

  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Filters state
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState('newest'); // newest, oldest
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [selectedTime, setSelectedTime] = useState('all'); // all, today, tomorrow, this_week, this_month
  const [selectedAccount, setSelectedAccount] = useState('all');
  // Internal notes
  const [openNotePostId, setOpenNotePostId] = useState(null);
  const [noteInput, setNoteInput] = useState('');

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    try {
      const [postsData, accountsData] = await Promise.all([getPosts(), getSocialAccounts()]);
      setPosts(postsData);
      setAccounts(accountsData);
    } catch (error) {
      toast.error('Failed to load posts');
    } finally {
      setLoading(false);
    }
  };

  const accountMap = accounts.reduce((acc, a) => {
    acc[a.id] = a;
    return acc;
  }, {});

  const handleDelete = async (postId) => {
    if (!window.confirm('Are you sure you want to delete this post?')) return;
    try {
      await deletePost(postId);
      setPosts(posts.filter((p) => p.id !== postId));
      toast.success('Post deleted');
    } catch (error) {
      toast.error('Failed to delete post');
    }
  };

  const handleDuplicate = async (postId) => {
    try {
      const copy = await duplicatePost(postId);
      setPosts((prev) => [copy, ...prev]);
      toast.success('Post duplicated as draft');
    } catch {
      toast.error('Failed to duplicate post');
    }
  };

  const handleAddNote = async (postId) => {
    if (!noteInput.trim()) return;
    try {
      const note = await addInternalNote(postId, noteInput.trim());
      setPosts((prev) =>
        prev.map((p) =>
          p.id === postId
            ? { ...p, internal_notes: [...(p.internal_notes || []), note] }
            : p
        )
      );
      setNoteInput('');
    } catch {
      toast.error('Failed to add note');
    }
  };

  const handleDeleteNote = async (postId, noteId) => {
    try {
      await deleteInternalNote(postId, noteId);
      setPosts((prev) =>
        prev.map((p) =>
          p.id === postId
            ? { ...p, internal_notes: (p.internal_notes || []).filter((n) => n.id !== noteId) }
            : p
        )
      );
    } catch {
      toast.error('Failed to delete note');
    }
  };

  const handleSubmitForReview = async (postId) => {
    try {
      await submitPostForReview(postId);
      setPosts((prev) =>
        prev.map((p) => (p.id === postId ? { ...p, status: 'pending_review' } : p))
      );
      toast.success('Post submitted for review');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to submit for review');
    }
  };

  const filteredPosts = useMemo(() => {
    let result = [...posts];

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(p =>
        (p.content || '').toLowerCase().includes(q) ||
        (p.youtube_title || '').toLowerCase().includes(q)
      );
    }

    // Filter by Tab Status (from URL query param or default 'all')
    if (initialStatus !== 'all') {
      result = result.filter(p => p.status === initialStatus);
    }

    // Filter by Platform
    if (selectedPlatform !== 'all') {
      result = result.filter(p => p.platforms && p.platforms.includes(selectedPlatform));
    }

    // Filter by Account
    if (selectedAccount !== 'all') {
      result = result.filter(p => p.accounts && p.accounts.includes(selectedAccount));
    }

    // Filter by Time
    if (selectedTime !== 'all') {
      result = result.filter(p => {
        const d = p.scheduled_time ? new Date(p.scheduled_time) : new Date(p.created_at);
        if (selectedTime === 'today') return isToday(d);
        if (selectedTime === 'tomorrow') return isTomorrow(d);
        if (selectedTime === 'this_week') return isThisWeek(d);
        if (selectedTime === 'this_month') return isThisMonth(d);
        return true;
      });
    }

    // Sort
    result.sort((a, b) => {
      const dateA = a.scheduled_time ? new Date(a.scheduled_time) : new Date(a.created_at);
      const dateB = b.scheduled_time ? new Date(b.scheduled_time) : new Date(b.created_at);
      return sortOrder === 'newest' ? dateB - dateA : dateA - dateB;
    });

    return result;
  }, [posts, searchQuery, initialStatus, selectedPlatform, selectedAccount, selectedTime, sortOrder]);

  const uniquePlatforms = [...new Set(posts.flatMap(p => p.platforms || []))];

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-slate-600">Loading posts...</div>
        </div>
      </DashboardLayout>
    );
  }

  const pageTitle = initialStatus === 'scheduled' ? 'Scheduled Posts' : 
                    initialStatus === 'published' ? 'Published Posts' : 
                    'All Posts';

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-[1600px] mx-auto">
        <div className="flex justify-between items-center">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 flex items-center gap-2">
            {pageTitle} <span className="text-slate-400 text-lg font-normal cursor-help" title="These are all your created posts">ⓘ</span>
          </h1>
          <Button onClick={() => navigate('/create')} size="sm">
            <FaPlus className="mr-2" />
            Create
          </Button>
        </div>

        {/* Filters Row */}
        <div className="flex flex-wrap items-center gap-4 bg-offwhite p-3 rounded-lg border border-slate-200 shadow-sm">
          {/* Search */}
          <div className="relative">
            <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
            <input
              type="text"
              placeholder="Search posts…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-300 w-44 placeholder:text-gray-300 text-gray-700"
            />
          </div>

          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-slate-600">Sort by:</label>
            <select 
              className="text-sm border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 py-1.5"
              value={sortOrder} onChange={(e) => setSortOrder(e.target.value)}
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
            </select>
          </div>

          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-slate-600">Platform:</label>
            <select 
              className="text-sm border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 py-1.5"
              value={selectedPlatform} onChange={(e) => setSelectedPlatform(e.target.value)}
            >
              <option value="all">All Platforms</option>
              {uniquePlatforms.map(p => (
                <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
              ))}
            </select>
          </div>

          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-slate-600">Time:</label>
            <select 
              className="text-sm border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 py-1.5"
              value={selectedTime} onChange={(e) => setSelectedTime(e.target.value)}
            >
              <option value="all">All Time</option>
              <option value="today">Today</option>
              <option value="tomorrow">Tomorrow</option>
              <option value="this_week">This Week</option>
              <option value="this_month">This Month</option>
            </select>
          </div>

          <div className="h-6 w-px bg-slate-200 hidden sm:block"></div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-slate-600">Accounts:</label>
            <select 
              className="text-sm border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 py-1.5"
              value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}
            >
              <option value="all">All Accounts</option>
              {accounts.map(a => (
                <option key={a.id} value={a.id}>{a.platform_username || a.platform}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Posts Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {filteredPosts.length === 0 ? (
            <div className="col-span-full border-2 border-dashed border-slate-200 rounded-xl p-12 text-center text-slate-500">
              No posts match your filters.
            </div>
          ) : (
            filteredPosts.map((post) => {
              const videoTitle = post.youtube_title || post.video_title || null;
              const postAccounts = (post.accounts || []).map((id) => accountMap[id]).filter(Boolean);
              const postDate = post.scheduled_time ? new Date(post.scheduled_time) : new Date(post.created_at);
              
              // Only taking the first associated platform to represent the pill if we want, or map them all
              const primaryPlatform = post.platforms?.[0] || 'unknown';

              return (
                <div
                  key={post.id}
                  className="bg-offwhite rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col hover:shadow-md transition-shadow relative group"
                >
                  {/* Action Dropdown Hover (Top Right) */}
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 z-10 bg-white/80 rounded border border-slate-100 px-1 py-1 backdrop-blur-sm shadow-sm">
                    <button onClick={() => navigate(`/create?edit=${post.id}`)} className="p-1 px-2 text-slate-500 hover:text-indigo-600 text-xs font-medium rounded hover:bg-slate-100 transition-colors">
                      Edit
                    </button>
                    <button
                      onClick={() => handleDuplicate(post.id)}
                      title="Duplicate as draft"
                      className="p-1 px-2 text-slate-500 hover:text-emerald-600 text-xs font-medium rounded hover:bg-slate-100 transition-colors flex items-center gap-1"
                    >
                      <FaCopy className="text-[10px]" />
                    </button>
                    {post.status === 'draft' && (
                      <button
                        onClick={() => handleSubmitForReview(post.id)}
                        title="Submit for review"
                        className="p-1 px-2 text-slate-500 hover:text-amber-600 text-xs font-medium rounded hover:bg-slate-100 transition-colors flex items-center gap-1"
                      >
                        <FaPaperPlane className="text-[10px]" />
                      </button>
                    )}
                    <button onClick={() => handleDelete(post.id)} className="p-1 px-2 text-slate-500 hover:text-red-600 text-xs font-medium rounded hover:bg-slate-100 transition-colors">
                      Delete
                    </button>
                  </div>

                  {/* Rejection note badge (shown on rejected drafts) */}
                  {post.status === 'draft' && post.rejection_note && (
                    <div className="absolute top-2 left-2 z-10">
                      <div
                        title={`Rejected: ${post.rejection_note}`}
                        className="flex items-center gap-1 bg-red-100 text-red-600 text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      >
                        <FaExclamationCircle className="text-[9px]" />
                        Rejected
                      </div>
                    </div>
                  )}

                  {/* Top Bar: Platform Name & Date */}
                  <div className="px-4 py-3 bg-offwhite border-b border-slate-100 flex justify-between items-center text-xs">
                    <div className="flex items-center gap-1.5 font-medium text-slate-600 capitalize bg-offwhite border border-slate-200 px-2 py-0.5 rounded text-[11px] uppercase tracking-wide">
                      {platformIcons[primaryPlatform]} {primaryPlatform}
                    </div>
                    <div className="text-slate-500 font-medium">
                      {format(postDate, 'MM/dd/yyyy')} • {format(postDate, 'h:mm a')}
                    </div>
                  </div>

                  {/* Body Sub-content */}
                  <div className="p-4 flex-1 flex flex-col text-sm">
                    {/* Caption Preview */}
                    <div className="text-slate-700 leading-relaxed line-clamp-4 whitespace-pre-wrap mb-4 flex-1">
                      {videoTitle ? <div className="font-semibold mb-1">{videoTitle}</div> : null}
                      {post.content || <span className="text-slate-400 italic">No caption</span>}
                    </div>

                    {/* Media Preview Thumbnail (If Image/Video provided) */}
                    {post.media_urls && post.media_urls.length > 0 && (
                      <div className="mb-4 h-32 bg-offwhite rounded-lg overflow-hidden border border-slate-200 flex items-center justify-center">
                         <img src={post.cover_image || post.media_urls[0]} alt="Media Thumbnail" className="w-full h-full object-cover" />
                      </div>
                    )}
                  </div>

                  {/* Bottom Bar: Accounts and Status Pill */}
                  <div className="px-4 py-3 border-t border-slate-100 flex justify-between items-center bg-offwhite">
                    {/* Avatars Stack */}
                    <div className="flex -space-x-2">
                      {postAccounts.slice(0, 4).map((acc, idx) => {
                        const colors = ['bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-purple-500', 'bg-pink-500'];
                        const bgColor = colors[(acc.platform_username || 'U').charCodeAt(0) % colors.length];
                        const zIndex = 10 - idx;
                        return (
                          <div key={acc.id} className="relative rounded-full border-2 border-white bg-offwhite" style={{ zIndex }}>
                             {acc.picture_url ? (
                                <img src={acc.picture_url} className="w-7 h-7 rounded-full object-cover" title={acc.platform_username} alt="avatar" />
                             ) : (
                                <div className={`w-7 h-7 rounded-full ${bgColor} flex items-center justify-center text-[10px] text-white font-bold`} title={acc.platform_username}>
                                  {(acc.platform_username || 'U').charAt(0).toUpperCase()}
                                </div>
                             )}
                             <div className="absolute -bottom-0.5 -right-0.5 bg-offwhite rounded-full p-[1px]">
                               {platformIcons[acc.platform] ? React.cloneElement(platformIcons[acc.platform], { className: "w-[8px] h-[8px]" }) : null}
                             </div>
                          </div>
                        )
                      })}
                      {postAccounts.length > 4 && (
                        <div className="w-7 h-7 rounded-full border-2 border-white bg-offwhite flex items-center justify-center text-[10px] text-slate-600 font-bold z-0">
                          +{postAccounts.length - 4}
                        </div>
                      )}
                    </div>

                    {/* Status Pill */}
                    <div className={`px-3 py-1 text-[11px] font-bold uppercase tracking-wider rounded-full ${
                      post.status === 'scheduled' ? 'bg-[#00A3FF] text-white' :
                      post.status === 'published' ? 'bg-emerald-500 text-white' :
                      post.status === 'failed' ? 'bg-red-500 text-white' :
                      'bg-offwhite border border-slate-300 text-slate-700'
                    }`}>
                      {post.status}
                    </div>
                  </div>

                  {/* Notes toggle button */}
                  <button
                    onClick={() => {
                      setOpenNotePostId(openNotePostId === post.id ? null : post.id);
                      setNoteInput('');
                    }}
                    className={`w-full flex items-center gap-1.5 px-4 py-2 text-[11px] font-medium border-t border-slate-100 transition-colors
                      ${openNotePostId === post.id ? 'bg-amber-50 text-amber-700' : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'}`}
                  >
                    <FaStickyNote className="text-[10px]" />
                    Notes
                    {(post.internal_notes?.length > 0) && (
                      <span className="ml-auto bg-amber-200 text-amber-800 text-[9px] font-bold px-1.5 py-0.5 rounded-full">
                        {post.internal_notes.length}
                      </span>
                    )}
                  </button>

                  {/* Notes panel */}
                  {openNotePostId === post.id && (
                    <div className="px-4 pb-3 bg-amber-50 border-t border-amber-100">
                      {/* Existing notes */}
                      <div className="space-y-2 pt-2 mb-2 max-h-36 overflow-y-auto">
                        {(post.internal_notes || []).length === 0 ? (
                          <p className="text-[11px] text-slate-400 italic">No notes yet.</p>
                        ) : (
                          (post.internal_notes || []).map((note) => (
                            <div key={note.id} className="flex items-start gap-2 group/note">
                              <p className="text-[12px] text-slate-700 flex-1 leading-snug">{note.text}</p>
                              <button
                                onClick={() => handleDeleteNote(post.id, note.id)}
                                className="opacity-0 group-hover/note:opacity-100 transition-opacity text-slate-300 hover:text-red-500 flex-shrink-0 mt-0.5"
                              >
                                <FaTimes className="text-[9px]" />
                              </button>
                            </div>
                          ))
                        )}
                      </div>
                      {/* Add note input */}
                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={noteInput}
                          onChange={(e) => setNoteInput(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleAddNote(post.id); }}
                          placeholder="Add a note…"
                          className="flex-1 text-[12px] border border-amber-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-offwhite placeholder:text-slate-300"
                        />
                        <button
                          onClick={() => handleAddNote(post.id)}
                          disabled={!noteInput.trim()}
                          className="px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-amber-400 hover:bg-amber-500 text-white disabled:opacity-40 transition-colors"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ContentLibrary;
