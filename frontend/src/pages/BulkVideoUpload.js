import React, { useState, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { getSocialAccounts } from '@/lib/api';
import AccountSelector from '@/components/composer/AccountSelector';
import { toast } from 'sonner';
import MediaValidationErrorModal from '@/components/MediaValidationErrorModal';
import { validateMediaForPlatforms } from '@/lib/mediaValidation';
import {
  FaArrowLeft, FaCloudUploadAlt, FaTimes, FaVideo, FaCalendarAlt,
  FaClock, FaGlobe, FaSpinner, FaPlus, FaExclamationCircle,
  FaFacebook, FaTwitter, FaLinkedin, FaInstagram, FaPinterest,
  FaYoutube, FaDiscord,
} from 'react-icons/fa';
import { SiTiktok as FaTiktok, SiBluesky, SiThreads } from 'react-icons/si';

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
  const colors = [
    'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
    'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
  ];
  return colors[(name?.charCodeAt(0) || 0) % colors.length];
};

// Fallback list used if browser doesn't support Intl.supportedValuesOf
const FALLBACK_TIMEZONES = [
  'UTC',
  'America/New_York','America/Chicago','America/Denver','America/Los_Angeles',
  'America/Phoenix','America/Anchorage','America/Honolulu',
  'America/Toronto','America/Vancouver','America/Mexico_City',
  'America/Bogota','America/Lima','America/Santiago','America/Sao_Paulo',
  'America/Buenos_Aires','America/Caracas','America/Halifax',
  'Europe/London','Europe/Dublin','Europe/Lisbon','Europe/Madrid',
  'Europe/Paris','Europe/Berlin','Europe/Rome','Europe/Amsterdam',
  'Europe/Brussels','Europe/Vienna','Europe/Zurich','Europe/Stockholm',
  'Europe/Oslo','Europe/Copenhagen','Europe/Helsinki','Europe/Warsaw',
  'Europe/Prague','Europe/Budapest','Europe/Bucharest','Europe/Athens',
  'Europe/Istanbul','Europe/Kiev','Europe/Moscow','Europe/Minsk',
  'Africa/Cairo','Africa/Lagos','Africa/Nairobi','Africa/Johannesburg',
  'Africa/Casablanca','Africa/Accra','Africa/Tunis','Africa/Algiers',
  'Asia/Dubai','Asia/Riyadh','Asia/Kuwait','Asia/Baghdad',
  'Asia/Tehran','Asia/Karachi','Asia/Kolkata','Asia/Colombo',
  'Asia/Kathmandu','Asia/Dhaka','Asia/Yangon','Asia/Bangkok',
  'Asia/Jakarta','Asia/Singapore','Asia/Kuala_Lumpur','Asia/Manila',
  'Asia/Hong_Kong','Asia/Shanghai','Asia/Taipei','Asia/Seoul',
  'Asia/Tokyo','Asia/Vladivostok','Asia/Magadan','Asia/Kamchatka',
  'Australia/Perth','Australia/Darwin','Australia/Adelaide',
  'Australia/Brisbane','Australia/Sydney','Australia/Melbourne',
  'Pacific/Auckland','Pacific/Fiji','Pacific/Honolulu',
  'Pacific/Guam','Pacific/Port_Moresby',
];

// Get UTC offset label for a timezone (e.g. "UTC+5:30")
const getUTCOffsetLabel = (tzName) => {
  try {
    const parts = new Intl.DateTimeFormat('en', {
      timeZone: tzName,
      timeZoneName: 'shortOffset',
    }).formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === 'timeZoneName');
    return tzPart?.value || 'UTC';
  } catch {
    return 'UTC';
  }
};

// Build sorted timezone list with UTC offset labels
const buildTimezoneList = () => {
  const names = (typeof Intl.supportedValuesOf === 'function')
    ? Intl.supportedValuesOf('timeZone')
    : FALLBACK_TIMEZONES;
  return names.map((tz) => ({
    value: tz,
    label: `${tz} (${getUTCOffsetLabel(tz)})`,
  }));
};

// Convert a user's chosen date + time in a named IANA timezone → UTC ISO string
// e.g. ("2025-03-29", "10:00", "Asia/Kolkata") → "2025-03-29T04:30:00.000Z"
const convertToUTC = (dateStr, timeStr, tzName) => {
  // Treat the input as if it were UTC to get a reference Date
  const dtAsUTC = new Date(`${dateStr}T${timeStr}:00Z`);
  if (isNaN(dtAsUTC.getTime())) return null;

  // Format that UTC instant in the target timezone — this tells us what the
  // "local wall clock" would read in that zone for that UTC instant
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: tzName,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
  const parts = formatter.formatToParts(dtAsUTC);
  const p = {};
  parts.forEach((pt) => (p[pt.type] = pt.value));

  // Clamp hour "24" → "00" (Intl edge case at midnight)
  const hour = p.hour === '24' ? '00' : p.hour;
  const localAsUTC = new Date(`${p.year}-${p.month}-${p.day}T${hour}:${p.minute}:${p.second}Z`);

  // The offset in ms between "target tz local time read as UTC" and our reference UTC
  const offsetMs = localAsUTC.getTime() - dtAsUTC.getTime();

  // Subtract the offset to get the true UTC instant
  return new Date(dtAsUTC.getTime() - offsetMs).toISOString();
};

const formatFileSize = (bytes) => {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// Searchable dropdown timezone selector
const TimezoneSelect = ({ value, onChange }) => {
  const [open, setOpen]     = useState(false);
  const [search, setSearch] = useState('');
  const wrapRef             = useRef(null);
  const searchRef           = useRef(null);

  const allTZ = useMemo(() => buildTimezoneList(), []);
  const filtered = useMemo(
    () => search.trim()
      ? allTZ.filter((tz) => tz.label.toLowerCase().includes(search.toLowerCase()))
      : allTZ,
    [allTZ, search]
  );

  const selected = allTZ.find((tz) => tz.value === value);

  // Close on outside click
  React.useEffect(() => {
    const handler = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleOpen = () => {
    setOpen((o) => !o);
    // Auto-focus search on open
    setTimeout(() => searchRef.current?.focus(), 50);
  };

  const pick = (tz) => {
    onChange(tz.value);
    setOpen(false);
    setSearch('');
  };

  return (
    <div ref={wrapRef} className="relative">
      {/* Trigger button */}
      <button
        type="button"
        onClick={handleOpen}
        className="w-full flex items-center gap-2 text-xs px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg hover:border-green-400 focus:outline-none focus:border-green-400 transition-colors text-left"
      >
        <FaGlobe className="text-gray-400 flex-shrink-0" />
        <span className="flex-1 truncate text-gray-700">{selected?.label || value}</span>
        <span className="text-gray-400 text-[10px]">{open ? '▲' : '▼'}</span>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden">
          {/* Search */}
          <div className="p-2 border-b border-gray-100">
            <input
              ref={searchRef}
              type="text"
              placeholder="Search timezone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full text-xs px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 transition-colors"
            />
          </div>
          {/* Options list */}
          <ul className="max-h-48 overflow-y-auto">
            {filtered.length === 0 && (
              <li className="text-xs text-gray-400 px-3 py-3 text-center">No timezones found</li>
            )}
            {filtered.map((tz) => (
              <li
                key={tz.value}
                onClick={() => pick(tz)}
                className={`text-xs px-3 py-2 cursor-pointer truncate transition-colors ${
                  tz.value === value
                    ? 'bg-green-50 text-green-700 font-semibold'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                {tz.label}
              </li>
            ))}
          </ul>
          <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400">
            {filtered.length} timezone{filtered.length !== 1 ? 's' : ''}
          </div>
        </div>
      )}
    </div>
  );
};

const VideoCard = ({ item, index, onUpdate, onRemove }) => (
  <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
    <div className="flex gap-4">
      {/* Thumbnail */}
      <div className="w-20 h-20 rounded-lg bg-gray-100 flex-shrink-0 overflow-hidden border border-gray-200 relative">
        {item.previewUrl ? (
          <video src={item.previewUrl} className="w-full h-full object-cover" muted />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <FaVideo className="text-2xl text-gray-300" />
          </div>
        )}
        <div className="absolute bottom-1 right-1 bg-black/60 text-white text-[9px] px-1 rounded">
          {item.file ? formatFileSize(item.file.size) : ''}
        </div>
      </div>

      {/* Fields */}
      <div className="flex-1 min-w-0 space-y-2.5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-semibold text-gray-700 truncate">{item.file?.name || `Video ${index + 1}`}</p>
          <button
            onClick={() => onRemove(index)}
            className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors flex-shrink-0"
          >
            <FaTimes className="text-xs" />
          </button>
        </div>

        <textarea
          value={item.caption}
          onChange={(e) => onUpdate(index, 'caption', e.target.value)}
          placeholder="Write a caption…"
          rows={2}
          className="w-full text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
        />

        <div className="flex gap-2">
          <div className="flex-1">
            <div className="relative">
              <FaCalendarAlt className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
              <input
                type="date"
                value={item.date}
                onChange={(e) => onUpdate(index, 'date', e.target.value)}
                className="w-full text-xs pl-7 pr-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
              />
            </div>
          </div>
          <div className="flex-1">
            <div className="relative">
              <FaClock className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
              <input
                type="time"
                value={item.time}
                onChange={(e) => onUpdate(index, 'time', e.target.value)}
                className="w-full text-xs pl-7 pr-2 py-1.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const BulkVideoUpload = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [videos, setVideos] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [mediaValidation, setMediaValidation] = useState(null); // { file, violations, platforms, pendingFiles }

  // Bulk settings
  const [bulkDate, setBulkDate] = useState('');
  const [bulkTime, setBulkTime] = useState('');
  const [bulkTimezone, setBulkTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  );

  const fileInputRef = useRef(null);

  React.useEffect(() => {
    setAccountsLoading(true);
    getSocialAccounts()
      .then((res) => setAccounts(Array.isArray(res) ? res : (res.accounts || [])))
      .catch(() => toast.error('Failed to load connected accounts'))
      .finally(() => setAccountsLoading(false));
  }, []);

  const addFiles = useCallback((files, { skipValidation = false } = {}) => {
    const videoFiles = Array.from(files).filter((f) => f.type.startsWith('video/'));
    if (!videoFiles.length) {
      toast.error('Please upload video files only');
      return;
    }

    // Validate against selected platforms (or all platforms if none selected yet)
    if (!skipValidation) {
      const selectedPlatforms = [...new Set(
        accounts.filter((a) => selectedAccounts.includes(a.id)).map((a) => a.platform)
      )];
      const platforms = selectedPlatforms.length > 0
        ? selectedPlatforms
        : ['instagram', 'facebook', 'youtube', 'twitter', 'linkedin', 'tiktok'];

      // Check all files — show modal for the first violation found
      for (const file of videoFiles) {
        const violations = validateMediaForPlatforms(file, platforms);
        if (violations.length > 0) {
          setMediaValidation({ file, violations, platforms, pendingFiles: videoFiles });
          return;
        }
      }
    }

    const newItems = videoFiles.map((file) => ({
      file,
      caption: '',
      date: '',
      time: '',
      previewUrl: URL.createObjectURL(file),
    }));
    setVideos((prev) => [...prev, ...newItems]);
  }, [accounts, selectedAccounts]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles]);

  const updateVideo = (index, field, value) => {
    setVideos((prev) => prev.map((v, i) => i === index ? { ...v, [field]: value } : v));
  };

  const removeVideo = (index) => {
    setVideos((prev) => {
      const item = prev[index];
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  };

  const applyBulkSettings = () => {
    if (!bulkDate && !bulkTime) {
      toast.error('Set at least a date or time to apply');
      return;
    }
    setVideos((prev) =>
      prev.map((v) => ({
        ...v,
        date: bulkDate || v.date,
        time: bulkTime || v.time,
      }))
    );
    toast.success('Bulk settings applied to all videos');
  };

  const toggleAccount = (id) => {
    setSelectedAccounts((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
    );
  };

  const handleScheduleAll = async () => {
    if (!selectedAccounts.length) {
      toast.error('Select at least one account');
      return;
    }
    const ready = videos.filter((v) => v.caption || v.file);
    if (!ready.length) {
      toast.error('Add at least one video');
      return;
    }

    setScheduling(true);
    try {
      // Upload each video via existing media pipeline then schedule posts
      let scheduled = 0;
      for (const video of ready) {
        const formData = new FormData();
        formData.append('file', video.file);

        const uploadRes = await fetch(
          `${process.env.REACT_APP_BACKEND_URL}/api/v1/upload/media`,
          {
            method: 'POST',
            headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
            body: formData,
          }
        );
        const uploadData = await uploadRes.json();
        const mediaId = uploadData.media_id;

        let scheduledTime = null;
        if (video.date && video.time) {
          // Convert date+time in the selected timezone → UTC ISO string
          scheduledTime = convertToUTC(video.date, video.time, bulkTimezone);
        }

        await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/v1/posts`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
          body: JSON.stringify({
            content: video.caption,
            media_ids: mediaId ? [mediaId] : [],
            platforms: [...new Set(
              accounts.filter((a) => selectedAccounts.includes(a.id)).map((a) => a.platform)
            )],
            account_ids: selectedAccounts,
            scheduled_time: scheduledTime,
            timezone: bulkTimezone,
          }),
        });
        scheduled++;
      }
      toast.success(`${scheduled} video${scheduled !== 1 ? 's' : ''} scheduled successfully`);
      navigate('/content');
    } catch {
      toast.error('Failed to schedule some videos. Please try again.');
    } finally {
      setScheduling(false);
    }
  };

  return (
    <DashboardLayout>
      {mediaValidation && (
        <MediaValidationErrorModal
          file={mediaValidation.file}
          violations={mediaValidation.violations}
          platforms={mediaValidation.platforms}
          onClose={() => setMediaValidation(null)}
          onContinue={
            mediaValidation.platforms.some(p =>
              !mediaValidation.violations.find(v => v.platform === p)
            )
              ? () => {
                  const pending = mediaValidation.pendingFiles;
                  setMediaValidation(null);
                  addFiles(pending, { skipValidation: true });
                }
              : undefined
          }
        />
      )}
      <div className="max-w-6xl mx-auto pb-12">

        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate('/bulk-upload')}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <FaArrowLeft />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Bulk Video Scheduling</h1>
            <p className="text-xs text-gray-500">Upload multiple videos and schedule them across all your accounts</p>
          </div>
        </div>

        {/* Connected accounts bar — always visible */}
        <div className="bg-white rounded-xl border border-gray-200 px-5 py-4 mb-6 shadow-sm">
          {accountsLoading ? (
            <div className="flex items-center gap-2 text-gray-400 text-xs py-1">
              <FaSpinner className="animate-spin text-xs" /> Loading accounts…
            </div>
          ) : accounts.length === 0 ? (
            <div className="flex items-center gap-2 text-amber-600 text-xs bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
              <FaExclamationCircle className="flex-shrink-0" />
              No connected accounts. Go to <a href="/settings" className="underline font-semibold ml-1">Settings → Accounts</a> to connect one.
            </div>
          ) : (
            <AccountSelector
              accounts={accounts}
              selectedAccounts={selectedAccounts}
              onToggle={toggleAccount}
              platformIcons={PLATFORM_ICONS}
              getAvatarColor={getAvatarColor}
            />
          )}
        </div>

        <div className="flex gap-6">
          {/* Left: video list */}
          <div className="flex-1 min-w-0 space-y-4">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl py-10 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors ${
                dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-green-300 hover:bg-green-50/30'
              }`}
            >
              <FaCloudUploadAlt className={`text-4xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
              <div className="text-center">
                <p className="text-sm font-semibold text-gray-600">
                  {dragging ? 'Drop videos here' : 'Click or drag & drop videos'}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">MP4, MOV, AVI, WebM supported</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                className="px-4 py-1.5 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
              >
                <FaPlus className="inline mr-1.5" />
                Add Videos
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              multiple
              className="hidden"
              onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}
            />

            {/* Video cards */}
            {videos.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Your Videos ({videos.length})
                </p>
                {videos.map((item, i) => (
                  <VideoCard
                    key={i}
                    item={item}
                    index={i}
                    onUpdate={updateVideo}
                    onRemove={removeVideo}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Right: Bulk Schedule Settings */}
          <div className="w-72 flex-shrink-0">
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm sticky top-20">
              <h3 className="text-sm font-bold text-gray-900 mb-4">Bulk Schedule Settings</h3>
              <p className="text-xs text-gray-500 mb-4 leading-relaxed">
                Set a common date, time and timezone to apply to all uploaded videos.
              </p>

              <div className="space-y-3 mb-4">
                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Date</label>
                  <div className="relative">
                    <FaCalendarAlt className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
                    <input
                      type="date"
                      value={bulkDate}
                      onChange={(e) => setBulkDate(e.target.value)}
                      className="w-full text-xs pl-7 pr-2 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Time</label>
                  <div className="relative">
                    <FaClock className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
                    <input
                      type="time"
                      value={bulkTime}
                      onChange={(e) => setBulkTime(e.target.value)}
                      className="w-full text-xs pl-7 pr-2 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Timezone</label>
                  <TimezoneSelect value={bulkTimezone} onChange={setBulkTimezone} />
                </div>
              </div>

              <button
                onClick={applyBulkSettings}
                className="w-full py-2 text-xs font-semibold border border-green-500 text-green-600 hover:bg-green-50 rounded-lg transition-colors mb-5"
              >
                Apply to All Videos
              </button>

              <div className="border-t border-gray-100 pt-5">
                <h4 className="text-xs font-bold text-gray-700 mb-3">Confirm &amp; Schedule All</h4>
                {selectedAccounts.length === 0 && (
                  <p className="text-[11px] text-amber-600 bg-amber-50 rounded-lg px-3 py-2 mb-3 border border-amber-100">
                    Select accounts above to enable scheduling
                  </p>
                )}
                <button
                  onClick={handleScheduleAll}
                  disabled={scheduling || !videos.length || !selectedAccounts.length}
                  className="w-full py-3 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow"
                >
                  {scheduling ? (
                    <><FaSpinner className="animate-spin" /> Scheduling…</>
                  ) : (
                    <>Schedule {videos.length || 0} Video{videos.length !== 1 ? 's' : ''}</>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default BulkVideoUpload;
