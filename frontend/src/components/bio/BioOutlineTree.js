import React, { useState, useRef } from 'react';
import {
  FaGripVertical,
  FaTrash,
  FaEye,
  FaEyeSlash,
  FaCopy,
  FaEdit,
  FaChevronDown,
  FaChevronUp,
  FaLink,
  FaUser,
  FaPlus,
  FaTimes,
  FaCheck,
  FaSitemap,
  FaFolder,
  FaBolt,
  FaPlay,
  FaEnvelope,
  FaCamera,
  FaSpinner,
} from 'react-icons/fa';
import { toast } from 'sonner';
import { uploadBioAvatar } from '@/lib/api';

export default function BioOutlineTree({
  title,
  setTitle,
  bio,
  setBio,
  avatarUrl,
  setAvatarUrl,
  handle = 'user',
  setHandle,
  verifiedBadge = false,
  setVerifiedBadge,
  socialLinks = {},
  setSocialLinks,
  theme,
  setTheme,
  blocks = [],
  setBlocks,
  pages = [],
  activePageId = 'home',
  onSelectPage,
  onAddPage,
  onDeletePage,
  onUpdateSubPage,
  onSavePage,
  saving = false,
  onOpenBlockEditor,
  onOpenAddModal,
  onQuickAddLink,
  onDuplicateBlock,
  onToggleBlockActive,
  onDeleteBlock,
  deletedBlocks = [],
  onRestoreBlock,
  onClearDeletedBlocks,
  onReorderBlocks,
}) {
  const [pageDropdownOpen, setPageDropdownOpen] = useState(false);
  const [addPageModalOpen, setAddPageModalOpen] = useState(false);
  const [newPageTitle, setNewPageTitle] = useState('');
  const [newPageSlug, setNewPageSlug] = useState('');
  const [quickLinkInput, setQuickLinkInput] = useState('');
  const [trashOpen, setTrashOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const homeFileInputRef = useRef(null);
  const subPageFileInputRef = useRef(null);

  const activePage = pages.find((p) => p.id === activePageId) || { title: 'Home', slug: 'home' };

  const handleAvatarFileChange = async (e, isSubPage = false) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      toast.error('Avatar image must be under 10MB');
      return;
    }
    try {
      setUploadingAvatar(true);
      const res = await uploadBioAvatar(file);
      if (res?.url) {
        if (isSubPage) {
          onUpdateSubPage?.('avatar_url', res.url);
          toast.success('Sub-page avatar updated!');
        } else {
          setAvatarUrl?.(res.url);
          toast.success('Display picture updated!');
        }
      }
    } catch (err) {
      console.error('Avatar upload failed:', err);
      toast.error(err?.response?.data?.detail || 'Failed to upload display picture');
    } finally {
      setUploadingAvatar(false);
      if (e.target) e.target.value = '';
    }
  };

  const handleQuickAddSubmit = (e) => {
    e.preventDefault();
    if (!quickLinkInput.trim()) return;
    onQuickAddLink?.(quickLinkInput.trim());
    setQuickLinkInput('');
  };

  const handleCreatePageSubmit = (e) => {
    e.preventDefault();
    if (!newPageTitle.trim()) return;
    const cleanSlug = newPageSlug.trim() || newPageTitle.trim().toLowerCase().replace(/[^a-z0-9]/g, '-');
    onAddPage?.(newPageTitle.trim(), cleanSlug);
    setNewPageTitle('');
    setNewPageSlug('');
    setAddPageModalOpen(false);
  };

  const handleDragStart = (e, index) => {
    setDraggedIdx(index);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === index) return;
    setDragOverIdx(index);
  };

  const handleDragEnd = () => {
    if (draggedIdx !== null && dragOverIdx !== null && draggedIdx !== dragOverIdx) {
      const updated = [...blocks];
      const [moved] = updated.splice(draggedIdx, 1);
      updated.splice(dragOverIdx, 0, moved);
      onReorderBlocks?.(updated);
    }
    setDraggedIdx(null);
    setDragOverIdx(null);
  };

  const getBlockGlyph = (blk) => {
    if (blk.is_featured) return '⚡';
    if (blk.type === 'video' || blk.media_url?.includes('youtube') || blk.media_url?.includes('vimeo')) return '▶';
    if (blk.type === 'newsletter' || blk.type === 'email_capture') return '✉️';
    if (blk.type === 'folder' || blk.type === 'tab_group') return '📁';
    return '🔗';
  };

  return (
    <div className="flex flex-col h-full bg-white/80 dark:bg-[#1C1C1E]/80 backdrop-blur-2xl border-r border-black/[0.06] dark:border-white/[0.08] text-gray-800 dark:text-gray-200 select-none overflow-y-auto custom-scrollbar">
      
      {/* ── 1. WORKSPACE BIO LIVE PROFILE CARD ── */}
      <div className="p-4 border-b border-black/[0.04] dark:border-white/[0.06] shrink-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
            Workspace Bio
          </span>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/40">
            Live
          </span>
        </div>
        <div className="flex items-center gap-3 p-2.5 rounded-xl bg-black/[0.03] dark:bg-white/[0.04] border border-black/[0.04] dark:border-white/[0.06]">
          <div
            onClick={() => homeFileInputRef.current?.click()}
            className="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 p-[1.5px] shrink-0 relative group cursor-pointer"
            title="Click to upload/change display picture"
          >
            {avatarUrl ? (
              <img src={avatarUrl} alt="" className="w-full h-full object-cover rounded-full" />
            ) : (
              <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 to-indigo-600 flex items-center justify-center text-xs font-black text-white">
                {title ? title[0] : 'U'}
              </div>
            )}
            <div className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity text-white text-[11px]">
              {uploadingAvatar ? <FaSpinner className="animate-spin" /> : <FaCamera />}
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-bold text-gray-900 dark:text-white truncate">
              {title || 'Your Name'}
            </div>
            <div className="text-[11px] text-gray-400 dark:text-gray-500 font-mono truncate">
              @{handle || 'handle'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => homeFileInputRef.current?.click()}
            disabled={uploadingAvatar}
            className="px-2 py-1 text-[10px] font-semibold rounded-lg bg-blue-50 dark:bg-blue-950/50 text-[#0071E3] dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition flex items-center gap-1 cursor-pointer disabled:opacity-50"
            title="Upload Display Picture"
          >
            {uploadingAvatar ? (
              <FaSpinner className="animate-spin text-[9px]" />
            ) : (
              <FaCamera className="text-[9px]" />
            )}
            <span>Photo</span>
          </button>
          <input
            type="file"
            ref={homeFileInputRef}
            accept="image/*"
            className="hidden"
            onChange={(e) => handleAvatarFileChange(e, false)}
          />
        </div>
      </div>

      {/* ── 2. IDENTITY & BIO INPUTS (Direct Access) ── */}
      <div className="p-4 border-b border-black/[0.04] dark:border-white/[0.06] space-y-2.5 shrink-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
            {activePageId === 'home' ? 'Identity & Profile' : 'Sub-Page Manager'}
          </span>
          {/* Multi-Page Selector Pill */}
          <div className="relative">
            <button
              onClick={() => setPageDropdownOpen(!pageDropdownOpen)}
              className="text-[10px] font-semibold text-[#0071E3] dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-0.5 rounded-full border border-blue-200/50 dark:border-blue-800/40 flex items-center gap-1"
            >
              <span>{activePage.title || 'Page'}</span>
              <FaChevronDown className="text-[8px]" />
            </button>

            {pageDropdownOpen && (
              <div className="absolute right-0 top-6 z-40 bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-2xl border border-black/[0.08] dark:border-white/[0.12] rounded-xl shadow-xl p-2 w-48 space-y-1 animate-in fade-in zoom-in-95 duration-100">
                <div className="p-1 text-[9px] font-bold uppercase tracking-wider text-gray-400">
                  Site Pages ({pages.length || 1})
                </div>
                <div
                  onClick={() => { onSelectPage?.('home'); setPageDropdownOpen(false); }}
                  className={`flex items-center justify-between p-1.5 rounded-lg text-xs font-semibold cursor-pointer ${
                    activePageId === 'home'
                      ? 'bg-blue-50 dark:bg-blue-950/50 text-[#0071E3]'
                      : 'hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
                  }`}
                >
                  <div className="flex items-center gap-1.5 truncate">
                    <FaSitemap className="text-[10px]" />
                    <span>Home</span>
                  </div>
                  {activePageId === 'home' && <FaCheck className="text-[10px]" />}
                </div>
                {pages.filter((p) => p.id !== 'home').map((pg) => (
                  <div
                    key={pg.id}
                    className={`flex items-center justify-between p-1.5 rounded-lg text-xs font-semibold group ${
                      activePageId === pg.id
                        ? 'bg-blue-50 dark:bg-blue-950/50 text-[#0071E3]'
                        : 'hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
                    }`}
                  >
                    <div
                      onClick={() => { onSelectPage?.(pg.id); setPageDropdownOpen(false); }}
                      className="flex-1 flex items-center justify-between cursor-pointer truncate mr-1"
                    >
                      <span className="truncate">{pg.title}</span>
                      {activePageId === pg.id && <FaCheck className="text-[10px]" />}
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm(`Delete sub-page "${pg.title}"?`)) {
                          onDeletePage?.(pg.id);
                        }
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 rounded transition-opacity"
                      title="Delete page"
                    >
                      <FaTrash className="text-[9px]" />
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => { setAddPageModalOpen(true); setPageDropdownOpen(false); }}
                  className="w-full text-left p-1.5 text-xs text-[#0071E3] font-semibold hover:underline flex items-center gap-1 pt-2 border-t border-black/[0.04] dark:border-white/[0.06]"
                >
                  <FaPlus className="text-[9px]" /> Add new page
                </button>
              </div>
            )}
          </div>
        </div>

        {activePageId === 'home' ? (
          <>
            {/* Display Picture Upload Section */}
            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400 block mb-1">
                Display Picture / Profile Avatar
              </label>
              <div className="flex items-center gap-2.5 p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
                <div className="w-10 h-10 rounded-full overflow-hidden shrink-0 border border-black/10 dark:border-white/10 bg-gray-100 dark:bg-gray-800">
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-xs font-bold text-gray-400">
                      {title ? title[0] : 'U'}
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0 flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => homeFileInputRef.current?.click()}
                    disabled={uploadingAvatar}
                    className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-[#0071E3] text-white hover:bg-blue-600 transition flex items-center gap-1 cursor-pointer disabled:opacity-50"
                  >
                    {uploadingAvatar ? (
                      <>
                        <FaSpinner className="animate-spin text-[10px]" />
                        <span>Uploading...</span>
                      </>
                    ) : (
                      <>
                        <FaCamera className="text-[10px]" />
                        <span>{avatarUrl ? 'Change Image' : 'Upload Image'}</span>
                      </>
                    )}
                  </button>
                  {avatarUrl && (
                    <button
                      type="button"
                      onClick={() => setAvatarUrl?.('')}
                      className="px-2 py-1 text-xs font-medium text-red-500 hover:text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition cursor-pointer"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
              <span className="text-[10px] text-gray-400 mt-1 block">
                JPG, PNG, WebP up to 10MB
              </span>
            </div>

            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">Display Name</label>
              <input
                type="text"
                value={title || ''}
                onChange={(e) => setTitle?.(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] focus:border-[#0071E3] focus:outline-none transition text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">Bio Tagline</label>
              <input
                type="text"
                value={bio || ''}
                onChange={(e) => setBio?.(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] focus:border-[#0071E3] focus:outline-none transition text-gray-900 dark:text-white"
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-xs font-medium text-gray-700 dark:text-gray-300">Apple Verified Badge</span>
              <label className="apple-switch">
                <input
                  type="checkbox"
                  checked={Boolean(verifiedBadge)}
                  onChange={(e) => setVerifiedBadge?.(e.target.checked)}
                />
                <span className="apple-switch-slider" />
              </label>
            </div>

            {/* Explicit Save Option for Home Page */}
            <button
              type="button"
              onClick={onSavePage}
              disabled={saving}
              className="w-full mt-2 py-2 px-3 rounded-xl text-xs font-semibold text-white bg-[#0071E3] hover:bg-blue-600 active:scale-[0.98] transition flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50 cursor-pointer"
            >
              {saving ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Saving Home Page...</span>
                </>
              ) : (
                <>
                  <FaCheck className="text-[10px]" />
                  <span>Save Home Page Changes</span>
                </>
              )}
            </button>
          </>
        ) : (
          /* Sub-Page Isolated Controls */
          <div className="space-y-2.5">
            <div className="p-2.5 rounded-xl bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-800/40 text-[11px] space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-blue-700 dark:text-blue-400 uppercase tracking-wider text-[9px] flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                  Sub-Page Isolated Mode
                </span>
                <span className="text-[10px] text-gray-500 font-mono">
                  ?page={activePage.slug || activePage.id}
                </span>
              </div>
              <p className="text-gray-600 dark:text-gray-300 text-[11px] leading-tight">
                Changes and blocks below are strictly confined to <strong>"{activePage.title}"</strong> and will never bleed to other pages.
              </p>
            </div>

            {/* Sub-Page Specific Display Picture */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                  Sub-Page Display Picture
                </label>
                {activePage.avatar_url && (
                  <span className="text-[9px] font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 px-1.5 py-0.5 rounded">
                    Custom for this page
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2.5 p-2 rounded-xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
                <div className="w-10 h-10 rounded-full overflow-hidden shrink-0 border border-black/10 dark:border-white/10 bg-gray-100 dark:bg-gray-800">
                  {activePage.avatar_url ? (
                    <img src={activePage.avatar_url} alt="Subpage Avatar" className="w-full h-full object-cover" />
                  ) : avatarUrl ? (
                    <img src={avatarUrl} alt="Main Avatar" className="w-full h-full object-cover opacity-60" title="Using main bio avatar" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-xs font-bold text-gray-400">
                      {activePage.title ? activePage.title[0] : 'P'}
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0 flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => subPageFileInputRef.current?.click()}
                    disabled={uploadingAvatar}
                    className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-[#0071E3] text-white hover:bg-blue-600 transition flex items-center gap-1 cursor-pointer disabled:opacity-50"
                  >
                    {uploadingAvatar ? (
                      <>
                        <FaSpinner className="animate-spin text-[10px]" />
                        <span>Uploading...</span>
                      </>
                    ) : (
                      <>
                        <FaCamera className="text-[10px]" />
                        <span>{activePage.avatar_url ? 'Change Avatar' : 'Custom Avatar'}</span>
                      </>
                    )}
                  </button>
                  {activePage.avatar_url && (
                    <button
                      type="button"
                      onClick={() => onUpdateSubPage?.('avatar_url', '')}
                      className="px-2 py-1 text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition cursor-pointer"
                      title="Revert to using main profile avatar"
                    >
                      Use Main
                    </button>
                  )}
                </div>
              </div>
              <input
                type="file"
                ref={subPageFileInputRef}
                accept="image/*"
                className="hidden"
                onChange={(e) => handleAvatarFileChange(e, true)}
              />
              <span className="text-[10px] text-gray-400 mt-1 block">
                {activePage.avatar_url ? 'Custom display picture for this sub-page' : 'Currently inheriting main bio display picture'}
              </span>
            </div>

            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">Sub-Page Title</label>
              <input
                type="text"
                value={activePage.title || ''}
                onChange={(e) => onUpdateSubPage?.('title', e.target.value)}
                placeholder="e.g. Portfolio, Shop, Press Kit"
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] focus:border-[#0071E3] focus:outline-none transition text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">Sub-Page Tagline / Description</label>
              <input
                type="text"
                value={activePage.description || ''}
                onChange={(e) => onUpdateSubPage?.('description', e.target.value)}
                placeholder="Tagline or bio for this sub-page..."
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] focus:border-[#0071E3] focus:outline-none transition text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium text-gray-500 dark:text-gray-400">URL Slug</label>
              <div className="flex items-center gap-1 mt-1">
                <span className="text-[10px] text-gray-400 font-mono select-none">?page=</span>
                <input
                  type="text"
                  value={activePage.slug || ''}
                  onChange={(e) => onUpdateSubPage?.('slug', e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '-'))}
                  placeholder="slug"
                  className="w-full px-2.5 py-1.5 text-xs font-mono rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] focus:border-[#0071E3] focus:outline-none transition text-gray-900 dark:text-white"
                />
              </div>
            </div>

            {/* Explicit Save Option for Sub-Page */}
            <button
              type="button"
              onClick={onSavePage}
              disabled={saving}
              className="w-full mt-2 py-2 px-3 rounded-xl text-xs font-semibold text-white bg-[#0071E3] hover:bg-blue-600 active:scale-[0.98] transition flex items-center justify-center gap-1.5 shadow-sm disabled:opacity-50 cursor-pointer"
            >
              {saving ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Saving Sub-Page...</span>
                </>
              ) : (
                <>
                  <FaCheck className="text-[10px]" />
                  <span>Save "{activePage.title || 'Sub-Page'}" Changes</span>
                </>
              )}
            </button>

            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                onClick={() => onSelectPage?.('home')}
                className="text-gray-500 hover:text-gray-900 dark:hover:text-white text-[11px] font-medium flex items-center gap-1 cursor-pointer"
              >
                ← Back to Home
              </button>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(`Delete sub-page "${activePage.title}" and all its blocks?`)) {
                    onDeletePage?.(activePageId);
                  }
                }}
                className="text-red-500 hover:text-red-600 text-[11px] font-medium flex items-center gap-1 cursor-pointer"
              >
                <FaTrash className="text-[9px]" /> Delete Page
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── 3. CONTENT BLOCKS TREE ── */}
      <div className="p-4 flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2">
          <div className="min-w-0 flex-1 pr-2">
            <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block truncate">
              {activePageId === 'home' ? 'Home Blocks' : `"${activePage.title}" Blocks`} ({blocks.length})
            </span>
            {activePageId !== 'home' && (
              <span className="text-[10px] text-[#0071E3] dark:text-blue-400 font-medium block truncate">
                Isolated to this page only
              </span>
            )}
          </div>
          <button
            onClick={onOpenAddModal}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold text-white bg-[#0071E3] hover:bg-blue-600 transition shadow-xs shrink-0 cursor-pointer"
          >
            <FaPlus className="text-[9px]" /> Block
          </button>
        </div>

        {/* Quick Add Link Bar */}
        <form onSubmit={handleQuickAddSubmit} className="mb-3">
          <div className="flex items-center gap-1.5 p-1 rounded-full bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08]">
            <FaLink className="text-gray-400 ml-2 text-xs" />
            <input
              type="url"
              value={quickLinkInput}
              onChange={(e) => setQuickLinkInput(e.target.value)}
              placeholder="Paste URL to add..."
              className="flex-1 bg-transparent text-xs text-gray-900 dark:text-white placeholder-gray-400 outline-none px-1"
            />
            <button
              type="submit"
              className="px-2.5 py-1 rounded-full bg-white dark:bg-[#2C2C2E] text-gray-800 dark:text-gray-200 text-[10px] font-bold shadow-xs hover:bg-gray-100 dark:hover:bg-[#3A3A3C] transition"
            >
              Add
            </button>
          </div>
        </form>

        {/* Draggable Blocks List */}
        <div className="space-y-2 flex-1 overflow-y-auto custom-scrollbar pr-0.5">
          {blocks.length === 0 ? (
            <div className="py-10 text-center text-xs text-gray-400 dark:text-gray-500 border border-dashed border-black/[0.08] dark:border-white/[0.1] rounded-2xl p-4">
              No blocks yet. Click <span className="font-semibold text-[#0071E3]">+ Block</span> to add links, media, or captures.
            </div>
          ) : (
            blocks.map((block, idx) => (
              <div
                key={block.id || idx}
                draggable
                onDragStart={(e) => handleDragStart(e, idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
                onClick={() => onOpenBlockEditor?.(block)}
                className={`p-3 rounded-xl bg-white dark:bg-[#2C2C2E] border transition-all cursor-pointer group shadow-xs ${
                  dragOverIdx === idx
                    ? 'border-[#0071E3] ring-2 ring-[#0071E3]/20'
                    : 'border-black/[0.06] dark:border-white/[0.08] hover:border-[#0071E3]/60'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-gray-400 dark:text-gray-500 cursor-grab text-xs">⋮⋮</span>
                    <span className="text-xs shrink-0">{getBlockGlyph(block)}</span>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold truncate text-gray-900 dark:text-white">
                        {block.title || block.headline || 'Untitled Link'}
                      </div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">
                        {block.subtitle || block.url || block.type || 'Custom block'}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {block.clicks ? (
                      <span className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded">
                        {block.clicks} clicks
                      </span>
                    ) : (
                      <span className="text-[10px] font-medium text-gray-400 dark:text-gray-500 px-1.5 py-0.5">
                        Active
                      </span>
                    )}

                    <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => { e.stopPropagation(); onToggleBlockActive?.(block.id); }}
                        className="p-1 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                        title={block.is_hidden ? 'Show' : 'Hide'}
                      >
                        {block.is_hidden ? <FaEyeSlash className="text-[10px]" /> : <FaEye className="text-[10px]" />}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); onDuplicateBlock?.(block.id); }}
                        className="p-1 text-gray-400 hover:text-[#0071E3]"
                        title="Duplicate"
                      >
                        <FaCopy className="text-[10px]" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); onDeleteBlock?.(block.id); }}
                        className="p-1 text-gray-400 hover:text-rose-600"
                        title="Delete"
                      >
                        <FaTrash className="text-[10px]" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Bottom Quick Save for Active Page */}
        {blocks.length > 0 && (
          <div className="pt-2 border-t border-black/[0.04] dark:border-white/[0.06] mt-2 shrink-0">
            <button
              type="button"
              onClick={onSavePage}
              disabled={saving}
              className="w-full py-1.5 px-3 rounded-lg text-xs font-semibold text-gray-700 dark:text-gray-200 bg-black/[0.03] dark:bg-white/[0.06] hover:bg-black/[0.06] dark:hover:bg-white/[0.1] border border-black/[0.06] dark:border-white/[0.08] active:scale-[0.98] transition flex items-center justify-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              <FaCheck className="text-[10px] text-[#0071E3]" />
              <span>{saving ? 'Saving...' : `Save ${activePageId === 'home' ? 'Home' : `"${activePage.title}"`} Blocks`}</span>
            </button>
          </div>
        )}

        {/* Deleted Items / Trash Drawer Trigger */}
        {deletedBlocks?.length > 0 && (
          <div className="pt-2 border-t border-black/[0.04] dark:border-white/[0.06] mt-2">
            <button
              onClick={() => setTrashOpen(!trashOpen)}
              className="text-[11px] font-semibold text-gray-500 hover:text-rose-600 flex items-center justify-between w-full"
            >
              <span>Recently Deleted ({deletedBlocks.length})</span>
              {trashOpen ? <FaChevronUp className="text-[9px]" /> : <FaChevronDown className="text-[9px]" />}
            </button>
            {trashOpen && (
              <div className="mt-2 space-y-1.5 max-h-32 overflow-y-auto">
                {deletedBlocks.map((b) => (
                  <div key={b.id} className="p-2 rounded-lg bg-rose-50/50 dark:bg-rose-950/20 flex items-center justify-between text-xs">
                    <span className="truncate text-gray-700 dark:text-gray-300">{b.title || 'Deleted Block'}</span>
                    <button
                      onClick={() => onRestoreBlock?.(b.id)}
                      className="text-[10px] text-[#0071E3] font-bold hover:underline"
                    >
                      Restore
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Add Page Modal ── */}
      {addPageModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] rounded-[24px] max-w-sm w-full p-5 shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white">Create Mini-Site Sub Page</h3>
            <div>
              <label className="text-[11px] font-medium text-gray-500">Page Title</label>
              <input
                type="text"
                value={newPageTitle}
                onChange={(e) => setNewPageTitle(e.target.value)}
                placeholder="e.g. Portfolio, Shop, Press Kit"
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3]"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium text-gray-500">Page Slug (URL Path)</label>
              <input
                type="text"
                value={newPageSlug}
                onChange={(e) => setNewPageSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '-'))}
                placeholder="e.g. shop, press"
                className="w-full mt-1 px-3 py-1.5 text-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3]"
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setAddPageModalOpen(false)}
                className="px-3 py-1.5 rounded-full text-xs font-semibold text-gray-600 dark:text-gray-400 hover:bg-black/[0.05]"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePageSubmit}
                className="px-4 py-1.5 rounded-full text-xs font-semibold text-white bg-[#0071E3] hover:bg-blue-600 shadow-xs"
              >
                Create Page
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
