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
