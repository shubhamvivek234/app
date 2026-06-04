import React from 'react';
import { format } from 'date-fns';
import { FaChevronLeft, FaChevronRight, FaInfoCircle, FaShare } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const CalendarToolbar = ({
  currentDate,
  calendarStart,
  viewMode,
  visiblePostCount,
  visibleNoteCount,
  onPrev,
  onNext,
  onViewModeChange,
  onShare,
  shareLoading,
}) => {
  const headerLabel = viewMode === 'month'
    ? format(currentDate, 'MMMM yyyy')
    : `Week of ${format(calendarStart, 'MMM d, yyyy')}`;

  return (
    <div className="mb-6 overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_25px_50px_-40px_rgba(15,23,42,0.45)]">
      <div className="border-b border-slate-100 px-5 py-5 sm:px-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">
                Calendar
              </span>
              <FaInfoCircle className="text-slate-300" />
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
              Plan the week without leaving the grid
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
              Scan what is scheduled, what needs context, and which days are overloaded before you open the full content library.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">
              <span>{visiblePostCount} scheduled</span>
              <span className="text-slate-300">·</span>
              <span>{visibleNoteCount} notes</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onShare}
              disabled={shareLoading}
              className="gap-2 border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            >
              <FaShare className="text-xs" />
              {shareLoading ? 'Generating…' : 'Share'}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 px-5 py-4 sm:px-6 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-1">
            <button
              type="button"
              onClick={() => onViewModeChange('month')}
              className={cn(
                'rounded-xl px-4 py-2 text-sm font-semibold transition-colors',
                viewMode === 'month'
                  ? 'bg-slate-950 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-white hover:text-slate-900',
              )}
              data-testid="month-view-button"
            >
              Month
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange('week')}
              className={cn(
                'rounded-xl px-4 py-2 text-sm font-semibold transition-colors',
                viewMode === 'week'
                  ? 'bg-slate-950 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-white hover:text-slate-900',
              )}
              data-testid="week-view-button"
            >
              Week
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 lg:justify-end">
          <div className="inline-flex items-center rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
            <button
              type="button"
              onClick={onPrev}
              className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
              data-testid="prev-button"
            >
              <FaChevronLeft />
            </button>
            <div className="min-w-[220px] px-4 text-center">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                {viewMode === 'month' ? 'Visible range' : 'Focused week'}
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-900">{headerLabel}</p>
            </div>
            <button
              type="button"
              onClick={onNext}
              className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
              data-testid="next-button"
            >
              <FaChevronRight />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarToolbar;
