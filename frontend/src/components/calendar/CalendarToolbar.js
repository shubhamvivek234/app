import React from 'react';
import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import { FaChevronLeft, FaChevronRight, FaShare, FaPlus, FaCalendarDay } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const PLATFORM_CHIPS = [
  { id: 'all', label: 'All Networks', dot: 'bg-indigo-600' },
  { id: 'instagram', label: 'Instagram', dot: 'bg-pink-500' },
  { id: 'linkedin', label: 'LinkedIn', dot: 'bg-blue-600' },
  { id: 'twitter', label: 'X (Twitter)', dot: 'bg-gray-800 dark:bg-gray-200' },
  { id: 'youtube', label: 'YouTube', dot: 'bg-red-600' },
  { id: 'facebook', label: 'Facebook', dot: 'bg-blue-500' },
  { id: 'tiktok', label: 'TikTok', dot: 'bg-teal-500' },
];

const CalendarToolbar = ({
  currentDate,
  calendarStart,
  viewMode,
  visiblePostCount,
  visibleNoteCount,
  selectedPlatform = 'all',
  onPlatformChange,
  onToday,
  onPrev,
  onNext,
  onViewModeChange,
  onShare,
  shareLoading,
}) => {
  const navigate = useNavigate();
  const headerLabel = viewMode === 'month'
    ? format(currentDate, 'MMMM yyyy')
    : `Week of ${format(calendarStart, 'MMM d, yyyy')}`;

  return (
    <div className="mb-6 rounded-3xl border border-gray-200/80 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
      
      {/* Top Header Row */}
      <div className="border-b border-gray-100 dark:border-gray-800 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center rounded-full bg-indigo-50 dark:bg-indigo-950/60 px-3 py-1 text-[11px] font-extrabold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/60">
                Master Calendar
              </span>
              <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                • {visiblePostCount} Scheduled Posts
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-gray-900 dark:text-white sm:text-3xl">
              Content Schedule Matrix
            </h1>
            <p className="mt-1 text-xs leading-relaxed text-gray-500 dark:text-gray-400 max-w-xl">
              Plan, review, and adjust publishing slots across all connected social channels in a single unified calendar.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Share Link Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={onShare}
              disabled={shareLoading}
              className="gap-2 rounded-xl border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 text-xs font-bold"
            >
              <FaShare className="text-xs text-indigo-600 dark:text-indigo-400" />
              {shareLoading ? 'Generating…' : 'Share Link'}
            </Button>

            {/* Direct Schedule Post Button */}
            <button
              onClick={() => navigate('/create-post')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white text-xs font-bold shadow-md shadow-indigo-500/20 active:scale-[0.98] transition-all"
            >
              <FaPlus className="text-xs" />
              Schedule Post
            </button>
          </div>

        </div>
      </div>

      {/* Middle Controls & Filter Row */}
      <div className="p-4 sm:px-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/40">
        
        {/* Left: View Mode Toggle & Today Navigator */}
        <div className="flex flex-wrap items-center gap-2.5">
          
          {/* View Mode */}
          <div className="flex items-center bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-1 rounded-xl shadow-2xs">
            <button
              type="button"
              onClick={() => onViewModeChange('month')}
              className={cn(
                'rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all',
                viewMode === 'month'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
              )}
              data-testid="month-view-button"
            >
              Month
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange('week')}
              className={cn(
                'rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all',
                viewMode === 'week'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
              )}
              data-testid="week-view-button"
            >
              Week
            </button>
          </div>

          {/* Today Button */}
          {onToday && (
            <button
              type="button"
              onClick={onToday}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 shadow-2xs transition-all"
            >
              <FaCalendarDay className="text-xs text-indigo-600 dark:text-indigo-400" />
              Today
            </button>
          )}

          {/* Date Step Controls */}
          <div className="inline-flex items-center rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-0.5 shadow-2xs">
            <button
              type="button"
              onClick={onPrev}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              data-testid="prev-button"
              title="Previous"
            >
              <FaChevronLeft className="text-xs" />
            </button>
            <span className="px-3 text-xs font-bold text-gray-900 dark:text-white select-none">
              {headerLabel}
            </span>
            <button
              type="button"
              onClick={onNext}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              data-testid="next-button"
              title="Next"
            >
              <FaChevronRight className="text-xs" />
            </button>
          </div>

        </div>

        {/* Right: Notes & Stats Badges */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-3 py-1.5 rounded-xl shadow-2xs">
            📝 {visibleNoteCount} Strategy Notes
          </span>
        </div>

      </div>

      {/* Bottom Platform Filter Chips */}
      {onPlatformChange && (
        <div className="px-5 py-2.5 bg-white dark:bg-gray-900 flex items-center gap-1.5 overflow-x-auto">
          <span className="text-[10px] font-extrabold uppercase tracking-wider text-gray-400 mr-1.5 flex-shrink-0">
            Network:
          </span>
          {PLATFORM_CHIPS.map((chip) => {
            const isSelected = selectedPlatform === chip.id;
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => onPlatformChange(chip.id)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold transition-all flex-shrink-0',
                  isSelected
                    ? 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 font-bold shadow-2xs'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border border-transparent',
                )}
              >
                <span className={cn('w-2 h-2 rounded-full flex-shrink-0', chip.dot)} />
                {chip.label}
              </button>
            );
          })}
        </div>
      )}

    </div>
  );
};

export default CalendarToolbar;
