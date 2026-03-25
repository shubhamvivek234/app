/**
 * SocialTools — tools grid (image5) with inline sub-views
 * Grid Maker (images 6-7) and Carousel Splitter (images 9-11)
 * All processing is 100% client-side via Canvas API + JSZip
 */
import React, { useState, useRef, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import JSZip from 'jszip';
import { saveAs } from 'file-saver';
import { toast } from 'sonner';
import {
  FaThLarge, FaFilm, FaArrowLeft, FaDownload, FaUpload, FaRedo,
} from 'react-icons/fa';
import { SiInstagram, SiTiktok, SiYoutube, SiLinkedin } from 'react-icons/si';
import { MdGridOn, MdViewCarousel } from 'react-icons/md';

// ── Tools catalogue ───────────────────────────────────────────────────────────
const TOOLS = [
  {
    id: 'instagram-grid',
    icon: MdGridOn,
    iconColor: '#E1306C',
    iconBg: 'bg-pink-50',
    platform: SiInstagram,
    title: 'Instagram Grid Maker',
    description: 'Split any image into perfect Instagram grid posts. Upload one image and get individual pieces to create stunning grid effects.',
    tag: 'Try it free →',
    available: true,
  },
  {
    id: 'instagram-carousel',
    icon: MdViewCarousel,
    iconColor: '#E1306C',
    iconBg: 'bg-pink-50',
    platform: SiInstagram,
    title: 'Instagram Carousel Splitter',
    description: 'Split images into seamless Instagram carousel posts. Create swipeable panoramas that boost engagement.',
    tag: 'Try it free →',
    available: true,
  },
  {
    id: 'tiktok-username',
    icon: SiTiktok,
    iconColor: '#000000',
    iconBg: 'bg-gray-50',
    platform: SiTiktok,
    title: 'TikTok Username Checker',
    description: 'Check if your desired TikTok username is available. Find the perfect handle for your TikTok content creator or business account.',
    tag: 'Coming soon',
    available: false,
  },
  {
    id: 'tiktok-caption',
    icon: FaFilm,
    iconColor: '#000000',
    iconBg: 'bg-gray-50',
    platform: SiTiktok,
    title: 'TikTok Caption Generator',
    description: 'Generate engaging, viral-worthy TikTok captions with AI. Choose your tone and audience for perfectly crafted captions.',
    tag: 'Coming soon',
    available: false,
  },
  {
    id: 'linkedin-formatter',
    icon: SiLinkedin,
    iconColor: '#0A66C2',
    iconBg: 'bg-blue-50',
    platform: SiLinkedin,
    title: 'LinkedIn Text Formatter',
    description: 'Format LinkedIn posts with bold, italic, underlined text and more. Stand out with professional text formatting.',
    tag: 'Coming soon',
    available: false,
  },
  {
    id: 'youtube-title',
    icon: SiYoutube,
    iconColor: '#FF0000',
    iconBg: 'bg-red-50',
    platform: SiYoutube,
    title: 'YouTube Title Checker',
    description: 'Check title length, prevent truncation, and see how your title looks in YouTube feeds. Upload thumbnails for complete preview.',
    tag: 'Coming soon',
    available: false,
  },
  {
    id: 'youtube-tags',
    icon: SiYoutube,
    iconColor: '#FF0000',
    iconBg: 'bg-red-50',
    platform: SiYoutube,
    title: 'YouTube Tag Generator',
    description: 'Generate optimised YouTube tags with AI. Get relevant, SEO-friendly tags that boost video discoverability and rankings.',
    tag: 'Coming soon',
    available: false,
  },
  {
    id: 'instagram-handle',
    icon: SiInstagram,
    iconColor: '#E1306C',
    iconBg: 'bg-pink-50',
    platform: SiInstagram,
    title: 'Instagram Handle Checker',
    description: 'Check if your desired Instagram username is available. Find the perfect handle for your brand, business, or personal account.',
    tag: 'Coming soon',
    available: false,
  },
];

const GRID_SIZES = ['3×1', '3×2', '3×3', '3×4', '3×5', '3×6'];
const BG_COLORS = [
  { value: '#000000', label: 'Black' },
  { value: '#d1d5db', label: 'Light Gray' },
  { value: '#ffffff', label: 'White' },
  { value: '#d1fae5', label: 'Light Green' },
];
const CANVAS_W = 340;
const PIECE_ASPECT = 5 / 4; // 4:5 → height = width * 5/4
const DIMENSION_GUIDE = [
  { label: '3×1 Grid', ratio: '12:5 ratio', cols: 3, rows: 1 },
  { label: '3×2 Grid', ratio: '6:5 ratio',  cols: 3, rows: 2 },
  { label: '3×3 Grid', ratio: '4:5 ratio',  cols: 3, rows: 3 },
  { label: '3×4 Grid', ratio: '3:5 ratio',  cols: 3, rows: 4 },
  { label: '3×5 Grid', ratio: '12:25 ratio',cols: 3, rows: 5 },
  { label: '3×6 Grid', ratio: '2:5 ratio',  cols: 3, rows: 6 },
];
const CAROUSEL_DIMS = [
  { slides: 3, width: 1080, height: 1350, label: '3 slides' },
  { slides: 4, width: 1440, height: 1350, label: '4 slides' },
  { slides: 5, width: 1800, height: 1350, label: '5 slides' },
  { slides: 6, width: 2160, height: 1350, label: '6 slides' },
  { slides: 7, width: 2520, height: 1350, label: '7 slides' },
];

// ── Tools grid ────────────────────────────────────────────────────────────────
const ToolCard = ({ tool, onSelect }) => {
  const { icon: Icon, iconColor, iconBg, title, description, tag, available } = tool;
  return (
    <div
      onClick={() => available && onSelect(tool.id)}
      className={`rounded-2xl border-2 p-5 transition-all duration-200 ${
        available
          ? 'border-green-200 bg-white hover:border-green-400 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer'
          : 'border-gray-100 bg-gray-50/50 cursor-not-allowed opacity-70'
      }`}
    >
      <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center mb-3`}>
        <Icon style={{ color: iconColor }} className="text-xl" />
      </div>
      <h3 className="text-sm font-bold text-gray-900 mb-1.5">{title}</h3>
      <p className="text-xs text-gray-500 leading-relaxed mb-3">{description}</p>
      <span className={`text-xs font-semibold ${available ? 'text-green-600' : 'text-gray-400'}`}>
        {tag}
      </span>
    </div>
  );
};

// ── Instagram Grid Maker ──────────────────────────────────────────────────────
const EXTENDED_BG_COLORS = [
  { value: '#000000', label: 'Black' },
  { value: '#1a1a2e', label: 'Dark Navy' },
  { value: '#374151', label: 'Slate' },
  { value: '#d1d5db', label: 'Light Gray' },
  { value: '#f3f4f6', label: 'Off White' },
  { value: '#ffffff', label: 'White' },
  { value: '#fce7f3', label: 'Soft Pink' },
  { value: '#d1fae5', label: 'Mint' },
];

const InstagramGridMaker = ({ onBack }) => {
  const [image, setImage]           = useState(null);
  const [imageName, setImageName]   = useState('');
  const [gridSize, setGridSize]     = useState('3×3');
  const [bgColor, setBgColor]       = useState('#ffffff');
  const [offsetX, setOffsetX]       = useState(0);
  const [offsetY, setOffsetY]       = useState(0);
  const [scale, setScale]           = useState(1);
  const [scalePercent, setScalePercent] = useState(100);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart]   = useState({ x: 0, y: 0 });
  const [hoveredTile, setHoveredTile] = useState(null);
  const [tiles, setTiles]           = useState([]);
  const [downloading, setDownloading] = useState(false);
  const [showDimensions, setShowDimensions] = useState(false);

  const posCanvasRef = useRef(null);
  const fileInputRef = useRef(null);

  const cols      = 3;
  const rows      = parseInt(gridSize.split('×')[1]);
  const totalTiles = cols * rows;
  const CANVAS_H  = Math.round(CANVAS_W * rows * PIECE_ASPECT / cols);

  // ── Load image ───────────────────────────────────────────────────────────────
  const loadImage = (file) => {
    if (!file || !file.type.startsWith('image/')) { toast.error('Please upload an image file'); return; }
    setImageName(file.name.replace(/\.[^/.]+$/, ''));
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        setImage(img);
        // Cover-fit initial position
        const s = Math.max(CANVAS_W / img.width, CANVAS_H / img.height);
        setScale(s);
        setScalePercent(Math.round(s * 100));
        setOffsetX((CANVAS_W - img.width * s) / 2);
        setOffsetY((CANVAS_H - img.height * s) / 2);
        setTiles([]);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  };

  // Reset to cover-fit when grid changes
  useEffect(() => {
    if (!image) return;
    const canvasH = Math.round(CANVAS_W * rows * PIECE_ASPECT / cols);
    const s = Math.max(CANVAS_W / image.width, canvasH / image.height);
    setScale(s);
    setScalePercent(Math.round(s * 100));
    setOffsetX((CANVAS_W - image.width * s) / 2);
    setOffsetY((canvasH - image.height * s) / 2);
    setTiles([]);
  }, [gridSize]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReset = () => {
    if (!image) return;
    const s = Math.max(CANVAS_W / image.width, CANVAS_H / image.height);
    setScale(s); setScalePercent(Math.round(s * 100));
    setOffsetX((CANVAS_W - image.width * s) / 2);
    setOffsetY((CANVAS_H - image.height * s) / 2);
  };

  // ── Draw position canvas ──────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = posCanvasRef.current;
    if (!canvas) return;
    canvas.width  = CANVAS_W;
    canvas.height = CANVAS_H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
    if (image) ctx.drawImage(image, offsetX, offsetY, image.width * scale, image.height * scale);
    // Dashed grid overlay
    ctx.setLineDash([5, 3]);
    ctx.strokeStyle = 'rgba(255,255,255,0.80)';
    ctx.lineWidth = 1.5;
    for (let c = 1; c < cols; c++) {
      const x = (c / cols) * CANVAS_W;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let r = 1; r < rows; r++) {
      const y = (r / rows) * CANVAS_H;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }
  }, [image, offsetX, offsetY, scale, bgColor, cols, rows, CANVAS_H]);

  // ── Live tile previews (debounced) ────────────────────────────────────────────
  useEffect(() => {
    if (!image) return;
    const timer = setTimeout(() => {
      const canvas = posCanvasRef.current;
      if (!canvas) return;
      const tileW = CANVAS_W / cols;
      const tileH = CANVAS_H / rows;
      const OUT_W = 300;
      const OUT_H = Math.round(OUT_W * PIECE_ASPECT);
      const newTiles = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const tc = document.createElement('canvas');
          tc.width = OUT_W; tc.height = OUT_H;
          tc.getContext('2d').drawImage(canvas, c * tileW, r * tileH, tileW, tileH, 0, 0, OUT_W, OUT_H);
          newTiles.push(tc.toDataURL('image/jpeg', 0.82));
        }
      }
      setTiles(newTiles);
    }, 90);
    return () => clearTimeout(timer);
  }, [image, offsetX, offsetY, scale, bgColor, cols, rows, CANVAS_H]);

  // ── Scale slider ──────────────────────────────────────────────────────────────
  const handleScaleChange = (e) => {
    const pct = parseInt(e.target.value);
    setScalePercent(pct);
    const newScale = pct / 100;
    // Zoom relative to canvas center
    const cx = CANVAS_W / 2, cy = CANVAS_H / 2;
    const imgCX = (cx - offsetX) / scale;
    const imgCY = (cy - offsetY) / scale;
    setScale(newScale);
    setOffsetX(cx - imgCX * newScale);
    setOffsetY(cy - imgCY * newScale);
  };

  // ── Drag ──────────────────────────────────────────────────────────────────────
  const handleMouseDown = (e) => {
    if (!image) return;
    e.preventDefault();
    const rect = posCanvasRef.current.getBoundingClientRect();
    const sx = CANVAS_W / rect.width;
    const sy = CANVAS_H / rect.height;
    setIsDragging(true);
    setDragStart({ x: (e.clientX - rect.left) * sx - offsetX, y: (e.clientY - rect.top) * sy - offsetY });
  };
  const handleMouseMove = (e) => {
    if (!isDragging || !image) return;
    const rect = posCanvasRef.current.getBoundingClientRect();
    const sx = CANVAS_W / rect.width;
    const sy = CANVAS_H / rect.height;
    setOffsetX((e.clientX - rect.left) * sx - dragStart.x);
    setOffsetY((e.clientY - rect.top) * sy - dragStart.y);
  };
  const handleMouseUp = () => setIsDragging(false);
  const handleTouchStart = (e) => { const t = e.touches[0]; handleMouseDown({ clientX: t.clientX, clientY: t.clientY, preventDefault: () => e.preventDefault() }); };
  const handleTouchMove  = (e) => { const t = e.touches[0]; handleMouseMove({ clientX: t.clientX, clientY: t.clientY }); };

  // ── Download helpers ──────────────────────────────────────────────────────────
  const buildTileCanvas = (r, c) => {
    const OUT_W = 1080, OUT_H = 1350;
    const tc = document.createElement('canvas');
    tc.width = OUT_W; tc.height = OUT_H;
    const ctx = tc.getContext('2d');
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, OUT_W, OUT_H);
    const tileW = CANVAS_W / cols;
    const tileH = CANVAS_H / rows;
    const sx = OUT_W / tileW, sy = OUT_H / tileH;
    ctx.drawImage(image, (offsetX - c * tileW) * sx, (offsetY - r * tileH) * sy, image.width * scale * sx, image.height * scale * sy);
    return tc;
  };

  const downloadTile = (index) => {
    const r = Math.floor(index / cols), c = index % cols;
    const tc = buildTileCanvas(r, c);
    const link = document.createElement('a');
    link.download = `${imageName || 'grid'}_${index + 1}.jpg`;
    link.href = tc.toDataURL('image/jpeg', 0.95);
    link.click();
  };

  const downloadAll = async () => {
    if (!image) return;
    setDownloading(true);
    try {
      const zip = new JSZip();
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const tc = buildTileCanvas(r, c);
          const num = r * cols + c + 1;
          zip.file(`${imageName || 'grid'}_${num}.jpg`, tc.toDataURL('image/jpeg', 0.95).split(',')[1], { base64: true });
        }
      }
      const content = await zip.generateAsync({ type: 'blob' });
      saveAs(content, `${imageName || 'instagram'}_grid_${gridSize.replace('×', 'x')}.zip`);
      toast.success(`${totalTiles} grid images downloaded`);
    } catch {
      toast.error('Failed to generate grid. Try a smaller image.');
    } finally {
      setDownloading(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto">

      {/* Back + Header */}
      <div className="mb-6">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 mb-5 transition-colors group">
          <FaArrowLeft className="text-xs group-hover:-translate-x-0.5 transition-transform" /> Back to Tools
        </button>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-md">
            <MdGridOn className="text-white text-2xl" />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1 bg-pink-50 text-pink-600 text-[10px] font-bold px-2 py-0.5 rounded-full border border-pink-100">
                <SiInstagram className="text-[9px]" /> Instagram
              </span>
              <span className="inline-flex items-center gap-1 bg-green-50 text-green-700 text-[10px] font-bold px-2 py-0.5 rounded-full border border-green-100">
                Free · Client-side
              </span>
            </div>
            <h2 className="text-2xl font-bold text-gray-900">Instagram Grid Maker</h2>
            <p className="text-sm text-gray-500 mt-0.5">Split any image into perfect grid posts. Your images never leave your device.</p>
          </div>
        </div>
      </div>

      {/* Controls bar */}
      <div className="bg-white border border-gray-200 rounded-2xl p-4 mb-5 shadow-sm">
        <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
          {/* Grid size */}
          <div>
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Grid Size</p>
            <div className="flex items-center gap-1.5 flex-wrap">
              {GRID_SIZES.map((size) => (
                <button key={size} onClick={() => setGridSize(size)}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                    gridSize === size
                      ? 'bg-gray-900 text-white border-gray-900 shadow-sm'
                      : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700'
                  }`}>
                  {size}
                </button>
              ))}
            </div>
          </div>

          {/* Vertical divider */}
          <div className="h-10 w-px bg-gray-100 self-end hidden sm:block" />

          {/* Background */}
          <div>
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Background</p>
            <div className="flex items-center gap-1.5 flex-wrap">
              {EXTENDED_BG_COLORS.map(({ value, label }) => (
                <button key={value} onClick={() => setBgColor(value)} title={label}
                  className={`w-6 h-6 rounded-full transition-all duration-150 ${bgColor === value ? 'ring-2 ring-offset-2 ring-green-500 scale-110' : 'hover:scale-110 hover:ring-2 hover:ring-offset-1 hover:ring-gray-300'}`}
                  style={{ background: value, border: value === '#ffffff' || value === '#f3f4f6' ? '1.5px solid #d1d5db' : 'none' }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {!image ? (
        /* ── Upload zone ── */
        <div
          className="border-2 border-dashed border-gray-200 rounded-2xl p-14 flex flex-col items-center justify-center gap-5 cursor-pointer hover:border-green-400 hover:bg-green-50/30 transition-all max-w-lg mx-auto group"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); loadImage(e.dataTransfer.files?.[0]); }}
        >
          <div className="w-16 h-16 rounded-2xl bg-gray-100 group-hover:bg-green-100 flex items-center justify-center transition-colors">
            <FaUpload className="text-2xl text-gray-400 group-hover:text-green-500 transition-colors" />
          </div>
          <div className="text-center">
            <p className="text-sm font-bold text-gray-700">Drop your image here</p>
            <p className="text-xs text-gray-400 mt-1">or click to browse files</p>
            <p className="text-xs text-gray-300 mt-0.5">JPG · PNG · WEBP · Any size</p>
          </div>
          <button className="px-6 py-2.5 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors shadow-sm">
            Choose Image
          </button>
        </div>
      ) : (
        /* ── Two-panel layout ── */
        <div className="grid grid-cols-2 gap-4">
          {/* LEFT: Position canvas */}
          <div>
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div>
                  <p className="text-xs font-bold text-gray-800">Position Image</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">Drag to reframe</p>
                </div>
                <button onClick={handleReset}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-2.5 py-1 transition-colors hover:border-gray-300">
                  <FaRedo className="text-[9px]" /> Reset
                </button>
              </div>

              <div className="relative select-none">
                <canvas
                  ref={posCanvasRef}
                  className="w-full block"
                  style={{ cursor: isDragging ? 'grabbing' : 'grab', touchAction: 'none' }}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseUp}
                  onTouchStart={handleTouchStart}
                  onTouchMove={handleTouchMove}
                  onTouchEnd={handleMouseUp}
                />
                <div className="absolute top-2 left-2 bg-black/50 backdrop-blur-sm text-white text-[9px] font-medium px-2 py-1 rounded-lg pointer-events-none flex items-center gap-1">
                  <span>⟵</span> Drag to position
                </div>
              </div>

              {/* Scale slider */}
              <div className="px-4 py-3 border-t border-gray-100">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[10px] font-semibold text-gray-500">Zoom</span>
                  <span className="text-[10px] font-bold text-gray-700 tabular-nums bg-gray-100 px-2 py-0.5 rounded-md">{scalePercent}%</span>
                </div>
                <input type="range" min="10" max="300" value={scalePercent} onChange={handleScaleChange}
                  className="w-full h-1.5 appearance-none bg-gray-200 rounded-full cursor-pointer"
                  style={{ accentColor: '#22c55e' }}
                />
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={downloadAll}
                disabled={downloading}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-green-500 hover:bg-green-600 active:bg-green-700 text-white text-sm font-bold rounded-xl transition-colors disabled:opacity-60 shadow-sm"
              >
                <FaDownload className="text-xs" />
                {downloading ? 'Generating…' : `Download ${gridSize}`}
              </button>
              <button
                onClick={() => { setImage(null); setImageName(''); setTiles([]); }}
                className="px-4 py-2.5 text-sm font-medium text-gray-500 border border-gray-200 rounded-xl hover:bg-gray-50 hover:text-gray-700 transition-colors"
              >
                New
              </button>
            </div>
          </div>

          {/* RIGHT: Grid preview */}
          <div>
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div>
                  <p className="text-xs font-bold text-gray-800">{gridSize} Preview</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">4:5 ratio · tap tile to save</p>
                </div>
                <button
                  onClick={downloadAll}
                  disabled={downloading || !tiles.length}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50 shadow-sm"
                >
                  <FaDownload className="text-[9px]" />
                  {downloading ? 'Wait…' : 'All'}
                </button>
              </div>

              <div className="p-2.5">
                <div
                  className="rounded-xl overflow-hidden"
                  style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: '2px', background: '#e5e7eb' }}
                >
                  {Array.from({ length: totalTiles }).map((_, i) => (
                    <div key={i}
                      className="relative group cursor-pointer"
                      style={{ aspectRatio: '4/5', overflow: 'hidden', background: bgColor }}
                      onMouseEnter={() => setHoveredTile(i)}
                      onMouseLeave={() => setHoveredTile(null)}
                      onClick={() => tiles[i] && downloadTile(i)}
                    >
                      {tiles[i] ? (
                        <img src={tiles[i]} alt={`tile ${i + 1}`} className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <div className="w-3 h-3 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
                        </div>
                      )}
                      {/* Tile number — always visible, subtle */}
                      <div className="absolute top-1 left-1 bg-black/30 text-white text-[8px] font-bold w-4 h-4 rounded-md flex items-center justify-center pointer-events-none">
                        {i + 1}
                      </div>
                      {/* Hover overlay */}
                      <div className={`absolute inset-0 bg-black/55 flex flex-col items-center justify-center transition-opacity duration-150 ${hoveredTile === i ? 'opacity-100' : 'opacity-0'}`}>
                        <FaDownload className="text-white text-sm mb-1" />
                        <span className="text-white text-[9px] font-bold">Save #{i + 1}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="px-4 pb-3 text-center">
                <p className="text-[10px] text-gray-400">Post in order 1 → {totalTiles} for grid effect</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { loadImage(e.target.files?.[0]); e.target.value = ''; }} />

      {/* Recommended Dimensions (collapsible) */}
      <div className="mt-8 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
        <button
          onClick={() => setShowDimensions(!showDimensions)}
          className="w-full flex items-center justify-between px-5 py-4 text-sm font-bold text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <span className="w-7 h-7 bg-gray-100 rounded-xl flex items-center justify-center text-sm">✂</span>
            <span>Recommended Dimensions</span>
          </div>
          <span className="text-gray-400 text-lg font-light">{showDimensions ? '−' : '+'}</span>
        </button>

        {showDimensions && (
          <div className="px-5 pb-5 border-t border-gray-100">
            <p className="text-xs text-gray-500 mt-4 mb-5">
              Recommended aspect ratios for Instagram grid posts. Each individual piece maintains the 4:5 aspect ratio.
            </p>
            <div className="grid grid-cols-3 gap-3 mb-5">
              {DIMENSION_GUIDE.map(({ label, ratio, cols: dc, rows: dr }) => (
                <div key={label} className="text-center bg-gray-50 border border-gray-100 rounded-xl p-4">
                  <div style={{ display: 'grid', gridTemplateColumns: `repeat(${dc}, 1fr)`, gap: '2px', width: 54, margin: '0 auto 10px' }}>
                    {Array.from({ length: dc * dr }).map((_, i) => (
                      <div key={i} style={{ background: '#d1d5db', borderRadius: 2, aspectRatio: '4/5' }} />
                    ))}
                  </div>
                  <p className="text-xs font-bold text-gray-700">{label}</p>
                  <p className="text-[10px] text-gray-400 mt-0.5">{ratio}</p>
                </div>
              ))}
            </div>
            <div className="bg-gray-50 rounded-xl border border-gray-100 p-4">
              <p className="text-xs font-bold text-gray-700 mb-2.5">Notes</p>
              <div className="space-y-1.5">
                {[
                  'Each piece maintains 4:5 — the Instagram standard aspect ratio',
                  'Use any resolution that matches these ratios (e.g., 1200×1500px for 4:5)',
                  'Keep important content away from split lines',
                  'Higher resolution = better quality when split',
                ].map((note, i) => (
                  <p key={i} className="text-[11px] text-gray-500 flex items-start gap-2">
                    <span className="text-gray-300 mt-0.5">›</span>{note}
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* How It Works */}
      <div className="mt-10">
        <div className="text-center mb-7">
          <h3 className="text-xl font-bold text-gray-900">How It Works</h3>
          <p className="text-sm text-gray-400 mt-1">Three simple steps to your perfect Instagram grid</p>
        </div>
        <div className="grid grid-cols-3 gap-4 relative">
          {/* Connector */}
          <div className="absolute top-10 left-[calc(33%+1rem)] right-[calc(33%+1rem)] h-px bg-gray-200 hidden md:block pointer-events-none" />
          {[
            { step: '01', emoji: '📤', title: 'Upload your image', desc: 'Upload any high-quality image — product photo, landscape, or artwork. JPG, PNG, WEBP supported.' },
            { step: '02', emoji: '🎯', title: 'Choose grid & position', desc: 'Select your grid layout, drag to reframe, and adjust zoom until your image looks perfect.' },
            { step: '03', emoji: '✨', title: 'Download & post', desc: 'Download all pieces as a ZIP and post them in sequence to create a stunning grid on your profile.' },
          ].map(({ step, emoji, title, desc }) => (
            <div key={step} className="bg-white border border-gray-200 rounded-2xl p-5 text-center shadow-sm relative z-10 hover:border-gray-300 hover:shadow-md transition-all">
              <div className="w-9 h-9 bg-gray-900 text-white text-xs font-bold rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
                {step}
              </div>
              <div className="text-2xl mb-3">{emoji}</div>
              <h4 className="text-xs font-bold text-gray-900 mb-2">{title}</h4>
              <p className="text-[11px] text-gray-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pro Tips */}
      <div className="mt-6 mb-10 bg-white border border-gray-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 bg-amber-50 border border-amber-100 rounded-xl flex items-center justify-center text-lg">💡</div>
          <div>
            <h3 className="text-sm font-bold text-gray-900">Pro Tips</h3>
            <p className="text-[10px] text-gray-400">Get the most out of your Instagram grid</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
          {[
            'Use 4:5 aspect ratio for best Instagram compatibility',
            'Use high-resolution images (at least 1080px width)',
            'Keep important content away from split lines',
            "Consider your feed's overall aesthetic and color palette",
            'Post consistently to maintain the grid effect over time',
            'Preview your grid before committing to post',
            'Test different background colors for best contrast',
            'Choose backgrounds that complement your image tones',
          ].map((tip, i) => (
            <div key={i} className="flex items-start gap-2.5 py-2 px-3 rounded-xl hover:bg-gray-50 transition-colors cursor-default">
              <span className="w-5 h-5 bg-green-100 text-green-700 text-[9px] font-bold rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">{i + 1}</span>
              <span className="text-xs text-gray-600 leading-relaxed">{tip}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
};

// ── Instagram Carousel Splitter ───────────────────────────────────────────────
const InstagramCarouselSplitter = ({ onBack }) => {
  const [image, setImage] = useState(null);
  const [imageName, setImageName] = useState('');
  const [numSlides, setNumSlides] = useState(3);
  const [downloading, setDownloading] = useState(false);
  const fileInputRef = useRef(null);

  const idealDim = CAROUSEL_DIMS.find((d) => d.slides === numSlides) || CAROUSEL_DIMS[0];

  const loadImage = (file) => {
    if (!file || !file.type.startsWith('image/')) {
      toast.error('Please upload an image file');
      return;
    }
    setImageName(file.name.replace(/\.[^/.]+$/, ''));
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => setImage(img);
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  };

  const downloadCarousel = async () => {
    if (!image) return;
    setDownloading(true);
    try {
      const zip = new JSZip();
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      const pieceW = Math.floor(image.width / numSlides);
      const pieceH = image.height;
      canvas.width = pieceW;
      canvas.height = pieceH;

      for (let i = 0; i < numSlides; i++) {
        ctx.clearRect(0, 0, pieceW, pieceH);
        ctx.drawImage(image, i * pieceW, 0, pieceW, pieceH, 0, 0, pieceW, pieceH);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
        zip.file(`${imageName || 'carousel'}_slide_${i + 1}.jpg`, dataUrl.split(',')[1], { base64: true });
      }

      const content = await zip.generateAsync({ type: 'blob' });
      saveAs(content, `${imageName || 'carousel'}_${numSlides}slides.zip`);
      toast.success(`${numSlides} carousel slides downloaded`);
    } catch {
      toast.error('Failed to generate carousel. Try a smaller image.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      {/* Sub-page header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
        >
          <FaArrowLeft />
        </button>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Instagram Carousel Splitter</h2>
          <p className="text-xs text-gray-500 mt-0.5">Split images into seamless Instagram carousel posts. Create stunning swipeable panoramas.</p>
        </div>
      </div>

      {!image ? (
        <div>
          {/* Upload zone */}
          <div
            className="border-2 border-dashed border-gray-200 rounded-2xl p-14 flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-green-400 hover:bg-green-50/30 transition-colors max-w-lg mx-auto"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); loadImage(e.dataTransfer.files?.[0]); }}
          >
            <FaUpload className="text-4xl text-gray-300" />
            <div className="text-center">
              <p className="text-sm font-semibold text-gray-600">Drop your image here</p>
              <p className="text-xs text-gray-400 mt-1">or click to browse</p>
              <p className="text-xs text-gray-400 mt-0.5">Supports JPG, PNG, WEBP</p>
            </div>
            <button className="px-5 py-2 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors">
              Choose Image
            </button>
          </div>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
            onChange={(e) => { loadImage(e.target.files?.[0]); e.target.value = ''; }} />

          {/* Recommended dimensions */}
          <div className="mt-8">
            <p className="text-xs font-semibold text-gray-500 text-center mb-4">
              For best results, use these dimensions:
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              {CAROUSEL_DIMS.map((d) => (
                <div key={d.slides} className="text-center bg-white rounded-xl border border-gray-200 px-4 py-3 min-w-[100px]">
                  <div className="flex gap-0.5 justify-center mb-2">
                    {Array.from({ length: d.slides }).map((_, i) => (
                      <div key={i} className="bg-green-400 rounded-sm" style={{ width: 10, height: 18 }} />
                    ))}
                  </div>
                  <p className="text-[10px] font-bold text-gray-700">{d.label}</p>
                  <p className="text-[10px] text-gray-400 font-mono">{d.width} × {d.height}px</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div>
          {/* Configure carousel */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm mb-6">
            <h3 className="text-sm font-bold text-gray-800 mb-4">Configure Your Carousel</h3>

            {/* Preview */}
            <div className="rounded-xl overflow-hidden border border-gray-200 mb-5 relative"
              style={{ display: 'flex', gap: '2px', background: '#e5e7eb' }}>
              {Array.from({ length: numSlides }).map((_, i) => (
                <div key={i} className="flex-1 relative overflow-hidden" style={{ paddingBottom: `${100 / numSlides}%` }}>
                  <img
                    src={image.src}
                    alt=""
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{ objectPosition: `${(i / (numSlides - 1)) * 100}% center` }}
                  />
                  <div className="absolute inset-0 flex items-end justify-center pb-1">
                    <span className="text-white text-xs font-bold drop-shadow">{i + 1}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Slide count picker */}
            <div className="mb-4">
              <label className="text-xs font-semibold text-gray-600 block mb-2">Number of Slides</label>
              <div className="flex gap-2">
                {[2, 3, 4, 5, 6, 7].map((n) => (
                  <button
                    key={n}
                    onClick={() => setNumSlides(n)}
                    className={`w-9 h-9 rounded-lg text-xs font-bold border transition-all ${
                      numSlides === n
                        ? 'bg-green-500 text-white border-green-500'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-green-400'
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* Ideal dimensions */}
            <div className="bg-gray-50 rounded-xl border border-gray-200 px-4 py-3 mb-5 text-xs text-gray-600">
              <p className="font-semibold text-gray-700 mb-1">Ideal dimensions to openness in slides carousel</p>
              <p className="font-mono text-base text-gray-800 font-bold">
                {idealDim.width} × {idealDim.height}px
              </p>
              <div className="flex gap-1 mt-2">
                {Array.from({ length: numSlides }).map((_, i) => (
                  <div key={i} className="bg-green-400 rounded-sm" style={{ width: 14, height: 22 }} />
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <button
                onClick={() => { setImage(null); setImageName(''); }}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                <FaRedo className="inline mr-1.5" />New Image
              </button>
              <button
                onClick={downloadCarousel}
                disabled={downloading}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors disabled:opacity-50 shadow"
              >
                <FaDownload />
                {downloading ? 'Generating…' : `Split into ${numSlides} Slides`}
              </button>
            </div>
          </div>
        </div>
      )}
      <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { loadImage(e.target.files?.[0]); e.target.value = ''; }} />

      {/* How it works */}
      <div className="mt-8 pt-8 border-t border-gray-100">
        <h3 className="text-sm font-bold text-gray-800 text-center mb-6">How It Works</h3>
        <div className="grid grid-cols-3 gap-6">
          {[
            { icon: FaUpload, title: 'Upload your image', desc: 'Upload your wide panoramic image. High resolution images provide better quality for each slide.' },
            { icon: MdViewCarousel, title: 'Choose slide count', desc: 'Select how many slides you want (2–7). Use the recommended dimensions for perfect Instagram proportions.' },
            { icon: FaDownload, title: 'Download & post', desc: 'Download all slides as a ZIP and upload them to Instagram as a carousel. Each slide connects seamlessly.' },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="text-center">
              <div className="w-12 h-12 rounded-2xl bg-green-100 flex items-center justify-center mx-auto mb-3">
                <Icon className="text-green-600 text-xl" />
              </div>
              <h4 className="text-sm font-bold text-gray-800 mb-1.5">{title}</h4>
              <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ── Main SocialTools page ─────────────────────────────────────────────────────
const SocialTools = () => {
  const [activeTool, setActiveTool] = useState(null);

  const renderTool = () => {
    if (activeTool === 'instagram-grid') return <InstagramGridMaker onBack={() => setActiveTool(null)} />;
    if (activeTool === 'instagram-carousel') return <InstagramCarouselSplitter onBack={() => setActiveTool(null)} />;
    return null;
  };

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto pb-12">
        {activeTool ? (
          renderTool()
        ) : (
          <>
            {/* Header */}
            <div className="text-center mb-10">
              <h1 className="text-3xl font-extrabold text-gray-900 mb-2">
                Free <span className="text-green-500">Social Media</span> Tools
              </h1>
              <p className="text-sm text-gray-500 max-w-md mx-auto">
                Professional-grade tools to supercharge your social media content creation.
                All free, all client-side — your images never leave your device.
              </p>
            </div>

            {/* Tools grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {TOOLS.map((tool) => (
                <ToolCard key={tool.id} tool={tool} onSelect={setActiveTool} />
              ))}
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
};

export default SocialTools;
