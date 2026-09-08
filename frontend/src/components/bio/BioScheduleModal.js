import React, { useEffect } from 'react';
import {
  FaTimes,
  FaClock,
  FaCalendarAlt,
  FaCheck,
  FaTrashAlt,
  FaInfoCircle,
  FaBolt,
} from 'react-icons/fa';
import { toast } from 'sonner';

export default function BioScheduleModal({
  isOpen,
  onClose,
  pageSchedule = { enabled: false, start_at: '', end_at: '' },
  setPageSchedule,
  handle,
}) {
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isEnabled = Boolean(pageSchedule?.enabled);
  const startAt = pageSchedule?.start_at || '';
  const endAt = pageSchedule?.end_at || '';

  // Calculate live status preview
  const now = new Date();
  let statusBadge = {
    label: 'Schedule Disabled',
    desc: 'Your Smart Bio is always live and visible when published.',
    color: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
    dot: 'bg-emerald-500',
  };

  if (isEnabled) {
    const startDate = startAt ? new Date(startAt) : null;
    const endDate = endAt ? new Date(endAt) : null;

    if (startDate && now < startDate) {
      statusBadge = {
        label: 'Upcoming (Coming Soon)',
        desc: `Goes live on ${startDate.toLocaleDateString(undefined, {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
        })}. Visitors currently see the Apple-styled "Coming Soon" card.`,
        color: 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
        dot: 'bg-amber-500 animate-pulse',
      };
    } else if (endDate && now > endDate) {
      statusBadge = {
        label: 'Window Expired',
        desc: `Expired on ${endDate.toLocaleDateString(undefined, {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
        })}. Visitors currently see the "Page Expired" status card.`,
        color: 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
        dot: 'bg-rose-500',
      };
    } else {
      statusBadge = {
        label: 'Active & Live Now',
        desc: endDate
          ? `Page is live now and will expire on ${endDate.toLocaleDateString(undefined, {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
            })}.`
          : 'Page is active and live now with scheduled start.',
        color: 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
        dot: 'bg-blue-500 animate-pulse',
      };
    }
  }

  // Quick Presets
  const formatInputDateTime = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const applyPreset = (hours) => {
    const start = new Date();
    const end = new Date(Date.now() + hours * 60 * 60 * 1000);
    setPageSchedule?.((prev) => ({
      ...prev,
      enabled: true,
      start_at: formatInputDateTime(start),
      end_at: formatInputDateTime(end),
    }));
    toast.success(`Schedule window set for next ${hours < 48 ? `${hours} hours` : `${Math.round(hours / 24)} days`}`);
  };

  const handleClearSchedule = () => {
    setPageSchedule?.((prev) => ({
      ...prev,
      start_at: '',
      end_at: '',
      enabled: false,
    }));
    toast.info('Schedule window cleared');
  };

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/50 backdrop-blur-xl animate-in fade-in duration-200 select-none"
    >
      {/* Apple Double-Bezel Container */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-lg p-1.5 sm:p-2 rounded-[2rem] bg-black/5 dark:bg-white/10 ring-1 ring-black/10 dark:ring-white/15 shadow-2xl backdrop-blur-2xl transition-all"
      >
        <div className="rounded-[calc(2rem-0.375rem)] bg-[#FFFFFF] dark:bg-[#1C1C1E] border border-black/[0.05] dark:border-white/[0.08] overflow-hidden flex flex-col text-gray-900 dark:text-gray-100">
          
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4.5 border-b border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-amber-500 to-orange-500 flex items-center justify-center text-white shadow-sm">
                <FaClock className="text-base" />
              </div>
              <div>
                <h2 className="text-base font-bold tracking-tight flex items-center gap-2">
                  <span>Scheduled Live Window</span>
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Control start time & end time for @{handle || 'your-bio'}
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full border border-black/[0.08] dark:border-white/[0.1] text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white flex items-center justify-center hover:bg-black/5 dark:hover:bg-white/5 transition active:scale-95 cursor-pointer"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-5">
            
            {/* Main Toggle Switch */}
            <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between">
              <div className="space-y-0.5 pr-4">
                <div className="text-xs font-bold text-gray-900 dark:text-white">
                  Enable Scheduled Visibility
                </div>
                <div className="text-[11px] text-gray-500 dark:text-gray-400 leading-relaxed">
                  When enabled, visitors can only view this bio during your specified window. Outside this window, a polite status card is displayed.
                </div>
              </div>
              <label className="apple-switch shrink-0">
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={(e) =>
                    setPageSchedule?.((prev) => ({ ...prev, enabled: e.target.checked }))
                  }
                />
                <span className="apple-switch-slider"></span>
              </label>
            </div>

            {/* Current Status Pill */}
            <div className={`p-3.5 rounded-2xl border flex items-start gap-3 ${statusBadge.color}`}>
              <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${statusBadge.dot}`} />
              <div className="space-y-0.5 min-w-0">
                <div className="text-xs font-bold">{statusBadge.label}</div>
                <div className="text-[11px] opacity-90 leading-relaxed">{statusBadge.desc}</div>
              </div>
            </div>

            {/* Date Time Inputs */}
            <div className={`space-y-4 transition-opacity duration-200 ${isEnabled ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
              
              {/* Start Time */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                  <FaCalendarAlt className="text-gray-400 text-[10px]" />
                  <span>Start Time (Go-Live)</span>
                </label>
                <input
                  type="datetime-local"
                  value={startAt}
                  onChange={(e) =>
                    setPageSchedule?.((prev) => ({ ...prev, start_at: e.target.value }))
                  }
                  className="w-full px-3.5 py-2 text-xs rounded-xl bg-gray-50 dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                />
                <p className="text-[10px] text-gray-400">
                  Leave blank to make the page live immediately upon publishing.
                </p>
              </div>

              {/* End Time */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                  <FaCalendarAlt className="text-gray-400 text-[10px]" />
                  <span>End Time (Expiry)</span>
                </label>
                <input
                  type="datetime-local"
                  value={endAt}
                  onChange={(e) =>
                    setPageSchedule?.((prev) => ({ ...prev, end_at: e.target.value }))
                  }
                  className="w-full px-3.5 py-2 text-xs rounded-xl bg-gray-50 dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                />
                <p className="text-[10px] text-gray-400">
                  Leave blank if the page should remain live indefinitely once started.
                </p>
              </div>

              {/* 1-Click Quick Presets */}
              <div className="pt-2">
                <div className="text-[11px] font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1">
                  <FaBolt className="text-amber-500 text-[10px]" />
                  <span>Quick Presets</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => applyPreset(24)}
                    className="px-2.5 py-1.5 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-gray-50 dark:bg-zinc-800/60 hover:bg-gray-100 dark:hover:bg-zinc-800 text-[11px] font-medium transition active:scale-95"
                  >
                    Next 24 Hours
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset(72)}
                    className="px-2.5 py-1.5 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-gray-50 dark:bg-zinc-800/60 hover:bg-gray-100 dark:hover:bg-zinc-800 text-[11px] font-medium transition active:scale-95"
                  >
                    Next 3 Days
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset(168)}
                    className="px-2.5 py-1.5 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-gray-50 dark:bg-zinc-800/60 hover:bg-gray-100 dark:hover:bg-zinc-800 text-[11px] font-medium transition active:scale-95"
                  >
                    Next 7 Days
                  </button>
                </div>
              </div>

            </div>

          </div>

          {/* Footer Actions */}
          <div className="px-6 py-4 border-t border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50 flex items-center justify-between">
            {(startAt || endAt || isEnabled) ? (
              <button
                type="button"
                onClick={handleClearSchedule}
                className="flex items-center gap-1.5 text-xs text-rose-500 hover:text-rose-600 font-semibold transition cursor-pointer"
              >
                <FaTrashAlt className="text-[10px]" />
                <span>Clear Schedule</span>
              </button>
            ) : (
              <span className="text-[11px] text-gray-400 flex items-center gap-1">
                <FaInfoCircle className="text-[10px]" />
                No time limits set
              </span>
            )}

            <button
              type="button"
              onClick={() => {
                toast.success('Schedule settings applied. Remember to click Publish to save live!');
                onClose();
              }}
              className="px-5 py-2 rounded-full text-xs font-semibold text-white bg-[#0071E3] hover:bg-[#0077ED] transition active:scale-95 cursor-pointer shadow-sm flex items-center gap-1.5"
            >
              <FaCheck className="text-[10px]" />
              <span>Done</span>
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
