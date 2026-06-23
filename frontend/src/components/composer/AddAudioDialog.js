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
  cleanupTemporaryAudio,
  getAudioAssets,
  renderVideoAudio,
  uploadMedia,
  waitForAudioRenderReady,
  waitForUploadReady,
} from '@/lib/api';

const fallbackWaveformBars = Array.from({ length: 64 }, (_, index) => {
  const value = Math.sin(index * 1.7) * 0.5 + Math.cos(index * 0.47) * 0.35 + 0.75;
  return Math.max(18, Math.min(92, Math.round(value * 56)));
});

const waveformPeaksToBars = (peaks) => {
  if (!Array.isArray(peaks) || peaks.length === 0) return null;
  const normalized = peaks
    .map((peak) => Number(peak))
    .filter((peak) => Number.isFinite(peak));
  if (normalized.length === 0) return null;
  const max = Math.max(...normalized, 1);
  return normalized.map((peak) => Math.max(14, Math.min(96, Math.round((peak / max) * 92))));
};

const buildWaveformBars = async (url, barCount = 64) => {
  if (!url || typeof window === 'undefined') return fallbackWaveformBars;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return fallbackWaveformBars;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Unable to load audio waveform');
  const buffer = await response.arrayBuffer();
  const audioContext = new AudioContextCtor();
  try {
    const audioBuffer = await audioContext.decodeAudioData(buffer);
    const channelData = audioBuffer.getChannelData(0);
    const samplesPerBar = Math.max(1, Math.floor(channelData.length / barCount));
    const bars = Array.from({ length: barCount }, (_, index) => {
      const start = index * samplesPerBar;
      const end = Math.min(channelData.length, start + samplesPerBar);
      let sum = 0;
      for (let cursor = start; cursor < end; cursor += 1) {
        sum += channelData[cursor] * channelData[cursor];
      }
      const rms = Math.sqrt(sum / Math.max(end - start, 1));
      return Math.max(14, Math.min(96, Math.round(rms * 260)));
    });
    const max = Math.max(...bars, 1);
    return bars.map((bar) => Math.max(14, Math.round((bar / max) * 92)));
  } finally {
    audioContext.close?.();
  }
};

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

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const clampVolume = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return clamp(parsed, 0, 1);
};

const clampSeconds = (value, max = null) => {
  const seconds = toSeconds(value);
  return Number.isFinite(max) && max > 0 ? Math.min(seconds, max) : seconds;
};

const waitForMediaMetadata = (element) => new Promise((resolve, reject) => {
  if (!element) {
    reject(new Error('Media element is not available'));
    return;
  }
  if (element.readyState >= 1) {
    resolve();
    return;
  }
  const cleanup = () => {
    element.removeEventListener('loadedmetadata', handleLoaded);
    element.removeEventListener('error', handleError);
  };
  const handleLoaded = () => {
    cleanup();
    resolve();
  };
  const handleError = () => {
    cleanup();
    reject(new Error('Media preview could not load'));
  };
  element.addEventListener('loadedmetadata', handleLoaded, { once: true });
  element.addEventListener('error', handleError, { once: true });
  element.load?.();
});

const seekMedia = (element, seconds) => {
  if (!element) return;
  const duration = Number.isFinite(element.duration) ? element.duration : null;
  const target = duration === null ? seconds : Math.min(seconds, Math.max(duration - 0.05, 0));
  element.currentTime = Math.max(target, 0);
};

export const getAudioMixPreviewState = ({
  selectedAudio,
  selectedVolume,
  originalVolume,
  muteOriginal,
  originalMuteTouched,
  hasOriginalAudio,
}) => {
  const hasSelectedAudio = Boolean(selectedAudio?.media_id || selectedAudio?.media_url);
  const selectedVolumeValue = clampVolume(selectedVolume);
  const selectedAudible = hasSelectedAudio && selectedVolumeValue > 0;
  const autoUseOriginal = Boolean(hasOriginalAudio) && !originalMuteTouched && (!hasSelectedAudio || !selectedAudible);
  const effectiveMuteOriginal = Boolean(muteOriginal) && !autoUseOriginal;
  const originalVolumeValue = effectiveMuteOriginal ? 0 : clampVolume(originalVolume);
  const originalAudible = Boolean(hasOriginalAudio) && originalVolumeValue > 0;
  const silent = hasSelectedAudio && !selectedAudible && !originalAudible;
  return {
    hasSelectedAudio,
    selectedVolume: selectedVolumeValue,
    originalVolume: originalVolumeValue,
    selectedAudible,
    originalAudible,
    autoUseOriginal,
    effectiveMuteOriginal,
    silent,
  };
};

const AddAudioDialog = ({
  open,
  onOpenChange,
  video,
  onRenderComplete,
  onRemoveCustomAudio,
  composerSessionId,
  onTemporaryAudioUploaded,
  onTemporaryAudioRemoved,
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
  const [waveformBars, setWaveformBars] = useState(fallbackWaveformBars);
  const [muteOriginal, setMuteOriginal] = useState(true);
  const [originalMuteTouched, setOriginalMuteTouched] = useState(false);
  const [measuredVideoDuration, setMeasuredVideoDuration] = useState(0);
  const [measuredAudioDuration, setMeasuredAudioDuration] = useState(0);
  const [activeDrag, setActiveDrag] = useState(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const videoRef = useRef(null);
  const audioRef = useRef(null);
  const fileInputRef = useRef(null);
  const trimTrackRef = useRef(null);
  const offsetTrackRef = useRef(null);
  const delayedAudioTimerRef = useRef(null);
  const licensedAudioEnabled = env.AUDIO_PROVIDER_ENABLED === 'true';
  const licensedAudioProviderName = env.AUDIO_PROVIDER_NAME || 'licensed audio provider';

  const selectedAudio = audioAssets.find((asset) => asset.media_id === selectedAudioId) || null;
  const videoDuration = Number(video?.duration || measuredVideoDuration || 0);
  const hasVideoDuration = Number.isFinite(videoDuration) && videoDuration > 0;
  const selectedAudioDuration = Number(selectedAudio?.duration_seconds || measuredAudioDuration || 0);
  const hasAudioDuration = Number.isFinite(selectedAudioDuration) && selectedAudioDuration > 0;
  const hasOriginalAudio = video?.hasAudio !== false;
  const trimStartSeconds = clampSeconds(trimStart, hasAudioDuration ? selectedAudioDuration : null);
  const trimEndSeconds = trimEnd === '' ? null : clampSeconds(trimEnd, hasAudioDuration ? selectedAudioDuration : null);
  const effectiveTrimEnd = trimEndSeconds || selectedAudioDuration || videoDuration || null;
  const offsetSeconds = clampSeconds(offset, hasVideoDuration ? videoDuration : null);
  const mixState = getAudioMixPreviewState({
    selectedAudio,
    selectedVolume,
    originalVolume,
    muteOriginal,
    originalMuteTouched,
    hasOriginalAudio,
  });
  const audioTimelineDuration = Math.max(
    selectedAudioDuration || 0,
    effectiveTrimEnd || 0,
    trimStartSeconds || 0,
    1,
  );
  const trimStartPercent = clamp((trimStartSeconds / audioTimelineDuration) * 100, 0, 100);
  const trimEndPercent = effectiveTrimEnd
    ? clamp((effectiveTrimEnd / audioTimelineDuration) * 100, trimStartPercent, 100)
    : 100;
  const offsetPercent = hasVideoDuration ? clamp((offsetSeconds / videoDuration) * 100, 0, 100) : 0;
  const originalVolumePercent = Math.round(mixState.originalVolume * 100);
  const selectedVolumePercent = Math.round(mixState.selectedVolume * 100);
  const canRender = Boolean(video?.mediaId && selectedAudio?.media_id && !rendering && !uploadingAudio && !mixState.silent);

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
      setPreviewLoading(false);
      setPreviewError('');
      setRenderProgress(0);
      setActiveDrag(null);
      clearTimeout(delayedAudioTimerRef.current);
    }
  }, [open]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = mixState.originalVolume;
      videoRef.current.muted = mixState.effectiveMuteOriginal || mixState.originalVolume <= 0;
    }
    if (audioRef.current) {
      audioRef.current.volume = mixState.selectedVolume;
    }
  }, [mixState.effectiveMuteOriginal, mixState.originalVolume, mixState.selectedVolume]);

  useEffect(() => {
    stopPreview();
    setMeasuredAudioDuration(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAudioId]);

  useEffect(() => {
    setMeasuredVideoDuration(0);
  }, [video?.mediaId]);

  useEffect(() => {
    if (!hasAudioDuration) return;
    if (trimStartSeconds >= selectedAudioDuration) {
      setTrimStart(Math.max(selectedAudioDuration - 0.1, 0));
    }
    if (trimEndSeconds !== null && trimEndSeconds > selectedAudioDuration) {
      setTrimEnd(String(selectedAudioDuration));
    }
  }, [hasAudioDuration, selectedAudioDuration, trimStartSeconds, trimEndSeconds]);

  useEffect(() => {
    if (!hasVideoDuration) return;
    if (offsetSeconds >= videoDuration) {
      setOffset(Math.max(videoDuration - 0.1, 0));
    }
  }, [hasVideoDuration, offsetSeconds, videoDuration]);

  useEffect(() => {
    if (
      open
      && selectedAudio?.media_id
      && mixState.selectedVolume <= 0
      && hasOriginalAudio
      && !originalMuteTouched
      && clampVolume(originalVolume) <= 0
    ) {
      setOriginalVolume(0.35);
    }
  }, [open, selectedAudio?.media_id, mixState.selectedVolume, hasOriginalAudio, originalMuteTouched, originalVolume]);

  useEffect(() => {
    let cancelled = false;
    if (!open || !selectedAudio?.media_url) {
      setWaveformBars(fallbackWaveformBars);
      return undefined;
    }
    const storedBars = waveformPeaksToBars(selectedAudio.waveform_peaks);
    if (storedBars) {
      setWaveformBars(storedBars);
      return undefined;
    }
    buildWaveformBars(selectedAudio.media_url)
      .then((bars) => {
        if (!cancelled) setWaveformBars(bars);
      })
      .catch(() => {
        if (!cancelled) setWaveformBars(fallbackWaveformBars);
      });
    return () => {
      cancelled = true;
    };
  }, [open, selectedAudio?.media_id, selectedAudio?.media_url, selectedAudio?.waveform_peaks]);

  const percentFromPointer = (event, ref) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 0;
    return clamp((event.clientX - rect.left) / rect.width, 0, 1);
  };

  const applyDrag = (mode, event) => {
    if (mode === 'trimStart' && hasAudioDuration) {
      const seconds = percentFromPointer(event, trimTrackRef) * selectedAudioDuration;
      const maxStart = Math.max((trimEndSeconds ?? selectedAudioDuration) - 0.1, 0);
      setTrimStart(Number(clamp(seconds, 0, maxStart).toFixed(1)));
      return;
    }
    if (mode === 'trimEnd' && hasAudioDuration) {
      const seconds = percentFromPointer(event, trimTrackRef) * selectedAudioDuration;
      const minEnd = Math.min(trimStartSeconds + 0.1, selectedAudioDuration);
      setTrimEnd(String(Number(clamp(seconds, minEnd, selectedAudioDuration).toFixed(1))));
      return;
    }
    if (mode === 'offset' && hasVideoDuration) {
      const seconds = percentFromPointer(event, offsetTrackRef) * videoDuration;
      setOffset(Number(clamp(seconds, 0, Math.max(videoDuration - 0.1, 0)).toFixed(1)));
    }
  };

  useEffect(() => {
    if (!activeDrag) return undefined;
    const handleMove = (event) => {
      event.preventDefault();
      applyDrag(activeDrag, event);
    };
    const handleUp = () => setActiveDrag(null);
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp, { once: true });
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  });

  const stopPreview = () => {
    clearTimeout(delayedAudioTimerRef.current);
    if (videoRef.current) videoRef.current.pause();
    if (audioRef.current) audioRef.current.pause();
    setPreviewLoading(false);
    setIsPreviewing(false);
  };

  const startPreview = async () => {
    if (!videoRef.current || !video?.url) return;
    clearTimeout(delayedAudioTimerRef.current);
    const videoEl = videoRef.current;
    const audioEl = audioRef.current;
    const hasSelectedAudio = Boolean(audioEl && selectedAudio?.media_url);
    setPreviewError('');
    setPreviewLoading(true);
    try {
      await waitForMediaMetadata(videoEl);
      seekMedia(videoEl, 0);
      videoEl.volume = mixState.originalVolume;
      videoEl.muted = mixState.effectiveMuteOriginal || mixState.originalVolume <= 0;

      if (hasSelectedAudio) {
        await waitForMediaMetadata(audioEl);
        audioEl.volume = mixState.selectedVolume;
        seekMedia(audioEl, trimStartSeconds);
      }

      setIsPreviewing(true);
      await videoEl.play();
      if (hasSelectedAudio && offsetSeconds > 0) {
        delayedAudioTimerRef.current = setTimeout(() => {
          seekMedia(audioEl, trimStartSeconds);
          audioEl.play().catch(() => {});
        }, offsetSeconds * 1000);
      } else if (hasSelectedAudio) {
        await audioEl.play();
      }
    } catch (error) {
      videoEl.pause();
      audioEl?.pause();
      setIsPreviewing(false);
      const message = error?.message || 'Preview could not start. Try clicking play again.';
      setPreviewError(message);
      toast.error(message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const togglePreview = () => {
    if (previewLoading) return;
    if (isPreviewing) {
      stopPreview();
    } else {
      startPreview();
    }
  };

  const handleAudioTimeUpdate = () => {
    const audioEl = audioRef.current;
    if (!audioEl) return;
    const end = trimEnd === '' ? null : trimEndSeconds;
    if (end && audioEl.currentTime >= end) {
      if (loopToEnd) {
        seekMedia(audioEl, trimStartSeconds);
        audioEl.play().catch(() => {});
      } else {
        audioEl.pause();
      }
    }
  };

  const handleClearSelectedAudio = () => {
    stopPreview();
    setSelectedAudioId('');
    setPreviewError('');
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
      const upload = await uploadMedia(
        file,
        (progressEvent) => {
          const total = progressEvent.total || file.size || 1;
          setUploadProgress(Math.round(((progressEvent.loaded || 0) * 100) / total));
        },
        {
          purpose: 'composer_audio_temp',
          composerSessionId,
        }
      );
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
      onTemporaryAudioUploaded?.(asset.media_id);
      toast.success('Audio uploaded');
    } catch (error) {
      toast.error(error?.message || 'Failed to upload audio');
    } finally {
      setUploadingAudio(false);
      setUploadProgress(0);
    }
  };

  const handleRemoveTemporaryAudio = async () => {
    if (!selectedAudio?.media_id || selectedAudio?.temporary !== true) return;
    const mediaId = selectedAudio.media_id;
    stopPreview();
    try {
      await cleanupTemporaryAudio({ mediaIds: [mediaId], reason: 'composer_audio_removed' });
      setAudioAssets((prev) => prev.filter((item) => item.media_id !== mediaId));
      setSelectedAudioId('');
      onTemporaryAudioRemoved?.(mediaId);
      toast.success('Uploaded audio removed');
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || 'Failed to remove uploaded audio');
    }
  };

  const resetMix = () => {
    stopPreview();
    setTrimStart(0);
    setTrimEnd('');
    setOffset(0);
    setLoopToEnd(true);
    setFadeIn(0.4);
    setFadeOut(0.8);
    setOriginalVolume(0.35);
    setSelectedVolume(0.9);
    setMuteOriginal(true);
    setOriginalMuteTouched(false);
    setPreviewError('');
  };

  const applyPreset = (preset) => {
    stopPreview();
    setOriginalMuteTouched(true);
    if (preset === 'replace') {
      setSelectedVolume(0.9);
      setOriginalVolume(0.35);
      setMuteOriginal(true);
      return;
    }
    if (preset === 'background') {
      setSelectedVolume(0.35);
      setOriginalVolume(0.75);
      setMuteOriginal(false);
      return;
    }
    setSelectedVolume(0.25);
    setOriginalVolume(0.9);
    setMuteOriginal(false);
  };

  const handleRemoveExistingCustomAudio = () => {
    stopPreview();
    onRemoveCustomAudio?.();
    onOpenChange?.(false);
  };

  const handleRender = async () => {
    if (!canRender) return;
    if (trimEndSeconds !== null && trimEndSeconds <= trimStartSeconds) {
      toast.error('Trim end must be after trim start');
      return;
    }
    if (hasAudioDuration && trimStartSeconds >= selectedAudioDuration) {
      toast.error('Trim start must be inside the selected audio track');
      return;
    }
    if (hasVideoDuration && offsetSeconds >= videoDuration) {
      toast.error('Start time must be inside the video duration');
      return;
    }
    setRendering(true);
    setRenderProgress(8);
    try {
      const render = await renderVideoAudio(video.mediaId, {
        audio_media_id: selectedAudio.media_id,
        trim_start_ms: Math.round(trimStartSeconds * 1000),
        trim_end_ms: trimEndSeconds === null ? null : Math.round(trimEndSeconds * 1000),
        video_offset_ms: Math.round(offsetSeconds * 1000),
        loop_to_video_end: loopToEnd,
        fade_in_ms: Math.round(fadeIn * 1000),
        fade_out_ms: Math.round(fadeOut * 1000),
        original_volume: mixState.originalVolume,
        selected_volume: mixState.selectedVolume,
        mute_original: mixState.effectiveMuteOriginal,
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
              {selectedAudio && (
                <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-700">Selected: {audioLabel(selectedAudio)}</p>
                    <p className="text-[11px] text-slate-500">
                      {selectedAudio.temporary === true
                        ? 'This uploaded track is temporary and can be removed from storage.'
                        : 'Clear this if you want to preview the video without added audio.'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button type="button" variant="ghost" size="sm" onClick={handleClearSelectedAudio} disabled={rendering}>
                      Clear
                    </Button>
                    {selectedAudio.temporary === true && (
                      <Button type="button" variant="outline" size="sm" onClick={handleRemoveTemporaryAudio} disabled={rendering}>
                        Remove upload
                      </Button>
                    )}
                  </div>
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
                <div>
                  <p className="text-sm font-semibold text-gray-900">Trim and align</p>
                  <p className="text-xs text-gray-500">Drag the cyan handles to trim. Drag the amber handle to align audio with the video.</p>
                </div>
                <span className="text-xs text-gray-500">
                  Audio {formatDuration(selectedAudioDuration)} · Video {formatDuration(videoDuration)}
                </span>
              </div>
              <div className="rounded-xl bg-slate-950 px-3 py-3">
                <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <span>Audio trim</span>
                  <span>{formatDuration(audioTimelineDuration)}</span>
                </div>
                <div className="flex h-16 items-end gap-1">
                  {waveformBars.map((height, index) => {
                    const barPercent = (index / Math.max(waveformBars.length - 1, 1)) * 100;
                    const inTrimRange = barPercent >= trimStartPercent && barPercent <= trimEndPercent;
                    return (
                      <span
                        key={index}
                        className={`flex-1 rounded-full transition-colors ${inTrimRange ? 'bg-cyan-300/90' : 'bg-slate-600/70'}`}
                        style={{ height: `${height}%` }}
                      />
                    );
                  })}
                </div>
                <div
                  ref={trimTrackRef}
                  className={`relative mt-3 h-3 rounded-full bg-slate-800 ${hasAudioDuration ? 'cursor-ew-resize' : 'cursor-not-allowed opacity-70'}`}
                >
                  <div
                    className="absolute top-0 h-3 rounded-full bg-cyan-300/80"
                    style={{ left: `${trimStartPercent}%`, width: `${Math.max(trimEndPercent - trimStartPercent, 1)}%` }}
                  />
                  <button
                    type="button"
                    disabled={!hasAudioDuration}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      setActiveDrag('trimStart');
                      applyDrag('trimStart', event);
                    }}
                    className="absolute top-1/2 h-6 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-100 bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.7)] disabled:opacity-40"
                    style={{ left: `${trimStartPercent}%` }}
                    title="Drag trim start"
                    aria-label="Drag trim start"
                  />
                  <button
                    type="button"
                    disabled={!hasAudioDuration}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      setActiveDrag('trimEnd');
                      applyDrag('trimEnd', event);
                    }}
                    className="absolute top-1/2 h-6 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-100 bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.7)] disabled:opacity-40"
                    style={{ left: `${trimEndPercent}%` }}
                    title="Drag trim end"
                    aria-label="Drag trim end"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Audio trim {formatDuration(trimStartSeconds)} - {formatDuration(effectiveTrimEnd || 0)}</span>
                  <span>{formatDuration(Math.max((effectiveTrimEnd || 0) - trimStartSeconds, 0))} selected</span>
                </div>
                <div className="mt-4 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  <span>Video alignment</span>
                  <span>{formatDuration(videoDuration)}</span>
                </div>
                <div
                  ref={offsetTrackRef}
                  className={`relative mt-2 h-3 rounded-full bg-slate-800 ${hasVideoDuration ? 'cursor-ew-resize' : 'cursor-not-allowed opacity-70'}`}
                  onPointerDown={(event) => {
                    if (!hasVideoDuration) return;
                    event.preventDefault();
                    setActiveDrag('offset');
                    applyDrag('offset', event);
                  }}
                >
                  <button
                    type="button"
                    disabled={!hasVideoDuration}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      setActiveDrag('offset');
                      applyDrag('offset', event);
                    }}
                    className="absolute -top-1 h-5 w-3 -translate-x-1/2 rounded-full border border-amber-100 bg-amber-300 shadow-[0_0_10px_rgba(252,211,77,0.8)] disabled:opacity-40"
                    style={{ left: `${offsetPercent}%` }}
                    title="Custom audio starts at this video time"
                    aria-label="Drag custom audio start time"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Custom audio starts at {formatDuration(offsetSeconds)}</span>
                  <span>{hasVideoDuration ? `${Math.round(offsetPercent)}% into video` : 'Set video duration by loading preview'}</span>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Trim start (sec)</Label>
                  <Input
                    type="number"
                    min="0"
                    max={hasAudioDuration ? selectedAudioDuration : undefined}
                    step="0.1"
                    value={trimStart}
                    onChange={(event) => setTrimStart(clampSeconds(event.target.value, hasAudioDuration ? selectedAudioDuration : null))}
                  />
                </div>
                <div>
                  <Label className="text-xs">Trim end (sec)</Label>
                  <Input
                    type="number"
                    min="0"
                    max={hasAudioDuration ? selectedAudioDuration : undefined}
                    step="0.1"
                    value={trimEnd}
                    onChange={(event) => {
                      const value = event.target.value;
                      setTrimEnd(value === '' ? '' : String(clampSeconds(value, hasAudioDuration ? selectedAudioDuration : null)));
                    }}
                    placeholder="End"
                  />
                </div>
                <div>
                  <Label className="text-xs">Start at video time (sec)</Label>
                  <Input
                    type="number"
                    min="0"
                    max={hasVideoDuration ? videoDuration : undefined}
                    step="0.1"
                    value={offset}
                    onChange={(event) => setOffset(clampSeconds(event.target.value, hasVideoDuration ? videoDuration : null))}
                  />
                </div>
                <div>
                  <Label className="text-xs">Fade in / out (sec)</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="number" min="0" max="10" step="0.1" value={fadeIn} onChange={(event) => setFadeIn(clampSeconds(event.target.value, 10))} />
                    <Input type="number" min="0" max="10" step="0.1" value={fadeOut} onChange={(event) => setFadeOut(clampSeconds(event.target.value, 10))} />
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
            {video?.audioMix && onRemoveCustomAudio && (
              <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-blue-950">This video already has custom audio</p>
                    <p className="mt-1 text-xs text-blue-800">Remove it to restore the original uploaded video before adding a different mix.</p>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={handleRemoveExistingCustomAudio} disabled={rendering}>
                    Remove custom audio
                  </Button>
                </div>
              </div>
            )}
            <div className="overflow-hidden rounded-2xl border border-gray-200 bg-black shadow-sm">
              {video?.url ? (
                <div className="relative">
                  <video
                    ref={videoRef}
                    src={video.url}
                    poster={video.thumbnailUrl && video.thumbnailUrl !== video.url ? video.thumbnailUrl : undefined}
                    className="aspect-video w-full cursor-pointer object-contain"
                    preload="metadata"
                    playsInline
                    onLoadedMetadata={(event) => {
                      const duration = event.currentTarget.duration;
                      if (Number.isFinite(duration) && duration > 0) {
                        setMeasuredVideoDuration(duration);
                      }
                    }}
                    onClick={togglePreview}
                    onPause={() => {
                      clearTimeout(delayedAudioTimerRef.current);
                      audioRef.current?.pause();
                      setIsPreviewing(false);
                    }}
                    onEnded={stopPreview}
                    onError={() => {
                      setPreviewError('Video preview could not load');
                      setIsPreviewing(false);
                      setPreviewLoading(false);
                    }}
                  />
                  <button
                    type="button"
                    onClick={togglePreview}
                    disabled={previewLoading}
                    className="absolute inset-0 flex items-center justify-center bg-black/10 transition hover:bg-black/20 disabled:cursor-wait"
                    aria-label={isPreviewing ? 'Pause preview mix' : 'Play preview mix'}
                  >
                    <span className="flex h-14 w-14 items-center justify-center rounded-full bg-white/95 text-gray-950 shadow-lg ring-1 ring-black/10">
                      {previewLoading ? (
                        <FaSpinner className="animate-spin" />
                      ) : isPreviewing ? (
                        <FaPause />
                      ) : (
                        <FaPlay className="ml-1" />
                      )}
                    </span>
                  </button>
                </div>
              ) : (
                <div className="flex aspect-video items-center justify-center text-sm text-gray-400">No video selected</div>
              )}
              {selectedAudio?.media_url && (
                <audio
                  ref={audioRef}
                  src={selectedAudio.media_url}
                  preload="metadata"
                  onLoadedMetadata={(event) => {
                    const duration = event.currentTarget.duration;
                    if (Number.isFinite(duration) && duration > 0) {
                      setMeasuredAudioDuration(duration);
                    }
                  }}
                  onTimeUpdate={handleAudioTimeUpdate}
                  onError={() => {
                    setPreviewError('Selected audio preview could not load');
                    stopPreview();
                  }}
                />
              )}
            </div>

            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">Preview mix</p>
                  <p className="text-xs text-gray-500">Browser preview approximates the final render.</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={resetMix} disabled={rendering}>
                    Reset mix
                  </Button>
                  <Button type="button" variant="outline" onClick={togglePreview} disabled={!video?.url || previewLoading}>
                    {previewLoading ? <FaSpinner className="mr-2 animate-spin" /> : isPreviewing ? <FaPause className="mr-2" /> : <FaPlay className="mr-2" />}
                    {previewLoading ? 'Loading' : isPreviewing ? 'Pause' : selectedAudio?.media_url ? 'Play mix' : 'Play video'}
                  </Button>
                </div>
              </div>
              {previewError && (
                <p className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {previewError}
                </p>
              )}
              {mixState.autoUseOriginal && mixState.hasSelectedAudio && !mixState.silent && (
                <p className="mt-3 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                  Selected audio is silent, so preview and render will keep the original video audio.
                </p>
              )}
              {mixState.silent && (
                <p className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  This mix would be silent. Raise selected audio volume or turn off “Mute original audio”.
                </p>
              )}
              {!selectedAudio?.media_url && (
                <p className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  Select or upload an audio track to preview the final mix. The video preview can still play without a selected track.
                </p>
              )}

              <div className="mt-5 space-y-5">
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                    <span>Mix presets</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => applyPreset('replace')} disabled={rendering}>
                      Replace
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => applyPreset('background')} disabled={rendering}>
                      Background
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => applyPreset('original')} disabled={rendering}>
                      Original louder
                    </Button>
                  </div>
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                    <span>Original video audio</span>
                    <span>{mixState.effectiveMuteOriginal ? 'Muted' : `${originalVolumePercent}%`}</span>
                  </div>
                  <Slider
                    value={[originalVolumePercent]}
                    min={0}
                    max={100}
                    step={1}
                    disabled={mixState.effectiveMuteOriginal}
                    onValueChange={(value) => setOriginalVolume(clampVolume((value?.[0] || 0) / 100))}
                  />
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                    <span>Selected audio</span>
                    <span>{selectedVolumePercent}%</span>
                  </div>
                  <Slider
                    value={[selectedVolumePercent]}
                    min={0}
                    max={100}
                    step={1}
                    onValueChange={(value) => setSelectedVolume(clampVolume((value?.[0] || 0) / 100))}
                  />
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">Mute original audio</p>
                  <p className="text-xs text-gray-500">
                    {mixState.autoUseOriginal
                      ? 'Original audio is being kept because selected audio is at 0%.'
                      : 'Replace existing video sound with the selected track.'}
                  </p>
                </div>
                <Switch
                  checked={mixState.effectiveMuteOriginal}
                  onCheckedChange={(checked) => {
                    setOriginalMuteTouched(true);
                    setMuteOriginal(checked);
                  }}
                />
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
