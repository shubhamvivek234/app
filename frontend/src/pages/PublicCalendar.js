import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicCalendar } from '@/lib/api';
import { getPostScheduledTimeZone, getScheduledDateKey } from '@/lib/scheduledTime';
import {
  format,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  startOfWeek,
  endOfWeek,
  isSameDay,
  addMonths,
  subMonths,
} from 'date-fns';
import {
  FaCalendarAlt,
  FaChevronLeft,
  FaChevronRight,
  FaClock,
  FaFacebook,
  FaInstagram,
  FaLinkedin,
  FaPinterest,
  FaRegStickyNote,
  FaTimes,
  FaYoutube,
  FaTiktok,
  FaShieldAlt,
} from 'react-icons/fa';
import { SiBluesky, SiThreads, SiX } from 'react-icons/si';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const PLATFORM_ICONS = {
  twitter: { icon: SiX, color: 'text-slate-900', label: 'X (Twitter)' },
  x: { icon: SiX, color: 'text-slate-900', label: 'X' },
  facebook: { icon: FaFacebook, color: 'text-blue-600', label: 'Facebook' },
  linkedin: { icon: FaLinkedin, color: 'text-blue-700', label: 'LinkedIn' },
  instagram: { icon: FaInstagram, color: 'text-pink-600', label: 'Instagram' },
  pinterest: { icon: FaPinterest, color: 'text-red-600', label: 'Pinterest' },
  youtube: { icon: FaYoutube, color: 'text-red-600', label: 'YouTube' },
  tiktok: { icon: FaTiktok, color: 'text-slate-900', label: 'TikTok' },
  bluesky: { icon: SiBluesky, color: 'text-sky-500', label: 'Bluesky' },
  threads: { icon: SiThreads, color: 'text-slate-900', label: 'Threads' },
};

const NOTE_BADGE_COLORS = {
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
  yellow: 'bg-amber-50 text-amber-700 border-amber-200',
  red: 'bg-rose-50 text-rose-700 border-rose-200',
};

const PublicCalendar = () => {
  const { token } = useParams();
  const [posts, setPosts] = useState([]);
  const [notes, setNotes] = useState([]);
  const [workspaceName, setWorkspaceName] = useState('Content Calendar');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedPost, setSelectedPost] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await getPublicCalendar(token);
        setPosts(data.posts || []);
        setNotes(data.notes || []);
        if (data.workspace_name) {
          setWorkspaceName(data.workspace_name);
        }
      } catch (err) {
        if (err.response?.status === 410) {
          setError('This calendar share link has expired.');
        } else {
          setError('This calendar link is invalid or has been revoked.');
        }
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  // Calendar grid math
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 0 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  const days = eachDayOfInterval({ start: calStart, end: calEnd });

  const getPostsForDay = (day) => {
    const dayKey = format(day, 'yyyy-MM-dd');
    return posts.filter((p) => {
      if (!p.scheduled_time) return false;
      return getScheduledDateKey(p.scheduled_time, getPostScheduledTimeZone(p)) === dayKey;
    });
  };

  const getNotesForDay = (day) => {
    const dayKey = format(day, 'yyyy-MM-dd');
    return notes.filter((n) => n.date === dayKey);
  };

  const isToday = (day) => isSameDay(day, new Date());

  const formatTime = (isoString, timeZone) => {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      return new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: timeZone || undefined,
      }).format(date);
    } catch {
      return '';
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#FAF9F6]">
        <div className="w-10 h-10 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-semibold text-slate-600">Loading public calendar…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[#FAF9F6] px-4 text-center">
        <div className="w-14 h-14 rounded-2xl bg-rose-50 border border-rose-200 text-rose-500 flex items-center justify-center mb-4 shadow-sm">
          <FaCalendarAlt className="text-2xl" />
        </div>
        <h1 className="text-xl font-bold text-slate-900 mb-2">Calendar Unavailable</h1>
        <p className="text-sm text-slate-500 max-w-md mb-6">{error}</p>
        <p className="text-xs text-slate-400">Please request an updated calendar share link from the workspace owner.</p>
      </div>
    );
  }

  const selectedDayPosts = selectedDay ? getPostsForDay(selectedDay) : [];
  const selectedDayNotes = selectedDay ? getNotesForDay(selectedDay) : [];

  return (
    <div className="min-h-screen bg-[#FAF9F6] text-slate-800 antialiased selection:bg-indigo-100 selection:text-indigo-900">
      {/* Top Header Bar */}
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-slate-200/80 px-4 sm:px-8 py-3.5 shadow-2xs">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 text-white font-extrabold text-sm flex items-center justify-center shadow-xs flex-shrink-0">
              ✦
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-extrabold text-slate-900 tracking-tight">
                  {workspaceName}
                </h1>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/80 shadow-2xs">
                  <FaShieldAlt className="text-[9px] text-emerald-600" />
                  Read-Only Calendar
                </span>
              </div>
              <p className="text-xs text-slate-500">Live schedule of upcoming content</p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setCurrentDate(new Date())}
              className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-bold text-slate-700 shadow-2xs transition-colors"
            >
              Today
            </button>
            <div className="flex items-center rounded-xl border border-slate-200 bg-white shadow-2xs">
              <button
                onClick={() => setCurrentDate(subMonths(currentDate, 1))}
                className="p-2 hover:bg-slate-50 text-slate-600 rounded-l-xl transition-colors"
                title="Previous month"
              >
                <FaChevronLeft className="text-xs" />
              </button>
              <span className="text-xs font-bold text-slate-800 min-w-[130px] text-center px-2">
                {format(currentDate, 'MMMM yyyy')}
              </span>
              <button
                onClick={() => setCurrentDate(addMonths(currentDate, 1))}
                className="p-2 hover:bg-slate-50 text-slate-600 rounded-r-xl transition-colors"
                title="Next month"
              >
                <FaChevronRight className="text-xs" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Calendar Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <div className="rounded-3xl border border-slate-200/90 bg-white shadow-sm overflow-hidden">
          {/* Day Names Header */}
          <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50/75">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
              <div
                key={d}
                className="py-3 text-center text-xs font-extrabold uppercase tracking-wider text-slate-500 border-r border-slate-200 last:border-r-0"
              >
                {d}
              </div>
            ))}
          </div>

          {/* 7-column Calendar Grid */}
          <div className="grid grid-cols-7 divide-x divide-y divide-slate-100">
            {days.map((day, idx) => {
              const dayPosts = getPostsForDay(day);
              const dayNotes = getNotesForDay(day);
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const today = isToday(day);

              return (
                <div
                  key={idx}
                  onClick={() => {
                    if (dayPosts.length > 0 || dayNotes.length > 0) {
                      setSelectedDay(day);
                    }
                  }}
                  className={`min-h-[140px] sm:min-h-[160px] p-2 sm:p-2.5 transition-colors flex flex-col justify-between ${
                    dayPosts.length > 0 || dayNotes.length > 0 ? 'cursor-pointer' : ''
                  } ${
                    today
                      ? 'bg-emerald-50/40 ring-1 ring-inset ring-emerald-300/80'
                      : isCurrentMonth
                      ? 'bg-white hover:bg-slate-50/70'
                      : 'bg-slate-50/40'
                  }`}
                >
                  {/* Top Day Header */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span
                        className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                          today
                            ? 'bg-emerald-500 text-white shadow-xs'
                            : isCurrentMonth
                            ? 'text-slate-800'
                            : 'text-slate-300'
                        }`}
                      >
                        {format(day, 'd')}
                      </span>
                      {dayPosts.length > 0 && (
                        <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded-md">
                          {dayPosts.length}
                        </span>
                      )}
                    </div>

                    {/* Notes (if any) */}
                    {dayNotes.length > 0 && (
                      <div className="space-y-1 mb-1.5">
                        {dayNotes.slice(0, 1).map((note) => (
                          <div
                            key={note.id || note.note_id}
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-lg border truncate ${
                              NOTE_BADGE_COLORS[note.color] || NOTE_BADGE_COLORS.green
                            }`}
                            title={note.note || note.text}
                          >
                            <FaRegStickyNote className="inline-block mr-1 text-[9px] -mt-0.5" />
                            {note.note || note.text}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Scheduled Post Chips */}
                    <div className="space-y-1.5">
                      {dayPosts.slice(0, 2).map((post) => {
                        const platforms = post.platforms || [];
                        const primaryPlatform = platforms[0]?.toLowerCase();
                        const platformMeta = PLATFORM_ICONS[primaryPlatform];
                        const Icon = platformMeta?.icon;

                        return (
                          <button
                            key={post.id}
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedPost(post);
                            }}
                            className="w-full text-left rounded-xl border border-slate-200/80 bg-white hover:border-indigo-300 hover:shadow-xs p-1.5 transition-all group"
                          >
                            <div className="flex items-center gap-1 text-[10px] text-slate-500 mb-0.5">
                              {Icon && <Icon className={`text-xs ${platformMeta.color}`} />}
                              <span className="font-semibold text-slate-700 truncate">
                                {formatTime(post.scheduled_time, getPostScheduledTimeZone(post))}
                              </span>
                            </div>
                            <p className="text-[11px] font-medium text-slate-700 line-clamp-2 leading-tight group-hover:text-indigo-600 transition-colors">
                              {post.content || 'Untitled post'}
                            </p>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* +More Button */}
                  {dayPosts.length > 2 && (
                    <div className="pt-1 text-left">
                      <span className="text-[10px] font-bold text-indigo-600 hover:text-indigo-700">
                        +{dayPosts.length - 2} more
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
          <span>Protected Read-Only View</span>
          <span>•</span>
          <span className="font-medium text-slate-500">Powered by Unravler</span>
        </footer>
      </main>

      {/* Post Detail Modal */}
      <Dialog open={!!selectedPost} onOpenChange={(open) => !open && setSelectedPost(null)}>
        <DialogContent className="max-w-lg border-slate-200 bg-white p-6 rounded-3xl shadow-xl">
          <DialogHeader>
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700">
                  <FaClock className="text-xs" />
                  Scheduled Post
                </span>
                {selectedPost?.status && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase tracking-wide bg-slate-100 text-slate-600">
                    {selectedPost.status}
                  </span>
                )}
              </div>
            </div>
            <DialogTitle className="text-base font-bold text-slate-900 pt-2">
              Post Details
            </DialogTitle>
          </DialogHeader>

          {selectedPost && (
            <div className="space-y-4 pt-2">
              {/* Scheduled Time & Platforms */}
              <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-2xl bg-slate-50 border border-slate-200/80 text-xs">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Scheduled Time</p>
                  <p className="font-bold text-slate-800 mt-0.5">
                    {selectedPost.scheduled_time
                      ? format(new Date(selectedPost.scheduled_time), 'EEEE, MMMM d, yyyy @ h:mm a')
                      : 'Not scheduled'}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Platforms</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    {(selectedPost.platforms || []).map((p) => {
                      const meta = PLATFORM_ICONS[p.toLowerCase()];
                      const Icon = meta?.icon;
                      return (
                        <span
                          key={p}
                          className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-xs font-semibold text-slate-700 shadow-2xs"
                        >
                          {Icon && <Icon className={`text-xs ${meta.color}`} />}
                          {meta?.label || p}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Post Content */}
              <div className="p-4 rounded-2xl bg-slate-50/60 border border-slate-200/70">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">Caption / Copy</p>
                <p className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap">
                  {selectedPost.content || '(No caption)'}
                </p>
              </div>

              {/* Media Attachments Preview */}
              {selectedPost.media_urls && selectedPost.media_urls.length > 0 && (
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Media Attachments</p>
                  <div className="grid grid-cols-2 gap-2">
                    {selectedPost.media_urls.map((url, i) => (
                      <div key={i} className="rounded-xl overflow-hidden border border-slate-200 bg-slate-100 aspect-video relative group">
                        <img
                          src={url}
                          alt="Attachment"
                          className="w-full h-full object-cover"
                          onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Day Overview Modal (When clicking a day cell with multiple posts) */}
      <Dialog open={!!selectedDay} onOpenChange={(open) => !open && setSelectedDay(null)}>
        <DialogContent className="max-w-lg border-slate-200 bg-white p-6 rounded-3xl shadow-xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900">
              {selectedDay && format(selectedDay, 'EEEE, MMMM d, yyyy')}
            </DialogTitle>
            <p className="text-xs text-slate-500">
              {selectedDayPosts.length} post{selectedDayPosts.length === 1 ? '' : 's'} scheduled
            </p>
          </DialogHeader>

          {/* Notes for this day */}
          {selectedDayNotes.length > 0 && (
            <div className="space-y-2 mt-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Calendar Notes</p>
              {selectedDayNotes.map((n) => (
                <div
                  key={n.id || n.note_id}
                  className={`p-3 rounded-2xl border text-xs font-semibold ${
                    NOTE_BADGE_COLORS[n.color] || NOTE_BADGE_COLORS.green
                  }`}
                >
                  <FaRegStickyNote className="inline-block mr-1.5 text-xs -mt-0.5" />
                  {n.note || n.text}
                </div>
              ))}
            </div>
          )}

          {/* Posts for this day */}
          <div className="space-y-2.5 mt-4">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Posts</p>
            {selectedDayPosts.map((post) => (
              <div
                key={post.id}
                onClick={() => {
                  setSelectedDay(null);
                  setSelectedPost(post);
                }}
                className="p-3.5 rounded-2xl border border-slate-200 bg-slate-50 hover:bg-white hover:border-indigo-300 transition-all cursor-pointer shadow-2xs group"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    {(post.platforms || []).map((p) => {
                      const meta = PLATFORM_ICONS[p.toLowerCase()];
                      const Icon = meta?.icon;
                      return Icon ? <Icon key={p} className={`text-xs ${meta.color}`} /> : null;
                    })}
                    <span className="text-xs font-bold text-slate-700">
                      {formatTime(post.scheduled_time, getPostScheduledTimeZone(post))}
                    </span>
                  </div>
                  <span className="text-[10px] font-bold text-indigo-600 group-hover:translate-x-0.5 transition-transform">
                    View →
                  </span>
                </div>
                <p className="text-xs text-slate-700 line-clamp-2 leading-relaxed font-medium">
                  {post.content}
                </p>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PublicCalendar;
