import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts, getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { FaInstagram, FaGripVertical, FaImages, FaArrowLeft } from 'react-icons/fa';
import { format, parseISO } from 'date-fns';
import { useNavigate } from 'react-router-dom';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

/** Resolve a media URL to a displayable src */
const resolveMediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${BACKEND_URL}${url}`;
};

/** A single grid cell */
const GridCell = ({
  post,
  index,
  isDragging,
  isDragOver,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}) => {
  const mediaUrl = post?.media_urls?.[0] || post?.video_url || null;
  const imgSrc = resolveMediaUrl(mediaUrl);
  const isScheduled = post?.status === 'scheduled';
  const isPlaceholder = !post;

  return (
    <div
      draggable={isScheduled}
      onDragStart={isScheduled ? () => onDragStart(index) : undefined}
      onDragOver={isScheduled ? (e) => { e.preventDefault(); onDragOver(index); } : undefined}
      onDrop={isScheduled ? () => onDrop(index) : undefined}
      onDragEnd={onDragEnd}
      className={`relative aspect-square overflow-hidden rounded-sm cursor-default group
        ${isScheduled ? 'cursor-grab active:cursor-grabbing' : ''}
        ${isDragOver ? 'ring-2 ring-blue-400 ring-offset-1' : ''}
        ${isDragging ? 'opacity-40' : ''}
        ${isPlaceholder ? 'bg-offwhite border border-gray-200' : ''}
      `}
    >
      {isPlaceholder ? (
        <div className="w-full h-full flex items-center justify-center">
          <FaImages className="text-gray-300 text-2xl" />
        </div>
      ) : imgSrc ? (
        <>
          <img
            src={imgSrc}
            alt={post.content?.slice(0, 40) || 'Post'}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
          {/* Hover overlay */}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2">
            {isScheduled && (
              <div className="flex items-center gap-1 mb-1">
                <FaGripVertical className="text-white text-xs opacity-70" />
                <span className="text-white text-[10px] opacity-80">drag to reorder</span>
              </div>
            )}
            <p className="text-white text-[11px] leading-tight line-clamp-2">
              {post.content}
            </p>
            {post.scheduled_time && (
              <p className="text-white/70 text-[10px] mt-1">
                {format(parseISO(post.scheduled_time), 'MMM d, h:mm a')}
              </p>
            )}
          </div>
          {/* Status badge */}
          <div className={`absolute top-1 right-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full
            ${isScheduled
              ? 'bg-amber-400/90 text-amber-900'
              : 'bg-emerald-500/90 text-white'}`}
          >
            {isScheduled ? 'SCHEDULED' : 'POSTED'}
          </div>
        </>
      ) : (
        /* Text-only post — show caption bg */
        <div className={`w-full h-full flex items-center justify-center p-2
          ${isScheduled ? 'bg-amber-50' : 'bg-offwhite'}`}
        >
          <p className="text-[11px] text-gray-600 text-center line-clamp-4 leading-tight">
            {post.content}
          </p>
          {/* Status badge */}
          <div className={`absolute top-1 right-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full
            ${isScheduled
              ? 'bg-amber-400/90 text-amber-900'
              : 'bg-emerald-500/90 text-white'}`}
          >
            {isScheduled ? 'SCHED' : 'POSTED'}
          </div>
        </div>
      )}
    </div>
  );
};

const InstagramGridPlanner = () => {
  const navigate = useNavigate();
  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dragIndex, setDragIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);

  // Load instagram accounts + posts
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [allPosts, allAccounts] = await Promise.all([
          getPosts(),
          getSocialAccounts(),
        ]);
        const igAccounts = allAccounts.filter(
          (a) => a.platform === 'instagram' && a.is_active
        );
        setAccounts(igAccounts);
        if (igAccounts.length > 0) setSelectedAccount(igAccounts[0]);

        // Filter for instagram posts (published + scheduled), sort by time desc
        const igPosts = allPosts
          .filter(
            (p) =>
              (p.platforms || []).includes('instagram') &&
              (p.status === 'published' || p.status === 'scheduled')
          )
          .sort((a, b) => {
            const timeA = a.published_at || a.scheduled_time || a.created_at;
            const timeB = b.published_at || b.scheduled_time || b.created_at;
            return new Date(timeB) - new Date(timeA);
          });
        setPosts(igPosts);
      } catch {
        toast.error('Failed to load posts');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  // Drag-and-drop: only rearrange scheduled posts among themselves
  const scheduledPosts  = posts.filter((p) => p.status === 'scheduled');
  const publishedPosts  = posts.filter((p) => p.status === 'published');

  // Grid: published posts are locked at top, scheduled follow
  // Pad to multiple of 3 so grid looks complete
  const gridPosts = [...publishedPosts, ...scheduledPosts];
  const remainder = gridPosts.length % 3;
  const padded = remainder === 0
    ? gridPosts
    : [...gridPosts, ...Array(3 - remainder).fill(null)];

  const handleDragStart = useCallback((index) => setDragIndex(index), []);
  const handleDragOver  = useCallback((index) => setDragOverIndex(index), []);
  const handleDragEnd   = useCallback(() => { setDragIndex(null); setDragOverIndex(null); }, []);

  const handleDrop = useCallback(
    (dropIndex) => {
      if (dragIndex === null || dragIndex === dropIndex) return;

      // Only allow reordering within scheduled posts
      const published = posts.filter((p) => p.status === 'published');
      const scheduled = posts.filter((p) => p.status === 'scheduled');

      // Map grid indices back to scheduled indices
      const publishedLen = published.length;
      const fromScheduled = dragIndex - publishedLen;
      const toScheduled   = dropIndex - publishedLen;

      if (fromScheduled < 0 || toScheduled < 0) return; // can't drag published

      const reordered = [...scheduled];
      const [moved] = reordered.splice(fromScheduled, 1);
      reordered.splice(toScheduled, 0, moved);

      setPosts([...published, ...reordered]);
      toast.success('Grid order updated — save to apply new schedule times');
    },
    [dragIndex, posts]
  );

  const stats = {
    total: posts.length,
    published: publishedPosts.length,
    scheduled: scheduledPosts.length,
    withImages: posts.filter((p) => p.media_urls?.length > 0 || p.video_url).length,
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
          >
            <FaArrowLeft />
          </button>
          <div className="flex items-center gap-2">
            <FaInstagram className="text-pink-500 text-xl" />
            <h1 className="text-xl font-semibold text-gray-900">Instagram Grid Planner</h1>
          </div>
          {accounts.length > 1 && (
            <select
              value={selectedAccount?.id || ''}
              onChange={(e) => setSelectedAccount(accounts.find((a) => a.id === e.target.value))}
              className="ml-auto text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-pink-400"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  @{a.account_name || a.username || 'instagram'}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Posts', value: stats.total },
            { label: 'Published', value: stats.published, color: 'text-emerald-600' },
            { label: 'Scheduled', value: stats.scheduled, color: 'text-amber-500' },
            { label: 'With Media', value: stats.withImages },
          ].map(({ label, value, color = 'text-gray-900' }) => (
            <div key={label} className="bg-offwhite rounded-xl border border-gray-200 p-4 text-center">
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full bg-emerald-500" />
            <span className="text-xs text-gray-500">Published (locked)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full bg-amber-400" />
            <span className="text-xs text-gray-500">Scheduled (drag to reorder)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full bg-offwhite border border-gray-300" />
            <span className="text-xs text-gray-500">Empty slot</span>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-8 h-8 border-2 border-pink-400 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : posts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 bg-offwhite rounded-2xl border border-gray-200">
            <FaInstagram className="text-5xl text-gray-200 mb-3" />
            <p className="text-gray-500 font-medium">No Instagram posts yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Create posts targeting Instagram to see your grid here.
            </p>
            <button
              onClick={() => navigate('/create')}
              className="mt-4 px-4 py-2 bg-gradient-to-r from-pink-500 to-purple-500 text-white rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Create a post
            </button>
          </div>
        ) : (
          <>
            {/* Profile header mockup */}
            <div className="bg-offwhite rounded-2xl border border-gray-200 p-4 mb-3">
              <div className="flex items-center gap-4 mb-4 pb-4 border-b border-gray-100">
                <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-pink-400 to-purple-500 flex items-center justify-center text-white text-xl font-bold">
                  {selectedAccount?.account_name?.[0]?.toUpperCase() || 'I'}
                </div>
                <div>
                  <p className="font-semibold text-gray-900">
                    @{selectedAccount?.account_name || selectedAccount?.username || 'your_account'}
                  </p>
                  <div className="flex gap-6 mt-1 text-sm text-gray-600">
                    <span><strong>{stats.total}</strong> posts</span>
                  </div>
                </div>
              </div>

              {/* 3-column grid */}
              <div className="grid grid-cols-3 gap-0.5">
                {padded.map((post, i) => (
                  <GridCell
                    key={post?.id || `empty-${i}`}
                    post={post}
                    index={i}
                    isDragging={dragIndex === i}
                    isDragOver={dragOverIndex === i}
                    onDragStart={handleDragStart}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    onDragEnd={handleDragEnd}
                  />
                ))}
              </div>
            </div>

            {scheduledPosts.length > 0 && (
              <p className="text-xs text-gray-400 text-center">
                Drag scheduled posts to visualise how your grid will look.
                Reordering does not change actual schedule times automatically.
              </p>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
};

export default InstagramGridPlanner;
