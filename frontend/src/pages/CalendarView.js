import React, { useEffect, useMemo, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts, getCalendarNotes, createCalendarNote, deleteCalendarNote, createCalendarShare, getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, startOfWeek, endOfWeek, addMonths, subMonths, addWeeks, subWeeks } from 'date-fns';
import { FaChevronLeft, FaChevronRight, FaInfoCircle, FaShare, FaLink, FaTimes, FaRegClock } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import BrandMarkLoader from '@/components/BrandMarkLoader';

const NOTE_COLORS = ['green', 'blue', 'yellow', 'red'];

const noteColorClasses = {
  green:  { chip: 'bg-green-100 text-green-700',  form: 'bg-green-50 text-green-800',  dot: 'bg-green-400'  },
  blue:   { chip: 'bg-blue-100 text-blue-700',    form: 'bg-blue-50 text-blue-800',    dot: 'bg-blue-400'   },
  yellow: { chip: 'bg-yellow-100 text-yellow-700',form: 'bg-yellow-50 text-yellow-800',dot: 'bg-yellow-400' },
  red:    { chip: 'bg-red-100 text-red-700',      form: 'bg-red-50 text-red-800',      dot: 'bg-red-400'    },
};

const statusBadgeClasses = {
  draft: 'bg-gray-100 text-gray-600',
  scheduled: 'bg-blue-100 text-blue-700',
  queued: 'bg-amber-100 text-amber-700',
  processing: 'bg-violet-100 text-violet-700',
  published: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  partial: 'bg-orange-100 text-orange-700',
  cancelled: 'bg-slate-100 text-slate-600',
};

const accountAvatarTone = [
  'bg-sky-100 text-sky-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-fuchsia-100 text-fuchsia-700',
];

const getAccountInitials = (account) => {
  const label = account?.platform_username || account?.display_name || account?.platform_user_id || account?.platform || '?';
  return String(label).slice(0, 2).toUpperCase();
};

const formatPostLabel = (post) => {
  const raw = post?.title || post?.content || 'Scheduled post';
  return String(raw).replace(/\s+/g, ' ').trim() || 'Scheduled post';
};

const getPostAccountIds = (post) => {
  if (Array.isArray(post?.account_ids) && post.account_ids.length > 0) return post.account_ids;
  if (Array.isArray(post?.social_account_ids) && post.social_account_ids.length > 0) return post.social_account_ids;
  if (Array.isArray(post?.platform_account_ids) && post.platform_account_ids.length > 0) return post.platform_account_ids;
  if (post?.social_account_id) return [post.social_account_id];
  if (Array.isArray(post?.publish_targets) && post.publish_targets.length > 0) {
    return post.publish_targets.map((target) => target?.account_id).filter(Boolean);
  }
  return [];
};

const AccountAvatar = ({ account, size = 'sm' }) => {
  const sizeClass = size === 'xs' ? 'h-5 w-5 text-[9px]' : 'h-6 w-6 text-[10px]';

  if (account?.picture_url) {
    return (
      <img
        src={account.picture_url}
        alt=""
        className={`${sizeClass} rounded-full border border-white object-cover shadow-sm`}
      />
    );
  }

  const tone = accountAvatarTone[(account?.id || account?.account_id || '').length % accountAvatarTone.length];
  return (
    <div className={`${sizeClass} ${tone} flex items-center justify-center rounded-full border border-white font-bold shadow-sm`}>
      {getAccountInitials(account)}
    </div>
  );
};

const CalendarPostChip = ({ post, accounts, compact = true, today = false }) => {
  const visibleAccounts = accounts.slice(0, 2);
  const extraAccounts = Math.max(accounts.length - visibleAccounts.length, 0);
  const status = String(post?.status || 'scheduled').toLowerCase();
  const statusClass = statusBadgeClasses[status] || statusBadgeClasses.scheduled;
  const label = formatPostLabel(post);
  const textClass = today ? 'text-white/95' : 'text-gray-700';
  const chipClass = today
    ? 'bg-green-400/90 border border-green-300 text-white'
    : 'bg-white border border-gray-200 text-gray-700 shadow-sm';
  const timeValue = post?.scheduled_time ? format(new Date(post.scheduled_time), 'h:mm a') : 'No time';

  return (
    <div
      className={`${chipClass} rounded-lg px-2 py-1.5`}
      title={label}
      data-testid={`post-${post.id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className={`flex min-w-0 items-center gap-1 text-[10px] font-semibold ${today ? 'text-white/90' : 'text-gray-500'}`}>
          <FaRegClock className="shrink-0" />
          <span className="truncate">{timeValue}</span>
        </div>
        <div className="flex shrink-0 items-center -space-x-1">
          {visibleAccounts.map((account) => (
            <AccountAvatar key={account.account_id || account.id} account={account} size="xs" />
          ))}
          {extraAccounts > 0 && (
            <div className={`ml-1 flex h-5 min-w-[20px] items-center justify-center rounded-full border border-white px-1 text-[9px] font-bold shadow-sm ${today ? 'bg-white/20 text-white' : 'bg-gray-100 text-gray-600'}`}>
              +{extraAccounts}
            </div>
          )}
        </div>
      </div>
      <div className={`mt-1 flex items-center gap-1.5 ${compact ? '' : 'gap-2'}`}>
        <span className={`inline-flex shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${today ? 'bg-white/15 text-white' : statusClass}`}>
          {status}
        </span>
        <span className={`min-w-0 truncate text-[11px] font-medium ${textClass}`}>
          {label}
        </span>
      </div>
    </div>
  );
};

const CalendarView = () => {
  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('month'); // 'month' or 'week'

  // Calendar Notes
  const [notes, setNotes] = useState([]);
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedPostsDay, setSelectedPostsDay] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [noteColor, setNoteColor] = useState('green');
  const [savingNote, setSavingNote] = useState(false);

  // Sharing
  const [shareToken, setShareToken] = useState(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);

  useEffect(() => {
    fetchPosts();
    loadAccounts();
  }, []);

  // Reload notes whenever the visible month/week changes
  useEffect(() => {
    const loadNotes = async () => {
      try {
        const month = format(currentDate, 'yyyy-MM');
        const data = await getCalendarNotes(month);
        setNotes(data);
      } catch {
        // silent — notes are non-critical
      }
    };
    loadNotes();
  }, [currentDate]);

  const fetchPosts = async () => {
    try {
      const data = await getPosts();
      setPosts(data.filter((p) => p.scheduled_time));
    } catch (error) {
      toast.error('Failed to load posts');
    } finally {
      setLoading(false);
    }
  };

  const loadAccounts = async () => {
    try {
      const data = await getSocialAccounts();
      setAccounts(Array.isArray(data) ? data : []);
    } catch {
      setAccounts([]);
    }
  };

  let calendarStart, calendarEnd;
  if (viewMode === 'month') {
    const monthStart = startOfMonth(currentDate);
    const monthEnd = endOfMonth(currentDate);
    calendarStart = startOfWeek(monthStart, { weekStartsOn: 0 });
    calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  } else {
    calendarStart = startOfWeek(currentDate, { weekStartsOn: 0 });
    calendarEnd = endOfWeek(currentDate, { weekStartsOn: 0 });
  }
  const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

  const accountLookup = useMemo(() => {
    const lookup = {};
    accounts.forEach((account) => {
      if (account?.id) lookup[account.id] = account;
      if (account?.account_id) lookup[account.account_id] = account;
    });
    return lookup;
  }, [accounts]);

  const getPostDisplayAccounts = (post) => {
    const resolved = getPostAccountIds(post)
      .map((accountId) => accountLookup[accountId])
      .filter(Boolean);
    const deduped = [];
    const seen = new Set();
    resolved.forEach((account) => {
      const key = account.account_id || account.id;
      if (!key || seen.has(key)) return;
      seen.add(key);
      deduped.push(account);
    });
    return deduped;
  };

  const getPostsForDay = (day) =>
    posts
      .filter((post) => isSameDay(new Date(post.scheduled_time), day))
      .sort((a, b) => new Date(a.scheduled_time) - new Date(b.scheduled_time));

  const getNotesForDay = (day) =>
    notes.filter((n) => n.date === format(day, 'yyyy-MM-dd'));

  const goToPrevious = () => {
    if (viewMode === 'month') setCurrentDate(subMonths(currentDate, 1));
    else setCurrentDate(subWeeks(currentDate, 1));
  };

  const goToNext = () => {
    if (viewMode === 'month') setCurrentDate(addMonths(currentDate, 1));
    else setCurrentDate(addWeeks(currentDate, 1));
  };

  const isToday = (day) => isSameDay(day, new Date());

  // ── Note handlers ──────────────────────────────────────────────────────────
  const handleAddNote = async () => {
    if (!noteText.trim() || !selectedDay) return;
    setSavingNote(true);
    try {
      const created = await createCalendarNote({
        date: format(selectedDay, 'yyyy-MM-dd'),
        text: noteText.trim(),
        color: noteColor,
      });
      setNotes((prev) => [...prev, created]);
      setNoteText('');
      toast.success('Note added');
    } catch {
      toast.error('Failed to add note');
    } finally {
      setSavingNote(false);
    }
  };

  const handleDeleteNote = async (noteId, e) => {
    e.stopPropagation();
    try {
      await deleteCalendarNote(noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch {
      toast.error('Failed to delete note');
    }
  };

  const closeNoteDialog = () => {
    setSelectedDay(null);
    setNoteText('');
    setNoteColor('green');
  };

  const closePostsDialog = () => {
    setSelectedPostsDay(null);
  };

  // ── Share handler ──────────────────────────────────────────────────────────
  const handleShare = async () => {
    setShareLoading(true);
    try {
      const share = await createCalendarShare();
      setShareToken(share.token);
      setShowShareModal(true);
    } catch {
      toast.error('Failed to generate share link');
    } finally {
      setShareLoading(false);
    }
  };

  const shareUrl = shareToken ? `${window.location.origin}/calendar/public/${shareToken}` : '';

  if (loading) {
    return (
      <DashboardLayout>
        <BrandMarkLoader overlay />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-full mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">Calendar</h1>
            <FaInfoCircle className="text-gray-400" />
          </div>

          <div className="flex items-center gap-3">
            {/* Share button */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleShare}
              disabled={shareLoading}
              className="gap-2 text-sm text-gray-600"
            >
              <FaShare className="text-xs" />
              {shareLoading ? 'Generating…' : 'Share'}
            </Button>

            {/* Month Navigation */}
            <div className="flex items-center gap-2">
              <button
                onClick={goToPrevious}
                className="p-1 hover:bg-gray-100 rounded"
                data-testid="prev-button"
              >
                <FaChevronLeft className="text-gray-500" />
              </button>
              <span className="text-lg font-medium text-gray-900 min-w-[200px] text-center">
                {viewMode === 'month'
                  ? format(currentDate, 'MMMM yyyy')
                  : `Week of ${format(calendarStart, 'MMM d, yyyy')}`}
              </span>
              <button
                onClick={goToNext}
                className="p-1 hover:bg-gray-100 rounded"
                data-testid="next-button"
              >
                <FaChevronRight className="text-gray-500" />
              </button>
            </div>

            {/* View Toggle */}
            <div className="flex bg-offwhite border border-gray-200 rounded-lg p-1">
              <Button
                variant={viewMode === 'month' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('month')}
                className={viewMode === 'month' ? 'bg-green-500 hover:bg-green-600' : ''}
                data-testid="month-view-button"
              >
                📅 Month
              </Button>
              <Button
                variant={viewMode === 'week' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('week')}
                className={viewMode === 'week' ? 'bg-green-500 hover:bg-green-600' : ''}
                data-testid="week-view-button"
              >
                📆 Week
              </Button>
            </div>
          </div>
        </div>

        {/* Calendar Grid */}
        <div className="bg-offwhite rounded-lg border border-gray-200 overflow-hidden">
          {/* Weekday Headers */}
          <div className="grid grid-cols-7 bg-offwhite border-b border-gray-200">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
              <div
                key={day}
                className="text-center text-sm font-medium text-gray-600 py-3 border-r border-gray-200 last:border-r-0"
              >
                {day}
              </div>
            ))}
          </div>

          {/* Calendar Days */}
          <div className="grid grid-cols-7">
            {calendarDays.map((day, index) => {
              const dayPosts = getPostsForDay(day);
              const dayNotes = getNotesForDay(day);
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const today = isToday(day);

              return (
                <div
                  key={index}
                  onClick={() => setSelectedDay(day)}
                  className={`min-h-[120px] border-b border-r border-gray-200 last:border-r-0 cursor-pointer transition-colors
                    ${!isCurrentMonth ? 'bg-offwhite hover:bg-gray-50' : 'bg-offwhite hover:bg-gray-50'}
                    ${today ? 'bg-green-500 hover:bg-green-500' : ''}`}
                  data-testid={`calendar-day-${format(day, 'yyyy-MM-dd')}`}
                >
                  {/* Day Number */}
                  <div className={`p-2 ${today ? 'text-white' : ''}`}>
                    <span className={`text-sm font-medium ${
                      isCurrentMonth
                        ? today ? 'text-white' : 'text-gray-900'
                        : 'text-gray-400'
                    }`}>
                      {format(day, 'MMM d') === format(day, 'MMM 1')
                        ? format(day, 'MMM d')
                        : format(day, 'd')}
                    </span>
                  </div>

                  {/* Posts */}
                  <div className="px-1 pb-1 space-y-1">
                    {dayPosts.slice(0, 2).map((post) => (
                      <div key={post.id} onClick={(e) => e.stopPropagation()}>
                        <CalendarPostChip
                          post={post}
                          accounts={getPostDisplayAccounts(post)}
                          today={today}
                        />
                      </div>
                    ))}
                    {dayPosts.length > 2 && (
                      <button
                        type="button"
                        className={`px-2 text-[11px] font-semibold transition-colors ${today ? 'text-white/90 hover:text-white' : 'text-gray-500 hover:text-gray-700'}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedPostsDay(day);
                        }}
                      >
                        +{dayPosts.length - 2} more
                      </button>
                    )}
                    {dayPosts.length === 0 && isCurrentMonth && !today && (
                      <div className="text-xs px-2 text-gray-400">No posts</div>
                    )}

                    {/* Note chips */}
                    {dayNotes.map((note) => (
                      <div
                        key={note.id}
                        className={`text-[10px] px-1.5 py-0.5 rounded-full truncate font-medium ${noteColorClasses[note.color]?.chip || noteColorClasses.green.chip}`}
                        title={note.text}
                        onClick={(e) => e.stopPropagation()}
                      >
                        📌 {note.text}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Posts Dialog ─────────────────────────────────────────────────────── */}
      <Dialog open={!!selectedPostsDay} onOpenChange={(open) => { if (!open) closePostsDialog(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-gray-900">
              {selectedPostsDay ? `Scheduled posts for ${format(selectedPostsDay, 'MMMM d, yyyy')}` : ''}
            </DialogTitle>
          </DialogHeader>

          {selectedPostsDay && (
            <div className="max-h-[420px] space-y-3 overflow-y-auto">
              {getPostsForDay(selectedPostsDay).map((post) => {
                const postAccounts = getPostDisplayAccounts(post);
                const fullAccountLabel = postAccounts.length
                  ? postAccounts.map((account) => account.platform_username || account.display_name || account.platform_user_id || account.platform).join(', ')
                  : 'No account info';

                return (
                  <div key={post.id} className="rounded-xl border border-gray-200 bg-offwhite p-3">
                    <CalendarPostChip post={post} accounts={postAccounts} compact={false} />
                    <div className="mt-3 grid gap-2 text-xs text-gray-500">
                      <div>
                        <span className="font-semibold text-gray-700">Scheduled:</span>{' '}
                        {post?.scheduled_time ? format(new Date(post.scheduled_time), 'MMMM d, yyyy h:mm a') : 'No scheduled time'}
                      </div>
                      <div>
                        <span className="font-semibold text-gray-700">Accounts:</span>{' '}
                        {fullAccountLabel}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Note Dialog ──────────────────────────────────────────────────────── */}
      <Dialog open={!!selectedDay} onOpenChange={(open) => { if (!open) closeNoteDialog(); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-gray-900">
              {selectedDay ? format(selectedDay, 'MMMM d, yyyy') : ''}
            </DialogTitle>
          </DialogHeader>

          {/* Existing notes for this day */}
          {selectedDay && getNotesForDay(selectedDay).length > 0 && (
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {getNotesForDay(selectedDay).map((note) => (
                <div
                  key={note.id}
                  className={`flex items-start justify-between gap-2 px-3 py-2 rounded-lg text-sm ${noteColorClasses[note.color]?.form || noteColorClasses.green.form}`}
                >
                  <span className="flex-1 leading-relaxed">{note.text}</span>
                  <button
                    onClick={(e) => handleDeleteNote(note.id, e)}
                    className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity mt-0.5"
                    title="Delete note"
                  >
                    <FaTimes className="text-xs" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add new note */}
          <div className={`${selectedDay && getNotesForDay(selectedDay).length > 0 ? 'border-t pt-3' : ''} space-y-2.5`}>
            <textarea
              rows={2}
              placeholder="Add a note for this day…"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleAddNote();
              }}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-green-400 placeholder:text-gray-300 text-gray-800"
            />

            {/* Color picker + save button */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                {NOTE_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setNoteColor(c)}
                    className={`w-5 h-5 rounded-full transition-transform ${noteColorClasses[c].dot} ${
                      noteColor === c ? 'scale-125 ring-2 ring-offset-1 ring-gray-400' : 'opacity-70'
                    }`}
                    title={c}
                  />
                ))}
              </div>
              <button
                onClick={handleAddNote}
                disabled={!noteText.trim() || savingNote}
                className="ml-auto px-3 py-1.5 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg disabled:opacity-40 transition-colors"
              >
                {savingNote ? 'Saving…' : 'Add Note'}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Share Modal ───────────────────────────────────────────────────────── */}
      <Dialog open={showShareModal} onOpenChange={setShowShareModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <FaLink className="text-green-500" />
              Shareable Calendar Link
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-500">
            Anyone with this link can view your scheduled content calendar — read-only, no login required.
          </p>
          <div className="flex items-center gap-2 bg-offwhite border border-gray-200 rounded-lg px-3 py-2.5">
            <span className="text-xs text-gray-600 truncate flex-1 font-mono">{shareUrl}</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(shareUrl);
                toast.success('Link copied!');
              }}
              className="text-xs font-semibold text-green-600 hover:text-green-700 flex-shrink-0 transition-colors"
            >
              Copy
            </button>
          </div>
          <p className="text-xs text-gray-400">
            This link is permanent until you revoke it. Share it with clients or team members.
          </p>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default CalendarView;
