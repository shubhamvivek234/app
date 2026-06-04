import React from 'react';
import { format } from 'date-fns';
import { FaArrowRight } from 'react-icons/fa';

import { cn } from '@/lib/utils';

import CalendarNotesSection from './CalendarNotesSection';
import CalendarPostChip from './CalendarPostChip';
import { getDaySummaryLabel, noteColorClasses } from './calendarHelpers';

const CalendarDayCell = ({
  day,
  posts = [],
  notes = [],
  isCurrentMonth,
  today = false,
  viewMode = 'month',
  visiblePostsPerDay = 2,
  getPostDisplayAccounts,
  onOpenAgenda,
}) => {
  const isWeek = viewMode === 'week';
  const dayNumberLabel = format(day, 'MMM d') === format(day, 'MMM 1')
    ? format(day, 'MMM d')
    : format(day, 'd');
  const summaryLabel = getDaySummaryLabel(posts.length, notes.length);
  const hiddenPostsCount = Math.max(posts.length - visiblePostsPerDay, 0);

  return (
    <div
      className={cn(
        'border-b border-r border-slate-200/90 last:border-r-0 transition-colors',
        isWeek ? 'min-h-[272px]' : 'min-h-[148px]',
        isCurrentMonth ? 'bg-white' : 'bg-slate-50/80',
        today ? 'bg-emerald-50/80 ring-1 ring-inset ring-emerald-200/80' : 'hover:bg-slate-50/90',
      )}
      data-testid={`calendar-day-${format(day, 'yyyy-MM-dd')}`}
    >
      <button
        type="button"
        onClick={() => onOpenAgenda?.(day)}
        className="flex w-full items-start justify-between gap-3 px-3 pt-3 text-left"
      >
        <div>
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold',
              today
                ? 'bg-emerald-500 text-white shadow-sm'
                : isCurrentMonth
                  ? 'bg-slate-100 text-slate-800'
                  : 'bg-slate-100 text-slate-500',
            )}
          >
            {dayNumberLabel}
          </span>
          {summaryLabel ? (
            <p className="mt-2 text-[11px] font-medium text-slate-500">{summaryLabel}</p>
          ) : null}
        </div>
        <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-600">
          <FaArrowRight className="text-[11px]" />
        </span>
      </button>

      <div className="space-y-2 px-2 pb-2 pt-3">
        {posts.slice(0, visiblePostsPerDay).map((post, index) => (
          <CalendarPostChip
            key={post.id}
            post={post}
            accounts={getPostDisplayAccounts(post)}
            compact={!isWeek}
            today={today}
            noteCount={!isWeek && index === 0 ? notes.length : 0}
            onClick={() => onOpenAgenda?.(day)}
          />
        ))}

        {hiddenPostsCount > 0 ? (
          <button
            type="button"
            className="rounded-xl px-2 py-1 text-[11px] font-semibold text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            onClick={() => onOpenAgenda?.(day)}
          >
            +{hiddenPostsCount} more scheduled
          </button>
        ) : null}

        {posts.length === 0 ? (
          <button
            type="button"
            onClick={() => onOpenAgenda?.(day)}
            className={cn(
              'w-full rounded-2xl border border-dashed px-3 py-3 text-left text-xs transition-colors',
              isWeek
                ? 'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-white'
                : 'border-slate-200/80 bg-slate-50/80 text-slate-400 hover:border-slate-300 hover:text-slate-500',
            )}
          >
            {isWeek ? 'No scheduled posts. Open the day agenda to add notes.' : 'No posts'}
          </button>
        ) : null}

        {!isWeek ? (
          <CalendarNotesSection notes={notes} compact />
        ) : notes.length > 0 ? (
          <div className="space-y-1">
            {notes.slice(0, 2).map((note) => (
              <div
                key={note.id}
                className={cn(
                  'rounded-2xl border px-2.5 py-2 text-[11px] leading-5',
                  noteColorClasses[note.color]?.form || noteColorClasses.green.form,
                  noteColorClasses[note.color]?.border || noteColorClasses.green.border,
                )}
              >
                {note.text}
              </div>
            ))}
            {notes.length > 2 ? (
              <button
                type="button"
                className="text-[11px] font-semibold text-slate-500 transition-colors hover:text-slate-700"
                onClick={() => onOpenAgenda?.(day)}
              >
                +{notes.length - 2} more notes
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default CalendarDayCell;
