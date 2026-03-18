import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Progress } from '@/components/ui/progress';
import {
  FaFacebook, FaInstagram, FaLinkedin, FaTwitter,
  FaYoutube, FaTiktok, FaPinterest,
  FaMusic, FaShoppingBag, FaInfoCircle,
  FaSmile, FaHashtag, FaCloudUploadAlt, FaTimes,
  FaChevronDown, FaChevronUp, FaGripVertical,
  FaFileAlt, FaFilePdf, FaFilePowerpoint, FaFileWord,
  FaCrop, FaSearch, FaExternalLinkAlt, FaImages, FaSpinner,
} from 'react-icons/fa';
import {
  SiBluesky, SiThreads, SiGiphy,
  SiCanva, SiDropbox, SiGoogledrive, SiUnsplash,
} from 'react-icons/si';
import { MdPhotoLibrary } from 'react-icons/md';
import { toast } from 'sonner';

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
  linkedin: 3000, youtube: 5000, tiktok: 2200, pinterest: 500, threads: 500,
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

const PlatformEditor = ({
  platform,
  postType,
  content,
  onContentChange,
  media,            // array of {url, type, name}
  uploading,
  uploadProgress,
  onFilesSelect,    // (files: File[]) => void  — only on first platform
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
  videoTitle, onVideoTitleChange,
  youtubePrivacy, onYoutubePrivacyChange,
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
  // Crop callback: (mediaIndex, targetRatio) => void
  onCropMedia,
  // Hashtag groups array: [{id, name, hashtags:[]}]
  hashtagGroups = [],
}) => {
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [hashtagOpen, setHashtagOpen] = useState(false);
  const [gifOpen, setGifOpen] = useState(false);
  const [gifSearch, setGifSearch] = useState('');
  const [gifResults, setGifResults] = useState([]);
  const [gifLoading, setGifLoading] = useState(false);
  // Image source dropdown
  const [sourceOpen, setSourceOpen] = useState(false);
  // Unsplash panel
  const [unsplashOpen, setUnsplashOpen] = useState(false);
  const [unsplashQuery, setUnsplashQuery] = useState('');
  const [unsplashResults, setUnsplashResults] = useState([]);
  const [unsplashLoading, setUnsplashLoading] = useState(false);
  const [unsplashPage, setUnsplashPage] = useState(1);
  const [unsplashHasMore, setUnsplashHasMore] = useState(false);
  const textareaRef = useRef(null);
  const localFileRef = useRef(null);
  const gifFileRef = useRef(null);
  const inputRef = fileInputRef || localFileRef;

  // Drag-to-reorder media thumbnails
  const mediaDragIdx  = useRef(null);
  const mediaOverIdx  = useRef(null);

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const hasVideo   = mediaArray.some(m => m.type === 'video');
  const isVideo    = postType === 'video';
  const canAddMore = onFilesSelect && !uploading && !hasVideo && !isVideo;

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
  const Icon = meta.icon;
  const limit = CHAR_LIMITS[platform] || 2200;
  const remaining = limit - content.length;
  const pct = content.length / limit;

  const counterColor =
    pct >= 1    ? 'text-red-600' :
    pct >= 0.9  ? 'text-orange-500' :
    pct >= 0.7  ? 'text-amber-500' :
    'text-gray-400';

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

  // ── Unsplash search ──────────────────────────────────────────────────────
  const searchUnsplash = useCallback(async (query, page = 1) => {
    const key = process.env.REACT_APP_UNSPLASH_ACCESS_KEY;
    if (!key || !query.trim()) return;
    setUnsplashLoading(true);
    try {
      const res = await fetch(
        `https://api.unsplash.com/search/photos?query=${encodeURIComponent(query)}&per_page=18&page=${page}&client_id=${key}`
      );
      const data = await res.json();
      const photos = (data.results || []).map(p => ({
        id: p.id,
        thumb: p.urls.small,
        full: p.urls.regular,
        alt: p.alt_description || p.description || query,
        user: p.user.name,
        userUrl: p.user.links.html,
        downloadUrl: p.links.download_location,
      }));
      if (page === 1) setUnsplashResults(photos);
      else setUnsplashResults(prev => [...prev, ...photos]);
      setUnsplashPage(page);
      setUnsplashHasMore(data.total_pages > page);
    } catch {
      toast.error('Failed to search Unsplash');
    } finally {
      setUnsplashLoading(false);
    }
  }, []);

  const handlePickUnsplash = async (photo) => {
    if (!onFilesSelect) return;
    setUnsplashOpen(false);
    try {
      // Trigger Unsplash download tracking (required by API guidelines)
      const key = process.env.REACT_APP_UNSPLASH_ACCESS_KEY;
      if (key) fetch(`${photo.downloadUrl}?client_id=${key}`).catch(() => {});

      toast.info('Downloading image…');
      const res = await fetch(photo.full);
      const blob = await res.blob();
      const ext = blob.type.includes('png') ? 'png' : 'jpg';
      const file = new File([blob], `unsplash-${photo.id}.${ext}`, { type: blob.type });
      onFilesSelect([file]);
    } catch {
      toast.error('Failed to download image');
    }
  };

  // ── Dropbox Chooser ───────────────────────────────────────────────────────
  const openDropboxChooser = () => {
    setSourceOpen(false);
    const appKey = process.env.REACT_APP_DROPBOX_APP_KEY;
    if (!appKey) {
      toast.error('Add REACT_APP_DROPBOX_APP_KEY to .env to use Dropbox');
      return;
    }
    if (!window.Dropbox) {
      // Dynamically load Dropbox SDK
      const script = document.createElement('script');
      script.src = 'https://www.dropbox.com/static/api/2/dropins.js';
      script.setAttribute('data-app-key', appKey);
      script.id = 'dropboxjs';
      script.onload = () => launchDropboxChooser();
      document.head.appendChild(script);
    } else {
      launchDropboxChooser();
    }
  };

  const launchDropboxChooser = () => {
    window.Dropbox.choose({
      success: async (files) => {
        if (!onFilesSelect) return;
        toast.info(`Downloading ${files.length} file${files.length > 1 ? 's' : ''} from Dropbox…`);
        const fileObjs = [];
        for (const f of files) {
          try {
            const res = await fetch(f.link);
            const blob = await res.blob();
            const name = f.name;
            fileObjs.push(new File([blob], name, { type: blob.type }));
          } catch {
            toast.error(`Failed to download ${f.name}`);
          }
        }
        if (fileObjs.length) onFilesSelect(fileObjs);
      },
      cancel: () => {},
      linkType: 'direct',
      multiselect: !isVideo,
      extensions: isVideo ? ['video'] : ['images'],
      folderselect: false,
    });
  };

  // ── Google Drive Picker ───────────────────────────────────────────────────
  const openGoogleDrivePicker = () => {
    setSourceOpen(false);
    const apiKey = process.env.REACT_APP_GOOGLE_PICKER_API_KEY;
    const clientId = process.env.REACT_APP_GOOGLE_CLIENT_ID;
    if (!apiKey || !clientId) {
      toast.error('Add REACT_APP_GOOGLE_PICKER_API_KEY and REACT_APP_GOOGLE_CLIENT_ID to .env to use Google Drive');
      return;
    }
    loadGooglePickerScript(() => {
      window.gapi.load('auth2,picker', () => {
        window.gapi.auth2.getAuthInstance()?.signIn().then((user) => {
          const token = user.getAuthResponse().access_token;
          const view = new window.google.picker.DocsView(window.google.picker.ViewId.DOCS_IMAGES);
          const picker = new window.google.picker.PickerBuilder()
            .enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED)
            .setOAuthToken(token)
            .setDeveloperKey(apiKey)
            .addView(view)
            .setCallback(async (data) => {
              if (data.action === window.google.picker.Action.PICKED) {
                const docs = data[window.google.picker.Response.DOCUMENTS];
                toast.info('Downloading from Google Drive…');
                const fileObjs = [];
                for (const doc of docs) {
                  try {
                    const res = await fetch(
                      `https://www.googleapis.com/drive/v3/files/${doc.id}?alt=media`,
                      { headers: { Authorization: `Bearer ${token}` } }
                    );
                    const blob = await res.blob();
                    fileObjs.push(new File([blob], doc.name, { type: blob.type }));
                  } catch {
                    toast.error(`Failed to download ${doc.name}`);
                  }
                }
                if (fileObjs.length) onFilesSelect(fileObjs);
              }
            })
            .build();
          picker.setVisible(true);
        }).catch(() => toast.error('Google sign-in failed'));
      });
    });
  };

  const loadGooglePickerScript = (cb) => {
    if (window.gapi) { cb(); return; }
    const script = document.createElement('script');
    script.src = 'https://apis.google.com/js/api.js';
    script.onload = () => {
      window.gapi.load('client', () => {
        window.gapi.client.init({ apiKey: process.env.REACT_APP_GOOGLE_PICKER_API_KEY, clientId: process.env.REACT_APP_GOOGLE_CLIENT_ID, scope: 'https://www.googleapis.com/auth/drive.readonly' }).then(cb);
      });
    };
    document.head.appendChild(script);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files?.length && onFilesSelect) onFilesSelect(Array.from(files));
  };

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
      className="bg-white rounded-xl border border-gray-200 shadow-sm mb-3 overflow-hidden"
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
          style={{ backgroundColor: `${meta.color}1a` }}
        >
          <Icon style={{ color: meta.color }} className="text-sm" />
        </div>

        {/* Instagram: inline Post/Reel/Story radios */}
        {platform === 'instagram' ? (
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
          <span className="text-sm font-semibold text-gray-700 capitalize">{platform}</span>
        )}

        <div className="flex-1" />

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

      {/* ── Collapsible body ─────────────────────────────────────────────────── */}
      {isExpanded && (
        <>
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
                ref={inputRef}
                type="file"
                accept={isVideo ? 'video/*' : 'image/*, image/gif'}
                multiple={!isVideo}
                onChange={handleFileChange}
                className="hidden"
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
                            onClick={(e) => { e.stopPropagation(); onCropMedia(idx, null); }}
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
                          onClick={() => inputRef.current?.click()}
                          onDrop={handleDrop}
                          onDragOver={(e) => e.preventDefault()}
                          className="border border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all text-center w-full py-6"
                        >
                          <svg className="text-gray-300 mb-1.5" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <rect x="3" y="3" width="18" height="18" rx="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <polyline points="21 15 16 10 5 21" />
                            <line x1="12" y1="8" x2="12" y2="16" />
                            <line x1="8" y1="12" x2="16" y2="12" />
                          </svg>
                          <p className="text-xs text-gray-500">
                            Drag & drop or <span className="text-blue-600">select files</span>
                          </p>
                          <p className="text-[10px] text-gray-300 mt-0.5">Supports multiple images</p>
                        </div>
                      ) : (
                        /* Small "+" add-more tile */
                        <div
                          onClick={() => inputRef.current?.click()}
                          onDrop={handleDrop}
                          onDragOver={(e) => e.preventDefault()}
                          className="border border-dashed border-gray-300 rounded-md flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all"
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
                        onClick={() => inputRef.current?.click()}
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}
                        className="border border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 transition-all text-center w-full py-6"
                      >
                        <svg className="text-gray-300 mb-1.5" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <polygon points="23 7 16 12 23 17 23 7" />
                          <rect x="1" y="5" width="15" height="14" rx="2" />
                        </svg>
                        <p className="text-xs text-gray-500">
                          Drag & drop or <span className="text-blue-600">select video</span>
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
                            onClick={(e) => { e.stopPropagation(); onCropMedia(idx, null); }}
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
                    Shared from first platform ({mediaArray.length} file{mediaArray.length !== 1 ? 's' : ''})
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
                      onClick={() => setSourceOpen(false)}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiCanva className="text-[#00C4CC] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Canva</span>
                      <FaExternalLinkAlt className="text-gray-300 text-[9px] ml-auto" />
                    </a>

                    {/* Unsplash */}
                    <button
                      onClick={() => { setSourceOpen(false); setUnsplashOpen(true); setUnsplashResults([]); setUnsplashQuery(''); }}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!onFilesSelect}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiUnsplash className="text-gray-800 text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Unsplash</span>
                      {!process.env.REACT_APP_UNSPLASH_ACCESS_KEY && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Dropbox */}
                    <button
                      onClick={openDropboxChooser}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!onFilesSelect}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiDropbox className="text-[#0061FF] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Dropbox</span>
                      {!process.env.REACT_APP_DROPBOX_APP_KEY && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Google Drive */}
                    <button
                      onClick={openGoogleDrivePicker}
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left"
                      disabled={!onFilesSelect}
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <SiGoogledrive className="text-[#4285F4] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Google Drive</span>
                      {(!process.env.REACT_APP_GOOGLE_PICKER_API_KEY || !process.env.REACT_APP_GOOGLE_CLIENT_ID) && (
                        <span className="text-[10px] text-amber-500 ml-auto">Setup</span>
                      )}
                    </button>

                    {/* Google Photos */}
                    <button
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left opacity-50 cursor-not-allowed"
                      title="Coming soon"
                      disabled
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        <MdPhotoLibrary className="text-[#EA4335] text-base" />
                      </div>
                      <span className="text-sm text-gray-700">Google Photos</span>
                      <span className="text-[10px] text-gray-400 ml-auto">Soon</span>
                    </button>

                    {/* OneDrive */}
                    <button
                      className="flex items-center gap-2.5 px-2 py-2 rounded hover:bg-gray-50 transition-colors w-full text-left opacity-50 cursor-not-allowed"
                      title="Coming soon"
                      disabled
                    >
                      <div className="w-5 h-5 flex items-center justify-center">
                        {/* Microsoft OneDrive icon */}
                        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="#0078D4">
                          <path d="M10.5 13.5a4.5 4.5 0 0 0 4.472 4.5H18a3 3 0 0 0 .623-5.927A5.5 5.5 0 0 0 8.05 10.8a3.5 3.5 0 0 0 .45 6.95h2A4.5 4.5 0 0 1 10.5 13.5z"/>
                          <path d="M14.972 18H9a4 4 0 0 1-.39-7.976A6 6 0 0 1 19.586 12.1 3.5 3.5 0 0 1 18 19h-3.028z" opacity=".5"/>
                        </svg>
                      </div>
                      <span className="text-sm text-gray-700">OneDrive</span>
                      <span className="text-[10px] text-gray-400 ml-auto">Soon</span>
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

          {/* ── Instagram-specific fields ─────────────────────────────────────── */}
          {platform === 'instagram' && (
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
          {platform === 'linkedin' && (
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
          {platform === 'youtube' && (
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
          {platform === 'tiktok' && (
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

    {/* ── Unsplash Modal ───────────────────────────────────────────────────── */}
    {unsplashOpen && (
      <div
        className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={(e) => { if (e.target === e.currentTarget) setUnsplashOpen(false); }}
      >
        <div className="bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden"
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
            {!process.env.REACT_APP_UNSPLASH_ACCESS_KEY ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700">
                <p className="font-semibold mb-1">Setup required</p>
                <p className="text-xs">
                  Get a free API key at{' '}
                  <a href="https://unsplash.com/developers" target="_blank" rel="noreferrer" className="underline font-medium">
                    unsplash.com/developers
                  </a>{' '}
                  and add <code className="bg-amber-100 px-1 rounded">REACT_APP_UNSPLASH_ACCESS_KEY=your_key</code>{' '}
                  to <code className="bg-amber-100 px-1 rounded">frontend/.env</code>
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
                  {process.env.REACT_APP_UNSPLASH_ACCESS_KEY
                    ? 'Search for beautiful free photos'
                    : 'Add your API key to start searching'}
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
                        alt={photo.alt}
                        className="w-full object-cover block"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all flex items-end">
                        <p className="text-white text-[10px] px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity truncate">
                          by{' '}
                          <span
                            className="underline"
                            onClick={(e) => { e.stopPropagation(); window.open(photo.userUrl + '?utm_source=socialentangler&utm_medium=referral', '_blank'); }}
                          >
                            {photo.user}
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
  </>
  );
};

export default PlatformEditor;
