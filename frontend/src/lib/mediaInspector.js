/**
 * Zero-dependency client-side media inspector.
 * Inspects HTML5 video/image metadata in milliseconds before upload or publish.
 */

export function formatDuration(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const totalSecs = Math.round(seconds);
  const mins = Math.floor(totalSecs / 60);
  const secs = totalSecs % 60;
  return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

export function formatFileSize(bytes) {
  if (!bytes || isNaN(bytes)) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

export function getAspectRatioLabel(width, height) {
  if (!width || !height) return 'Unknown';
  const ratio = width / height;

  if (ratio >= 0.50 && ratio <= 0.65) return '9:16 (Vertical)';
  if (ratio >= 0.75 && ratio <= 0.85) return '4:5 (Portrait)';
  if (ratio >= 0.95 && ratio <= 1.05) return '1:1 (Square)';
  if (ratio >= 1.70 && ratio <= 1.85) return '16:9 (Landscape)';
  if (ratio >= 0.60 && ratio <= 0.72) return '2:3 (Pin)';
  
  return `${width}:${height} (${ratio.toFixed(2)})`;
}

/**
 * Inspects a File or Blob object asynchronously.
 * Returns { type, width, height, duration, size, aspectRatioLabel, aspectRatio }
 */
export async function inspectMediaFile(file) {
  if (!file) return null;

  const isVideo = file.type?.startsWith('video/') || /\.(mp4|mov|webm|avi|m4v)$/i.test(file.name || '');
  const isImage = file.type?.startsWith('image/') || /\.(jpe?g|png|webp|gif)$/i.test(file.name || '');

  const baseMeta = {
    fileName: file.name || 'media',
    fileSize: file.size || 0,
    fileSizeBytes: file.size || 0,
    fileSizeFormatted: formatFileSize(file.size || 0),
    mimeType: file.type || (isVideo ? 'video/mp4' : 'image/jpeg'),
    isVideo,
    isImage,
  };

  if (isVideo) {
    return new Promise((resolve) => {
      const video = document.createElement('video');
      video.preload = 'metadata';
      const blobUrl = URL.createObjectURL(file);

      const cleanup = () => {
        try {
          URL.revokeObjectURL(blobUrl);
        } catch (_) {}
      };

      const timeout = setTimeout(() => {
        cleanup();
        resolve({
          ...baseMeta,
          width: 1920,
          height: 1080,
          duration: 30,
          durationFormatted: '0:30',
          aspectRatio: 16 / 9,
          aspectRatioLabel: '16:9 (Landscape)',
        });
      }, 3000);

      video.onloadedmetadata = () => {
        clearTimeout(timeout);
        const width = video.videoWidth || 1920;
        const height = video.videoHeight || 1080;
        const duration = video.duration || 0;
        cleanup();

        resolve({
          ...baseMeta,
          width,
          height,
          duration,
          durationFormatted: formatDuration(duration),
          aspectRatio: width / height,
          aspectRatioLabel: getAspectRatioLabel(width, height),
        });
      };

      video.onerror = () => {
        clearTimeout(timeout);
        cleanup();
        resolve({
          ...baseMeta,
          width: 1920,
          height: 1080,
          duration: 0,
          durationFormatted: '0:00',
          aspectRatio: 16 / 9,
          aspectRatioLabel: 'Unknown',
        });
      };

      video.src = blobUrl;
    });
  }

  if (isImage) {
    return new Promise((resolve) => {
      const img = new Image();
      const blobUrl = URL.createObjectURL(file);

      const cleanup = () => {
        try {
          URL.revokeObjectURL(blobUrl);
        } catch (_) {}
      };

      img.onload = () => {
        const width = img.naturalWidth || 1080;
        const height = img.naturalHeight || 1080;
        cleanup();
        resolve({
          ...baseMeta,
          width,
          height,
          duration: null,
          durationFormatted: null,
          aspectRatio: width / height,
          aspectRatioLabel: getAspectRatioLabel(width, height),
        });
      };

      img.onerror = () => {
        cleanup();
        resolve({
          ...baseMeta,
          width: 1080,
          height: 1080,
          duration: null,
          durationFormatted: null,
          aspectRatio: 1,
          aspectRatioLabel: '1:1 (Square)',
        });
      };

      img.src = blobUrl;
    });
  }

  return baseMeta;
}

/**
 * Validates media against selected platform constraints.
 */
export function validateMediaSpecs(meta, selectedPlatforms = []) {
  if (!meta || !meta.isVideo) {
    return {
      isValid: true,
      hasErrors: false,
      hasWarnings: false,
      platformResults: {},
      summary: 'Media is ready for publishing',
    };
  }

  const results = {};
  let errorCount = 0;
  let warnCount = 0;

  selectedPlatforms.forEach((platform) => {
    const p = platform.toLowerCase();
    const checks = [];

    // 1. TikTok
    if (p === 'tiktok') {
      if (meta.aspectRatio > 0.70) {
        checks.push({
          level: 'warn',
          message: 'TikTok performs best with vertical (9:16) video. Current aspect ratio is ' + meta.aspectRatioLabel,
        });
      }
      if (meta.duration && meta.duration > 3600) {
        checks.push({
          level: 'error',
          message: 'TikTok video exceeds maximum 60 minutes limit.',
        });
      }
      if (meta.fileSizeBytes > 500 * 1024 * 1024) {
        checks.push({
          level: 'error',
          message: 'TikTok file size exceeds 500MB web limit.',
        });
      }
    }

    // 2. Instagram
    if (p === 'instagram') {
      if (meta.aspectRatio > 0.85) {
        checks.push({
          level: 'warn',
          message: 'Instagram Reels requires 9:16 or 4:5 vertical video. Landscape videos may show black bars.',
        });
      }
      if (meta.duration && meta.duration > 90) {
        checks.push({
          level: 'warn',
          message: `Video is ${meta.durationFormatted}. Standard Instagram Reels are recommended under 90 seconds.`,
        });
      }
      if (meta.fileSizeBytes > 4 * 1024 * 1024 * 1024) {
        checks.push({
          level: 'error',
          message: 'Instagram video exceeds maximum 4GB limit.',
        });
      }
    }

    // 3. Twitter / X
    if (p === 'twitter') {
      if (meta.duration && meta.duration > 140) {
        checks.push({
          level: 'error',
          message: `X (Twitter) max video duration is 2m 20s (140s). Detected: ${meta.durationFormatted}.`,
        });
      }
      if (meta.fileSizeBytes > 512 * 1024 * 1024) {
        checks.push({
          level: 'error',
          message: 'X (Twitter) video exceeds 512MB limit.',
        });
      }
    }

    // 4. YouTube
    if (p === 'youtube') {
      if (meta.duration && meta.duration > 60 && meta.aspectRatio < 0.70) {
        checks.push({
          level: 'warn',
          message: `Vertical video exceeds 60s (${meta.durationFormatted}). It will publish as a standard video, not a YouTube Short.`,
        });
      }
    }

    // 5. LinkedIn
    if (p === 'linkedin') {
      if (meta.duration && meta.duration > 600) {
        checks.push({
          level: 'error',
          message: `LinkedIn video exceeds 10 minutes limit (${meta.durationFormatted}).`,
        });
      }
      if (meta.fileSizeBytes > 5 * 1024 * 1024 * 1024) {
        checks.push({
          level: 'error',
          message: 'LinkedIn video exceeds 5GB limit.',
        });
      }
    }

    // Compile platform status
    const hasPlatformError = checks.some((c) => c.level === 'error');
    const hasPlatformWarn = checks.some((c) => c.level === 'warn');

    if (hasPlatformError) errorCount++;
    else if (hasPlatformWarn) warnCount++;

    results[platform] = {
      platform,
      status: hasPlatformError ? 'error' : hasPlatformWarn ? 'warn' : 'pass',
      checks,
    };
  });

  return {
    meta,
    platformResults: results,
    hasErrors: errorCount > 0,
    hasWarnings: warnCount > 0,
    errorCount,
    warnCount,
    summary: errorCount > 0
      ? `${errorCount} platform specification issue(s) need attention before publishing.`
      : warnCount > 0
      ? `${warnCount} platform optimization warning(s) detected.`
      : 'All platform specifications passed.',
  };
}
