import React, { useState } from 'react';
import {
  FaCheckCircle,
  FaExclamationTriangle,
  FaTimesCircle,
  FaVideo,
  FaChevronDown,
  FaChevronUp,
  FaInfoCircle
} from 'react-icons/fa';

export default function VideoValidatorBadge({ validationResult, selectedPlatforms = [] }) {
  const [expanded, setExpanded] = useState(false);

  if (!validationResult || !validationResult.meta || !validationResult.meta.isVideo) {
    return null;
  }

  const { meta, platformResults, hasErrors, hasWarnings, summary } = validationResult;

  const badgeColor = hasErrors
    ? 'bg-rose-50 border-rose-200 text-rose-700 dark:bg-rose-950/40 dark:border-rose-800 dark:text-rose-300'
    : hasWarnings
    ? 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-300'
    : 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-300';

  const BadgeIcon = hasErrors ? FaTimesCircle : hasWarnings ? FaExclamationTriangle : FaCheckCircle;

  return (
    <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs overflow-hidden transition-all">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors text-left"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <BadgeIcon className={`text-base shrink-0 ${hasErrors ? 'text-rose-500' : hasWarnings ? 'text-amber-500' : 'text-emerald-500'}`} />
          <div className="min-w-0">
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 block truncate">
              Video Specs Pre-Check: {meta.aspectRatioLabel} • {meta.durationFormatted || '0:00'}
            </span>
            <span className="text-[11px] text-slate-500 dark:text-slate-400 block truncate">
              {summary}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${badgeColor}`}>
            {hasErrors ? 'Action Needed' : hasWarnings ? 'Notice' : 'Pass'}
          </span>
          {expanded ? <FaChevronUp className="text-xs text-slate-400" /> : <FaChevronDown className="text-xs text-slate-400" />}
        </div>
      </button>

      {expanded && (
        <div className="p-3.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-3 text-xs">
          {/* Metadata quick row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Aspect Ratio</span>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-0.5 block">{meta.aspectRatioLabel}</span>
            </div>
            <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Duration</span>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-0.5 block">{meta.durationFormatted || '0s'}</span>
            </div>
            <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Resolution</span>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-0.5 block">{meta.width} × {meta.height}</span>
            </div>
            <div className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">File Size</span>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-0.5 block">{meta.fileSizeFormatted}</span>
            </div>
          </div>

          {/* Platform breakdown */}
          <div className="space-y-1.5 pt-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 block">
              Platform Readiness Matrix
            </span>
            {selectedPlatforms.length === 0 ? (
              <p className="text-[11px] text-slate-400 italic">No platforms selected yet.</p>
            ) : (
              selectedPlatforms.map((platform) => {
                const res = platformResults[platform] || { status: 'pass', checks: [] };
                return (
                  <div
                    key={platform}
                    className="flex items-start justify-between p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/70 dark:border-slate-800/80 gap-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="capitalize font-semibold text-slate-800 dark:text-slate-200">
                        {platform}
                      </span>
                      {res.status === 'pass' && (
                        <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded">
                          ✓ Compatible
                        </span>
                      )}
                      {res.status === 'warn' && (
                        <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 px-1.5 py-0.5 rounded">
                          ⚠️ Optimal ratio notice
                        </span>
                      )}
                      {res.status === 'error' && (
                        <span className="text-[10px] font-bold text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 px-1.5 py-0.5 rounded">
                          ⛔ Format mismatch
                        </span>
                      )}
                    </div>
                    {res.checks.length > 0 && (
                      <div className="text-[11px] text-right text-slate-600 dark:text-slate-300">
                        {res.checks.map((c, i) => (
                          <div key={i} className={c.level === 'error' ? 'text-rose-600 dark:text-rose-400 font-medium' : 'text-amber-600 dark:text-amber-400'}>
                            {c.message}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
