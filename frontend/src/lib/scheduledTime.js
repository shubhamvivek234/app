const DEFAULT_LOCALE = 'en-US';

const formatterCache = new Map();

const parseDate = (value) => {
  if (!value) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const normalizeTimeZone = (timeZone) => {
  if (!timeZone || typeof timeZone !== 'string') return null;
  try {
    new Intl.DateTimeFormat(DEFAULT_LOCALE, { timeZone }).format(new Date());
    return timeZone;
  } catch {
    return null;
  }
};

const getFormatter = (options) => {
  const key = JSON.stringify(options);
  if (!formatterCache.has(key)) {
    formatterCache.set(key, new Intl.DateTimeFormat(DEFAULT_LOCALE, options));
  }
  return formatterCache.get(key);
};

const formatWithOptions = (value, options, fallback) => {
  const parsed = parseDate(value);
  if (!parsed) return fallback;
  return getFormatter(options).format(parsed);
};

const formatParts = (value, timeZone) => {
  const parsed = parseDate(value);
  if (!parsed) return null;
  const formatter = getFormatter({
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(timeZone ? { timeZone } : {}),
  });
  const partMap = {};
  formatter.formatToParts(parsed).forEach((part) => {
    if (part.type !== 'literal') {
      partMap[part.type] = part.value;
    }
  });
  if (!partMap.year || !partMap.month || !partMap.day) return null;
  return `${partMap.year}-${partMap.month}-${partMap.day}`;
};

const getZonedDateTimeParts = (value, timeZone) => {
  const parsed = parseDate(value);
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  if (!parsed || !resolvedTimeZone) return null;
  const formatter = getFormatter({
    timeZone: resolvedTimeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  const partMap = {};
  formatter.formatToParts(parsed).forEach((part) => {
    if (part.type !== 'literal') {
      partMap[part.type] = part.value;
    }
  });
  if (!partMap.year || !partMap.month || !partMap.day || !partMap.hour || !partMap.minute || !partMap.second) {
    return null;
  }
  return {
    year: partMap.year,
    month: partMap.month,
    day: partMap.day,
    hour: partMap.hour === '24' ? '00' : partMap.hour,
    minute: partMap.minute,
    second: partMap.second,
  };
};

export const convertWallClockToUtcIso = (dateStr, timeStr, timeZone) => {
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  if (!resolvedTimeZone || !dateStr || !timeStr) return null;

  const utcReference = new Date(`${dateStr}T${timeStr}:00Z`);
  if (Number.isNaN(utcReference.getTime())) return null;

  const zonedParts = getZonedDateTimeParts(utcReference, resolvedTimeZone);
  if (!zonedParts) return null;

  const zonedAsUtc = new Date(
    `${zonedParts.year}-${zonedParts.month}-${zonedParts.day}T${zonedParts.hour}:${zonedParts.minute}:${zonedParts.second}Z`
  );
  if (Number.isNaN(zonedAsUtc.getTime())) return null;

  const offsetMs = zonedAsUtc.getTime() - utcReference.getTime();
  return new Date(utcReference.getTime() - offsetMs).toISOString();
};

export const getPostScheduledTimeZone = (post) => {
  if (!post?.scheduled_timezone_explicit) return null;
  return normalizeTimeZone(post?.timezone);
};

export const formatScheduledTime = (value, timeZone = null) => {
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  return formatWithOptions(
    value,
    {
      hour: 'numeric',
      minute: '2-digit',
      ...(resolvedTimeZone ? { timeZone: resolvedTimeZone } : {}),
    },
    'No time',
  );
};

export const formatScheduledDateTime = (value, timeZone = null, { includeTimeZone = false } = {}) => {
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  return formatWithOptions(
    value,
    {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      ...(resolvedTimeZone ? { timeZone: resolvedTimeZone } : {}),
      ...(resolvedTimeZone && includeTimeZone ? { timeZoneName: 'short' } : {}),
    },
    'No scheduled time',
  );
};

export const formatScheduledCompactDateTime = (value, timeZone = null, { includeTimeZone = false } = {}) => {
  const resolvedTimeZone = normalizeTimeZone(timeZone);
  return formatWithOptions(
    value,
    {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      ...(resolvedTimeZone ? { timeZone: resolvedTimeZone } : {}),
      ...(resolvedTimeZone && includeTimeZone ? { timeZoneName: 'short' } : {}),
    },
    'Unknown time',
  );
};

export const getScheduledDateKey = (value, timeZone = null) => formatParts(value, normalizeTimeZone(timeZone));
