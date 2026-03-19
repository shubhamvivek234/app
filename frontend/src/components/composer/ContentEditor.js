import React, { useState, useRef, useEffect } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { FaSmile, FaLink, FaImage, FaHashtag, FaBold, FaItalic, FaStrikethrough, FaCode, FaMagic } from 'react-icons/fa';
import { generateContent, getHashtagGroups } from '@/lib/api';
import { applyFormat, toBold, toItalic, toStrikethrough, toMonospace } from '@/lib/textFormat';
import { toast } from 'sonner';

const EMOJI_LIST = [
  '😀','😂','😍','🥰','😎','🤩','🙌','👏','🔥','✨','💯','🎉','❤️','💪','👍',
  '😊','🤔','😢','😭','🎊','🚀','💡','📸','🎯','🌟','💥','👀','🤝','📱','💻',
  '🌈','🦋','🌸','🍕','☕','🎵','🎶','📢','💬','📊','🏆','🥳','😄','🙏','💎',
];

const charLimits = {
  twitter: 280,
  bluesky: 300,
  facebook: 2200,
  instagram: 2200,
  linkedin: 3000,
  youtube: 5000,
  tiktok: 2200,
  pinterest: 500,
  threads: 500,
};

/** Small toolbar icon button — uses onMouseDown to keep textarea focus */
const ToolBtn = ({ onClick, title, children, active }) => (
  <button
    type="button"
    onMouseDown={(e) => { e.preventDefault(); onClick(); }}
    title={title}
    className={`p-2 rounded-lg transition-colors text-sm font-medium leading-none
      ${active
        ? 'bg-gray-100 text-gray-800'
        : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
      }`}
  >
    {children}
  </button>
);

const ContentEditor = ({ content, onChange, selectedPlatforms, postType, onMediaClick }) => {
  const [emojiOpen, setEmojiOpen]         = useState(false);
  const [aiOpen, setAiOpen]               = useState(false);
  const [aiPrompt, setAiPrompt]           = useState('');
  const [aiLoading, setAiLoading]         = useState(false);
  const [hashtagOpen, setHashtagOpen]     = useState(false);
  const [hashtagGroups, setHashtagGroups] = useState([]);
  const [hashtagLoading, setHashtagLoading] = useState(false);
  const textareaRef = useRef(null);

  // Most restrictive limit among selected platforms
  const activeLimit = selectedPlatforms.length > 0
    ? Math.min(...selectedPlatforms.map(p => charLimits[p] || 2200))
    : 2200;

  const remaining = activeLimit - content.length;
  const pct = content.length / activeLimit;

  const counterColor =
    pct >= 1 ? 'text-red-600' :
    pct >= 0.9 ? 'text-orange-500' :
    pct >= 0.7 ? 'text-amber-500' :
    'text-gray-400';

  const barColor =
    pct >= 1 ? 'bg-red-500' :
    pct >= 0.9 ? 'bg-orange-400' :
    pct >= 0.7 ? 'bg-amber-400' :
    'bg-blue-400';

  // ── Emoji ─────────────────────────────────────────────────────────────────
  const insertEmoji = (emoji) => {
    const el = textareaRef.current;
    if (!el) { onChange(content + emoji); return; }
    const start = el.selectionStart;
    const end   = el.selectionEnd;
    const newContent = content.slice(0, start) + emoji + content.slice(end);
    onChange(newContent);
    setEmojiOpen(false);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + emoji.length, start + emoji.length);
    }, 0);
  };

  // ── Text Formatting ────────────────────────────────────────────────────────
  const applyTextFormat = (transformFn) => {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart, selectionEnd } = el;
    if (selectionStart === selectionEnd) return; // nothing selected
    const { newValue, selectionStart: newStart, selectionEnd: newEnd } =
      applyFormat(content, selectionStart, selectionEnd, transformFn);
    onChange(newValue);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(newStart, newEnd);
    }, 0);
  };

  // ── AI Caption ─────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!aiPrompt.trim()) return;
    setAiLoading(true);
    try {
      const platform = selectedPlatforms[0] || null;
      const result = await generateContent(aiPrompt.trim(), platform);
      const generated = result.content || '';
      onChange(content ? content + '\n\n' + generated : generated);
      setAiOpen(false);
      setAiPrompt('');
      toast.success('Caption generated!');
    } catch (err) {
      toast.error('Failed to generate caption');
    } finally {
      setAiLoading(false);
    }
  };

  // ── Hashtag Groups ─────────────────────────────────────────────────────────
  const loadHashtagGroups = async () => {
    if (hashtagGroups.length > 0) return; // already loaded
    setHashtagLoading(true);
    try {
      const data = await getHashtagGroups();
      setHashtagGroups(data);
    } catch {
      toast.error('Failed to load hashtag groups');
    } finally {
      setHashtagLoading(false);
    }
  };

  const insertHashtags = (group) => {
    const tags = group.hashtags
      .map(h => (h.startsWith('#') ? h : `#${h}`))
      .join(' ');
    const el = textareaRef.current;
    if (!el) { onChange(content + (content ? ' ' : '') + tags); return; }
    const start = el.selectionStart;
    const prefix = content.length > 0 && !content.endsWith(' ') && !content.endsWith('\n') ? ' ' : '';
    const newContent = content.slice(0, start) + prefix + tags + content.slice(start);
    onChange(newContent);
    setHashtagOpen(false);
    const cursor = start + prefix.length + tags.length;
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(cursor, cursor);
    }, 0);
  };

  // ── Limit label ────────────────────────────────────────────────────────────
  const limitLabel = selectedPlatforms.length > 0
    ? `Limit: ${activeLimit.toLocaleString()} (${selectedPlatforms
        .filter(p => charLimits[p] === activeLimit)
        .map(p => p.charAt(0).toUpperCase() + p.slice(1))
        .join(', ')})`
    : `${activeLimit.toLocaleString()} chars`;

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden mb-4">
      {/* ── Formatting toolbar ── */}
      <div className="flex items-center gap-0.5 px-3 pt-2.5 pb-1 border-b border-gray-100">
        <ToolBtn onClick={() => applyTextFormat(toBold)} title="Bold (select text first)">
          <FaBold />
        </ToolBtn>
        <ToolBtn onClick={() => applyTextFormat(toItalic)} title="Italic (select text first)">
          <FaItalic />
        </ToolBtn>
        <ToolBtn onClick={() => applyTextFormat(toStrikethrough)} title="Strikethrough (select text first)">
          <FaStrikethrough />
        </ToolBtn>
        <ToolBtn onClick={() => applyTextFormat(toMonospace)} title="Monospace (select text first)">
          <FaCode />
        </ToolBtn>

        <div className="w-px h-4 bg-gray-200 mx-1" />

        {/* AI Caption */}
        <Popover open={aiOpen} onOpenChange={setAiOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              title="Generate caption with AI"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-emerald-600 hover:bg-emerald-50 border border-emerald-200 hover:border-emerald-300 transition-colors ml-0.5"
            >
              <FaMagic className="text-xs" />
              <span>AI</span>
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-72 p-3" align="start">
            <p className="text-xs font-semibold text-gray-700 mb-2">Generate with AI</p>
            <textarea
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-emerald-400 placeholder:text-gray-300 text-gray-800"
              rows={3}
              placeholder="e.g. A post about our summer sale…"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleGenerate();
              }}
            />
            <div className="flex justify-end mt-2">
              <button
                type="button"
                onClick={handleGenerate}
                disabled={aiLoading || !aiPrompt.trim()}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {aiLoading ? 'Generating…' : 'Generate'}
              </button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* ── Textarea ── */}
      <Textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          postType === 'video' ? 'Add a caption for your video…' :
          postType === 'image' ? 'Write a caption for your image…' :
          'What would you like to share?'
        }
        className="min-h-[140px] resize-none border-none focus-visible:ring-0 text-[15px] leading-relaxed text-gray-800 placeholder:text-gray-300 p-4 rounded-none"
      />

      {/* ── Character progress bar ── */}
      <div className="px-4 pb-1">
        <div className="w-full h-0.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-200 ${barColor}`}
            style={{ width: `${Math.min(pct * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* ── Bottom toolbar ── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-100">
        <div className="flex items-center gap-1">
          {postType !== 'text' && (
            <button
              type="button"
              onClick={onMediaClick}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
              title="Add media"
            >
              <FaImage className="text-base" />
            </button>
          )}

          {/* Emoji */}
          <Popover open={emojiOpen} onOpenChange={setEmojiOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
                title="Emoji"
              >
                <FaSmile className="text-base" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-2" align="start">
              <div className="grid grid-cols-8 gap-1">
                {EMOJI_LIST.map((e) => (
                  <button
                    key={e}
                    type="button"
                    onClick={() => insertEmoji(e)}
                    className="text-xl hover:bg-gray-100 rounded p-1 transition-colors leading-none"
                  >
                    {e}
                  </button>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          {/* Link placeholder */}
          <button
            type="button"
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
            title="Add link"
          >
            <FaLink className="text-base" />
          </button>

          {/* Hashtag Groups */}
          <Popover
            open={hashtagOpen}
            onOpenChange={(open) => {
              setHashtagOpen(open);
              if (open) loadHashtagGroups();
            }}
          >
            <PopoverTrigger asChild>
              <button
                type="button"
                className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
                title="Insert hashtag group"
              >
                <FaHashtag className="text-base" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-2" align="start">
              <p className="text-xs font-semibold text-gray-500 px-1 mb-2">Hashtag Groups</p>
              {hashtagLoading ? (
                <p className="text-xs text-gray-400 px-1 py-2">Loading…</p>
              ) : hashtagGroups.length === 0 ? (
                <div className="px-1 py-2 text-center">
                  <p className="text-xs text-gray-400 mb-2">No hashtag groups yet.</p>
                  <a
                    href="/hashtags"
                    className="text-xs text-emerald-600 hover:text-emerald-700 font-medium"
                  >
                    Create your first group →
                  </a>
                </div>
              ) : (
                <div className="space-y-1 max-h-56 overflow-y-auto">
                  {hashtagGroups.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      onClick={() => insertHashtags(group)}
                      className="w-full text-left px-2 py-2 rounded-lg hover:bg-gray-50 transition-colors group"
                    >
                      <p className="text-sm font-medium text-gray-800 group-hover:text-gray-900">
                        {group.name}
                      </p>
                      <p className="text-xs text-gray-400 truncate mt-0.5">
                        {group.hashtags.slice(0, 5).map(h => h.startsWith('#') ? h : `#${h}`).join(' ')}
                        {group.hashtags.length > 5 && ` +${group.hashtags.length - 5}`}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </PopoverContent>
          </Popover>
        </div>

        <div className="flex items-center gap-2">
          {content.length > 0 && (
            <span className="text-xs text-gray-400" title={limitLabel}>
              {limitLabel}
            </span>
          )}
          <span className={`text-xs font-semibold tabular-nums ${counterColor}`}>
            {remaining >= 0 ? remaining : `−${Math.abs(remaining)}`}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ContentEditor;
