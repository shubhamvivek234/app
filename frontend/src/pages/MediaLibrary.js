import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getMediaAssets, uploadMediaAsset, deleteMediaAsset } from '@/lib/api';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  FaImages, FaUpload, FaSearch, FaCopy, FaTrash, FaVideo, FaImage,
  FaTimes, FaCloudUploadAlt,
} from 'react-icons/fa';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const formatBytes = (bytes) => {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const isVideo = (contentType = '') => contentType.startsWith('video/');

const resolveUrl = (url) => {
  if (!url) return '';
  if (url.startsWith('http')) return url;
  return `${BACKEND_URL}${url}`;
};

// ── Asset card ────────────────────────────────────────────────────────────────
const AssetCard = ({ asset, onCopy, onDelete }) => {
  const url = resolveUrl(asset.url);
  const video = isVideo(asset.content_type);

  return (
    <div className="group relative bg-offwhite rounded-xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
      {/* Preview */}
      <div className="relative w-full aspect-square bg-offwhite border-b border-gray-100 overflow-hidden">
        {video ? (
          <video
            src={url}
            className="w-full h-full object-cover"
            muted
            preload="metadata"
          />
        ) : (
          <img
            src={url}
            alt={asset.filename}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={(e) => {
              e.target.style.display = 'none';
              e.target.nextSibling.style.display = 'flex';
            }}
          />
        )}
        {/* Fallback for broken images */}
        <div
          className="absolute inset-0 hidden items-center justify-center bg-offwhite text-gray-300"
        >
          {video ? <FaVideo className="text-3xl" /> : <FaImage className="text-3xl" />}
        </div>

        {/* Type badge */}
        <div className="absolute top-2 left-2">
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
            video ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
          }`}>
            {video ? 'Video' : 'Image'}
          </span>
        </div>

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
          <button
            onClick={() => onCopy(asset)}
            className="w-9 h-9 rounded-full bg-white/90 hover:bg-offwhite text-gray-700 flex items-center justify-center transition-colors shadow"
            title="Copy URL"
          >
            <FaCopy className="text-sm" />
          </button>
          <button
            onClick={() => onDelete(asset)}
            className="w-9 h-9 rounded-full bg-white/90 hover:bg-red-500 hover:text-white text-gray-700 flex items-center justify-center transition-colors shadow"
            title="Delete"
          >
            <FaTrash className="text-sm" />
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="px-3 py-2.5">
        <p className="text-xs font-medium text-gray-800 truncate" title={asset.filename}>
          {asset.filename}
        </p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-[10px] text-gray-400">{formatBytes(asset.size_bytes)}</span>
          <span className="text-[10px] text-gray-400">
            {asset.created_at
              ? (() => { try { return format(parseISO(asset.created_at), 'MMM d'); } catch { return ''; } })()
              : ''}
          </span>
        </div>
      </div>
    </div>
  );
};

// ── Upload zone ───────────────────────────────────────────────────────────────
const UploadZone = ({ onFiles, dragging, onDragOver, onDragLeave, onDrop }) => (
  <div
    onDragOver={onDragOver}
    onDragLeave={onDragLeave}
    onDrop={onDrop}
    className={`border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center gap-3 transition-colors ${
      dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-gray-300'
    }`}
  >
    <FaCloudUploadAlt className={`text-4xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
    <div className="text-center">
      <p className="text-sm font-semibold text-gray-600">
        {dragging ? 'Drop to upload' : 'Drag & drop files here'}
      </p>
      <p className="text-xs text-gray-400 mt-0.5">Images and videos · Multiple files supported</p>
    </div>
    <button
      onClick={onFiles}
      className="px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
    >
      Browse Files
    </button>
  </div>
);

// ── Skeleton card ─────────────────────────────────────────────────────────────
const SkeletonCard = () => (
  <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden animate-pulse">
    <div className="aspect-square bg-gray-50" />
    <div className="px-3 py-2.5 space-y-1.5">
      <div className="h-3 bg-gray-50 rounded w-3/4" />
      <div className="h-2 bg-gray-50 rounded w-1/2" />
    </div>
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────
const MediaLibrary = () => {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [filterType, setFilterType] = useState('all'); // 'all' | 'image' | 'video'
  const [searchQuery, setSearchQuery] = useState('');
  const [dragging, setDragging] = useState(false);

  const fileInputRef = useRef(null);

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMediaAssets();
      setAssets(data);
    } catch {
      toast.error('Failed to load media library');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  // Client-side filter
  const filtered = useMemo(() => {
    let list = assets;
    if (filterType !== 'all') {
      list = list.filter((a) => (a.content_type || '').startsWith(`${filterType}/`));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((a) => (a.filename || '').toLowerCase().includes(q));
    }
    return list;
  }, [assets, filterType, searchQuery]);

  // ── Upload logic ──────────────────────────────────────────────────────────
  const handleFiles = async (files) => {
    const arr = Array.from(files).filter((f) =>
      f.type.startsWith('image/') || f.type.startsWith('video/')
    );
    if (!arr.length) {
      toast.error('Only image and video files are supported');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    const uploaded = [];

    for (let i = 0; i < arr.length; i++) {
      try {
        const asset = await uploadMediaAsset(arr[i], (e) => {
          const fileProgress = Math.round((e.loaded * 100) / e.total);
          const overall = Math.round(((i / arr.length) + fileProgress / 100 / arr.length) * 100);
          setUploadProgress(overall);
        });
        uploaded.push(asset);
      } catch {
        toast.error(`Failed to upload ${arr[i].name}`);
      }
    }

    if (uploaded.length) {
      setAssets((prev) => [...uploaded, ...prev]);
      toast.success(`${uploaded.length} file${uploaded.length > 1 ? 's' : ''} uploaded`);
    }
    setUploading(false);
    setUploadProgress(0);
  };

  const handleFileInputChange = (e) => {
    if (e.target.files?.length) {
      handleFiles(e.target.files);
      e.target.value = '';
    }
  };

  // ── Drag & drop ───────────────────────────────────────────────────────────
  const handleDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  // ── Copy URL ──────────────────────────────────────────────────────────────
  const handleCopy = (asset) => {
    navigator.clipboard.writeText(resolveUrl(asset.url));
    toast.success('URL copied to clipboard');
  };

  // ── Delete ────────────────────────────────────────────────────────────────
  const handleDelete = async (asset) => {
    if (!window.confirm(`Delete "${asset.filename}"? This cannot be undone.`)) return;
    try {
      await deleteMediaAsset(asset.id);
      setAssets((prev) => prev.filter((a) => a.id !== asset.id));
      toast.success('Asset deleted');
    } catch {
      toast.error('Failed to delete asset');
    }
  };

  const imageCount = assets.filter((a) => (a.content_type || '').startsWith('image/')).length;
  const videoCount = assets.filter((a) => (a.content_type || '').startsWith('video/')).length;

  return (
    <DashboardLayout>
      <div
        className="max-w-6xl mx-auto"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,video/*"
          className="hidden"
          onChange={handleFileInputChange}
        />

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <FaImages className="text-green-500" />
              Media Library
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {assets.length} asset{assets.length !== 1 ? 's' : ''} · {imageCount} image{imageCount !== 1 ? 's' : ''}, {videoCount} video{videoCount !== 1 ? 's' : ''}
            </p>
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-60"
          >
            <FaUpload className="text-xs" />
            {uploading ? `Uploading… ${uploadProgress}%` : 'Upload'}
          </button>
        </div>

        {/* Upload progress bar */}
        {uploading && (
          <div className="mb-4">
            <div className="w-full h-1.5 bg-offwhite border border-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Search + Filter */}
        <div className="flex items-center gap-3 mb-5">
          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
            <input
              type="text"
              placeholder="Search by filename…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-300 placeholder:text-gray-300"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <FaTimes className="text-xs" />
              </button>
            )}
          </div>

          {/* Type filter */}
          <div className="flex items-center gap-1 bg-offwhite border border-gray-200 rounded-lg p-1">
            {[
              { label: 'All', value: 'all' },
              { label: 'Images', value: 'image' },
              { label: 'Videos', value: 'video' },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setFilterType(opt.value)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  filterType === opt.value
                    ? 'bg-offwhite text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {[...Array(10)].map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : assets.length === 0 ? (
          <UploadZone
            dragging={dragging}
            onFiles={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          />
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <FaImages className="text-4xl text-gray-200 mb-3" />
            <p className="text-sm font-medium text-gray-500">No results for "{searchQuery}"</p>
            <button
              onClick={() => { setSearchQuery(''); setFilterType('all'); }}
              className="mt-3 text-xs text-green-600 hover:text-green-700 font-medium"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {/* Upload tile */}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="aspect-square rounded-xl border-2 border-dashed border-gray-200 hover:border-green-400 hover:bg-green-50 flex flex-col items-center justify-center gap-2 transition-colors text-gray-400 hover:text-green-500"
            >
              <FaUpload className="text-xl" />
              <span className="text-xs font-medium">Upload</span>
            </button>

            {filtered.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                onCopy={handleCopy}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default MediaLibrary;
