import React, { useEffect, useRef, useState } from 'react';
import { FaMusic, FaPause, FaPlay, FaSpinner, FaUpload } from 'react-icons/fa';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import env from '@/env';
import {
  getAudioAssets,
  renderVideoAudio,
  uploadMedia,
  waitForAudioRenderReady,
  waitForUploadReady,
} from '@/lib/api';

const waveformBars = Array.from({ length: 52 }, (_, index) => {
  const value = Math.sin(index * 1.7) * 0.5 + Math.cos(index * 0.47) * 0.35 + 0.75;
  return Math.max(18, Math.min(92, Math.round(value * 56)));
});

const formatDuration = (seconds) => {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return '0:00';
  const mins = Math.floor(value / 60);
  const secs = Math.floor(value % 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
};

const audioLabel = (asset) => (
  asset?.source_label
  || asset?.filename
  || asset?.original_filename
  || asset?.media_id
  || 'Audio track'
);

const toSeconds = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(parsed, 0) : 0;
};

const AddAudioDialog = ({
  open,
  onOpenChange,
  video,
  onRenderComplete,
}) => {
  const [audioAssets, setAudioAssets] = useState([]);
  const [selectedAudioId, setSelectedAudioId] = useState('');
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [rendering, setRendering] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState('');
  const [offset, setOffset] = useState(0);
  const [loopToEnd, setLoopToEnd] = useState(true);
  const [fadeIn, setFadeIn] = useState(0.4);
  const [fadeOut, setFadeOut] = useState(0.8);
  const [originalVolume, setOriginalVolume] = useState(0.35);
  const [selectedVolume, setSelectedVolume] = useState(0.9);
  const [muteOriginal, setMuteOriginal] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const videoRef = useRef(null);
  const audioRef = useRef(null);
  const fileInputRef = useRef(null);
  const delayedAudioTimerRef = useRef(null);
  const licensedAudioEnabled = env.AUDIO_PROVIDER_ENABLED === 'true';
  const licensedAudioProviderName = env.AUDIO_PROVIDER_NAME || 'licensed audio provider';

  const selectedAudio = audioAssets.find((asset) => asset.media_id === selectedAudioId) || null;
  const canRender = Boolean(video?.mediaId && selectedAudio?.media_id && !rendering && !uploadingAudio);

  useEffect(() => {
    if (!open) return;
    setLoadingLibrary(true);
    getAudioAssets()
      .then((assets) => {
        const normalized = Array.isArray(assets) ? assets : [];
        setAudioAssets(normalized);
        if (!selectedAudioId && normalized[0]?.media_id) {
          setSelectedAudioId(normalized[0].media_id);
        }
      })
      .catch(() => toast.error('Failed to load audio library'))
      .finally(() => setLoadingLibrary(false));
  }, [open, selectedAudioId]);

  useEffect(() => {
    if (!open) {
      setIsPreviewing(false);
      setRenderProgress(0);
      clearTimeout(delayedAudioTimerRef.current);
    }
  }, [open]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = muteOriginal ? 0 : originalVolume;
      videoRef.current.muted = muteOriginal;
    }
    if (audioRef.current) {
      audioRef.current.volume = selectedVolume;
    }
  }, [muteOriginal, originalVolume, selectedVolume]);

  const stopPreview = () => {
    clearTimeout(delayedAudioTimerRef.current);
    if (videoRef.current) videoRef.current.pause();
    if (audioRef.current) audioRef.current.pause();
    setIsPreviewing(false);
  };

  const startPreview = async () => {
    if (!videoRef.current || !audioRef.current || !selectedAudio?.media_url) return;
    clearTimeout(delayedAudioTimerRef.current);
    const videoEl = videoRef.current;
    const audioEl = audioRef.current;
    videoEl.currentTime = 0;
    videoEl.volume = muteOriginal ? 0 : originalVolume;
    videoEl.muted = muteOriginal;
    audioEl.volume = selectedVolume;
    audioEl.currentTime = trimStart;
    setIsPreviewing(true);
    try {
      await videoEl.play();
      if (offset > 0) {
        delayedAudioTimerRef.current = setTimeout(() => {
          audioEl.currentTime = trimStart;
          audioEl.play().catch(() => {});
        }, offset * 1000);
      } else {
        await audioEl.play();
      }
    } catch {
      setIsPreviewing(false);
      toast.error('Preview could not start. Try clicking play again.');
    }
  };

  const handleAudioTimeUpdate = () => {
    const audioEl = audioRef.current;
    if (!audioEl) return;
    const end = trimEnd === '' ? null : toSeconds(trimEnd);
    if (end && audioEl.currentTime >= end) {
      if (loopToEnd) {
        audioEl.currentTime = trimStart;
        audioEl.play().catch(() => {});
      } else {
        audioEl.pause();
      }
    }
  };

  const handleAudioUpload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('audio/')) {
      toast.error('Select an audio file');
      return;
    }
    setUploadingAudio(true);
    setUploadProgress(0);
    try {
      const upload = await uploadMedia(file, (progressEvent) => {
        const total = progressEvent.total || file.size || 1;
        setUploadProgress(Math.round(((progressEvent.loaded || 0) * 100) / total));
      });
      const asset = await waitForUploadReady(upload.media_job_id, {
        onPoll: (polled) => {
          if (polled?.status === 'processing') setUploadProgress(95);
        },
      });
      const normalizedAsset = {
        ...asset,
        source_label: asset.source_label || file.name,
      };
      setAudioAssets((prev) => [normalizedAsset, ...prev.filter((item) => item.media_id !== asset.media_id)]);
      setSelectedAudioId(asset.media_id);
      toast.success('Audio uploaded');
    } catch (error) {
      toast.error(error?.message || 'Failed to upload audio');
    } finally {
      setUploadingAudio(false);
      setUploadProgress(0);
    }
  };

  const handleRender = async () => {
    if (!canRender) return;
    const trimEndSeconds = trimEnd === '' ? null : toSeconds(trimEnd);
    if (trimEndSeconds !== null && trimEndSeconds <= trimStart) {
      toast.error('Trim end must be after trim start');
      return;
    }
    setRendering(true);
    setRenderProgress(8);
    try {
      const render = await renderVideoAudio(video.mediaId, {
        audio_media_id: selectedAudio.media_id,
        trim_start_ms: Math.round(trimStart * 1000),
        trim_end_ms: trimEndSeconds === null ? null : Math.round(trimEndSeconds * 1000),
        video_offset_ms: Math.round(offset * 1000),
        loop_to_video_end: loopToEnd,
        fade_in_ms: Math.round(fadeIn * 1000),
        fade_out_ms: Math.round(fadeOut * 1000),
        original_volume: muteOriginal ? 0 : originalVolume,
        selected_volume: selectedVolume,
        mute_original: muteOriginal,
        normalize_audio: true,
      });
      const renderedAsset = await waitForAudioRenderReady(render.render_job_id, {
        onPoll: (asset) => {
          if (asset?.status === 'processing') {
            setRenderProgress((current) => Math.min(current + 12, 88));
          }
        },
      });
      setRenderProgress(100);
      await onRenderComplete?.(renderedAsset);
      toast.success('Audio added to video');
      onOpenChange?.(false);
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || 'Failed to render audio');
    } finally {
      setRendering(false);
      setRenderProgress(0);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => {
      if (!value) stopPreview();
      onOpenChange?.(value);
    }}>
      <DialogContent className="max-w-5xl p-0 overflow-hidden">
        <DialogHeader className="border-b border-gray-200 px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2 text-lg">
            <FaMusic className="text-blue-600" />
            Add audio to video
          </DialogTitle>
        </DialogHeader>

        <div className="grid gap-0 md:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-5 border-r border-gray-200 bg-slate-50/70 p-6">
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">Audio source</p>
                  <p className="text-xs text-gray-500">Upload your own track or reuse audio from your library.</p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingAudio || rendering}
                >
                  {uploadingAudio ? <FaSpinner className="mr-2 animate-spin" /> : <FaUpload className="mr-2" />}
                  Upload audio
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={handleAudioUpload}
                />
              </div>
              {uploadingAudio && (
                <div className="mb-3">
                  <Progress value={uploadProgress} className="h-2" />
                  <p className="mt-1 text-xs text-gray-500">Uploading audio: {uploadProgress}%</p>
                </div>
              )}
              {loadingLibrary ? (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-sm text-gray-500">
                  Loading audio library...
                </div>
              ) : audioAssets.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-sm text-gray-500">
                  No audio tracks yet. Upload an MP3, M4A, WAV, AAC, OGG, or FLAC file to begin.
                </div>
              ) : (
                <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
                  {audioAssets.map((asset) => (
                    <button
                      type="button"
                      key={asset.media_id}
                      onClick={() => setSelectedAudioId(asset.media_id)}
                      className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                        selectedAudioId === asset.media_id
                          ? 'border-blue-400 bg-blue-50'
                          : 'border-gray-200 bg-white hover:border-gray-300'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-semibold text-gray-900">{audioLabel(asset)}</span>
                        <span className="shrink-0 text-xs text-gray-500">{formatDuration(asset.duration_seconds)}</span>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-gray-500">{asset.mime_type || 'audio'}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-gray-900">Licensed audio</p>
                  <p className="mt-1 text-xs text-gray-500">
                    {licensedAudioEnabled
                      ? `${licensedAudioProviderName} search can be wired here when catalog terms are finalized.`
                      : 'Provider search is not configured. Use uploaded or library audio for now.'}
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" disabled>
                  Search
                </Button>
              </div>
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-900">Trim and align</p>
                <span className="text-xs text-gray-500">Video length {formatDuration(video?.duration)}</span>
              </div>
              <div className="rounded-xl bg-slate-950 px-3 py-3">
                <div className="flex h-16 items-end gap-1">
                  {waveformBars.map((height, index) => (
                    <span
                      key={index}
                      className="flex-1 rounded-full bg-cyan-300/80"
                      style={{ height: `${height}%` }}
                    />
                  ))}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Trim start (sec)</Label>
                  <Input type="number" min="0" step="0.1" value={trimStart} onChange={(event) => setTrimStart(toSeconds(event.target.value))} />
                </div>
                <div>
                  <Label className="text-xs">Trim end (sec)</Label>
                  <Input type="number" min="0" step="0.1" value={trimEnd} onChange={(event) => setTrimEnd(event.target.value)} placeholder="End" />
                </div>
                <div>
                  <Label className="text-xs">Start at video time (sec)</Label>
                  <Input type="number" min="0" step="0.1" value={offset} onChange={(event) => setOffset(toSeconds(event.target.value))} />
                </div>
                <div>
                  <Label className="text-xs">Fade in / out (sec)</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="number" min="0" step="0.1" value={fadeIn} onChange={(event) => setFadeIn(toSeconds(event.target.value))} />
                    <Input type="number" min="0" step="0.1" value={fadeOut} onChange={(event) => setFadeOut(toSeconds(event.target.value))} />
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">Loop selected audio to the end</p>
                  <p className="text-xs text-gray-500">Useful when the track is shorter than the video.</p>
                </div>
                <Switch checked={loopToEnd} onCheckedChange={setLoopToEnd} />
              </div>
            </div>
          </div>

          <div className="space-y-5 p-6">
            <div className="overflow-hidden rounded-2xl border border-gray-200 bg-black shadow-sm">
              {video?.url ? (
                <video
                  ref={videoRef}
                  src={video.url}
                  className="aspect-video w-full object-contain"
                  playsInline
                  onPause={() => {
                    clearTimeout(delayedAudioTimerRef.current);
                    audioRef.current?.pause();
                    setIsPreviewing(false);
                  }}
                  onEnded={stopPreview}
                />
              ) : (
                <div className="flex aspect-video items-center justify-center text-sm text-gray-400">No video selected</div>
              )}
              {selectedAudio?.media_url && (
                <audio
                  ref={audioRef}
                  src={selectedAudio.media_url}
                  preload="metadata"
                  onTimeUpdate={handleAudioTimeUpdate}
                />
              )}
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">Preview mix</p>
                  <p className="text-xs text-gray-500">Browser preview approximates the final render.</p>
                </div>
                <Button type="button" variant="outline" onClick={isPreviewing ? stopPreview : startPreview} disabled={!selectedAudio?.media_url}>
                  {isPreviewing ? <FaPause className="mr-2" /> : <FaPlay className="mr-2" />}
                  {isPreviewing ? 'Pause' : 'Play'}
                </Button>
              </div>

              <div className="mt-5 space-y-5">
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                    <span>Original video audio</span>
                    <span>{muteOriginal ? 'Muted' : `${Math.round(originalVolume * 100)}%`}</span>
                  </div>
                  <Slider
                    value={[Math.round(originalVolume * 100)]}
                    min={0}
                    max={100}
                    step={1}
                    disabled={muteOriginal}
                    onValueChange={(value) => setOriginalVolume((value?.[0] || 0) / 100)}
                  />
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                    <span>Selected audio</span>
                    <span>{Math.round(selectedVolume * 100)}%</span>
                  </div>
                  <Slider
                    value={[Math.round(selectedVolume * 100)]}
                    min={0}
                    max={150}
                    step={1}
                    onValueChange={(value) => setSelectedVolume((value?.[0] || 0) / 100)}
                  />
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">Mute original audio</p>
                  <p className="text-xs text-gray-500">Replace existing video sound with the selected track.</p>
                </div>
                <Switch checked={muteOriginal} onCheckedChange={setMuteOriginal} />
              </div>
            </div>

            {rendering && (
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
                <div className="mb-2 flex items-center justify-between text-sm font-semibold text-blue-800">
                  <span>Rendering final video</span>
                  <span>{renderProgress}%</span>
                </div>
                <Progress value={renderProgress} className="h-2" />
                <p className="mt-2 text-xs text-blue-700">Keep this page open while the new video asset is prepared.</p>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="border-t border-gray-200 px-6 py-4">
          <Button type="button" variant="outline" onClick={() => onOpenChange?.(false)} disabled={rendering}>
            Cancel
          </Button>
          <Button type="button" onClick={handleRender} disabled={!canRender}>
            {rendering && <FaSpinner className="mr-2 animate-spin" />}
            Render and use video
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default AddAudioDialog;
