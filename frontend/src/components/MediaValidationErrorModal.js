/**
 * Modal shown when an uploaded file violates one or more platform limits.
 * Displays per-platform errors and the file info clearly.
 */
import React from 'react';
import { FaTimes, FaExclamationTriangle, FaInfoCircle } from 'react-icons/fa';
import { formatBytes, PLATFORM_LIMITS } from '@/lib/mediaValidation';

const PLATFORM_ICONS = {
  instagram: '📸',
  facebook:  '👥',
  youtube:   '▶️',
  twitter:   '🐦',
  linkedin:  '💼',
  tiktok:    '🎵',
  pinterest: '📌',
};

/**
 * Props:
 *   file         – File object being rejected
 *   violations   – array of { platform, label, field, error }
 *   platforms    – all selected platforms (to show "OK" ones too)
 *   onClose      – called when user dismisses
 *   onContinue   – if provided, user can choose to upload anyway (warnings only)
 */
const MediaValidationErrorModal = ({ file, violations = [], platforms = [], onClose, onContinue }) => {
  if (!file) return null;

  const isVideo = file.type.startsWith('video/');
  const violatingPlatforms = new Set(violations.map(v => v.platform));
  const okPlatforms = platforms.filter(p => !violatingPlatforms.has(p) && PLATFORM_LIMITS[p]);

  // Group violations by platform for cleaner display
  const byPlatform = {};
  for (const v of violations) {
    if (!byPlatform[v.platform]) byPlatform[v.platform] = [];
    byPlatform[v.platform].push(v);
  }

  // Size-only violations can suggest we still upload to compatible platforms
  const canContinueWithSome = okPlatforms.length > 0 && onContinue;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-start gap-3 p-5 border-b border-gray-100">
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
            <FaExclamationTriangle className="text-red-500 text-lg" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-gray-900">
              File not compatible with {violatingPlatforms.size === 1 ? 'a platform' : 'some platforms'}
            </h2>
            <p className="text-xs text-gray-500 mt-0.5 truncate">
              {file.name} · {formatBytes(file.size)} · {isVideo ? 'Video' : 'Image'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 w-7 h-7 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors"
          >
            <FaTimes className="text-sm" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-5 space-y-3">

          {/* Violations */}
          {Object.entries(byPlatform).map(([platformId, pvList]) => (
            <div key={platformId} className="rounded-xl border border-red-100 bg-red-50 p-3">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-base leading-none">{PLATFORM_ICONS[platformId] || '📱'}</span>
                <span className="text-sm font-semibold text-red-800">
                  {PLATFORM_LIMITS[platformId]?.label || platformId}
                </span>
              </div>
              <ul className="space-y-1">
                {pvList.map((v, i) => (
                  <li key={i} className="text-xs text-red-700 flex items-start gap-1.5">
                    <span className="mt-0.5 flex-shrink-0">•</span>
                    <span>{v.error}</span>
                  </li>
                ))}
              </ul>
              {PLATFORM_LIMITS[platformId]?.notes && (
                <p className="mt-1.5 text-xs text-red-500 italic">
                  {PLATFORM_LIMITS[platformId].notes}
                </p>
              )}
            </div>
          ))}

          {/* OK platforms */}
          {okPlatforms.length > 0 && (
            <div className="rounded-xl border border-green-100 bg-green-50 p-3">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-sm">✅</span>
                <span className="text-sm font-semibold text-green-800">Compatible platforms</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {okPlatforms.map(p => (
                  <span
                    key={p}
                    className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 rounded-full px-2 py-0.5 font-medium"
                  >
                    {PLATFORM_ICONS[p]} {PLATFORM_LIMITS[p]?.label || p}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Tip */}
          <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 flex gap-2">
            <FaInfoCircle className="text-blue-400 flex-shrink-0 mt-0.5 text-sm" />
            <p className="text-xs text-blue-700">
              {isVideo
                ? 'To post to all platforms, reduce the video file size or duration before uploading. YouTube accepts files up to 256 GB.'
                : 'To post to all platforms, reduce the image file size or convert to a compatible format.'}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 flex gap-2 justify-end">
          {canContinueWithSome ? (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Choose different file
              </button>
              <button
                onClick={onContinue}
                className="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
              >
                Upload for compatible platforms only
              </button>
            </>
          ) : (
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-semibold bg-gray-800 hover:bg-gray-900 text-white rounded-lg transition-colors"
            >
              Choose a different file
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default MediaValidationErrorModal;
