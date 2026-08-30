import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { jsPDF } from 'jspdf';
import {
  FaDownload,
  FaCopy,
  FaPlus,
  FaTrash,
  FaMagic,
  FaFilePdf,
  FaLayerGroup,
  FaChevronLeft,
  FaChevronRight,
} from 'react-icons/fa';
import { toast } from 'sonner';

const ASPECT_RATIOS = [
  { id: '1:1', label: 'Square', sub: 'Instagram / LinkedIn', width: 1080, height: 1080, icon: '■' },
  { id: '4:5', label: 'Portrait', sub: 'LinkedIn PDF / IG Feed', width: 1080, height: 1350, icon: '▮' },
  { id: '16:9', label: 'Landscape', sub: 'X (Twitter) / YouTube', width: 1200, height: 675, icon: '▬' },
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
  '📌 FRAMEWORK',
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

const DEFAULT_CAROUSEL_SLIDES = [
  {
    id: 'slide-1',
    badge: '📌 5-STEP PLAYBOOK',
    headline: 'The Exact Framework to 10x Your LinkedIn Reach',
    subtitle: 'Swipe through for the 5-step actionable breakdown 👉',
    gradientId: 'hyper-indigo',
  },
  {
    id: 'slide-2',
    badge: 'STEP 1',
    headline: 'Hook Them in the First 2 Lines',
    subtitle: 'People browse in a fast feed. Create curiosity or state a counter-intuitive truth.',
    gradientId: 'hyper-indigo',
  },
  {
    id: 'slide-3',
    badge: 'STEP 2',
    headline: 'Keep External Links in the First Comment',
    subtitle: 'LinkedIn penalizes posts with outbound links. Drop URLs in the first comment automatically.',
    gradientId: 'hyper-indigo',
  },
  {
    id: 'slide-4',
    badge: 'STEP 3',
    headline: 'Use Multi-Page PDF Document Slides',
    subtitle: 'Carousels generate 3x higher dwell time than single image posts.',
    gradientId: 'hyper-indigo',
  },
  {
    id: 'slide-5',
    badge: '🎯 TAKEAWAY',
    headline: 'Found this helpful? Save & Share with your network!',
    subtitle: 'Follow for weekly actionable social growth playbooks.',
    gradientId: 'hyper-indigo',
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

  // Studio Mode: 'single' (Image) | 'carousel' (Multi-page PDF)
  const [studioMode, setStudioMode] = useState('single');
  const [slides, setSlides] = useState(DEFAULT_CAROUSEL_SLIDES);
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);

  const [aspectRatio, setAspectRatio] = useState(ASPECT_RATIOS[1]); // Default 4:5 for LinkedIn Carousels
  const [selectedGradient, setSelectedGradient] = useState(GRADIENTS[0]);
  const [patternOverlay, setPatternOverlay] = useState('dots');

  // Single mode content
  const [badge, setBadge] = useState('💡 QUICK TIP');
  const [headline, setHeadline] = useState(initialHeadline || 'Design high-converting social graphics in seconds.');
  const [subtitle, setSubtitle] = useState('Zero Canva tab switching. Direct 1-click export to your scheduler.');
  const [authorName, setAuthorName] = useState('Acme Team');
  const [authorHandle, setAuthorHandle] = useState('@acmegrowth');
  const [fontFamily, setFontFamily] = useState('system-ui');
  const [headlineSize, setHeadlineSize] = useState(54);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  // Sync active slide fields when in carousel mode
  const currentBadge = studioMode === 'carousel' ? (slides[activeSlideIdx]?.badge || '') : badge;
  const currentHeadline = studioMode === 'carousel' ? (slides[activeSlideIdx]?.headline || '') : headline;
  const currentSubtitle = studioMode === 'carousel' ? (slides[activeSlideIdx]?.subtitle || '') : subtitle;

  const updateActiveSlide = (key, value) => {
    if (studioMode !== 'carousel') return;
    setSlides(prev => {
      const next = [...prev];
      if (next[activeSlideIdx]) {
        next[activeSlideIdx] = { ...next[activeSlideIdx], [key]: value };
      }
      return next;
    });
  };

  const drawSlideToCanvas = useCallback((ctx, width, height, sBadge, sHeadline, sSubtitle, sGradient, slideNum = null, totalSlides = null) => {
    ctx.clearRect(0, 0, width, height);

    // 1. Background Gradient
    const gradObj = sGradient || selectedGradient;
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradObj.colors.forEach((col, idx) => {
      gradient.addColorStop(idx / (gradObj.colors.length - 1), col);
    });
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    // 2. Pattern Overlay
    if (patternOverlay === 'dots') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
      const spacing = 36;
      for (let x = 0; x < width; x += spacing) {
        for (let y = 0; y < height; y += spacing) {
          ctx.beginPath();
          ctx.arc(x, y, 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    } else if (patternOverlay === 'grid') {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
      ctx.lineWidth = 1.5;
      const step = 60;
      for (let x = 0; x < width; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
    }

    // 3. Inner Frosted Glass Card
    const cardMargin = width * 0.06;
    const cardRadius = 36;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.22)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(cardMargin, cardMargin, width - cardMargin * 2, height - cardMargin * 2, cardRadius);
    ctx.fill();
    ctx.stroke();

    const textX = cardMargin * 2;
    let cursorY = cardMargin * 2 + 30;

    // 4. Badge Tag
    if (sBadge && sBadge.trim()) {
      ctx.font = `bold 22px ${fontFamily}`;
      const badgeText = sBadge.toUpperCase();
      const badgeWidth = ctx.measureText(badgeText).width + 36;
      const badgeHeight = 44;

      ctx.fillStyle = 'rgba(0, 0, 0, 0.28)';
      ctx.beginPath();
      ctx.roundRect(textX, cursorY, badgeWidth, badgeHeight, 22);
      ctx.fill();

      ctx.fillStyle = gradObj.text;
      ctx.fillText(badgeText, textX + 18, cursorY + 29);
      cursorY += badgeHeight + 40;
    } else {
      cursorY += 20;
    }

    // Slide indicator if carousel
    if (slideNum && totalSlides) {
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
      const slideTag = `${slideNum} / ${totalSlides}`;
      const tagW = ctx.measureText(slideTag).width;
      ctx.fillText(slideTag, width - cardMargin * 2 - tagW, cardMargin * 2 + 30);
    }

    // 5. Headline
    ctx.fillStyle = gradObj.text;
    ctx.font = `bold ${headlineSize}px ${fontFamily}`;
    const maxTextWidth = width - cardMargin * 4;
    const words = sHeadline.split(' ');
    let currentLine = '';
    const lines = [];

    for (const w of words) {
      const testLine = currentLine ? `${currentLine} ${w}` : w;
      if (ctx.measureText(testLine).width > maxTextWidth) {
        lines.push(currentLine);
        currentLine = w;
      } else {
        currentLine = testLine;
      }
    }
    if (currentLine) lines.push(currentLine);

    const lineHeight = headlineSize * 1.25;
    lines.forEach((line) => {
      ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
      cursorY += lineHeight;
    });

    cursorY += 24;

    // 6. Subtitle
    if (sSubtitle && sSubtitle.trim()) {
      ctx.fillStyle = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(15, 23, 42, 0.85)';
      ctx.font = `normal 30px ${fontFamily}`;
      const subWords = sSubtitle.split(' ');
      let subLine = '';
      const subLines = [];

      for (const w of subWords) {
        const testSub = subLine ? `${subLine} ${w}` : w;
        if (ctx.measureText(testSub).width > maxTextWidth) {
          subLines.push(subLine);
          subLine = w;
        } else {
          subLine = testSub;
        }
      }
      if (subLine) subLines.push(subLine);

      subLines.forEach((line) => {
        ctx.fillText(line, textX, cursorY + 24);
        cursorY += 42;
      });
    }

    // 7. Author Branding (Bottom)
    const bottomY = height - cardMargin * 2 - 20;
    const avatarRadius = 24;
    const avatarX = textX + avatarRadius;

    ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
    ctx.beginPath();
    ctx.arc(avatarX, bottomY, avatarRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = gradObj.text;
    ctx.font = `bold 22px ${fontFamily}`;
    ctx.textAlign = 'center';
    ctx.fillText(authorName.charAt(0).toUpperCase() || 'U', avatarX, bottomY + 8);
    ctx.textAlign = 'left';

    ctx.font = `bold 24px ${fontFamily}`;
    ctx.fillText(authorName, avatarX + avatarRadius + 16, bottomY - 2);

    ctx.font = `normal 20px ${fontFamily}`;
    ctx.fillStyle = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(15, 23, 42, 0.7)';
    ctx.fillText(authorHandle, avatarX + avatarRadius + 16, bottomY + 22);
  }, [selectedGradient, patternOverlay, fontFamily, headlineSize, authorName, authorHandle]);

  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = aspectRatio.width;
    const height = aspectRatio.height;
    canvas.width = width;
    canvas.height = height;

    const slideNum = studioMode === 'carousel' ? activeSlideIdx + 1 : null;
    const totalSlides = studioMode === 'carousel' ? slides.length : null;

    drawSlideToCanvas(ctx, width, height, currentBadge, currentHeadline, currentSubtitle, selectedGradient, slideNum, totalSlides);
  }, [aspectRatio, selectedGradient, currentBadge, currentHeadline, currentSubtitle, studioMode, activeSlideIdx, slides, drawSlideToCanvas]);

  useEffect(() => {
    renderCanvas();
  }, [renderCanvas]);

  const handleDownloadImage = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `social-graphic-${aspectRatio.id.replace(':', '-')}.png`;
    link.href = dataUrl;
    link.click();
    toast.success('High-res PNG graphic exported!');
  };

  const handleDownloadPdf = async () => {
    setIsExportingPdf(true);
    try {
      const width = aspectRatio.width;
      const height = aspectRatio.height;
      const pdf = new jsPDF({
        orientation: width > height ? 'landscape' : 'portrait',
        unit: 'px',
        format: [width, height],
      });

      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = width;
      tempCanvas.height = height;
      const tempCtx = tempCanvas.getContext('2d');

      slides.forEach((s, idx) => {
        if (idx > 0) pdf.addPage([width, height]);
        drawSlideToCanvas(tempCtx, width, height, s.badge, s.headline, s.subtitle, selectedGradient, idx + 1, slides.length);
        const imgData = tempCanvas.toDataURL('image/jpeg', 0.95);
        pdf.addImage(imgData, 'JPEG', 0, 0, width, height);
      });

      pdf.save('linkedin-carousel-slides.pdf');
      toast.success('🎉 LinkedIn Multi-Page PDF Carousel exported successfully!');
    } catch (err) {
      toast.error('Failed to export PDF: ' + err.message);
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleCopyClipboard = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      canvas.toBlob(async (blob) => {
        if (!blob) return;
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': blob })
        ]);
        toast.success('Graphic copied to clipboard!');
      });
    } catch {
      toast.error('Failed to copy to clipboard.');
    }
  };

  const handleAttachPost = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    if (onAttachToPost) {
      onAttachToPost({
        url: dataUrl,
        type: 'image',
        name: 'graphic-studio-export.png',
      });
      toast.success('Graphic attached to post composer!');
    } else {
      sessionStorage.setItem('attached_studio_graphic', dataUrl);
      navigate('/create-post');
      toast.success('Redirecting to post composer with your graphic attached!');
    }
  };

  const addSlide = () => {
    if (slides.length >= 10) {
      toast.error('Maximum 10 slides per carousel');
      return;
    }
    const newSlide = {
      id: `slide-${Date.now()}`,
      badge: `STEP ${slides.length}`,
      headline: 'New Insight Point',
      subtitle: 'Add clear actionable takeaways for your audience.',
      gradientId: selectedGradient.id,
    };
    setSlides(prev => [...prev, newSlide]);
    setActiveSlideIdx(slides.length);
  };

  const removeSlide = (idx) => {
    if (slides.length <= 2) {
      toast.error('Carousels require at least 2 slides');
      return;
    }
    setSlides(prev => prev.filter((_, i) => i !== idx));
    if (activeSlideIdx >= slides.length - 1) {
      setActiveSlideIdx(Math.max(0, slides.length - 2));
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">

      {/* ── Left Preview Canvas Column ── */}
      <div className="xl:col-span-7 flex flex-col items-center">

        {/* Studio Mode Switcher */}
        <div className="w-full mb-4 flex items-center justify-between bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-2xl p-2 shadow-2xs">
          <div className="flex items-center gap-1.5 p-1 bg-gray-100 dark:bg-gray-800 rounded-xl">
            <button
              onClick={() => setStudioMode('single')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                studioMode === 'single'
                  ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-2xs'
                  : 'text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              Single Graphic
            </button>
            <button
              onClick={() => setStudioMode('carousel')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                studioMode === 'carousel'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              <FaLayerGroup className="text-[10px]" />
              LinkedIn PDF Carousel ({slides.length} Slides)
            </button>
          </div>

          <span className="text-[11px] font-semibold text-gray-400 hidden sm:inline-block pr-2">
            Vector High-Res
          </span>
        </div>

        {/* Canvas Display */}
        <div className="w-full bg-gray-100/80 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-3xl p-6 flex flex-col items-center justify-center shadow-inner relative overflow-hidden">
          <div className="max-w-full max-h-[540px] flex items-center justify-center">
            <canvas
              ref={canvasRef}
              className="max-w-full max-h-[500px] object-contain rounded-2xl shadow-2xl transition-all duration-300"
            />
          </div>

          {/* Carousel Slide Navigation if in carousel mode */}
          {studioMode === 'carousel' && (
            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={() => setActiveSlideIdx(Math.max(0, activeSlideIdx - 1))}
                disabled={activeSlideIdx === 0}
                className="p-2 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 disabled:opacity-30 shadow-xs"
              >
                <FaChevronLeft className="text-xs" />
              </button>
              <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                Slide {activeSlideIdx + 1} of {slides.length}
              </span>
              <button
                onClick={() => setActiveSlideIdx(Math.min(slides.length - 1, activeSlideIdx + 1))}
                disabled={activeSlideIdx === slides.length - 1}
                className="p-2 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 disabled:opacity-30 shadow-xs"
              >
                <FaChevronRight className="text-xs" />
              </button>
            </div>
          )}
        </div>

        {/* Carousel Slide Thumbnails */}
        {studioMode === 'carousel' && (
          <div className="w-full mt-4 flex items-center gap-2 overflow-x-auto pb-2">
            {slides.map((s, idx) => (
              <div
                key={s.id}
                onClick={() => setActiveSlideIdx(idx)}
                className={`relative shrink-0 w-28 p-2.5 rounded-xl border cursor-pointer transition-all ${
                  activeSlideIdx === idx
                    ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 ring-2 ring-indigo-500/20'
                    : 'border-gray-200 bg-white dark:bg-gray-900 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-bold text-gray-500">#{idx + 1}</span>
                  {slides.length > 2 && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeSlide(idx);
                      }}
                      className="text-gray-400 hover:text-red-500 p-0.5"
                    >
                      <FaTrash className="text-[9px]" />
                    </button>
                  )}
                </div>
                <p className="text-[10px] font-bold text-gray-900 dark:text-white truncate">
                  {s.badge || `Slide ${idx + 1}`}
                </p>
                <p className="text-[9px] text-gray-400 truncate mt-0.5">
                  {s.headline || 'No text'}
                </p>
              </div>
            ))}

            {slides.length < 10 && (
              <button
                onClick={addSlide}
                className="shrink-0 flex items-center justify-center gap-1 w-24 h-16 rounded-xl border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-indigo-500 text-gray-500 text-xs font-bold transition-colors"
              >
                <FaPlus className="text-[10px]" /> Add
              </button>
            )}
          </div>
        )}

        {/* Export & Actions Toolbar */}
        <div className="w-full mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {studioMode === 'carousel' ? (
              <button
                onClick={handleDownloadPdf}
                disabled={isExportingPdf}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 active:scale-95 transition-all"
              >
                <FaFilePdf className="text-xs" />
                {isExportingPdf ? 'Exporting PDF...' : 'Download LinkedIn Carousel (PDF)'}
              </button>
            ) : (
              <button
                onClick={handleDownloadImage}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-900 hover:bg-black text-white font-bold text-xs shadow-sm active:scale-95 transition-all"
              >
                <FaDownload className="text-xs" />
                Download PNG
              </button>
            )}

            <button
              onClick={handleCopyClipboard}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 font-bold text-xs text-gray-700 dark:text-gray-200 active:scale-95 transition-all"
            >
              <FaCopy className="text-xs" />
              Copy Slide
            </button>
          </div>

          <button
            onClick={handleAttachPost}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold text-xs shadow-md shadow-indigo-500/20 active:scale-95 transition-all"
          >
            <FaMagic className="text-xs" />
            Attach to Post Composer
          </button>
        </div>

      </div>

      {/* ── Right Controls Panel Column ── */}
      <div className="xl:col-span-5 space-y-6">

        {/* 1. Quick Templates */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-2xs">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3 flex items-center gap-1.5">
            <FaMagic className="text-amber-500" /> 1-Click Templates
          </p>
          <div className="grid grid-cols-2 gap-2">
            {TEMPLATES.map((tmpl) => (
              <button
                key={tmpl.name}
                onClick={() => {
                  if (studioMode === 'carousel') {
                    updateActiveSlide('badge', tmpl.badge);
                    updateActiveSlide('headline', tmpl.headline);
                    updateActiveSlide('subtitle', tmpl.subtitle);
                  } else {
                    setBadge(tmpl.badge);
                    setHeadline(tmpl.headline);
                    setSubtitle(tmpl.subtitle);
                  }
                  const foundGrad = GRADIENTS.find(g => g.id === tmpl.gradientId);
                  if (foundGrad) setSelectedGradient(foundGrad);
                  setFontFamily(tmpl.font);
                }}
                className="text-left p-3 rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-800/40 hover:bg-indigo-50/50 hover:border-indigo-200 transition-all text-xs font-semibold text-gray-800 dark:text-gray-200"
              >
                {tmpl.name}
              </button>
            ))}
          </div>
        </div>

        {/* 2. Text & Content Editor */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-2xs space-y-4">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
            {studioMode === 'carousel' ? `Slide #${activeSlideIdx + 1} Content` : 'Text & Content'}
          </p>

          <div>
            <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">Badge / Tag</label>
            <input
              type="text"
              value={currentBadge}
              onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('badge', e.target.value) : setBadge(e.target.value)}
              placeholder="e.g. 💡 QUICK TIP"
              className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none"
            />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {BADGE_PRESETS.slice(0, 5).map((p) => (
                <button
                  key={p}
                  onClick={() => studioMode === 'carousel' ? updateActiveSlide('badge', p) : setBadge(p)}
                  className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-800 hover:bg-indigo-50 text-gray-600 dark:text-gray-300"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">Main Headline</label>
            <textarea
              rows={3}
              value={currentHeadline}
              onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('headline', e.target.value) : setHeadline(e.target.value)}
              className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none resize-none font-medium"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">Subtitle / Key Takeaway</label>
            <textarea
              rows={2}
              value={currentSubtitle}
              onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('subtitle', e.target.value) : setSubtitle(e.target.value)}
              className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-[11px] font-bold text-gray-500 mb-1">Author Name</label>
              <input
                type="text"
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 mb-1">Handle</label>
              <input
                type="text"
                value={authorHandle}
                onChange={(e) => setAuthorHandle(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              />
            </div>
          </div>
        </div>

        {/* 3. Style & Gradients */}
        <div className="bg-white dark:bg-gray-900 border border-gray-200/80 dark:border-gray-800 rounded-3xl p-5 shadow-2xs space-y-4">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            Style & Gradients
          </p>

          <div className="grid grid-cols-4 gap-2">
            {GRADIENTS.map((g) => (
              <button
                key={g.id}
                onClick={() => setSelectedGradient(g)}
                className={`h-12 rounded-xl flex items-center justify-center transition-all ${
                  selectedGradient.id === g.id ? 'ring-2 ring-indigo-500 ring-offset-2 scale-105 shadow-md' : 'opacity-80 hover:opacity-100'
                }`}
                style={{
                  background: `linear-gradient(135deg, ${g.colors[0]}, ${g.colors[1]})`,
                }}
                title={g.name}
              />
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-[11px] font-bold text-gray-500 mb-1">Typography</label>
              <select
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                {FONTS.map((f) => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-500 mb-1">Texture Overlay</label>
              <select
                value={patternOverlay}
                onChange={(e) => setPatternOverlay(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                <option value="none">Clean Solid</option>
                <option value="dots">Subtle Dots</option>
                <option value="grid">Modern Grid</option>
              </select>
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
