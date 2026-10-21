import React from 'react';

const statuses = { active: 'Active', checkpoint: 'Checkpoint', checkpoint_detected: 'Checkpoint detected',
  warming: 'Warming', paused: 'Paused', disconnected: 'Disconnected', reauth_required: 'Sign-in required',
  session_expired: 'Session expired', error: 'Error' };
const stops = { rate_limited_429: 'Rate limit', security_challenge_999: 'Security challenge',
  checkpoint_captcha: 'LinkedIn checkpoint', proxy_unhealthy: 'Proxy issue', session_expired: 'Session expired',
  commercial_limit: 'Commercial limit' };
const ownLabel = (map, value) => typeof value === 'string' && Object.hasOwn(map, value) ? map[value] : null;
export const savedStatus = value => ownLabel(statuses, value) || 'Needs review';
export const savedCap = value => Number.isInteger(value) && value >= 0 && value <= 100 ? value : null;

// Server's legacy naive Mongo timestamps represent UTC, as in paid_access._utc.
function recordedTime(value) {
  if (typeof value !== 'string' || value.length > 40) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
  if (!match) return null;
  const [, year, month, day, hour, minute, second, zone] = match;
  if (+year < 1970 || +month < 1 || +month > 12 || +day < 1
      || +day > new Date(Date.UTC(+year, +month, 0)).getUTCDate()
      || +hour > 23 || +minute > 59 || +second > 59) return null;
  const stamp = new Date(zone ? value : `${value}Z`);
  return Number.isFinite(stamp.getTime()) ? stamp.toISOString() : null;
}

export default function SenderStoredDetails({ account }) {
  const stop = ownLabel(stops, account.stop_reason);
  const hasStop = account.stop_reason !== undefined && account.stop_reason !== null && account.stop_reason !== '';
  const hasCooldown = account.cooldown_until !== undefined && account.cooldown_until !== null;
  const cooldown = recordedTime(account.cooldown_until);
  const level = Number.isInteger(account.warmup_level) && account.warmup_level >= 1 && account.warmup_level <= 4
    ? account.warmup_level : 'Not recorded';
  return <div className="mt-3 space-y-1 text-xs text-gray-500" aria-label="Recorded sender details">
    <p>Warm-up level: {level}</p>
    {hasStop && <p className="text-amber-800">{stop ? `Recorded stop: ${stop}` : 'Recorded stop requires review'}</p>}
    {hasCooldown && <p>{cooldown ? <>Recorded cooldown: <time dateTime={cooldown}>{cooldown.replace('T', ' ').replace('.000Z', ' UTC').replace('Z', ' UTC')}</time></>
      : 'Cooldown timing requires review'}</p>}
    {hasCooldown && <p>Elapsed cooldown does not clear a recorded stop.</p>}
    <p>Live health is not verified here. Launch and sending check current access, resources and permissions.</p>
  </div>;
}
