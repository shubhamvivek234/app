/**
 * Client-side media validation against platform-specific limits.
 * Mirrors the server-side PLATFORM_LIMITS in media_pipeline/validation.py.
 *
 * Usage:
 *   const errors = validateMediaForPlatforms(file, ['instagram', 'youtube']);
 *   // errors is an array of { platform, label, error } objects, empty = OK
 */

// ── Plan upload limits (must match api/routes/upload.py _MAX_FILE_BYTES) ──────
export const PLAN_LIMITS = {
  starter: 500 * 1024 * 1024,                // 500 MB
  pro:     2  * 1024 * 1024 * 1024,          // 2 GB
  agency:  10 * 1024 * 1024 * 1024,          // 10 GB
};

// ── Per-platform constraints ───────────────────────────────────────────────────
export const PLATFORM_LIMITS = {
  instagram: {
    label:        'Instagram',
    maxVideoBytes: 650  * 1024 * 1024,        // 650 MB
    maxImageBytes: 8    * 1024 * 1024,        // 8 MB
    maxDuration:   3600,                       // 60 min
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime'],
    allowedImageTypes: ['image/jpeg', 'image/png'],
    notes: 'Reels: max 650 MB · 60 min · MP4/MOV only',
  },
  facebook: {
    label:        'Facebook',
    maxVideoBytes: 4    * 1024 * 1024 * 1024, // 4 GB
    maxImageBytes: 10   * 1024 * 1024,        // 10 MB
    maxDuration:   7200,                       // 2 hours
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    notes: 'Videos: max 4 GB · 2 hours',
  },
  youtube: {
    label:        'YouTube',
    maxVideoBytes: 256  * 1024 * 1024 * 1024, // 256 GB
    maxImageBytes: 2    * 1024 * 1024,        // 2 MB (thumbnail)
    maxDuration:   null,                       // no limit
    maxWidth:      null,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm', 'video/mpeg'],
    allowedImageTypes: ['image/jpeg', 'image/png'],
    notes: 'Videos: max 256 GB — no duration limit',
  },
  twitter: {
    label:        'Twitter / X',
    maxVideoBytes: 512  * 1024 * 1024,        // 512 MB
    maxImageBytes: 5    * 1024 * 1024,        // 5 MB
    maxDuration:   140,                        // 2 min 20 sec
    maxWidth:      1280,
    allowedVideoTypes: ['video/mp4', 'video/quicktime'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    notes: 'Videos: max 512 MB · 2m20s · MP4/MOV',
  },
  linkedin: {
    label:        'LinkedIn',
    maxVideoBytes: 5    * 1024 * 1024 * 1024, // 5 GB
    maxImageBytes: 5    * 1024 * 1024,        // 5 MB
    maxDuration:   600,                        // 10 min
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif'],
    notes: 'Videos: max 5 GB · 10 min',
  },
  tiktok: {
    label:        'TikTok',
    maxVideoBytes: 4    * 1024 * 1024 * 1024, // 4 GB
    maxImageBytes: 20   * 1024 * 1024,        // 20 MB
    maxDuration:   600,                        // 10 min
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/webm'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp'],
    notes: 'Videos: max 4 GB · 10 min · portrait (9:16) recommended',
  },
  pinterest: {
    label:        'Pinterest',
    maxVideoBytes: 2    * 1024 * 1024 * 1024, // 2 GB
    maxImageBytes: 20   * 1024 * 1024,        // 20 MB
    maxDuration:   900,                        // 15 min
    maxWidth:      null,
    allowedVideoTypes: ['video/mp4'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
    notes: 'Videos: max 2 GB · 15 min · MP4 only',
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

export function formatBytes(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024)        return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

/**
 * Validate a single File object against a list of platform identifiers.
 *
 * Returns an array of violation objects:
 *   [{ platform, label, field, error }]
 *
 * Empty array = file is acceptable for all given platforms.
 */
export function validateMediaForPlatforms(file, platforms = []) {
  if (!file) return [];

  const isVideo = file.type.startsWith('video/');
  const isImage = file.type.startsWith('image/');

  if (!isVideo && !isImage) {
    return [{ platform: 'all', label: 'All platforms', field: 'type', error: `Unsupported file type: ${file.type}` }];
  }

  const violations = [];

  for (const platformId of platforms) {
    const limits = PLATFORM_LIMITS[platformId];
    if (!limits) continue;

    if (isVideo) {
      // Size
      if (limits.maxVideoBytes && file.size > limits.maxVideoBytes) {
        violations.push({
          platform: platformId,
          label:    limits.label,
          field:    'size',
          error:    `File is ${formatBytes(file.size)} — ${limits.label} allows max ${formatBytes(limits.maxVideoBytes)} for videos`,
        });
      }
      // MIME type
      if (limits.allowedVideoTypes && !limits.allowedVideoTypes.includes(file.type)) {
        const allowed = limits.allowedVideoTypes.map(t => t.split('/')[1].toUpperCase()).join(', ');
        violations.push({
          platform: platformId,
          label:    limits.label,
          field:    'type',
          error:    `${limits.label} only accepts ${allowed} videos — got ${file.type.split('/')[1].toUpperCase()}`,
        });
      }
    }

    if (isImage) {
      // Size
      if (limits.maxImageBytes && file.size > limits.maxImageBytes) {
        violations.push({
          platform: platformId,
          label:    limits.label,
          field:    'size',
          error:    `File is ${formatBytes(file.size)} — ${limits.label} allows max ${formatBytes(limits.maxImageBytes)} for images`,
        });
      }
      // MIME type
      if (limits.allowedImageTypes && !limits.allowedImageTypes.includes(file.type)) {
        const allowed = limits.allowedImageTypes.map(t => t.split('/')[1].toUpperCase()).join(', ');
        violations.push({
          platform: platformId,
          label:    limits.label,
          field:    'type',
          error:    `${limits.label} only accepts ${allowed} images — got ${file.type.split('/')[1].toUpperCase()}`,
        });
      }
    }
  }

  return violations;
}

/**
 * Validate a file against a user's plan upload limit.
 * Returns null if OK, or an error string if exceeded.
 */
export function validatePlanLimit(file, plan = 'starter') {
  const max = PLAN_LIMITS[plan] ?? PLAN_LIMITS.starter;
  if (file.size > max) {
    return `File is ${formatBytes(file.size)} — your ${plan} plan allows max ${formatBytes(max)} per file. Upgrade for larger uploads.`;
  }
  return null;
}

/**
 * Get a summary string of what a platform supports.
 */
export function getPlatformLimitSummary(platformId) {
  const limits = PLATFORM_LIMITS[platformId];
  if (!limits) return '';
  return limits.notes || '';
}
