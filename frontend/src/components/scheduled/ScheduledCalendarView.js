import React, { useMemo, useState } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import timeGridPlugin from '@fullcalendar/timegrid';
import { addDays, addHours, format, parseISO } from 'date-fns';
import {
  FaBolt,
  FaCalendarAlt,
  FaCheck,
  FaChevronDown,
  FaExclamationTriangle,
  FaGlobe,
  FaLock,
  FaRegClock,
  FaSearch,
  FaTimes,
} from 'react-icons/fa';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { updatePost } from '@/lib/api';
import {
  convertWallClockToUtcIso,
  formatScheduledCompactDateTime,
  getPostScheduledTimeZone,
  getScheduledWallClockParts,
} from '@/lib/scheduledTime';
import {
  formatPostLabel,
  formatPostPreview,
  getAccountLabel,
  getPostAccountIds,
  getPostMediaMeta,
  getPostPlatforms,
  PLATFORM_LABELS,
  statusBadgeClasses,
} from '@/components/calendar/calendarHelpers';

const COMMON_TIMEZONES = [
  'UTC',
  'Africa/Cairo',
  'Africa/Johannesburg',
  'Africa/Lagos',
  'Africa/Nairobi',
  'America/Bogota',
  'America/Buenos_Aires',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Mexico_City',
  'America/New_York',
  'America/Phoenix',
  'America/Santiago',
  'America/Sao_Paulo',
  'America/Toronto',
  'America/Vancouver',
  'Asia/Bangkok',
  'Asia/Dhaka',
  'Asia/Dubai',
  'Asia/Hong_Kong',
  'Asia/Jakarta',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Manila',
  'Asia/Riyadh',
  'Asia/Seoul',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Melbourne',
  'Australia/Perth',
  'Australia/Sydney',
  'Europe/Amsterdam',
  'Europe/Berlin',
  'Europe/Dublin',
  'Europe/Istanbul',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Paris',
  'Europe/Rome',
  'Europe/Zurich',
  'Pacific/Auckland',
  'Pacific/Honolulu',
];

const PLATFORM_BEST_TIMES = {
  instagram: ['09:00', '12:30', '18:00'],
  linkedin: ['08:30', '12:00', '17:30'],
  twitter: ['09:30', '13:00', '19:00'],
  youtube: ['14:00', '17:00', '20:00'],
  tiktok: ['10:00', '15:00', '19:30'],
  facebook: ['09:00', '13:00', '17:00'],
  threads: ['09:00', '12:00', '18:00'],
  pinterest: ['15:00', '19:00', '21:00'],
  bluesky: ['09:00', '13:00', '18:00'],
};

const getBrowserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
};

const getApiErrorMessage = (error, fallback = 'Failed to reschedule post') => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => item?.msg || item?.message || item)
      .filter(Boolean)
      .join(', ');
    return message || fallback;
  }
  if (detail && typeof detail === 'object') {
    return detail.message || detail.msg || fallback;
  }
  return error?.message || fallback;
};

const getPrimaryAccount = (post, accountMap) => {
  const accountId = getPostAccountIds(post)[0];
  return accountId ? accountMap[accountId] : null;
};

const buildPlatformLabel = (post) => {
  const platforms = getPostPlatforms(post);
  if (platforms.length === 0) return 'No platform';
  const primary = PLATFORM_LABELS[platforms[0]] || platforms[0];
  return platforms.length > 1 ? `${primary} +${platforms.length - 1}` : primary;
};

const buildDropWallClock = ({ event, oldEvent, viewType }) => {
  const targetStart = event.start;
  if (!targetStart) return null;

  const originalStart = oldEvent?.start || event.start;
  const date = format(targetStart, 'yyyy-MM-dd');
  const time = viewType === 'dayGridMonth'
    ? format(originalStart, 'HH:mm')
    : format(targetStart, 'HH:mm');

  return { date, time };
};

const mergeDateWithOriginalTime = (date, originalTime) => {
  if (!date || !originalTime) return date || null;
  const merged = new Date(date);
  merged.setHours(originalTime.getHours(), originalTime.getMinutes(), 0, 0);
  return merged;
};

const getEffectiveAllowedDropDate = (dropInfo, draggedEvent) => {
  if (!dropInfo?.start) return null;
  if (dropInfo.allDay && draggedEvent?.start) {
    return mergeDateWithOriginalTime(dropInfo.start, draggedEvent.start);
  }
  return dropInfo.start;
};

const isFutureDate = (value) => {
  const parsed = value instanceof Date ? value : new Date(value);
  return !Number.isNaN(parsed.getTime()) && parsed.getTime() > Date.now();
};

const getRecommendedBestTimes = (post, targetDate) => {
  const platforms = getPostPlatforms(post);
  const timeSet = new Set();
  platforms.forEach((plat) => {
    const list = PLATFORM_BEST_TIMES[plat.toLowerCase()] || [];
    list.forEach((t) => timeSet.add(t));
  });

  if (timeSet.size === 0) {
    ['09:00', '13:00', '18:00'].forEach((t) => timeSet.add(t));
  }

  const sorted = Array.from(timeSet).sort();
  const todayStr = format(new Date(), 'yyyy-MM-dd');

  if (targetDate === todayStr) {
    const nowHHmm = format(new Date(), 'HH:mm');
    return sorted.filter((t) => t > nowHHmm);
  }
  return sorted;
};

const ScheduledEventContent = ({ eventInfo }) => {
  const post = eventInfo.event.extendedProps.post;
  const locked = eventInfo.event.extendedProps.locked;
  const platforms = getPostPlatforms(post);
  const primaryPlatform = platforms[0] || 'post';
  const title = formatPostLabel(post);
  const statusClass = statusBadgeClasses[post?.status] || 'bg-slate-100 text-slate-600';

  return (
    <div className="min-w-0 rounded-xl border border-sky-200/70 bg-white/95 px-2 py-1.5 text-left shadow-sm ring-1 ring-white/70 dark:border-sky-900/60 dark:bg-slate-900/95 dark:ring-slate-800">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="shrink-0 font-mono text-[10px] font-semibold text-slate-500 dark:text-slate-400">
          {eventInfo.timeText || 'Time'}
        </span>
        <span className="shrink-0 rounded-full bg-slate-900 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white dark:bg-slate-800 dark:text-slate-200">
          {PLATFORM_LABELS[primaryPlatform] || primaryPlatform}
        </span>
        {locked ? <FaLock className="ml-auto shrink-0 text-[9px] text-amber-500" /> : null}
      </div>
      <div className="mt-1 truncate text-[11px] font-semibold leading-tight text-slate-800 dark:text-slate-100">
        {title}
      </div>
      <div className={`mt-1 inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${statusClass}`}>
        {post?.status || 'scheduled'}
      </div>
    </div>
  );
};

const ScheduledCalendarView = ({
  posts,
  accountMap,
  onPostUpdated,
  onRefresh,
  onEditPost,
}) => {
  const calendarTimeZone = useMemo(() => getBrowserTimeZone(), []);
  const [selectedPost, setSelectedPost] = useState(null);
  const [exactDate, setExactDate] = useState('');
  const [exactTime, setExactTime] = useState('');
  const [targetTimezone, setTargetTimezone] = useState(calendarTimeZone);
  const [tzSearchQuery, setTzSearchQuery] = useState('');
  const [tzDropdownOpen, setTzDropdownOpen] = useState(false);
  const [savingPostId, setSavingPostId] = useState(null);
  const [pendingDropInfo, setPendingDropInfo] = useState(null);
  const [isDropAction, setIsDropAction] = useState(false);

  const scheduledPosts = useMemo(
    () => (posts || []).filter((post) => post?.scheduled_time),
    [posts],
  );

  const events = useMemo(
    () => scheduledPosts.map((post) => ({
      id: post.id,
      title: formatPostLabel(post),
      start: post.scheduled_time,
      editable: post.status === 'scheduled',
      durationEditable: false,
      classNames: post.status === 'scheduled' ? ['scheduled-calendar-event'] : ['scheduled-calendar-event', 'is-locked'],
      extendedProps: {
        post,
        locked: post.status !== 'scheduled',
      },
    })),
    [scheduledPosts],
  );

  // Timezone options
  const timezoneOptions = useMemo(() => {
    const set = new Set([calendarTimeZone, ...COMMON_TIMEZONES]);
    if (selectedPost?.timezone) set.add(selectedPost.timezone);
    return Array.from(set);
  }, [calendarTimeZone, selectedPost]);

  const filteredTimezones = useMemo(() => {
    if (!tzSearchQuery.trim()) return timezoneOptions;
    const q = tzSearchQuery.toLowerCase();
    return timezoneOptions.filter((tz) => tz.toLowerCase().includes(q));
  }, [timezoneOptions, tzSearchQuery]);

  // Original timezone of post if explicitly set
  const originalExplicitTz = useMemo(() => {
    if (!selectedPost) return null;
    return getPostScheduledTimeZone(selectedPost);
  }, [selectedPost]);

  // AI Best time suggestions for selected post
  const bestTimes = useMemo(() => {
    if (!selectedPost || !exactDate) return [];
    return getRecommendedBestTimes(selectedPost, exactDate);
  }, [selectedPost, exactDate]);

  // Overlap / Same Account Collision Detection
  const overlapInfo = useMemo(() => {
    if (!selectedPost || !exactDate || !exactTime) return null;

    const targetIso = convertWallClockToUtcIso(exactDate, exactTime, targetTimezone);
    if (!targetIso) return null;
    const targetTimestamp = new Date(targetIso).getTime();

    const postAccountIds = new Set(getPostAccountIds(selectedPost));
    const postPlatforms = new Set(getPostPlatforms(selectedPost));

    // Check other posts within 30 minutes
    const BUFFER_MS = 30 * 60 * 1000;

    for (const other of scheduledPosts) {
      if (other.id === selectedPost.id) continue;
      if (other.status !== 'scheduled' && other.status !== 'queued') continue;

      const otherTime = new Date(other.scheduled_time).getTime();
      const diffMs = Math.abs(targetTimestamp - otherTime);

      if (diffMs <= BUFFER_MS) {
        const otherAccountIds = getPostAccountIds(other);
        const otherPlatforms = getPostPlatforms(other);

        const hasSharedAccount = otherAccountIds.some((id) => postAccountIds.has(id));
        const hasSharedPlatform = otherPlatforms.some((p) => postPlatforms.has(p));

        if (hasSharedAccount || hasSharedPlatform) {
          const conflictingDateParts = getScheduledWallClockParts(other.scheduled_time, targetTimezone);
          const bufferedDate = new Date(targetTimestamp + BUFFER_MS);
          const bufferedParts = getScheduledWallClockParts(bufferedDate.toISOString(), targetTimezone);

          return {
            hasOverlap: true,
            conflictingPost: other,
            conflictingTime: conflictingDateParts?.time || 'same time',
            suggestedTime: bufferedParts?.time || '18:00',
            suggestedDate: bufferedParts?.date || exactDate,
            sharedAccountLabel: hasSharedAccount
              ? (accountMap?.[otherAccountIds[0]]?.display_name || buildPlatformLabel(other))
              : buildPlatformLabel(other),
          };
        }
      }
    }
    return null;
  }, [selectedPost, exactDate, exactTime, targetTimezone, scheduledPosts, accountMap]);

  const applyReschedule = async () => {
    if (!selectedPost?.id || !exactDate || !exactTime) return;

    if (selectedPost.status !== 'scheduled') {
      if (pendingDropInfo) pendingDropInfo.revert();
      toast.error('This post is already being processed and cannot be moved.');
      handleCloseDialog();
      return;
    }

    const scheduledIso = convertWallClockToUtcIso(exactDate, exactTime, targetTimezone);
    if (!scheduledIso) {
      toast.error('Could not understand the selected schedule time.');
      return;
    }
    if (!isFutureDate(scheduledIso)) {
      toast.error('Choose a future date and time.');
      return;
    }

    setSavingPostId(selectedPost.id);
    try {
      const updated = await updatePost(selectedPost.id, {
        scheduled_time: scheduledIso,
        timezone: targetTimezone,
        version: selectedPost.version,
      });
      onPostUpdated?.(updated);
      toast.success(
        `Post rescheduled to ${formatScheduledCompactDateTime(updated.scheduled_time, targetTimezone, { includeTimeZone: true })}`
      );
      setPendingDropInfo(null);
      setSelectedPost(null);
      setIsDropAction(false);
    } catch (error) {
      if (pendingDropInfo) pendingDropInfo.revert();
      if ([409, 422].includes(error?.response?.status)) {
        onRefresh?.();
      }
      toast.error(getApiErrorMessage(error));
    } finally {
      setSavingPostId(null);
    }
  };

  const handleEventDrop = (dropInfo) => {
    const post = dropInfo.event.extendedProps.post;
    const wallClock = buildDropWallClock({
      event: dropInfo.event,
      oldEvent: dropInfo.oldEvent,
      viewType: dropInfo.view.type,
    });
    if (!wallClock) {
      dropInfo.revert();
      toast.error('Could not read the target calendar time.');
      return;
    }

    setPendingDropInfo(dropInfo);
    setIsDropAction(true);
    setSelectedPost(post);
    setExactDate(wallClock.date);
    setExactTime(wallClock.time);
    setTargetTimezone(calendarTimeZone);
    setTzDropdownOpen(false);
  };

  const handleEventClick = (clickInfo) => {
    const post = clickInfo.event.extendedProps.post;
    const parts = getScheduledWallClockParts(post.scheduled_time, calendarTimeZone);
    setPendingDropInfo(null);
    setIsDropAction(false);
    setSelectedPost(post);
    setExactDate(parts?.date || format(clickInfo.event.start || new Date(), 'yyyy-MM-dd'));
    setExactTime(parts?.time || format(clickInfo.event.start || new Date(), 'HH:mm'));
    setTargetTimezone(calendarTimeZone);
    setTzDropdownOpen(false);
  };

  const handleCloseDialog = () => {
    if (pendingDropInfo) {
      pendingDropInfo.revert();
      setPendingDropInfo(null);
    }
    setSelectedPost(null);
    setIsDropAction(false);
    setTzDropdownOpen(false);
  };

  // Quick Action Handlers for Mobile & Fast Reschedule
  const handleQuickAddHour = () => {
    if (!exactDate || !exactTime) return;
    try {
      const currentIso = `${exactDate}T${exactTime}:00`;
      const dateObj = parseISO(currentIso);
      const nextDate = addHours(dateObj, 1);
      setExactDate(format(nextDate, 'yyyy-MM-dd'));
      setExactTime(format(nextDate, 'HH:mm'));
    } catch {
      // noop
    }
  };

  const handleQuickTomorrow = () => {
    if (!exactDate) return;
    try {
      const nextDay = addDays(parseISO(`${exactDate}T00:00:00`), 1);
      setExactDate(format(nextDay, 'yyyy-MM-dd'));
    } catch {
      // noop
    }
  };

  const handleQuickNextWeek = () => {
    if (!exactDate) return;
    try {
      const nextWeek = addDays(parseISO(`${exactDate}T00:00:00`), 7);
      setExactDate(format(nextWeek, 'yyyy-MM-dd'));
    } catch {
      // noop
    }
  };

  const selectedAccount = selectedPost ? getPrimaryAccount(selectedPost, accountMap || {}) : null;
  const selectedMedia = selectedPost ? getPostMediaMeta(selectedPost) : null;
  const todayDate = format(new Date(), 'yyyy-MM-dd');
  const minExactTime = exactDate === todayDate ? format(new Date(), 'HH:mm') : undefined;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <FaRegClock className="text-sky-500" />
            Scheduled calendar
          </div>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Showing {scheduledPosts.length} filtered scheduled post{scheduledPosts.length === 1 ? '' : 's'} in {calendarTimeZone}. Drag to reschedule or tap to configure.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            <FaGlobe className="text-[10px] text-slate-400" />
            Browser timezone: <span className="font-semibold text-slate-900 dark:text-white">{calendarTimeZone}</span>
          </div>
        </div>
      </div>

      {scheduledPosts.length === 0 ? (
        <div className="m-4 rounded-xl border-2 border-dashed border-slate-200 p-12 text-center text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No scheduled posts match the current filters.
        </div>
      ) : (
        <div className="scheduled-calendar-shell p-3">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={{
              left: 'prev,next today',
              center: 'title',
              right: 'dayGridMonth,timeGridWeek,timeGridDay',
            }}
            buttonText={{
              today: 'Today',
              month: 'Month',
              week: 'Week',
              day: 'Day',
            }}
            events={events}
            editable
            eventStartEditable
            eventDurationEditable={false}
            eventDrop={handleEventDrop}
            eventClick={handleEventClick}
            eventContent={(eventInfo) => <ScheduledEventContent eventInfo={eventInfo} />}
            eventAllow={(dropInfo, draggedEvent) => {
              const post = draggedEvent?.extendedProps?.post;
              const effectiveDropDate = getEffectiveAllowedDropDate(dropInfo, draggedEvent);
              return post?.status === 'scheduled' && isFutureDate(effectiveDropDate);
            }}
            nowIndicator
            allDaySlot={false}
            slotDuration="00:30:00"
            snapDuration="00:05:00"
            scrollTime="08:00:00"
            height="auto"
            dayMaxEvents={4}
            eventDisplay="block"
          />
        </div>
      )}

      <Dialog open={Boolean(selectedPost)} onOpenChange={(open) => !open && handleCloseDialog()}>
        <DialogContent motionPreset="centered" className="max-w-xl rounded-3xl border-slate-200 dark:border-slate-800 dark:bg-slate-900">
          <DialogHeader className="text-left">
            <DialogTitle className="flex items-center gap-2 text-lg text-slate-950 dark:text-slate-100">
              <FaCalendarAlt className="text-sky-500" />
              {isDropAction ? 'Confirm New Schedule Slot' : 'Reschedule Post'}
            </DialogTitle>
            <DialogDescription className="dark:text-slate-400">
              Review target date, local time, and timezone before updating.
            </DialogDescription>
          </DialogHeader>

          {selectedPost && (
            <div className="space-y-4">
              {/* Post Summary Preview */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/60">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-900 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-white dark:bg-slate-700">
                    {buildPlatformLabel(selectedPost)}
                  </span>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${statusBadgeClasses[selectedPost.status] || 'bg-slate-100 text-slate-600'}`}>
                    {selectedPost.status}
                  </span>
                  {selectedMedia ? (
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:ring-slate-600">
                      {selectedMedia.label}
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-2.5 line-clamp-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {formatPostLabel(selectedPost)}
                </h3>
                <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
                  {formatPostPreview(selectedPost, 140)}
                </p>
                <p className="mt-2 text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {selectedAccount ? getAccountLabel(selectedAccount) : 'No account label available'}
                </p>
              </div>

              {/* Quick Actions (Mobile / One-Tap Shortcuts) */}
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Quick Actions
                </label>
                <div className="mt-1.5 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleQuickAddHour}
                    className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-all"
                  >
                    +1 Hour
                  </button>
                  <button
                    type="button"
                    onClick={handleQuickTomorrow}
                    className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-all"
                  >
                    Tomorrow
                  </button>
                  <button
                    type="button"
                    onClick={handleQuickNextWeek}
                    className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-all"
                  >
                    Next Week
                  </button>
                </div>
              </div>

              {/* Date & Time Inputs */}
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
                  Date
                  <input
                    type="date"
                    value={exactDate}
                    min={todayDate}
                    onChange={(event) => setExactDate(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-sky-950"
                  />
                </label>
                <label className="space-y-1.5 text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
                  Time (Local / Browser)
                  <input
                    type="time"
                    step="60"
                    value={exactTime}
                    min={minExactTime}
                    onChange={(event) => setExactTime(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-sky-950"
                  />
                </label>
              </div>

              {/* AI Best-Time Suggestions */}
              {bestTimes.length > 0 && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-3 dark:border-emerald-900/60 dark:bg-emerald-950/30">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                    <FaBolt className="text-amber-500" />
                    AI Peak Engagement Slots for {exactDate}:
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {bestTimes.map((timeStr) => (
                      <button
                        key={timeStr}
                        type="button"
                        onClick={() => setExactTime(timeStr)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                          exactTime === timeStr
                            ? 'bg-emerald-600 text-white shadow-xs'
                            : 'bg-white text-emerald-800 border border-emerald-200 hover:bg-emerald-100 dark:bg-slate-800 dark:text-emerald-300 dark:border-emerald-800 dark:hover:bg-slate-700'
                        }`}
                      >
                        ⚡ {timeStr}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Same-Account Collision / Overlap Warning */}
              {overlapInfo?.hasOverlap && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-3.5 dark:border-amber-900/60 dark:bg-amber-950/30">
                  <div className="flex items-start gap-2.5">
                    <FaExclamationTriangle className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-amber-900 dark:text-amber-200">
                        Schedule Collision Warning
                      </p>
                      <p className="mt-0.5 text-xs leading-relaxed text-amber-800 dark:text-amber-300/90">
                        Another post is scheduled on <span className="font-semibold">{overlapInfo.sharedAccountLabel}</span> around <span className="font-semibold">{overlapInfo.conflictingTime}</span>. Posting in the same 30m window may reduce reach.
                      </p>
                      <div className="mt-2 flex items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setExactTime(overlapInfo.suggestedTime);
                            if (overlapInfo.suggestedDate) setExactDate(overlapInfo.suggestedDate);
                          }}
                          className="h-7 border-amber-300 bg-amber-100 text-xs font-bold text-amber-900 hover:bg-amber-200 dark:border-amber-700 dark:bg-amber-900/50 dark:text-amber-200 dark:hover:bg-amber-900"
                        >
                          Auto-space +30m to {overlapInfo.suggestedTime}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Timezone Selector & Context */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                    Timezone
                  </label>
                  {originalExplicitTz && originalExplicitTz !== targetTimezone && (
                    <button
                      type="button"
                      onClick={() => setTargetTimezone(originalExplicitTz)}
                      className="text-[11px] font-semibold text-sky-600 hover:underline dark:text-sky-400"
                    >
                      Reset to original ({originalExplicitTz})
                    </button>
                  )}
                </div>

                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setTzDropdownOpen((prev) => !prev)}
                    className="flex w-full items-center justify-between rounded-xl border border-slate-300 bg-white px-3 py-2 text-left text-sm text-slate-900 shadow-2xs hover:border-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  >
                    <span className="flex items-center gap-2 truncate">
                      <FaGlobe className="text-xs text-slate-400" />
                      <span className="truncate">{targetTimezone}</span>
                      {targetTimezone === calendarTimeZone && (
                        <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-700 dark:bg-sky-950 dark:text-sky-300">
                          Local
                        </span>
                      )}
                    </span>
                    <FaChevronDown className="text-xs text-slate-400" />
                  </button>

                  {tzDropdownOpen && (
                    <div className="absolute z-50 mt-1 max-h-56 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-800">
                      <div className="border-b border-slate-100 p-2 dark:border-slate-700">
                        <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-2 py-1.5 dark:bg-slate-700">
                          <FaSearch className="text-xs text-slate-400" />
                          <input
                            type="text"
                            placeholder="Search timezones..."
                            value={tzSearchQuery}
                            onChange={(e) => setTzSearchQuery(e.target.value)}
                            className="w-full bg-transparent text-xs text-slate-900 focus:outline-none dark:text-white"
                          />
                          {tzSearchQuery && (
                            <button
                              type="button"
                              onClick={() => setTzSearchQuery('')}
                              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                            >
                              <FaTimes className="text-xs" />
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="max-h-40 overflow-y-auto p-1">
                        {filteredTimezones.map((tz) => (
                          <button
                            key={tz}
                            type="button"
                            onClick={() => {
                              setTargetTimezone(tz);
                              setTzDropdownOpen(false);
                            }}
                            className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs font-medium transition-colors ${
                              targetTimezone === tz
                                ? 'bg-sky-50 font-bold text-sky-700 dark:bg-sky-950/60 dark:text-sky-300'
                                : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700'
                            }`}
                          >
                            <span className="truncate">{tz}</span>
                            {targetTimezone === tz && <FaCheck className="text-xs text-sky-600" />}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {originalExplicitTz && originalExplicitTz !== targetTimezone && (
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    ℹ️ Originally created in <span className="font-semibold text-slate-700 dark:text-slate-300">{originalExplicitTz}</span>. Saving will update the timezone to <span className="font-semibold text-slate-700 dark:text-slate-300">{targetTimezone}</span>.
                  </p>
                )}
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:justify-between sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => selectedPost && onEditPost?.(selectedPost.id)}
              className="border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-300 sm:mr-auto"
            >
              Edit in Composer
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleCloseDialog}
              className="border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-300"
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!selectedPost || !exactDate || !exactTime || savingPostId === selectedPost?.id}
              onClick={applyReschedule}
              className="bg-indigo-600 font-bold text-white hover:bg-indigo-700"
            >
              {savingPostId === selectedPost?.id ? 'Saving…' : 'Confirm Reschedule'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ScheduledCalendarView;

