import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaArrowLeft, FaCopy, FaCheck, FaTrash, FaPaperPlane, FaDesktop, FaMobileAlt,
  FaThumbsUp, FaCommentDots, FaShare, FaBookmark, FaGlobeAmericas, FaLightbulb,
  FaHeart, FaFire, FaRocket, FaUndo
} from 'react-icons/fa';
import { SiLinkedin } from 'react-icons/si';
import { useAuth } from '@/context/AuthContext';
import {
  toBoldSans, toBoldSerif, toItalicSans, toItalicSerif, toBoldItalic,
  toUnderline, toDoubleUnderline, toStrikethrough, toMonospace,
  toScript, toBoldScript, toDoubleStruck, toGothic, toSmallCaps,
  toPlainText, toBulletList, toCircledNumberedList, applyFormat, STYLE_CATALOGUE
} from '@/lib/textFormat';

const TEMPLATES = [
  {
    name: '🎯 Contrarian Take',
    content: `Most people believe that 𝗒𝗈𝗎 𝗇𝖾𝖾𝖽 𝗍𝗈 𝗐𝗈𝗋𝗄 𝟪𝟢 𝗁𝗈𝗎𝗋𝗌 𝖺 𝗐𝖾𝖾𝗄 to succeed.\n\nThey're completely wrong.\n\nHere are 3 harsh truths I learned the hard way:\n\n➊ 𝗢𝘂𝘁𝗽𝘂𝘁 > 𝗛𝗼𝘂𝗿𝘀: Quality decisions compound faster than busywork.\n➋ 𝗦𝘆𝘀𝘁𝗲𝗺𝘀 > 𝗠𝗼𝘁𝗶𝘃𝗮𝘁𝗶𝗼𝗻: Motivation fades; automations run forever.\n➌ 𝗥𝗲𝘀𝘁 𝗶𝘀 𝗮 𝗦𝘁𝗿𝗮𝘁𝗲𝗴𝘆: Exhausted leaders make catastrophic mistakes.\n\n👉 What's your take? Agree or disagree?`,
  },
  {
    name: '🚀 5-Step Framework',
    content: `How to master 𝗰𝗼𝗻𝘁𝗲𝗻𝘁 𝗱𝗶𝘀𝘁𝗿𝗶𝗯𝘂𝘁𝗶𝗼𝗻 in 2026:\n\n(A 5-step actionable framework)\n\n➊ 𝗦𝘁𝗲𝗽 𝟭: Pick 1 core pillar topic.\n➋ 𝗦𝘁𝗲𝗽 𝟮: Write 1 long-form high-value breakdown.\n➌ 𝗦𝘁𝗲𝗽 𝟯: Repurpose into 5 carousel slides & 3 short threads.\n➍ 𝗦𝘁𝗲𝗽 𝟰: Schedule across LinkedIn, X, and Instagram.\n➎ 𝗦𝘁𝗲𝗽 𝟱: Analyze top 10% performers and double down.\n\nSave this for your next launch 📌`,
  },
  {
    name: '📈 Personal Story / Transformation',
    content: `3 years ago, I had 𝟢 𝖼𝗅𝗂𝖾𝗇𝗍𝗌 and zero online presence.\n\nToday, we just crossed 𝟭𝟬,𝟬𝟬𝟬+ active creators on our platform.\n\nHere are the 4 fundamental mindset shifts that changed everything:\n\n➊ 𝗦𝗵𝗶𝗳𝘁 𝟭: Focus on giving value before asking for anything.\n➋ 𝗦𝗵𝗶𝗳𝘁 𝟮: Consistency over intensity (1 post/day > 10 posts/month).\n➌ 𝗦𝗵𝗶𝗳𝘁 𝟯: Build in public with total transparency.\n➍ 𝗦𝗵𝗶𝗳𝘁 𝟰: Delegate low-leverage tasks early.\n\nIf you're starting today: keep going. Compounding is real. 🚀`,
  },
  {
    name: '✨ Curated Resource List',
    content: `10 free creator tools that feel illegal to know:\n\n🔹 𝗨𝗻𝗿𝗮𝘃𝗹𝗲𝗿 — Multi-platform social scheduling & analytics\n🔹 𝗖𝗮𝗻𝘃𝗮 — Rapid visual graphics & carousel templates\n🔹 𝗡𝗼𝘁𝗶𝗼𝗻 — Centralized content workspace & wiki\n🔹 𝗖𝗵𝗮𝘁𝗚𝗣𝗧 — Ideation & draft brainstorming partner\n🔹 𝗨𝗻𝘀𝗽𝗹𝗮𝘀𝗵 — High-resolution royalty-free imagery\n\n♻️ Repost if you found this valuable!`,
  },
];

const EMOJI_PILLS = ['👉', '🚀', '💡', '✅', '🔹', '📌', '🔥', '📈', '✨', '🎯', '🧵', '💬'];

export default function LinkedInTextFormatter({ onBack }) {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [text, setText] = useState(
    `How to write 𝗵𝗶𝗴𝗵-𝗲𝗻𝗴𝗮𝗴𝗲𝗺𝗲𝗻𝘁 𝗟𝗶𝗻𝗸𝗲𝗱𝗜𝗻 𝗽𝗼𝘀𝘁𝘀 in 2026:\n\nMost posts get ignored because the 𝘩𝘰𝘰𝘬 is weak.\n\nHere is how to fix it in 3 steps:\n\n➊ 𝗦𝘁𝗮𝗿𝘁 𝘄𝗶𝘁𝗵 𝗮 𝗽𝘂𝗻𝗰𝗵𝘆 𝗵𝗼𝗼𝗸 (under 140 chars)\n➋ 𝗨𝘀𝗲 𝘄𝗵𝗶𝘁𝗲𝘀𝗽𝗮𝗰𝗲 to make it readable\n➌ 𝗔𝗱𝗱 𝗮 𝗰𝗹𝗲𝗮𝗿 𝗰𝗮𝗹𝗹-𝘁𝗼-𝗮𝗰𝘁𝗶𝗼𝗻 at the bottom\n\n👉 Try selecting any text above and clicking a format button!`
  );

  const [copied, setCopied] = useState(false);
  const [previewDevice, setPreviewDevice] = useState('desktop'); // 'desktop' | 'mobile'
  const [isSeeMoreExpanded, setIsSeeMoreExpanded] = useState(false);
  const textareaRef = useRef(null);

  // Character and line metrics
  const charCount = text.length;
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const lines = text.split('\n');

  // LinkedIn hook fold cutoff is roughly first 3 lines or ~140 chars
  const hookThresholdChars = previewDevice === 'mobile' ? 140 : 210;
  const hookLines = lines.slice(0, 3).join('\n');
  const isHookShort = hookLines.length <= hookThresholdChars;

  const handleApplyTransform = (transformFn) => {
    const el = textareaRef.current;
    if (!el) {
      setText((prev) => transformFn(prev));
      return;
    }
    const { selectionStart, selectionEnd } = el;
    const { newValue, selectionStart: newStart, selectionEnd: newEnd } = applyFormat(
      text,
      selectionStart,
      selectionEnd,
      transformFn
    );
    setText(newValue);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(newStart, newEnd);
    }, 0);
  };

  const handleInsertBullet = (bulletSymbol) => {
    const el = textareaRef.current;
    if (!el) return;
    const { selectionStart, selectionEnd } = el;
    if (selectionStart !== selectionEnd) {
      const selected = text.slice(selectionStart, selectionEnd);
      const formatted = toBulletList(selected, bulletSymbol);
      const newValue = text.slice(0, selectionStart) + formatted + text.slice(selectionEnd);
      setText(newValue);
    } else {
      const before = text.slice(0, selectionStart);
      const after = text.slice(selectionStart);
      const newValue = `${before}${bulletSymbol} ${after}`;
      setText(newValue);
    }
    el.focus();
  };

  const handleInsertEmoji = (emoji) => {
    const el = textareaRef.current;
    if (!el) {
      setText((prev) => prev + emoji);
      return;
    }
    const { selectionStart, selectionEnd } = el;
    const before = text.slice(0, selectionStart);
    const after = text.slice(selectionEnd);
    const newValue = `${before}${emoji}${after}`;
    setText(newValue);
    setTimeout(() => {
      el.focus();
      const pos = selectionStart + emoji.length;
      el.setSelectionRange(pos, pos);
    }, 0);
  };

  const handleCopy = () => {
    if (!text.trim()) {
      toast.error('Nothing to copy!');
      return;
    }
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success('Formatted text copied to clipboard!');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCreatePost = () => {
    if (!text.trim()) {
      toast.error('Please enter or format some text first.');
      return;
    }
    navigate('/create-post', { state: { initialContent: text } });
  };

  // Preview content truncated at the "...see more" fold
  const getDisplayContent = () => {
    if (isSeeMoreExpanded || lines.length <= 3) {
      return text;
    }
    return lines.slice(0, 3).join('\n');
  };

  const authorName = user?.name || user?.email?.split('@')[0] || 'LinkedIn Creator';
  const authorHeadline = user?.headline || 'Founder • Content Creator • Growth Strategist';
  const authorInitial = authorName.charAt(0).toUpperCase();

  return (
    <div className="w-full pb-16">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:text-gray-900 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 transition-all shadow-xs"
          >
            <FaArrowLeft className="text-[10px]" /> Back to Tools
          </button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
              <SiLinkedin className="text-blue-600 text-lg" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 leading-tight">LinkedIn Text Formatter</h2>
              <p className="text-[11px] text-gray-500">Transform regular text into Unicode bold, italic, lists & preview live feed</p>
            </div>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-xl transition-all shadow-xs"
          >
            {copied ? <FaCheck className="text-green-600 text-xs" /> : <FaCopy className="text-xs" />}
            {copied ? 'Copied!' : 'Copy Text'}
          </button>
          <button
            onClick={handleCreatePost}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-xl transition-all shadow-xs"
          >
            <FaPaperPlane className="text-[10px]" /> Open in Composer
          </button>
        </div>
      </div>

      {/* Main Studio Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* ── Left Column: Editor & Controls (7 Cols) ── */}
        <div className="lg:col-span-7 space-y-4">

          {/* Quick Viral Templates */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                <FaFire className="text-amber-500 text-xs" /> 1-Click Viral Templates
              </span>
              <span className="text-[10px] text-gray-400">Click to load</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {TEMPLATES.map((tmpl, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setText(tmpl.content);
                    toast.success(`Loaded "${tmpl.name}" template`);
                  }}
                  className="px-2.5 py-2 text-[11px] font-semibold text-gray-700 bg-gray-50 hover:bg-blue-50 hover:text-blue-700 border border-gray-100 hover:border-blue-200 rounded-xl text-left transition-all truncate"
                  title={tmpl.name}
                >
                  {tmpl.name}
                </button>
              ))}
            </div>
          </div>

          {/* Typography Toolbar */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-700">Typography & Unicode Styles</span>
              <button
                onClick={() => handleApplyTransform(toPlainText)}
                className="flex items-center gap-1 text-[11px] font-semibold text-gray-500 hover:text-red-600 transition-colors"
                title="Convert all Unicode back to standard plain text"
              >
                <FaUndo className="text-[9px]" /> Strip to Plain Text
              </button>
            </div>

            {/* Font Style Buttons */}
            <div className="flex flex-wrap gap-1.5">
              {STYLE_CATALOGUE.map((st) => (
                <button
                  key={st.id}
                  onClick={() => handleApplyTransform(st.fn)}
                  className="px-2.5 py-1.5 text-xs font-medium bg-gray-50 hover:bg-gray-100 border border-gray-200 text-gray-800 rounded-lg transition-all hover:border-gray-300 active:scale-95"
                  title={`Apply ${st.name} (Select text or applies to entire post)`}
                >
                  {st.preview}
                </button>
              ))}
            </div>

            {/* List & Bullet Quick Inserts */}
            <div className="pt-2 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-[10px] font-bold text-gray-400 mr-1 uppercase">Bullets:</span>
                <button
                  onClick={() => handleApplyTransform((s) => toCircledNumberedList(s, true))}
                  className="px-2 py-1 text-[11px] font-semibold bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md text-gray-700"
                  title="Format with circled numbers ➊ ➋ ➌"
                >
                  ➊ ➋ ➌
                </button>
                <button
                  onClick={() => handleApplyTransform((s) => toCircledNumberedList(s, false))}
                  className="px-2 py-1 text-[11px] font-semibold bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md text-gray-700"
                  title="Format with white circled numbers ① ② ③"
                >
                  ① ② ③
                </button>
                <button
                  onClick={() => handleInsertBullet('•')}
                  className="px-2 py-1 text-[11px] font-semibold bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md text-gray-700"
                  title="Bullet list •"
                >
                  • Dot
                </button>
                <button
                  onClick={() => handleInsertBullet('🔹')}
                  className="px-2 py-1 text-[11px] font-semibold bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md text-gray-700"
                >
                  🔹 Diamond
                </button>
                <button
                  onClick={() => handleInsertBullet('✅')}
                  className="px-2 py-1 text-[11px] font-semibold bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md text-gray-700"
                >
                  ✅ Check
                </button>
              </div>

              {/* Emoji bar */}
              <div className="flex items-center gap-1">
                {EMOJI_PILLS.map((em, i) => (
                  <button
                    key={i}
                    onClick={() => handleInsertEmoji(em)}
                    className="w-6 h-6 flex items-center justify-center text-xs hover:bg-gray-100 rounded-md transition-colors"
                  >
                    {em}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Textarea Editor */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-700">Write & Edit Post</span>
              <button
                onClick={() => setText('')}
                className="text-[11px] text-gray-400 hover:text-red-600 flex items-center gap-1 transition-colors"
              >
                <FaTrash className="text-[9px]" /> Clear
              </button>
            </div>

            <textarea
              ref={textareaRef}
              rows={12}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type or paste your LinkedIn post here... Highlight any text and click a formatting button above!"
              className="w-full text-sm text-gray-900 border border-gray-200 rounded-xl p-3.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-sans leading-relaxed resize-y"
            />

            {/* Metrics & Hook Quality Meter */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs text-gray-500 border-t border-gray-100">
              <div className="flex items-center gap-4">
                <span>
                  <strong className="text-gray-900">{charCount}</strong> / 3,000 characters
                </span>
                <span>
                  <strong className="text-gray-900">{wordCount}</strong> words
                </span>
                <span>
                  <strong className="text-gray-900">{lines.length}</strong> lines
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-gray-500">Hook fold:</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    isHookShort
                      ? 'bg-green-100 text-green-700'
                      : 'bg-amber-100 text-amber-700'
                  }`}
                >
                  {isHookShort ? '✓ Optimal (under fold)' : '⚠ Truncates early'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right Column: LinkedIn Live Feed Preview (5 Cols) ── */}
        <div className="lg:col-span-5 space-y-4">

          {/* Preview Device Controls */}
          <div className="bg-white border border-gray-200 rounded-2xl p-3 shadow-xs flex items-center justify-between">
            <span className="text-xs font-bold text-gray-700">LinkedIn Feed Preview</span>
            <div className="flex items-center bg-gray-100 p-1 rounded-xl gap-1">
              <button
                onClick={() => setPreviewDevice('desktop')}
                className={`flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-lg transition-all ${
                  previewDevice === 'desktop'
                    ? 'bg-white text-gray-900 shadow-xs'
                    : 'text-gray-500 hover:text-gray-900'
                }`}
              >
                <FaDesktop className="text-[10px]" /> Desktop
              </button>
              <button
                onClick={() => setPreviewDevice('mobile')}
                className={`flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-lg transition-all ${
                  previewDevice === 'mobile'
                    ? 'bg-white text-gray-900 shadow-xs'
                    : 'text-gray-500 hover:text-gray-900'
                }`}
              >
                <FaMobileAlt className="text-[10px]" /> Mobile
              </button>
            </div>
          </div>

          {/* Realistic LinkedIn Post Feed Card */}
          <div
            className={`bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden transition-all ${
              previewDevice === 'mobile' ? 'max-w-[360px] mx-auto border-2 border-gray-300' : 'w-full'
            }`}
          >
            {/* Post Header */}
            <div className="p-4 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-500 text-white font-bold text-sm flex items-center justify-center flex-shrink-0 shadow-xs">
                  {authorInitial}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-xs font-bold text-gray-900 truncate">{authorName}</h4>
                    <span className="text-[10px] text-gray-400">• 1st</span>
                  </div>
                  <p className="text-[10px] text-gray-500 truncate leading-tight mt-0.5">{authorHeadline}</p>
                  <p className="text-[10px] text-gray-400 flex items-center gap-1 mt-0.5">
                    <span>1h</span> • <span>Edited</span> • <FaGlobeAmericas className="text-[9px]" />
                  </p>
                </div>
              </div>
              <button className="text-xs font-bold text-blue-600 hover:text-blue-700 hover:bg-blue-50 px-2.5 py-1 rounded-full transition-colors">
                + Follow
              </button>
            </div>

            {/* Post Content with "...see more" simulation */}
            <div className="px-4 pb-4 text-xs text-gray-900 leading-relaxed font-sans whitespace-pre-wrap select-text">
              {text ? (
                <>
                  {getDisplayContent()}
                  {lines.length > 3 && !isSeeMoreExpanded && (
                    <button
                      onClick={() => setIsSeeMoreExpanded(true)}
                      className="text-gray-500 hover:text-gray-800 font-semibold ml-1 cursor-pointer transition-colors"
                    >
                      ...see more
                    </button>
                  )}
                  {lines.length > 3 && isSeeMoreExpanded && (
                    <button
                      onClick={() => setIsSeeMoreExpanded(false)}
                      className="block text-[10px] text-blue-600 font-semibold mt-2 cursor-pointer"
                    >
                      (Collapse preview)
                    </button>
                  )}
                </>
              ) : (
                <span className="text-gray-400 italic">Your formatted post preview will render here in real-time...</span>
              )}
            </div>

            {/* Social Engagement Stats */}
            <div className="px-4 py-2 border-t border-gray-100 flex items-center justify-between text-[11px] text-gray-500">
              <div className="flex items-center gap-1">
                <span className="flex -space-x-1">
                  <span className="w-4 h-4 rounded-full bg-blue-500 flex items-center justify-center text-[8px] text-white">👍</span>
                  <span className="w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-[8px] text-white">❤️</span>
                  <span className="w-4 h-4 rounded-full bg-amber-500 flex items-center justify-center text-[8px] text-white">💡</span>
                </span>
                <span className="ml-1 text-[10px] text-gray-500">142</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-gray-400">
                <span>38 comments</span> • <span>12 reposts</span>
              </div>
            </div>

            {/* Social Action Bar */}
            <div className="px-2 py-1.5 border-t border-gray-100 flex items-center justify-around text-gray-600">
              <button className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-100 rounded-lg text-xs font-semibold transition-colors">
                <FaThumbsUp className="text-[11px] text-gray-500" /> Like
              </button>
              <button className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-100 rounded-lg text-xs font-semibold transition-colors">
                <FaCommentDots className="text-[11px] text-gray-500" /> Comment
              </button>
              <button className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-100 rounded-lg text-xs font-semibold transition-colors">
                <FaShare className="text-[11px] text-gray-500" /> Repost
              </button>
              <button className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-100 rounded-lg text-xs font-semibold transition-colors">
                <FaBookmark className="text-[11px] text-gray-500" /> Send
              </button>
            </div>
          </div>

          {/* LinkedIn Best Practices Card */}
          <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 text-xs space-y-2">
            <h4 className="font-bold text-blue-900 flex items-center gap-1.5">
              <FaLightbulb className="text-amber-500 text-xs" /> LinkedIn Algorithm Pro Tips
            </h4>
            <ul className="text-blue-800 space-y-1.5 text-[11px] leading-relaxed">
              <li>• <strong>Hook in line 1-2:</strong> Keep the first 140 chars punchy to trigger "...see more" clicks.</li>
              <li>• <strong>Generous Line Breaks:</strong> Avoid blocks of text. 1-2 sentences per paragraph maximize dwell time.</li>
              <li>• <strong>Bold for Headings only:</strong> Highlight key concepts or bullet points; over-bolding looks spammy.</li>
              <li>• <strong>End with a Conversation Starter:</strong> Ask an open question to prompt comments in the first 60 minutes.</li>
            </ul>
          </div>

        </div>

      </div>
    </div>
  );
}
