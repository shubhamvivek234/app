import {
  PLATFORM_LIMITS,
  validateMediaForPlatforms,
  validateCommonPostPlatform,
  getMediaActionableIssues,
} from './mediaValidation';

describe('mediaValidation', () => {
  it('has consistent limits for major platforms', () => {
    expect(PLATFORM_LIMITS.instagram.maxVideoBytes).toBe(4 * 1024 * 1024 * 1024);
    expect(PLATFORM_LIMITS.twitter.maxImageBytes).toBe(5 * 1024 * 1024);
    expect(PLATFORM_LIMITS.tiktok.maxVideoBytes).toBe(500 * 1024 * 1024);
  });

  it('flags oversized images on Twitter', () => {
    const file = {
      type: 'image/jpeg',
      size: 8 * 1024 * 1024, // 8 MB
    };
    const violations = validateMediaForPlatforms(file, ['twitter']);
    expect(violations.length).toBe(1);
    expect(violations[0].platform).toBe('twitter');
    expect(violations[0].field).toBe('size');
  });

  it('detects actionable issues for 9:16 vertical orientation on TikTok', () => {
    const landscapeVideo = {
      id: 'job-landscape-1',
      type: 'video',
      width: 1920,
      height: 1080,
      size: 50 * 1024 * 1024,
      has_audio: true,
    };

    const actions = getMediaActionableIssues('tiktok', {
      media: [landscapeVideo],
      postFormat: 'Post',
    });

    expect(actions.length).toBe(1);
    expect(actions[0].type).toBe('auto_fit_9_16');
    expect(actions[0].mediaIndex).toBe(0);
    expect(actions[0].mediaId).toBe('job-landscape-1');
  });

  it('detects actionable issues for oversized media on Twitter', () => {
    const largeImage = {
      id: 'job-large-img',
      type: 'image',
      width: 2000,
      height: 2000,
      size: 9 * 1024 * 1024, // 9 MB (Twitter limit is 5MB)
    };

    const actions = getMediaActionableIssues('twitter', {
      media: [largeImage],
      postFormat: 'Post',
    });

    expect(actions.length).toBe(1);
    expect(actions[0].type).toBe('auto_compress');
    expect(actions[0].maxBytes).toBe(5 * 1024 * 1024);
  });

  it('detects silent video on TikTok and suggests adding silent audio', () => {
    const silentVerticalVideo = {
      id: 'job-silent-video',
      type: 'video',
      width: 1080,
      height: 1920,
      size: 20 * 1024 * 1024,
      has_audio: false,
    };

    const actions = getMediaActionableIssues('tiktok', {
      media: [silentVerticalVideo],
      postFormat: 'Post',
    });

    expect(actions.some((a) => a.type === 'add_silent_audio')).toBe(true);
  });
});
