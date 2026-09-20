import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  FaScissors,
  FaYoutube,
  FaFire,
  FaSpinner,
  FaPlay,
  FaCheck,
  FaXmark,
  FaFilm,
  FaArrowUpRightFromSquare,
  FaTrash,
} from 'react-icons/fa6';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  createClippingJob,
  getClippingJob,
  getClippingJobs,
  deleteClippingJob,
} from '@/lib/api';

export default function VideoClipperModal({ open, onClose, accounts = [], onDraftCreated }) {
  const [activeTab, setActiveTab] = useState('new'); // 'new' | 'jobs'
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [numClips, setNumClips] = useState(3);
  const [fitMode, setFitMode] = useState('blur'); // 'blur' | 'crop'
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState('viral_yellow');
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  // Active or past jobs
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (open) {
      loadJobs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Poll active job while in progress
  useEffect(() => {
    let timer;
    if (activeJob && ['queued', 'downloading', 'transcribing', 'analyzing', 'rendering'].includes(activeJob.status)) {
      setPolling(true);
      timer = setInterval(async () => {
        try {
          const updated = await getClippingJob(activeJob.id);
          setActiveJob(updated);
          if (['completed', 'failed'].includes(updated.status)) {
            setPolling(false);
            loadJobs();
            if (updated.status === 'completed') {
              toast.success(`Generated ${updated.clips?.length || 0} vertical shorts!`);
            } else if (updated.status === 'failed') {
              toast.error(updated.error_message || 'Video clipping failed');
            }
          }
        } catch {
          // ignore poll error
        }
      }, 3000);
    } else {
      setPolling(false);
    }
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJob]);

  const loadJobs = async () => {
    try {
      const data = await getClippingJobs();
      setJobs(data || []);
      if (data && data.length > 0 && !activeJob) {
        // If there's an ongoing job, follow it
        const ongoing = data.find((j) => ['queued', 'downloading', 'transcribing', 'analyzing', 'rendering'].includes(j.status));
        if (ongoing) {
          setActiveJob(ongoing);
        }
      }
    } catch {
      // ignore
    }
  };

  const handleStartClipping = async (e) => {
    e.preventDefault();
    if (!youtubeUrl.trim() || (!youtubeUrl.includes('youtube.com') && !youtubeUrl.includes('youtu.be'))) {
      toast.error('Please enter a valid YouTube video link');
      return;
    }

    setSubmitting(true);
    try {
      const targetPlatforms = Array.from(
        new Set(
          accounts
            .filter((a) => selectedAccounts.includes(a.id))
            .map((a) => (a.platform || '').toLowerCase())
            .filter(Boolean)
        )
      );

      const payload = {
        youtube_url: youtubeUrl.trim(),
        num_clips: parseInt(numClips, 10),
        fit_mode: fitMode,
        burn_subtitles: burnSubtitles,
        subtitle_style: subtitleStyle,
        target_account_ids: selectedAccounts,
        target_platforms: targetPlatforms.length > 0 ? targetPlatforms : ['tiktok', 'instagram', 'youtube'],
        auto_create_drafts: true,
      };

      const job = await createClippingJob(payload);
      setActiveJob(job);
      setYoutubeUrl('');
      loadJobs();
      toast.success('Clipping job started! The AI engine is analyzing moments.');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to start clipping job');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteJob = async (jobId) => {
    try {
      await deleteClippingJob(jobId);
      if (activeJob?.id === jobId) {
        setActiveJob(null);
      }
      loadJobs();
      toast.success('Job deleted');
    } catch {
      toast.error('Failed to delete job');
    }
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="max-w-3xl rounded-3xl border-slate-200 dark:border-slate-800 dark:bg-slate-900 max-h-[90vh] overflow-y-auto">
        <DialogHeader className="text-left pb-3 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-slate-900 dark:text-white text-xl font-bold">
              <span className="p-2 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400">
                <FaScissors className="text-base" />
              </span>
              AI Video Clipper & Vertical Shorts
            </DialogTitle>
            <div className="flex gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs">
              <button
                type="button"
                onClick={() => setActiveTab('new')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                  activeTab === 'new'
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                Clip Video
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('jobs')}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                  activeTab === 'jobs'
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-xs'
                    : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                Clips Library ({jobs.length})
              </button>
            </div>
          </div>
          <DialogDescription className="text-xs text-slate-500 dark:text-slate-400 pt-1">
            Turn long YouTube podcasts, keynotes, and videos into high-engagement 9:16 vertical shorts with bold subtitles and automated drafts.
          </DialogDescription>
        </DialogHeader>

        {activeTab === 'new' ? (
          <div className="space-y-6 pt-2">
            {/* Live Progress Card if an active job is executing */}
            {activeJob && ['queued', 'downloading', 'transcribing', 'analyzing', 'rendering'].includes(activeJob.status) && (
              <div className="p-4 rounded-2xl border border-purple-200 bg-purple-50/70 dark:border-purple-900/60 dark:bg-purple-950/40 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FaSpinner className="animate-spin text-purple-600 text-sm" />
                    <span className="text-xs font-bold text-purple-950 dark:text-purple-200">
                      {activeJob.current_step}
                    </span>
                  </div>
                  <span className="text-xs font-bold text-purple-700 dark:text-purple-300">
                    {activeJob.progress}%
                  </span>
                </div>
                <div className="w-full bg-purple-200 dark:bg-purple-900/60 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-purple-600 h-2 transition-all duration-500 rounded-full"
                    style={{ width: `${activeJob.progress}%` }}
                  />
                </div>
                <p className="text-[11px] text-purple-800/80 dark:text-purple-300/80">
                  Target: <span className="font-semibold">{activeJob.video_title || activeJob.youtube_url}</span>
                </p>
              </div>
            )}

            {/* If active job just completed */}
            {activeJob && activeJob.status === 'completed' && activeJob.clips?.length > 0 && (
              <div className="p-4 rounded-2xl border border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/60 dark:bg-emerald-950/40 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-200 font-bold text-sm">
                    <FaCheck className="text-emerald-600" />
                    Generated {activeJob.clips.length} Standalone Shorts!
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveJob(null)}
                    className="text-xs text-emerald-700 hover:text-emerald-900 font-medium"
                  >
                    Start another
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {activeJob.clips.map((clip) => (
                    <div
                      key={clip.clip_id}
                      className="p-3 rounded-xl border border-emerald-100 bg-white dark:border-slate-800 dark:bg-slate-800 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-600 bg-amber-50 dark:bg-amber-950/60 px-2 py-0.5 rounded-md">
                          <FaFire className="text-[10px]" /> {clip.viral_score}% Viral Score
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">
                          {clip.duration_sec}s
                        </span>
                      </div>
                      <p className="text-xs font-bold text-slate-900 dark:text-white line-clamp-1">
                        {clip.title}
                      </p>
                      <p className="text-[11px] text-slate-600 dark:text-slate-400 line-clamp-2 italic">
                        "{clip.hook || clip.caption}"
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <form onSubmit={handleStartClipping} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                  <FaYoutube className="text-red-500 text-sm" />
                  YouTube Video Link
                </label>
                <Input
                  type="url"
                  required
                  placeholder="https://www.youtube.com/watch?v=... or youtu.be/..."
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  className="dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Clips to Extract: <strong className="text-purple-600">{numClips} shorts</strong>
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    value={numClips}
                    onChange={(e) => setNumClips(e.target.value)}
                    className="w-full accent-purple-600 cursor-pointer"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>1 clip</span>
                    <span>3 clips</span>
                    <span>5 clips</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Vertical 9:16 Fit Mode
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setFitMode('blur')}
                      className={`p-2 rounded-xl text-xs font-semibold border text-center transition-all ${
                        fitMode === 'blur'
                          ? 'border-purple-600 bg-purple-50 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 font-bold'
                          : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      🌫️ Blur Pad
                    </button>
                    <button
                      type="button"
                      onClick={() => setFitMode('crop')}
                      className={`p-2 rounded-xl text-xs font-semibold border text-center transition-all ${
                        fitMode === 'crop'
                          ? 'border-purple-600 bg-purple-50 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 font-bold'
                          : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                      }`}
                    >
                      ✂️ Center Crop
                    </button>
                  </div>
                </div>
              </div>

              {/* Subtitles & Styling */}
              <div className="grid gap-4 sm:grid-cols-2 p-3.5 rounded-2xl border border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-850">
                <div className="space-y-1">
                  <label className="flex items-center gap-2 cursor-pointer text-xs font-bold text-slate-800 dark:text-slate-200">
                    <input
                      type="checkbox"
                      checked={burnSubtitles}
                      onChange={(e) => setBurnSubtitles(e.target.checked)}
                      className="rounded text-purple-600 focus:ring-purple-500"
                    />
                    🔥 Burn Bold Animated Subtitles
                  </label>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 pl-5">
                    Embeds high-visibility karaoke captions tuned for mobile playback without sound.
                  </p>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Subtitle Theme
                  </label>
                  <select
                    value={subtitleStyle}
                    disabled={!burnSubtitles}
                    onChange={(e) => setSubtitleStyle(e.target.value)}
                    className="w-full text-xs rounded-xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  >
                    <option value="viral_yellow">🟡 Viral Yellow (TikTok Trend)</option>
                    <option value="clean_white">⚪ Clean Minimalist White</option>
                    <option value="modern_cyan">🔷 Electric Cyan</option>
                  </select>
                </div>
              </div>

              {/* Target Channel Destination */}
              {accounts && accounts.length > 0 && (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Auto-create Drafts in Social Accounts (Optional)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {accounts.map((acc) => {
                      const isSelected = selectedAccounts.includes(acc.id);
                      return (
                        <button
                          key={acc.id}
                          type="button"
                          onClick={() =>
                            setSelectedAccounts((prev) =>
                              isSelected ? prev.filter((id) => id !== acc.id) : [...prev, acc.id]
                            )
                          }
                          className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                            isSelected
                              ? 'border-purple-600 bg-purple-50 text-purple-700 dark:border-purple-600 dark:bg-purple-950 dark:text-purple-300 font-bold'
                              : 'border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300'
                          }`}
                        >
                          <span>{acc.platform_username || acc.account_name || acc.platform}</span>
                          <span className="text-[10px] opacity-70">({acc.platform})</span>
                          {isSelected && <span className="text-[10px] text-purple-600">✓</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <DialogFooter className="pt-2">
                <Button type="button" variant="outline" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={submitting || polling || !youtubeUrl.trim()}
                  className="bg-purple-600 text-white hover:bg-purple-700 font-bold"
                >
                  {submitting ? (
                    <FaSpinner className="animate-spin mr-2" />
                  ) : (
                    <FaScissors className="mr-2 text-xs" />
                  )}
                  Extract {numClips} Viral Shorts
                </Button>
              </DialogFooter>
            </form>
          </div>
        ) : (
          /* Jobs Library Tab */
          <div className="space-y-4 pt-2">
            {jobs.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
                No video clipping jobs created yet.
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map((j) => (
                  <div
                    key={j.id}
                    className="p-4 rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-850 space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-900 dark:text-white line-clamp-1">
                            {j.video_title || j.youtube_url}
                          </span>
                          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                            j.status === 'completed'
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                              : j.status === 'failed'
                              ? 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
                              : 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300'
                          }`}>
                            {j.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
                          {new Date(j.created_at).toLocaleString()} • {j.clips?.length || 0} clips
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        {j.status === 'completed' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setActiveJob(j);
                              setActiveTab('new');
                            }}
                            className="text-xs"
                          >
                            View Clips
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDeleteJob(j.id)}
                          className="text-rose-600 hover:text-rose-700"
                        >
                          <FaTrash className="text-xs" />
                        </Button>
                      </div>
                    </div>

                    {j.clips && j.clips.length > 0 && (
                      <div className="grid gap-2 sm:grid-cols-2 pt-1 border-t border-slate-100 dark:border-slate-800">
                        {j.clips.map((clip) => (
                          <div
                            key={clip.clip_id}
                            className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 flex items-center justify-between text-xs"
                          >
                            <span className="font-semibold text-slate-800 dark:text-slate-200 truncate pr-2">
                              {clip.title}
                            </span>
                            <span className="shrink-0 text-amber-600 font-bold text-[11px]">
                              🔥 {clip.viral_score}%
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
