import React, { useState } from 'react';
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
} from 'react-icons/fa';

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

  const activePage = pages.find((p) => p.id === activePageId) || { title: 'Home', slug: 'home' };

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
          <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 p-[1.5px] shrink-0">
            {avatarUrl ? (
              <img src={avatarUrl} alt="" className="w-full h-full object-cover rounded-full" />
            ) : (
              <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 to-indigo-600 flex items-center justify-center text-xs font-black text-white">
                {title ? title[0] : 'U'}
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-bold text-gray-900 dark:text-white truncate">
              {title || 'Your Name'}
            </div>
            <div className="text-[11px] text-gray-400 dark:text-gray-500 font-mono truncate">
              @{handle || 'handle'}
            </div>
          </div>
        </div>
      </div>

      {/* ── 2. IDENTITY & BIO INPUTS (Direct Access) ── */}
      <div className="p-4 border-b border-black/[0.04] dark:border-white/[0.06] space-y-2.5 shrink-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
            Identity & Bio
          </span>
          {/* Multi-Page Selector Pill */}
          <div className="relative">
            <button
              onClick={() => setPageDropdownOpen(!pageDropdownOpen)}
              className="text-[10px] font-semibold text-[#0071E3] dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 px-2.5 py-0.5 rounded-full border border-blue-200/50 dark:border-blue-800/40 flex items-center gap-1"
            >
              <span>{activePage.title}</span>
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
                    onClick={() => { onSelectPage?.(pg.id); setPageDropdownOpen(false); }}
                    className={`flex items-center justify-between p-1.5 rounded-lg text-xs font-semibold cursor-pointer ${
                      activePageId === pg.id
                        ? 'bg-blue-50 dark:bg-blue-950/50 text-[#0071E3]'
                        : 'hover:bg-black/[0.04] dark:hover:bg-white/[0.06]'
                    }`}
                  >
                    <span className="truncate">{pg.title}</span>
                    {activePageId === pg.id && <FaCheck className="text-[10px]" />}
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
      </div>

      {/* ── 3. CONTENT BLOCKS TREE ── */}
      <div className="p-4 flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
            Content Blocks ({blocks.length})
          </span>
          <button
            onClick={onOpenAddModal}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold text-white bg-[#0071E3] hover:bg-blue-600 transition shadow-xs"
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
