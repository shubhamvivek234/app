/**
 * 17.6 — Pre-upload status timeline for scheduled video posts.
 *
 * Displays a live status timeline on the post card showing exactly what is
 * happening with the pre-upload process so users never ask "why is my post late?"
 *
 * Example output:
 *   ✅ 11:42 AM — Video uploaded to Instagram servers
 *   ✅ 11:44 AM — Instagram finished processing your video
 *   ⏳ 12:00 PM — Post goes live (scheduled — 9 minutes away)
 */
import React, { useEffect, useState } from 'react';

// ── helpers ────────────────────────────────────────────────────────────────────

const fmtTime = (isoOrDate) => {
  if (!isoOrDate) return '';
  try {
    return new Date(isoOrDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const minutesAway = (isoDate) => {
  if (!isoDate) return null;
  const diff = Math.round((new Date(isoDate) - Date.now()) / 60000);
  if (diff <= 0) return null;
  return diff === 1 ? '1 minute away' : `${diff} minutes away`;
};

// ── Step icons ─────────────────────────────────────────────────────────────────
const CheckIcon = () => (
  <span className="flex-shrink-0 w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center">
    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 10 8" fill="none">
      <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  </span>
);

const SpinnerIcon = () => (
  <span className="flex-shrink-0 w-4 h-4 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />
);

const ClockIcon = () => (
  <span className="flex-shrink-0 w-4 h-4 rounded-full border-2 border-gray-300 flex items-center justify-center">
    <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
  </span>
);

const ErrorIcon = () => (
  <span className="flex-shrink-0 w-4 h-4 rounded-full bg-red-500 flex items-center justify-center">
    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 10 10" fill="none">
      <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  </span>
);

// ── Build timeline steps from post fields ─────────────────────────────────────

function buildSteps(post) {
  const {
    pre_upload_status,
    pre_upload_start_time,
    pre_upload_started_at,
    pre_upload_completed_at,
    pre_upload_error,
    scheduled_time,
    platforms = [],
    published_at,
    status,
  } = post;

  const videoPlats = platforms.filter((p) => ['instagram', 'youtube'].includes(p));
  const platLabel = videoPlats.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(' & ');

  const steps = [];

  // Step 1 — Upload started
  const uploadStarted = pre_upload_started_at || pre_upload_start_time;
  const uploadDone =
    pre_upload_status === 'ready' ||
    pre_upload_status === 'failed' ||
    pre_upload_status === 'timeout' ||
    status === 'published';

  if (uploadStarted) {
    steps.push({
      time: fmtTime(uploadStarted),
      label: `Video uploading to ${platLabel || 'platform'} servers`,
      state: uploadDone ? 'done' : pre_upload_status === 'uploading' ? 'active' : 'pending',
    });
  } else if (pre_upload_status === 'pending' || !pre_upload_status) {
    steps.push({
      time: fmtTime(pre_upload_start_time),
      label: `Upload to ${platLabel || 'platform'} starts soon`,
      state: 'pending',
    });
  }

  // Step 2 — Processing complete
  if (pre_upload_completed_at) {
    steps.push({
      time: fmtTime(pre_upload_completed_at),
      label: `${platLabel || 'Platform'} finished processing your video`,
      state: 'done',
    });
  } else if (pre_upload_status === 'uploading') {
    steps.push({
      time: '',
      label: `Waiting for ${platLabel || 'platform'} to finish processing…`,
      state: 'active',
    });
  } else if (pre_upload_status === 'ready') {
    steps.push({
      time: fmtTime(pre_upload_completed_at || scheduled_time),
      label: `${platLabel || 'Platform'} finished processing — ready to go live`,
      state: 'done',
    });
  }

  // Step 3 — Error or timeout
  if (pre_upload_status === 'failed' || pre_upload_status === 'timeout') {
    steps.push({
      time: '',
      label: pre_upload_error || 'Pre-upload failed — post could not be published on time',
      state: 'error',
    });
    return steps;
  }

  // Step 4 — Goes live
  if (status === 'published') {
    steps.push({
      time: fmtTime(published_at || scheduled_time),
      label: `Posted to ${platLabel || 'platform'} on time`,
      state: 'done',
    });
  } else {
    const away = minutesAway(scheduled_time);
    steps.push({
      time: fmtTime(scheduled_time),
      label: away
        ? `Post goes live (scheduled — ${away})`
        : `Post goes live at scheduled time`,
      state: 'pending',
    });
  }

  return steps;
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Props:
 *   post — the full post document from the API
 *   compact — if true, renders a minimal inline version (no heading)
 */
const PreUploadTimeline = ({ post, compact = false }) => {
  const [now, setNow] = useState(Date.now());

  // Re-render every 30s so "X minutes away" countdown stays current
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  // Only render for video posts with two-phase platforms
  const isVideoPost = ['video', 'reel', 'story'].includes(post.post_type);
  const hasPhased = (post.platforms || []).some((p) => ['instagram', 'youtube'].includes(p));
  if (!isVideoPost || !hasPhased) return null;

  // Don't show timeline for posts that have no pre_upload activity yet and
  // are still far away (nothing meaningful to display)
  const hasActivity =
    post.pre_upload_status ||
    post.pre_upload_start_time ||
    post.pre_upload_started_at;
  if (!hasActivity && post.status === 'scheduled') return null;

  const steps = buildSteps(post);
  if (!steps.length) return null;

  const stateIcon = {
    done: <CheckIcon />,
    active: <SpinnerIcon />,
    pending: <ClockIcon />,
    error: <ErrorIcon />,
  };

  const stateText = {
    done: 'text-emerald-700',
    active: 'text-blue-700',
    pending: 'text-gray-400',
    error: 'text-red-600',
  };

  return (
    <div className={`${compact ? '' : 'px-4 pb-3 pt-2'} border-t border-gray-100 bg-gray-50/60`}>
      {!compact && (
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">
          Upload timeline
        </p>
      )}
      <ol className="space-y-1.5">
        {steps.map((step, i) => (
          <li key={i} className="flex items-center gap-2">
            {stateIcon[step.state] || <ClockIcon />}
            <span className={`text-[11px] leading-tight ${stateText[step.state] || 'text-gray-500'}`}>
              {step.time && (
                <span className="font-semibold mr-1">{step.time}</span>
              )}
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
};

export default PreUploadTimeline;
