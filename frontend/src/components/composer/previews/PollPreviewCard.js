import React from 'react';

const DURATION_LABELS = {
  ONE_DAY: '1 day',
  THREE_DAYS: '3 days',
  SEVEN_DAYS: '7 days',
  FOURTEEN_DAYS: '14 days',
};

const PollPreviewCard = ({ poll, platformLabel = 'Poll' }) => {
  if (!poll?.question) return null;

  const options = Array.isArray(poll.options) ? poll.options.filter(Boolean).slice(0, 4) : [];
  if (options.length < 2) return null;

  return (
    <div className="mt-3 rounded-2xl border border-gray-200 bg-white/90 p-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
          {platformLabel} Poll
        </span>
        <span className="text-[11px] text-gray-400">
          {DURATION_LABELS[poll.duration] || 'Poll'}
        </span>
      </div>

      <p className="mt-2 text-sm font-semibold text-gray-900">{poll.question}</p>

      <div className="mt-3 space-y-2">
        {options.map((option, index) => (
          <div
            key={`${option}-${index}`}
            className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700"
          >
            <div className="h-4 w-4 rounded-full border border-gray-300 bg-white" />
            <span className="truncate">{option}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default PollPreviewCard;
