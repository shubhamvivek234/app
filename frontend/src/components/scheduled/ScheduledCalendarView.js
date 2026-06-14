import React, { useMemo, useState } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import timeGridPlugin from '@fullcalendar/timegrid';
import { format } from 'date-fns';
import { FaLock, FaRegClock } from 'react-icons/fa';
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

const ScheduledEventContent = ({ eventInfo }) => {
  const post = eventInfo.event.extendedProps.post;
  const locked = eventInfo.event.extendedProps.locked;
  const platforms = getPostPlatforms(post);
  const primaryPlatform = platforms[0] || 'post';
  const title = formatPostLabel(post);
  const statusClass = statusBadgeClasses[post?.status] || 'bg-slate-100 text-slate-600';

  return (
    <div className="min-w-0 rounded-lg border border-sky-200/70 bg-white/95 px-2 py-1.5 text-left shadow-sm ring-1 ring-white/70">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="shrink-0 font-mono text-[10px] font-semibold text-slate-500">
          {eventInfo.timeText || 'Time'}
        </span>
        <span className="shrink-0 rounded-full bg-slate-900 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
          {PLATFORM_LABELS[primaryPlatform] || primaryPlatform}
        </span>
        {locked ? <FaLock className="ml-auto shrink-0 text-[9px] text-amber-500" /> : null}
      </div>
      <div className="mt-1 truncate text-[11px] font-semibold leading-tight text-slate-800">
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
  const [savingPostId, setSavingPostId] = useState(null);

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

  const applyReschedule = async (post, date, time, { revert } = {}) => {
    if (!post?.id || !date || !time) return;

    if (post.status !== 'scheduled') {
      revert?.();
      toast.error('This post is already being processed and cannot be moved.');
      return;
    }

    const scheduledIso = convertWallClockToUtcIso(date, time, calendarTimeZone);
    if (!scheduledIso) {
      revert?.();
      toast.error('Could not understand the selected schedule time.');
      return;
    }

    setSavingPostId(post.id);
    try {
      const updated = await updatePost(post.id, {
        scheduled_time: scheduledIso,
        timezone: calendarTimeZone,
        version: post.version,
      });
      onPostUpdated?.(updated);
      setSelectedPost(null);
      toast.success(`Post rescheduled to ${formatScheduledCompactDateTime(updated.scheduled_time, calendarTimeZone, { includeTimeZone: true })}`);
    } catch (error) {
      revert?.();
      if ([409, 422].includes(error?.response?.status)) {
        onRefresh?.();
      }
      toast.error(getApiErrorMessage(error));
    } finally {
      setSavingPostId(null);
    }
  };

  const handleEventDrop = async (dropInfo) => {
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
    await applyReschedule(post, wallClock.date, wallClock.time, { revert: () => dropInfo.revert() });
  };

  const handleEventClick = (clickInfo) => {
    const post = clickInfo.event.extendedProps.post;
    const parts = getScheduledWallClockParts(post.scheduled_time, calendarTimeZone);
    setSelectedPost(post);
    setExactDate(parts?.date || format(clickInfo.event.start || new Date(), 'yyyy-MM-dd'));
    setExactTime(parts?.time || format(clickInfo.event.start || new Date(), 'HH:mm'));
  };

  const selectedAccount = selectedPost ? getPrimaryAccount(selectedPost, accountMap || {}) : null;
  const selectedMedia = selectedPost ? getPostMediaMeta(selectedPost) : null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FaRegClock className="text-sky-500" />
            Scheduled calendar
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Showing {scheduledPosts.length} filtered scheduled post{scheduledPosts.length === 1 ? '' : 's'} in {calendarTimeZone}. Drag to reschedule, or click for exact time.
          </p>
        </div>
        <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
          Browser timezone: {calendarTimeZone}
        </div>
      </div>

      {scheduledPosts.length === 0 ? (
        <div className="m-4 rounded-xl border-2 border-dashed border-slate-200 p-12 text-center text-sm text-slate-500">
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
            eventAllow={(_dropInfo, draggedEvent) => {
              const post = draggedEvent?.extendedProps?.post;
              return post?.status === 'scheduled';
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

      <Dialog open={Boolean(selectedPost)} onOpenChange={(open) => !open && setSelectedPost(null)}>
        <DialogContent motionPreset="centered" className="max-w-xl rounded-3xl border-slate-200">
          <DialogHeader className="text-left">
            <DialogTitle>Reschedule post</DialogTitle>
            <DialogDescription>
              Set the exact local time for this scheduled post. The save uses {calendarTimeZone}.
            </DialogDescription>
          </DialogHeader>

          {selectedPost && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-900 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-white">
                    {buildPlatformLabel(selectedPost)}
                  </span>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-bold uppercase tracking-wide ${statusBadgeClasses[selectedPost.status] || 'bg-slate-100 text-slate-600'}`}>
                    {selectedPost.status}
                  </span>
                  {selectedMedia ? (
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
                      {selectedMedia.label}
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-3 line-clamp-2 text-sm font-semibold text-slate-900">
                  {formatPostLabel(selectedPost)}
                </h3>
                <p className="mt-1 line-clamp-3 text-sm leading-relaxed text-slate-600">
                  {formatPostPreview(selectedPost, 180)}
                </p>
                <p className="mt-3 text-xs text-slate-500">
                  {selectedAccount ? getAccountLabel(selectedAccount) : 'No account label available'}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-sm font-medium text-slate-700">
                  Date
                  <input
                    type="date"
                    value={exactDate}
                    onChange={(event) => setExactDate(event.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-100"
                  />
                </label>
                <label className="space-y-1.5 text-sm font-medium text-slate-700">
                  Time
                  <input
                    type="time"
                    step="60"
                    value={exactTime}
                    onChange={(event) => setExactTime(event.target.value)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-100"
                  />
                </label>
              </div>

              <p className="rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-700">
                Month drag keeps the current time. Week and day drag use the exact slot you drop onto.
              </p>
            </div>
          )}

          <DialogFooter className="gap-2 sm:justify-between sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => selectedPost && onEditPost?.(selectedPost.id)}
              className="sm:mr-auto"
            >
              Edit full post
            </Button>
            <Button type="button" variant="outline" onClick={() => setSelectedPost(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!selectedPost || !exactDate || !exactTime || savingPostId === selectedPost?.id}
              onClick={() => applyReschedule(selectedPost, exactDate, exactTime)}
            >
              {savingPostId === selectedPost?.id ? 'Saving…' : 'Save time'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ScheduledCalendarView;
