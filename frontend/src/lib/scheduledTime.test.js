import {
  convertWallClockToUtcIso,
  formatScheduledCompactDateTime,
  formatScheduledDateTime,
  formatScheduledTime,
  getPostScheduledTimeZone,
  getScheduledDateKey,
  getScheduledWallClockParts,
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

  it('round-trips a selected wall-clock time for the stored timezone', () => {
    const utcValue = convertWallClockToUtcIso('2026-06-11', '10:00', 'Asia/Kolkata');

    expect(utcValue).toBe('2026-06-11T04:30:00.000Z');
    expect(formatScheduledTime(utcValue, 'Asia/Kolkata')).toBe('10:00 AM');
    expect(getScheduledDateKey(utcValue, 'Asia/Kolkata')).toBe('2026-06-11');
    expect(getScheduledWallClockParts(utcValue, 'Asia/Kolkata')).toEqual({
      date: '2026-06-11',
      time: '10:00',
    });
  });

  it('keeps the same scheduled clock time for DST-aware zones', () => {
    const utcValue = convertWallClockToUtcIso('2026-06-11', '10:00', 'America/New_York');

    expect(utcValue).toBe('2026-06-11T14:00:00.000Z');
    expect(formatScheduledTime(utcValue, 'America/New_York')).toBe('10:00 AM');
    expect(getScheduledDateKey(utcValue, 'America/New_York')).toBe('2026-06-11');
  });
});
