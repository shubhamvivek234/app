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

  it('aggregates actionable issues for Common Post across selected platforms', () => {
    const landscapeVideo = {
      id: 'job-common-landscape',
      type: 'video',
      width: 1920,
      height: 1080,
      size: 30 * 1024 * 1024,
      has_audio: false,
    };

    const actions = getMediaActionableIssues('common', {
      media: [landscapeVideo],
      postFormat: 'Post',
      selectedPlatforms: ['tiktok', 'twitter'],
    });

    expect(actions.length).toBeGreaterThan(0);
    expect(actions.some((a) => a.type === 'auto_fit_9_16')).toBe(true);
    expect(actions.some((a) => a.type === 'add_silent_audio')).toBe(true);
  });

  it('computes character limits and strictest platform for Common Post', () => {
    const { getCommonCharacterLimits } = require('./mediaValidation');
    const result = getCommonCharacterLimits(['twitter', 'linkedin', 'instagram']);
    expect(result.minLimit).toBe(280);
    expect(result.strictestPlatform).toBe('twitter');
    expect(result.platforms.find((p) => p.platform === 'twitter').shortLabel).toBe('X');
    expect(result.platforms.find((p) => p.platform === 'instagram').shortLabel).toBe('IG');
  });

  describe('validateCommonPostPlatform', () => {
    it('enforces character limit per platform', () => {
      const longText = 'A'.repeat(300);
      const twitterVal = validateCommonPostPlatform('twitter', { caption: longText });
      expect(twitterVal.errors.some((e) => e.includes('maximum is 280') || e.includes('Maximum is 280'))).toBe(true);

      const linkedinVal = validateCommonPostPlatform('linkedin', { caption: longText });
      expect(linkedinVal.errors.some((e) => e.includes('Maximum is'))).toBe(false);
    });

    it('enforces image count ceilings (e.g. 4 for Twitter, 10 for Instagram)', () => {
      const fiveImages = Array(5).fill(null).map((_, i) => ({
        type: 'image',
        width: 1000,
        height: 1000,
        size: 500 * 1024,
      }));

      const twitterVal = validateCommonPostPlatform('twitter', { media: fiveImages });
      expect(twitterVal.errors.some((e) => e.includes('supports up to 4 images'))).toBe(true);

      const igVal = validateCommonPostPlatform('instagram', { media: fiveImages });
      expect(igVal.errors.some((e) => e.includes('supports up to'))).toBe(false);
    });

    it('blocks mixed images and videos on platforms that do not support it', () => {
      const mixedMedia = [
        { type: 'image', width: 1000, height: 1000, size: 500 * 1024 },
        { type: 'video', width: 1920, height: 1080, size: 5 * 1024 * 1024 },
      ];

      const twitterVal = validateCommonPostPlatform('twitter', { media: mixedMedia });
      expect(twitterVal.errors.some((e) => e.includes('mixed image and video'))).toBe(true);

      const fbVal = validateCommonPostPlatform('facebook', { media: mixedMedia });
      expect(fbVal.errors.some((e) => e.includes('mixed image and video'))).toBe(false);
    });

    it('enforces video requirement on YouTube', () => {
      const textOnly = validateCommonPostPlatform('youtube', { caption: 'Hello World' });
      expect(textOnly.notes.some((n) => n.includes('Add media'))).toBe(true);

      const imageOnly = validateCommonPostPlatform('youtube', {
        caption: 'Hello World',
        media: [{ type: 'image', width: 1000, height: 1000, size: 500 * 1024 }],
      });
      expect(imageOnly.errors.some((e) => e.includes('does not support image uploads'))).toBe(true);
    });

    it('validates polls and prohibits poll + media attachments', () => {
      const pollWithMedia = {
        question: 'What is your favorite color?',
        options: ['Blue', 'Green'],
        duration: 'ONE_DAY',
      };
      const result = validateCommonPostPlatform('twitter', {
        poll: pollWithMedia,
        media: [{ type: 'image', width: 1000, height: 1000, size: 500 * 1024 }],
      });
      expect(result.errors.some((e) => e.includes('poll posts cannot include media'))).toBe(true);
    });
  });
});

