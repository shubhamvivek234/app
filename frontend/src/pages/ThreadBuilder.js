import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { createPost, uploadMedia, getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { useEffect } from 'react';
import {
  FaXTwitter, FaPlus, FaTrash, FaImage, FaXmark, FaClock,
  FaCheck, FaGripVertical,
} from 'react-icons/fa6';
import { FaBookmark } from 'react-icons/fa';

const TWEET_MAX = 280;

const genId = () => Math.random().toString(36).slice(2, 9);

const defaultTweet = () => ({ id: genId(), content: '', media_url: null, uploading: false });

// ── Character count ring ──────────────────────────────────────────────────────
const CharRing = ({ count, max = TWEET_MAX }) => {
  const remaining = max - count;
  const pct = Math.min(count / max, 1);
  const r = 10;
  const circ = 2 * Math.PI * r;
  const dash = pct * circ;
  const color = remaining <= 0 ? '#ef4444' : remaining <= 20 ? '#f59e0b' : '#22c55e';

  if (count === 0) return null;
  return (
    <div className="relative flex items-center justify-center w-7 h-7">
      <svg className="absolute" width="28" height="28" viewBox="0 0 28 28">
        <circle cx="14" cy="14" r={r} fill="none" stroke="#e5e7eb" strokeWidth="2.5" />
        <circle
          cx="14" cy="14" r={r}
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 14 14)"
        />
      </svg>
      {remaining <= 20 && (
        <span className={`text-[10px] font-bold ${remaining <= 0 ? 'text-red-500' : 'text-amber-500'}`}>
          {remaining}
        </span>
      )}
    </div>
  );
};

// ── Tweet composer block ──────────────────────────────────────────────────────
const TweetBlock = ({ tweet, index, total, onChange, onDelete, onAddAfter, onImageUpload, onRemoveImage }) => {
  const fileRef = useRef(null);
  const remaining = TWEET_MAX - tweet.content.length;

  return (
    <div className="relative flex gap-3 group">
      {/* Thread line */}
      <div className="flex flex-col items-center">
        <div className="w-9 h-9 rounded-full bg-white border-2 border-gray-200 flex items-center justify-center flex-shrink-0">
          <FaXTwitter className="text-gray-600 text-sm" />
        </div>
        {index < total - 1 && (
          <div className="w-0.5 bg-gray-200 flex-1 my-1" style={{ minHeight: 24 }} />
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 pb-4">
        <div className={`rounded-xl border transition-colors ${remaining < 0 ? 'border-red-300' : 'border-gray-200'} bg-white p-3`}>
          <textarea
            rows={3}
            value={tweet.content}
            onChange={(e) => onChange(tweet.id, 'content', e.target.value)}
            placeholder={index === 0 ? "Start your thread here…" : "Continue the thread…"}
            className="w-full text-sm text-gray-800 resize-none focus:outline-none placeholder:text-gray-300 leading-relaxed"
          />

          {/* Image preview */}
          {tweet.media_url && (
            <div className="relative mt-2 rounded-lg overflow-hidden border border-gray-200 w-32 h-24">
              <img src={tweet.media_url} alt="" className="w-full h-full object-cover" />
              <button
                onClick={() => onRemoveImage(tweet.id)}
                className="absolute top-1 right-1 w-5 h-5 bg-black/60 hover:bg-black/80 text-white rounded-full flex items-center justify-center"
              >
                <FaXmark className="text-[9px]" />
              </button>
            </div>
          )}

          {/* Toolbar */}
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100">
            <div className="flex items-center gap-1">
              {/* Image upload */}
              {!tweet.media_url && (
                <>
                  <input ref={fileRef} type="file" accept="image/*" className="hidden"
                    onChange={(e) => { if (e.target.files?.[0]) { onImageUpload(tweet.id, e.target.files[0]); e.target.value = ''; } }} />
                  <button
                    onClick={() => fileRef.current?.click()}
                    disabled={tweet.uploading}
                    title="Add image"
                    className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    {tweet.uploading ? (
                      <div className="w-4 h-4 border-2 border-blue-300 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <FaImage className="text-sm" />
                    )}
                  </button>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <CharRing count={tweet.content.length} />
              {total > 1 && (
                <button
                  onClick={() => onDelete(tweet.id)}
                  className="p-1.5 text-gray-300 hover:text-red-400 hover:bg-red-50 rounded-lg transition-colors"
                  title="Remove tweet"
                >
                  <FaTrash className="text-xs" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Add tweet below */}
        <button
          onClick={() => onAddAfter(index)}
          className="mt-2 flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-green-500 transition-colors"
        >
          <FaPlus className="text-[10px]" />
          Add tweet
        </button>
      </div>
    </div>
  );
};

// ── Preview panel ─────────────────────────────────────────────────────────────
const PreviewPanel = ({ tweets, handle = 'yourhandle' }) => {
  const valid = tweets.filter((t) => t.content.trim() || t.media_url);
  if (!valid.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-300 text-sm gap-2">
        <FaXTwitter className="text-3xl" />
        <span>Thread preview</span>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {valid.map((tweet, i) => (
        <div key={tweet.id} className="flex gap-3 relative">
          {/* Avatar + line */}
          <div className="flex flex-col items-center">
            <div className="w-9 h-9 rounded-full bg-white border border-gray-200 flex items-center justify-center flex-shrink-0 text-xs font-bold text-gray-500">
              {handle[0].toUpperCase()}
            </div>
            {i < valid.length - 1 && (
              <div className="w-0.5 bg-gray-200 flex-1 my-1" style={{ minHeight: 20 }} />
            )}
          </div>
          {/* Content */}
          <div className="flex-1 pb-4">
            <div className="flex items-baseline gap-1.5 mb-1">
              <span className="text-xs font-bold text-gray-900">@{handle}</span>
              <span className="text-[10px] text-gray-400">· now</span>
            </div>
            {tweet.content && (
              <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{tweet.content}</p>
            )}
            {tweet.media_url && (
              <img src={tweet.media_url} alt="" className="mt-2 rounded-xl border border-gray-200 w-full max-h-40 object-cover" />
            )}
            {/* Like/retweet row */}
            <div className="flex items-center gap-4 mt-2 text-gray-400">
              {['💬', '🔁', '❤️'].map((e) => (
                <span key={e} className="text-xs">{e} 0</span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

// ── Scheduling panel ──────────────────────────────────────────────────────────
const SchedulePanel = ({ scheduledTime, onScheduledTimeChange }) => (
  <div className="flex items-center gap-2">
    <FaClock className="text-gray-400 text-sm flex-shrink-0" />
    <input
      type="datetime-local"
      value={scheduledTime}
      onChange={(e) => onScheduledTimeChange(e.target.value)}
      className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-green-300 text-gray-600"
    />
    {scheduledTime && (
      <button onClick={() => onScheduledTimeChange('')} className="text-gray-400 hover:text-gray-600">
        <FaXmark className="text-xs" />
      </button>
    )}
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────
const ThreadBuilder = () => {
  const navigate = useNavigate();
  const [tweets, setTweets] = useState([defaultTweet()]);
  const [scheduledTime, setScheduledTime] = useState('');
  const [twitterAccounts, setTwitterAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSocialAccounts().then((accs) => {
      const tw = (Array.isArray(accs) ? accs : []).filter((a) => a.platform === 'twitter');
      setTwitterAccounts(tw);
      if (tw.length === 1) setSelectedAccount(tw[0].id);
    }).catch(() => {});
  }, []);

  // ── Tweet mutations ──────────────────────────────────────────────────────────
  const updateTweet = useCallback((id, key, value) => {
    setTweets((prev) => prev.map((t) => (t.id === id ? { ...t, [key]: value } : t)));
  }, []);

  const addAfter = useCallback((index) => {
    setTweets((prev) => {
      const next = [...prev];
      next.splice(index + 1, 0, defaultTweet());
      return next;
    });
  }, []);

  const removeTweet = useCallback((id) => {
    setTweets((prev) => prev.length > 1 ? prev.filter((t) => t.id !== id) : prev);
  }, []);

  const handleImageUpload = useCallback(async (id, file) => {
    updateTweet(id, 'uploading', true);
    try {
      const res = await uploadMedia(file);
      updateTweet(id, 'media_url', res.url);
    } catch {
      toast.error('Image upload failed');
    } finally {
      updateTweet(id, 'uploading', false);
    }
  }, [updateTweet]);

  const removeImage = useCallback((id) => updateTweet(id, 'media_url', null), [updateTweet]);

  // ── Validation ───────────────────────────────────────────────────────────────
  const validTweets = tweets.filter((t) => t.content.trim() || t.media_url);
  const hasOverflow = tweets.some((t) => t.content.length > TWEET_MAX);
  const canSubmit = validTweets.length > 0 && !hasOverflow && !saving;

  // ── Save / Schedule ──────────────────────────────────────────────────────────
  const handleSave = async (schedule = false) => {
    if (!canSubmit) return;
    if (schedule && !scheduledTime) { toast.error('Pick a date and time to schedule'); return; }

    setSaving(true);
    try {
      // First tweet content becomes the post `content` (summary)
      const firstContent = validTweets[0].content || `Thread (${validTweets.length} tweets)`;
      const cleanTweets = validTweets.map(({ id, uploading, ...rest }) => rest);

      await createPost({
        content: firstContent,
        post_type: 'thread',
        platforms: ['twitter'],
        accounts: selectedAccount ? [selectedAccount] : [],
        media_urls: validTweets.filter((t) => t.media_url).map((t) => t.media_url),
        thread_tweets: cleanTweets,
        scheduled_time: schedule && scheduledTime
          ? new Date(scheduledTime).toISOString()
          : undefined,
      });

      toast.success(schedule ? 'Thread scheduled ✓' : 'Thread saved as draft ✓');
      navigate('/content');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save thread');
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <FaXTwitter className="text-gray-900 text-lg" />
            <h1 className="text-xl font-bold text-gray-900">Thread Builder</h1>
            <span className="text-xs font-medium text-gray-400 bg-white border border-gray-200 px-2 py-0.5 rounded-full">
              {validTweets.length} tweet{validTweets.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        <div className="flex gap-6">
          {/* ── Left: Composer ── */}
          <div className="flex-1 min-w-0">
            {/* Account selector */}
            {twitterAccounts.length > 1 && (
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Post as</label>
                <select
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300 bg-white"
                >
                  <option value="">Any connected account</option>
                  {twitterAccounts.map((a) => (
                    <option key={a.id} value={a.id}>@{a.platform_username || a.id}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Tweet blocks */}
            <div>
              {tweets.map((tweet, i) => (
                <TweetBlock
                  key={tweet.id}
                  tweet={tweet}
                  index={i}
                  total={tweets.length}
                  onChange={updateTweet}
                  onDelete={removeTweet}
                  onAddAfter={addAfter}
                  onImageUpload={handleImageUpload}
                  onRemoveImage={removeImage}
                />
              ))}
            </div>

            {/* Validation warning */}
            {hasOverflow && (
              <div className="flex items-center gap-2 text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2 mt-2">
                One or more tweets exceed 280 characters. Please shorten them before saving.
              </div>
            )}

            {/* Scheduling + action row */}
            <div className="mt-4 pt-4 border-t border-gray-100 space-y-3">
              <SchedulePanel
                scheduledTime={scheduledTime}
                onScheduledTimeChange={setScheduledTime}
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleSave(true)}
                  disabled={!canSubmit || !scheduledTime}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg disabled:opacity-50 transition-colors"
                >
                  <FaClock className="text-xs" />
                  {saving ? 'Scheduling…' : 'Schedule Thread'}
                </button>
                <button
                  onClick={() => handleSave(false)}
                  disabled={!canSubmit}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50 rounded-lg disabled:opacity-50 transition-colors"
                >
                  <FaBookmark className="text-xs" />
                  {saving ? 'Saving…' : 'Save Draft'}
                </button>
              </div>
            </div>
          </div>

          {/* ── Right: Preview ── */}
          <div className="w-80 flex-shrink-0">
            <div className="sticky top-6">
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
                  <FaXTwitter className="text-sm text-gray-700" />
                  <span className="text-xs font-semibold text-gray-600">Thread Preview</span>
                </div>
                <div className="px-4 py-4 max-h-[600px] overflow-y-auto">
                  <PreviewPanel
                    tweets={tweets}
                    handle={twitterAccounts.find((a) => a.id === selectedAccount)?.platform_username || 'you'}
                  />
                </div>
              </div>

              {/* Tips */}
              <div className="mt-4 bg-blue-50 rounded-xl border border-blue-100 px-4 py-3 space-y-1.5">
                <p className="text-xs font-semibold text-blue-700">Tips</p>
                <ul className="text-xs text-blue-600 space-y-1 list-disc list-inside">
                  <li>Each tweet is limited to 280 characters</li>
                  <li>Add images to individual tweets</li>
                  <li>Click "Add tweet" to extend your thread</li>
                  <li>Empty tweets are skipped when posting</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ThreadBuilder;
