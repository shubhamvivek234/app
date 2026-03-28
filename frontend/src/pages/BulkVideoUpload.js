import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { getSocialAccounts } from '@/lib/api';
import AccountSelector from '@/components/composer/AccountSelector';
import { toast } from 'sonner';
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

const TIMEZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'Europe/London', 'Europe/Paris', 'Asia/Kolkata',
  'Asia/Tokyo', 'Australia/Sydney',
];

const formatFileSize = (bytes) => {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

  // Bulk settings
  const [bulkDate, setBulkDate] = useState('');
  const [bulkTime, setBulkTime] = useState('');
  const [bulkTimezone, setBulkTimezone] = useState('UTC');

  const fileInputRef = useRef(null);

  React.useEffect(() => {
    setAccountsLoading(true);
    getSocialAccounts()
      .then((res) => setAccounts(Array.isArray(res) ? res : (res.accounts || [])))
      .catch(() => toast.error('Failed to load connected accounts'))
      .finally(() => setAccountsLoading(false));
  }, []);

  const addFiles = useCallback((files) => {
    const videoFiles = Array.from(files).filter((f) => f.type.startsWith('video/'));
    if (!videoFiles.length) {
      toast.error('Please upload video files only');
      return;
    }
    const newItems = videoFiles.map((file) => ({
      file,
      caption: '',
      date: '',
      time: '',
      previewUrl: URL.createObjectURL(file),
    }));
    setVideos((prev) => [...prev, ...newItems]);
  }, []);

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
          scheduledTime = new Date(`${video.date}T${video.time}:00`).toISOString();
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
                  <div className="relative">
                    <FaGlobe className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
                    <select
                      value={bulkTimezone}
                      onChange={(e) => setBulkTimezone(e.target.value)}
                      className="w-full text-xs pl-7 pr-2 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-green-400 focus:bg-white transition-colors appearance-none"
                    >
                      {TIMEZONES.map((tz) => (
                        <option key={tz} value={tz}>{tz}</option>
                      ))}
                    </select>
                  </div>
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
