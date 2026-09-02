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
  FaTwitter,
  FaTerminal,
  FaChartLine,
  FaQuoteLeft,
  FaStar,
  FaTimes,
  FaFont,
  FaPalette,
} from 'react-icons/fa';
import { toast } from 'sonner';
import { trackEvent } from '@/lib/analytics';
import { repurposeContent } from '@/lib/api';

const ASPECT_RATIOS = [
  { id: '1:1', label: 'Square', sub: 'Instagram / LinkedIn', width: 1080, height: 1080, icon: '■' },
  { id: '4:5', label: 'Portrait', sub: 'LinkedIn PDF / IG Feed', width: 1080, height: 1350, icon: '▮' },
  { id: '16:9', label: 'Landscape', sub: 'X (Twitter) / YouTube', width: 1200, height: 675, icon: '▬' },
  { id: '9:16', label: 'Story / Reel', sub: 'TikTok / Shorts / IG Story', width: 1080, height: 1920, icon: '📱' },
];

const CARD_ARCHETYPES = [
  { id: 'glassmorphic', label: 'Frosted Glass', icon: FaLayerGroup, desc: 'Translucent frosted card with specular rim' },
  { id: 'tweet_card', label: 'X / Twitter Post', icon: FaTwitter, desc: 'Authentic post card with verified badge & metrics' },
  { id: 'editorial_paper', label: 'Editorial Paper', icon: FaQuoteLeft, desc: 'Warm minimalist stone card with serif font' },
  { id: 'metric_stat', label: 'Big Stat Callout', icon: FaChartLine, desc: 'Giant growth KPI with positive delta pill' },
  { id: 'code_snippet', label: 'Code Terminal', icon: FaTerminal, desc: 'macOS dark terminal with traffic lights' },
  { id: 'testimonial', label: '5-Star Review', icon: FaStar, desc: 'Client quote with gold 5-star rating' },
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
  { id: 'aurora-green', name: 'Aurora Green', colors: ['#064e3b', '#047857', '#34d399'], text: '#ffffff' },
  { id: 'sunset-peach', name: 'Sunset Peach', colors: ['#ea580c', '#f97316', '#fb923c'], text: '#ffffff' },
  { id: 'acid-lime', name: 'Acid Lime', colors: ['#14532d', '#15803d', '#84cc16'], text: '#ffffff' },
  { id: 'frosted-quartz', name: 'Frosted Quartz', colors: ['#312e81', '#4338ca', '#818cf8'], text: '#ffffff' },
];

const SOLID_COLORS = [
  { id: 'solid-jet-black', name: 'Jet Black', color: '#09090B', text: '#ffffff' },
  { id: 'solid-slate-dark', name: 'Slate 900', color: '#0F172A', text: '#ffffff' },
  { id: 'solid-pure-white', name: 'Pure White', color: '#FFFFFF', text: '#0F172A' },
  { id: 'solid-warm-stone', name: 'Warm Stone', color: '#F5F5F4', text: '#0F172A' },
  { id: 'solid-british-green', name: 'Racing Green', color: '#064E3B', text: '#ffffff' },
  { id: 'solid-royal-navy', name: 'Royal Navy', color: '#0A192F', text: '#ffffff' },
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
    archetype: 'glassmorphic',
    badge: '🚀 NEW FEATURE',
    headline: 'Introducing the all-new Unravler v3.0 Studio',
    subtitle: 'Streamline your social distribution in half the time.',
    gradientId: 'hyper-indigo',
    font: 'system-ui',
  },
  {
    name: 'Viral X/Twitter Post',
    archetype: 'tweet_card',
    badge: '🔥 HOT TAKE',
    headline: 'Most creators fail not because their content is bad, but because they post without a distribution system. Build the engine first.',
    subtitle: '10:42 AM · Sep 2, 2026',
    gradientId: 'deep-space',
    font: 'system-ui',
  },
  {
    name: 'Actionable Tip',
    archetype: 'glassmorphic',
    badge: '💡 QUICK TIP',
    headline: 'How to double your LinkedIn reach without posting links in the caption.',
    subtitle: 'Keep external URLs in the first comment to avoid algorithm throttling.',
    gradientId: 'dark-titanium',
    font: 'system-ui',
  },
  {
    name: 'High-Impact Quote',
    archetype: 'editorial_paper',
    badge: '✨ PRO INSIGHT',
    headline: '"Consistency is not about posting every day. It is about never disappearing."',
    subtitle: 'Build a repeatable publishing engine that works for you.',
    gradientId: 'sunset-blvd',
    font: 'Georgia',
  },
  {
    name: 'Metrics / Result',
    archetype: 'metric_stat',
    badge: '📈 CASE STUDY',
    headline: '+340% Organic Reach in 30 Days',
    subtitle: 'Here is the exact weekly cadence and timing playbook we used.',
    gradientId: 'emerald-lush',
    font: 'system-ui',
  },
  {
    name: 'Code Snippet',
    archetype: 'code_snippet',
    badge: '💻 DEV LOG',
    headline: 'Automating Social Content Delivery',
    subtitle: 'TypeScript SDK sample for headless publishing.',
    gradientId: 'midnight-violet',
    font: 'Courier New',
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

  // Card Archetype
  const [cardArchetype, setCardArchetype] = useState('glassmorphic'); // 'glassmorphic' | 'tweet_card' | 'editorial_paper' | 'metric_stat' | 'code_snippet' | 'testimonial'

  // Frame & Bezel
  const [showMacOsBar, setShowMacOsBar] = useState(false);
  const [cardShadow, setCardShadow] = useState('elevated'); // 'subtle' | 'elevated' | 'glow' | 'none'
  const [isVerified, setIsVerified] = useState(true);
  const [showStars, setShowStars] = useState(false);
  const [showWatermark, setShowWatermark] = useState(true);
  const [watermarkText, setWatermarkText] = useState('unravler.com');

  // Archetype specific state
  const [metricValue, setMetricValue] = useState('+340%');
  const [metricDelta, setMetricDelta] = useState('▲ +28% MoM');
  const [metricLabel, setMetricLabel] = useState('Organic Impressions');
  const [codeFilename, setCodeFilename] = useState('distribute.ts');
  const [codeSnippet, setCodeSnippet] = useState(
`// Automated distribution pipeline
const post = await unravler.publish({
  channels: ['linkedin', 'x', 'threads'],
  content: 'Scale social reach effortlessly',
  firstComment: 'https://unravler.com'
});`
  );

  const [aspectRatio, setAspectRatio] = useState(ASPECT_RATIOS[1]); // Default 4:5 for LinkedIn Carousels
  const [bgType, setBgType] = useState('gradient'); // 'gradient' | 'solid'
  const [selectedGradient, setSelectedGradient] = useState(GRADIENTS[0]);
  const [selectedSolid, setSelectedSolid] = useState(SOLID_COLORS[0]);
  const [patternOverlay, setPatternOverlay] = useState('dots');

  // Content
  const [badge, setBadge] = useState('💡 QUICK TIP');
  const [headline, setHeadline] = useState(initialHeadline || 'Design high-converting social graphics in seconds.');
  const [subtitle, setSubtitle] = useState('Zero Canva tab switching. Direct 1-click export to your scheduler.');
  const [authorName, setAuthorName] = useState('Alex Rivera');
  const [authorHandle, setAuthorHandle] = useState('@alexgrowth');
  const [fontFamily, setFontFamily] = useState('system-ui');
  const [headlineSize, setHeadlineSize] = useState(54);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [canvasZoom, setCanvasZoom] = useState(1);

  // AI Generator Modal
  const [aiModal, setAiModal] = useState({ open: false, topic: '', loading: false });

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

    // 1. Background Fill (Solid or Gradient)
    const isSolid = bgType === 'solid';
    const gradObj = isSolid
      ? { colors: [selectedSolid.color, selectedSolid.color], text: selectedSolid.text, name: selectedSolid.name }
      : (sGradient || selectedGradient);

    if (isSolid) {
      ctx.fillStyle = selectedSolid.color;
      ctx.fillRect(0, 0, width, height);
    } else {
      const gradient = ctx.createLinearGradient(0, 0, width * 0.9, height);
      gradObj.colors.forEach((col, idx) => {
        gradient.addColorStop(idx / (gradObj.colors.length - 1), col);
      });
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      // Subtle ambient top-center glow spotlight for dimensional depth
      const radialGlow = ctx.createRadialGradient(width * 0.5, height * 0.25, 50, width * 0.5, height * 0.3, width * 0.7);
      radialGlow.addColorStop(0, 'rgba(255, 255, 255, 0.12)');
      radialGlow.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = radialGlow;
      ctx.fillRect(0, 0, width, height);
    }

    // 2. Texture Overlay
    if (patternOverlay === 'dots') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
      const spacing = 36;
      for (let x = 0; x < width; x += spacing) {
        for (let y = 0; y < height; y += spacing) {
          ctx.beginPath();
          ctx.arc(x, y, 2, 0, Math.PI * 2);
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
    } else if (patternOverlay === 'scanlines') {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += 12) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }
    }

    // 3. Inner Card Dimensions & Shadow
    const cardMargin = width * 0.07;
    const cardW = width - cardMargin * 2;
    const cardH = height - cardMargin * 2;
    const cardRadius = 32;

    ctx.save();
    if (cardShadow === 'elevated') {
      ctx.shadowColor = 'rgba(0, 0, 0, 0.38)';
      ctx.shadowBlur = 48;
      ctx.shadowOffsetY = 24;
    } else if (cardShadow === 'subtle') {
      ctx.shadowColor = 'rgba(0, 0, 0, 0.18)';
      ctx.shadowBlur = 20;
      ctx.shadowOffsetY = 10;
    } else if (cardShadow === 'glow') {
      ctx.shadowColor = gradObj.colors[0] || 'rgba(99, 102, 241, 0.5)';
      ctx.shadowBlur = 64;
      ctx.shadowOffsetY = 16;
    }

    // Card Background Color & Stroke based on Archetype
    let cardTextColor = '#ffffff';
    let cardSubtextColor = 'rgba(255, 255, 255, 0.75)';
    let cardAccentColor = '#38bdf8';

    if (cardArchetype === 'tweet_card') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.96)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#64748b';
      cardAccentColor = '#0284c7';
    } else if (cardArchetype === 'editorial_paper') {
      ctx.fillStyle = '#FAF8F5';
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.12)';
      cardTextColor = '#18181b';
      cardSubtextColor = '#52525b';
      cardAccentColor = '#b45309';
    } else if (cardArchetype === 'metric_stat') {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      cardTextColor = '#ffffff';
      cardSubtextColor = 'rgba(255, 255, 255, 0.8)';
      cardAccentColor = '#10b981';
    } else if (cardArchetype === 'code_snippet') {
      ctx.fillStyle = '#090D16';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
      cardTextColor = '#e2e8f0';
      cardSubtextColor = '#94a3b8';
      cardAccentColor = '#818cf8';
    } else if (cardArchetype === 'testimonial') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#475569';
      cardAccentColor = '#f59e0b';
    } else {
      // 'glassmorphic'
      ctx.fillStyle = 'rgba(255, 255, 255, 0.14)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.28)';
      cardTextColor = gradObj.text || '#ffffff';
      cardSubtextColor = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.8)' : 'rgba(15, 23, 42, 0.8)';
      cardAccentColor = '#fbbf24';
    }

    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(cardMargin, cardMargin, cardW, cardH, cardRadius);
    ctx.fill();
    ctx.stroke();
    ctx.restore(); // Clears canvas shadow so text doesn't blur

    const textX = cardMargin + width * 0.05;
    const maxTextWidth = cardW - width * 0.1;
    let cursorY = cardMargin + 40;

    // 4. macOS Window Bar (Traffic Lights)
    if (showMacOsBar || cardArchetype === 'code_snippet') {
      const dotRadius = 7;
      const dotY = cursorY + 8;
      // Red
      ctx.fillStyle = '#FF5F56';
      ctx.beginPath();
      ctx.arc(textX, dotY, dotRadius, 0, Math.PI * 2);
      ctx.fill();
      // Yellow
      ctx.fillStyle = '#FFBD2E';
      ctx.beginPath();
      ctx.arc(textX + 22, dotY, dotRadius, 0, Math.PI * 2);
      ctx.fill();
      // Green
      ctx.fillStyle = '#27C93F';
      ctx.beginPath();
      ctx.arc(textX + 44, dotY, dotRadius, 0, Math.PI * 2);
      ctx.fill();

      // Centered Window Title
      const winTitle = cardArchetype === 'code_snippet' ? codeFilename : (cardArchetype === 'tweet_card' ? 'x.com/post' : 'unravler-studio');
      ctx.font = `bold 16px ${fontFamily}`;
      ctx.fillStyle = cardSubtextColor;
      ctx.textAlign = 'center';
      ctx.fillText(winTitle, cardMargin + cardW / 2, dotY + 5);
      ctx.textAlign = 'left';

      cursorY += 40;

      // Divider line
      ctx.strokeStyle = cardArchetype === 'code_snippet' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cardMargin, cursorY);
      ctx.lineTo(cardMargin + cardW, cursorY);
      ctx.stroke();

      cursorY += 30;
    }

    // 5. Carousel Slide Pagination Indicator (Top-Right)
    if (slideNum && totalSlides) {
      const slideTag = `${slideNum} / ${totalSlides}`;
      ctx.font = `bold 18px ${fontFamily}`;
      const tagW = ctx.measureText(slideTag).width + 24;
      const tagH = 34;
      const tagX = cardMargin + cardW - tagW - 24;
      const tagY = cardMargin + 24;

      ctx.fillStyle = 'rgba(0, 0, 0, 0.22)';
      ctx.beginPath();
      ctx.roundRect(tagX, tagY, tagW, tagH, 17);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(slideTag, tagX + 12, tagY + 23);
    }

    // ── ARCHETYPE CONTENT RENDERING ──

    // Helper: Wrap text lines
    const wrapLines = (text, maxWidth, fontStr) => {
      ctx.font = fontStr;
      const words = (text || '').split(' ');
      let currentLine = '';
      const lines = [];
      for (const w of words) {
        const test = currentLine ? `${currentLine} ${w}` : w;
        if (ctx.measureText(test).width > maxWidth) {
          if (currentLine) lines.push(currentLine);
          currentLine = w;
        } else {
          currentLine = test;
        }
      }
      if (currentLine) lines.push(currentLine);
      return lines;
    };

    if (cardArchetype === 'tweet_card') {
      // Author header row (Avatar + Name + Handle + Verified Badge + X logo)
      const avatarR = 30;
      const avX = textX + avatarR;
      const avY = cursorY + avatarR;

      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.arc(avX, avY, avatarR, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = `bold 24px ${fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillText(authorName.charAt(0).toUpperCase() || 'U', avX, avY + 8);
      ctx.textAlign = 'left';

      // Name & Verified Badge
      const nameX = avX + avatarR + 16;
      ctx.fillStyle = '#0f172a';
      ctx.font = `bold 26px ${fontFamily}`;
      ctx.fillText(authorName, nameX, avY - 2);

      if (isVerified) {
        const nameW = ctx.measureText(authorName).width;
        // Verified blue badge
        ctx.fillStyle = '#1d9bf0';
        ctx.beginPath();
        ctx.arc(nameX + nameW + 16, avY - 8, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('✓', nameX + nameW + 16, avY - 4);
        ctx.textAlign = 'left';
      }

      // Handle
      ctx.fillStyle = '#64748b';
      ctx.font = `normal 20px ${fontFamily}`;
      ctx.fillText(authorHandle, nameX, avY + 22);

      // X Logo (Top right)
      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 28px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText('𝕏', cardMargin + cardW - 36, avY + 4);
      ctx.textAlign = 'left';

      cursorY += avatarR * 2 + 36;

      // Tweet Body Text
      ctx.fillStyle = '#0f172a';
      const tweetLines = wrapLines(sHeadline, maxTextWidth, `500 ${headlineSize}px ${fontFamily}`);
      const lineHeight = headlineSize * 1.3;
      tweetLines.forEach(line => {
        ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
        cursorY += lineHeight;
      });

      cursorY += 24;

      // Tweet Timestamp
      ctx.fillStyle = '#94a3b8';
      ctx.font = `normal 20px ${fontFamily}`;
      ctx.fillText(sSubtitle || '10:42 AM · Sep 2, 2026', textX, cursorY);

      cursorY += 30;

      // Divider line
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(textX, cursorY);
      ctx.lineTo(textX + maxTextWidth, cursorY);
      ctx.stroke();

      cursorY += 28;

      // Engagement Stats Row
      ctx.font = `bold 18px ${fontFamily}`;
      ctx.fillStyle = '#0f172a';
      ctx.fillText('48', textX, cursorY);
      ctx.fillStyle = '#64748b';
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillText('Replies', textX + 32, cursorY);

      ctx.font = `bold 18px ${fontFamily}`;
      ctx.fillStyle = '#0f172a';
      ctx.fillText('142', textX + 130, cursorY);
      ctx.fillStyle = '#64748b';
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillText('Reposts', textX + 172, cursorY);

      ctx.font = `bold 18px ${fontFamily}`;
      ctx.fillStyle = '#0f172a';
      ctx.fillText('1.8K', textX + 280, cursorY);
      ctx.fillStyle = '#64748b';
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillText('Likes', textX + 330, cursorY);

    } else if (cardArchetype === 'editorial_paper') {
      // Editorial luxury card
      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 18px Georgia`;
        ctx.fillStyle = '#b45309';
        ctx.fillText(sBadge.toUpperCase(), textX, cursorY + 20);
        cursorY += 45;
      }

      // Large Quotation Mark
      ctx.font = `italic 72px Georgia`;
      ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
      ctx.fillText('“', textX - 10, cursorY + 40);
      cursorY += 30;

      // Serif Headline
      ctx.fillStyle = '#18181b';
      const serifLines = wrapLines(sHeadline, maxTextWidth, `bold ${headlineSize}px Georgia`);
      const serifLineH = headlineSize * 1.35;
      serifLines.forEach(line => {
        ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
        cursorY += serifLineH;
      });

      cursorY += 20;

      // Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#52525b';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 26px Georgia`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 22);
          cursorY += 38;
        });
      }

      // Bottom Author attribution
      const bottomY = cardMargin + cardH - 36;
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(textX, bottomY - 30);
      ctx.lineTo(textX + maxTextWidth, bottomY - 30);
      ctx.stroke();

      ctx.font = `bold 22px Georgia`;
      ctx.fillStyle = '#18181b';
      ctx.fillText(authorName, textX, bottomY);
      ctx.font = `italic 18px Georgia`;
      ctx.fillStyle = '#71717a';
      ctx.fillText(authorHandle, textX + ctx.measureText(authorName).width + 16, bottomY);

    } else if (cardArchetype === 'metric_stat') {
      // Big Stat KPI Callout
      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 18px ${fontFamily}`;
        const bText = sBadge.toUpperCase();
        const bW = ctx.measureText(bText).width + 28;
        ctx.fillStyle = 'rgba(56, 189, 248, 0.18)';
        ctx.beginPath();
        ctx.roundRect(textX, cursorY, bW, 36, 18);
        ctx.fill();
        ctx.fillStyle = '#38bdf8';
        ctx.fillText(bText, textX + 14, cursorY + 24);
        cursorY += 60;
      }

      // Giant Stat Value
      ctx.font = `900 96px ${fontFamily}`;
      ctx.fillStyle = '#ffffff';
      ctx.fillText(metricValue, textX, cursorY + 80);

      // Trend Badge (e.g. ▲ +28% MoM)
      const statW = ctx.measureText(metricValue).width;
      if (metricDelta) {
        ctx.font = `bold 20px ${fontFamily}`;
        const deltaW = ctx.measureText(metricDelta).width + 24;
        const deltaX = textX + statW + 24;
        const deltaY = cursorY + 24;
        ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
        ctx.beginPath();
        ctx.roundRect(deltaX, deltaY, deltaW, 36, 18);
        ctx.fill();
        ctx.fillStyle = '#10b981';
        ctx.fillText(metricDelta, deltaX + 12, deltaY + 25);
      }

      cursorY += 120;

      // Metric Label
      ctx.font = `bold 28px ${fontFamily}`;
      ctx.fillStyle = '#38bdf8';
      ctx.fillText(metricLabel.toUpperCase(), textX, cursorY);
      cursorY += 36;

      // Headline context
      ctx.fillStyle = '#ffffff';
      const metricLines = wrapLines(sHeadline, maxTextWidth, `bold 36px ${fontFamily}`);
      metricLines.forEach(l => {
        ctx.fillText(l, textX, cursorY + 30);
        cursorY += 46;
      });

      cursorY += 16;
      // Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#94a3b8';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 24px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 20);
          cursorY += 36;
        });
      }

      // Bottom author
      const bottomY = cardMargin + cardH - 30;
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = '#ffffff';
      ctx.fillText(authorName, textX, bottomY);
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(authorHandle, textX + ctx.measureText(authorName).width + 12, bottomY);

    } else if (cardArchetype === 'code_snippet') {
      // Code Snippet Terminal
      const codeLines = codeSnippet.split('\n');
      ctx.font = `normal 24px "Courier New", monospace`;
      const codeLineH = 38;

      codeLines.forEach((line, idx) => {
        // Line number
        ctx.fillStyle = '#475569';
        ctx.textAlign = 'right';
        ctx.fillText(`${idx + 1}`, textX + 30, cursorY + 24);
        ctx.textAlign = 'left';

        // Syntax coloring
        const lineX = textX + 56;
        if (line.trim().startsWith('//')) {
          ctx.fillStyle = '#64748b';
        } else if (line.includes('const ') || line.includes('await ') || line.includes('import ') || line.includes('return ')) {
          ctx.fillStyle = '#c084fc';
        } else if (line.includes("'") || line.includes('"')) {
          ctx.fillStyle = '#38bdf8';
        } else {
          ctx.fillStyle = '#e2e8f0';
        }
        ctx.fillText(line, lineX, cursorY + 24);
        cursorY += codeLineH;
      });

      // Context note at bottom
      if (sSubtitle) {
        cursorY += 30;
        ctx.font = `italic 20px ${fontFamily}`;
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(`// ${sSubtitle}`, textX, cursorY);
      }

    } else if (cardArchetype === 'testimonial') {
      // 5-Star Testimonial
      if (showStars || true) {
        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 36px sans-serif';
        ctx.fillText('★★★★★', textX, cursorY + 30);
        cursorY += 56;
      }

      // Quote Headline
      ctx.fillStyle = '#0f172a';
      const quoteLines = wrapLines(sHeadline.startsWith('"') ? sHeadline : `"${sHeadline}"`, maxTextWidth, `bold ${headlineSize}px ${fontFamily}`);
      const qLineH = headlineSize * 1.3;
      quoteLines.forEach(line => {
        ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
        cursorY += qLineH;
      });

      cursorY += 24;

      if (sSubtitle) {
        ctx.fillStyle = '#64748b';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 26px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 22);
          cursorY += 38;
        });
      }

      // Customer avatar & name
      const bottomY = cardMargin + cardH - 40;
      const avR = 26;
      const avX = textX + avR;

      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.arc(avX, bottomY, avR, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = `bold 22px ${fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillText(authorName.charAt(0).toUpperCase() || 'U', avX, bottomY + 8);
      ctx.textAlign = 'left';

      ctx.font = `bold 24px ${fontFamily}`;
      ctx.fillStyle = '#0f172a';
      ctx.fillText(authorName, avX + avR + 16, bottomY - 2);

      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(authorHandle, avX + avR + 16, bottomY + 20);

    } else {
      // Default: 'glassmorphic'
      // 4. Badge Tag
      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 20px ${fontFamily}`;
        const badgeText = sBadge.toUpperCase();
        const badgeWidth = ctx.measureText(badgeText).width + 36;
        const badgeHeight = 44;

        ctx.fillStyle = 'rgba(0, 0, 0, 0.28)';
        ctx.beginPath();
        ctx.roundRect(textX, cursorY, badgeWidth, badgeHeight, 22);
        ctx.fill();

        ctx.fillStyle = gradObj.text || '#ffffff';
        ctx.fillText(badgeText, textX + 18, cursorY + 29);
        cursorY += badgeHeight + 36;
      } else {
        cursorY += 20;
      }

      // 5. Headline
      ctx.fillStyle = gradObj.text || '#ffffff';
      const lines = wrapLines(sHeadline, maxTextWidth, `bold ${headlineSize}px ${fontFamily}`);
      const lineHeight = headlineSize * 1.25;
      lines.forEach((line) => {
        ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
        cursorY += lineHeight;
      });

      cursorY += 24;

      // 6. Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(15, 23, 42, 0.85)';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 28px ${fontFamily}`);
        subLines.forEach((line) => {
          ctx.fillText(line, textX, cursorY + 24);
          cursorY += 40;
        });
      }

      // 7. Author Branding (Bottom)
      const bottomY = cardMargin + cardH - 36;
      const avatarRadius = 24;
      const avatarX = textX + avatarRadius;

      ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.beginPath();
      ctx.arc(avatarX, bottomY, avatarRadius, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = gradObj.text || '#ffffff';
      ctx.font = `bold 22px ${fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillText(authorName.charAt(0).toUpperCase() || 'U', avatarX, bottomY + 8);
      ctx.textAlign = 'left';

      ctx.font = `bold 24px ${fontFamily}`;
      ctx.fillText(authorName, avatarX + avatarRadius + 16, bottomY - 2);

      if (isVerified) {
        const nameW = ctx.measureText(authorName).width;
        ctx.fillStyle = '#38bdf8';
        ctx.beginPath();
        ctx.arc(avatarX + avatarRadius + 16 + nameW + 14, bottomY - 10, 8, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('✓', avatarX + avatarRadius + 16 + nameW + 14, bottomY - 6);
        ctx.textAlign = 'left';
      }

      ctx.font = `normal 20px ${fontFamily}`;
      ctx.fillStyle = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(15, 23, 42, 0.7)';
      ctx.fillText(authorHandle, avatarX + avatarRadius + 16, bottomY + 22);
    }

    // 8. Watermark (Bottom Right)
    if (showWatermark && watermarkText) {
      ctx.font = `bold 16px ${fontFamily}`;
      ctx.fillStyle = cardArchetype === 'editorial_paper' || cardArchetype === 'tweet_card' || cardArchetype === 'testimonial'
        ? 'rgba(0, 0, 0, 0.25)'
        : 'rgba(255, 255, 255, 0.4)';
      ctx.textAlign = 'right';
      ctx.fillText(watermarkText, cardMargin + cardW - 20, cardMargin + cardH - 20);
      ctx.textAlign = 'left';
    }
  }, [
    bgType,
    selectedGradient,
    selectedSolid,
    patternOverlay,
    cardArchetype,
    showMacOsBar,
    cardShadow,
    isVerified,
    showStars,
    showWatermark,
    watermarkText,
    metricValue,
    metricDelta,
    metricLabel,
    codeFilename,
    codeSnippet,
    fontFamily,
    headlineSize,
    authorName,
    authorHandle,
  ]);

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
  }, [
    aspectRatio,
    selectedGradient,
    currentBadge,
    currentHeadline,
    currentSubtitle,
    studioMode,
    activeSlideIdx,
    slides,
    drawSlideToCanvas,
  ]);

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
    trackEvent('graphic_image_downloaded', {
      aspect_ratio: aspectRatio.id,
      gradient: selectedGradient.name,
      archetype: cardArchetype,
    });
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
        const grad = s.gradientId ? (GRADIENTS.find(g => g.id === s.gradientId) || selectedGradient) : selectedGradient;
        drawSlideToCanvas(tempCtx, width, height, s.badge, s.headline, s.subtitle, grad, idx + 1, slides.length);
        const imgData = tempCanvas.toDataURL('image/jpeg', 0.95);
        pdf.addImage(imgData, 'JPEG', 0, 0, width, height);
      });

      pdf.save('linkedin-carousel-slides.pdf');
      toast.success('🎉 LinkedIn Multi-Page PDF Carousel exported successfully!');
      trackEvent('carousel_pdf_exported', {
        slide_count: slides.length,
        aspect_ratio: aspectRatio.id,
        gradient: selectedGradient.name,
      });
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

  const moveSlide = (idx, direction) => {
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= slides.length) return;
    setSlides(prev => {
      const next = [...prev];
      const temp = next[idx];
      next[idx] = next[targetIdx];
      next[targetIdx] = temp;
      return next;
    });
    setActiveSlideIdx(targetIdx);
  };

  // AI Magic Carousel Generator
  const handleRunAiGenerate = async () => {
    if (!aiModal.topic.trim()) {
      toast.error('Please enter a topic or concept');
      return;
    }
    setAiModal(prev => ({ ...prev, loading: true }));
    try {
      const res = await repurposeContent(aiModal.topic, { tone: 'engaging' });
      if (res && res.carousel_slides && res.carousel_slides.length > 0) {
        const generatedSlides = res.carousel_slides.slice(0, 7).map((s, idx) => ({
          id: `ai-slide-${Date.now()}-${idx}`,
          badge: s.slide_num === 1 ? '📌 OVERVIEW' : (idx === res.carousel_slides.length - 1 ? '🎯 TAKEAWAY' : `STEP ${idx}`),
          headline: s.title || `Key Insight #${idx + 1}`,
          subtitle: s.body || '',
          gradientId: selectedGradient.id,
        }));
        setSlides(generatedSlides);
        setActiveSlideIdx(0);
        setStudioMode('carousel');
        setAiModal({ open: false, topic: '', loading: false });
        toast.success(`✨ Generated ${generatedSlides.length}-slide LinkedIn carousel!`);
        trackEvent('ai_carousel_generated', { slide_count: generatedSlides.length });
      } else if (res && res.key_takeaways && res.key_takeaways.length > 0) {
        setHeadline(res.key_takeaways[0]);
        setSubtitle(res.key_takeaways[1] || '');
        setBadge('💡 QUICK TIP');
        setAiModal({ open: false, topic: '', loading: false });
        toast.success('Generated graphic copy!');
      } else {
        toast.error('Could not generate slides for this prompt. Try a broader topic.');
      }
    } catch (err) {
      toast.error('AI generation failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAiModal(prev => ({ ...prev, loading: false }));
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">

      {/* ── Left Preview Canvas Column ── */}
      <div className="xl:col-span-7 flex flex-col items-center space-y-4">

        {/* Studio Mode Switcher & Quick AI Action */}
        <div className="w-full flex items-center justify-between bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-2xl p-2 shadow-2xs">
          <div className="flex items-center gap-1.5 p-1 bg-gray-100/90 dark:bg-zinc-800 rounded-xl">
            <button
              onClick={() => setStudioMode('single')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                studioMode === 'single'
                  ? 'bg-white dark:bg-zinc-900 text-gray-900 dark:text-white shadow-2xs'
                  : 'text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              Single Graphic
            </button>
            <button
              onClick={() => setStudioMode('carousel')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                studioMode === 'carousel'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-xs'
                  : 'text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              <FaLayerGroup className="text-[10px]" />
              LinkedIn PDF Carousel ({slides.length} Slides)
            </button>
          </div>

          <button
            onClick={() => setAiModal({ open: true, topic: '', loading: false })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/20 text-xs font-bold transition-all cursor-pointer"
          >
            <FaMagic className="text-xs" />
            <span className="hidden sm:inline">AI Generator</span>
          </button>
        </div>

        {/* Aspect Ratio & Canvas Toolbar */}
        <div className="w-full flex items-center justify-between gap-2 px-1">
          {/* Aspect Ratios */}
          <div className="flex items-center gap-1 bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-xl p-1 shadow-2xs">
            {ASPECT_RATIOS.map(ar => (
              <button
                key={ar.id}
                onClick={() => setAspectRatio(ar)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  aspectRatio.id === ar.id
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 shadow-2xs'
                    : 'text-gray-500 hover:text-gray-900 dark:hover:text-gray-200'
                }`}
                title={ar.sub}
              >
                <span className="text-[10px]">{ar.icon}</span>
                <span>{ar.id}</span>
              </button>
            ))}
          </div>

          {/* Canvas Zoom Controls */}
          <div className="flex items-center gap-1 bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-xl p-1 shadow-2xs text-xs font-medium text-gray-500">
            <button
              onClick={() => setCanvasZoom(prev => Math.max(0.6, prev - 0.1))}
              className="px-2 py-0.5 hover:text-gray-900 dark:hover:text-white rounded cursor-pointer"
              title="Zoom out"
            >
              -
            </button>
            <span className="text-[11px] font-mono px-1">{Math.round(canvasZoom * 100)}%</span>
            <button
              onClick={() => setCanvasZoom(prev => Math.min(1.4, prev + 0.1))}
              className="px-2 py-0.5 hover:text-gray-900 dark:hover:text-white rounded cursor-pointer"
              title="Zoom in"
            >
              +
            </button>
            <button
              onClick={() => setCanvasZoom(1)}
              className="px-1.5 py-0.5 text-[10px] text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 rounded cursor-pointer"
            >
              Reset
            </button>
          </div>
        </div>

        {/* Canvas Display Stage */}
        <div className="w-full bg-[#E5E5E3] dark:bg-zinc-950/80 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-6 sm:p-8 flex flex-col items-center justify-center shadow-inner relative overflow-hidden min-h-[480px]">
          {/* Subtle Ambient Studio Spotlight */}
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(#d4d4d4_1px,transparent_1px)] dark:bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:24px_24px] opacity-40" />

          <div
            className="max-w-full flex items-center justify-center relative z-10 transition-transform duration-200"
            style={{ transform: `scale(${canvasZoom})` }}
          >
            <canvas
              ref={canvasRef}
              className="max-w-full max-h-[500px] object-contain rounded-2xl shadow-2xl transition-all duration-300"
            />
          </div>

          {/* Carousel Slide Navigation if in carousel mode */}
          {studioMode === 'carousel' && (
            <div className="mt-5 flex items-center gap-3 relative z-10">
              <button
                onClick={() => setActiveSlideIdx(Math.max(0, activeSlideIdx - 1))}
                disabled={activeSlideIdx === 0}
                className="p-2 rounded-full bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 disabled:opacity-30 shadow-xs cursor-pointer active:scale-90 transition-transform"
              >
                <FaChevronLeft className="text-xs" />
              </button>
              <span className="text-xs font-bold text-gray-800 dark:text-zinc-200 bg-white/80 dark:bg-zinc-900/80 px-3 py-1 rounded-full border border-gray-200/60 dark:border-zinc-800 shadow-2xs backdrop-blur-xs">
                Slide {activeSlideIdx + 1} of {slides.length}
              </span>
              <button
                onClick={() => setActiveSlideIdx(Math.min(slides.length - 1, activeSlideIdx + 1))}
                disabled={activeSlideIdx === slides.length - 1}
                className="p-2 rounded-full bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 text-gray-700 dark:text-gray-300 disabled:opacity-30 shadow-xs cursor-pointer active:scale-90 transition-transform"
              >
                <FaChevronRight className="text-xs" />
              </button>
            </div>
          )}
        </div>

        {/* Carousel Slide Thumbnails */}
        {studioMode === 'carousel' && (
          <div className="w-full flex items-center gap-2.5 overflow-x-auto pb-2 pt-1">
            {slides.map((s, idx) => (
              <div
                key={s.id}
                onClick={() => setActiveSlideIdx(idx)}
                className={`relative shrink-0 w-32 p-3 rounded-2xl border cursor-pointer transition-all ${
                  activeSlideIdx === idx
                    ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 ring-2 ring-indigo-500/20 shadow-xs'
                    : 'border-gray-200/80 bg-white dark:bg-zinc-900 hover:border-gray-300 shadow-2xs'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-bold text-gray-500">#{idx + 1}</span>
                  <div className="flex items-center gap-1">
                    {idx > 0 && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          moveSlide(idx, -1);
                        }}
                        className="text-gray-400 hover:text-gray-700 p-0.5 text-[8px]"
                        title="Move Left"
                      >
                        ◀
                      </button>
                    )}
                    {idx < slides.length - 1 && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          moveSlide(idx, 1);
                        }}
                        className="text-gray-400 hover:text-gray-700 p-0.5 text-[8px]"
                        title="Move Right"
                      >
                        ▶
                      </button>
                    )}
                    {slides.length > 2 && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeSlide(idx);
                        }}
                        className="text-gray-400 hover:text-rose-500 p-0.5"
                        title="Delete Slide"
                      >
                        <FaTrash className="text-[9px]" />
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-[11px] font-bold text-gray-900 dark:text-white truncate">
                  {s.badge || `Slide ${idx + 1}`}
                </p>
                <p className="text-[10px] text-gray-500 dark:text-gray-400 truncate mt-0.5 leading-tight">
                  {s.headline || 'No text'}
                </p>
              </div>
            ))}

            {slides.length < 10 && (
              <button
                onClick={addSlide}
                className="shrink-0 flex flex-col items-center justify-center gap-1 w-24 h-20 rounded-2xl border-2 border-dashed border-gray-300 dark:border-zinc-700 hover:border-indigo-500 hover:bg-indigo-50/20 text-gray-500 text-xs font-bold transition-all cursor-pointer"
              >
                <FaPlus className="text-xs" />
                <span>Add Slide</span>
              </button>
            )}
          </div>
        )}

        {/* Export & Actions Toolbar */}
        <div className="w-full flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="flex items-center gap-2">
            {studioMode === 'carousel' ? (
              <button
                onClick={handleDownloadPdf}
                disabled={isExportingPdf}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 active:scale-95 transition-all cursor-pointer"
              >
                <FaFilePdf className="text-xs" />
                {isExportingPdf ? 'Exporting PDF...' : 'Download LinkedIn Carousel (PDF)'}
              </button>
            ) : (
              <button
                onClick={handleDownloadImage}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-900 hover:bg-black dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 font-bold text-xs shadow-xs active:scale-95 transition-all cursor-pointer"
              >
                <FaDownload className="text-xs" />
                Download High-Res PNG
              </button>
            )}

            <button
              onClick={handleCopyClipboard}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-300/80 dark:border-zinc-700 bg-white dark:bg-zinc-800 hover:bg-gray-50 dark:hover:bg-zinc-700 font-bold text-xs text-gray-700 dark:text-gray-200 active:scale-95 transition-all cursor-pointer shadow-2xs"
            >
              <FaCopy className="text-xs" />
              Copy Slide
            </button>
          </div>

          <button
            onClick={handleAttachPost}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold text-xs shadow-md shadow-indigo-500/20 active:scale-95 transition-all cursor-pointer"
          >
            <FaMagic className="text-xs" />
            Attach to Post Composer →
          </button>
        </div>

      </div>

      {/* ── Right Controls Panel Column ── */}
      <div className="xl:col-span-5 space-y-5">

        {/* 1. Layout Archetypes Selector */}
        <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center justify-between">
            <span>Card Layout Archetype</span>
            <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400">6 Styles</span>
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {CARD_ARCHETYPES.map((arch) => {
              const Icon = arch.icon;
              const isSelected = cardArchetype === arch.id;
              return (
                <button
                  key={arch.id}
                  onClick={() => {
                    setCardArchetype(arch.id);
                    if (arch.id === 'code_snippet') {
                      setShowMacOsBar(true);
                      setFontFamily('Courier New');
                    } else if (arch.id === 'editorial_paper') {
                      setFontFamily('Georgia');
                    }
                  }}
                  className={`flex flex-col items-start p-3 rounded-2xl border text-left transition-all cursor-pointer ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/50 ring-2 ring-indigo-500/20'
                      : 'border-gray-200/80 dark:border-zinc-800 bg-gray-50/60 dark:bg-zinc-800/40 hover:bg-gray-100 dark:hover:bg-zinc-800'
                  }`}
                >
                  <div className={`w-7 h-7 rounded-xl flex items-center justify-center mb-1.5 ${
                    isSelected ? 'bg-indigo-600 text-white' : 'bg-gray-200 dark:bg-zinc-700 text-gray-700 dark:text-gray-300'
                  }`}>
                    <Icon className="text-xs" />
                  </div>
                  <span className="text-xs font-bold text-gray-900 dark:text-white leading-tight">
                    {arch.label}
                  </span>
                  <span className="text-[9px] text-gray-400 leading-tight mt-0.5 line-clamp-1">
                    {arch.desc}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 2. Quick Presets */}
        <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2.5 flex items-center gap-1.5">
            <FaMagic className="text-amber-500" /> 1-Click Templates
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {TEMPLATES.map((tmpl) => (
              <button
                key={tmpl.name}
                onClick={() => {
                  setCardArchetype(tmpl.archetype || 'glassmorphic');
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
                  if (foundGrad) {
                    setBgType('gradient');
                    setSelectedGradient(foundGrad);
                  }
                  setFontFamily(tmpl.font);
                }}
                className="text-left p-2.5 rounded-xl border border-gray-100 dark:border-zinc-800 bg-gray-50/70 dark:bg-zinc-800/40 hover:bg-indigo-50/50 hover:border-indigo-200 transition-all text-xs font-semibold text-gray-800 dark:text-gray-200 cursor-pointer"
              >
                {tmpl.name}
              </button>
            ))}
          </div>
        </div>

        {/* 3. Background & Styling */}
        <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
              <FaPalette className="text-indigo-500" /> Canvas Background
            </p>
            <div className="flex items-center gap-1 bg-gray-100 dark:bg-zinc-800 p-0.5 rounded-lg text-[10px] font-bold">
              <button
                onClick={() => setBgType('gradient')}
                className={`px-2 py-0.5 rounded-md cursor-pointer ${bgType === 'gradient' ? 'bg-white dark:bg-zinc-900 text-gray-900 dark:text-white shadow-2xs' : 'text-gray-500'}`}
              >
                Gradients
              </button>
              <button
                onClick={() => setBgType('solid')}
                className={`px-2 py-0.5 rounded-md cursor-pointer ${bgType === 'solid' ? 'bg-white dark:bg-zinc-900 text-gray-900 dark:text-white shadow-2xs' : 'text-gray-500'}`}
              >
                Luxury Solids
              </button>
            </div>
          </div>

          {bgType === 'gradient' ? (
            <div className="grid grid-cols-4 sm:grid-cols-8 gap-1.5">
              {GRADIENTS.map((g) => (
                <button
                  key={g.id}
                  onClick={() => setSelectedGradient(g)}
                  className={`h-10 rounded-xl flex items-center justify-center transition-all cursor-pointer ${
                    selectedGradient.id === g.id ? 'ring-2 ring-indigo-500 ring-offset-2 scale-105 shadow-md' : 'opacity-80 hover:opacity-100'
                  }`}
                  style={{
                    background: `linear-gradient(135deg, ${g.colors[0]}, ${g.colors[1]})`,
                  }}
                  title={g.name}
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
              {SOLID_COLORS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSolid(s)}
                  className={`h-10 rounded-xl flex items-center justify-center transition-all cursor-pointer border border-gray-200 dark:border-zinc-700 ${
                    selectedSolid.id === s.id ? 'ring-2 ring-indigo-500 ring-offset-2 scale-105 shadow-md' : 'opacity-80 hover:opacity-100'
                  }`}
                  style={{ backgroundColor: s.color }}
                  title={s.name}
                />
              ))}
            </div>
          )}

          {/* Texture & Shadow */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Texture Overlay</label>
              <select
                value={patternOverlay}
                onChange={(e) => setPatternOverlay(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none cursor-pointer"
              >
                <option value="none">Clean Solid</option>
                <option value="dots">Subtle Dots</option>
                <option value="grid">Architectural Grid</option>
                <option value="scanlines">Tech Scanlines</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Card Shadow Depth</label>
              <select
                value={cardShadow}
                onChange={(e) => setCardShadow(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none cursor-pointer"
              >
                <option value="elevated">Elevated 3D</option>
                <option value="subtle">Subtle Soft</option>
                <option value="glow">Vibrant Glow</option>
                <option value="none">Flat / No Shadow</option>
              </select>
            </div>
          </div>

          {/* Window Chrome & Bezel Options */}
          <div className="pt-2 border-t border-gray-100 dark:border-zinc-800 flex items-center justify-between gap-4">
            <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={showMacOsBar}
                onChange={(e) => setShowMacOsBar(e.target.checked)}
                className="rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
              />
              <span>macOS Traffic Lights Bar (🔴 🟡 🟢)</span>
            </label>
          </div>
        </div>

        {/* 4. Text & Content Editor */}
        <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
            <FaFont className="text-gray-500" />
            {studioMode === 'carousel' ? `Slide #${activeSlideIdx + 1} Content` : 'Text & Content'}
          </p>

          {/* If Metric Stat Archetype */}
          {cardArchetype === 'metric_stat' ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Giant KPI / Stat</label>
                  <input
                    type="text"
                    value={metricValue}
                    onChange={(e) => setMetricValue(e.target.value)}
                    placeholder="e.g. +340% or $1.2M"
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white font-bold outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Delta Pill</label>
                  <input
                    type="text"
                    value={metricDelta}
                    onChange={(e) => setMetricDelta(e.target.value)}
                    placeholder="e.g. ▲ +28% MoM"
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Metric Label</label>
                <input
                  type="text"
                  value={metricLabel}
                  onChange={(e) => setMetricLabel(e.target.value)}
                  placeholder="e.g. Organic Reach"
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                />
              </div>
            </div>
          ) : cardArchetype === 'code_snippet' ? (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Filename</label>
                <input
                  type="text"
                  value={codeFilename}
                  onChange={(e) => setCodeFilename(e.target.value)}
                  placeholder="e.g. pipeline.ts"
                  className="w-full text-xs px-3.5 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Code Lines</label>
                <textarea
                  rows={4}
                  value={codeSnippet}
                  onChange={(e) => setCodeSnippet(e.target.value)}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-mono resize-none leading-relaxed"
                />
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">Badge / Category Pill</label>
              <input
                type="text"
                value={currentBadge}
                onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('badge', e.target.value) : setBadge(e.target.value)}
                placeholder="e.g. 💡 QUICK TIP"
                className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
              />
              <div className="flex flex-wrap gap-1.5 mt-2">
                {BADGE_PRESETS.slice(0, 5).map((p) => (
                  <button
                    key={p}
                    onClick={() => studioMode === 'carousel' ? updateActiveSlide('badge', p) : setBadge(p)}
                    className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-gray-100 dark:bg-zinc-800 hover:bg-indigo-50 text-gray-600 dark:text-gray-300 cursor-pointer"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">
              {cardArchetype === 'tweet_card' ? 'Tweet Body' : 'Headline'}
            </label>
            <textarea
              rows={3}
              value={currentHeadline}
              onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('headline', e.target.value) : setHeadline(e.target.value)}
              className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none font-medium leading-relaxed"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">
              {cardArchetype === 'tweet_card' ? 'Timestamp / Date' : 'Subtitle / Key Takeaway'}
            </label>
            <textarea
              rows={2}
              value={currentSubtitle}
              onChange={(e) => studioMode === 'carousel' ? updateActiveSlide('subtitle', e.target.value) : setSubtitle(e.target.value)}
              className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none leading-relaxed"
            />
          </div>

          {/* Typography & Size */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Typography</label>
              <select
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none cursor-pointer"
              >
                {FONTS.map((f) => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Headline Size ({headlineSize}px)</label>
              <input
                type="range"
                min="36"
                max="72"
                value={headlineSize}
                onChange={(e) => setHeadlineSize(Number(e.target.value))}
                className="w-full accent-indigo-600 cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* 5. Author Branding & Toggles */}
        <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
          <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
            Author & Verification Badges
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Author Name</label>
              <input
                type="text"
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-600 dark:text-gray-400 mb-1">Handle</label>
              <input
                type="text"
                value={authorHandle}
                onChange={(e) => setAuthorHandle(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
              />
            </div>
          </div>

          <div className="pt-2 border-t border-gray-100 dark:border-zinc-800 space-y-2">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={isVerified}
                  onChange={(e) => setIsVerified(e.target.checked)}
                  className="rounded text-blue-500 focus:ring-blue-400 cursor-pointer"
                />
                <span>Blue Verified Badge (✓)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={showStars}
                  onChange={(e) => setShowStars(e.target.checked)}
                  className="rounded text-amber-500 focus:ring-amber-400 cursor-pointer"
                />
                <span>5-Star Rating (★★★★★)</span>
              </label>
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={showWatermark}
                  onChange={(e) => setShowWatermark(e.target.checked)}
                  className="rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                />
                <span>Brand Watermark</span>
              </label>
              {showWatermark && (
                <input
                  type="text"
                  value={watermarkText}
                  onChange={(e) => setWatermarkText(e.target.value)}
                  placeholder="e.g. unravler.com"
                  className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none w-36"
                />
              )}
            </div>
          </div>
        </div>

      </div>

      {/* ── AI MAGIC CAROUSEL GENERATOR MODAL ── */}
      {aiModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
          <div className="w-full max-w-lg bg-white dark:bg-zinc-900 rounded-3xl border border-gray-200 dark:border-zinc-800 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100 dark:border-zinc-800">
              <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2">
                <FaMagic className="text-amber-500 text-xs" /> AI Carousel & Graphic Generator
              </h3>
              <button
                onClick={() => setAiModal({ open: false, topic: '', loading: false })}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
              >
                <FaTimes className="text-xs" />
              </button>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-gray-700 dark:text-gray-300">
                What is your topic, concept, or article link?
              </label>
              <textarea
                rows={3}
                value={aiModal.topic}
                onChange={(e) => setAiModal((prev) => ({ ...prev, topic: e.target.value }))}
                placeholder="e.g. 5 actionable lessons from scaling an AI SaaS to $50k MRR without venture capital..."
                className="w-full p-3 bg-gray-50/70 dark:bg-zinc-800/60 border border-gray-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-gray-900 dark:text-white placeholder-gray-400 transition-all resize-none"
              />
            </div>

            {/* Quick Prompts */}
            <div className="flex flex-wrap gap-1.5">
              {[
                '5 LinkedIn Growth Rules',
                'Cold Email Framework',
                'AI Tools That Save 10h/week',
                'Founder Mistake in 2026',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setAiModal((prev) => ({ ...prev, topic: suggestion }))}
                  className="px-2.5 py-1 bg-gray-100 dark:bg-zinc-800 hover:bg-amber-50 text-[11px] font-medium text-gray-600 dark:text-gray-300 rounded-lg transition-colors cursor-pointer"
                >
                  {suggestion}
                </button>
              ))}
            </div>

            <button
              onClick={handleRunAiGenerate}
              disabled={aiModal.loading || !aiModal.topic.trim()}
              className="w-full py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer active:scale-95"
            >
              {aiModal.loading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Generating 5-Slide Carousel...</span>
                </>
              ) : (
                <>
                  <FaMagic className="text-xs" />
                  <span>Generate 5-Slide LinkedIn Carousel</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

