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
import {
  FaLink,
  FaCheck,
  FaExternalLinkAlt,
  FaSyncAlt,
  FaTrashAlt,
  FaCopy,
  FaQrcode,
  FaShieldAlt,
  FaEye,
} from 'react-icons/fa';
import QRCode from 'qrcode';

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
import { useSearchParams } from 'react-router-dom';
import {
  createCalendarNote,
  createCalendarShare,
  revokeCalendarShare,
  deleteCalendarNote,
  getCalendarNotes,
  getPosts,
  getSocialAccounts,
  getCampaigns,
} from '@/lib/api';
import { getPostScheduledTimeZone, getScheduledDateKey } from '@/lib/scheduledTime';
import { toast } from 'sonner';

const CalendarView = () => {
  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('month');

  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(() => searchParams.get('campaign') || searchParams.get('campaign_id') || 'all');

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
  const [showQr, setShowQr] = useState(false);
  const [qrCodeUrl, setQrCodeUrl] = useState('');

  const shareUrl = shareToken ? `${window.location.origin}/calendar/public/${shareToken}` : '';

  useEffect(() => {
    if (shareUrl) {
      QRCode.toDataURL(shareUrl, { width: 160, margin: 1 })
        .then(setQrCodeUrl)
        .catch(() => {});
    }
  }, [shareUrl]);

  useEffect(() => {
    fetchPosts();
    loadAccounts();
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    try {
      const data = await getCampaigns();
      setCampaigns(data || []);
    } catch {
      // Non-blocking
    }
  };

  const campaignMap = useMemo(() => {
    const map = {};
    (campaigns || []).forEach((c) => {
      if (c && c.id) map[c.id] = c;
    });
    return map;
  }, [campaigns]);

  const handleCampaignChange = (cmpId) => {
    setSelectedCampaign(cmpId);
    if (cmpId && cmpId !== 'all') {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('campaign', cmpId);
        return next;
      });
    } else {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete('campaign');
        next.delete('campaign_id');
        return next;
      });
    }
  };

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
        if (selectedPlatform !== 'all') {
          const postPlatforms = (post.platforms || []).map((p) => String(p).toLowerCase());
          if (!postPlatforms.includes(selectedPlatform.toLowerCase())) return false;
        }
        if (selectedCampaign !== 'all') {
          if (post.campaign_id !== selectedCampaign) return false;
        }
        return true;
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
          campaigns={campaigns}
          selectedCampaign={selectedCampaign}
          onCampaignChange={handleCampaignChange}
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
                campaignMap={campaignMap}
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
        onRetrySuccess={fetchPosts}
      />

      <Dialog open={showShareModal} onOpenChange={setShowShareModal}>
        <DialogContent
          motionPreset="centered"
          className="max-w-lg overflow-hidden border-gray-200 dark:border-gray-800 p-0 sm:rounded-[28px] bg-white dark:bg-gray-900 shadow-2xl"
        >
          {/* Header Banner */}
          <div className="border-b border-gray-100 dark:border-gray-800 bg-gray-50/75 dark:bg-gray-900/90 px-6 py-5">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 px-2.5 py-0.5 text-[11px] font-extrabold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/60">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live Client Link
              </span>
            </div>
            <DialogTitle className="mt-2 text-xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
              Share Content Calendar
            </DialogTitle>
            <p className="mt-1 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
              Anyone with this link can view your scheduled and published content calendar in read-only mode without logging in.
            </p>
          </div>

          {/* Modal Body */}
          <div className="px-6 py-5 space-y-4">
            {/* Public Link Input Box */}
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1.5">
                Shareable URL
              </label>
              <div className="flex items-center gap-2 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/70 p-2 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 transition-all">
                <div className="pl-2 text-gray-400 dark:text-gray-500">
                  <FaLink className="text-xs text-indigo-600 dark:text-indigo-400" />
                </div>
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  onClick={(e) => e.target.select()}
                  className="w-full bg-transparent font-mono text-xs text-gray-800 dark:text-gray-200 focus:outline-none select-all truncate px-1"
                />
                <button
                  type="button"
                  onClick={handleCopyShare}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:scale-95 text-white text-xs font-bold transition-all shadow-xs shrink-0"
                >
                  {copied ? <FaCheck className="text-xs text-emerald-300" /> : <FaCopy className="text-xs" />}
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>

            {/* Quick Action Buttons */}
            <div className="flex items-center gap-2.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => window.open(shareUrl, '_blank', 'noopener,noreferrer')}
                className="flex-1 rounded-xl border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 font-bold text-xs gap-1.5 h-9"
              >
                <FaExternalLinkAlt className="text-xs text-indigo-600 dark:text-indigo-400" />
                Open in New Tab
              </Button>

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowQr((prev) => !prev)}
                className={`rounded-xl border-gray-200 dark:border-gray-700 text-xs font-bold gap-1.5 h-9 px-3 transition-colors ${
                  showQr
                    ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <FaQrcode className="text-xs" />
                {showQr ? 'Hide QR' : 'QR Code'}
              </Button>
            </div>

            {/* QR Code Collapsible Display */}
            {showQr && qrCodeUrl && (
              <div className="flex flex-col items-center justify-center p-4 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50/70 dark:bg-gray-800/40 animate-in fade-in zoom-in-95 duration-150">
                <div className="p-2.5 rounded-2xl bg-white shadow-xs border border-gray-100">
                  <img src={qrCodeUrl} alt="Calendar Share QR Code" className="w-32 h-32 rounded-lg" />
                </div>
                <p className="mt-2 text-[11px] font-medium text-gray-500 dark:text-gray-400">
                  Scan to preview the client calendar on mobile
                </p>
              </div>
            )}

            {/* Information / Permissions Cards */}
            <div className="grid grid-cols-2 gap-2.5 p-3 rounded-2xl bg-gray-50/75 dark:bg-gray-800/40 border border-gray-200/80 dark:border-gray-800 text-[11px]">
              <div className="flex items-start gap-2">
                <FaEye className="text-indigo-500 mt-0.5 shrink-0" />
                <div>
                  <p className="font-bold text-gray-800 dark:text-gray-200">Read-Only Access</p>
                  <p className="text-gray-500 dark:text-gray-400 text-[10px] leading-tight mt-0.5">
                    Viewers can inspect posts & notes, but cannot edit or publish
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <FaShieldAlt className="text-emerald-500 mt-0.5 shrink-0" />
                <div>
                  <p className="font-bold text-gray-800 dark:text-gray-200">Private & Secure</p>
                  <p className="text-gray-500 dark:text-gray-400 text-[10px] leading-tight mt-0.5">
                    No login required. Access can be rotated or revoked anytime
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Footer Action Bar */}
          <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/60 px-6 py-3.5 flex items-center justify-between">
            <button
              type="button"
              onClick={handleRegenerateShare}
              disabled={shareLoading}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 transition-colors disabled:opacity-50"
              title="Generate a brand new URL, invalidating the previous link"
            >
              <FaSyncAlt className={`text-[10px] ${shareLoading ? 'animate-spin text-indigo-600' : ''}`} />
              Regenerate link
            </button>
            <button
              type="button"
              onClick={handleRevokeShare}
              disabled={revoking}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-600 hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300 transition-colors disabled:opacity-50"
              title="Immediately deactivate and delete this link"
            >
              <FaTrashAlt className="text-[10px]" />
              {revoking ? 'Revoking…' : 'Revoke link'}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default CalendarView;
