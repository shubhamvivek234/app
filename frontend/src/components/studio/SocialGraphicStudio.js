import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FaDownload,
  FaCopy,
  FaShare,
  FaUndo,
  FaRedo,
  FaPlus,
  FaPalette,
  FaFont,
  FaShapes,
  FaCheck,
  FaMagic,
} from 'react-icons/fa';
import { toast } from 'sonner';

const ASPECT_RATIOS = [
  { id: '1:1', label: 'Square', sub: 'Instagram / LinkedIn', width: 1080, height: 1080, icon: '■' },
  { id: '16:9', label: 'Landscape', sub: 'X (Twitter) / YouTube', width: 1200, height: 675, icon: '▬' },
  { id: '4:5', label: 'Portrait', sub: 'IG Feed / Carousel', width: 1080, height: 1350, icon: '▮' },
  { id: '9:16', label: 'Story / Reel', sub: 'TikTok / Shorts / IG Story', width: 1080, height: 1920, icon: '📱' },
];

const GRADIENTS = [
  { id: 'hyper-indigo', name: 'Hyper Indigo', colors: ['#4f46e5', '#7c3aed', '#9333ea'], text: '#ffffff' },
  { id: 'sunset-blvd', name: 'Sunset Blvd', colors: ['#f43f5e', '#fb7185', '#f59e0b'], text: '#ffffff' },
  { id: 'dark-titanium', name: 'Dark Titanium', colors: ['#0f172a', '#1e293b', '#334155'], text: '#ffffff' },
  { id: 'emerald-lush', name: 'Emerald Lush', colors: ['#065f46', '#059669', '#10b981'], text: '#ffffff' },
  { id: 'cyber-neon', name: 'Cyber Neon', colors: ['#000000', '#18022e', '#4c0519'], text: '#38bdf8' },
  { id: 'rose-gold', name: 'Rose Gold', colors: ['#4c1d95', '#831843', '#be123c'], text: '#ffffff' },
  { id: 'oceanic', name: 'Oceanic Blue', colors: ['#0c4a6e', '#0284c7', '#38bdf8'], text: '#ffffff' },
  { id: 'deep-space', name: 'Deep Space', colors: ['#020617', '#0f172a', '#1e1b4b'], text: '#ffffff' },
  { id: 'sunset-gold', name: 'Golden Hour', colors: ['#78350f', '#d97706', '#fbbf24'], text: '#ffffff' },
  { id: 'midnight-violet', name: 'Midnight Violet', colors: ['#2e1065', '#581c87', '#7e22ce'], text: '#ffffff' },
  { id: 'clean-cloud', name: 'Clean Editorial', colors: ['#f8fafc', '#f1f5f9', '#e2e8f0'], text: '#0f172a' },
  { id: 'charcoal-mono', name: 'Charcoal Minimal', colors: ['#18181b', '#27272a', '#3f3f46'], text: '#ffffff' },
];

const BADGE_PRESETS = [
  '🚀 NEW FEATURE',
  '💡 QUICK TIP',
  '🧵 THREAD 1/5',
  '🔥 TRENDING',
  '⭐ 5-STAR REVIEW',
  '🎙️ NEW EPISODE',
  '✨ PRO INSIGHT',
  '📈 CASE STUDY',
];

const TEMPLATES = [
  {
    name: 'Bold Announcement',
    badge: '🚀 NEW FEATURE',
    headline: 'Introducing the all-new Unravler v3.0 Studio',
    subtitle: 'Streamline your social distribution in half the time.',
    gradientId: 'hyper-indigo',
    font: 'system-ui',
  },
  {
    name: 'Actionable Tip',
    badge: '💡 QUICK TIP',
    headline: 'How to double your LinkedIn reach without posting links in the caption.',
    subtitle: 'Keep external URLs in the first comment to avoid algorithm throttling.',
    gradientId: 'dark-titanium',
    font: 'system-ui',
  },
  {
    name: 'High-Impact Quote',
    badge: '✨ PRO INSIGHT',
    headline: '"Consistency is not about posting every day. It is about never disappearing."',
    subtitle: 'Build a repeatable publishing engine that works for you.',
    gradientId: 'sunset-blvd',
    font: 'Georgia',
  },
  {
    name: 'Metrics / Result',
    badge: '📈 CASE STUDY',
    headline: '+340% Organic Impressions in 30 Days',
    subtitle: 'Here is the exact weekly cadence and timing playbook we used.',
    gradientId: 'emerald-lush',
    font: 'system-ui',
  },
];

const FONTS = [
  { id: 'system-ui', label: 'Modern Sans' },
  { id: 'Georgia', label: 'Editorial Serif' },
  { id: 'Courier New', label: 'Monospace Code' },
  { id: 'Arial Black', label: 'Heavy Impact' },
];

export default function SocialGraphicStudio({ onAttachToPost, initialHeadline = '' }) {
  const navigate = useNavigate();
  const canvasRef = useRef(null);

  const [aspectRatio, setAspectRatio] = useState(ASPECT_RATIOS[0]);
  const [selectedGradient, setSelectedGradient] = useState(GRADIENTS[0]);
  const [patternOverlay, setPatternOverlay] = useState('dots'); // 'none' | 'dots' | 'grid'

  const [badge, setBadge] = useState('💡 QUICK TIP');
  const [headline, setHeadline] = useState(initialHeadline || 'Design high-converting social graphics in seconds.');
  const [subtitle, setSubtitle] = useState('Zero Canva tab switching. Direct 1-click export to your scheduler.');
  const [authorName, setAuthorName] = useState('Acme Team');
  const [authorHandle, setAuthorHandle] = useState('@acmegrowth');
  const [fontFamily, setFontFamily] = useState('system-ui');
  const [headlineSize, setHeadlineSize] = useState(54);
  const [copied, setCopied] = useState(false);

  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = aspectRatio.width;
    const height = aspectRatio.height;
    canvas.width = width;
    canvas.height = height;

    // 1. Draw Gradient Background
    const grad = ctx.createLinearGradient(0, 0, width, height);
    const colors = selectedGradient.colors;
    if (colors.length === 2) {
      grad.addColorStop(0, colors[0]);
      grad.addColorStop(1, colors[1]);
    } else if (colors.length === 3) {
      grad.addColorStop(0, colors[0]);
      grad.addColorStop(0.5, colors[1]);
      grad.addColorStop(1, colors[2]);
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    // 2. Pattern Overlay
    if (patternOverlay === 'dots') {
      ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.07)' : 'rgba(0, 0, 0, 0.05)';
      const dotSpacing = 36;
      for (let x = 20; x < width; x += dotSpacing) {
        for (let y = 20; y < height; y += dotSpacing) {
          ctx.beginPath();
          ctx.arc(x, y, 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    } else if (patternOverlay === 'grid') {
      ctx.strokeStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.04)';
      ctx.lineWidth = 1;
      const gridSpacing = 48;
      for (let x = 0; x < width; x += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
    }

    // 3. Inner Card Glass Effect
    const paddingX = Math.round(width * 0.08);
    const paddingY = Math.round(height * 0.08);
    const cardWidth = width - paddingX * 2;
    const cardHeight = height - paddingY * 2;
    const cardRadius = 32;

    ctx.save();
    ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.06)' : 'rgba(255, 255, 255, 0.6)';
    ctx.strokeStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.08)';
    ctx.lineWidth = 2;

    // Rounded card path
    ctx.beginPath();
    ctx.roundRect(paddingX, paddingY, cardWidth, cardHeight, cardRadius);
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    const textPaddingLeft = paddingX + 56;
    const maxTextWidth = cardWidth - 112;
    let currentY = paddingY + 68;

    // 4. Badge / Tag
    if (badge) {
      ctx.save();
      ctx.font = `bold 22px ${fontFamily}`;
      const badgeMetrics = ctx.measureText(badge);
      const badgeWidth = badgeMetrics.width + 36;
      const badgeHeight = 44;

      ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(15, 23, 42, 0.08)';
      ctx.beginPath();
      ctx.roundRect(textPaddingLeft, currentY, badgeWidth, badgeHeight, 22);
      ctx.fill();

      ctx.fillStyle = selectedGradient.text;
      ctx.fillText(badge, textPaddingLeft + 18, currentY + 30);
      ctx.restore();

      currentY += badgeHeight + 42;
    }

    // 5. Headline Text (Wrapped)
    ctx.save();
    ctx.fillStyle = selectedGradient.text;
    ctx.font = `bold ${headlineSize}px ${fontFamily}`;
    ctx.textBaseline = 'top';

    const words = headline.split(' ');
    let line = '';
    const lines = [];

    for (let n = 0; n < words.length; n++) {
      const testLine = line + words[n] + ' ';
      const metrics = ctx.measureText(testLine);
      if (metrics.width > maxTextWidth && n > 0) {
        lines.push(line.trim());
        line = words[n] + ' ';
      } else {
        line = testLine;
      }
    }
    lines.push(line.trim());

    const lineHeight = headlineSize * 1.25;
    for (let i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], textPaddingLeft, currentY);
      currentY += lineHeight;
    }
    ctx.restore();

    currentY += 24;

    // 6. Subtitle Text (Wrapped)
    if (subtitle) {
      ctx.save();
      ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.82)' : 'rgba(15, 23, 42, 0.75)';
      const subSize = Math.max(Math.round(headlineSize * 0.48), 24);
      ctx.font = `500 ${subSize}px ${fontFamily}`;
      ctx.textBaseline = 'top';

      const subWords = subtitle.split(' ');
      let subLine = '';
      const subLines = [];

      for (let n = 0; n < subWords.length; n++) {
        const testLine = subLine + subWords[n] + ' ';
        const metrics = ctx.measureText(testLine);
        if (metrics.width > maxTextWidth && n > 0) {
          subLines.push(subLine.trim());
          subLine = subWords[n] + ' ';
        } else {
          subLine = testLine;
        }
      }
      subLines.push(subLine.trim());

      const subLineHeight = subSize * 1.35;
      for (let i = 0; i < subLines.length; i++) {
        ctx.fillText(subLines[i], textPaddingLeft, currentY);
        currentY += subLineHeight;
      }
      ctx.restore();
    }

    // 7. Footer / Author & Brand
    const footerY = paddingY + cardHeight - 64;

    ctx.save();
    // Avatar Circle
    ctx.fillStyle = selectedGradient.text === '#ffffff' ? '#ffffff' : '#0f172a';
    ctx.beginPath();
    ctx.arc(textPaddingLeft + 24, footerY + 12, 24, 0, Math.PI * 2);
    ctx.fill();

    // Initials inside avatar
    ctx.fillStyle = selectedGradient.text === '#ffffff' ? '#4f46e5' : '#ffffff';
    ctx.font = `bold 18px ${fontFamily}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText((authorName || 'U').charAt(0).toUpperCase(), textPaddingLeft + 24, footerY + 12);

    // Author metadata
    ctx.textAlign = 'left';
    ctx.fillStyle = selectedGradient.text;
    ctx.font = `bold 22px ${fontFamily}`;
    ctx.fillText(authorName, textPaddingLeft + 60, footerY + 4);

    ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.65)' : 'rgba(15, 23, 42, 0.55)';
    ctx.font = `18px ${fontFamily}`;
    ctx.fillText(authorHandle, textPaddingLeft + 60, footerY + 28);

    // Watermark right
    ctx.textAlign = 'right';
    ctx.fillStyle = selectedGradient.text === '#ffffff' ? 'rgba(255, 255, 255, 0.45)' : 'rgba(15, 23, 42, 0.4)';
    ctx.font = `bold 16px ${fontFamily}`;
    ctx.fillText('⚡ unravler.com', paddingX + cardWidth - 48, footerY + 16);
    ctx.restore();

  }, [aspectRatio, selectedGradient, patternOverlay, badge, headline, subtitle, authorName, authorHandle, fontFamily, headlineSize]);

  useEffect(() => {
    renderCanvas();
  }, [renderCanvas]);

  const handleDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `social-graphic-${aspectRatio.id.replace(':', 'x')}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
    toast.success('High-res graphic downloaded!');
  };

  const handleCopyClipboard = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      canvas.toBlob(async (blob) => {
        if (!blob) return;
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob }),
        ]);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        toast.success('Image copied to clipboard!');
      });
    } catch (err) {
      toast.error('Failed to copy to clipboard (unsupported in some browsers)');
    }
  };

  const handleAttachPost = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    if (onAttachToPost) {
      onAttachToPost(dataUrl);
      toast.success('Graphic attached to post draft!');
    } else {
      navigate('/create-post', { state: { initialMediaDataUrl: dataUrl, initialContent: `${headline}\n\n${subtitle}` } });
    }
  };

  const applyTemplate = (tmpl) => {
    setBadge(tmpl.badge);
    setHeadline(tmpl.headline);
    setSubtitle(tmpl.subtitle);
    const grad = GRADIENTS.find((g) => g.id === tmpl.gradientId) || GRADIENTS[0];
    setSelectedGradient(grad);
    setFontFamily(tmpl.font);
    toast.success(`Applied template: ${tmpl.name}`);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-8 items-start">
      
      {/* ── Left Preview Canvas ── */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-6 shadow-sm flex flex-col items-center justify-center min-h-[580px]">
        
        {/* Canvas Display */}
        <div className="relative max-w-full flex items-center justify-center p-2 bg-gray-100/70 dark:bg-gray-950/60 rounded-2xl border border-gray-200/60 dark:border-gray-800 shadow-inner">
          <canvas
            ref={canvasRef}
            className="max-h-[540px] w-auto max-w-full rounded-xl shadow-2xl object-contain"
          />
        </div>

        {/* Action Controls Bar */}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gray-900 hover:bg-black text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 font-bold text-xs shadow-md active:scale-95 transition-all"
          >
            <FaDownload className="text-xs" />
            Download PNG (High-Res)
          </button>

          <button
            onClick={handleCopyClipboard}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 font-bold text-xs shadow-2xs active:scale-95 transition-all"
          >
            {copied ? <FaCheck className="text-emerald-500" /> : <FaCopy className="text-xs" />}
            {copied ? 'Copied!' : 'Copy to Clipboard'}
          </button>

          <button
            onClick={handleAttachPost}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold text-xs shadow-md shadow-indigo-500/20 active:scale-95 transition-all"
          >
            <FaMagic className="text-xs" />
            Attach to Post Composer
          </button>
        </div>

      </div>

      {/* ── Right Controls Panel ── */}
      <div className="space-y-6">

        {/* 1. Quick Templates */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-sm">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3 flex items-center gap-1.5">
            <FaMagic className="text-amber-500" /> 1-Click Templates
          </p>
          <div className="grid grid-cols-2 gap-2">
            {TEMPLATES.map((tmpl) => (
              <button
                key={tmpl.name}
                type="button"
                onClick={() => applyTemplate(tmpl)}
                className="text-left p-2.5 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-indigo-500 bg-gray-50/50 dark:bg-gray-800/50 hover:bg-indigo-50/40 dark:hover:bg-indigo-950/30 transition-all text-xs font-semibold"
              >
                {tmpl.name}
              </button>
            ))}
          </div>
        </div>

        {/* 2. Aspect Ratio Presets */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-sm">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">
            Canvas Format & Aspect Ratio
          </p>
          <div className="grid grid-cols-2 gap-2">
            {ASPECT_RATIOS.map((ratio) => {
              const isSelected = aspectRatio.id === ratio.id;
              return (
                <button
                  key={ratio.id}
                  type="button"
                  onClick={() => setAspectRatio(ratio)}
                  className={`p-3 rounded-2xl border text-left transition-all ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-bold shadow-2xs'
                      : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm">{ratio.icon}</span>
                    <span className="text-[10px] font-mono text-gray-400">{ratio.id}</span>
                  </div>
                  <p className="text-xs font-bold mt-1.5">{ratio.label}</p>
                  <p className="text-[10px] text-gray-500 truncate">{ratio.sub}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* 3. Gradient Color Palettes */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-sm">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">
            Color Palette & Gradients
          </p>
          <div className="grid grid-cols-4 gap-2">
            {GRADIENTS.map((grad) => {
              const isSelected = selectedGradient.id === grad.id;
              return (
                <button
                  key={grad.id}
                  type="button"
                  onClick={() => setSelectedGradient(grad)}
                  title={grad.name}
                  className={`h-12 rounded-xl border-2 transition-all overflow-hidden relative shadow-2xs ${
                    isSelected ? 'border-indigo-600 scale-105 ring-2 ring-indigo-500/20' : 'border-transparent hover:scale-102'
                  }`}
                  style={{
                    background: `linear-gradient(135deg, ${grad.colors.join(', ')})`,
                  }}
                >
                  {isSelected && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                      <FaCheck className="text-white text-xs drop-shadow" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Pattern Toggle */}
          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">Texture Overlay:</span>
            <div className="flex items-center gap-1.5">
              {['none', 'dots', 'grid'].map((pat) => (
                <button
                  key={pat}
                  type="button"
                  onClick={() => setPatternOverlay(pat)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold capitalize transition-all ${
                    patternOverlay === pat
                      ? 'bg-indigo-600 text-white shadow-xs'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {pat}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 4. Text & Content Layer */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-sm space-y-3.5">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            Typography & Content
          </p>

          {/* Badge */}
          <div>
            <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
              Badge / Category Tag
            </label>
            <input
              type="text"
              value={badge}
              onChange={(e) => setBadge(e.target.value)}
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500"
              placeholder="e.g. 🚀 NEW LAUNCH"
            />
            <div className="flex flex-wrap gap-1 mt-1.5">
              {BADGE_PRESETS.slice(0, 4).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setBadge(p)}
                  className="text-[9px] px-2 py-0.5 rounded-md bg-gray-100 dark:bg-gray-800 hover:bg-indigo-50 text-gray-600 dark:text-gray-400 hover:text-indigo-600"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Main Headline */}
          <div>
            <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
              Headline
            </label>
            <textarea
              rows={3}
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500 resize-none"
              placeholder="Main text on the card..."
            />
          </div>

          {/* Subtitle */}
          <div>
            <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
              Subtitle / Supporting Text
            </label>
            <textarea
              rows={2}
              value={subtitle}
              onChange={(e) => setSubtitle(e.target.value)}
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:border-indigo-500 resize-none"
              placeholder="Supporting description..."
            />
          </div>

          {/* Font & Size */}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <div>
              <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
                Font Family
              </label>
              <select
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full text-xs px-2.5 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none"
              >
                {FONTS.map((f) => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
                Headline Size: {headlineSize}px
              </label>
              <input
                type="range"
                min={32}
                max={72}
                value={headlineSize}
                onChange={(e) => setHeadlineSize(Number(e.target.value))}
                className="w-full mt-2 accent-indigo-600"
              />
            </div>
          </div>

          {/* Author Metadata */}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <div>
              <label className="block text-[10px] font-semibold text-gray-500 mb-0.5">Author Name</label>
              <input
                type="text"
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
              />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-gray-500 mb-0.5">Handle</label>
              <input
                type="text"
                value={authorHandle}
                onChange={(e) => setAuthorHandle(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
              />
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
