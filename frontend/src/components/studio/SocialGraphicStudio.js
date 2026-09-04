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
  FaBolt,
  FaComments,
  FaExchangeAlt,
  FaAdjust,
  FaBorderAll,
  FaArrowsAltV,
  FaGem,
  FaSlidersH,
  FaCheckCircle,
} from 'react-icons/fa';
import { toast } from 'sonner';
import { trackEvent } from '@/lib/analytics';
import { repurposeContent } from '@/lib/api';

export const ASPECT_RATIOS = [
  { id: '1:1', label: 'Square', sub: 'Instagram / LinkedIn', width: 1080, height: 1080, icon: '■' },
  { id: '4:5', label: 'Portrait', sub: 'LinkedIn PDF / IG Feed', width: 1080, height: 1350, icon: '▮' },
  { id: '16:9', label: 'Landscape', sub: 'X (Twitter) / YouTube', width: 1200, height: 675, icon: '▬' },
  { id: '9:16', label: 'Story / Reel', sub: 'TikTok / Shorts / IG Story', width: 1080, height: 1920, icon: '📱' },
];

export const CARD_ARCHETYPES = [
  { id: 'glassmorphic', label: 'Frosted Glass', icon: FaLayerGroup, desc: 'Translucent frosted card with specular rim', tag: 'Aesthetic' },
  { id: 'bento_glow', label: 'Bento Glow', icon: FaGem, desc: 'Dark OLED card with neon gradient border', tag: 'Modern' },
  { id: 'tweet_card', label: 'X / Twitter Post', icon: FaTwitter, desc: 'Authentic post card with verified badge & metrics', tag: 'Social' },
  { id: 'editorial_paper', label: 'Editorial Paper', icon: FaQuoteLeft, desc: 'Warm minimalist stone card with luxury serif', tag: 'Editorial' },
  { id: 'metric_stat', label: 'Big Stat Callout', icon: FaChartLine, desc: 'Giant growth KPI with positive delta pill', tag: 'Data' },
  { id: 'brutalist_mono', label: 'Neo-Brutalist', icon: FaBorderAll, desc: 'High-contrast black border & hard drop shadow', tag: 'Trendy' },
  { id: 'code_snippet', label: 'Code Terminal', icon: FaTerminal, desc: 'macOS dark terminal with traffic lights', tag: 'Developer' },
  { id: 'testimonial', label: '5-Star Review', icon: FaStar, desc: 'Client quote with gold 5-star rating', tag: 'Social Proof' },
  { id: 'minimal_swiss', label: 'Minimal Swiss', icon: FaBolt, desc: 'High-fashion typographic poster with index badge', tag: 'Agency' },
  { id: 'chat_bubble', label: 'Chat Conversation', icon: FaComments, desc: 'Story dialogue with incoming prompt & punchline', tag: 'Story' },
  { id: 'versus_comparison', label: 'Versus Matrix', icon: FaExchangeAlt, desc: 'The Old Way ✕ vs The 10x Modern System ✓', tag: 'Viral' },
  { id: 'split_contrast', label: 'Split Contrast', icon: FaAdjust, desc: 'Dual-tone high contrast header & light body', tag: 'High Impact' },
];

export const CARD_PLACEMENTS = [
  { id: 'center', label: 'Centered', desc: 'Balanced symmetrical placement' },
  { id: 'bottom', label: 'Grounded Bottom', desc: 'Anchored lower third' },
  { id: 'top', label: 'Top Anchored', desc: 'Header emphasis' },
  { id: 'full_bleed', label: 'Edge-to-Edge', desc: 'Maximum screen fill' },
];

export const CARD_WIDTHS = [
  { id: 'compact', label: 'Compact (78%)', desc: 'Focused card width' },
  { id: 'standard', label: 'Balanced (86%)', desc: 'Golden standard' },
  { id: 'wide', label: 'Wide (94%)', desc: 'Dense information fill' },
];

export const GRADIENTS = [
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

export const SOLID_COLORS = [
  { id: 'solid-jet-black', name: 'Jet Black', color: '#09090B', text: '#ffffff' },
  { id: 'solid-slate-dark', name: 'Slate 900', color: '#0F172A', text: '#ffffff' },
  { id: 'solid-pure-white', name: 'Pure White', color: '#FFFFFF', text: '#0F172A' },
  { id: 'solid-warm-stone', name: 'Warm Stone', color: '#F5F5F4', text: '#0F172A' },
  { id: 'solid-british-green', name: 'Racing Green', color: '#064E3B', text: '#ffffff' },
  { id: 'solid-royal-navy', name: 'Royal Navy', color: '#0A192F', text: '#ffffff' },
];

export const BADGE_PRESETS = [
  '🚀 NEW FEATURE',
  '💡 QUICK TIP',
  '🧵 THREAD 1/5',
  '🔥 TRENDING',
  '⭐ 5-STAR REVIEW',
  '🎙️ NEW EPISODE',
  '✨ PRO INSIGHT',
  '📈 CASE STUDY',
  '📌 FRAMEWORK',
  '⚡ UNPOPULAR OPINION',
];

export const TEMPLATES = [
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
    name: 'Bento Dark Tech',
    archetype: 'bento_glow',
    badge: '⚡ NEXT GEN',
    headline: 'Headless Social Orchestration with Autonomous MCP Agents',
    subtitle: 'Plug Cursor, Claude, or Windsurf directly into your multi-channel pipeline.',
    gradientId: 'cyber-neon',
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
    name: 'Neo-Brutalist Drop',
    archetype: 'brutalist_mono',
    badge: '🛑 STOP SCROLLING',
    headline: 'Stop relying on organic luck. Systems beat inspiration every time.',
    subtitle: 'The 3-step flywheel that generated 12,000 inbound leads in Q3.',
    gradientId: 'acid-lime',
    font: 'Arial Black',
  },
  {
    name: 'Code Terminal',
    archetype: 'code_snippet',
    badge: '💻 DEV LOG',
    headline: 'Automating Social Content Delivery',
    subtitle: 'TypeScript SDK sample for headless publishing.',
    gradientId: 'midnight-violet',
    font: 'Courier New',
  },
  {
    name: '5-Star Review',
    archetype: 'testimonial',
    badge: '⭐ CLIENT STORY',
    headline: '"Unravler replaced 4 separate tools for our agency. We save 15+ hours every single week."',
    subtitle: 'Head of Content, Horizon Media',
    gradientId: 'sunset-gold',
    font: 'system-ui',
  },
  {
    name: 'Swiss Architectural',
    archetype: 'minimal_swiss',
    badge: 'EDITION NO. 14',
    headline: 'The Psychology of High-Dwell Visual Carousels on Modern Feeds',
    subtitle: 'Why structured information hierarchies generate 4x higher save rates.',
    gradientId: 'clean-cloud',
    font: 'system-ui',
  },
  {
    name: 'The Old Way vs 10x',
    archetype: 'versus_comparison',
    badge: '⚖️ BREAKDOWN',
    headline: 'Manual Posting vs The Unravler Flywheel',
    subtitle: 'Why top 1% creators never manually log into 5 different platforms.',
    gradientId: 'dark-titanium',
    font: 'system-ui',
  },
  {
    name: 'Chat Storytime',
    archetype: 'chat_bubble',
    badge: '💬 FOUNDER DIALOGUE',
    headline: 'How do you ship 20 high-quality social posts in 1 hour?',
    subtitle: 'A simple framework anyone can replicate.',
    gradientId: 'oceanic',
    font: 'system-ui',
  },
];

export const DEFAULT_CAROUSEL_SLIDES = [
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

export const FONTS = [
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

  // Active Inspector Tab: 'layout' | 'style' | 'content' | 'extras'
  const [activeInspectorTab, setActiveInspectorTab] = useState('layout');

  // Card Archetype
  const [cardArchetype, setCardArchetype] = useState('glassmorphic');

  // Placement & Dimensions
  const [cardPlacement, setCardPlacement] = useState('center'); // 'center' | 'bottom' | 'top' | 'full_bleed'
  const [cardWidthMode, setCardWidthMode] = useState('standard'); // 'compact' | 'standard' | 'wide'
  const [cardCornerRadius, setCardCornerRadius] = useState(32);

  // Frame & Bezel
  const [showMacOsBar, setShowMacOsBar] = useState(false);
  const [cardShadow, setCardShadow] = useState('elevated'); // 'subtle' | 'elevated' | 'glow' | 'none'
  const [isVerified, setIsVerified] = useState(true);
  const [showStars, setShowStars] = useState(false);
  const [showWatermark, setShowWatermark] = useState(true);
  const [watermarkText, setWatermarkText] = useState('unravler.com');

  // Archetype-specific state
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

  // Versus Archetype State
  const [versusLeftLabel, setVersusLeftLabel] = useState('Traditional Way');
  const [versusLeftText, setVersusLeftText] = useState('Posting manually across 5 platforms with no analytics or first-comment strategy.');
  const [versusRightLabel, setVersusRightLabel] = useState('The 10x Unravler System');
  const [versusRightText, setVersusRightText] = useState('1-click multi-network sync, automated first comments & AI carousels.');

  // Chat Archetype State
  const [chatSenderName, setChatSenderName] = useState('Sarah (Founder)');
  const [chatPrompt, setChatPrompt] = useState('How do you publish 5x/week without spending all day on social?');
  const [chatReply, setChatReply] = useState('Batch 1 master post into carousels, threads, and short clips in 10 minutes.');

  // Swiss Archetype State
  const [swissIndex, setSwissIndex] = useState('01');
  const [swissTagline, setSwissTagline] = useState('ISSUE NO. 24 — ARCHITECTURE');

  // Canvas Options
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

    // 3. Card Placement & Dimensions
    let widthRatio = 0.86;
    if (cardPlacement === 'full_bleed') widthRatio = 0.96;
    else if (cardWidthMode === 'compact') widthRatio = 0.78;
    else if (cardWidthMode === 'wide') widthRatio = 0.94;

    let heightRatio = 0.86;
    if (cardPlacement === 'full_bleed') heightRatio = 0.96;
    else if (cardPlacement === 'bottom' || cardPlacement === 'top') heightRatio = 0.82;

    const cardW = width * widthRatio;
    const cardH = height * heightRatio;
    const cardMarginX = (width - cardW) / 2;

    let cardMarginY = (height - cardH) / 2;
    if (cardPlacement === 'top') {
      cardMarginY = height * 0.05;
    } else if (cardPlacement === 'bottom') {
      cardMarginY = height - cardH - (height * 0.05);
    } else if (cardPlacement === 'full_bleed') {
      cardMarginY = (height - cardH) / 2;
    }

    const effectiveRadius = cardArchetype === 'brutalist_mono' ? 0 : cardCornerRadius;

    // Hard drop shadow for Neo-Brutalist
    if (cardArchetype === 'brutalist_mono') {
      ctx.fillStyle = '#000000';
      ctx.fillRect(cardMarginX + 12, cardMarginY + 12, cardW, cardH);
    }

    // Standard Shadow
    ctx.save();
    if (cardArchetype !== 'brutalist_mono') {
      if (cardShadow === 'elevated') {
        ctx.shadowColor = 'rgba(0, 0, 0, 0.40)';
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
    }

    // Colors & Strokes
    let cardTextColor = '#ffffff';
    let cardSubtextColor = 'rgba(255, 255, 255, 0.75)';
    let cardAccentColor = '#38bdf8';

    if (cardArchetype === 'tweet_card') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.96)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#64748b';
      cardAccentColor = '#0284c7';
    } else if (cardArchetype === 'bento_glow') {
      ctx.fillStyle = 'rgba(10, 15, 29, 0.92)';
      const borderGrad = ctx.createLinearGradient(cardMarginX, cardMarginY, cardMarginX + cardW, cardMarginY + cardH);
      borderGrad.addColorStop(0, gradObj.colors[0] || '#4f46e5');
      borderGrad.addColorStop(1, gradObj.colors[gradObj.colors.length - 1] || '#9333ea');
      ctx.strokeStyle = borderGrad;
      cardTextColor = '#ffffff';
      cardSubtextColor = '#94a3b8';
      cardAccentColor = '#38bdf8';
    } else if (cardArchetype === 'editorial_paper') {
      ctx.fillStyle = '#FAF8F5';
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.12)';
      cardTextColor = '#18181b';
      cardSubtextColor = '#52525b';
      cardAccentColor = '#b45309';
    } else if (cardArchetype === 'metric_stat') {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.90)';
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      cardTextColor = '#ffffff';
      cardSubtextColor = 'rgba(255, 255, 255, 0.8)';
      cardAccentColor = '#10b981';
    } else if (cardArchetype === 'brutalist_mono') {
      ctx.fillStyle = '#ffffff';
      ctx.strokeStyle = '#000000';
      cardTextColor = '#000000';
      cardSubtextColor = '#18181b';
      cardAccentColor = '#e11d48';
    } else if (cardArchetype === 'code_snippet') {
      ctx.fillStyle = '#090D16';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
      cardTextColor = '#e2e8f0';
      cardSubtextColor = '#94a3b8';
      cardAccentColor = '#818cf8';
    } else if (cardArchetype === 'testimonial') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#475569';
      cardAccentColor = '#f59e0b';
    } else if (cardArchetype === 'minimal_swiss') {
      ctx.fillStyle = '#FAFAF9';
      ctx.strokeStyle = '#E5E7EB';
      cardTextColor = '#0F172A';
      cardSubtextColor = '#475569';
      cardAccentColor = '#2563EB';
    } else if (cardArchetype === 'chat_bubble') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.96)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#64748b';
      cardAccentColor = '#2563eb';
    } else if (cardArchetype === 'versus_comparison') {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
      cardTextColor = '#ffffff';
      cardSubtextColor = '#94a3b8';
      cardAccentColor = '#10b981';
    } else if (cardArchetype === 'split_contrast') {
      ctx.fillStyle = '#ffffff';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      cardTextColor = '#0f172a';
      cardSubtextColor = '#475569';
      cardAccentColor = '#4f46e5';
    } else {
      // Default: 'glassmorphic'
      ctx.fillStyle = 'rgba(255, 255, 255, 0.14)';
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.28)';
      cardTextColor = gradObj.text || '#ffffff';
      cardSubtextColor = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.8)' : 'rgba(15, 23, 42, 0.8)';
      cardAccentColor = '#fbbf24';
    }

    ctx.lineWidth = cardArchetype === 'brutalist_mono' ? 4 : (cardArchetype === 'bento_glow' ? 2.5 : 2);
    ctx.beginPath();
    ctx.roundRect(cardMarginX, cardMarginY, cardW, cardH, effectiveRadius);
    ctx.fill();
    ctx.stroke();
    ctx.restore(); // Restore shadow context

    // For Split Contrast: Draw top header banner
    if (cardArchetype === 'split_contrast') {
      const headerH = cardH * 0.36;
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(cardMarginX, cardMarginY, cardW, headerH, [effectiveRadius, effectiveRadius, 0, 0]);
      ctx.clip();
      const splitGrad = ctx.createLinearGradient(cardMarginX, cardMarginY, cardMarginX + cardW, cardMarginY + headerH);
      splitGrad.addColorStop(0, gradObj.colors[0] || '#0f172a');
      splitGrad.addColorStop(1, gradObj.colors[gradObj.colors.length - 1] || '#1e1b4b');
      ctx.fillStyle = splitGrad;
      ctx.fillRect(cardMarginX, cardMarginY, cardW, headerH);
      ctx.restore();
    }

    // Bento Glow specular top rim
    if (cardArchetype === 'bento_glow') {
      ctx.save();
      const specularGrad = ctx.createLinearGradient(cardMarginX, cardMarginY, cardMarginX + cardW, cardMarginY);
      specularGrad.addColorStop(0, 'rgba(255, 255, 255, 0)');
      specularGrad.addColorStop(0.5, 'rgba(255, 255, 255, 0.3)');
      specularGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.strokeStyle = specularGrad;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(cardMarginX, cardMarginY, cardW, cardH, effectiveRadius);
      ctx.stroke();
      ctx.restore();
    }

    const textX = cardMarginX + cardW * 0.07;
    const maxTextWidth = cardW - (cardW * 0.14);
    let cursorY = cardMarginY + 40;

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
      ctx.fillText(winTitle, cardMarginX + cardW / 2, dotY + 5);
      ctx.textAlign = 'left';

      cursorY += 40;

      // Divider line
      ctx.strokeStyle = cardArchetype === 'code_snippet' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cardMarginX, cursorY);
      ctx.lineTo(cardMarginX + cardW, cursorY);
      ctx.stroke();

      cursorY += 30;
    }

    // 5. Carousel Slide Pagination Indicator (Top-Right)
    if (slideNum && totalSlides) {
      const slideTag = `${slideNum} / ${totalSlides}`;
      ctx.font = `bold 18px ${fontFamily}`;
      const tagW = ctx.measureText(slideTag).width + 24;
      const tagH = 34;
      const tagX = cardMarginX + cardW - tagW - 24;
      const tagY = cardMarginY + 24;

      ctx.fillStyle = cardArchetype === 'editorial_paper' || cardArchetype === 'tweet_card' || cardArchetype === 'minimal_swiss'
        ? 'rgba(0, 0, 0, 0.06)'
        : 'rgba(0, 0, 0, 0.35)';
      ctx.beginPath();
      ctx.roundRect(tagX, tagY, tagW, tagH, 17);
      ctx.fill();

      ctx.fillStyle = cardArchetype === 'editorial_paper' || cardArchetype === 'tweet_card' || cardArchetype === 'minimal_swiss'
        ? '#0f172a'
        : '#ffffff';
      ctx.fillText(slideTag, tagX + 12, tagY + 23);
    }

    // ── ARCHETYPE CONTENT RENDERING ──

    if (cardArchetype === 'tweet_card') {
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

      ctx.fillStyle = '#64748b';
      ctx.font = `normal 20px ${fontFamily}`;
      ctx.fillText(authorHandle, nameX, avY + 22);

      // X Logo
      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 28px sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText('𝕏', cardMarginX + cardW - 36, avY + 4);
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

    } else if (cardArchetype === 'bento_glow') {
      // Bento Glow Archetype
      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 18px ${fontFamily}`;
        const bText = sBadge.toUpperCase();
        const bW = ctx.measureText(bText).width + 32;
        const bH = 40;

        ctx.fillStyle = 'rgba(79, 70, 229, 0.25)';
        ctx.strokeStyle = 'rgba(129, 140, 248, 0.6)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.roundRect(textX, cursorY, bW, bH, 20);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#a5b4fc';
        ctx.fillText(bText, textX + 16, cursorY + 25);
        cursorY += bH + 32;
      }

      // Headline
      ctx.fillStyle = '#ffffff';
      const bentoLines = wrapLines(sHeadline, maxTextWidth, `bold ${headlineSize}px ${fontFamily}`);
      const bentoLineH = headlineSize * 1.25;
      bentoLines.forEach(l => {
        ctx.fillText(l, textX, cursorY + headlineSize * 0.85);
        cursorY += bentoLineH;
      });

      cursorY += 24;

      // Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#94a3b8';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 26px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 24);
          cursorY += 38;
        });
      }

      // Bottom Row: Bento Chips
      const bottomY = cardMarginY + cardH - 40;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
      ctx.beginPath();
      ctx.roundRect(textX, bottomY - 32, 140, 36, 18);
      ctx.fill();
      ctx.fillStyle = '#38bdf8';
      ctx.font = `bold 14px ${fontFamily}`;
      ctx.fillText('⚡ 10x FLYWHEEL', textX + 14, bottomY - 9);

      // Author on right
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'right';
      ctx.fillText(authorName, cardMarginX + cardW - 32, bottomY - 14);
      ctx.font = `normal 16px ${fontFamily}`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(authorHandle, cardMarginX + cardW - 32, bottomY + 8);
      ctx.textAlign = 'left';

    } else if (cardArchetype === 'editorial_paper') {
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

      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#52525b';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 26px Georgia`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 22);
          cursorY += 38;
        });
      }

      const bottomY = cardMarginY + cardH - 36;
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

      // Trend Delta Pill
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
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#94a3b8';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 24px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 20);
          cursorY += 36;
        });
      }

      const bottomY = cardMarginY + cardH - 30;
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = '#ffffff';
      ctx.fillText(authorName, textX, bottomY);
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(authorHandle, textX + ctx.measureText(authorName).width + 12, bottomY);

    } else if (cardArchetype === 'brutalist_mono') {
      // Neo-Brutalist Monolith
      if (sBadge && sBadge.trim()) {
        ctx.font = `900 18px ${fontFamily}`;
        const bText = sBadge.toUpperCase();
        const bW = ctx.measureText(bText).width + 24;
        ctx.fillStyle = '#000000';
        ctx.fillRect(textX, cursorY, bW, 36);
        ctx.fillStyle = '#FACC15';
        ctx.fillText(bText, textX + 12, cursorY + 25);
        cursorY += 56;
      }

      // Heavy Headline
      ctx.fillStyle = '#000000';
      const brutLines = wrapLines(sHeadline, maxTextWidth, `900 ${headlineSize}px ${fontFamily}`);
      const brutLineH = headlineSize * 1.2;
      brutLines.forEach(l => {
        ctx.fillText(l, textX, cursorY + headlineSize * 0.85);
        cursorY += brutLineH;
      });

      cursorY += 20;

      // Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#18181b';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `600 26px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 22);
          cursorY += 36;
        });
      }

      // Bottom Bar
      const bottomY = cardMarginY + cardH - 40;
      ctx.fillStyle = '#000000';
      ctx.fillRect(textX, bottomY - 30, maxTextWidth, 4);

      ctx.font = `900 22px ${fontFamily}`;
      ctx.fillStyle = '#000000';
      ctx.fillText(authorName.toUpperCase(), textX, bottomY + 12);
      ctx.font = `700 18px ${fontFamily}`;
      ctx.fillStyle = '#52525b';
      ctx.fillText(authorHandle, textX + ctx.measureText(authorName.toUpperCase()).width + 16, bottomY + 12);

    } else if (cardArchetype === 'minimal_swiss') {
      // Minimal Swiss Poster
      // Oversized Index Number
      ctx.font = `900 72px ${fontFamily}`;
      ctx.fillStyle = '#0F172A';
      ctx.fillText(swissIndex || '01', textX, cursorY + 54);

      // Vertical line divider
      const numW = ctx.measureText(swissIndex || '01').width;
      ctx.strokeStyle = '#CBD5E1';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(textX + numW + 24, cursorY);
      ctx.lineTo(textX + numW + 24, cursorY + 60);
      ctx.stroke();

      // Tagline
      ctx.font = `800 18px ${fontFamily}`;
      ctx.fillStyle = '#64748B';
      ctx.fillText(swissTagline || 'ISSUE NO. 24 — ARCHITECTURE', textX + numW + 42, cursorY + 36);

      cursorY += 90;

      // Horizontal separator
      ctx.strokeStyle = '#E2E8F0';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(textX, cursorY);
      ctx.lineTo(textX + maxTextWidth, cursorY);
      ctx.stroke();

      cursorY += 36;

      // Swiss Headline
      ctx.fillStyle = '#0F172A';
      const swissLines = wrapLines(sHeadline, maxTextWidth, `bold ${headlineSize}px ${fontFamily}`);
      const swissLineH = headlineSize * 1.25;
      swissLines.forEach(l => {
        ctx.fillText(l, textX, cursorY + headlineSize * 0.85);
        cursorY += swissLineH;
      });

      cursorY += 24;

      // Subtitle
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#475569';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 26px ${fontFamily}`);
        subLines.forEach(l => {
          ctx.fillText(l, textX, cursorY + 22);
          cursorY += 38;
        });
      }

      // Bottom Row
      const bottomY = cardMarginY + cardH - 36;
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = '#0F172A';
      ctx.fillText(`• ${authorName}`, textX, bottomY);
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillStyle = '#64748B';
      ctx.fillText(authorHandle, textX + ctx.measureText(`• ${authorName}`).width + 16, bottomY);

    } else if (cardArchetype === 'chat_bubble') {
      // Chat Conversation Storytime
      // Contact Bar
      const avR = 26;
      const avX = textX + avR;
      const avY = cursorY + avR;

      ctx.fillStyle = '#2563eb';
      ctx.beginPath();
      ctx.arc(avX, avY, avR, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = `bold 22px ${fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillText(chatSenderName.charAt(0).toUpperCase() || 'S', avX, avY + 7);
      ctx.textAlign = 'left';

      // Contact Name & Active Status
      const nameX = avX + avR + 14;
      ctx.fillStyle = '#0f172a';
      ctx.font = `bold 24px ${fontFamily}`;
      ctx.fillText(chatSenderName, nameX, avY - 2);

      // Active status dot
      ctx.fillStyle = '#22c55e';
      ctx.beginPath();
      ctx.arc(nameX + 6, avY + 18, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#64748b';
      ctx.font = `normal 16px ${fontFamily}`;
      ctx.fillText('Active now', nameX + 18, avY + 23);

      cursorY += avR * 2 + 36;

      // Incoming Bubble (Gray)
      const promptLines = wrapLines(chatPrompt || sHeadline, maxTextWidth * 0.85, `normal 28px ${fontFamily}`);
      const promptBubbleH = promptLines.length * 40 + 36;
      ctx.fillStyle = '#f1f5f9';
      ctx.beginPath();
      ctx.roundRect(textX, cursorY, maxTextWidth * 0.88, promptBubbleH, 24);
      ctx.fill();

      ctx.fillStyle = '#0f172a';
      ctx.font = `500 28px ${fontFamily}`;
      promptLines.forEach((l, idx) => {
        ctx.fillText(l, textX + 24, cursorY + 34 + idx * 40);
      });

      cursorY += promptBubbleH + 28;

      // Outgoing Bubble (Blue Gradient)
      const replyLines = wrapLines(chatReply || sSubtitle, maxTextWidth * 0.85, `bold 28px ${fontFamily}`);
      const replyBubbleH = replyLines.length * 42 + 36;
      const replyBubbleW = maxTextWidth * 0.88;
      const replyX = textX + maxTextWidth - replyBubbleW;

      const chatGrad = ctx.createLinearGradient(replyX, cursorY, replyX + replyBubbleW, cursorY + replyBubbleH);
      chatGrad.addColorStop(0, '#2563eb');
      chatGrad.addColorStop(1, '#4f46e5');
      ctx.fillStyle = chatGrad;
      ctx.beginPath();
      ctx.roundRect(replyX, cursorY, replyBubbleW, replyBubbleH, 24);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = `bold 28px ${fontFamily}`;
      replyLines.forEach((l, idx) => {
        ctx.fillText(l, replyX + 24, cursorY + 34 + idx * 42);
      });

      cursorY += replyBubbleH + 20;

      // Read Receipt
      ctx.font = `italic 16px ${fontFamily}`;
      ctx.fillStyle = '#94a3b8';
      ctx.textAlign = 'right';
      ctx.fillText('Delivered · Read 1m ago ✓✓', textX + maxTextWidth, cursorY);
      ctx.textAlign = 'left';

    } else if (cardArchetype === 'versus_comparison') {
      // Versus Matrix Archetype
      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 18px ${fontFamily}`;
        const bText = sBadge.toUpperCase();
        const bW = ctx.measureText(bText).width + 28;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
        ctx.beginPath();
        ctx.roundRect(textX, cursorY, bW, 36, 18);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.fillText(bText, textX + 14, cursorY + 24);
        cursorY += 56;
      }

      // Title
      ctx.fillStyle = '#ffffff';
      ctx.font = `bold 36px ${fontFamily}`;
      ctx.fillText(sHeadline, textX, cursorY + 28);
      cursorY += 52;

      // Block 1: Traditional Way (Red tint)
      const blockH = 150;
      ctx.fillStyle = 'rgba(239, 68, 68, 0.12)';
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(textX, cursorY, maxTextWidth, blockH, 20);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#f87171';
      ctx.font = `bold 22px ${fontFamily}`;
      ctx.fillText(`✕  ${versusLeftLabel || 'The Old Way'}`, textX + 24, cursorY + 38);

      ctx.fillStyle = '#cbd5e1';
      const oldLines = wrapLines(versusLeftText, maxTextWidth - 48, `normal 22px ${fontFamily}`);
      oldLines.slice(0, 2).forEach((l, idx) => {
        ctx.fillText(l, textX + 24, cursorY + 74 + idx * 32);
      });

      cursorY += blockH + 24;

      // Block 2: 10x Way (Green tint)
      ctx.fillStyle = 'rgba(16, 185, 129, 0.16)';
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.6)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(textX, cursorY, maxTextWidth, blockH, 20);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#34d399';
      ctx.font = `bold 24px ${fontFamily}`;
      ctx.fillText(`✓  ${versusRightLabel || 'The 10x System'}`, textX + 24, cursorY + 38);

      ctx.fillStyle = '#ffffff';
      const newLines = wrapLines(versusRightText, maxTextWidth - 48, `500 22px ${fontFamily}`);
      newLines.slice(0, 2).forEach((l, idx) => {
        ctx.fillText(l, textX + 24, cursorY + 74 + idx * 32);
      });

    } else if (cardArchetype === 'split_contrast') {
      // Split Contrast Archetype
      // Top header banner was clipped and filled earlier
      const headerH = cardH * 0.36;
      let topCursor = cardMarginY + 30;

      if (sBadge && sBadge.trim()) {
        ctx.font = `bold 16px ${fontFamily}`;
        const bText = sBadge.toUpperCase();
        const bW = ctx.measureText(bText).width + 24;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.beginPath();
        ctx.roundRect(textX, topCursor, bW, 32, 16);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.fillText(bText, textX + 12, topCursor + 22);
        topCursor += 48;
      }

      ctx.fillStyle = '#ffffff';
      const splitTopLines = wrapLines(sHeadline, maxTextWidth, `bold 38px ${fontFamily}`);
      splitTopLines.slice(0, 2).forEach((l, idx) => {
        ctx.fillText(l, textX, topCursor + 30 + idx * 46);
      });

      // Bottom Body
      let bodyCursor = cardMarginY + headerH + 40;
      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = '#1e293b';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `500 28px ${fontFamily}`);
        subLines.forEach((l) => {
          ctx.fillText(l, textX, bodyCursor + 24);
          bodyCursor += 40;
        });
      }

      const bottomY = cardMarginY + cardH - 36;
      ctx.font = `bold 20px ${fontFamily}`;
      ctx.fillStyle = '#0f172a';
      ctx.fillText(authorName, textX, bottomY);
      ctx.font = `normal 18px ${fontFamily}`;
      ctx.fillStyle = '#64748b';
      ctx.fillText(authorHandle, textX + ctx.measureText(authorName).width + 12, bottomY);

    } else if (cardArchetype === 'code_snippet') {
      const codeLines = codeSnippet.split('\n');
      ctx.font = `normal 24px "Courier New", monospace`;
      const codeLineH = 38;

      codeLines.forEach((line, idx) => {
        ctx.fillStyle = '#475569';
        ctx.textAlign = 'right';
        ctx.fillText(`${idx + 1}`, textX + 30, cursorY + 24);
        ctx.textAlign = 'left';

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

      if (sSubtitle) {
        cursorY += 30;
        ctx.font = `italic 20px ${fontFamily}`;
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(`// ${sSubtitle}`, textX, cursorY);
      }

    } else if (cardArchetype === 'testimonial') {
      if (showStars || true) {
        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 36px sans-serif';
        ctx.fillText('★★★★★', textX, cursorY + 30);
        cursorY += 56;
      }

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

      const bottomY = cardMarginY + cardH - 40;
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

      ctx.fillStyle = gradObj.text || '#ffffff';
      const lines = wrapLines(sHeadline, maxTextWidth, `bold ${headlineSize}px ${fontFamily}`);
      const lineHeight = headlineSize * 1.25;
      lines.forEach((line) => {
        ctx.fillText(line, textX, cursorY + headlineSize * 0.85);
        cursorY += lineHeight;
      });

      cursorY += 24;

      if (sSubtitle && sSubtitle.trim()) {
        ctx.fillStyle = gradObj.text === '#ffffff' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(15, 23, 42, 0.85)';
        const subLines = wrapLines(sSubtitle, maxTextWidth, `normal 28px ${fontFamily}`);
        subLines.forEach((line) => {
          ctx.fillText(line, textX, cursorY + 24);
          cursorY += 40;
        });
      }

      // Author Branding
      const bottomY = cardMarginY + cardH - 36;
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
      ctx.fillStyle = cardArchetype === 'editorial_paper' || cardArchetype === 'tweet_card' || cardArchetype === 'testimonial' || cardArchetype === 'minimal_swiss' || cardArchetype === 'split_contrast'
        ? 'rgba(0, 0, 0, 0.25)'
        : 'rgba(255, 255, 255, 0.4)';
      ctx.textAlign = 'right';
      ctx.fillText(watermarkText, cardMarginX + cardW - 20, cardMarginY + cardH - 20);
      ctx.textAlign = 'left';
    }
  }, [
    bgType,
    selectedGradient,
    selectedSolid,
    patternOverlay,
    cardArchetype,
    cardPlacement,
    cardWidthMode,
    cardCornerRadius,
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
    versusLeftLabel,
    versusLeftText,
    versusRightLabel,
    versusRightText,
    chatSenderName,
    chatPrompt,
    chatReply,
    swissIndex,
    swissTagline,
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
            <span className="hidden sm:inline">AI Magic Writer</span>
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
                    ? 'bg-indigo-600 text-white shadow-2xs'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <span>{ar.icon}</span>
                <span>{ar.label}</span>
                <span className="hidden sm:inline text-[10px] opacity-70">({ar.id})</span>
              </button>
            ))}
          </div>

          {/* Canvas Zoom */}
          <div className="flex items-center gap-1 bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-xl px-2 py-1 shadow-2xs text-xs font-mono text-gray-500">
            <button
              onClick={() => setCanvasZoom(prev => Math.max(0.6, prev - 0.1))}
              className="px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded cursor-pointer"
            >
              -
            </button>
            <span>{Math.round(canvasZoom * 100)}%</span>
            <button
              onClick={() => setCanvasZoom(prev => Math.min(1.4, prev + 0.1))}
              className="px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded cursor-pointer"
            >
              +
            </button>
          </div>
        </div>

        {/* Main Canvas Frame */}
        <div className="w-full flex items-center justify-center p-6 bg-gray-100/80 dark:bg-zinc-950/80 border border-gray-200/80 dark:border-zinc-800/80 rounded-3xl overflow-hidden min-h-[440px] shadow-inner relative">
          <canvas
            ref={canvasRef}
            style={{
              transform: `scale(${canvasZoom})`,
              transformOrigin: 'center center',
              maxWidth: '100%',
              maxHeight: '520px',
              objectFit: 'contain',
              borderRadius: '24px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              transition: 'transform 0.15s ease-out',
            }}
          />
        </div>

        {/* Carousel Multi-Slide Reel (Only shown in carousel mode) */}
        {studioMode === 'carousel' && (
          <div className="w-full flex items-center gap-2.5 overflow-x-auto pb-2 pt-1 px-1">
            {slides.map((s, idx) => (
              <div
                key={s.id}
                onClick={() => setActiveSlideIdx(idx)}
                className={`shrink-0 flex flex-col justify-between w-28 h-24 p-2.5 rounded-2xl border transition-all cursor-pointer ${
                  activeSlideIdx === idx
                    ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/40 shadow-xs ring-2 ring-indigo-500/20'
                    : 'border-gray-200/80 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-100 dark:bg-zinc-800 text-gray-700 dark:text-gray-300">
                    #{idx + 1}
                  </span>
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
                className="shrink-0 flex flex-col items-center justify-center gap-1 w-24 h-24 rounded-2xl border-2 border-dashed border-gray-300 dark:border-zinc-700 hover:border-indigo-500 hover:bg-indigo-50/20 text-gray-500 text-xs font-bold transition-all cursor-pointer"
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

      {/* ── Right Controls Inspector Panel Column ── */}
      <div className="xl:col-span-5 space-y-4">

        {/* Inspector Navigation Tabs */}
        <div className="flex items-center p-1 bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-2xl shadow-2xs">
          {[
            { id: 'layout', label: 'Layout & Archetype', icon: FaBorderAll },
            { id: 'style', label: 'Canvas & Style', icon: FaPalette },
            { id: 'content', label: 'Content & Copy', icon: FaFont },
            { id: 'extras', label: 'Archetype Extras', icon: FaSlidersH },
          ].map(tab => {
            const Icon = tab.icon;
            const isSelected = activeInspectorTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveInspectorTab(tab.id)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
                }`}
              >
                <Icon className="text-[11px]" />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* ── TAB 1: LAYOUT & ARCHETYPE ── */}
        {activeInspectorTab === 'layout' && (
          <div className="space-y-4">
            {/* 1. Layout Archetypes Selector */}
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center justify-between">
                <span>Card Layout Archetype</span>
                <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950">
                  12 Premium Styles
                </span>
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[380px] overflow-y-auto pr-1">
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
                        } else if (arch.id === 'brutalist_mono') {
                          setFontFamily('Arial Black');
                        }
                      }}
                      className={`flex flex-col items-start p-3 rounded-2xl border text-left transition-all cursor-pointer relative group ${
                        isSelected
                          ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/50 ring-2 ring-indigo-500/20'
                          : 'border-gray-200/80 dark:border-zinc-800 bg-gray-50/60 dark:bg-zinc-800/40 hover:bg-gray-100 dark:hover:bg-zinc-800'
                      }`}
                    >
                      <div className="w-full flex items-center justify-between mb-1.5">
                        <div className={`w-7 h-7 rounded-xl flex items-center justify-center ${
                          isSelected ? 'bg-indigo-600 text-white' : 'bg-gray-200 dark:bg-zinc-700 text-gray-700 dark:text-gray-300'
                        }`}>
                          <Icon className="text-xs" />
                        </div>
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-200/70 dark:bg-zinc-700 text-gray-600 dark:text-gray-300">
                          {arch.tag}
                        </span>
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

            {/* 2. Card Placement & Sizing Controls */}
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
                <FaArrowsAltV className="text-indigo-500" /> Card Placement & Inset
              </p>

              {/* Placement options */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {CARD_PLACEMENTS.map((cp) => (
                  <button
                    key={cp.id}
                    onClick={() => setCardPlacement(cp.id)}
                    className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                      cardPlacement === cp.id
                        ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-bold ring-1 ring-indigo-500/20'
                        : 'border-gray-200 dark:border-zinc-800 bg-gray-50/70 dark:bg-zinc-800/40 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <p className="text-xs font-bold leading-tight">{cp.label}</p>
                    <p className="text-[9px] text-gray-400 leading-tight mt-0.5 truncate">{cp.desc}</p>
                  </button>
                ))}
              </div>

              {/* Width Modes */}
              <div className="grid grid-cols-3 gap-2 pt-1">
                {CARD_WIDTHS.map((cw) => (
                  <button
                    key={cw.id}
                    onClick={() => setCardWidthMode(cw.id)}
                    className={`py-2 px-2.5 rounded-xl border text-center transition-all cursor-pointer ${
                      cardWidthMode === cw.id
                        ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-bold'
                        : 'border-gray-200 dark:border-zinc-800 bg-gray-50/70 dark:bg-zinc-800/40 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <p className="text-xs font-bold">{cw.label}</p>
                  </button>
                ))}
              </div>

              {/* Corner Radius Slider */}
              <div className="pt-2 border-t border-gray-100 dark:border-zinc-800">
                <div className="flex items-center justify-between text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  <span>Card Corner Radius</span>
                  <span>{cardCornerRadius}px</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="48"
                  value={cardCornerRadius}
                  onChange={(e) => setCardCornerRadius(Number(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
              </div>
            </div>

            {/* 3. Quick 1-Click Templates */}
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2.5 flex items-center gap-1.5">
                <FaMagic className="text-amber-500" /> Curated 1-Click Templates
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
                      toast.success(`Loaded "${tmpl.name}" template`);
                    }}
                    className="text-left p-2.5 rounded-xl border border-gray-100 dark:border-zinc-800 bg-gray-50/70 dark:bg-zinc-800/40 hover:bg-indigo-50/50 hover:border-indigo-200 transition-all text-xs font-semibold text-gray-800 dark:text-gray-200 cursor-pointer"
                  >
                    <p className="font-bold truncate">{tmpl.name}</p>
                    <p className="text-[9px] text-gray-400 mt-0.5 truncate">{tmpl.archetype}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 2: CANVAS & STYLE ── */}
        {activeInspectorTab === 'style' && (
          <div className="space-y-4">
            {/* Background Selector */}
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

            {/* Branding & Watermark */}
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={showWatermark}
                    onChange={(e) => setShowWatermark(e.target.checked)}
                    className="rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                  />
                  <span>Brand Watermark Stamp</span>
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
        )}

        {/* ── TAB 3: CONTENT & COPY ── */}
        {activeInspectorTab === 'content' && (
          <div className="space-y-4">
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
                <FaFont className="text-gray-500" />
                {studioMode === 'carousel' ? `Slide #${activeSlideIdx + 1} Content` : 'Text & Content'}
              </p>

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
                  {BADGE_PRESETS.slice(0, 6).map((p) => (
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

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1.5">
                  {cardArchetype === 'tweet_card' ? 'Tweet Body' : 'Headline / Hook'}
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
          </div>
        )}

        {/* ── TAB 4: ARCHETYPE EXTRAS & CONTEXTUAL CONTROLS ── */}
        {activeInspectorTab === 'extras' && (
          <div className="space-y-4">
            {/* Contextual Card Controls */}
            {cardArchetype === 'metric_stat' && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
                <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Big Stat KPI Settings
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Giant KPI</label>
                    <input
                      type="text"
                      value={metricValue}
                      onChange={(e) => setMetricValue(e.target.value)}
                      placeholder="+340%"
                      className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white font-bold outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Delta Pill</label>
                    <input
                      type="text"
                      value={metricDelta}
                      onChange={(e) => setMetricDelta(e.target.value)}
                      placeholder="▲ +28% MoM"
                      className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Metric Label</label>
                  <input
                    type="text"
                    value={metricLabel}
                    onChange={(e) => setMetricLabel(e.target.value)}
                    placeholder="Organic Reach"
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                  />
                </div>
              </div>
            )}

            {cardArchetype === 'code_snippet' && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
                <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Code Terminal Snippet
                </p>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Filename</label>
                  <input
                    type="text"
                    value={codeFilename}
                    onChange={(e) => setCodeFilename(e.target.value)}
                    placeholder="pipeline.ts"
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Code Lines</label>
                  <textarea
                    rows={4}
                    value={codeSnippet}
                    onChange={(e) => setCodeSnippet(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-mono resize-none leading-relaxed"
                  />
                </div>
              </div>
            )}

            {cardArchetype === 'versus_comparison' && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
                <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Versus Matrix Comparison Settings
                </p>
                <div className="space-y-2 p-3 rounded-2xl bg-rose-50/50 dark:bg-rose-950/20 border border-rose-200/60 dark:border-rose-900/40">
                  <label className="block text-xs font-bold text-rose-700 dark:text-rose-400">Traditional / Old Way (✕)</label>
                  <input
                    type="text"
                    value={versusLeftLabel}
                    onChange={(e) => setVersusLeftLabel(e.target.value)}
                    placeholder="The Old Way"
                    className="w-full text-xs px-3 py-1.5 rounded-xl border border-rose-200 bg-white dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-bold"
                  />
                  <textarea
                    rows={2}
                    value={versusLeftText}
                    onChange={(e) => setVersusLeftText(e.target.value)}
                    className="w-full text-xs px-3 py-1.5 rounded-xl border border-rose-200 bg-white dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none"
                  />
                </div>
                <div className="space-y-2 p-3 rounded-2xl bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200/60 dark:border-emerald-900/40">
                  <label className="block text-xs font-bold text-emerald-700 dark:text-emerald-400">The 10x Modern System (✓)</label>
                  <input
                    type="text"
                    value={versusRightLabel}
                    onChange={(e) => setVersusRightLabel(e.target.value)}
                    placeholder="The 10x System"
                    className="w-full text-xs px-3 py-1.5 rounded-xl border border-emerald-200 bg-white dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-bold"
                  />
                  <textarea
                    rows={2}
                    value={versusRightText}
                    onChange={(e) => setVersusRightText(e.target.value)}
                    className="w-full text-xs px-3 py-1.5 rounded-xl border border-emerald-200 bg-white dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none"
                  />
                </div>
              </div>
            )}

            {cardArchetype === 'chat_bubble' && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
                <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Chat Conversation Settings
                </p>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Contact Name</label>
                  <input
                    type="text"
                    value={chatSenderName}
                    onChange={(e) => setChatSenderName(e.target.value)}
                    placeholder="Sarah (Founder)"
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Incoming Hook / Question</label>
                  <textarea
                    rows={2}
                    value={chatPrompt}
                    onChange={(e) => setChatPrompt(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Outgoing Answer / Insight</label>
                  <textarea
                    rows={2}
                    value={chatReply}
                    onChange={(e) => setChatReply(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none resize-none"
                  />
                </div>
              </div>
            )}

            {cardArchetype === 'minimal_swiss' && (
              <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-3">
                <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Minimal Swiss Index & Tagline
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Index Number</label>
                    <input
                      type="text"
                      value={swissIndex}
                      onChange={(e) => setSwissIndex(e.target.value)}
                      placeholder="01"
                      className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none font-mono font-bold"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">Swiss Tagline</label>
                    <input
                      type="text"
                      value={swissTagline}
                      onChange={(e) => setSwissTagline(e.target.value)}
                      placeholder="ISSUE NO. 24"
                      className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800 text-gray-900 dark:text-white outline-none"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Author Attribution & Badges */}
            <div className="bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 rounded-3xl p-5 shadow-2xs space-y-4">
              <p className="text-[11px] font-extrabold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                Author Attribution & Social Badges
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
              </div>
            </div>
          </div>
        )}

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
