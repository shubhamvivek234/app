import React, { useEffect, useRef, useState } from 'react';
import {
  FaCheck,
  FaCompactDisc,
  FaFolder,
  FaMusic,
  FaPause,
  FaPlay,
  FaSave,
  FaSpinner,
  FaTrash,
  FaUpload,
  FaVolumeMute,
  FaVolumeUp,
} from 'react-icons/fa';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import fallbackStockTracks from '@/data/stockAudio.json';
import env from '@/env';
import {
  cleanupTemporaryAudio,
  getAudioAssets,
  getStockAudioTracks,
  persistTemporaryAudio,
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
  try {
    const response = await fetch(url);
    if (!response.ok) return fallbackWaveformBars;
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
  } catch (_e) {
    return fallbackWaveformBars;
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
  || asset?.title
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

const STOCK_CATEGORIES = [
  { id: 'all', label: 'All Vibe Tracks' },
  { id: 'chill', label: 'Lo-Fi Chill' },
  { id: 'upbeat', label: 'Upbeat Vlog' },
  { id: 'cinematic', label: 'Cinematic' },
  { id: 'tech', label: 'Tech Flow' },
  { id: 'acoustic', label: 'Acoustic' },
  { id: 'electronic', label: 'Synthwave' },
];

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
  // Navigation & source state
  const [sourceTab, setSourceTab] = useState('stock'); // 'stock' | 'library' | 'upload'
  const [stockCategory, setStockCategory] = useState('all');
  const [stockTracks, setStockTracks] = useState(fallbackStockTracks || []);
  const [audioAssets, setAudioAssets] = useState([]);
  const [selectedAudioId, setSelectedAudioId] = useState('');
  const [auditioningTrackId, setAuditioningTrackId] = useState(null);

  // Loading & Progress
  const [loadingLibrary, setLoadingLibrary] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [persistingAudio, setPersistingAudio] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);

  // Mix parameters
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState('');
  const [offset, setOffset] = useState(0);
  const [loopToEnd, setLoopToEnd] = useState(true);
  const [fadeIn, setFadeIn] = useState(0.4);
  const [fadeOut, setFadeOut] = useState(0.8);
  const [originalVolume, setOriginalVolume] = useState(0.35);
  const [selectedVolume, setSelectedVolume] = useState(0.9);
  const [muteOriginal, setMuteOriginal] = useState(true);
  const [originalMuteTouched, setOriginalMuteTouched] = useState(false);

  // Playback & Scrubber State
  const [waveformBars, setWaveformBars] = useState(fallbackWaveformBars);
  const [currentAudioPlayTime, setCurrentAudioPlayTime] = useState(0);
  const [measuredVideoDuration, setMeasuredVideoDuration] = useState(0);
  const [measuredAudioDuration, setMeasuredAudioDuration] = useState(0);
  const [activeDrag, setActiveDrag] = useState(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  // Refs
  const videoRef = useRef(null);
  const audioRef = useRef(null);
  const auditionAudioRef = useRef(null);
  const fileInputRef = useRef(null);
  const trimTrackRef = useRef(null);
  const offsetTrackRef = useRef(null);
  const waveformTrackRef = useRef(null);

  // All known audio assets combined
  const allKnownAssets = [
    ...audioAssets,
    ...stockTracks.filter((st) => !audioAssets.some((ua) => ua.media_id === st.media_id)),
  ];
  const selectedAudio = allKnownAssets.find((asset) => asset.media_id === selectedAudioId) || null;

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
  const playheadPercent = clamp((currentAudioPlayTime / audioTimelineDuration) * 100, 0, 100);

  const originalVolumePercent = Math.round(mixState.originalVolume * 100);
  const selectedVolumePercent = Math.round(mixState.selectedVolume * 100);
  const canRender = Boolean(video?.mediaId && selectedAudio?.media_id && !rendering && !uploadingAudio && !mixState.silent);
  const videoPreviewAspectRatio = video?.width && video?.height ? `${video.width} / ${video.height}` : undefined;

  // Load stock audio and user library audio on dialog open
  useEffect(() => {
    if (!open) return;
    getStockAudioTracks().then((tracks) => {
      if (Array.isArray(tracks) && tracks.length > 0) {
        setStockTracks(tracks);
      }
    });

    setLoadingLibrary(true);
    getAudioAssets()
      .then((assets) => {
        const normalized = Array.isArray(assets) ? assets : [];
        setAudioAssets(normalized);
      })
      .catch(() => toast.error('Failed to load user audio library'))
      .finally(() => setLoadingLibrary(false));
  }, [open]);

  // Cleanup on close
  useEffect(() => {
    if (!open) {
      stopPreview();
      stopAudition();
      setPreviewLoading(false);
      setPreviewError('');
      setRenderProgress(0);
      setActiveDrag(null);
      setCurrentAudioPlayTime(0);
    }
  }, [open]);

  // Keep volumes synchronized
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = mixState.originalVolume;
      videoRef.current.muted = mixState.effectiveMuteOriginal || mixState.originalVolume <= 0;
    }
    if (audioRef.current) {
      audioRef.current.volume = mixState.selectedVolume;
    }
  }, [mixState.effectiveMuteOriginal, mixState.originalVolume, mixState.selectedVolume]);

  // Reset preview when selected audio changes
  useEffect(() => {
    stopPreview();
    setMeasuredAudioDuration(0);
    setCurrentAudioPlayTime(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAudioId]);

  // Load waveform bars
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

  // Range clamp guards
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

  // Drag interaction
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

  // Auditioning single stock track
  const stopAudition = () => {
    if (auditionAudioRef.current) {
      auditionAudioRef.current.pause();
    }
    setAuditioningTrackId(null);
  };

  const toggleAudition = (track) => {
    if (auditioningTrackId === track.media_id) {
      stopAudition();
      return;
    }
    stopPreview();
    if (auditionAudioRef.current) {
      auditionAudioRef.current.src = track.media_url;
      auditionAudioRef.current.currentTime = 0;
      auditionAudioRef.current.volume = 0.85;
      auditionAudioRef.current.play().catch(() => {});
      setAuditioningTrackId(track.media_id);
    }
  };

  // Synchronized Preview System
  const stopPreview = () => {
    if (videoRef.current) videoRef.current.pause();
    if (audioRef.current) audioRef.current.pause();
    setPreviewLoading(false);
    setIsPreviewing(false);
  };

  const startPreview = async () => {
    if (!videoRef.current || !video?.url) return;
    stopAudition();
    const videoEl = videoRef.current;
    const audioEl = audioRef.current;
    const hasSelected = Boolean(audioEl && selectedAudio?.media_url);

    setPreviewError('');
    setPreviewLoading(true);
    try {
      await waitForMediaMetadata(videoEl);
      seekMedia(videoEl, 0);
      videoEl.volume = mixState.originalVolume;
      videoEl.muted = mixState.effectiveMuteOriginal || mixState.originalVolume <= 0;

      if (hasSelected) {
        await waitForMediaMetadata(audioEl);
        audioEl.volume = mixState.selectedVolume;
        seekMedia(audioEl, trimStartSeconds);
        setCurrentAudioPlayTime(trimStartSeconds);
      }

      setIsPreviewing(true);
      await videoEl.play();
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

  // Video timeupdate handler: sync audio strictly
  const handleVideoTimeUpdate = () => {
    const videoEl = videoRef.current;
    const audioEl = audioRef.current;
    if (!videoEl) return;
    const currentVTime = videoEl.currentTime;

    if (audioEl && selectedAudio?.media_url) {
      if (currentVTime < offsetSeconds) {
        if (!audioEl.paused) audioEl.pause();
        seekMedia(audioEl, trimStartSeconds);
        setCurrentAudioPlayTime(trimStartSeconds);
      } else {
        const elapsed = currentVTime - offsetSeconds;
        const range = Math.max((effectiveTrimEnd || selectedAudioDuration || 1) - trimStartSeconds, 0.5);
        let targetAudioTime;
        if (loopToEnd && range > 0) {
          targetAudioTime = trimStartSeconds + (elapsed % range);
        } else {
          targetAudioTime = trimStartSeconds + elapsed;
        }

        if (!loopToEnd && targetAudioTime >= (effectiveTrimEnd || selectedAudioDuration)) {
          if (!audioEl.paused) audioEl.pause();
        } else {
          if (Math.abs(audioEl.currentTime - targetAudioTime) > 0.25) {
            seekMedia(audioEl, targetAudioTime);
          }
          if (audioEl.paused && !videoEl.paused && isPreviewing) {
            audioEl.play().catch(() => {});
          }
        }
        setCurrentAudioPlayTime(audioEl.currentTime);
      }
    }
  };

  // Click waveform to seek
  const handleWaveformClick = (event) => {
    const rect = waveformTrackRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return;
    const clickFraction = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const targetAudioSec = clickFraction * audioTimelineDuration;

    if (audioRef.current) {
      seekMedia(audioRef.current, targetAudioSec);
      setCurrentAudioPlayTime(targetAudioSec);
    }
    if (videoRef.current) {
      const targetVideoSec = clamp(targetAudioSec - trimStartSeconds + offsetSeconds, 0, videoDuration || 9999);
      seekMedia(videoRef.current, targetVideoSec);
    }
  };

  // Clear audio selection
  const handleClearSelectedAudio = () => {
    stopPreview();
    setSelectedAudioId('');
    setPreviewError('');
    setCurrentAudioPlayTime(0);
  };

  // Upload user audio
  const handleAudioUpload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('audio/')) {
      toast.error('Select an audio file (MP3, WAV, M4A, AAC, OGG, or FLAC)');
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
      toast.success('Audio track uploaded');
    } catch (error) {
      toast.error(error?.message || 'Failed to upload audio');
    } finally {
      setUploadingAudio(false);
      setUploadProgress(0);
    }
  };

  // Save temporary upload to user library
  const handlePersistAudio = async () => {
    if (!selectedAudio?.media_id) return;
    setPersistingAudio(true);
    try {
      await persistTemporaryAudio(selectedAudio.media_id);
      setAudioAssets((prev) =>
        prev.map((item) =>
          item.media_id === selectedAudio.media_id ? { ...item, temporary: false } : item
        )
      );
      toast.success('Track saved permanently to your Media Library');
    } catch (err) {
      toast.error('Could not save track to library');
    } finally {
      setPersistingAudio(false);
    }
  };

  // Remove temporary upload
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

  const visibleStockTracks = stockCategory === 'all'
    ? stockTracks
    : stockTracks.filter((track) => track.category === stockCategory);

  return (
    <Dialog open={open} onOpenChange={(value) => {
      if (!value) {
        stopPreview();
        stopAudition();
      }
      onOpenChange?.(value);
    }}>
      <DialogContent
        motionPreset="centered"
        className="flex max-h-[94dvh] w-[min(1160px,calc(100vw-1.5rem))] max-w-none flex-col gap-0 overflow-hidden p-0"
      >
        {/* Hidden audition player */}
        <audio ref={auditionAudioRef} onEnded={stopAudition} />

        <DialogHeader className="shrink-0 border-b border-gray-200 px-5 py-3.5 text-left sm:px-6">
          <DialogTitle className="flex items-center gap-2 text-lg font-bold text-gray-900">
            <FaMusic className="text-blue-600" />
            Add audio to video
          </DialogTitle>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-0 overflow-y-auto md:grid-cols-[1.1fr_0.9fr]">
          {/* Left Column: Source Selection & Timeline Controls */}
          <div className="space-y-4 bg-slate-50/70 p-4 sm:p-5 md:border-r md:border-gray-200">
            {/* Source Selection Card */}
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-xs">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-bold text-gray-900">Audio source</p>
                  <p className="text-xs text-gray-500">Pick from curated royalty-free music or upload your own.</p>
                </div>
                {/* Source Tabs */}
                <div className="flex items-center rounded-lg bg-gray-100 p-0.5 text-xs font-semibold text-gray-600">
                  <button
                    type="button"
                    onClick={() => setSourceTab('stock')}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition ${
                      sourceTab === 'stock' ? 'bg-white text-blue-600 shadow-xs' : 'hover:text-gray-900'
                    }`}
                  >
                    <FaCompactDisc className="text-[11px]" />
                    <span>Stock Music</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceTab('library')}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition ${
                      sourceTab === 'library' ? 'bg-white text-blue-600 shadow-xs' : 'hover:text-gray-900'
                    }`}
                  >
                    <FaFolder className="text-[11px]" />
                    <span>My Library</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceTab('upload')}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition ${
                      sourceTab === 'upload' ? 'bg-white text-blue-600 shadow-xs' : 'hover:text-gray-900'
                    }`}
                  >
                    <FaUpload className="text-[10px]" />
                    <span>Upload</span>
                  </button>
                </div>
              </div>

              {/* TAB 1: Stock Royalty-Free Music */}
              {sourceTab === 'stock' && (
                <div className="space-y-2.5">
                  {/* Category Pills */}
                  <div className="flex flex-wrap gap-1">
                    {STOCK_CATEGORIES.map((cat) => (
                      <button
                        type="button"
                        key={cat.id}
                        onClick={() => setStockCategory(cat.id)}
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition ${
                          stockCategory === cat.id
                            ? 'bg-blue-600 text-white shadow-xs'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {cat.label}
                      </button>
                    ))}
                  </div>

                  {/* Track Cards */}
                  <div className="max-h-52 space-y-1.5 overflow-y-auto pr-1">
                    {visibleStockTracks.map((track) => {
                      const isSelected = selectedAudioId === track.media_id;
                      const isAuditioning = auditioningTrackId === track.media_id;
                      return (
                        <div
                          key={track.media_id}
                          className={`flex items-center justify-between gap-3 rounded-xl border p-2.5 transition ${
                            isSelected
                              ? 'border-blue-500 bg-blue-50/70 ring-1 ring-blue-400'
                              : 'border-gray-200 bg-white hover:border-gray-300'
                          }`}
                        >
                          <div className="flex min-w-0 items-center gap-2.5">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleAudition(track);
                              }}
                              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition ${
                                isAuditioning
                                  ? 'bg-blue-600 text-white animate-pulse'
                                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              }`}
                              title={isAuditioning ? 'Pause preview' : 'Audition track'}
                            >
                              {isAuditioning ? <FaPause className="text-xs" /> : <FaPlay className="ml-0.5 text-xs" />}
                            </button>
                            <div className="min-w-0">
                              <p className="truncate text-xs font-bold text-gray-900">{track.title}</p>
                              <div className="flex items-center gap-2 text-[10px] text-gray-500">
                                <span className="font-semibold text-blue-600 uppercase tracking-wider">{track.category}</span>
                                <span>·</span>
                                <span>{track.bpm} BPM</span>
                                <span>·</span>
                                <span>{formatDuration(track.duration_seconds)}</span>
                                {track.mood && (
                                  <>
                                    <span>·</span>
                                    <span className="italic text-gray-400">{track.mood}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              stopAudition();
                              setSelectedAudioId(track.media_id);
                            }}
                            className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                              isSelected
                                ? 'bg-blue-600 text-white'
                                : 'bg-gray-100 text-gray-700 hover:bg-blue-50 hover:text-blue-600'
                            }`}
                          >
                            {isSelected ? 'Selected' : 'Use'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* TAB 2: User Library */}
              {sourceTab === 'library' && (
                <div>
                  {loadingLibrary ? (
                    <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-xs text-gray-500">
                      Loading user audio library...
                    </div>
                  ) : audioAssets.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-xs text-gray-500">
                      No saved audio tracks yet in your library. Use the "Upload" tab to add tracks.
                    </div>
                  ) : (
                    <div className="max-h-52 space-y-1.5 overflow-y-auto pr-1">
                      {audioAssets.map((asset) => (
                        <button
                          type="button"
                          key={asset.media_id}
                          onClick={() => setSelectedAudioId(asset.media_id)}
                          className={`w-full rounded-xl border p-2.5 text-left transition ${
                            selectedAudioId === asset.media_id
                              ? 'border-blue-400 bg-blue-50'
                              : 'border-gray-200 bg-white hover:border-gray-300'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="truncate text-xs font-semibold text-gray-900">{audioLabel(asset)}</span>
                            <span className="shrink-0 text-[11px] text-gray-500">{formatDuration(asset.duration_seconds)}</span>
                          </div>
                          <p className="mt-0.5 truncate text-[10px] text-gray-400">{asset.mime_type || 'audio file'}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: Upload Custom Audio */}
              {sourceTab === 'upload' && (
                <div className="space-y-3">
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50/50 p-6 transition hover:border-blue-400 hover:bg-blue-50/30"
                  >
                    <FaUpload className="mb-2 text-2xl text-blue-600" />
                    <p className="text-xs font-semibold text-gray-800">Click to upload an audio track</p>
                    <p className="text-[11px] text-gray-500">MP3, WAV, M4A, AAC, OGG, or FLAC up to 50MB</p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      disabled={uploadingAudio || rendering}
                    >
                      {uploadingAudio ? <FaSpinner className="mr-2 animate-spin" /> : <FaUpload className="mr-2" />}
                      Select audio file
                    </Button>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*"
                    className="hidden"
                    onChange={handleAudioUpload}
                  />
                  {uploadingAudio && (
                    <div className="rounded-xl border border-blue-100 bg-blue-50 p-3">
                      <div className="mb-1 flex items-center justify-between text-xs font-semibold text-blue-800">
                        <span>Uploading track...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <Progress value={uploadProgress} className="h-1.5" />
                    </div>
                  )}
                </div>
              )}

              {/* Selected Audio Active Banner */}
              {selectedAudio && (
                <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-slate-100 p-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-bold text-slate-800">
                      Active: {audioLabel(selectedAudio)}
                    </p>
                    <p className="text-[10px] text-slate-500">
                      {selectedAudio.is_stock
                        ? 'Royalty-free background track'
                        : selectedAudio.temporary === true
                        ? 'Temporary upload (you can save this track to your library)'
                        : 'From your permanent media library'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {selectedAudio.temporary === true && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1 text-blue-700 border-blue-200 hover:bg-blue-50"
                        onClick={handlePersistAudio}
                        disabled={persistingAudio || rendering}
                        title="Save this track permanently to your library"
                      >
                        {persistingAudio ? <FaSpinner className="animate-spin text-[10px]" /> : <FaSave className="text-[10px]" />}
                        Save to library
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={handleClearSelectedAudio}
                      disabled={rendering}
                    >
                      Clear
                    </Button>
                    {selectedAudio.temporary === true && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-red-600 hover:bg-red-50 hover:text-red-700"
                        onClick={handleRemoveTemporaryAudio}
                        disabled={rendering}
                        title="Delete this uploaded file"
                      >
                        <FaTrash className="text-[10px]" />
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Timeline, Waveform & Alignment Card */}
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-xs">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-gray-900">Trim and align</p>
                  <p className="text-xs text-gray-500">
                    Click waveform to scrub. Drag cyan handles to trim audio; drag amber handle for video offset.
                  </p>
                </div>
                <span className="text-xs font-semibold text-gray-600">
                  Audio {formatDuration(selectedAudioDuration)} · Video {formatDuration(videoDuration)}
                </span>
              </div>

              {/* Waveform & Scrubber */}
              <div className="rounded-xl bg-slate-950 p-3 shadow-inner">
                <div className="mb-2 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  <span>Waveform Timeline</span>
                  <span className="font-mono text-cyan-300">
                    {formatDuration(currentAudioPlayTime)} / {formatDuration(audioTimelineDuration)}
                  </span>
                </div>

                {/* Clickable Waveform with Playhead */}
                <div
                  ref={waveformTrackRef}
                  onClick={handleWaveformClick}
                  className="relative flex h-16 cursor-pointer items-end gap-1 rounded-lg transition hover:brightness-110"
                  title="Click anywhere to scrub playback"
                >
                  {waveformBars.map((height, index) => {
                    const barPercent = (index / Math.max(waveformBars.length - 1, 1)) * 100;
                    const inTrimRange = barPercent >= trimStartPercent && barPercent <= trimEndPercent;
                    return (
                      <span
                        key={index}
                        className={`flex-1 rounded-full transition-colors ${
                          inTrimRange ? 'bg-cyan-400/90' : 'bg-slate-700/60'
                        }`}
                        style={{ height: `${height}%` }}
                      />
                    );
                  })}

                  {/* Active Playhead Cursor */}
                  {hasAudioDuration && (
                    <div
                      className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_8px_#38bdf8]"
                      style={{ left: `${playheadPercent}%` }}
                    />
                  )}
                </div>

                {/* Trim Slider Track */}
                <div
                  ref={trimTrackRef}
                  className={`relative mt-3 h-3 rounded-full bg-slate-800 ${
                    hasAudioDuration ? 'cursor-ew-resize' : 'cursor-not-allowed opacity-60'
                  }`}
                >
                  <div
                    className="absolute top-0 h-3 rounded-full bg-cyan-400/80"
                    style={{
                      left: `${trimStartPercent}%`,
                      width: `${Math.max(trimEndPercent - trimStartPercent, 1)}%`,
                    }}
                  />
                  <button
                    type="button"
                    disabled={!hasAudioDuration}
                    onPointerDown={(event) => {
                      event.preventDefault();
                      setActiveDrag('trimStart');
                      applyDrag('trimStart', event);
                    }}
                    className="absolute top-1/2 h-6 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-100 bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.8)] disabled:opacity-40"
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
                    className="absolute top-1/2 h-6 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-100 bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.8)] disabled:opacity-40"
                    style={{ left: `${trimEndPercent}%` }}
                    title="Drag trim end"
                    aria-label="Drag trim end"
                  />
                </div>

                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Audio trim: {formatDuration(trimStartSeconds)} – {formatDuration(effectiveTrimEnd || 0)}</span>
                  <span>{formatDuration(Math.max((effectiveTrimEnd || 0) - trimStartSeconds, 0))} duration</span>
                </div>

                {/* Video Alignment Offset */}
                <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  <span>Video start alignment</span>
                  <span>Starts at {formatDuration(offsetSeconds)}</span>
                </div>
                <div
                  ref={offsetTrackRef}
                  className={`relative mt-2 h-3 rounded-full bg-slate-800 ${
                    hasVideoDuration ? 'cursor-ew-resize' : 'cursor-not-allowed opacity-60'
                  }`}
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
                    className="absolute -top-1 h-5 w-3 -translate-x-1/2 rounded-full border border-amber-100 bg-amber-300 shadow-[0_0_8px_rgba(252,211,77,0.9)] disabled:opacity-40"
                    style={{ left: `${offsetPercent}%` }}
                    title="Custom audio starts at this video time"
                    aria-label="Drag custom audio start time"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                  <span>Offset into video: {formatDuration(offsetSeconds)}</span>
                  <span>{hasVideoDuration ? `${Math.round(offsetPercent)}% into video` : 'Ready'}</span>
                </div>
              </div>

              {/* Number Inputs & Fine Tuning */}
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs font-semibold text-gray-700">Trim start (sec)</Label>
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
                  <Label className="text-xs font-semibold text-gray-700">Trim end (sec)</Label>
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
                  <Label className="text-xs font-semibold text-gray-700">Start at video time (sec)</Label>
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
                  <Label className="text-xs font-semibold text-gray-700">Fade in / out (sec)</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="number" min="0" max="10" step="0.1" value={fadeIn} onChange={(event) => setFadeIn(clampSeconds(event.target.value, 10))} />
                    <Input type="number" min="0" max="10" step="0.1" value={fadeOut} onChange={(event) => setFadeOut(clampSeconds(event.target.value, 10))} />
                  </div>
                </div>
              </div>

              {/* Loop Switch */}
              <div className="mt-4 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2.5">
                <div>
                  <p className="text-sm font-semibold text-gray-800">Loop selected audio to video end</p>
                  <p className="text-xs text-gray-500">Automatically repeats track if shorter than video.</p>
                </div>
                <Switch checked={loopToEnd} onCheckedChange={setLoopToEnd} />
              </div>
            </div>
          </div>

          {/* Right Column: Video Preview & Mix Balancing */}
          <div className="space-y-4 p-4 sm:p-5">
            {video?.audioMix && onRemoveCustomAudio && (
              <div className="rounded-2xl border border-blue-200 bg-blue-50/80 p-3.5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-blue-950">This video has custom audio attached</p>
                    <p className="text-xs text-blue-800">Restore original video sound before adding another mix.</p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      stopPreview();
                      onRemoveCustomAudio?.();
                      onOpenChange?.(false);
                    }}
                    disabled={rendering}
                    className="border-blue-300 text-blue-800 hover:bg-blue-100"
                  >
                    Restore original
                  </Button>
                </div>
              </div>
            )}

            {/* Video Player Display */}
            <div className="overflow-hidden rounded-2xl border border-gray-200 bg-black shadow-md">
              {video?.url ? (
                <div
                  className="relative flex max-h-[42dvh] min-h-[190px] items-center justify-center bg-black"
                  style={videoPreviewAspectRatio ? { aspectRatio: videoPreviewAspectRatio } : undefined}
                >
                  <video
                    ref={videoRef}
                    src={video.url}
                    poster={video.thumbnailUrl && video.thumbnailUrl !== video.url ? video.thumbnailUrl : undefined}
                    className="h-full max-h-[42dvh] w-full max-w-full cursor-pointer object-contain"
                    preload="metadata"
                    playsInline
                    onLoadedMetadata={(event) => {
                      const dur = event.currentTarget.duration;
                      if (Number.isFinite(dur) && dur > 0) {
                        setMeasuredVideoDuration(dur);
                      }
                    }}
                    onTimeUpdate={handleVideoTimeUpdate}
                    onClick={togglePreview}
                    onPause={() => {
                      audioRef.current?.pause();
                      setIsPreviewing(false);
                    }}
                    onSeeked={() => {
                      if (audioRef.current && selectedAudio?.media_url) {
                        const currentV = videoRef.current?.currentTime || 0;
                        if (currentV >= offsetSeconds) {
                          const elapsed = currentV - offsetSeconds;
                          const range = Math.max((effectiveTrimEnd || selectedAudioDuration || 1) - trimStartSeconds, 0.5);
                          const targetTime = loopToEnd ? trimStartSeconds + (elapsed % range) : trimStartSeconds + elapsed;
                          seekMedia(audioRef.current, targetTime);
                          setCurrentAudioPlayTime(targetTime);
                        } else {
                          seekMedia(audioRef.current, trimStartSeconds);
                          setCurrentAudioPlayTime(trimStartSeconds);
                        }
                      }
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
                    className="absolute inset-0 flex items-center justify-center bg-black/15 transition hover:bg-black/25 disabled:cursor-wait"
                    aria-label={isPreviewing ? 'Pause preview mix' : 'Play preview mix'}
                  >
                    <span className="flex h-14 w-14 items-center justify-center rounded-full bg-white/95 text-gray-950 shadow-lg ring-1 ring-black/10 transition hover:scale-105">
                      {previewLoading ? (
                        <FaSpinner className="animate-spin text-lg" />
                      ) : isPreviewing ? (
                        <FaPause className="text-lg" />
                      ) : (
                        <FaPlay className="ml-1 text-lg" />
                      )}
                    </span>
                  </button>
                </div>
              ) : (
                <div className="flex aspect-video items-center justify-center text-sm text-gray-400">No video selected</div>
              )}

              {/* Dedicated Mixed Audio Element */}
              {selectedAudio?.media_url && (
                <audio
                  ref={audioRef}
                  src={selectedAudio.media_url}
                  preload="metadata"
                  onLoadedMetadata={(event) => {
                    const dur = event.currentTarget.duration;
                    if (Number.isFinite(dur) && dur > 0) {
                      setMeasuredAudioDuration(dur);
                    }
                  }}
                  onError={() => {
                    setPreviewError('Selected audio preview could not load');
                    stopPreview();
                  }}
                />
              )}
            </div>

            {/* Mix Controls & Volume Balancing */}
            <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-xs">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-bold text-gray-900">Audio mix controls</p>
                  <p className="text-xs text-gray-500">Balance original speech vs background music.</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={resetMix} disabled={rendering}>
                    Reset
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={togglePreview} disabled={!video?.url || previewLoading}>
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
              {mixState.silent && (
                <p className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
                  This mix would be silent. Raise selected audio volume or turn off “Mute original audio”.
                </p>
              )}

              <div className="mt-4 space-y-4">
                {/* Mix Presets */}
                <div>
                  <div className="mb-2 text-xs font-semibold text-gray-600">Mix presets</div>
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

                {/* Original Video Audio Slider */}
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-gray-700">
                    <span className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setOriginalMuteTouched(true);
                          setMuteOriginal(!mixState.effectiveMuteOriginal);
                        }}
                        className="text-gray-500 hover:text-gray-900"
                        title={mixState.effectiveMuteOriginal ? 'Unmute original audio' : 'Mute original audio'}
                      >
                        {mixState.effectiveMuteOriginal ? <FaVolumeMute className="text-red-500" /> : <FaVolumeUp />}
                      </button>
                      Original video audio
                    </span>
                    <span className="font-semibold text-gray-900">
                      {mixState.effectiveMuteOriginal ? 'Muted' : `${originalVolumePercent}%`}
                    </span>
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

                {/* Selected Audio Volume Slider */}
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-gray-700">
                    <span className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setSelectedVolume(selectedVolume > 0 ? 0 : 0.85)}
                        className="text-gray-500 hover:text-gray-900"
                        title={selectedVolume === 0 ? 'Unmute music' : 'Mute music'}
                      >
                        {selectedVolume === 0 ? <FaVolumeMute className="text-red-500" /> : <FaMusic className="text-blue-600" />}
                      </button>
                      Selected background music
                    </span>
                    <span className="font-semibold text-gray-900">{selectedVolumePercent}%</span>
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

              {/* Mute Original Audio Toggle */}
              <div className="mt-4 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2.5">
                <div>
                  <p className="text-sm font-semibold text-gray-800">Mute original video sound</p>
                  <p className="text-xs text-gray-500">Replaces video audio completely with selected music.</p>
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

            {/* Rendering Progress Indicator */}
            {rendering && (
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
                <div className="mb-2 flex items-center justify-between text-sm font-bold text-blue-900">
                  <span className="flex items-center gap-2">
                    <FaSpinner className="animate-spin" />
                    Rendering final video with audio...
                  </span>
                  <span>{renderProgress}%</span>
                </div>
                <Progress value={renderProgress} className="h-2" />
                <p className="mt-2 text-xs text-blue-700">
                  FFmpeg is baking your custom audio mix. This takes just a couple seconds.
                </p>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="shrink-0 border-t border-gray-200 px-5 py-3.5 sm:px-6">
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
