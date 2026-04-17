/**
 * BulkCSVUpload — full-page bulk CSV scheduling
 * Steps: upload → validating → review → editing (post cards) → done
 */
import React, { useState, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { getSocialAccounts } from '@/lib/api';
import AccountSelector from '@/components/composer/AccountSelector';
import { toast } from 'sonner';
import {
  FaArrowLeft, FaCloudUploadAlt, FaDownload, FaFileCsv, FaCheckCircle,
  FaExclamationTriangle, FaSpinner, FaExclamationCircle, FaGlobe,
  FaFacebook, FaTwitter, FaLinkedin, FaInstagram, FaPinterest,
  FaYoutube, FaDiscord, FaTimesCircle, FaTimes, FaCalendarAlt,
  FaClock, FaVideo, FaFileAlt, FaChevronRight,
} from 'react-icons/fa';
import { SiTiktok as FaTiktok, SiBluesky, SiThreads } from 'react-icons/si';

// ── Platform config ────────────────────────────────────────────────────────────
const PLATFORM_ICONS = {
  facebook:  { icon: FaFacebook,  color: 'text-blue-600' },
  twitter:   { icon: FaTwitter,   color: 'text-sky-500' },
  linkedin:  { icon: FaLinkedin,  color: 'text-blue-700' },
  instagram: { icon: FaInstagram, color: 'text-pink-500' },
  pinterest: { icon: FaPinterest, color: 'text-red-600' },
  youtube:   { icon: FaYoutube,   color: 'text-red-600' },
  tiktok:    { icon: FaTiktok,    color: 'text-gray-900' },
  bluesky:   { icon: SiBluesky,   color: 'text-blue-500' },
  threads:   { icon: SiThreads,   color: 'text-gray-900' },
  discord:   { icon: FaDiscord,   color: 'text-indigo-500' },
};

const getAvatarColor = (name) => {
  const colors = ['bg-blue-500','bg-green-500','bg-yellow-500','bg-red-500','bg-purple-500','bg-pink-500','bg-indigo-500','bg-teal-500'];
  return colors[(name?.charCodeAt(0) || 0) % colors.length];
};

const VALID_PLATFORMS = ['instagram','youtube','twitter','tiktok','linkedin','facebook','bluesky','discord','threads','pinterest'];
const PLATFORM_CHAR_LIMITS = {
  instagram: 2200, facebook: 63206, twitter: 280,
  tiktok: 4000, linkedin: 3000, youtube: 5000, bluesky: 300,
};
const TITLE_LIMITS = { youtube: 100, linkedin: 150 };
const PRIVATE_IP_RE = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)/;

// ── CSV parser ────────────────────────────────────────────────────────────────
const parseCSV = (text) => {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n');
  if (!lines.length) return { headers: [], rows: [] };
  const parseRow = (line) => {
    const cols = []; let cur = ''; let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') { if (inQ && line[i+1] === '"') { cur += '"'; i++; } else { inQ = !inQ; } continue; }
      if (ch === ',' && !inQ) { cols.push(cur); cur = ''; continue; }
      cur += ch;
    }
    cols.push(cur);
    return cols.map((c) => c.trim());
  };
  const headers = parseRow(lines[0]).map((h) => h.toLowerCase().trim().replace(/\s+/g, '_'));
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const cols = parseRow(line);
    const obj = { _row: i };
    headers.forEach((h, j) => { obj[h] = (cols[j] || '').trim(); });
    rows.push(obj);
  }
  return { headers, rows };
};

// ── DateTime utilities ────────────────────────────────────────────────────────
const MONTH_ABBR = { jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11 };

const parseDateTime = (str) => {
  if (!str) return null;
  const s = str.trim();
  const mAbbr = s.match(/^(\d{1,2})\/([A-Za-z]{3})\/(\d{4}) (\d{2}):(\d{2})$/);
  if (mAbbr) {
    const mo = MONTH_ABBR[mAbbr[2].toLowerCase()];
    if (mo !== undefined)
      return new Date(parseInt(mAbbr[3]), mo, parseInt(mAbbr[1]), parseInt(mAbbr[4]), parseInt(mAbbr[5]));
  }
  const mNum = s.match(/^(\d{1,2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);
  if (mNum)
    return new Date(parseInt(mNum[3]), parseInt(mNum[2])-1, parseInt(mNum[1]), parseInt(mNum[4]), parseInt(mNum[5]));
  return null;
};

const parseDateTimeParts = (str) => {
  if (!str) return null;
  const s = str.trim();
  const mAbbr = s.match(/^(\d{1,2})\/([A-Za-z]{3})\/(\d{4}) (\d{2}):(\d{2})$/);
  if (mAbbr) {
    const mo = MONTH_ABBR[mAbbr[2].toLowerCase()];
    if (mo !== undefined) {
      const mm = String(mo + 1).padStart(2, '0');
      const dd = String(parseInt(mAbbr[1])).padStart(2, '0');
      return { dateStr: `${mAbbr[3]}-${mm}-${dd}`, timeStr: `${mAbbr[4]}:${mAbbr[5]}` };
    }
  }
  const mNum = s.match(/^(\d{1,2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);
  if (mNum) {
    const dd = String(parseInt(mNum[1])).padStart(2, '0');
    return { dateStr: `${mNum[3]}-${mNum[2]}-${dd}`, timeStr: `${mNum[4]}:${mNum[5]}` };
  }
  return null;
};

// ── Timezone utilities ────────────────────────────────────────────────────────
const FALLBACK_TIMEZONES = [
  'UTC','America/New_York','America/Chicago','America/Denver','America/Los_Angeles',
  'America/Toronto','America/Vancouver','America/Sao_Paulo','America/Buenos_Aires',
  'Europe/London','Europe/Paris','Europe/Berlin','Europe/Rome','Europe/Moscow',
  'Africa/Cairo','Africa/Lagos','Africa/Nairobi','Africa/Johannesburg',
  'Asia/Dubai','Asia/Karachi','Asia/Kolkata','Asia/Bangkok','Asia/Singapore',
  'Asia/Hong_Kong','Asia/Shanghai','Asia/Seoul','Asia/Tokyo',
  'Australia/Sydney','Australia/Melbourne','Pacific/Auckland','Pacific/Honolulu',
];

const getUTCOffsetLabel = (tzName) => {
  try {
    const parts = new Intl.DateTimeFormat('en', { timeZone: tzName, timeZoneName: 'shortOffset' }).formatToParts(new Date());
    return parts.find((p) => p.type === 'timeZoneName')?.value || 'UTC';
  } catch { return 'UTC'; }
};

const buildTimezoneList = () => {
  const names = (typeof Intl.supportedValuesOf === 'function') ? Intl.supportedValuesOf('timeZone') : FALLBACK_TIMEZONES;
  return names.map((tz) => ({ value: tz, label: `${tz} (${getUTCOffsetLabel(tz)})` }));
};

const convertToUTC = (dateStr, timeStr, tzName) => {
  const dtAsUTC = new Date(`${dateStr}T${timeStr}:00Z`);
  if (isNaN(dtAsUTC.getTime())) return null;
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: tzName, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const parts = formatter.formatToParts(dtAsUTC);
  const p = {};
  parts.forEach((pt) => (p[pt.type] = pt.value));
  const hour = p.hour === '24' ? '00' : p.hour;
  const localAsUTC = new Date(`${p.year}-${p.month}-${p.day}T${hour}:${p.minute}:${p.second}Z`);
  const offsetMs = localAsUTC.getTime() - dtAsUTC.getTime();
  return new Date(dtAsUTC.getTime() - offsetMs).toISOString();
};

// ── Client-side row validation (format only, no URL/platform checks) ──────────
const validateRowFormat = (row) => {
  const errors = []; const warnings = [];
  if (!row.content && !row.image_urls && !row.video_url) errors.push('At least one of content, image_urls, or video_url is required');
  if (row.image_urls && row.video_url) errors.push('Cannot have both image_urls and video_url');
  if (!row.platforms) errors.push('platforms is required');
  const platforms = (row.platforms || '').toLowerCase().split(',').map((p) => p.trim()).filter(Boolean);
  for (const p of platforms) {
    if (!VALID_PLATFORMS.includes(p)) errors.push(`Unknown platform: "${p}"`);
  }
  if (row.post_type === 'reel' && !platforms.includes('instagram')) errors.push('post_type "reel" requires instagram');
  if (row.post_type === 'story' && !platforms.some((p) => ['instagram','facebook'].includes(p))) errors.push('post_type "story" requires instagram or facebook');
  if (row.content) {
    for (const p of platforms) {
      const limit = PLATFORM_CHAR_LIMITS[p];
      if (limit && row.content.length > limit) errors.push(`Content exceeds ${p} limit (${row.content.length}/${limit})`);
    }
    if (platforms.includes('instagram') && row.content.length > 125) warnings.push('Instagram: content over 125 chars hidden behind "more"');
    if (platforms.includes('linkedin') && row.content.length > 140) warnings.push('LinkedIn: content over 140 chars collapses');
  }
  if (row.title) {
    if (platforms.includes('youtube') && row.title.length > TITLE_LIMITS.youtube) errors.push(`YouTube title too long (${row.title.length}/100)`);
    if (platforms.includes('linkedin') && row.title.length > TITLE_LIMITS.linkedin) errors.push(`LinkedIn title too long (${row.title.length}/150)`);
  }
  if (row.scheduled_time) {
    const dt = parseDateTime(row.scheduled_time);
    if (!dt || isNaN(dt.getTime())) {
      errors.push('Invalid scheduled_time — use DD/Mon/YYYY HH:mm');
    } else {
      const now = new Date();
      if (dt < now) errors.push('scheduled_time is in the past');
      if (dt > new Date(now.getTime() + 365*24*60*60*1000)) errors.push('scheduled_time is more than 365 days ahead');
      if (dt > now && dt < new Date(now.getTime() + 2*60*1000)) warnings.push('scheduled_time is within 2 minutes of now');
    }
  }
  // URL format check (not network, just format)
  if (row.image_urls) {
    const urls = row.image_urls.split('||').map((u) => u.trim());
    if (urls.length > 10) errors.push('image_urls: max 10 URLs per row');
    for (const u of urls) {
      if (!u.startsWith('http')) errors.push(`Invalid image URL (not http): "${u.slice(0,40)}"`);
      else if (PRIVATE_IP_RE.test(u.replace(/^https?:\/\//, ''))) errors.push('image_url targets private address');
    }
  }
  if (row.video_url) {
    if (!row.video_url.startsWith('http')) errors.push('Invalid video_url (not http)');
    else if (PRIVATE_IP_RE.test(row.video_url.replace(/^https?:\/\//, ''))) errors.push('video_url targets private address');
  }
  return { errors, warnings };
};

const truncate = (s, n = 50) => (!s ? '—' : s.length > n ? s.slice(0, n) + '…' : s);

// ── Timezone selector ─────────────────────────────────────────────────────────
const TimezoneSelect = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const wrapRef = useRef(null);
  const searchRef = useRef(null);
  const allTZ = useMemo(() => buildTimezoneList(), []);
  const filtered = useMemo(() => search.trim() ? allTZ.filter((tz) => tz.label.toLowerCase().includes(search.toLowerCase())) : allTZ, [allTZ, search]);
  const selected = allTZ.find((tz) => tz.value === value);
  React.useEffect(() => {
    const h = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  return (
    <div ref={wrapRef} className="relative">
      <button type="button" onClick={() => { setOpen((o) => !o); setTimeout(() => searchRef.current?.focus(), 50); }}
        className="w-full flex items-center gap-2 text-xs px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg hover:border-green-400 focus:outline-none focus:border-green-400 transition-colors text-left">
        <FaGlobe className="text-gray-400 flex-shrink-0" />
        <span className="flex-1 truncate text-gray-700">{selected?.label || value}</span>
        <span className="text-gray-400 text-[10px]">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          <div className="p-2 border-b border-gray-100">
            <input ref={searchRef} type="text" placeholder="Search timezone…" value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full text-xs px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 transition-colors" />
          </div>
          <ul className="max-h-48 overflow-y-auto">
            {filtered.length === 0 && <li className="text-xs text-gray-400 px-3 py-3 text-center">No timezones found</li>}
            {filtered.map((tz) => (
              <li key={tz.value} onClick={() => { onChange(tz.value); setOpen(false); setSearch(''); }}
                className={`text-xs px-3 py-2 cursor-pointer truncate transition-colors ${tz.value === value ? 'bg-green-50 text-green-700 font-semibold' : 'text-gray-700 hover:bg-gray-50'}`}>
                {tz.label}
              </li>
            ))}
          </ul>
          <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400">{filtered.length} timezone{filtered.length !== 1 ? 's' : ''}</div>
        </div>
      )}
    </div>
  );
};

// ── PostCard — editable card for the editing step ─────────────────────────────
const PostCard = ({ item, index, onUpdate, onRemove }) => {
  const hasImage = item.image_urls?.length > 0;
  const hasVideo = !!item.video_url;
  const [imgError, setImgError] = useState(false);
  const [vidError, setVidError] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="flex gap-4">
        {/* Media preview */}
        <div className="w-24 h-24 rounded-lg bg-gray-100 flex-shrink-0 border border-gray-200 overflow-hidden relative flex items-center justify-center">
          {hasImage && !imgError ? (
            <>
              <img
                src={item.image_urls[0]}
                alt=""
                className="absolute inset-0 w-full h-full object-cover"
                onError={() => setImgError(true)}
              />
              {item.image_urls.length > 1 && (
                <div className="absolute bottom-1 right-1 bg-black/60 text-white text-[9px] px-1.5 py-0.5 rounded-md font-semibold z-10">
                  +{item.image_urls.length - 1}
                </div>
              )}
            </>
          ) : hasImage && imgError ? (
            <div className="flex flex-col items-center gap-1 text-center px-2">
              <FaFileAlt className="text-xl text-gray-300" />
              <span className="text-[9px] text-gray-400 leading-tight">Image unavailable</span>
            </div>
          ) : hasVideo && !vidError ? (
            <video
              src={item.video_url}
              className="absolute inset-0 w-full h-full object-cover"
              muted
              preload="metadata"
              onError={() => setVidError(true)}
            />
          ) : hasVideo && vidError ? (
            <div className="flex flex-col items-center gap-1 text-center px-2">
              <FaVideo className="text-xl text-purple-300" />
              <span className="text-[9px] text-gray-400 leading-tight">Video unavailable</span>
            </div>
          ) : (
            <FaFileAlt className="text-2xl text-gray-300" />
          )}
        </div>

        {/* Fields */}
        <div className="flex-1 min-w-0 space-y-2.5">
          <div className="flex items-start justify-between gap-2">
            {/* Platform badges */}
            <div className="flex flex-wrap gap-1">
              {item.platforms.map((p) => {
                const cfg = PLATFORM_ICONS[p];
                const Icon = cfg?.icon;
                return (
                  <span key={p} className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                    {Icon && <Icon className={`text-[9px] ${cfg.color}`} />}
                    {p}
                  </span>
                );
              })}
            </div>
            <button onClick={() => onRemove(index)} className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors flex-shrink-0">
              <FaTimes className="text-xs" />
            </button>
          </div>

          <textarea
            value={item.content}
            onChange={(e) => onUpdate(index, 'content', e.target.value)}
            placeholder="Write a caption…"
            rows={2}
            className="w-full text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
          />

          <div className="flex gap-2">
            <div className="flex-1 relative">
              <FaCalendarAlt className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
              <input type="date" value={item.date} onChange={(e) => onUpdate(index, 'date', e.target.value)}
                className="w-full text-xs pl-7 pr-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors" />
            </div>
            <div className="flex-1 relative">
              <FaClock className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
              <input type="time" value={item.time} onChange={(e) => onUpdate(index, 'time', e.target.value)}
                className="w-full text-xs pl-7 pr-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
const BulkCSVUpload = () => {
  const navigate = useNavigate();

  // Accounts
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [selectedAccounts, setSelectedAccounts] = useState([]);

  // Step flow: 'upload' → 'validating' → 'review' → 'editing' → 'done'
  const [step, setStep] = useState('upload');
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState('');

  // CSV rows + per-row validation results
  const [rows, setRows] = useState([]);
  const [rowValidation, setRowValidation] = useState([]); // { errors[], warnings[], valid }
  const [expandedRow, setExpandedRow] = useState(null);

  // Editable post cards (editing step)
  const [posts, setPosts] = useState([]);

  // Scheduling
  const [bulkTimezone, setBulkTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [scheduling, setScheduling] = useState(false);
  const [scheduleResults, setScheduleResults] = useState(null);
  const [sentPosts, setSentPosts] = useState([]);

  const fileInputRef = useRef(null);

  React.useEffect(() => {
    setAccountsLoading(true);
    getSocialAccounts()
      .then((res) => setAccounts(Array.isArray(res) ? res : (res.accounts || [])))
      .catch(() => toast.error('Failed to load connected accounts'))
      .finally(() => setAccountsLoading(false));
  }, []);

  // Derived
  const validRows = useMemo(() => rows.filter((_, i) => rowValidation[i]?.valid), [rows, rowValidation]);
  const invalidCount = rows.length - validRows.length;

  // ── Template download ──────────────────────────────────────────────────────
  const downloadTemplate = () => {
    const cols = 'content,platforms,accounts,scheduled_time,image_urls,video_url,title,tags,post_type';
    const future = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    const pad = (n) => String(n).padStart(2, '0');
    const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const futureStr = `${pad(future.getDate())}/${MONTHS[future.getMonth()]}/${future.getFullYear()} 10:00`;
    const example = `"Hello world! First post via CSV","instagram,twitter","all","${futureStr}","https://images.unsplash.com/photo-1506744038136-46273834b3fb.jpg","","","social,marketing","image"`;
    const csv = [cols, example].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url;
    a.download = 'socialentangler_bulk_template.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  // ── Validation pipeline: format + URL network check + platform connectivity ─
  const runValidation = async (parsedRows, currentAccounts) => {
    setStep('validating');

    // 1. Client-side format validation
    const formatResults = parsedRows.map((row) => validateRowFormat(row));

    // 2. Collect unique URLs from rows that passed format check
    const urlsToCheck = [];
    const seenUrls = new Set();
    parsedRows.forEach((row, i) => {
      if (formatResults[i].errors.length > 0) return;
      if (row.image_urls) {
        row.image_urls.split('||').map((u) => u.trim()).filter(Boolean).forEach((u) => {
          if (!seenUrls.has(u)) { seenUrls.add(u); urlsToCheck.push(u); }
        });
      }
      if (row.video_url?.trim()) {
        const u = row.video_url.trim();
        if (!seenUrls.has(u)) { seenUrls.add(u); urlsToCheck.push(u); }
      }
    });

    // 3. Backend URL validation (HEAD requests)
    const urlResults = {};
    if (urlsToCheck.length > 0) {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(
          `${process.env.REACT_APP_BACKEND_URL}/api/bulk/validate-urls`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ urls: urlsToCheck }),
          }
        );
        if (res.ok) {
          const data = await res.json();
          data.forEach((r) => { urlResults[r.url] = r; });
        }
      } catch {
        // URL validation service unavailable — skip, don't block
      }
    }

    // 4. Connected platforms (any account — regardless of selection)
    const connectedPlatformSet = new Set(
      currentAccounts.map((a) => (a.platform || '').toLowerCase()).filter(Boolean)
    );

    // 5. Merge format + URL + platform results
    const finalResults = parsedRows.map((row, i) => {
      const base = { ...formatResults[i] };
      const errors = [...base.errors];
      const warnings = [...base.warnings];

      if (errors.length > 0) return { errors, warnings, valid: false };

      // URL checks
      if (row.image_urls) {
        row.image_urls.split('||').map((u) => u.trim()).filter(Boolean).forEach((u) => {
          const r = urlResults[u];
          if (r && !r.ok) errors.push(`Image URL not accessible: ${r.error || 'unreachable'} — ${u.slice(0,50)}`);
        });
      }
      if (row.video_url?.trim()) {
        const r = urlResults[row.video_url.trim()];
        if (r && !r.ok) errors.push(`Video URL not accessible: ${r.error || 'unreachable'}`);
      }

      // Platform connectivity check
      const platforms = (row.platforms || '').toLowerCase().split(',').map((p) => p.trim()).filter((p) => VALID_PLATFORMS.includes(p));
      const notConnected = platforms.filter((p) => !connectedPlatformSet.has(p));
      if (notConnected.length > 0) {
        errors.push(`Platform not connected: ${notConnected.join(', ')} — go to Settings → Accounts`);
      }

      return { errors, warnings, valid: errors.length === 0 };
    });

    setRowValidation(finalResults);
    setStep('review');
  };

  // ── Process CSV file ───────────────────────────────────────────────────────
  const processFile = (file) => {
    if (!file) return;
    if (!file.name.endsWith('.csv')) { toast.error('Please upload a .csv file'); return; }
    if (file.size > 10 * 1024 * 1024) { toast.error('CSV file must be under 10 MB'); return; }
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const { headers, rows: parsed } = parseCSV(e.target.result);
        if (!parsed.length) { toast.error('CSV has no data rows'); return; }
        const required = ['content', 'platforms'];
        const missing = required.filter((h) => !headers.includes(h));
        if (missing.length) {
          const guessOld = headers.some((h) => h === 'text' || h === 'image_url');
          toast.error(guessOld ? 'CSV uses old column names. Download the new template.' : `Missing required columns: ${missing.join(', ')}`);
          return;
        }
        setRows(parsed);
        setRowValidation([]);
        setExpandedRow(null);
        runValidation(parsed, accounts);
      } catch {
        toast.error('Failed to parse CSV. Ensure it is UTF-8 encoded.');
      }
    };
    reader.readAsText(file);
  };

  // ── Load valid rows as editable post cards ─────────────────────────────────
  const handleLoadPosts = () => {
    const items = validRows.map((row) => {
      const dtParts = parseDateTimeParts(row.scheduled_time);
      return {
        content: row.content || '',
        platforms: (row.platforms || '').toLowerCase().split(',').map((p) => p.trim()).filter(Boolean),
        image_urls: row.image_urls ? row.image_urls.split('||').map((u) => u.trim()).filter(Boolean) : [],
        video_url: row.video_url?.trim() || null,
        title: row.title || null,
        tags: row.tags ? row.tags.split(',').map((t) => t.trim()).filter(Boolean) : [],
        post_type: row.post_type || null,
        date: dtParts?.dateStr || '',
        time: dtParts?.timeStr || '',
        _row: row._row,
      };
    });
    setPosts(items);
    setStep('editing');
  };

  const updatePost = (index, field, value) => {
    setPosts((prev) => prev.map((p, i) => i === index ? { ...p, [field]: value } : p));
  };

  const removePost = (index) => {
    setPosts((prev) => prev.filter((_, i) => i !== index));
  };

  // ── Schedule all posts ────────────────────────────────────────────────────
  const handleScheduleAll = async () => {
    if (!posts.length) return;
    setScheduling(true);
    try {
      const token = localStorage.getItem('token');
      const payload = posts.map((item) => {
        let scheduledTime = null;
        if (item.date && item.time) {
          scheduledTime = convertToUTC(item.date, item.time, bulkTimezone);
        }
        return {
          content: item.content,
          platforms: item.platforms,
          scheduled_time: scheduledTime,
          image_urls: item.image_urls,
          video_url: item.video_url,
          title: item.title,
          tags: item.tags,
          post_type: item.post_type,
          row: item._row || 0,
          status: 'scheduled',
        };
      });

      const res = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/bulk/csv-upload`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ posts: payload, selected_account_ids: selectedAccounts, fallback_timezone: bulkTimezone }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      setSentPosts(payload);
      setScheduleResults(data);
      setStep('done');
      toast.success(`${data.created} post${data.created !== 1 ? 's' : ''} scheduled`);
    } catch (err) {
      toast.error(err.message || 'Scheduling failed. Please try again.');
    } finally {
      setScheduling(false);
    }
  };

  const resetFlow = () => {
    setStep('upload'); setRows([]); setRowValidation([]); setFileName('');
    setExpandedRow(null); setPosts([]); setScheduleResults(null); setSentPosts([]);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button onClick={() => navigate('/bulk-upload')}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
            <FaArrowLeft />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Bulk CSV Upload</h1>
            <p className="text-xs text-gray-500">Import posts from a CSV, validate, then schedule across your accounts</p>
          </div>
          {(step === 'review' || step === 'editing') && (
            <button onClick={resetFlow} className="ml-auto text-xs text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0">
              ← Upload new file
            </button>
          )}
        </div>

        {/* Connected accounts bar — shown during editing step only */}
        {step === 'editing' && (
          <div className="bg-white rounded-xl border border-gray-200 px-5 py-4 mb-6 shadow-sm">
            {accountsLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-xs py-1">
                <FaSpinner className="animate-spin text-xs" /> Loading accounts…
              </div>
            ) : accounts.length === 0 ? (
              <div className="flex items-center gap-2 text-amber-600 text-xs bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                <FaExclamationCircle className="flex-shrink-0" />
                No connected accounts. <a href="/accounts" className="underline font-semibold ml-1">Connect one →</a>
              </div>
            ) : (
              <AccountSelector
                accounts={accounts}
                selectedAccounts={selectedAccounts}
                onToggle={(id) => setSelectedAccounts((prev) => prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id])}
                platformIcons={PLATFORM_ICONS}
                getAvatarColor={getAvatarColor}
              />
            )}
          </div>
        )}

        {/* ── STEP: upload ── */}
        {step === 'upload' && (
          <div className="space-y-5">
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-gray-900 mb-1">1. Prepare your CSV file</h3>
              <p className="text-xs text-gray-500 mb-4 leading-relaxed">
                Columns: <strong>content, platforms, accounts, scheduled_time, image_urls, video_url, title, tags, post_type</strong>.{' '}
                Use <code className="bg-gray-100 px-1 rounded text-green-700">DD/Mon/YYYY HH:mm</code> for dates.
                Separate multiple platforms with commas, multiple image URLs with <code className="bg-gray-100 px-1 rounded text-green-700">||</code>.
              </p>
              <div className="overflow-x-auto rounded-lg border border-gray-200 mb-4 bg-offwhite">
                <table className="text-[10px] min-w-[500px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      {['content','platforms','scheduled_time','image_urls','video_url','post_type'].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[1,2,3].map((r) => (
                      <tr key={r} className="border-b border-gray-100 last:border-0">
                        {[1,2,3,4,5,6].map((c) => <td key={c} className="px-3 py-2 text-gray-300">—</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button onClick={downloadTemplate}
                className="flex items-center gap-2 px-4 py-2 text-xs font-semibold border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 rounded-lg transition-colors shadow-sm">
                <FaDownload className="text-[10px]" /> Download CSV Template
              </button>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h3 className="text-sm font-bold text-gray-900 mb-4">2. Upload your CSV file</h3>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); processFile(e.dataTransfer.files?.[0]); }}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl py-14 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors ${
                  dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-green-300 hover:bg-green-50/30'
                }`}
              >
                <FaCloudUploadAlt className={`text-4xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
                <div className="text-center">
                  <p className="text-sm font-semibold text-gray-600">{dragging ? 'Drop your CSV here' : 'Click or drag & drop your CSV file'}</p>
                  <p className="text-xs text-gray-400 mt-0.5">UTF-8 encoded .csv — max 10 MB</p>
                </div>
                <button onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  className="px-4 py-1.5 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors">
                  <FaFileCsv className="inline mr-1.5" /> Upload CSV
                </button>
              </div>
              <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                onChange={(e) => { processFile(e.target.files?.[0]); e.target.value = ''; }} />
            </div>
          </div>
        )}

        {/* ── STEP: validating ── */}
        {step === 'validating' && (
          <div className="bg-white rounded-xl border border-gray-200 p-16 shadow-sm flex flex-col items-center justify-center gap-5">
            <FaSpinner className="text-4xl text-green-500 animate-spin" />
            <div className="text-center">
              <p className="text-base font-semibold text-gray-700">Validating your CSV…</p>
              <p className="text-xs text-gray-500 mt-1.5">Checking URL accessibility and platform connections</p>
            </div>
          </div>
        )}

        {/* ── STEP: review ── */}
        {step === 'review' && (
          <div className="space-y-5">
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm text-center">
                <p className="text-2xl font-bold text-gray-900">{rows.length}</p>
                <p className="text-xs text-gray-500 mt-0.5">Total rows</p>
              </div>
              <div className="bg-white rounded-xl border border-green-200 p-4 shadow-sm text-center">
                <p className="text-2xl font-bold text-green-600">{validRows.length}</p>
                <p className="text-xs text-gray-500 mt-0.5">Valid — will load</p>
              </div>
              <div className={`bg-white rounded-xl border p-4 shadow-sm text-center ${invalidCount > 0 ? 'border-red-200' : 'border-gray-200'}`}>
                <p className={`text-2xl font-bold ${invalidCount > 0 ? 'text-red-500' : 'text-gray-300'}`}>{invalidCount}</p>
                <p className="text-xs text-gray-500 mt-0.5">Errors — will skip</p>
              </div>
            </div>

            {/* Validation table */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
                <div className="flex items-center gap-2">
                  <FaFileCsv className="text-green-500" />
                  <span className="text-sm font-bold text-gray-900">{fileName}</span>
                </div>
                <button onClick={resetFlow} className="text-xs text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1">
                  <FaTimes className="text-[10px]" /> Upload different file
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[600px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      {['#','Content','Media','Platforms','Scheduled Time','Status'].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => {
                      const { errors, warnings } = rowValidation[i] || { errors: [], warnings: [] };
                      const hasError = errors.length > 0;
                      const hasWarning = warnings.length > 0;
                      const isExpanded = expandedRow === i;
                      return (
                        <React.Fragment key={i}>
                          <tr className={`border-b border-gray-50 ${hasError ? 'bg-red-50/40' : 'bg-white'}`}>
                            <td className="px-4 py-3 text-xs text-gray-400 font-mono">{row._row}</td>
                            <td className="px-4 py-3 text-xs text-gray-700 max-w-[200px]">
                              <span title={row.content}>{truncate(row.content)}</span>
                            </td>
                            <td className="px-4 py-3">
                              {row.video_url ? (
                                <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-semibold">VIDEO</span>
                              ) : row.image_urls ? (
                                <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-semibold">IMG</span>
                              ) : (
                                <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-semibold">TEXT</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-xs text-gray-500 capitalize">{truncate(row.platforms, 25)}</td>
                            <td className="px-4 py-3 text-xs text-gray-500">
                              {row.scheduled_time || <span className="text-gray-300 italic">Queue</span>}
                            </td>
                            <td className="px-4 py-3">
                              {hasError ? (
                                <button onClick={() => setExpandedRow(isExpanded ? null : i)}
                                  className={`p-1 rounded transition-colors ${isExpanded ? 'bg-red-100' : 'hover:bg-red-50'}`}>
                                  <FaExclamationTriangle className="text-red-500 text-sm" />
                                </button>
                              ) : hasWarning ? (
                                <button onClick={() => setExpandedRow(isExpanded ? null : i)}
                                  className={`p-1 rounded transition-colors ${isExpanded ? 'bg-amber-50' : 'hover:bg-amber-50'}`}>
                                  <FaExclamationTriangle className="text-amber-400 text-sm" />
                                </button>
                              ) : (
                                <FaCheckCircle className="text-green-500 text-sm" />
                              )}
                            </td>
                          </tr>
                          {isExpanded && (hasError || hasWarning) && (
                            <tr className={`border-b border-gray-100 ${hasError ? 'bg-red-50/60' : 'bg-amber-50/60'}`}>
                              <td colSpan={6} className="px-4 pb-3 pt-0">
                                <div className={`rounded-lg border px-4 py-3 ${hasError ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50'}`}>
                                  {errors.length > 0 && (
                                    <div className="mb-2">
                                      <p className="text-[10px] font-bold uppercase tracking-wide text-red-500 mb-1.5">Errors — row will be skipped</p>
                                      <ul className="space-y-1">
                                        {errors.map((err, j) => (
                                          <li key={j} className="flex items-start gap-2 text-xs text-red-700">
                                            <FaExclamationTriangle className="text-red-400 mt-0.5 shrink-0 text-[10px]" />{err}
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                  {warnings.length > 0 && (
                                    <div>
                                      <p className="text-[10px] font-bold uppercase tracking-wide text-amber-500 mb-1.5">Warnings</p>
                                      <ul className="space-y-1">
                                        {warnings.map((w, j) => (
                                          <li key={j} className="flex items-start gap-2 text-xs text-amber-700">
                                            <FaExclamationTriangle className="text-amber-400 mt-0.5 shrink-0 text-[10px]" />{w}
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Footer: summary + action */}
              <div className="px-5 py-4 border-t border-gray-100 flex items-center justify-between gap-3">
                {invalidCount > 0 ? (
                  <p className="text-xs text-gray-500">
                    <FaExclamationTriangle className="inline text-amber-400 mr-1" />
                    <strong>{invalidCount}</strong> row{invalidCount !== 1 ? 's' : ''} with errors will be skipped.
                  </p>
                ) : (
                  <p className="text-xs text-green-600 font-medium">
                    <FaCheckCircle className="inline mr-1" />
                    All {rows.length} rows passed validation.
                  </p>
                )}
                {validRows.length > 0 ? (
                  <button
                    onClick={handleLoadPosts}
                    className="flex items-center gap-2 px-6 py-2.5 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors shadow-sm flex-shrink-0"
                  >
                    Load {validRows.length} Valid Post{validRows.length !== 1 ? 's' : ''}
                    <FaChevronRight className="text-xs" />
                  </button>
                ) : (
                  <button onClick={resetFlow} className="text-xs font-semibold text-red-500 hover:underline flex-shrink-0">
                    Upload a new file
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── STEP: editing ── */}
        {step === 'editing' && (
          <div className="flex gap-6 items-start">
            {/* Left: post cards */}
            <div className="flex-1 min-w-0 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Your Posts ({posts.length})
              </p>
              {posts.map((item, i) => (
                <PostCard
                  key={i}
                  item={item}
                  index={i}
                  onUpdate={updatePost}
                  onRemove={removePost}
                />
              ))}
              {posts.length === 0 && (
                <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
                  <p className="text-sm text-gray-400">All posts removed.</p>
                  <button onClick={resetFlow} className="mt-2 text-xs text-green-600 hover:underline">Start over</button>
                </div>
              )}
            </div>

            {/* Right: sticky settings panel */}
            <div className="w-72 flex-shrink-0">
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm sticky top-20 space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-gray-900 mb-1">Scheduling Timezone</h3>
                  <p className="text-xs text-gray-500 mb-3 leading-relaxed">
                    Used to interpret date/time values. Edit individual cards to adjust per-post.
                  </p>
                  <TimezoneSelect value={bulkTimezone} onChange={setBulkTimezone} />
                </div>

                <div className="border-t border-gray-100 pt-5">
                  {selectedAccounts.length === 0 && (
                    <p className="text-[11px] text-amber-600 bg-amber-50 rounded-lg px-3 py-2 mb-3 border border-amber-100">
                      No accounts selected above — will post to all connected accounts for each platform.
                    </p>
                  )}
                  <div className="bg-gray-50 rounded-lg px-3 py-2.5 mb-4 text-[11px] text-gray-600 space-y-1">
                    <div className="flex justify-between">
                      <span>Posts ready</span>
                      <span className="font-semibold text-green-600">{posts.length}</span>
                    </div>
                  </div>
                  <button
                    onClick={handleScheduleAll}
                    disabled={scheduling || !posts.length}
                    className="w-full py-3 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow"
                  >
                    {scheduling ? (
                      <><FaSpinner className="animate-spin" /> Scheduling…</>
                    ) : (
                      <>Schedule {posts.length} Post{posts.length !== 1 ? 's' : ''}</>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── STEP: done ── */}
        {step === 'done' && scheduleResults && (
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <FaCheckCircle className="text-green-500 text-xl" />
              </div>
              <div>
                <h3 className="text-base font-bold text-gray-900">Import Complete</h3>
                <p className="text-xs text-gray-500">
                  <span className="text-green-600 font-semibold">{scheduleResults.created} post{scheduleResults.created !== 1 ? 's' : ''} scheduled</span>
                  {scheduleResults.failed > 0 && <span className="text-red-500 ml-2 font-semibold">{scheduleResults.failed} failed</span>}
                </p>
              </div>
            </div>

            {scheduleResults.results?.length > 0 && (
              <div className="overflow-x-auto rounded-xl border border-gray-200 mb-5">
                <table className="w-full text-sm min-w-[400px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      {['Row','Content Preview','Platforms','Result'].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {scheduleResults.results.map((r, i) => {
                      const sent = sentPosts[i] || {};
                      const isOk = r.status === 'created';
                      const errMsg = (r.errors || [])[0] || 'Failed';
                      return (
                        <tr key={i} className={`border-b border-gray-50 ${isOk ? 'bg-white' : 'bg-red-50/40'}`}>
                          <td className="px-4 py-3 text-xs text-gray-400 font-mono">{r.row}</td>
                          <td className="px-4 py-3 text-xs text-gray-700 max-w-[180px]">
                            <span title={sent.content}>{truncate(sent.content || '', 45)}</span>
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 capitalize">{(sent.platforms || []).join(', ')}</td>
                          <td className="px-4 py-3">
                            {isOk ? (
                              <span className="flex items-center gap-1 text-xs text-green-600">
                                <FaCheckCircle className="text-[10px]" /> Scheduled
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-xs text-red-500" title={errMsg}>
                                <FaTimesCircle className="text-[10px]" /> {truncate(errMsg, 30)}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={() => navigate('/publish')}
                className="px-5 py-2.5 text-xs font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors shadow">
                View Scheduled Posts
              </button>
              <button onClick={resetFlow}
                className="px-5 py-2.5 text-xs font-semibold border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 rounded-xl transition-colors">
                Upload Another CSV
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default BulkCSVUpload;
