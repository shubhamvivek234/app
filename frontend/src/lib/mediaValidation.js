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
    maxVideoBytes: 4    * 1024 * 1024 * 1024, // 4 GB (Reels — verified 2026)
    maxImageBytes: 30   * 1024 * 1024,        // 30 MB
    maxDuration:   3600,                       // 60 min
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime'],
    allowedImageTypes: ['image/jpeg', 'image/png'],
    notes: 'Reels: max 4 GB · 60 min · MP4/MOV only · 4:5 portrait preferred',
  },
  facebook: {
    label:        'Facebook',
    maxVideoBytes: 10   * 1024 * 1024 * 1024, // 10 GB (feed); Reels/Stories: 4 GB
    maxImageBytes: 30   * 1024 * 1024,        // 30 MB
    maxDuration:   14400,                      // 4 hours (feed)
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    notes: 'Feed: max 10 GB · 4 hrs · Reels/Stories: max 4 GB',
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
    maxVideoBytes: 500  * 1024 * 1024,        // 500 MB (web — verified 2026; iOS: 287.6 MB, Android: 72 MB)
    maxImageBytes: 20   * 1024 * 1024,        // 20 MB
    maxDuration:   3600,                       // 60 min
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/webm'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp'],
    notes: 'Videos: max 500 MB (web) · 60 min · 9:16 mandatory',
  },
  pinterest: {
    label:        'Pinterest',
    maxVideoBytes: 2    * 1024 * 1024 * 1024, // 2 GB
    maxImageBytes: 20   * 1024 * 1024,        // 20 MB
    maxDuration:   900,                        // 15 min
    maxWidth:      null,
    allowedVideoTypes: ['video/mp4', 'video/quicktime', 'video/x-m4v'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
    notes: 'Videos: max 2 GB · 15 min · MP4/MOV/M4V · H.264 or H.265 · 2:3 preferred',
  },
  threads: {
    label:        'Threads',
    maxVideoBytes: 1024 * 1024 * 1024,
    maxImageBytes: 8    * 1024 * 1024,
    maxDuration:   300,
    maxWidth:      1920,
    allowedVideoTypes: ['video/mp4', 'video/quicktime'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp'],
    notes: 'Publishing adapter not configured in this workspace yet.',
  },
  bluesky: {
    label:        'Bluesky',
    maxVideoBytes: 100  * 1024 * 1024,
    maxImageBytes: 8    * 1024 * 1024,
    maxDuration:   60,
    maxWidth:      2000,
    allowedVideoTypes: ['video/mp4'],
    allowedImageTypes: ['image/jpeg', 'image/png', 'image/webp'],
    notes: 'Publishing adapter not configured in this workspace yet.',
  },
};

export const COMMON_POST_UNSUPPORTED = {
  reddit: 'This platform is not supported in Common Post yet. Use platform-specific composition.',
  discord: 'This platform is not supported in Common Post yet. Use platform-specific composition.',
  mastodon: 'This platform is not supported in Common Post yet. Use platform-specific composition.',
  snapchat: 'This platform is not supported in Common Post yet. Use platform-specific composition.',
  threads: 'Threads publishing is not configured in this workspace yet. Remove it or use platform-specific composition.',
  bluesky: 'Bluesky publishing is not configured in this workspace yet. Remove it or use platform-specific composition.',
  pinterest: 'Pinterest publishing is not configured in this workspace yet. Remove it or use platform-specific composition.',
};

const PLATFORM_TEXT_LIMITS = {
  facebook: 63206,
  instagram: 2200,
  twitter: 280,
  linkedin: 3000,
  youtube: 5000,
  tiktok: 2200,
  pinterest: 500,
  threads: 500,
  bluesky: 300,
};

const PLATFORM_ASPECT_RULES = {
  instagram: {
    image: {
      Post: { ratio: 4 / 5, label: '4:5' },
      Reel: { ratio: 9 / 16, label: '9:16' },
      Story: { ratio: 9 / 16, label: '9:16' },
    },
    video: {
      Post: { ratio: 4 / 5, label: '4:5' },
      Reel: { ratio: 9 / 16, label: '9:16' },
      Story: { ratio: 9 / 16, label: '9:16' },
    },
  },
  facebook: {
    image: { ratio: 1, label: '1:1' },
    video: { ratio: 1, label: '1:1' },
  },
  linkedin: {
    image: { ratio: 1.91, label: '1.91:1' },
    video: { ratio: 1.91, label: '1.91:1' },
  },
  youtube: {
    video: { ratio: 16 / 9, label: '16:9' },
  },
  tiktok: {
    video: { ratio: 9 / 16, label: '9:16' },
  },
};

const ASPECT_RATIO_TOLERANCE = 0.1;

const COMMON_POST_RULES = {
  facebook: {
    allowTextOnly: true,
    maxImages: 1,
    maxVideos: 1,
    allowMixed: false,
  },
  instagram: {
    allowTextOnly: false,
    maxImages: 1,
    maxVideos: 1,
    allowMixed: false,
  },
  twitter: {
    allowTextOnly: true,
    maxImages: 0,
    maxVideos: 0,
    allowMixed: false,
    unsupportedMediaMessage: 'Twitter/X media publishing is not wired in this workspace yet. Use text-only or platform-specific composition.',
  },
  linkedin: {
    allowTextOnly: true,
    maxImages: 1,
    maxVideos: 1,
    allowMixed: false,
  },
  youtube: {
    allowTextOnly: false,
    maxImages: 0,
    maxVideos: 1,
    exactVideoCount: 1,
    allowMixed: false,
  },
  tiktok: {
    allowTextOnly: false,
    maxImages: 0,
    maxVideos: 1,
    exactVideoCount: 1,
    allowMixed: false,
  },
};

const getAspectRule = (platformId, mediaType, postFormat) => {
  const platformRule = PLATFORM_ASPECT_RULES[platformId];
  if (!platformRule) return null;
  const typeRule = platformRule[mediaType];
  if (!typeRule) return null;
  if (typeRule[postFormat]) return typeRule[postFormat];
  return typeRule;
};

const isAspectRatioOutOfRange = (ratio, targetRatio) => {
  if (!ratio || !targetRatio) return false;
  return Math.abs(ratio - targetRatio) / targetRatio > ASPECT_RATIO_TOLERANCE;
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

export function validateCommonPostPlatform(platformId, {
  caption = '',
  media = [],
  postFormat = 'Post',
} = {}) {
  const errors = [];
  const notes = [];

  if (COMMON_POST_UNSUPPORTED[platformId]) {
    errors.push(COMMON_POST_UNSUPPORTED[platformId]);
    return { errors, notes };
  }

  const rule = COMMON_POST_RULES[platformId];
  const limit = PLATFORM_LIMITS[platformId];
  if (!rule || !limit) {
    errors.push('This platform is not supported in Common Post yet. Use platform-specific composition.');
    return { errors, notes };
  }

  const normalizedMedia = Array.isArray(media) ? media : [];
  const images = normalizedMedia.filter((item) => item?.type === 'image');
  const videos = normalizedMedia.filter((item) => item?.type === 'video');
  const hasMedia = normalizedMedia.length > 0;
  const hasCaption = Boolean((caption || '').trim());

  if (!hasMedia) {
    if (!rule.allowTextOnly) {
      notes.push(`Add media in Common Post or upload it directly in ${limit.label} before publishing there.`);
    }
    if (!hasCaption) {
      notes.push(`Add a caption, media, or both when you're ready to publish to ${limit.label}.`);
    }
  }

  if (hasMedia && rule.exactVideoCount && videos.length !== rule.exactVideoCount) {
    errors.push(`${limit.label} requires exactly ${rule.exactVideoCount} video in Common Post.`);
  }

  if (hasMedia) {
    if (rule.maxImages === 0 && images.length > 0) {
      errors.push(`${limit.label} does not support image uploads in Common Post.`);
    } else if (typeof rule.maxImages === 'number' && images.length > rule.maxImages) {
      errors.push(`${limit.label} supports up to ${rule.maxImages} image${rule.maxImages !== 1 ? 's' : ''}. You uploaded ${images.length}.`);
    }

    if (rule.maxVideos === 0 && videos.length > 0) {
      errors.push(`${limit.label} does not support video uploads in Common Post.`);
    } else if (typeof rule.maxVideos === 'number' && videos.length > rule.maxVideos) {
      errors.push(`${limit.label} supports up to ${rule.maxVideos} video${rule.maxVideos !== 1 ? 's' : ''}. You uploaded ${videos.length}.`);
    }

    if (!rule.allowMixed && images.length > 0 && videos.length > 0) {
      errors.push(`${limit.label} does not support mixed image and video media in Common Post.`);
    }
  }

  if (rule.unsupportedMediaMessage && hasMedia) {
    errors.push(rule.unsupportedMediaMessage);
  }

  const maxChars = PLATFORM_TEXT_LIMITS[platformId];
  if (maxChars && caption.length > maxChars) {
    errors.push(`${limit.label} caption is ${caption.length} characters. Maximum is ${maxChars}.`);
  }

  normalizedMedia.forEach((item, index) => {
    if (!item) return;

    const mediaLabel = `${item.type === 'video' ? 'Video' : 'Image'} ${index + 1}`;
    const mimeType = item.mimeType || item.file?.type || '';
    const sizeBytes = item.size || item.file?.size || 0;
    const width = item.width || 0;
    const height = item.height || 0;
    const duration = item.duration || 0;

    if (item.type === 'image') {
      if (limit.maxImageBytes && sizeBytes > limit.maxImageBytes) {
        errors.push(`${mediaLabel} is ${formatBytes(sizeBytes)}. ${limit.label} allows up to ${formatBytes(limit.maxImageBytes)} per image.`);
      }
      if (mimeType && limit.allowedImageTypes && !limit.allowedImageTypes.includes(mimeType)) {
        errors.push(`${mediaLabel} uses ${mimeType}. ${limit.label} accepts ${limit.allowedImageTypes.map((type) => type.split('/')[1].toUpperCase()).join(', ')} images.`);
      }
      const aspectRule = getAspectRule(platformId, 'image', postFormat);
      const actualRatio = width > 0 && height > 0 ? width / height : 0;
      if (aspectRule && actualRatio && isAspectRatioOutOfRange(actualRatio, aspectRule.ratio)) {
        errors.push(`Crop image ${index + 1} to ${aspectRule.label} for ${limit.label} before posting.`);
      }
    }

    if (item.type === 'video') {
      if (limit.maxVideoBytes && sizeBytes > limit.maxVideoBytes) {
        errors.push(`${mediaLabel} is ${formatBytes(sizeBytes)}. ${limit.label} allows up to ${formatBytes(limit.maxVideoBytes)} per video.`);
      }
      if (mimeType && limit.allowedVideoTypes && !limit.allowedVideoTypes.includes(mimeType)) {
        errors.push(`${mediaLabel} uses ${mimeType}. ${limit.label} accepts ${limit.allowedVideoTypes.map((type) => type.split('/')[1].toUpperCase()).join(', ')} videos.`);
      }
      if (limit.maxDuration && duration && duration > limit.maxDuration) {
        errors.push(`${mediaLabel} is ${Math.ceil(duration)} seconds. ${limit.label} allows up to ${limit.maxDuration} seconds.`);
      }
      const aspectRule = getAspectRule(platformId, 'video', postFormat);
      const actualRatio = width > 0 && height > 0 ? width / height : 0;
      if (aspectRule && actualRatio && isAspectRatioOutOfRange(actualRatio, aspectRule.ratio)) {
        errors.push(`Adjust video ${index + 1} to ${aspectRule.label} for ${limit.label} before posting.`);
      }
    }
  });

  if (limit.notes) {
    notes.push(limit.notes);
  }

  return { errors, notes };
}

export function buildCommonPostValidation({
  platforms = [],
  captionByPlatform = {},
  mediaByPlatform = {},
  postFormat = 'Post',
} = {}) {
  return platforms.reduce((acc, platformId) => {
    acc[platformId] = validateCommonPostPlatform(platformId, {
      caption: captionByPlatform[platformId] || '',
      media: mediaByPlatform[platformId] || [],
      postFormat,
    });
    return acc;
  }, {});
}
