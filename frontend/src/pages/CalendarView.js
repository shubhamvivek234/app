import React, { useEffect, useMemo, useState } from 'react';
import {
  addMonths,
  addWeeks,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  startOfMonth,
  startOfWeek,
  subMonths,
  subWeeks,
} from 'date-fns';
import { FaLink, FaCheck, FaExternalLinkAlt, FaSyncAlt, FaTrashAlt } from 'react-icons/fa';

import DashboardLayout from '@/components/DashboardLayout';
import CalendarDayCell from '@/components/calendar/CalendarDayCell';
import CalendarToolbar from '@/components/calendar/CalendarToolbar';
import DayAgendaPanel from '@/components/calendar/DayAgendaPanel';
import {
  getPostAccountIds,
  NOTE_COLORS,
} from '@/components/calendar/calendarHelpers';
import BrandMarkLoader from '@/components/BrandMarkLoader';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  createCalendarNote,
  createCalendarShare,
  revokeCalendarShare,
  deleteCalendarNote,
  getCalendarNotes,
  getPosts,
  getSocialAccounts,
} from '@/lib/api';
import { getPostScheduledTimeZone, getScheduledDateKey } from '@/lib/scheduledTime';
import { toast } from 'sonner';

const CalendarView = () => {
  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('month');

  const [selectedPlatform, setSelectedPlatform] = useState('all');

  const [notes, setNotes] = useState([]);
  const [agendaDay, setAgendaDay] = useState(null);
  const [noteText, setNoteText] = useState('');
  const [noteColor, setNoteColor] = useState(NOTE_COLORS[0]);
  const [savingNote, setSavingNote] = useState(false);

  const [shareToken, setShareToken] = useState(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState(false);

  useEffect(() => {
    fetchPosts();
    loadAccounts();
  }, []);

  useEffect(() => {
    const loadNotes = async () => {
      try {
        const month = format(currentDate, 'yyyy-MM');
        const data = await getCalendarNotes({ month });
        setNotes(data);
      } catch {
        // Notes are supportive; do not block the calendar if they fail.
      }
    };
    loadNotes();
  }, [currentDate]);

  const fetchPosts = async () => {
    try {
      const pageSize = 100;
      const collected = [];
      let page = 1;

      while (true) {
        const batch = await getPosts(null, { page, limit: pageSize });
        if (!Array.isArray(batch) || batch.length === 0) break;
        collected.push(...batch);
        if (batch.length < pageSize) break;
        page += 1;
      }

      setPosts(collected.filter((post) => post.scheduled_time));
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

  let calendarStart;
  let calendarEnd;

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
  const visiblePostsPerDay = viewMode === 'week' ? 6 : 2;

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

  const getPostsForDay = (day) => {
    const dayKey = format(day, 'yyyy-MM-dd');
    return posts
      .filter((post) => {
        const matchesDay = getScheduledDateKey(post.scheduled_time, getPostScheduledTimeZone(post)) === dayKey;
        if (!matchesDay) return false;
        if (selectedPlatform === 'all') return true;
        const postPlatforms = (post.platforms || []).map((p) => String(p).toLowerCase());
        return postPlatforms.includes(selectedPlatform.toLowerCase());
      })
      .sort((a, b) => new Date(a.scheduled_time) - new Date(b.scheduled_time));
  };

  const getNotesForDay = (day) =>
    notes.filter((note) => note.date === format(day, 'yyyy-MM-dd'));

  const visibleScheduledCount = calendarDays.reduce((total, day) => total + getPostsForDay(day).length, 0);
  const visibleNotesCount = calendarDays.reduce((total, day) => total + getNotesForDay(day).length, 0);

  const openAgenda = (day) => {
    setAgendaDay(day);
    setNoteText('');
    setNoteColor(NOTE_COLORS[0]);
  };

  const closeAgenda = () => {
    setAgendaDay(null);
    setNoteText('');
    setNoteColor(NOTE_COLORS[0]);
  };

  const goToPrevious = () => {
    if (viewMode === 'month') setCurrentDate(subMonths(currentDate, 1));
    else setCurrentDate(subWeeks(currentDate, 1));
  };

  const goToNext = () => {
    if (viewMode === 'month') setCurrentDate(addMonths(currentDate, 1));
    else setCurrentDate(addWeeks(currentDate, 1));
  };

  const goToToday = () => {
    setCurrentDate(new Date());
  };

  const isToday = (day) => isSameDay(day, new Date());

  const handleAddNote = async () => {
    if (!noteText.trim() || !agendaDay) return;
    setSavingNote(true);
    try {
      const created = await createCalendarNote({
        date: format(agendaDay, 'yyyy-MM-dd'),
        note: noteText.trim(),
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
    if (e?.stopPropagation) e.stopPropagation();
    try {
      await deleteCalendarNote(noteId);
      setNotes((prev) => prev.filter((note) => note.id !== noteId));
      toast.success('Note removed');
    } catch {
      toast.error('Failed to delete note');
    }
  };

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

  const handleCopyShare = () => {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    toast.success('Share link copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevokeShare = async () => {
    setRevoking(true);
    try {
      await revokeCalendarShare();
      setShareToken(null);
      setShowShareModal(false);
      toast.success('Calendar share link has been revoked');
    } catch {
      toast.error('Failed to revoke share link');
    } finally {
      setRevoking(false);
    }
  };

  const handleRegenerateShare = async () => {
    setShareLoading(true);
    try {
      const share = await createCalendarShare({ regenerate: true });
      setShareToken(share.token);
      toast.success('Generated new calendar share link');
    } catch {
      toast.error('Failed to regenerate share link');
    } finally {
      setShareLoading(false);
    }
  };

  const shareUrl = shareToken ? `${window.location.origin}/calendar/public/${shareToken}` : '';
  const agendaPosts = agendaDay ? getPostsForDay(agendaDay) : [];
  const agendaNotes = agendaDay ? getNotesForDay(agendaDay) : [];

  if (loading) {
    return <BrandMarkLoader />;
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-[1500px]">
        <CalendarToolbar
          currentDate={currentDate}
          calendarStart={calendarStart}
          viewMode={viewMode}
          visiblePostCount={visibleScheduledCount}
          visibleNoteCount={visibleNotesCount}
          selectedPlatform={selectedPlatform}
          onPlatformChange={setSelectedPlatform}
          onToday={goToToday}
          onPrev={goToPrevious}
          onNext={goToNext}
          onViewModeChange={setViewMode}
          onShare={handleShare}
          shareLoading={shareLoading}
        />

        <div className="overflow-hidden rounded-3xl border border-gray-200/90 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm">
          <div className="grid grid-cols-7 border-b border-gray-200/90 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-800/60">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
              <div
                key={day}
                className="border-r border-gray-200/90 dark:border-gray-800 px-3 py-3 text-center text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 last:border-r-0"
              >
                {day}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 divide-x divide-y divide-gray-100 dark:divide-gray-800">
            {calendarDays.map((day) => (
              <CalendarDayCell
                key={format(day, 'yyyy-MM-dd')}
                day={day}
                posts={getPostsForDay(day)}
                notes={getNotesForDay(day)}
                isCurrentMonth={day.getMonth() === currentDate.getMonth()}
                today={isToday(day)}
                viewMode={viewMode}
                visiblePostsPerDay={visiblePostsPerDay}
                getPostDisplayAccounts={getPostDisplayAccounts}
                onOpenAgenda={openAgenda}
              />
            ))}
          </div>
        </div>
      </div>

      <DayAgendaPanel
        open={!!agendaDay}
        day={agendaDay}
        posts={agendaPosts}
        notes={agendaNotes}
        getPostDisplayAccounts={getPostDisplayAccounts}
        noteText={noteText}
        noteColor={noteColor}
        onNoteTextChange={setNoteText}
        onNoteColorChange={setNoteColor}
        onAddNote={handleAddNote}
        onDeleteNote={handleDeleteNote}
        savingNote={savingNote}
        onClose={closeAgenda}
      />

      <Dialog open={showShareModal} onOpenChange={setShowShareModal}>
        <DialogContent className="max-w-md border-slate-200 dark:border-slate-800 dark:bg-slate-900">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              <FaLink className="text-emerald-500" />
              Shareable Calendar Link
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-400">
            Anyone with this link can view your scheduled content calendar in read-only mode without logging in.
          </p>
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800">
            <span className="flex-1 truncate font-mono text-xs text-slate-600 dark:text-slate-300">{shareUrl}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 gap-1.5 h-8 px-2.5"
              onClick={() => window.open(shareUrl, '_blank', 'noopener,noreferrer')}
              title="Open public calendar in new tab"
            >
              <FaExternalLinkAlt className="text-[10px]" />
              Open
            </Button>
            <Button
              type="button"
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold gap-1.5 h-8 px-3"
              onClick={handleCopyShare}
            >
              {copied ? <FaCheck className="text-xs text-emerald-300" /> : null}
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
            <button
              type="button"
              onClick={handleRegenerateShare}
              disabled={shareLoading}
              className="inline-flex items-center gap-1.5 text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 font-medium transition-colors"
            >
              <FaSyncAlt className={`text-[10px] ${shareLoading ? 'animate-spin' : ''}`} />
              Regenerate link
            </button>
            <button
              type="button"
              onClick={handleRevokeShare}
              disabled={revoking}
              className="inline-flex items-center gap-1.5 text-rose-500 hover:text-rose-600 font-semibold transition-colors"
            >
              <FaTrashAlt className="text-[10px]" />
              {revoking ? 'Revoking…' : 'Revoke link'}
            </button>
          </div>

          <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-relaxed">
            This link stays active until you revoke it. Share it with clients or teammates when they only need visibility.
          </p>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default CalendarView;
