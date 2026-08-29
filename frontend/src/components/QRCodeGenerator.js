import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import QRCode from 'qrcode';
import { toast } from 'sonner';
import {
  FaArrowLeft, FaDownload, FaCopy, FaPrint, FaPaperPlane,
  FaLink, FaWifi, FaAddressCard, FaFont, FaMobileAlt, FaEnvelope,
  FaQrcode, FaPalette, FaShapes, FaImage, FaBorderAll, FaMagic,
  FaCheck, FaUndo, FaShareAlt, FaTrash, FaSlidersH
} from 'react-icons/fa';
import {
  SiInstagram, SiLinkedin, SiTiktok, SiYoutube, SiWhatsapp, SiTelegram, SiX
} from 'react-icons/si';

const CONTENT_TYPES = [
  { id: 'url', label: 'Website URL', icon: FaLink, desc: 'Link to any website, bio page, or short link' },
  { id: 'app', label: 'App Download', icon: FaMobileAlt, desc: 'Direct users to iOS App Store & Google Play' },
  { id: 'social', label: 'Social Profile', icon: FaShareAlt, desc: 'Link directly to your Instagram, LinkedIn, X, etc.' },
  { id: 'vcard', label: 'Digital vCard', icon: FaAddressCard, desc: 'Share your complete contact information' },
  { id: 'wifi', label: 'Wi-Fi Network', icon: FaWifi, desc: 'Allow visitors to connect to Wi-Fi instantly' },
  { id: 'text', label: 'Plain Text / Promo', icon: FaFont, desc: 'Display discount coupons or event messages' },
  { id: 'email', label: 'Email / Message', icon: FaEnvelope, desc: 'Open email client with pre-filled message' },
];

const COLOR_PRESETS = [
  { name: 'Classic Black', fg: '#111827', bg: '#ffffff', eye: '#111827' },
  { name: 'Unravler Indigo', fg: '#4F46E5', bg: '#ffffff', eye: '#4338CA', gradient: ['#4F46E5', '#7C3AED'] },
  { name: 'Instagram Sunset', fg: '#E1306C', bg: '#ffffff', eye: '#C13584', gradient: ['#833AB4', '#FD1D1D', '#FCB045'] },
  { name: 'Emerald Growth', fg: '#059669', bg: '#ffffff', eye: '#047857', gradient: ['#059669', '#10B981'] },
  { name: 'Midnight Navy', fg: '#1E293B', bg: '#F8FAFC', eye: '#0F172A', gradient: ['#0F172A', '#334155'] },
  { name: 'Cyber Neon', fg: '#06B6D4', bg: '#0F172A', eye: '#3B82F6', gradient: ['#06B6D4', '#3B82F6'] },
  { name: 'Ruby Bold', fg: '#E11D48', bg: '#ffffff', eye: '#BE123C', gradient: ['#E11D48', '#FB7185'] },
  { name: 'Warm Amber', fg: '#D97706', bg: '#FFFBEB', eye: '#B45309', gradient: ['#D97706', '#F59E0B'] },
];

const FRAMES = [
  { id: 'none', label: 'No Frame', cta: '' },
  { id: 'bottom-banner', label: 'Bottom Banner', cta: 'SCAN ME' },
  { id: 'top-banner', label: 'Top Banner', cta: 'VISIT WEBSITE' },
  { id: 'card-badge', label: 'Badge Card', cta: 'CONNECT WITH ME' },
  { id: 'app-frame', label: 'App Store Frame', cta: 'DOWNLOAD APP' },
  { id: 'promo-frame', label: 'Promo Frame', cta: 'EXCLUSIVE OFFER' },
];

const LOGO_PRESETS = [
  { id: 'none', label: 'None', icon: null },
  { id: 'unravler', label: 'Unravler', text: '✦', color: '#6366F1' },
  { id: 'instagram', label: 'Instagram', icon: SiInstagram, color: '#E1306C' },
  { id: 'linkedin', label: 'LinkedIn', icon: SiLinkedin, color: '#0A66C2' },
  { id: 'x', label: 'X (Twitter)', icon: SiX, color: '#000000' },
  { id: 'youtube', label: 'YouTube', icon: SiYoutube, color: '#FF0000' },
  { id: 'tiktok', label: 'TikTok', icon: SiTiktok, color: '#000000' },
  { id: 'whatsapp', label: 'WhatsApp', icon: SiWhatsapp, color: '#25D366' },
  { id: 'wifi', label: 'Wi-Fi', icon: FaWifi, color: '#4F46E5' },
];

export default function QRCodeGenerator({ onBack }) {
  const navigate = useNavigate();
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);

  // ── Content State ──────────────────────────────────────────────────────────
  const [contentType, setContentType] = useState('url');
  const [url, setUrl] = useState('https://www.unravler.com');
  const [appIos, setAppIos] = useState('https://apps.apple.com/app/id123456789');
  const [appAndroid, setAppAndroid] = useState('https://play.google.com/store/apps/details?id=com.unravler.app');
  const [socialPlatform, setSocialPlatform] = useState('instagram');
  const [socialHandle, setSocialHandle] = useState('unravlerapp');
  const [vcard, setVcard] = useState({
    firstName: 'Alex',
    lastName: 'Morgan',
    org: 'Unravler Agency',
    title: 'Head of Growth',
    phone: '+1 (555) 234-5678',
    email: 'alex@unravler.com',
    url: 'https://www.unravler.com',
  });
  const [wifi, setWifi] = useState({
    ssid: 'Guest_WiFi_HighSpeed',
    password: 'ConnectFast2026',
    encryption: 'WPA',
    hidden: false,
  });
  const [plainText, setPlainText] = useState('Use code UNRAVLER20 for 20% off your subscription!');
  const [emailData, setEmailData] = useState({
    to: 'hello@unravler.com',
    subject: 'Partnership Inquiry',
    body: 'Hi team, I would love to learn more about Unravler.',
  });

  // ── Styling State ──────────────────────────────────────────────────────────
  const [fgColor, setFgColor] = useState('#111827');
  const [bgColor, setBgColor] = useState('#ffffff');
  const [eyeColor, setEyeColor] = useState('#111827');
  const [useGradient, setUseGradient] = useState(false);
  const [gradientColors, setGradientColors] = useState(['#4F46E5', '#7C3AED']);
  const [isTransparentBg, setIsTransparentBg] = useState(false);

  const [dotStyle, setDotStyle] = useState('rounded'); // 'square' | 'rounded' | 'dots'
  const [eyeStyle, setEyeStyle] = useState('rounded'); // 'square' | 'rounded' | 'circle'
  const [errorLevel, setErrorLevel] = useState('H'); // L, M, Q, H
  const [frame, setFrame] = useState('none');
  const [frameCta, setFrameCta] = useState('SCAN ME');
  const [frameBg, setFrameBg] = useState('#111827');
  const [frameTextColor, setFrameTextColor] = useState('#ffffff');

  const [selectedLogoPreset, setSelectedLogoPreset] = useState('unravler');
  const [customLogoUrl, setCustomLogoUrl] = useState(null);
  const [logoSize, setLogoSize] = useState(22); // percent of QR width

  const [exportRes, setExportRes] = useState('1024'); // 512, 1024, 2048
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  // Compute final encoded payload
  const getPayload = useCallback(() => {
    switch (contentType) {
      case 'url':
        return url.trim() || 'https://www.unravler.com';
      case 'app':
        return appIos.trim() || appAndroid.trim() || 'https://www.unravler.com';
      case 'social': {
        const handle = socialHandle.replace(/^@/, '').trim();
        switch (socialPlatform) {
          case 'instagram': return `https://instagram.com/${handle}`;
          case 'linkedin': return `https://linkedin.com/in/${handle}`;
          case 'x': return `https://x.com/${handle}`;
          case 'youtube': return `https://youtube.com/@${handle}`;
          case 'tiktok': return `https://tiktok.com/@${handle}`;
          case 'whatsapp': return `https://wa.me/${handle.replace(/[^0-9]/g, '')}`;
          case 'telegram': return `https://t.me/${handle}`;
          default: return `https://instagram.com/${handle}`;
        }
      }
      case 'vcard': {
        return `BEGIN:VCARD\nVERSION:3.0\nN:${vcard.lastName};${vcard.firstName};;;\nFN:${vcard.firstName} ${vcard.lastName}\nORG:${vcard.org}\nTITLE:${vcard.title}\nTEL;TYPE=CELL:${vcard.phone}\nEMAIL:${vcard.email}\nURL:${vcard.url}\nEND:VCARD`;
      }
      case 'wifi': {
        return `WIFI:T:${wifi.encryption};S:${wifi.ssid};P:${wifi.password};H:${wifi.hidden ? 'true' : 'false'};;`;
      }
      case 'email': {
        return `mailto:${emailData.to}?subject=${encodeURIComponent(emailData.subject)}&body=${encodeURIComponent(emailData.body)}`;
      }
      case 'text':
      default:
        return plainText || 'Unravler QR Code';
    }
  }, [contentType, url, appIos, appAndroid, socialPlatform, socialHandle, vcard, wifi, emailData, plainText]);

  // Render QR Canvas with high-DPI and custom eye/module geometry
  const renderCanvas = useCallback(async (targetCanvas, exportSize = 600) => {
    if (!targetCanvas) return;
    const payload = getPayload();

    try {
      const qr = QRCode.create(payload, {
        errorCorrectionLevel: errorLevel,
      });

      const moduleCount = qr.modules.size;
      const marginModules = frame !== 'none' ? 3 : 2;
      const totalModules = moduleCount + marginModules * 2;
      const scale = exportSize / totalModules;

      const hasFrame = frame !== 'none';
      const frameHeightExtra = hasFrame ? Math.round(exportSize * 0.18) : 0;
      const isTopFrame = frame === 'top-banner';

      const canvasWidth = exportSize;
      const canvasHeight = exportSize + frameHeightExtra;

      targetCanvas.width = canvasWidth;
      targetCanvas.height = canvasHeight;
      const ctx = targetCanvas.getContext('2d');
      ctx.clearRect(0, 0, canvasWidth, canvasHeight);

      // Background
      if (!isTransparentBg) {
        ctx.fillStyle = hasFrame ? frameBg : bgColor;
        if (hasFrame) {
          // Rounded frame card
          const radius = Math.round(exportSize * 0.05);
          ctx.beginPath();
          ctx.roundRect(0, 0, canvasWidth, canvasHeight, radius);
          ctx.fill();

          // QR inner background container
          ctx.fillStyle = bgColor;
          const qrBoxY = isTopFrame ? frameHeightExtra : 0;
          const qrBoxPad = Math.round(exportSize * 0.03);
          ctx.beginPath();
          ctx.roundRect(qrBoxPad, qrBoxY + qrBoxPad, canvasWidth - qrBoxPad * 2, exportSize - qrBoxPad * 2, radius * 0.8);
          ctx.fill();
        } else {
          ctx.fillRect(0, 0, canvasWidth, canvasHeight);
        }
      }

      const qrOffsetY = isTopFrame ? frameHeightExtra : 0;

      // Draw CTA Frame text
      if (hasFrame) {
        ctx.fillStyle = frameTextColor;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = `bold ${Math.round(exportSize * 0.052)}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`;
        const textY = isTopFrame
          ? frameHeightExtra / 2
          : exportSize + frameHeightExtra / 2;
        ctx.fillText(frameCta || 'SCAN ME', canvasWidth / 2, textY);
      }

      // Prepare foreground style (solid or linear gradient)
      let fgStyle = fgColor;
      if (useGradient && gradientColors.length >= 2) {
        const grad = ctx.createLinearGradient(0, qrOffsetY, canvasWidth, qrOffsetY + exportSize);
        gradientColors.forEach((col, idx) => {
          grad.addColorStop(idx / (gradientColors.length - 1), col);
        });
        fgStyle = grad;
      }

      // Check if coordinates fall inside 7x7 corner finder patterns
      const isFinderPattern = (r, c) => {
        if (r < 7 && c < 7) return 'top-left';
        if (r < 7 && c >= moduleCount - 7) return 'top-right';
        if (r >= moduleCount - 7 && c < 7) return 'bottom-left';
        return null;
      };

      // Check if module is in center logo cutout area
      const hasLogo = (selectedLogoPreset !== 'none' || customLogoUrl);
      const logoModuleRadius = hasLogo ? Math.ceil((moduleCount * (logoSize / 100)) / 2) : 0;
      const centerModule = Math.floor(moduleCount / 2);

      const isLogoArea = (r, c) => {
        if (!hasLogo) return false;
        return (
          Math.abs(r - centerModule) <= logoModuleRadius &&
          Math.abs(c - centerModule) <= logoModuleRadius
        );
      };

      // Draw Data Modules
      ctx.fillStyle = fgStyle;
      for (let r = 0; r < moduleCount; r++) {
        for (let c = 0; c < moduleCount; c++) {
          if (isFinderPattern(r, c)) continue; // Eyes drawn separately with dedicated styling
          if (isLogoArea(r, c)) continue; // Reserve space for logo

          if (qr.modules.get(r, c)) {
            const x = (c + marginModules) * scale;
            const y = qrOffsetY + (r + marginModules) * scale;
            const w = scale;
            const h = scale;

            if (dotStyle === 'dots') {
              ctx.beginPath();
              ctx.arc(x + w / 2, y + h / 2, (w / 2) * 0.88, 0, Math.PI * 2);
              ctx.fill();
            } else if (dotStyle === 'rounded') {
              ctx.beginPath();
              ctx.roundRect(x + w * 0.05, y + h * 0.05, w * 0.9, h * 0.9, w * 0.35);
              ctx.fill();
            } else {
              ctx.fillRect(x, y, w + 0.5, h + 0.5);
            }
          }
        }
      }

      // Draw the 3 Finder Pattern Eyes (Top-Left, Top-Right, Bottom-Left)
      const drawEye = (originR, originC) => {
        const eyeX = (originC + marginModules) * scale;
        const eyeY = qrOffsetY + (originR + marginModules) * scale;
        const eyeW = 7 * scale;
        const eyeH = 7 * scale;

        ctx.fillStyle = eyeColor || fgColor;

        // Outer 7x7 Ring
        if (eyeStyle === 'circle') {
          // Circular outer ring
          ctx.beginPath();
          ctx.arc(eyeX + eyeW / 2, eyeY + eyeH / 2, eyeW / 2, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = bgColor;
          ctx.beginPath();
          ctx.arc(eyeX + eyeW / 2, eyeY + eyeH / 2, (eyeW / 2) - scale, 0, Math.PI * 2);
          ctx.fill();

          // Inner 3x3 circle
          ctx.fillStyle = eyeColor || fgColor;
          ctx.beginPath();
          ctx.arc(eyeX + eyeW / 2, eyeY + eyeH / 2, 1.5 * scale, 0, Math.PI * 2);
          ctx.fill();
        } else if (eyeStyle === 'rounded') {
          // Soft rounded outer ring
          const radiusOuter = scale * 2;
          ctx.beginPath();
          ctx.roundRect(eyeX, eyeY, eyeW, eyeH, radiusOuter);
          ctx.fill();

          ctx.fillStyle = bgColor;
          const radiusInner = scale * 1.2;
          ctx.beginPath();
          ctx.roundRect(eyeX + scale, eyeY + scale, eyeW - scale * 2, eyeH - scale * 2, radiusInner);
          ctx.fill();

          // Inner 3x3 rounded square
          ctx.fillStyle = eyeColor || fgColor;
          ctx.beginPath();
          ctx.roundRect(eyeX + scale * 2, eyeY + scale * 2, scale * 3, scale * 3, scale * 0.8);
          ctx.fill();
        } else {
          // Classic square
          ctx.fillRect(eyeX, eyeY, eyeW, eyeH);

          ctx.fillStyle = bgColor;
          ctx.fillRect(eyeX + scale, eyeY + scale, eyeW - scale * 2, eyeH - scale * 2);

          ctx.fillStyle = eyeColor || fgColor;
          ctx.fillRect(eyeX + scale * 2, eyeY + scale * 2, scale * 3, scale * 3);
        }
      };

      drawEye(0, 0); // Top-Left
      drawEye(0, moduleCount - 7); // Top-Right
      drawEye(moduleCount - 7, 0); // Bottom-Left

      // Draw Center Logo / Icon Badge
      if (hasLogo) {
        const logoPx = Math.round(exportSize * (logoSize / 100));
        const logoX = canvasWidth / 2 - logoPx / 2;
        const logoY = qrOffsetY + exportSize / 2 - logoPx / 2;
        const logoPadding = Math.round(logoPx * 0.18);

        // Logo background circle / pad
        ctx.fillStyle = bgColor;
        ctx.beginPath();
        ctx.arc(canvasWidth / 2, qrOffsetY + exportSize / 2, (logoPx / 2) + logoPadding, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = (eyeColor || fgColor) + '20';
        ctx.lineWidth = Math.max(1, Math.round(scale * 0.5));
        ctx.stroke();

        // Custom uploaded image or preset icon
        if (customLogoUrl) {
          const img = new Image();
          img.crossOrigin = 'anonymous';
          img.onload = () => {
            ctx.drawImage(img, logoX, logoY, logoPx, logoPx);
          };
          img.src = customLogoUrl;
        } else {
          // Draw preset icon badge
          const preset = LOGO_PRESETS.find((p) => p.id === selectedLogoPreset);
          if (preset) {
            ctx.fillStyle = preset.color || fgColor;
            ctx.beginPath();
            ctx.arc(canvasWidth / 2, qrOffsetY + exportSize / 2, logoPx / 2, 0, Math.PI * 2);
            ctx.fill();

            // Inner icon text or glyph
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = `bold ${Math.round(logoPx * 0.52)}px -apple-system, sans-serif`;
            ctx.fillText(preset.text || '✦', canvasWidth / 2, qrOffsetY + exportSize / 2);
          }
        }
      }
    } catch (err) {
      console.error('Failed to render QR Code:', err);
    }
  }, [
    getPayload, errorLevel, frame, frameCta, frameBg, frameTextColor,
    fgColor, bgColor, eyeColor, useGradient, gradientColors, isTransparentBg,
    dotStyle, eyeStyle, selectedLogoPreset, customLogoUrl, logoSize
  ]);

  // Trigger live render on state changes
  useEffect(() => {
    renderCanvas(canvasRef.current, 520);
  }, [renderCanvas]);

  // Handle custom logo image file upload
  const handleLogoUpload = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please upload an image file (PNG, JPG, SVG)');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      setCustomLogoUrl(e.target.result);
      setSelectedLogoPreset('custom');
      toast.success('Custom logo added to QR center');
    };
    reader.readAsDataURL(file);
  };

  // Download High-Resolution QR image
  const handleDownload = async (format = 'png') => {
    setDownloading(true);
    try {
      const size = parseInt(exportRes, 10) || 1024;
      const offscreenCanvas = document.createElement('canvas');
      await renderCanvas(offscreenCanvas, size);

      if (format === 'svg') {
        // Generate crisp vector SVG
        const payload = getPayload();
        const svgString = await QRCode.toString(payload, {
          type: 'svg',
          errorCorrectionLevel: errorLevel,
          color: {
            dark: fgColor,
            light: isTransparentBg ? '#00000000' : bgColor,
          },
        });
        const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
        const urlObj = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = urlObj;
        a.download = `unravler-qr-${contentType}-${Date.now()}.svg`;
        a.click();
        URL.revokeObjectURL(urlObj);
        toast.success('Vector SVG downloaded!');
      } else {
        // Export PNG / JPEG
        const mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png';
        offscreenCanvas.toBlob((blob) => {
          if (!blob) {
            toast.error('Failed to create image file');
            return;
          }
          const urlObj = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = urlObj;
          a.download = `unravler-qr-${contentType}-${Date.now()}.${format}`;
          a.click();
          URL.revokeObjectURL(urlObj);
          toast.success(`High-res ${format.toUpperCase()} (${size}×${size}px) downloaded!`);
        }, mimeType, 0.95);
      }
    } catch (err) {
      toast.error('Download failed: ' + (err.message || 'Unknown error'));
    } finally {
      setDownloading(false);
    }
  };

  // Copy QR Image directly to Clipboard
  const handleCopyClipboard = async () => {
    try {
      const offscreenCanvas = document.createElement('canvas');
      await renderCanvas(offscreenCanvas, 800);
      offscreenCanvas.toBlob(async (blob) => {
        if (!blob) return;
        try {
          await navigator.clipboard.write([
            new ClipboardItem({ 'image/png': blob })
          ]);
          setCopied(true);
          toast.success('QR Code image copied to clipboard!');
          setTimeout(() => setCopied(false), 2000);
        } catch {
          toast.error('Clipboard copy not permitted by browser. Try Download instead.');
        }
      });
    } catch (err) {
      toast.error('Could not copy image');
    }
  };

  // Open formatted print sheet
  const handlePrint = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    const win = window.open('', '_blank');
    win.document.write(`
      <html>
        <head>
          <title>Print QR Code — Unravler</title>
          <style>
            body { font-family: -apple-system, sans-serif; text-align: center; padding: 40px; }
            .card { display: inline-block; border: 2px dashed #e5e7eb; padding: 32px; border-radius: 24px; max-width: 420px; }
            img { max-width: 100%; height: auto; display: block; margin: 0 auto 16px; }
            h2 { font-size: 20px; color: #111827; margin: 0 0 8px; }
            p { font-size: 13px; color: #6b7280; margin: 0; word-break: break-all; }
          </style>
        </head>
        <body>
          <div class="card">
            <img src="${dataUrl}" />
            <h2>Scan with your phone camera</h2>
            <p>${getPayload()}</p>
          </div>
          <script>
            window.onload = () => { window.print(); window.close(); };
          </script>
        </body>
      </html>
    `);
    win.document.close();
  };

  // Attach to Unravler Post Composer
  const handleCreatePost = async () => {
    try {
      const payload = getPayload();
      navigate('/create-post', {
        state: {
          initialContent: `Scan our QR code to check this out: ${payload}\n\nGenerated with Unravler Social Tools 🚀`,
        },
      });
    } catch (err) {
      toast.error('Could not launch composer');
    }
  };

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
            <div className="w-8 h-8 rounded-lg bg-pink-50 border border-pink-100 flex items-center justify-center">
              <FaQrcode className="text-pink-600 text-base" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 leading-tight">QR Code Generator</h2>
              <p className="text-[11px] text-gray-500">Create custom branded QR codes for links, Wi-Fi, vCard, and multi-store downloads</p>
            </div>
          </div>
        </div>

        {/* Global Action Bar */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyClipboard}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-xl transition-all shadow-xs"
          >
            {copied ? <FaCheck className="text-green-600 text-xs" /> : <FaCopy className="text-xs" />}
            {copied ? 'Copied Image!' : 'Copy Image'}
          </button>
          <button
            onClick={handlePrint}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 rounded-xl transition-all shadow-xs"
          >
            <FaPrint className="text-xs" /> Print Flyer
          </button>
          <button
            onClick={() => handleDownload('png')}
            disabled={downloading}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 rounded-xl transition-all shadow-xs disabled:opacity-50"
          >
            <FaDownload className="text-xs" /> Download PNG
          </button>
        </div>
      </div>

      {/* Main Studio Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* ── Left Column: Config & Customization (7 Cols) ── */}
        <div className="lg:col-span-7 space-y-5">

          {/* Step 1: Content Type Switcher */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs">
            <h3 className="text-xs font-bold text-gray-900 mb-3 flex items-center gap-1.5">
              <span className="w-4 h-4 rounded-full bg-indigo-100 text-indigo-700 text-[10px] flex items-center justify-center font-bold">1</span>
              Choose QR Content Type
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {CONTENT_TYPES.map((ct) => {
                const Icon = ct.icon;
                const active = contentType === ct.id;
                return (
                  <button
                    key={ct.id}
                    onClick={() => setContentType(ct.id)}
                    className={`flex flex-col items-start p-2.5 rounded-xl border text-left transition-all ${
                      active
                        ? 'border-indigo-600 bg-indigo-50/50 shadow-xs'
                        : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}
                  >
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center mb-1.5 ${
                      active ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600'
                    }`}>
                      <Icon className="text-xs" />
                    </div>
                    <span className={`text-xs font-bold ${active ? 'text-indigo-900' : 'text-gray-800'}`}>
                      {ct.label}
                    </span>
                    <span className="text-[10px] text-gray-400 leading-tight mt-0.5 line-clamp-1">
                      {ct.desc}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Step 2: Content Input Form */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs">
            <h3 className="text-xs font-bold text-gray-900 mb-3 flex items-center gap-1.5">
              <span className="w-4 h-4 rounded-full bg-indigo-100 text-indigo-700 text-[10px] flex items-center justify-center font-bold">2</span>
              Enter Content Details
            </h3>

            {/* URL Mode */}
            {contentType === 'url' && (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Destination Web URL</label>
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://yourwebsite.com or short link"
                    className="w-full text-xs text-gray-900 border border-gray-200 rounded-xl px-3.5 py-2.5 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setUrl('https://www.unravler.com')}
                    className="text-[10px] text-indigo-600 font-semibold hover:underline"
                  >
                    + Use Main Website
                  </button>
                  <button
                    onClick={() => navigate('/short-links')}
                    className="text-[10px] text-gray-500 font-semibold hover:underline"
                  >
                    ↗ Pick from Short Links & UTM
                  </button>
                </div>
              </div>
            )}

            {/* Multi-Store App Download */}
            {contentType === 'app' && (
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Apple App Store URL</label>
                  <input
                    type="url"
                    value={appIos}
                    onChange={(e) => setAppIos(e.target.value)}
                    placeholder="https://apps.apple.com/app/..."
                    className="w-full text-xs text-gray-900 border border-gray-200 rounded-xl px-3.5 py-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Google Play Store URL</label>
                  <input
                    type="url"
                    value={appAndroid}
                    onChange={(e) => setAppAndroid(e.target.value)}
                    placeholder="https://play.google.com/store/apps/..."
                    className="w-full text-xs text-gray-900 border border-gray-200 rounded-xl px-3.5 py-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* Social Profile */}
            {contentType === 'social' && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {[
                    { id: 'instagram', label: 'Instagram', icon: SiInstagram },
                    { id: 'linkedin', label: 'LinkedIn', icon: SiLinkedin },
                    { id: 'x', label: 'X (Twitter)', icon: SiX },
                    { id: 'tiktok', label: 'TikTok', icon: SiTiktok },
                    { id: 'youtube', label: 'YouTube', icon: SiYoutube },
                    { id: 'whatsapp', label: 'WhatsApp', icon: SiWhatsapp },
                  ].map((p) => {
                    const Icon = p.icon;
                    return (
                      <button
                        key={p.id}
                        onClick={() => setSocialPlatform(p.id)}
                        className={`flex items-center gap-2 p-2 rounded-xl border text-xs font-semibold ${
                          socialPlatform === p.id ? 'border-indigo-600 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-700'
                        }`}
                      >
                        <Icon /> {p.label}
                      </button>
                    );
                  })}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    {socialPlatform === 'whatsapp' ? 'Phone Number with Country Code' : 'Username / Handle'}
                  </label>
                  <input
                    type="text"
                    value={socialHandle}
                    onChange={(e) => setSocialHandle(e.target.value)}
                    placeholder={socialPlatform === 'whatsapp' ? '+1234567890' : '@yourhandle'}
                    className="w-full text-xs text-gray-900 border border-gray-200 rounded-xl px-3.5 py-2.5 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* vCard Contact Card */}
            {contentType === 'vcard' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">First Name</label>
                  <input
                    type="text"
                    value={vcard.firstName}
                    onChange={(e) => setVcard({ ...vcard, firstName: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Last Name</label>
                  <input
                    type="text"
                    value={vcard.lastName}
                    onChange={(e) => setVcard({ ...vcard, lastName: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Company / Org</label>
                  <input
                    type="text"
                    value={vcard.org}
                    onChange={(e) => setVcard({ ...vcard, org: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Phone Number</label>
                  <input
                    type="text"
                    value={vcard.phone}
                    onChange={(e) => setVcard({ ...vcard, phone: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Email Address</label>
                  <input
                    type="email"
                    value={vcard.email}
                    onChange={(e) => setVcard({ ...vcard, email: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {/* Wi-Fi Network */}
            {contentType === 'wifi' && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-gray-700 mb-1">Network Name (SSID)</label>
                    <input
                      type="text"
                      value={wifi.ssid}
                      onChange={(e) => setWifi({ ...wifi, ssid: e.target.value })}
                      className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-semibold text-gray-700 mb-1">Wi-Fi Password</label>
                    <input
                      type="text"
                      value={wifi.password}
                      onChange={(e) => setWifi({ ...wifi, password: e.target.value })}
                      className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <label className="text-xs font-semibold text-gray-700">Security:</label>
                  {['WPA', 'WEP', 'nopass'].map((sec) => (
                    <label key={sec} className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer">
                      <input
                        type="radio"
                        name="encryption"
                        checked={wifi.encryption === sec}
                        onChange={() => setWifi({ ...wifi, encryption: sec })}
                      />
                      {sec === 'nopass' ? 'Open (No password)' : sec}
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Plain Text */}
            {contentType === 'text' && (
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Message or Promo Content</label>
                <textarea
                  rows={3}
                  value={plainText}
                  onChange={(e) => setPlainText(e.target.value)}
                  className="w-full text-xs border border-gray-200 rounded-xl p-2.5 focus:ring-2 focus:ring-indigo-500 focus:outline-none leading-relaxed"
                />
              </div>
            )}

            {/* Email */}
            {contentType === 'email' && (
              <div className="space-y-2.5">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Recipient Email</label>
                  <input
                    type="email"
                    value={emailData.to}
                    onChange={(e) => setEmailData({ ...emailData, to: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-700 mb-1">Subject Line</label>
                  <input
                    type="text"
                    value={emailData.subject}
                    onChange={(e) => setEmailData({ ...emailData, subject: e.target.value })}
                    className="w-full text-xs border border-gray-200 rounded-xl p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

          </div>

          {/* Step 3: Colors & Brand Styling */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
                <span className="w-4 h-4 rounded-full bg-indigo-100 text-indigo-700 text-[10px] flex items-center justify-center font-bold">3</span>
                Brand Colors & Geometry
              </h3>
              <label className="flex items-center gap-1.5 text-xs text-gray-600 font-semibold cursor-pointer">
                <input
                  type="checkbox"
                  checked={useGradient}
                  onChange={(e) => setUseGradient(e.target.checked)}
                  className="rounded text-indigo-600 focus:ring-0"
                />
                Use Gradient
              </label>
            </div>

            {/* Color Presets */}
            <div className="flex flex-wrap gap-1.5">
              {COLOR_PRESETS.map((cp, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    setFgColor(cp.fg);
                    setBgColor(cp.bg);
                    setEyeColor(cp.eye);
                    if (cp.gradient) {
                      setUseGradient(true);
                      setGradientColors(cp.gradient);
                    } else {
                      setUseGradient(false);
                    }
                  }}
                  className="px-2.5 py-1 text-[11px] font-semibold rounded-lg border border-gray-200 hover:border-gray-300 flex items-center gap-1.5 bg-white transition-all shadow-2xs"
                >
                  <span className="w-3 h-3 rounded-full border border-black/10" style={{ backgroundColor: cp.fg }} />
                  {cp.name}
                </button>
              ))}
            </div>

            {/* Individual Color Controls */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-[11px] font-semibold text-gray-600 mb-1">Foreground</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={fgColor}
                    onChange={(e) => setFgColor(e.target.value)}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-gray-200"
                  />
                  <span className="text-xs font-mono text-gray-700">{fgColor}</span>
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-600 mb-1">Background</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={bgColor}
                    disabled={isTransparentBg}
                    onChange={(e) => setBgColor(e.target.value)}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-gray-200 disabled:opacity-30"
                  />
                  <label className="flex items-center gap-1 text-[10px] text-gray-500 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isTransparentBg}
                      onChange={(e) => setIsTransparentBg(e.target.checked)}
                    />
                    Transparent
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-600 mb-1">Corner Eye Color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={eyeColor}
                    onChange={(e) => setEyeColor(e.target.value)}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-gray-200"
                  />
                  <span className="text-xs font-mono text-gray-700">{eyeColor}</span>
                </div>
              </div>
            </div>

            {/* Geometry / Shapes */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-[11px] font-semibold text-gray-700 mb-1.5">Module Dot Style</label>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: 'rounded', label: 'Rounded' },
                    { id: 'dots', label: 'Circular' },
                    { id: 'square', label: 'Square' },
                  ].map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setDotStyle(s.id)}
                      className={`py-1.5 text-xs font-semibold rounded-lg border transition-all ${
                        dotStyle === s.id ? 'border-indigo-600 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-600'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-700 mb-1.5">Corner Eye Style</label>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: 'rounded', label: 'Soft Edge' },
                    { id: 'circle', label: 'Circle' },
                    { id: 'square', label: 'Square' },
                  ].map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setEyeStyle(s.id)}
                      className={`py-1.5 text-xs font-semibold rounded-lg border transition-all ${
                        eyeStyle === s.id ? 'border-indigo-600 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-600'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Step 4: Logo & Frame CTA */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-xs space-y-4">
            <h3 className="text-xs font-bold text-gray-900 flex items-center gap-1.5">
              <span className="w-4 h-4 rounded-full bg-indigo-100 text-indigo-700 text-[10px] flex items-center justify-center font-bold">4</span>
              Logo & Call-To-Action Frame
            </h3>

            {/* Logo Presets & Upload */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-semibold text-gray-700">Center Logo Badge</label>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-xs text-indigo-600 font-bold hover:underline flex items-center gap-1"
                >
                  + Upload Custom Logo
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => handleLogoUpload(e.target.files?.[0])}
                />
              </div>

              <div className="flex flex-wrap gap-1.5">
                {LOGO_PRESETS.map((lp) => (
                  <button
                    key={lp.id}
                    onClick={() => {
                      setSelectedLogoPreset(lp.id);
                      setCustomLogoUrl(null);
                    }}
                    className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all ${
                      selectedLogoPreset === lp.id && !customLogoUrl
                        ? 'border-indigo-600 bg-indigo-50 text-indigo-900 shadow-2xs'
                        : 'border-gray-200 bg-white text-gray-700'
                    }`}
                  >
                    {lp.icon && <lp.icon style={{ color: lp.color }} />}
                    {lp.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Frame Selector */}
            <div className="pt-2 border-t border-gray-100">
              <label className="block text-[11px] font-semibold text-gray-700 mb-1.5">Frame Banner Template</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {FRAMES.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => {
                      setFrame(f.id);
                      if (f.cta) setFrameCta(f.cta);
                    }}
                    className={`p-2 rounded-xl border text-xs font-semibold text-left transition-all ${
                      frame === f.id ? 'border-indigo-600 bg-indigo-50 text-indigo-900' : 'border-gray-200 bg-white text-gray-700'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {frame !== 'none' && (
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-600 mb-1">Banner Text</label>
                    <input
                      type="text"
                      value={frameCta}
                      onChange={(e) => setFrameCta(e.target.value)}
                      className="w-full text-xs border border-gray-200 rounded-lg p-1.5 font-bold"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-600 mb-1">Frame Color</label>
                    <input
                      type="color"
                      value={frameBg}
                      onChange={(e) => setFrameBg(e.target.value)}
                      className="w-full h-7 rounded border border-gray-200 cursor-pointer"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-gray-600 mb-1">Text Color</label>
                    <input
                      type="color"
                      value={frameTextColor}
                      onChange={(e) => setFrameTextColor(e.target.value)}
                      className="w-full h-7 rounded border border-gray-200 cursor-pointer"
                    />
                  </div>
                </div>
              )}
            </div>

          </div>

        </div>

        {/* ── Right Column: Live Canvas Preview & Exporter (5 Cols) ── */}
        <div className="lg:col-span-5 space-y-4">

          {/* Main QR Preview Card */}
          <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm flex flex-col items-center justify-center sticky top-20">
            <div className="flex items-center justify-between w-full mb-4">
              <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                <FaQrcode className="text-indigo-600" /> Live High-Res Preview
              </span>
              <span className="text-[10px] font-bold text-green-600 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                100% Scannable (Level {errorLevel})
              </span>
            </div>

            {/* The Live Rendered Canvas */}
            <div className="p-4 bg-gray-50 border border-gray-200 rounded-2xl flex items-center justify-center shadow-inner max-w-full overflow-hidden">
              <canvas
                ref={canvasRef}
                className="max-w-[280px] w-full h-auto drop-shadow-md rounded-xl"
              />
            </div>

            {/* Quick Stats */}
            <p className="text-[11px] text-gray-500 text-center mt-3 truncate max-w-full font-mono">
              Payload: {getPayload()}
            </p>

            {/* Resolution Selector & Download Options */}
            <div className="w-full mt-5 pt-4 border-t border-gray-100 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">Export Resolution</span>
                <select
                  value={exportRes}
                  onChange={(e) => setExportRes(e.target.value)}
                  className="text-xs border border-gray-200 rounded-lg px-2.5 py-1 text-gray-800 bg-gray-50 font-semibold focus:outline-none"
                >
                  <option value="512">Standard (512×512px)</option>
                  <option value="1024">HD Screen (1024×1024px)</option>
                  <option value="2048">4K Ultra Print (2048×2048px)</option>
                </select>
              </div>

              {/* Download Buttons */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => handleDownload('png')}
                  disabled={downloading}
                  className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition-all shadow-xs disabled:opacity-50"
                >
                  <FaDownload className="text-xs" /> PNG Image
                </button>
                <button
                  onClick={() => handleDownload('svg')}
                  disabled={downloading}
                  className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-white hover:bg-gray-50 text-gray-800 border border-gray-200 rounded-xl text-xs font-bold transition-all shadow-xs disabled:opacity-50"
                >
                  <FaDownload className="text-xs" /> Vector SVG
                </button>
              </div>

              {/* Seamless Unravler Integration Action */}
              <button
                onClick={handleCreatePost}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 bg-gray-900 hover:bg-black text-white rounded-xl text-xs font-bold transition-all shadow-xs"
              >
                <FaPaperPlane className="text-[10px]" /> Post with QR in Unravler
              </button>
            </div>
          </div>

          {/* Quick Printing & Scanning Tips */}
          <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4 text-xs space-y-1.5">
            <h4 className="font-bold text-amber-900 flex items-center gap-1.5">
              💡 QR Best Practices
            </h4>
            <p className="text-amber-800 text-[11px] leading-relaxed">
              • High contrast between foreground and background ensures 100% instant phone scan speed.
            </p>
            <p className="text-amber-800 text-[11px] leading-relaxed">
              • SVG format is recommended for print banners, restaurant menus, stickers, and business cards.
            </p>
          </div>

        </div>

      </div>
    </div>
  );
}
