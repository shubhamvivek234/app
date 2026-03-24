/**
 * SocialTools — tools grid (image5) with inline sub-views
 * Grid Maker (images 6-7) and Carousel Splitter (images 9-11)
 * All processing is 100% client-side via Canvas API + JSZip
 */
import React, { useState, useRef } from 'react';
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
const InstagramGridMaker = ({ onBack }) => {
  const [image, setImage] = useState(null);
  const [imageName, setImageName] = useState('');
  const [gridSize, setGridSize] = useState('3×3');
  const [downloading, setDownloading] = useState(false);
  const fileInputRef = useRef(null);

  const cols = 3;
  const rows = parseInt(gridSize.split('×')[1]);
  const totalTiles = cols * rows;

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

  const downloadGrid = async () => {
    if (!image) return;
    setDownloading(true);
    try {
      const zip = new JSZip();
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');

      // Crop source to cols:rows ratio
      const srcAspect = cols / rows;
      const imgAspect = image.width / image.height;
      let srcX = 0, srcY = 0, srcW = image.width, srcH = image.height;
      if (imgAspect > srcAspect) {
        srcW = Math.floor(image.height * srcAspect);
        srcX = Math.floor((image.width - srcW) / 2);
      } else {
        srcH = Math.floor(image.width / srcAspect);
        srcY = Math.floor((image.height - srcH) / 2);
      }

      const pieceW = Math.floor(srcW / cols);
      const pieceH = Math.floor(srcH / rows);
      canvas.width = pieceW;
      canvas.height = pieceH;

      let counter = 1;
      // Instagram grid reads right-to-left bottom-up for display,
      // but we number posts for upload order: top-right → top-left → ...
      for (let r = 0; r < rows; r++) {
        for (let c = cols - 1; c >= 0; c--) {
          ctx.clearRect(0, 0, pieceW, pieceH);
          ctx.drawImage(image, srcX + c * pieceW, srcY + r * pieceH, pieceW, pieceH, 0, 0, pieceW, pieceH);
          const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
          zip.file(`${imageName || 'grid'}_${counter}.jpg`, dataUrl.split(',')[1], { base64: true });
          counter++;
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
          <h2 className="text-xl font-bold text-gray-900">Instagram Grid Maker</h2>
          <p className="text-xs text-gray-500 mt-0.5">Split any image into Instagram grid posts. Create stunning grid effects.</p>
        </div>
      </div>

      {/* Grid size selector */}
      <div className="flex items-center gap-3 mb-6">
        <span className="text-xs font-semibold text-gray-500 mr-1">Grid size:</span>
        {GRID_SIZES.map((size) => (
          <button
            key={size}
            onClick={() => setGridSize(size)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all ${
              gridSize === size
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            }`}
          >
            {size}
          </button>
        ))}
      </div>

      <div className={`grid gap-6 ${image ? 'grid-cols-2' : 'grid-cols-1 max-w-xl'}`}>
        {/* Upload / Position area */}
        <div>
          {!image ? (
            <div
              className="border-2 border-dashed border-gray-200 rounded-2xl p-14 flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-green-400 hover:bg-green-50/30 transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); loadImage(e.dataTransfer.files?.[0]); }}
            >
              <FaUpload className="text-4xl text-gray-300" />
              <div className="text-center">
                <p className="text-sm font-semibold text-gray-600">Upload Image</p>
                <p className="text-xs text-gray-400 mt-1">
                  Choose an image to split into {gridSize} ({totalTiles} images)
                </p>
                <p className="text-xs text-gray-400 mt-0.5">JPG, PNG, WEBP</p>
              </div>
              <button className="mt-2 px-5 py-2 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors">
                Choose File
              </button>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-gray-600">Position Your Image</p>
                <button
                  onClick={() => { setImage(null); setImageName(''); }}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors"
                >
                  <FaRedo className="text-[10px]" /> New Image
                </button>
              </div>
              <div className="rounded-xl overflow-hidden border border-gray-200 relative aspect-square bg-gray-100">
                <img src={image.src} alt="preview" className="w-full h-full object-cover" />
              </div>
              <p className="text-xs text-gray-400 font-mono mt-2">
                Original: {image.width}×{image.height}px
              </p>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => { loadImage(e.target.files?.[0]); e.target.value = ''; }}
          />
        </div>

        {/* Preview grid */}
        {image && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-600">{gridSize} Grid Preview ({totalTiles} images)</p>
              <button
                onClick={downloadGrid}
                disabled={downloading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50 shadow-sm"
              >
                <FaDownload className="text-[10px]" />
                {downloading ? 'Generating…' : 'Download All'}
              </button>
            </div>

            <div
              className="rounded-xl overflow-hidden border border-gray-200 relative"
              style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: '2px', background: '#e5e7eb' }}
            >
              {Array.from({ length: totalTiles }).map((_, i) => {
                const r = Math.floor(i / cols);
                const c = i % cols;
                return (
                  <div key={i} className="relative aspect-square bg-gray-100 overflow-hidden">
                    <img
                      src={image.src}
                      alt=""
                      className="absolute"
                      style={{
                        width: `${cols * 100}%`,
                        height: `${rows * 100}%`,
                        left: `-${c * 100}%`,
                        top: `-${r * 100}%`,
                        objectFit: 'cover',
                      }}
                    />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-white text-base font-bold drop-shadow-lg opacity-80">{i + 1}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            <p className="text-[11px] text-gray-400 mt-2 text-center">
              Click any image to download. Numbers show upload order (1 = post first).
            </p>
          </div>
        )}
      </div>

      {/* How it works */}
      <div className="mt-12 pt-8 border-t border-gray-100">
        <h3 className="text-sm font-bold text-gray-800 text-center mb-6">How It Works</h3>
        <div className="grid grid-cols-3 gap-6">
          {[
            { icon: FaUpload, title: 'Upload your image', desc: 'Upload your high-quality image — whether it\'s a product photo, landscape, or artwork. We support all major image formats.' },
            { icon: MdGridOn, title: 'Choose grid size', desc: 'Select your desired Instagram grid (3×1 through 3×6). We\'ll split it perfectly, optimized for 1:1 carousel appearance.' },
            { icon: FaDownload, title: 'Download & post', desc: 'Download all grid pieces as a ZIP file, numbered for upload order. Post them to Instagram as a carousel to reveal the full image.' },
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
