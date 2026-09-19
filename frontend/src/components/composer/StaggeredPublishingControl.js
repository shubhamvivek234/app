import React from 'react';
import { FaClock, FaRandom, FaArrowRight, FaLayerGroup } from 'react-icons/fa';

const PRESET_INTERVALS = [
  { label: 'All at once', minutes: 0 },
  { label: '15m apart', minutes: 15 },
  { label: '30m apart', minutes: 30 },
  { label: '60m apart', minutes: 60 },
];

export default function StaggeredPublishingControl({
  selectedPlatforms = [],
  staggerMinutes = 0,
  onChangeStaggerMinutes,
  baseScheduledTime,
  platformIcons = {},
}) {
  if (selectedPlatforms.length < 2) return null;

  const baseTime = baseScheduledTime ? new Date(baseScheduledTime) : new Date();

  return (
    <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-3.5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-xs">
            <FaClock className="text-[11px]" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-gray-800 dark:text-slate-200 flex items-center gap-1.5">
              Staggered Cross-Posting
              <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 px-1.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                Viral Reach
              </span>
            </h4>
            <p className="text-[11px] text-gray-500 dark:text-slate-400">
              Space out publishing across networks to avoid duplicate spam flags.
            </p>
          </div>
        </div>

        {/* Interval presets */}
        <div className="flex items-center gap-1">
          {PRESET_INTERVALS.map((preset) => {
            const active = Number(staggerMinutes) === preset.minutes;
            return (
              <button
                key={preset.minutes}
                type="button"
                onClick={() => onChangeStaggerMinutes(preset.minutes)}
                className={`px-2 py-1 rounded-lg text-xs font-medium transition-all ${
                  active
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 border border-gray-200 dark:border-slate-700 hover:bg-gray-100 dark:hover:bg-slate-700'
                }`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Visual Timeline when Stagger is active */}
      {staggerMinutes > 0 && (
        <div className="pt-1">
          <div className="flex flex-wrap items-center gap-2 py-2 px-2.5 rounded-xl bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-slate-700/80 text-xs">
            {selectedPlatforms.map((platform, index) => {
              const platformDelayMs = index * staggerMinutes * 60 * 1000;
              const targetTime = new Date(baseTime.getTime() + platformDelayMs);
              const timeString = targetTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              const platformInfo = platformIcons[platform] || {};
              const Icon = platformInfo.icon;

              return (
                <React.Fragment key={platform}>
                  {index > 0 && (
                    <div className="flex items-center text-slate-400 text-[10px] gap-0.5">
                      <FaArrowRight className="text-[8px]" />
                      <span className="font-mono text-[9px]">+{staggerMinutes}m</span>
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 py-1 px-2 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
                    {Icon && <Icon className={`text-xs ${platformInfo.color || ''}`} />}
                    <span className="capitalize font-semibold text-gray-800 dark:text-slate-200 text-[11px]">
                      {platform}
                    </span>
                    <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-mono font-medium">
                      {timeString}
                    </span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
