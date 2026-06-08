import {
  formatScheduledCompactDateTime,
  formatScheduledDateTime,
  formatScheduledTime,
  getPostScheduledTimeZone,
  getScheduledDateKey,
} from './scheduledTime';

describe('scheduledTime helpers', () => {
  it('formats scheduled times using the explicit post timezone', () => {
    const value = '2026-06-08T08:30:00.000Z';

    expect(formatScheduledTime(value, 'Asia/Kolkata')).toBe('2:00 PM');
    expect(getScheduledDateKey(value, 'Asia/Kolkata')).toBe('2026-06-08');
    expect(formatScheduledCompactDateTime(value, 'Asia/Kolkata')).toContain('2:00 PM');
    expect(formatScheduledDateTime(value, 'Asia/Kolkata')).toContain('2:00 PM');
  });

  it('uses timezone only for posts that explicitly persisted it', () => {
    expect(getPostScheduledTimeZone({
      timezone: 'Asia/Kolkata',
      scheduled_timezone_explicit: true,
    })).toBe('Asia/Kolkata');

    expect(getPostScheduledTimeZone({
      timezone: 'UTC',
      scheduled_timezone_explicit: false,
    })).toBeNull();
  });
});
