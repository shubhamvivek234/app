import React, { useState, useRef, useEffect, useCallback, useId } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
  FaFacebook, FaInstagram, FaLinkedin, FaTwitter,
  FaYoutube, FaTiktok, FaPinterest,
  FaMusic, FaShoppingBag, FaInfoCircle, FaExclamationTriangle,
  FaSmile, FaHashtag, FaCloudUploadAlt, FaTimes,
  FaChevronDown, FaChevronUp, FaGripVertical,
  FaFileAlt, FaFilePdf, FaFilePowerpoint, FaFileWord,
  FaCrop, FaSearch, FaExternalLinkAlt, FaImages, FaSpinner, FaChartBar,
} from 'react-icons/fa';
import {
  SiBluesky, SiThreads, SiGiphy,
  SiCanva, SiDropbox, SiGoogledrive, SiUnsplash,
} from 'react-icons/si';
import { MdPhotoLibrary } from 'react-icons/md';
import { toast } from 'sonner';
import env from '@/env';
import {
  searchUnsplashMedia,
  getCanvaImportUrl,
  listCanvaDesigns,
  createCanvaExport,
  getCanvaExport,
} from '@/lib/api';

const PLATFORM_ICONS = {
  facebook:  { icon: FaFacebook,  color: '#1877F2' },
  instagram: { icon: FaInstagram, color: '#E1306C' },
  twitter:   { icon: FaTwitter,   color: '#1DA1F2' },
  linkedin:  { icon: FaLinkedin,  color: '#0A66C2' },
  youtube:   { icon: FaYoutube,   color: '#FF0000' },
  tiktok:    { icon: FaTiktok,    color: '#010101' },
  pinterest: { icon: FaPinterest, color: '#E60023' },
  bluesky:   { icon: SiBluesky,   color: '#0085FF' },
  threads:   { icon: SiThreads,   color: '#101010' },
};

const CHAR_LIMITS = {
  twitter: 280, bluesky: 300, facebook: 63206, instagram: 2200,
  linkedin: 3000, youtube: 5000, tiktok: 2200, pinterest: 500, threads: 500, common: 5000,
};

// Ideal aspect ratios (width/height) per platform/format
const PLATFORM_ASPECT_RATIOS = {
  instagram: {
    Post:  { ratio: 4 / 5,  label: '4:5',    name: 'Instagram Grid and Feed' },
    Reel:  { ratio: 9 / 16, label: '9:16',   name: 'Instagram Reels' },
    Story: { ratio: 9 / 16, label: '9:16',   name: 'Instagram Stories' },
  },
  tiktok:    { ratio: 9 / 16,  label: '9:16',    name: 'TikTok' },
  youtube:   { ratio: 16 / 9,  label: '16:9',    name: 'YouTube' },
  twitter:   { ratio: 16 / 9,  label: '16:9',    name: 'Twitter / X' },
  facebook:  { ratio: 1,        label: '1:1',     name: 'Facebook Feed' },
  linkedin:  { ratio: 1.91,     label: '1.91:1',  name: 'LinkedIn' },
  pinterest: { ratio: 2 / 3,   label: '2:3',     name: 'Pinterest' },
  threads:   { ratio: 1,        label: '1:1',     name: 'Threads' },
  bluesky:   { ratio: 1,        label: '1:1',     name: 'Bluesky' },
};

// How far off (fraction) before we show a warning (10% tolerance)
const ASPECT_RATIO_TOLERANCE = 0.10;

const getIdealAspectInfo = (platform, postFormat) => {
  const entry = PLATFORM_ASPECT_RATIOS[platform];
  if (!entry) return null;
  if (platform === 'instagram' && postFormat) return entry[postFormat] || entry.Post;
  return entry;
};

const getAccountInitial = (label = '') => (label.trim().charAt(0) || '?').toUpperCase();

const POLL_SUPPORTED_PLATFORMS = ['linkedin', 'twitter', 'threads'];

const POLL_DURATION_OPTIONS = {
  twitter: [
    { value: 'ONE_DAY', label: '1 day' },
    { value: 'THREE_DAYS', label: '3 days' },
    { value: 'SEVEN_DAYS', label: '7 days' },
  ],
  linkedin: [
    { value: 'ONE_DAY', label: '1 day' },
    { value: 'THREE_DAYS', label: '3 days' },
    { value: 'SEVEN_DAYS', label: '7 days' },
    { value: 'FOURTEEN_DAYS', label: '14 days' },
  ],
  threads: [
    { value: 'ONE_DAY', label: '1 day' },
  ],
};

const createPollDraft = (poll = null, platform = 'twitter') => {
  const options = Array.isArray(poll?.options) ? poll.options.slice(0, 4) : [];
  while (options.length < 2) {
    options.push('');
  }
  return {
    question: poll?.question || '',
    options,
    duration: poll?.duration || (POLL_DURATION_OPTIONS[platform]?.[0]?.value || 'ONE_DAY'),
  };
};

// Extended emoji list for social media
const EMOJI_LIST = [
  // Smileys & Emotion
  '😀','😁','😂','🤣','😃','😄','😅','😆','😉','😊','😋','😎','😍','🥰','😘',
  '😗','😙','😚','☺️','🙂','🤗','🤩','🤔','😐','😶','🙄','😏','😒','😕','🙃',
  '😲','😢','😭','😤','😡','🤬','😳','🥵','🥶','😱','😰','😨','🥴','😵','🤯',
  '🤠','🥳','🧐','😷','🤒','🤧','🤑','😈','👿','💀','🤡','👻','🤥','🤫','🤭',
  // Gestures & People
  '👍','👎','👌','🤌','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','👇','☝️','✋',
  '🖐️','🤚','👋','🤲','👐','🙌','👏','🤝','🙏','💪','🦾','✍️','💅','🤳','🫶',
  '💁','🙆','🙅','🤦','🤷','💆','💇','🧖','🧘','🏃','🚶','🧍','🧎','👫','👨‍👩‍👧',
  // Hearts & Love
  '❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗',
  '💖','💘','💝','💟','♥️','💌','💋','😻','💑','💏','🫀','❤️‍🔥','❤️‍🩹',
  // Stars & Celebration
  '✨','🔥','💥','⚡','🌟','⭐','🌈','☀️','🌙','❄️','💫','🌊','🌀','🎇','🎆',
  '🎉','🎊','🎈','🎀','🎁','🥳','🎏','🎐','🎑','🏮','🎃','🎄','🎋','🎍','🎎',
  // Nature & Animals
  '🌸','🌺','🌻','🌹','🌷','🌱','🌿','🍀','🍃','🌲','🌳','🌴','🌵','🌾','🍄',
  '🐶','🐱','🦊','🐻','🐼','🐸','🦋','🐝','🦄','🐙','🦁','🐯','🐨','🦋','🐬',
  '🦅','🦉','🐧','🦜','🐢','🦎','🦕','🐳','🦈','🐬','🐠','🐡','🦞','🦀','🦑',
  // Objects & Tech
  '📸','📷','📱','💻','🖥️','⌨️','📊','📈','📉','📝','✏️','💡','🔍','🔑','🗝️',
  '🔒','💰','💵','💳','📧','🗓️','📅','📆','⏰','⌚','⏳','🎯','🏆','🥇','🎁',
  '🔭','🔬','🧪','🧬','💊','🩺','🩻','🧲','💿','📀','🖨️','🖱️','📡','🛰️','🚀',
  // Music & Entertainment
  '🎵','🎶','🎸','🎹','🥁','🎺','🎻','🎤','🎧','🎼','🎬','🎥','📺','🎮','🕹️',
  '🎲','♟️','🎭','🎨','🖼️','🎪','🎠','🎡','🎢','🎟️','🎰','🃏','🀄','🎯','🎳',
  // Food & Drink
  '🍕','🍔','🍟','🌮','🌯','🥗','🍣','🍱','🍜','🍝','🥘','🍲','☕','🍵','🧃',
  '🥤','🧋','🍺','🍷','🥂','🍾','🍰','🎂','🍩','🍪','🍫','🍬','🍭','🍓','🍇',
  '🍎','🍊','🍋','🥑','🥦','🌽','🍆','🥕','🧄','🧅','🌶️','🫑','🥜','🌰','🍞',
  // Travel & Places
  '🏠','🏡','🏢','🏣','🏤','🏥','🏦','🏨','🏩','🏪','🏫','⛪','🕌','🗼','🗽',
  '🗺️','🌍','🌎','🌏','🏔️','⛰️','🌋','🏕️','🏖️','🏜️','🏝️','🌅','🌄','🌠','🎑',
  '✈️','🚀','🛸','🚂','🚗','🚕','🚙','🏎️','🛵','🚲','🛹','🚢','⛵','🚁','🛻',
  // Symbols & Signs
  '💯','✅','❌','⭕','🆕','🆒','🆓','🔝','🔛','🔜','🔚','🔙','⬆️','⬇️','↩️',
  '🔄','🔃','📌','📍','🔖','🏷️','💬','💭','🗯️','📢','📣','🔔','🔕','🎵','♾️',
];

const MEDIA_SOURCE_SETUP = {
  unsplash: () => Boolean(env.UNSPLASH_ACCESS_KEY),
  dropbox: () => Boolean(env.DROPBOX_APP_KEY),
  google_drive: () => Boolean(env.GOOGLE_CLIENT_ID),
  google_photos: () => Boolean(env.GOOGLE_PHOTOS_CLIENT_ID || env.GOOGLE_CLIENT_ID),
  onedrive: () => Boolean(env.ONEDRIVE_APP_ID && env.ONEDRIVE_REDIRECT_URI),
  canva: () => env.CANVA_IMPORT_ENABLED === 'true',
};

const PROVIDER_SETUP_LABELS = {
  unsplash: 'Backend UNSPLASH access key',
  dropbox: 'Dropbox app key',
  google_drive: 'Google client ID',
  google_photos: 'Google Photos client ID',
  onedrive: 'OneDrive app ID + redirect URI',
  canva: 'Backend Canva import config',
};

const GOOGLE_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.readonly';
const GOOGLE_PHOTOS_SCOPE = 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly';
const GOOGLE_DRIVE_PAGE_SIZE = 24;

const loadExternalScript = (src, id, dataAttributes = {}) => new Promise((resolve, reject) => {
  const existing = id ? document.getElementById(id) : null;
  if (existing) {
    if (existing.dataset.loaded === 'true') {
      resolve();
      return;
    }
    existing.addEventListener('load', () => resolve(), { once: true });
    existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)), { once: true });
    return;
  }
  const script = document.createElement('script');
  script.src = src;
  script.async = true;
  if (id) script.id = id;
  Object.entries(dataAttributes).forEach(([key, value]) => {
    if (value) {
      script.setAttribute(key, value);
    }
  });
  script.onload = () => {
    script.dataset.loaded = 'true';
    resolve();
  };
  script.onerror = () => reject(new Error(`Failed to load ${src}`));
  document.head.appendChild(script);
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const formatFileSize = (bytes) => {
  const size = Number(bytes);
  if (!Number.isFinite(size) || size <= 0) return null;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded = value >= 10 || unitIndex === 0 ? Math.round(value) : value.toFixed(1);
  return `${rounded} ${units[unitIndex]}`;
};

const escapeGoogleDriveQuery = (value = '') => (
  String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'")
);

const PlatformEditor = ({
  platform,
  title,
  headerIcon: HeaderIcon,
  headerColor,
  postType,
  content,
  onContentChange,
  media,            // array of {url, type, name}
  uploading,
  uploadProgress,
  onFilesSelect,    // (files: File[]) => void  — only on first platform
  onImportRemoteMedia, // (items: RemoteImportItem[]) => void
  onRemoveMedia,    // (index: number) => void  — only on first platform
  onReorderMedia,   // (from, to) => void       — only on first platform
  fileInputRef,
  // Accordion expand/collapse
  isExpanded = true,
  onToggleExpand,
  // Drag-to-reorder (applied to the header)
  onDragStart,
  onDragEnter,
  onDragEnd,
  onDragOver,
  // Instagram
  postFormat, onPostFormatChange,
  firstComment, onFirstCommentChange,
  location, onLocationChange,
  shopGridLink, onShopGridLinkChange,
  // YouTube
  videoTitle = '', onVideoTitleChange,
  youtubePrivacy = 'public', onYoutubePrivacyChange,
  // LinkedIn
  linkedinFirstComment, onLinkedinFirstCommentChange,
  linkedinDocumentUrl, linkedinDocumentTitle,
  onLinkedinDocumentChange,
  // TikTok
  tiktokPrivacy = 'public', onTiktokPrivacyChange,
  tiktokAllowDuet = true, onTiktokAllowDuetChange,
  tiktokAllowStitch = true, onTiktokAllowStitchChange,
  tiktokAllowComments = true, onTiktokAllowCommentsChange,
  // Alt Text (parallel array to media)
  altTexts = [],
  onAltTextsChange,
  poll = null,
  onPollChange,
  // Crop callback: (mediaIndex, targetRatio) => void
  onCropMedia,
  // Hashtag groups array: [{id, name, hashtags:[]}]
  hashtagGroups = [],
  errorMessages = [],
  infoMessages = [],
  showPlatformSpecificFields = true,
  onResetToCommon,
  accountTabs = [],
  activeAccountId = null,
  onSelectAccount,
  issueCountOverride,
}) => {
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [hashtagOpen, setHashtagOpen] = useState(false);
  const [gifOpen, setGifOpen] = useState(false);
  const [gifSearch, setGifSearch] = useState('');
  const [gifResults, setGifResults] = useState([]);
  const [gifLoading, setGifLoading] = useState(false);
  const [pollDialogOpen, setPollDialogOpen] = useState(false);
  // Image source dropdown
  const [sourceOpen, setSourceOpen] = useState(false);
  // Unsplash panel
  const [unsplashOpen, setUnsplashOpen] = useState(false);
  const [unsplashQuery, setUnsplashQuery] = useState('');
  const [unsplashResults, setUnsplashResults] = useState([]);
  const [unsplashLoading, setUnsplashLoading] = useState(false);
  const [unsplashPage, setUnsplashPage] = useState(1);
  const [unsplashHasMore, setUnsplashHasMore] = useState(false);
  const [googleDriveOpen, setGoogleDriveOpen] = useState(false);
  const [googleDriveToken, setGoogleDriveToken] = useState('');
  const [googleDriveQuery, setGoogleDriveQuery] = useState('');
  const [googleDriveItems, setGoogleDriveItems] = useState([]);
  const [googleDriveSelectedIds, setGoogleDriveSelectedIds] = useState([]);
  const [googleDriveNextPageToken, setGoogleDriveNextPageToken] = useState(null);
  const [googleDriveLoading, setGoogleDriveLoading] = useState(false);
  const [canvaOpen, setCanvaOpen] = useState(false);
  const [canvaSessionId, setCanvaSessionId] = useState(null);
  const [canvaDesigns, setCanvaDesigns] = useState([]);
  const [canvaQuery, setCanvaQuery] = useState('');
  const [canvaContinuation, setCanvaContinuation] = useState(null);
  const [canvaLoading, setCanvaLoading] = useState(false);
  const [canvaImportingId, setCanvaImportingId] = useState(null);
  const [pollDraft, setPollDraft] = useState(() => createPollDraft(poll, platform));
  const textareaRef = useRef(null);
  const localFileRef = useRef(null);
  const gifFileRef = useRef(null);
  const inputRef = fileInputRef || localFileRef;
  const fileInputId = useId();
  const canvaPopupRef = useRef(null);
  const googleIdentityLoadPromiseRef = useRef(null);
  const googleIdentityReadyRef = useRef(false);

  // Drag-to-reorder media thumbnails
  const mediaDragIdx  = useRef(null);
  const mediaOverIdx  = useRef(null);

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const hasVideo   = mediaArray.some(m => m.type === 'video');
  const isVideoPlatform = platform === 'youtube' || platform === 'tiktok';
  const isVideo    = postType === 'video' || isVideoPlatform;
  const canAddMore = onFilesSelect && !uploading && !hasVideo && !isVideo;
  const canImportFromSources = Boolean(onImportRemoteMedia);

  // Aspect ratio logic
  const idealInfo = getIdealAspectInfo(platform, postFormat);
  // Find images with mismatched aspect ratio (only for first platform that has onCropMedia)
  const aspectWarnings = mediaArray
    .map((item, idx) => {
      if (item.type === 'video' || !item.width || !item.height || !idealInfo) return null;
      const actual = item.width / item.height;
      const delta = Math.abs(actual - idealInfo.ratio) / idealInfo.ratio;
      if (delta <= ASPECT_RATIO_TOLERANCE) return null;
      return { idx, actual, ideal: idealInfo };
    })
    .filter(Boolean);

  const meta = PLATFORM_ICONS[platform] || { icon: FaFacebook, color: '#888' };
  const Icon = HeaderIcon || meta.icon;
  const platformColor = headerColor || meta.color;
  const label = title || platform;
  const limit = CHAR_LIMITS[platform] || 2200;
  const remaining = limit - content.length;
  const pct = content.length / limit;
  const issueCount = typeof issueCountOverride === 'number' ? issueCountOverride : errorMessages.length;

  const counterColor =
    pct >= 1    ? 'text-red-600' :
    pct >= 0.9  ? 'text-orange-500' :
    pct >= 0.7  ? 'text-amber-500' :
    'text-gray-400';
  const supportsPoll = POLL_SUPPORTED_PLATFORMS.includes(platform);
  const pollDurationOptions = POLL_DURATION_OPTIONS[platform] || POLL_DURATION_OPTIONS.twitter;
  const normalizedPoll = poll?.question ? {
    question: poll.question,
    options: Array.isArray(poll.options) ? poll.options.filter(Boolean).slice(0, 4) : [],
    duration: poll.duration || pollDurationOptions[0]?.value || 'ONE_DAY',
  } : null;
  const hasPoll = Boolean(normalizedPoll?.question);
  const pollOptionCount = normalizedPoll?.options?.length || 0;

  const loadCanvaDesignList = useCallback(async (query = '', continuation = null, append = false) => {
    if (!canvaSessionId) return;
    setCanvaLoading(true);
    try {
      const payload = await listCanvaDesigns({
        sessionId: canvaSessionId,
        query,
        continuation,
      });
      const nextDesigns = Array.isArray(payload?.designs) ? payload.designs : [];
      setCanvaDesigns((prev) => (append ? [...prev, ...nextDesigns] : nextDesigns));
      setCanvaContinuation(payload?.continuation || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to load Canva designs');
    } finally {
      setCanvaLoading(false);
    }
  }, [canvaSessionId]);

  useEffect(() => {
    if (!pollDialogOpen) {
      setPollDraft(createPollDraft(poll, platform));
    }
  }, [platform, poll, pollDialogOpen]);

  useEffect(() => {
    const handleCanvaMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;
      if (payload.type === 'canva-import-connected' && payload.session_id) {
        setCanvaSessionId(payload.session_id);
        setCanvaOpen(true);
        setCanvaContinuation(null);
        setCanvaQuery('');
        setCanvaDesigns([]);
        toast.success('Canva connected');
      }
      if (payload.type === 'canva-import-error') {
        toast.error(payload.error || 'Canva import failed');
      }
    };

    window.addEventListener('message', handleCanvaMessage);
    return () => window.removeEventListener('message', handleCanvaMessage);
  }, []);

  useEffect(() => {
    if (canvaOpen && canvaSessionId && canvaDesigns.length === 0 && !canvaLoading) {
      loadCanvaDesignList('', null, false);
    }
  }, [canvaOpen, canvaSessionId, canvaDesigns.length, canvaLoading, loadCanvaDesignList]);

  const insertEmoji = (emoji) => {
    const el = textareaRef.current;
    if (!el) { onContentChange(content + emoji); return; }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    onContentChange(content.slice(0, start) + emoji + content.slice(end));
    setEmojiOpen(false);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + emoji.length, start + emoji.length);
    }, 0);
  };

  const openPollDialog = () => {
    setPollDraft(createPollDraft(poll, platform));
    setPollDialogOpen(true);
  };

  const updatePollOption = (index, value) => {
    setPollDraft((prev) => {
      const nextOptions = [...prev.options];
      nextOptions[index] = value;
      return { ...prev, options: nextOptions };
    });
  };

  const addPollOption = () => {
    setPollDraft((prev) => (
      prev.options.length >= 4
        ? prev
        : { ...prev, options: [...prev.options, ''] }
    ));
  };

  const removePollOption = (index) => {
    setPollDraft((prev) => {
      if (prev.options.length <= 2) return prev;
      return {
        ...prev,
        options: prev.options.filter((_, optionIndex) => optionIndex !== index),
      };
    });
  };

  const canSavePoll = Boolean(pollDraft.question.trim())
    && pollDraft.options.filter((option) => option.trim()).length >= 2;

  const savePoll = () => {
    if (!canSavePoll) return;
    onPollChange?.({
      question: pollDraft.question.trim(),
      options: pollDraft.options.map((option) => option.trim()).filter(Boolean).slice(0, 4),
      duration: pollDraft.duration,
    });
    setPollDialogOpen(false);
  };

  const clearPoll = () => {
    onPollChange?.(null);
    setPollDraft(createPollDraft(null, platform));
    setPollDialogOpen(false);
  };

  // Insert a hashtag group's tags at cursor position
  const insertHashtagGroup = (hashtags) => {
    const el = textareaRef.current;
    const tagStr = hashtags.map(t => t.startsWith('#') ? t : `#${t}`).join(' ');
    if (!el) { onContentChange(content + ' ' + tagStr); setHashtagOpen(false); return; }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const prefix = content.slice(0, start);
    const suffix = content.slice(end);
    const insert = (prefix.endsWith(' ') || prefix === '') ? tagStr : ' ' + tagStr;
    onContentChange(prefix + insert + suffix);
    setHashtagOpen(false);
    setTimeout(() => {
      el.focus();
      const pos = start + insert.length;
      el.setSelectionRange(pos, pos);
    }, 0);
  };

  // Fetch GIFs from Tenor
  const searchGifs = async (query) => {
    if (!query.trim()) { setGifResults([]); return; }
    setGifLoading(true);
    try {
      const key = process.env.REACT_APP_TENOR_API_KEY;
      if (!key) {
        // No API key — user must upload from system
        setGifResults([]);
        return;
      }
      const res = await fetch(
        `https://api.tenor.com/v1/search?q=${encodeURIComponent(query)}&key=${key}&limit=16&media_filter=minimal`
      );
      const data = await res.json();
      const items = (data.results || []).map(r => ({
        id: r.id,
        preview: r.media?.[0]?.tinygif?.url,
        full: r.media?.[0]?.gif?.url,
        title: r.title,
      }));
      setGifResults(items);
    } catch {
      setGifResults([]);
    } finally {
      setGifLoading(false);
    }
  };

  // Pick a GIF URL from search results — download and pass as file
  const handlePickGif = async (gifUrl, title) => {
    setGifOpen(false);
    if (!onFilesSelect) return;
    try {
      toast.info('Downloading GIF…');
      const res = await fetch(gifUrl);
      const blob = await res.blob();
      const file = new File([blob], `${title || 'gif'}.gif`, { type: 'image/gif' });
      onFilesSelect([file]);
    } catch {
      toast.error('Failed to load GIF');
    }
  };

  const importSelectedRemoteMedia = useCallback(async (items) => {
    if (!canImportFromSources) return;
    await Promise.resolve(onImportRemoteMedia(items));
  }, [canImportFromSources, onImportRemoteMedia]);

  // ── Unsplash search ──────────────────────────────────────────────────────
  const searchUnsplash = useCallback(async (query, page = 1) => {
    if (!query.trim()) return;
    setUnsplashLoading(true);
    try {
      const data = await searchUnsplashMedia({ query, page });
      const photos = Array.isArray(data?.results) ? data.results : [];
      if (page === 1) setUnsplashResults(photos);
      else setUnsplashResults(prev => [...prev, ...photos]);
      setUnsplashPage(page);
      setUnsplashHasMore(Boolean(data?.has_more));
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to search Unsplash');
    } finally {
      setUnsplashLoading(false);
    }
  }, []);

  const handlePickUnsplash = async (photo) => {
    if (!canImportFromSources) return;
    setUnsplashOpen(false);
    try {
      toast.info('Importing from Unsplash…');
      await importSelectedRemoteMedia([
        {
          provider: 'unsplash',
          download_url: photo.full,
          name: `unsplash-${photo.id}.jpg`,
          source_item_id: photo.id,
          source_label: photo.description || photo.photographer_name || 'Unsplash image',
          source_attribution: photo.source_attribution,
          tracking_url: photo.download_url,
        },
      ]);
    } catch {
      toast.error('Failed to import Unsplash image');
    }
  };

  const loadDropboxSdk = async () => {
    if (window.Dropbox) return;
    await loadExternalScript(
      'https://www.dropbox.com/static/api/2/dropins.js',
      'dropboxjs',
      { 'data-app-key': env.DROPBOX_APP_KEY }
    );
  };

  // ── Dropbox Chooser ───────────────────────────────────────────────────────
  const openDropboxChooser = async () => {
    setSourceOpen(false);
    if (!MEDIA_SOURCE_SETUP.dropbox()) {
      toast.error(`Add ${PROVIDER_SETUP_LABELS.dropbox} to use Dropbox`);
      return;
    }
    try {
      await loadDropboxSdk();
      window.Dropbox.choose({
        success: async (files) => {
          if (!canImportFromSources) return;
          const items = files.map((file) => ({
            provider: 'dropbox',
            download_url: file.link,
            name: file.name,
            source_item_id: file.id || file.link,
            source_label: file.name,
          }));
          toast.info(`Importing ${items.length} Dropbox file${items.length > 1 ? 's' : ''}…`);
          await importSelectedRemoteMedia(items);
        },
        cancel: () => {},
        linkType: 'direct',
        multiselect: !isVideo,
        extensions: isVideo ? ['video'] : ['images'],
        folderselect: false,
      });
    } catch {
      toast.error('Failed to open Dropbox');
    }
  };

  const loadGoogleIdentityClient = useCallback(() => {
    if (googleIdentityReadyRef.current) {
      return Promise.resolve();
    }
    if (!googleIdentityLoadPromiseRef.current) {
      googleIdentityLoadPromiseRef.current = loadExternalScript(
        'https://accounts.google.com/gsi/client',
        'google-gsi-client'
      ).then(() => {
        googleIdentityReadyRef.current = true;
      });
    }
    return googleIdentityLoadPromiseRef.current;
  }, []);

  const requestGoogleAccessToken = async (scope, clientId) => new Promise((resolve, reject) => {
    const tokenClient = window.google?.accounts?.oauth2?.initTokenClient({
      client_id: clientId,
      scope,
      callback: (response) => {
        if (response?.error) {
          reject(new Error(response.error));
          return;
        }
        resolve(response.access_token);
      },
      error_callback: (error) => {
        const message = error?.type === 'popup_failed_to_open'
          ? 'Google authorization popup was blocked'
          : error?.type === 'popup_closed'
            ? 'Google authorization popup was closed before it finished'
            : 'Google authorization failed';
        reject(new Error(message));
      },
    });

    if (!tokenClient) {
      reject(new Error('Google Identity Services unavailable'));
      return;
    }
    tokenClient.requestAccessToken({ prompt: 'consent' });
  });

  useEffect(() => {
    loadGoogleIdentityClient().catch(() => {});
  }, [loadGoogleIdentityClient]);

  const loadGoogleDriveItems = useCallback(async ({ token, query = '', pageToken = null, append = false }) => {
    setGoogleDriveLoading(true);
    try {
      const queryParts = [
        'trashed = false',
        isVideo ? "mimeType contains 'video/'" : "mimeType contains 'image/'",
      ];
      if (query.trim()) {
        queryParts.push(`name contains '${escapeGoogleDriveQuery(query.trim())}'`);
      }

      const params = new URLSearchParams({
        pageSize: String(GOOGLE_DRIVE_PAGE_SIZE),
        orderBy: 'modifiedTime desc',
        fields: 'nextPageToken,files(id,name,mimeType,size,modifiedTime,thumbnailLink,iconLink,webViewLink)',
        supportsAllDrives: 'true',
        includeItemsFromAllDrives: 'true',
        q: queryParts.join(' and '),
      });
      if (pageToken) {
        params.set('pageToken', pageToken);
      }

      const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params.toString()}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error('Failed to load Google Drive files');
      }

      const payload = await response.json();
      const files = Array.isArray(payload?.files) ? payload.files : [];
      setGoogleDriveItems((prev) => (append ? [...prev, ...files] : files));
      setGoogleDriveNextPageToken(payload?.nextPageToken || null);
    } finally {
      setGoogleDriveLoading(false);
    }
  }, [isVideo]);

  const toggleGoogleDriveSelection = useCallback((fileId) => {
    setGoogleDriveSelectedIds((prev) => {
      if (isVideo) {
        return prev[0] === fileId ? [] : [fileId];
      }
      return prev.includes(fileId)
        ? prev.filter((id) => id !== fileId)
        : [...prev, fileId];
    });
  }, [isVideo]);

  // ── Google Drive Picker ───────────────────────────────────────────────────
  const openGoogleDrivePicker = async () => {
    setSourceOpen(false);
    if (!MEDIA_SOURCE_SETUP.google_drive()) {
      toast.error(`Add ${PROVIDER_SETUP_LABELS.google_drive} to use Google Drive`);
      return;
    }
    try {
      if (!googleIdentityReadyRef.current) {
        await loadGoogleIdentityClient();
      }
      const token = await requestGoogleAccessToken(GOOGLE_DRIVE_SCOPE, env.GOOGLE_CLIENT_ID);
      setGoogleDriveToken(token);
      setGoogleDriveQuery('');
      setGoogleDriveSelectedIds([]);
      setGoogleDriveNextPageToken(null);
      setGoogleDriveItems([]);
      setGoogleDriveOpen(true);
      await loadGoogleDriveItems({ token, query: '', pageToken: null, append: false });
    } catch (error) {
      toast.error(error?.message || 'Google Drive import failed');
    }
  };

  const importGoogleDriveSelection = useCallback(async () => {
    if (!canImportFromSources || !googleDriveToken) return;
    const selectedFiles = googleDriveItems.filter((file) => googleDriveSelectedIds.includes(file.id));
    if (!selectedFiles.length) {
      toast.info('Select at least one Google Drive file to import');
      return;
    }

    try {
      const items = selectedFiles.map((file) => ({
        provider: 'google_drive',
        download_url: `https://www.googleapis.com/drive/v3/files/${file.id}?alt=media`,
        name: file.name,
        source_item_id: file.id,
        source_label: file.name,
        content_type: file.mimeType,
        file_size_bytes: Number(file.size) || undefined,
        auth_bearer_token: googleDriveToken,
      }));
      toast.info(`Importing ${items.length} Google Drive file${items.length > 1 ? 's' : ''}…`);
      await importSelectedRemoteMedia(items);
      setGoogleDriveOpen(false);
      setGoogleDriveSelectedIds([]);
    } catch (error) {
      toast.error(error?.message || 'Google Drive import failed');
    }
  }, [canImportFromSources, googleDriveItems, googleDriveSelectedIds, googleDriveToken, importSelectedRemoteMedia]);

  const parseGoogleDurationMs = (durationValue, fallbackMs) => {
    if (!durationValue || typeof durationValue !== 'string') return fallbackMs;
    const match = durationValue.match(/^(\d+(?:\.\d+)?)s$/);
    if (!match) return fallbackMs;
    return Math.max(1000, Math.round(Number(match[1]) * 1000));
  };

  const openGooglePhotosPicker = async () => {
    setSourceOpen(false);
    if (!MEDIA_SOURCE_SETUP.google_photos()) {
      toast.error(`Add ${PROVIDER_SETUP_LABELS.google_photos} to use Google Photos`);
      return;
    }
    const pickerWindow = window.open('', 'google-photos-picker', 'width=1280,height=800');
    if (!pickerWindow) {
      toast.error('Popup blocked while opening Google Photos');
      return;
    }
    try {
      pickerWindow.document.title = 'Google Photos';
      pickerWindow.document.body.innerHTML = '<div style="font-family:system-ui,-apple-system,sans-serif;padding:32px;color:#111827">Opening Google Photos…</div>';
      if (!googleIdentityReadyRef.current) {
        await loadGoogleIdentityClient();
      }
      const clientId = env.GOOGLE_PHOTOS_CLIENT_ID || env.GOOGLE_CLIENT_ID;
      const token = await requestGoogleAccessToken(GOOGLE_PHOTOS_SCOPE, clientId);
      const sessionResponse = await fetch('https://photospicker.googleapis.com/v1/sessions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });
      if (!sessionResponse.ok) {
        throw new Error('Failed to create Google Photos session');
      }
      const session = await sessionResponse.json();
      if (pickerWindow.closed) {
        throw new Error('Google Photos window was closed before it could finish loading');
      }
      pickerWindow.location.replace(`${session.pickerUri}/autoclose`);
      let pollMs = parseGoogleDurationMs(session.pollingConfig?.pollInterval, 2000);
      const timeoutMs = parseGoogleDurationMs(session.pollingConfig?.timeoutIn, 180000);
      const startedAt = Date.now();
      toast.info('Select media in Google Photos…');

      while (Date.now() - startedAt < timeoutMs) {
        await sleep(pollMs);
        const statusResponse = await fetch(`https://photospicker.googleapis.com/v1/sessions/${session.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!statusResponse.ok) {
          throw new Error('Failed to poll Google Photos session');
        }
        const statusPayload = await statusResponse.json();
        pollMs = parseGoogleDurationMs(statusPayload.pollingConfig?.pollInterval, pollMs);
        if (!statusPayload.mediaItemsSet) {
          continue;
        }

        const itemsResponse = await fetch(`https://photospicker.googleapis.com/v1/mediaItems?sessionId=${session.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!itemsResponse.ok) {
          throw new Error('Failed to load selected Google Photos items');
        }
        const itemsPayload = await itemsResponse.json();
        const selected = (itemsPayload.mediaItems || []).map((item) => ({
          provider: 'google_photos',
          download_url: item.mediaFile?.baseUrl,
          name: item.filename || `google-photos-${item.id}`,
          source_item_id: item.id,
          source_label: item.filename || 'Google Photos media',
          content_type: item.mediaFile?.mimeType || item.mimeType,
          auth_bearer_token: token,
          source_attribution: {
            provider: 'google_photos',
            product_url: item.productUrl || null,
          },
        })).filter((item) => item.download_url);

        const compatible = selected.filter((item) => (
          isVideo
            ? (item.content_type || '').startsWith('video/')
            : (item.content_type || '').startsWith('image/')
        ));
        const filteredSelection = isVideo ? compatible.slice(0, 1) : compatible;

        if (filteredSelection.length > 0) {
          toast.info(`Importing ${filteredSelection.length} Google Photos item${filteredSelection.length > 1 ? 's' : ''}…`);
          await importSelectedRemoteMedia(filteredSelection);
        } else if (selected.length > 0) {
          toast.error(isVideo ? 'Select a video from Google Photos for this post' : 'Select image media from Google Photos for this post');
        } else {
          toast.info('No Google Photos items selected');
        }
        try {
          await fetch(`https://photospicker.googleapis.com/v1/sessions/${session.id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          });
        } catch {
          // Ignore cleanup failures.
        }
        if (!pickerWindow.closed) {
          pickerWindow.close();
        }
        return;
      }

      if (!pickerWindow.closed) {
        pickerWindow.close();
      }
      toast.info('Google Photos selection was cancelled');
    } catch (error) {
      if (!pickerWindow.closed) {
        pickerWindow.close();
      }
      toast.error(error?.message || 'Google Photos import failed');
    }
  };

  const openOneDrivePicker = async () => {
    setSourceOpen(false);
    if (!MEDIA_SOURCE_SETUP.onedrive()) {
      toast.error(`Add ${PROVIDER_SETUP_LABELS.onedrive} to use OneDrive`);
      return;
    }
    try {
      await loadExternalScript('https://js.live.net/v7.2/OneDrive.js', 'onedrive-picker-sdk');
      window.OneDrive.open({
        clientId: env.ONEDRIVE_APP_ID,
        action: 'query',
        multiSelect: !isVideo,
        advanced: {
          redirectUri: env.ONEDRIVE_REDIRECT_URI,
          queryParameters: 'select=id,name,size,file,photo,video,@microsoft.graph.downloadUrl',
          filter: isVideo ? 'folder,.mp4,.mov,.avi,.webm,.m4v' : 'folder,.png,.jpg,.jpeg,.webp,.gif',
        },
        success: async (files) => {
          if (!canImportFromSources) return;
          const values = Array.isArray(files?.value) ? files.value : [];
          const items = values
            .map((file) => ({
              provider: 'onedrive',
              download_url: file['@microsoft.graph.downloadUrl'] || file.link,
              name: file.name,
              source_item_id: file.id,
              source_label: file.name,
              file_size_bytes: Number(file.size) || undefined,
              content_type: file?.file?.mimeType || (file.photo ? 'image/*' : (file.video ? 'video/*' : undefined)),
            }))
            .filter((item) => item.download_url);
          if (!items.length) {
            toast.info('No OneDrive files selected');
            return;
          }
          toast.info(`Importing ${items.length} OneDrive file${items.length > 1 ? 's' : ''}…`);
          await importSelectedRemoteMedia(items);
        },
        cancel: () => {},
        error: (error) => {
          toast.error(error?.message || 'OneDrive import failed');
        },
      });
    } catch (error) {
      toast.error(error?.message || 'Failed to open OneDrive');
    }
  };

  const connectCanva = useCallback(async () => {
    if (!MEDIA_SOURCE_SETUP.canva()) {
      toast.error(`Add ${PROVIDER_SETUP_LABELS.canva} to enable Canva import`);
      return;
    }
    const popup = window.open('', 'canva-import', 'width=1080,height=760');
    if (!popup) {
      toast.error('Popup blocked while connecting Canva');
      return;
    }
    try {
      popup.document.title = 'Connecting Canva';
      popup.document.body.innerHTML = '<div style="font-family:system-ui,-apple-system,sans-serif;padding:32px;color:#111827">Connecting Canva…</div>';
      const payload = await getCanvaImportUrl();
      if (popup.closed) {
        throw new Error('Canva window was closed before it could finish loading');
      }
      popup.location.replace(payload.auth_url);
      canvaPopupRef.current = popup;
    } catch (error) {
      if (!popup.closed) {
        popup.close();
      }
      toast.error(error?.response?.data?.detail || error?.message || 'Failed to start Canva import');
    }
  }, []);

  const importCanvaDesign = useCallback(async (design) => {
    if (!canImportFromSources || !canvaSessionId) return;
    const fileType = isVideo ? 'mp4' : 'png';
    setCanvaImportingId(design.id);
    try {
      let exportJob = await createCanvaExport({
        sessionId: canvaSessionId,
        designId: design.id,
        fileType,
      });
      let attempts = 0;
      while (exportJob.status !== 'success' && exportJob.status !== 'failed' && attempts < 40) {
        await sleep(1500);
        exportJob = await getCanvaExport({
          sessionId: canvaSessionId,
          exportId: exportJob.export_id,
        });
        attempts += 1;
      }
      if (exportJob.status !== 'success' || !Array.isArray(exportJob.download_urls) || exportJob.download_urls.length === 0) {
        throw new Error('Canva export failed');
      }
      const items = exportJob.download_urls.map((downloadUrl, index) => ({
        provider: 'canva',
        download_url: downloadUrl,
        name: `${design.title || 'canva-design'}${exportJob.download_urls.length > 1 ? `-${index + 1}` : ''}.${fileType}`,
        source_item_id: design.id,
        source_label: design.title || 'Canva design',
        source_attribution: {
          provider: 'canva',
          design_id: design.id,
          edit_url: design.edit_url || null,
        },
      }));
      toast.info('Importing Canva design…');
      await importSelectedRemoteMedia(items);
      setCanvaOpen(false);
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || 'Failed to import Canva design');
    } finally {
      setCanvaImportingId(null);
    }
  }, [canImportFromSources, canvaSessionId, importSelectedRemoteMedia, isVideo]);

  const handleDrop = (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files?.length && onFilesSelect) onFilesSelect(Array.from(files));
  };

  const triggerFilePicker = useCallback((event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const input = inputRef?.current;
    if (!input) {
      toast.error('Unable to open file picker right now. Please refresh and try again.');
      return;
    }
    try {
      if (typeof input.showPicker === 'function') {
        input.showPicker();
        return;
      }
    } catch (_) {
      // Some browsers reject showPicker() and still allow click().
    }
    input.click();
  }, [inputRef]);

  const handlePickerKeyDown = useCallback((event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      triggerFilePicker(event);
    }
  }, [triggerFilePicker]);

  const handleFileChange = (e) => {
    const files = e.target.files;
    if (files?.length && onFilesSelect) {
      onFilesSelect(Array.from(files));
      e.target.value = null; // reset input so same file can be re-selected
    }
  };

  return (
  <>
    <div
      className="bg-offwhite rounded-xl border border-gray-200 shadow-sm mb-3 overflow-hidden"
      onDragEnter={onDragEnter}
      onDragOver={(e) => { e.preventDefault(); onDragOver?.(e); }}
    >
      {/* ── Platform header (always visible, clickable to expand/collapse) ── */}
      <div
        className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer select-none transition-colors ${
          isExpanded ? 'border-b border-gray-100' : ''
        } hover:bg-gray-50/70`}
        onClick={onToggleExpand}
        draggable
        onDragStart={(e) => { e.stopPropagation(); onDragStart?.(e); }}
        onDragEnd={onDragEnd}
      >
        {/* Drag handle */}
        <FaGripVertical
          className="text-gray-300 hover:text-gray-400 flex-shrink-0 text-sm cursor-grab active:cursor-grabbing"
          onClick={(e) => e.stopPropagation()}
        />

        {/* Platform icon with brand color bg */}
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: `${platformColor}1a` }}
        >
          <Icon style={{ color: platformColor }} className="text-sm" />
        </div>

        {/* Instagram: inline Post/Reel/Story radios */}
        {platform === 'instagram' && !title ? (
          <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
            {['Post', 'Reel', 'Story'].map((fmt) => (
              <label key={fmt} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name={`postFormat-${platform}`}
                  value={fmt}
                  checked={postFormat === fmt}
                  onChange={() => onPostFormatChange(fmt)}
                  className="w-3.5 h-3.5 accent-pink-500"
                />
                <span className="text-sm font-medium text-gray-700">{fmt}</span>
              </label>
            ))}
          </div>
        ) : (
          <span className="text-sm font-semibold text-gray-700 capitalize">{label}</span>
        )}

        <div className="flex-1" />

        {onResetToCommon && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onResetToCommon(); }}
            className="text-[11px] font-semibold text-blue-600 hover:text-blue-700 mr-2"
          >
            Reset to Common
          </button>
        )}

        {issueCount > 0 && (
          <div className="flex items-center gap-1 rounded-full bg-red-50 border border-red-200 px-2 py-0.5 mr-2">
            <FaExclamationTriangle className="text-[10px] text-red-500" />
            <span className="text-[11px] font-semibold text-red-700">
              {issueCount}
            </span>
          </div>
        )}

        {/* Content preview snippet when collapsed */}
        {!isExpanded && content.trim() && (
          <span className="text-xs text-gray-400 mr-1 max-w-[200px] truncate italic">
            {content.substring(0, 45)}{content.length > 45 ? '…' : ''}
          </span>
        )}

        {/* Expand / Collapse chevron */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggleExpand?.(); }}
          className="flex-shrink-0 w-6 h-6 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {isExpanded
            ? <FaChevronUp className="text-[11px]" />
            : <FaChevronDown className="text-[11px]" />
          }
        </button>
      </div>

      {accountTabs.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-100 bg-gray-50/60 flex flex-wrap gap-2">
          {accountTabs.map((account) => {
            const isActive = activeAccountId === account.id;
            return (
              <button
                key={account.id}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectAccount?.(account.id);
                }}
                title={account.label}
                className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                  isActive
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:text-gray-800'
                }`}
              >
                {account.pictureUrl ? (
                  <img
                    src={account.pictureUrl}
                    alt={account.label}
                    className="h-7 w-7 rounded-full object-cover"
                  />
                ) : (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-300 text-[11px] font-bold text-white">
                    {getAccountInitial(account.label)}
                  </div>
                )}
                {account.errorCount > 0 && (
                  <span className="inline-flex items-center justify-center rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] text-red-700">
                    {account.errorCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Collapsible body ─────────────────────────────────────────────────── */}
      {isExpanded && (
        <>
          {(errorMessages.length > 0 || infoMessages.length > 0) && (
            <div className="px-4 pt-3 space-y-2">
              {errorMessages.length > 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                  <div className="flex items-center gap-2 mb-1">
                    <FaExclamationTriangle className="text-red-500 text-xs" />
                    <span className="text-xs font-semibold text-red-700">Resolve these issues</span>
                  </div>
                  <ul className="space-y-1">
                    {errorMessages.map((message, index) => (
                      <li key={`${message}-${index}`} className="text-xs text-red-700 leading-snug">
                        {message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {infoMessages.length > 0 && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 space-y-1">
                  {infoMessages.map((message, index) => (
                    <p key={`${message}-${index}`} className="text-xs text-blue-700 leading-snug">
                      {message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Textarea */}
          <div className="px-4 pt-3 pb-2">
            <Textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => onContentChange(e.target.value)}
              placeholder="What would you like to share?"
              className="min-h-[90px] resize-none border-none focus-visible:ring-0 px-0 text-[14px] text-gray-800 placeholder:text-gray-300 bg-transparent"
            />
          </div>

          {/* Media area (image / video posts only) */}
          {postType !== 'text' && (
            <div className="px-4 pb-3">
              {/* Hidden file input — multiple for images, single for video */}
              <input
                id={fileInputId}
                ref={inputRef}
                type="file"
                accept={isVideo ? 'video/*' : 'image/*, image/gif'}
                multiple={!isVideo}
                onChange={handleFileChange}
                className="sr-only absolute -left-[9999px] h-px w-px opacity-0"
              />
              {/* Hidden GIF file input */}
              <input
                ref={gifFileRef}
                type="file"
                accept="image/gif"
                className="hidden"
                onChange={(e) => {
                  const files = e.target.files;
                  if (files?.length && onFilesSelect) {
                    onFilesSelect(Array.from(files));
                    e.target.value = null;
                  }
                }}
              />

              {/* ── Primary platform: full upload UI ─────────────────────── */}
              {onFilesSelect && (
                <>
                  {/* Thumbnails row + upload/drop zone */}
                  <div className="flex flex-wrap gap-2 items-start">

                    {/* Existing thumbnails — draggable to reorder */}
                    {mediaArray.map((item, idx) => (
                      <div
                        key={idx}
                        draggable={!!onReorderMedia}
                        onDragStart={() => { mediaDragIdx.current = idx; }}
                        onDragEnter={() => { mediaOverIdx.current = idx; }}
                        onDragEnd={() => {
                          if (
                            mediaDragIdx.current !== null &&
                            mediaOverIdx.current !== null &&
                            mediaDragIdx.current !== mediaOverIdx.current
                          ) {
                            onReorderMedia?.(mediaDragIdx.current, mediaOverIdx.current);
                          }
                          mediaDragIdx.current = null;
                          mediaOverIdx.current = null;
                        }}
                        onDragOver={(e) => e.preventDefault()}
                        className="relative group rounded-md overflow-hidden border border-gray-200 bg-black cursor-grab active:cursor-grabbing"
                        style={{ width: '80px', height: '80px', flexShrink: 0 }}
                        title={item.name}
                      >
                        {item.type === 'video' ? (
                          <video src={item.url} className="w-full h-full object-cover" />
                        ) : (
                          <img src={item.url} alt="" className="w-full h-full object-cover" />
                        )}

                        {/* Remove button */}
                        {onRemoveMedia && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onRemoveMedia(idx); }}
                            className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/70 text-white flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity z-10"
                          >
                            <FaTimes />
                          </button>
                        )}

                        {/* Crop button (images only) */}
                        {onCropMedia && item.type !== 'video' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onCropMedia(idx, idealInfo?.ratio ?? null); }}
                            className="absolute bottom-1 right-1 w-5 h-5 rounded bg-black/70 text-white flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity z-10"
                            title="Crop image"
                          >
                            <FaCrop />
                          </button>
                        )}

                        {/* Position badge when multiple */}
                        {mediaArray.length > 1 && (
                          <div className="absolute bottom-1 left-1 w-4 h-4 rounded bg-black/60 text-white text-[9px] flex items-center justify-center font-medium">
                            {idx + 1}
                          </div>
                        )}
                      </div>
                    ))}

                    {/* Upload progress tile */}
                    {uploading && (
                      <div
                        className="border border-gray-200 rounded-lg flex flex-col items-center justify-center gap-1"
                        style={{ width: '80px', height: '80px', flexShrink: 0 }}
                      >
                        <FaCloudUploadAlt className="text-blue-400 text-xl animate-pulse" />
                        <span className="text-[10px] text-gray-500">{uploadProgress}%</span>
                      </div>
                    )}

                    {/* Drop/add zone — large when empty, small "+" when has media */}
                    {canAddMore && (
                      mediaArray.length === 0 ? (
                        /* Large empty-state drop zone */
                        <div
                          onDrop={handleDrop}
                          onDragOver={(e) => e.preventDefault()}
                          onClick={triggerFilePicker}
                          onKeyDown={handlePickerKeyDown}
                          role="button"
                          tabIndex={0}
                          className="relative border border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all text-center w-full py-6"
                        >
                          <svg className="text-gray-300 mb-1.5" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <rect x="3" y="3" width="18" height="18" rx="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <polyline points="21 15 16 10 5 21" />
                            <line x1="12" y1="8" x2="12" y2="16" />
                            <line x1="8" y1="12" x2="16" y2="12" />
                          </svg>
                          <p className="text-xs text-gray-500">
                            Drag & drop or{' '}
                            <button
                              type="button"
                              className="text-blue-600 cursor-pointer font-medium"
                              onClick={triggerFilePicker}
                            >
                              select files
                            </button>
                          </p>
                          <p className="text-[10px] text-gray-300 mt-0.5">Supports multiple images</p>
                        </div>
                      ) : (
                        /* Small "+" add-more tile */
                        <div
                          onDrop={handleDrop}
                          onDragOver={(e) => e.preventDefault()}
                          onClick={triggerFilePicker}
                          onKeyDown={handlePickerKeyDown}
                          role="button"
                          tabIndex={0}
                          className="relative border border-dashed border-gray-300 rounded-md flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all"
                          style={{ width: '80px', height: '80px', flexShrink: 0 }}
                          title="Add more images"
                        >
                          <svg className="text-gray-300" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <rect x="3" y="3" width="18" height="18" rx="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <polyline points="21 15 16 10 5 21" />
                            <line x1="12" y1="8" x2="12" y2="16" />
                            <line x1="8" y1="12" x2="16" y2="12" />
                          </svg>
                          <p className="text-[10px] text-gray-400 mt-1 text-center">Add more</p>
                        </div>
                      )
                    )}

                    {/* Video: show drop zone only if empty */}
                    {onFilesSelect && isVideo && !uploading && mediaArray.length === 0 && (
                      <div
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}
                        onClick={triggerFilePicker}
                        onKeyDown={handlePickerKeyDown}
                        role="button"
                        tabIndex={0}
                        className="relative border border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all text-center w-full py-6"
                      >
                        <svg className="text-gray-300 mb-1.5" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <polygon points="23 7 16 12 23 17 23 7" />
                          <rect x="1" y="5" width="15" height="14" rx="2" />
                        </svg>
                        <p className="text-xs text-gray-500">
                          Drag & drop or{' '}
                          <button
                            type="button"
                            className="text-blue-600 cursor-pointer font-medium"
                            onClick={triggerFilePicker}
                          >
                            select video
                          </button>
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Shared hint if media present */}
                  {mediaArray.length > 1 && (
                    <p className="text-[10px] text-gray-400 mt-1.5">
                      Drag thumbnails to reorder · {mediaArray.length} image{mediaArray.length !== 1 ? 's' : ''} selected
                    </p>
                  )}

                  {/* ── Aspect Ratio Warning ── */}
                  {aspectWarnings.length > 0 && idealInfo && (
                    <div className="mt-2 rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 flex items-start gap-2">
                      <FaInfoCircle className="text-blue-500 text-sm mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-blue-700 leading-snug">
                          Photos at <strong>{idealInfo.label}</strong> aspect ratio look best on your{' '}
                          {idealInfo.name}.{' '}
                          {onCropMedia ? (
                            <span>
                              Post as-is or{' '}
                              <button
                                type="button"
                                onClick={() => onCropMedia(aspectWarnings[0].idx, idealInfo.ratio)}
                                className="font-semibold underline text-blue-700 hover:text-blue-900 transition-colors"
                              >
                                crop image
                              </button>
                            </span>
                          ) : 'Post as-is or crop before uploading.'}
                        </p>
                        {aspectWarnings.length > 1 && (
                          <div className="flex gap-1 mt-1.5 flex-wrap">
                            {aspectWarnings.map(w => (
                              <button
                                key={w.idx}
                                type="button"
                                onClick={() => onCropMedia?.(w.idx, idealInfo.ratio)}
                                className="flex items-center gap-1 text-[11px] text-blue-700 bg-blue-100 hover:bg-blue-200 px-2 py-0.5 rounded-full transition-colors"
                              >
                                <FaCrop className="text-[9px]" /> Crop #{w.idx + 1}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* ── Alt Text (Accessibility) ── */}
                  {mediaArray.length > 0 && !isVideo && onAltTextsChange && (
                    <div className="mt-3 space-y-2">
                      <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wide">
                        Alt Text (Accessibility)
                      </p>
                      {mediaArray.filter(item => item.type !== 'video').map((item, i) => (
                        <div key={item.url || i} className="flex items-center gap-2">
                          <img
                            src={item.url}
                            alt=""
                            className="w-8 h-8 rounded object-cover flex-shrink-0 border border-gray-100"
                          />
                          <input
                            type="text"
                            placeholder={`Describe image ${i + 1}…`}
                            value={altTexts[i] || ''}
                            onChange={(e) => {
                              const next = [...altTexts];
                              next[i] = e.target.value;
                              onAltTextsChange(next);
                            }}
                            className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300 placeholder:text-gray-300 text-gray-700"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* ── Secondary platforms: show shared thumbnails read-only ─── */}
              {!onFilesSelect && mediaArray.length > 0 && (
                <div>
                  <div className="flex flex-wrap gap-2 items-start">
                    {mediaArray.map((item, idx) => (
                      <div
                        key={idx}
                        className="relative group rounded-md overflow-hidden border border-gray-200 bg-black"
                        style={{ width: '72px', height: '72px', flexShrink: 0 }}
                        title={item.name}
                      >
                        {item.type === 'video' ? (
                          <video src={item.url} className="w-full h-full object-cover" />
                        ) : (
                          <img src={item.url} alt="" className="w-full h-full object-cover" />
                        )}
                        {/* Crop button for secondary platforms */}
                        {onCropMedia && item.type !== 'video' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); onCropMedia(idx, idealInfo?.ratio ?? null); }}
                            className="absolute bottom-1 right-1 w-5 h-5 rounded bg-black/70 text-white flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity z-10"
                            title="Crop image"
                          >
                            <FaCrop />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1.5">
                    {mediaArray.length} file{mediaArray.length !== 1 ? 's' : ''} selected for this platform
                  </p>
                </div>
              )}
            </div>
          )}

          {/* ── Toolbar ──────────────────────────────────────────────────────── */}
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100">
            <div className="flex items-center gap-1">
              {/* Canva + Source Picker dropdown */}
              <div className="flex items-center">
                <a
                  href="https://www.canva.com"
                  target="_blank"
                  rel="noreferrer"
                  className="w-6 h-6 rounded-l-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold font-serif italic hover:opacity-80 transition-opacity flex-shrink-0"
                  title="Open Canva"
                >
                  C
                </a>

                <Popover open={sourceOpen} onOpenChange={setSourceOpen}>
                  <PopoverTrigger asChild>
                    <button
                      className="w-5 h-6 rounded-r-full bg-slate-700 text-white flex items-center justify-center hover:bg-slate-600 transition-colors flex-shrink-0 border-l border-slate-600"
                      title="More image sources"
                    >
                      <FaChevronDown className="text-[9px]" />
                    </button>
                  </PopoverTrigger>

                  <PopoverContent className="w-52 p-1.5" align="start" sideOffset={6}>
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-2 py-1">
                      Image Sources
                    </p>

                    {/* Canva */}
                    <a
                      href="https://www.canva.com"
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      onClick={(event) => {
                        event.preventDefault();
                        setSourceOpen(false);
                        setCanvaOpen(true);
                      }}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiCanva className="text-[#00C4CC] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Canva</span>
                      {!MEDIA_SOURCE_SETUP.canva() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </a>

                    {/* Unsplash */}
                    <button
                      onClick={() => { setSourceOpen(false); setUnsplashOpen(true); setUnsplashResults([]); setUnsplashQuery(''); }}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!canImportFromSources || !MEDIA_SOURCE_SETUP.unsplash()}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiUnsplash className="text-gray-800 text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Unsplash</span>
                      {!MEDIA_SOURCE_SETUP.unsplash() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Dropbox */}
                    <button
                      onClick={openDropboxChooser}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!canImportFromSources || !MEDIA_SOURCE_SETUP.dropbox()}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiDropbox className="text-[#0061FF] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Dropbox</span>
                      {!MEDIA_SOURCE_SETUP.dropbox() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Google Drive */}
                    <button
                      onClick={openGoogleDrivePicker}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!canImportFromSources || !MEDIA_SOURCE_SETUP.google_drive()}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiGoogledrive className="text-[#4285F4] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Google Drive</span>
                      {!MEDIA_SOURCE_SETUP.google_drive() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Google Photos */}
                    <button
                      onClick={openGooglePhotosPicker}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!canImportFromSources || !MEDIA_SOURCE_SETUP.google_photos()}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <MdPhotoLibrary className="text-[#EA4335] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Google Photos</span>
                      {!MEDIA_SOURCE_SETUP.google_photos() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* OneDrive */}
                    <button
                      onClick={openOneDrivePicker}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!canImportFromSources || !MEDIA_SOURCE_SETUP.onedrive()}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        {/* Microsoft OneDrive icon */}
                        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="#0078D4">
                          <path d="M10.5 13.5a4.5 4.5 0 0 0 4.472 4.5H18a3 3 0 0 0 .623-5.927A5.5 5.5 0 0 0 8.05 10.8a3.5 3.5 0 0 0 .45 6.95h2A4.5 4.5 0 0 1 10.5 13.5z"/>
                          <path d="M14.972 18H9a4 4 0 0 1-.39-7.976A6 6 0 0 1 19.586 12.1 3.5 3.5 0 0 1 18 19h-3.028z" opacity=".5"/>
                        </svg>
                      </div>
                      <span className="text-sm text-gray-700">OneDrive</span>
                      {!MEDIA_SOURCE_SETUP.onedrive() && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>
                  </PopoverContent>
                </Popover>
              </div>

              {/* Emoji picker */}
              <Popover open={emojiOpen} onOpenChange={setEmojiOpen}>
                <PopoverTrigger asChild>
                  <button className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors" title="Emoji">
                    <FaSmile className="text-base" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-[320px] p-2" align="start">
                  <div className="grid grid-cols-10 gap-0.5 max-h-52 overflow-y-auto">
                    {EMOJI_LIST.map((e, i) => (
                      <button
                        key={i}
                        onClick={() => insertEmoji(e)}
                        className="text-lg hover:bg-gray-100 rounded p-0.5 transition-colors leading-none w-7 h-7 flex items-center justify-center"
                      >
                        {e}
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>

              {/* Hashtag Groups — 3rd icon */}
              <Popover open={hashtagOpen} onOpenChange={setHashtagOpen}>
                <PopoverTrigger asChild>
                  <button
                    className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
                    title="Hashtag Groups"
                  >
                    <FaHashtag className="text-base" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-2" align="start">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 px-1">
                    Hashtag Groups
                  </p>
                  {hashtagGroups.length === 0 ? (
                    <p className="text-xs text-gray-400 px-1 py-2">
                      No hashtag groups yet. Create them in{' '}
                      <a href="/hashtags" className="text-blue-500 underline" target="_blank" rel="noreferrer">
                        Hashtag Groups
                      </a>
                      .
                    </p>
                  ) : (
                    <div className="space-y-1 max-h-56 overflow-y-auto">
                      {hashtagGroups.map((group) => (
                        <button
                          key={group.id}
                          onClick={() => insertHashtagGroup(group.hashtags)}
                          className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-50 transition-colors"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-gray-700">{group.name}</span>
                            <span className="text-xs text-gray-400">{group.hashtags.length}</span>
                          </div>
                          <p className="text-[11px] text-gray-400 truncate mt-0.5">
                            {group.hashtags.slice(0, 5).map(h => h.startsWith('#') ? h : `#${h}`).join(' ')}
                            {group.hashtags.length > 5 ? ` +${group.hashtags.length - 5}` : ''}
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </PopoverContent>
              </Popover>

              {supportsPoll && (
                <button
                  type="button"
                  onClick={openPollDialog}
                  className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold transition-colors ${
                    hasPoll
                      ? 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                      : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
                  }`}
                  title="Create poll"
                >
                  <FaChartBar className="text-sm" />
                  <span>Poll</span>
                </button>
              )}

              {/* GIF picker — 4th icon (only for image posts) */}
              {postType !== 'text' && !isVideo && (
                <Popover open={gifOpen} onOpenChange={setGifOpen}>
                  <PopoverTrigger asChild>
                    <button
                      className="px-1.5 py-0.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors text-[10px] font-bold tracking-tight border border-gray-200 leading-none"
                      title="Add GIF"
                      style={{ fontSize: '10px', minWidth: '28px' }}
                    >
                      GIF
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="w-72 p-3" align="start">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      Add GIF
                    </p>
                    {/* Upload from system */}
                    <button
                      onClick={() => { setGifOpen(false); gifFileRef.current?.click(); }}
                      className="w-full flex items-center gap-2 px-3 py-2 mb-2 border border-dashed border-gray-300 rounded-lg hover:border-blue-300 hover:bg-blue-50/30 transition-all text-sm text-gray-500"
                    >
                      <FaCloudUploadAlt className="text-gray-400 text-base" />
                      Upload GIF from device
                    </button>

                    {/* Tenor search */}
                    {process.env.REACT_APP_TENOR_API_KEY ? (
                      <>
                        <div className="flex gap-2 mb-2">
                          <div className="relative flex-1">
                            <FaSearch className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-300 text-xs" />
                            <input
                              type="text"
                              placeholder="Search Tenor GIFs…"
                              value={gifSearch}
                              onChange={(e) => setGifSearch(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && searchGifs(gifSearch)}
                              className="w-full pl-6 pr-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-300"
                            />
                          </div>
                          <button
                            onClick={() => searchGifs(gifSearch)}
                            className="px-2.5 py-1.5 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                          >
                            Search
                          </button>
                        </div>
                        {gifLoading && (
                          <p className="text-xs text-gray-400 text-center py-3">Searching…</p>
                        )}
                        {!gifLoading && gifResults.length > 0 && (
                          <div className="grid grid-cols-4 gap-1 max-h-48 overflow-y-auto">
                            {gifResults.map((gif) => (
                              <button
                                key={gif.id}
                                onClick={() => handlePickGif(gif.full, gif.title)}
                                className="relative rounded overflow-hidden hover:ring-2 hover:ring-blue-400 transition-all"
                                style={{ aspectRatio: '1' }}
                                title={gif.title}
                              >
                                <img
                                  src={gif.preview}
                                  alt={gif.title}
                                  className="w-full h-full object-cover"
                                />
                              </button>
                            ))}
                          </div>
                        )}
                        {!gifLoading && gifResults.length === 0 && gifSearch && (
                          <p className="text-xs text-gray-400 text-center py-2">No results. Try a different search.</p>
                        )}
                        <p className="text-[10px] text-gray-300 mt-2 text-center">Powered by Tenor</p>
                      </>
                    ) : (
                      <p className="text-[11px] text-gray-400">
                        Add <code className="bg-gray-100 px-1 rounded">REACT_APP_TENOR_API_KEY</code> to{' '}
                        <code className="bg-gray-100 px-1 rounded">.env</code> to enable GIF search.
                      </p>
                    )}
                  </PopoverContent>
                </Popover>
              )}
            </div>

            {/* Character counter */}
            <span className={`text-xs font-semibold tabular-nums ${counterColor} bg-gray-50 px-2 py-0.5 rounded`}>
              {remaining >= 0 ? remaining : `−${Math.abs(remaining)}`}
            </span>
          </div>

          {hasPoll && (
            <div className="mx-4 mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                    Poll ready
                  </p>
                  <p className="mt-1 text-sm font-semibold text-gray-900">{normalizedPoll.question}</p>
                  <p className="mt-1 text-xs text-amber-800">
                    {pollOptionCount} option{pollOptionCount === 1 ? '' : 's'} • {pollDurationOptions.find((item) => item.value === normalizedPoll.duration)?.label || 'Poll'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={openPollDialog}
                  className="text-xs font-semibold text-amber-700 hover:text-amber-800"
                >
                  Edit
                </button>
              </div>
            </div>
          )}

          {/* ── Instagram-specific fields ─────────────────────────────────────── */}
          {showPlatformSpecificFields && platform === 'instagram' && (
            <div className="border-t border-gray-100 px-4 py-3 space-y-3">
              {/* Add Stickers */}
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-gray-700 w-24 flex-shrink-0">Add Stickers</span>
                <div className="flex items-center gap-2">
                  <button className="flex items-center gap-1.5 px-3 py-1 border border-gray-200 rounded-full text-xs font-medium text-gray-600 hover:border-gray-300 transition-colors">
                    <FaMusic className="text-gray-400 text-xs" /> Music
                  </button>
                  <button className="flex items-center gap-1.5 px-3 py-1 border border-gray-200 rounded-full text-xs font-medium text-gray-600 hover:border-gray-300 transition-colors">
                    <FaShoppingBag className="text-gray-400 text-xs" /> Tag Products
                  </button>
                  <div className="ml-auto flex items-center gap-1 text-blue-600 text-xs font-medium cursor-pointer">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    Automatic <FaChevronDown className="text-[9px]" />
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-[100px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">First Comment</Label>
                <Input placeholder="Your comment" value={firstComment} onChange={(e) => onFirstCommentChange(e.target.value)} className="h-9 text-sm border-gray-200" />
              </div>
              <div className="grid grid-cols-[100px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">Location</Label>
                <div className="relative">
                  <Input placeholder="Type the location" value={location} onChange={(e) => onLocationChange(e.target.value)} className="h-9 text-sm border-gray-200 pr-8" />
                  <FaChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
                </div>
              </div>
              <div className="grid grid-cols-[100px_1fr] items-center gap-3">
                <div className="flex items-center gap-1">
                  <Label className="text-sm font-semibold text-gray-700">Shop Grid Link</Label>
                  <FaInfoCircle className="text-gray-300 text-xs" />
                </div>
                <Input placeholder="Website or Product URL" value={shopGridLink} onChange={(e) => onShopGridLinkChange(e.target.value)} className="h-9 text-sm border-gray-200" />
              </div>
            </div>
          )}

          {/* ── LinkedIn-specific fields ──────────────────────────────────────── */}
          {showPlatformSpecificFields && platform === 'linkedin' && (
            <div className="border-t border-gray-100 px-4 py-3 space-y-3">
              <div className="grid grid-cols-[100px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">First Comment</Label>
                <Input placeholder="Your comment" value={linkedinFirstComment} onChange={(e) => onLinkedinFirstCommentChange(e.target.value)} className="h-9 text-sm border-gray-200" />
              </div>
              {/* Document attachment */}
              <div className="space-y-1.5">
                <Label className="text-sm font-semibold text-gray-700">Document (PDF / PPT / DOC)</Label>
                {linkedinDocumentUrl ? (
                  <div className="flex items-center gap-2 p-2.5 bg-blue-50 border border-blue-200 rounded-lg">
                    {/\.pdf$/i.test(linkedinDocumentUrl) ? (
                      <FaFilePdf className="text-red-500 text-lg flex-shrink-0" />
                    ) : /\.(ppt|pptx)$/i.test(linkedinDocumentUrl) ? (
                      <FaFilePowerpoint className="text-orange-500 text-lg flex-shrink-0" />
                    ) : /\.(doc|docx)$/i.test(linkedinDocumentUrl) ? (
                      <FaFileWord className="text-blue-600 text-lg flex-shrink-0" />
                    ) : (
                      <FaFileAlt className="text-blue-500 text-lg flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-gray-700 truncate">
                        {linkedinDocumentTitle || linkedinDocumentUrl.split('/').pop()}
                      </p>
                      <input
                        type="text"
                        value={linkedinDocumentTitle || ''}
                        onChange={(e) => onLinkedinDocumentChange({ url: linkedinDocumentUrl, title: e.target.value })}
                        placeholder="Document title…"
                        className="mt-1 w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => onLinkedinDocumentChange({ url: null, title: null })}
                      className="text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                    >
                      <FaTimes className="text-xs" />
                    </button>
                  </div>
                ) : (
                  <label className="flex items-center gap-2 p-2.5 border border-dashed border-blue-200 rounded-lg cursor-pointer hover:bg-blue-50 transition-colors">
                    <FaCloudUploadAlt className="text-blue-400 text-base" />
                    <span className="text-xs text-gray-500">Click to attach PDF, PPT, DOC, DOCX</span>
                    <input
                      type="file"
                      accept=".pdf,.ppt,.pptx,.doc,.docx"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file && onLinkedinDocumentChange) onLinkedinDocumentChange({ file, title: file.name.replace(/\.[^.]+$/, '') });
                        e.target.value = '';
                      }}
                    />
                  </label>
                )}
              </div>
            </div>
          )}

          {/* ── YouTube-specific fields ───────────────────────────────────────── */}
          {showPlatformSpecificFields && platform === 'youtube' && (
            <div className="border-t border-gray-100 px-4 py-3 space-y-3">
              <div className="flex justify-end">
                <div className="flex items-center gap-1 text-blue-600 text-xs font-medium cursor-pointer">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  Automatic <FaChevronDown className="text-[9px]" />
                </div>
              </div>
              <div className="grid grid-cols-[80px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">Title</Label>
                <Input placeholder="Enter a title for your video" value={videoTitle} onChange={(e) => onVideoTitleChange(e.target.value)} className="h-9 text-sm border-gray-200" />
              </div>
              <div className="grid grid-cols-[80px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">Category</Label>
                <div className="flex items-center gap-3">
                  <Select defaultValue="entertainment">
                    <SelectTrigger className="h-9 text-sm flex-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="autos">Autos & Vehicles</SelectItem>
                      <SelectItem value="education">Education</SelectItem>
                      <SelectItem value="entertainment">Entertainment</SelectItem>
                      <SelectItem value="howto">Howto & Style</SelectItem>
                      <SelectItem value="music">Music</SelectItem>
                      <SelectItem value="news">News & Politics</SelectItem>
                      <SelectItem value="science">Science & Technology</SelectItem>
                      <SelectItem value="sports">Sports</SelectItem>
                    </SelectContent>
                  </Select>
                  <span className="text-sm font-semibold text-gray-700 flex-shrink-0">Visibility</span>
                  <Select value={youtubePrivacy} onValueChange={onYoutubePrivacyChange}>
                    <SelectTrigger className="h-9 text-sm flex-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">Public</SelectItem>
                      <SelectItem value="unlisted">Unlisted</SelectItem>
                      <SelectItem value="private">Private</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-[80px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">License</Label>
                <Select defaultValue="standard">
                  <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="standard">Standard YouTube License</SelectItem>
                    <SelectItem value="creative">Creative Commons</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-5 flex-wrap">
                {[
                  { id: `${platform}-notify`, label: 'Notify Subscribers', defaultChecked: true },
                  { id: `${platform}-embed`,  label: 'Allow Embedding',    defaultChecked: true },
                  { id: `${platform}-kids`,   label: 'Made for Kids',      defaultChecked: false },
                ].map(({ id, label, defaultChecked }) => (
                  <label key={id} className="flex items-center gap-1.5 cursor-pointer">
                    <Checkbox id={id} defaultChecked={defaultChecked} className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600" />
                    <span className="text-sm text-gray-700">{label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          {/* ── TikTok-specific fields ─────────────────────────────────────────── */}
          {showPlatformSpecificFields && platform === 'tiktok' && (
            <div className="border-t border-gray-100 px-4 py-3 space-y-3">
              <div className="grid grid-cols-[80px_1fr] items-center gap-3">
                <Label className="text-sm font-semibold text-gray-700">Visibility</Label>
                <Select value={tiktokPrivacy} onValueChange={onTiktokPrivacyChange}>
                  <SelectTrigger className="h-9 text-sm border-gray-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="public">Public</SelectItem>
                    <SelectItem value="friends">Friends only</SelectItem>
                    <SelectItem value="private">Private</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-5 flex-wrap">
                {[
                  { label: 'Allow Duet',     value: tiktokAllowDuet,     onChange: onTiktokAllowDuetChange },
                  { label: 'Allow Stitch',   value: tiktokAllowStitch,   onChange: onTiktokAllowStitchChange },
                  { label: 'Allow Comments', value: tiktokAllowComments, onChange: onTiktokAllowCommentsChange },
                ].map(({ label, value, onChange }) => (
                  <label key={label} className="flex items-center gap-1.5 cursor-pointer">
                    <Checkbox
                      checked={!!value}
                      onCheckedChange={onChange}
                      className="data-[state=checked]:bg-black data-[state=checked]:border-black"
                    />
                    <span className="text-sm text-gray-700">{label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>

    <Dialog
      open={googleDriveOpen}
      onOpenChange={(open) => {
        setGoogleDriveOpen(open);
        if (!open) {
          setGoogleDriveSelectedIds([]);
        }
      }}
    >
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SiGoogledrive className="text-[#4285F4] text-lg" />
            <span>Import from Google Drive</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-col gap-2 md:flex-row">
            <div className="relative flex-1">
              <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300 text-sm" />
              <input
                type="text"
                value={googleDriveQuery}
                onChange={(event) => setGoogleDriveQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && googleDriveToken) {
                    loadGoogleDriveItems({
                      token: googleDriveToken,
                      query: googleDriveQuery,
                      pageToken: null,
                      append: false,
                    }).catch(() => {
                      toast.error('Failed to load Google Drive files');
                    });
                  }
                }}
                placeholder={`Search ${isVideo ? 'videos' : 'images'} in Google Drive…`}
                className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
              />
            </div>
            <button
              type="button"
              onClick={() => {
                if (!googleDriveToken) return;
                loadGoogleDriveItems({
                  token: googleDriveToken,
                  query: googleDriveQuery,
                  pageToken: null,
                  append: false,
                }).catch(() => {
                  toast.error('Failed to load Google Drive files');
                });
              }}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
            >
              Search
            </button>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <p className="text-sm font-medium text-gray-900">
                {isVideo ? 'Pick one video to import' : 'Pick one or more images to import'}
              </p>
              <span className="text-xs text-gray-500">
                {googleDriveSelectedIds.length} selected
              </span>
            </div>

            <div className="max-h-[420px] overflow-y-auto">
              {googleDriveItems.map((file) => {
                const isSelected = googleDriveSelectedIds.includes(file.id);
                const fileSize = formatFileSize(file.size);
                const modifiedDate = file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : null;
                return (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => toggleGoogleDriveSelection(file.id)}
                    className={`flex w-full items-center gap-3 border-b border-gray-100 px-4 py-3 text-left last:border-b-0 ${
                      isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    <Checkbox checked={isSelected} className="pointer-events-none data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600" />
                    <div className="flex h-11 w-11 items-center justify-center overflow-hidden rounded-lg bg-gray-100">
                      {file.iconLink ? (
                        <img src={file.iconLink} alt="" className="h-6 w-6 object-contain" />
                      ) : (
                        <FaImages className="text-gray-400" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-gray-900">{file.name || 'Untitled file'}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                        {file.mimeType && <span>{file.mimeType}</span>}
                        {fileSize && <span>{fileSize}</span>}
                        {modifiedDate && <span>Updated {modifiedDate}</span>}
                      </div>
                    </div>
                  </button>
                );
              })}

              {!googleDriveLoading && googleDriveItems.length === 0 && (
                <div className="px-4 py-12 text-center text-sm text-gray-500">
                  No matching Google Drive media found.
                </div>
              )}

              {googleDriveLoading && (
                <div className="px-4 py-12 text-center text-sm text-gray-500">
                  Loading Google Drive files…
                </div>
              )}
            </div>
          </div>

          {googleDriveNextPageToken && !googleDriveLoading && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => {
                  if (!googleDriveToken) return;
                  loadGoogleDriveItems({
                    token: googleDriveToken,
                    query: googleDriveQuery,
                    pageToken: googleDriveNextPageToken,
                    append: true,
                  }).catch(() => {
                    toast.error('Failed to load more Google Drive files');
                  });
                }}
                className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
              >
                Load more
              </button>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <button
            type="button"
            onClick={() => setGoogleDriveOpen(false)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
          >
            Close
          </button>
          <button
            type="button"
            onClick={importGoogleDriveSelection}
            disabled={googleDriveSelectedIds.length === 0}
            className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            Import {googleDriveSelectedIds.length > 0 ? googleDriveSelectedIds.length : ''} {googleDriveSelectedIds.length === 1 ? 'file' : 'files'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog open={canvaOpen} onOpenChange={setCanvaOpen}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SiCanva className="text-[#00C4CC] text-lg" />
            <span>Import from Canva</span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-gray-900">Use exported Canva designs in this post</p>
              <p className="mt-1 text-xs text-gray-500">
                Import recent Canva designs as {isVideo ? 'MP4 video' : 'PNG image'} assets, or open Canva in a new tab.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <a
                href="https://www.canva.com"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
              >
                <FaExternalLinkAlt className="text-[10px]" />
                Open Canva
              </a>
              <button
                type="button"
                onClick={connectCanva}
                className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-700"
              >
                {canvaSessionId ? 'Reconnect Canva' : 'Connect Canva'}
              </button>
            </div>
          </div>

          {!MEDIA_SOURCE_SETUP.canva() && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              <p className="font-semibold">Setup required</p>
              <p className="mt-1 text-xs">
                Enable Canva import in <code className="rounded bg-amber-100 px-1">frontend/.env</code> with
                {' '}<code className="rounded bg-amber-100 px-1">REACT_APP_CANVA_IMPORT_ENABLED=true</code>, and configure
                {' '}<code className="rounded bg-amber-100 px-1">CANVA_CLIENT_ID</code>,
                {' '}<code className="rounded bg-amber-100 px-1">CANVA_CLIENT_SECRET</code>, and
                {' '}<code className="rounded bg-amber-100 px-1">CANVA_REDIRECT_URI</code> on the backend.
              </p>
            </div>
          )}

          {canvaSessionId && (
            <>
              <div className="flex flex-col gap-2 md:flex-row">
                <div className="relative flex-1">
                  <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300 text-sm" />
                  <input
                    type="text"
                    value={canvaQuery}
                    onChange={(event) => setCanvaQuery(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        setCanvaContinuation(null);
                        loadCanvaDesignList(canvaQuery, null, false);
                      }
                    }}
                    placeholder="Search recent Canva designs…"
                    className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setCanvaContinuation(null);
                    loadCanvaDesignList(canvaQuery, null, false);
                  }}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
                >
                  Search
                </button>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                {canvaDesigns.map((design) => (
                  <div key={design.id} className="rounded-xl border border-gray-200 bg-white p-3">
                    <div className="flex gap-3">
                      <div className="h-20 w-20 overflow-hidden rounded-lg bg-gray-100">
                        {design.thumbnail_url ? (
                          <img src={design.thumbnail_url} alt={design.title || 'Canva design'} className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full items-center justify-center text-xs text-gray-400">No preview</div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-gray-900">{design.title || 'Untitled design'}</p>
                        <p className="mt-1 text-xs text-gray-500">
                          {design.updated_at ? `Updated ${new Date(design.updated_at).toLocaleDateString()}` : 'Recent Canva design'}
                        </p>
                        <div className="mt-3 flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => importCanvaDesign(design)}
                            disabled={canvaImportingId === design.id}
                            className="rounded-lg bg-gray-900 px-3 py-2 text-xs font-semibold text-white hover:bg-gray-700 disabled:opacity-50"
                          >
                            {canvaImportingId === design.id ? 'Exporting…' : `Import ${isVideo ? 'MP4' : 'PNG'}`}
                          </button>
                          {design.edit_url && (
                            <a
                              href={design.edit_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700"
                            >
                              Edit
                              <FaExternalLinkAlt className="text-[9px]" />
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {!canvaLoading && canvaDesigns.length === 0 && (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-sm text-gray-500">
                  Connect Canva to load recent designs, then import them directly into this composer.
                </div>
              )}

              {canvaLoading && (
                <div className="rounded-xl border border-dashed border-gray-200 px-4 py-8 text-center text-sm text-gray-500">
                  Loading Canva designs…
                </div>
              )}

              {canvaContinuation && !canvaLoading && (
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={() => loadCanvaDesignList(canvaQuery, canvaContinuation, true)}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:border-gray-300"
                  >
                    Load more
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>

    {/* ── Unsplash Modal ───────────────────────────────────────────────────── */}
    {unsplashOpen && (
      <div
        className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={(e) => { if (e.target === e.currentTarget) setUnsplashOpen(false); }}
      >
        <div className="bg-offwhite rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          style={{ width: '680px', maxWidth: '95vw', height: '600px', maxHeight: '90vh' }}
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-5 py-3.5 border-b border-gray-100">
            <SiUnsplash className="text-gray-800 text-lg" />
            <span className="text-sm font-semibold text-gray-800">Unsplash — Free Stock Photos</span>
            <div className="flex-1" />
            <button
              onClick={() => setUnsplashOpen(false)}
              className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-gray-100 transition-colors text-gray-400"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>

          {/* Search bar */}
          <div className="px-5 py-3 border-b border-gray-100">
            {!MEDIA_SOURCE_SETUP.unsplash() ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700">
                <p className="font-semibold mb-1">Setup required</p>
                <p className="text-xs">
                  Get a free API key at{' '}
                  <a href="https://unsplash.com/developers" target="_blank" rel="noreferrer" className="underline font-medium">
                    unsplash.com/developers
                  </a>{' '}
                  and add <code className="bg-amber-100 px-1 rounded">UNSPLASH_ACCESS_KEY=your_key</code>{' '}
                  to the backend environment.
                </p>
              </div>
            ) : (
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300 text-sm" />
                  <input
                    autoFocus
                    type="text"
                    placeholder="Search free high-res photos…"
                    value={unsplashQuery}
                    onChange={(e) => setUnsplashQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && searchUnsplash(unsplashQuery, 1)}
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-300"
                  />
                </div>
                <button
                  onClick={() => searchUnsplash(unsplashQuery, 1)}
                  disabled={unsplashLoading || !unsplashQuery.trim()}
                  className="px-4 py-2 text-sm bg-gray-900 text-white rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50"
                >
                  {unsplashLoading ? <FaSpinner className="animate-spin" /> : 'Search'}
                </button>
              </div>
            )}
          </div>

          {/* Results grid */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {unsplashLoading && unsplashResults.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <FaSpinner className="animate-spin text-gray-400 text-2xl" />
              </div>
            ) : unsplashResults.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
                <FaImages className="text-4xl opacity-30" />
                <p className="text-sm">
                  {MEDIA_SOURCE_SETUP.unsplash()
                    ? 'Search for beautiful free photos'
                    : 'Add the backend access key to start searching'}
                </p>
              </div>
            ) : (
              <>
                <div className="columns-3 gap-2 space-y-2">
                  {unsplashResults.map((photo) => (
                    <button
                      key={photo.id}
                      onClick={() => handlePickUnsplash(photo)}
                      className="w-full block rounded-lg overflow-hidden relative group break-inside-avoid hover:ring-2 hover:ring-blue-400 transition-all"
                    >
                      <img
                        src={photo.thumb}
                        alt={photo.description || 'Unsplash image'}
                        className="w-full object-cover block"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all flex items-end">
                        <p className="text-white text-[10px] px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity truncate">
                          by{' '}
                          <span
                            className="underline"
                            onClick={(e) => {
                              e.stopPropagation();
                              const profileUrl = photo.photographer_profile
                                ? `${photo.photographer_profile}${photo.photographer_profile.includes('?') ? '&' : '?'}utm_source=socialentangler&utm_medium=referral`
                                : null;
                              if (profileUrl) {
                                window.open(profileUrl, '_blank');
                              }
                            }}
                          >
                            {photo.photographer_name}
                          </span>
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
                {unsplashHasMore && (
                  <button
                    onClick={() => searchUnsplash(unsplashQuery, unsplashPage + 1)}
                    disabled={unsplashLoading}
                    className="w-full mt-3 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-50 rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    {unsplashLoading ? <FaSpinner className="animate-spin text-xs" /> : null}
                    Load more
                  </button>
                )}
                <p className="text-[10px] text-gray-300 text-center mt-3">
                  Photos from{' '}
                  <a href="https://unsplash.com?utm_source=socialentangler&utm_medium=referral" target="_blank" rel="noreferrer" className="underline">
                    Unsplash
                  </a>
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    )}

    <Dialog open={pollDialogOpen} onOpenChange={setPollDialogOpen}>
      <DialogContent className="max-w-xl gap-0 overflow-hidden rounded-2xl p-0">
        <DialogHeader className="border-b border-gray-100 px-5 py-4">
          <DialogTitle className="flex items-center gap-3 text-xl font-bold text-gray-900">
            <span>Add a new poll</span>
            <div className="flex items-center gap-2">
              {POLL_SUPPORTED_PLATFORMS.map((platformId) => {
                const platformMeta = PLATFORM_ICONS[platformId];
                const PollIcon = platformMeta?.icon || FaChartBar;
                const isCurrent = platformId === platform;
                return (
                  <span
                    key={platformId}
                    className={`flex h-8 w-8 items-center justify-center rounded-full border ${
                      isCurrent ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-white text-gray-400'
                    }`}
                  >
                    <PollIcon className="text-sm" />
                  </span>
                );
              })}
            </div>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5 px-5 py-5">
          <div className="space-y-2">
            <Label className="text-sm font-semibold text-gray-900">Question</Label>
            <Input
              value={pollDraft.question}
              onChange={(event) => setPollDraft((prev) => ({ ...prev, question: event.target.value }))}
              placeholder="What would you like to ask?"
              className="h-14 text-lg"
            />
          </div>

          {pollDraft.options.map((option, index) => (
            <div key={`poll-option-${index}`} className="space-y-2">
              <Label className="text-sm font-semibold text-gray-900">
                Option {index + 1}
              </Label>
              <div className="flex items-center gap-2">
                <Input
                  value={option}
                  onChange={(event) => updatePollOption(index, event.target.value)}
                  placeholder={`Option ${index + 1}`}
                  className="h-14 text-lg"
                />
                {pollDraft.options.length > 2 && (
                  <button
                    type="button"
                    onClick={() => removePollOption(index)}
                    className="flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 text-gray-400 hover:border-red-200 hover:text-red-500"
                    aria-label={`Remove option ${index + 1}`}
                  >
                    <FaTimes />
                  </button>
                )}
              </div>
            </div>
          ))}

          {pollDraft.options.length < 4 && (
            <button
              type="button"
              onClick={addPollOption}
              className="text-left text-sm font-semibold text-blue-600 hover:text-blue-700"
            >
              + Add option
            </button>
          )}

          <div className="space-y-2">
            <Label className="text-sm font-semibold text-gray-900">Poll duration</Label>
            <Select
              value={pollDraft.duration}
              onValueChange={(value) => setPollDraft((prev) => ({ ...prev, duration: value }))}
            >
              <SelectTrigger className="h-14 text-lg">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {pollDurationOptions.map((duration) => (
                  <SelectItem key={duration.value} value={duration.value}>
                    {duration.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-amber-700">
              Poll posts for {label} are text-only. Remove any media from this account before publishing.
            </p>
          </div>
        </div>

        <DialogFooter className="border-t border-gray-100 px-5 py-4 sm:justify-between">
          <button
            type="button"
            onClick={clearPoll}
            className="text-sm font-semibold text-blue-600 hover:text-blue-700"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={savePoll}
            disabled={!canSavePoll}
            className="rounded-full bg-blue-600 px-6 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-200"
          >
            Save poll
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>
  );
};

export default PlatformEditor;
