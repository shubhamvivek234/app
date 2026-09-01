import React, { useState } from 'react';
import {
  FaGripVertical,
  FaTrash,
  FaEye,
  FaEyeSlash,
  FaCopy,
  FaChartLine,
  FaEllipsisV,
  FaChevronDown,
  FaChevronUp,
  FaBell,
  FaLink,
  FaShareAlt,
  FaUser,
  FaPlay,
  FaEnvelope,
  FaThLarge,
} from 'react-icons/fa';

export default function BioOutlineTree({
  title,
  setTitle,
  bio,
  setBio,
  avatarUrl,
  setAvatarUrl,
  socialLinks,
  setSocialLinks,
  theme,
  setTheme,
  blocks,
  onOpenBlockEditor,
  onOpenAddModal,
  onQuickAddLink,
  onDuplicateBlock,
  onToggleBlockActive,
  onDeleteBlock,
  deletedBlocks,
  onRestoreBlock,
  onClearDeletedBlocks,
  onReorderBlocks,
}) {
  const [headerOpen, setHeaderOpen] = useState(false);
  const [socialsOpen, setSocialsOpen] = useState(false);
  const [announceOpen, setAnnounceOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const [quickLinkInput, setQuickLinkInput] = useState('');
  const [draggedIdx, setDraggedIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);

  const handleQuickAddSubmit = (e) => {
    e.preventDefault();
    if (!quickLinkInput.trim()) return;
    onQuickAddLink(quickLinkInput.trim());
    setQuickLinkInput('');
  };

  // Drag and drop handlers
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
      onReorderBlocks(updated);
    }
    setDraggedIdx(null);
    setDragOverIdx(null);
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 border-r border-zinc-200/80 dark:border-zinc-800 text-zinc-800 dark:text-zinc-200 select-none overflow-y-auto custom-scrollbar">
      
      {/* ── 1. Page Header Dropdown ── */}
      <div className="p-3.5 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 bg-zinc-50 dark:bg-zinc-800/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200/70 dark:border-zinc-700/60 rounded-xl px-3 py-1.5 cursor-pointer flex-1">
          <span className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">Page:</span>
          <span className="text-xs font-bold text-zinc-900 dark:text-white truncate">Home</span>
          <FaChevronDown className="text-[10px] text-zinc-400 ml-auto" />
        </div>
        <button
          onClick={() => {}}
          className="px-3 py-1.5 text-xs font-bold text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-white bg-zinc-50 dark:bg-zinc-800/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200/70 dark:border-zinc-700/60 rounded-xl transition-colors whitespace-nowrap"
        >
          Add page +
        </button>
      </div>

      <div className="p-3.5 space-y-2.5 flex-1">
        
        {/* ── 2. Collapsible Header Card ── */}
        <div className="border border-zinc-200/80 dark:border-zinc-800 rounded-2xl bg-zinc-50/50 dark:bg-zinc-800/30 overflow-hidden transition-all">
          <button
            onClick={() => setHeaderOpen(!headerOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50 transition-colors"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-full bg-zinc-200 dark:bg-zinc-700 flex items-center justify-center text-xs font-bold overflow-hidden flex-shrink-0">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                ) : (
                  <FaUser className="text-zinc-400 text-xs" />
                )}
              </div>
              <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200 truncate">
                Header
              </span>
            </div>
            {headerOpen ? <FaChevronUp className="text-xs text-zinc-400" /> : <FaChevronDown className="text-xs text-zinc-400" />}
          </button>

          {headerOpen && (
            <div className="p-3 pt-0 space-y-2.5 border-t border-zinc-100 dark:border-zinc-800/60 mt-1">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1">
                  Profile Title / Name
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Your Name or Brand"
                  className="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 font-semibold text-zinc-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1">
                  Bio Description
                </label>
                <textarea
                  rows={2}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Artist, founder & content creator based in..."
                  className="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-800 dark:text-zinc-200 resize-none"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1">
                  Avatar Photo URL
                </label>
                <input
                  type="url"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="https://.../avatar.jpg"
                  className="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-800 dark:text-zinc-200 font-mono"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── 3. Collapsible Socials Strip ── */}
        <div className="border border-zinc-200/80 dark:border-zinc-800 rounded-2xl bg-zinc-50/50 dark:bg-zinc-800/30 overflow-hidden transition-all">
          <button
            onClick={() => setSocialsOpen(!socialsOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <FaShareAlt className="text-xs text-indigo-500 flex-shrink-0" />
              <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">
                Socials
              </span>
              <span className="text-[10px] text-zinc-400">
                ({Object.keys(socialLinks || {}).filter((k) => socialLinks[k]).length} active)
              </span>
            </div>
            {socialsOpen ? <FaChevronUp className="text-xs text-zinc-400" /> : <FaChevronDown className="text-xs text-zinc-400" />}
          </button>

          {socialsOpen && (
            <div className="p-3 pt-0 space-y-2 border-t border-zinc-100 dark:border-zinc-800/60 mt-1">
              {['instagram', 'tiktok', 'youtube', 'twitter', 'linkedin', 'spotify', 'github', 'discord'].map((plat) => (
                <div key={plat} className="flex items-center gap-2">
                  <span className="w-16 text-[10px] font-bold uppercase tracking-wider text-zinc-400 capitalize">
                    {plat === 'twitter' ? 'X' : plat}
                  </span>
                  <input
                    type="text"
                    value={socialLinks?.[plat] || ''}
                    onChange={(e) => setSocialLinks({ ...socialLinks, [plat]: e.target.value })}
                    placeholder={`https://${plat}.com/...`}
                    className="flex-1 px-2.5 py-1 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg outline-hidden focus:ring-1 focus:ring-indigo-500 text-zinc-800 dark:text-zinc-200 font-mono"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 4. Collapsible Announcement Banner ── */}
        <div className="border border-zinc-200/80 dark:border-zinc-800 rounded-2xl bg-zinc-50/50 dark:bg-zinc-800/30 overflow-hidden transition-all">
          <button
            onClick={() => setAnnounceOpen(!announceOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-zinc-100/50 dark:hover:bg-zinc-800/50 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <FaBell className="text-xs text-amber-500 flex-shrink-0" />
              <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">
                Announce
              </span>
              {theme?.announcement_active && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              )}
            </div>
            <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
              {theme?.announcement_active ? 'Edit' : 'Add'}
            </span>
          </button>

          {announceOpen && (
            <div className="p-3 pt-0 space-y-2.5 border-t border-zinc-100 dark:border-zinc-800/60 mt-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Show Top Banner</span>
                <input
                  type="checkbox"
                  checked={theme?.announcement_active || false}
                  onChange={(e) => setTheme({ ...theme, announcement_active: e.target.checked })}
                  className="w-4 h-4 text-indigo-600 rounded-sm focus:ring-indigo-500"
                />
              </div>
              <div>
                <input
                  type="text"
                  value={theme?.announcement_banner || ''}
                  onChange={(e) => setTheme({ ...theme, announcement_banner: e.target.value })}
                  placeholder="🚀 Summer Drop Live! Free shipping on all orders."
                  className="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                />
              </div>
              <div>
                <input
                  type="url"
                  value={theme?.announcement_url || ''}
                  onChange={(e) => setTheme({ ...theme, announcement_url: e.target.value })}
                  placeholder="https://..."
                  className="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white font-mono"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── 5. Blocks Header & Quick Paste Bar ── */}
        <div className="pt-2">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-zinc-900 dark:text-white">Blocks</span>
              <span className="text-[10px] font-bold text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded-full">
                {blocks.length}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={onOpenAddModal}
                className="px-2.5 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/60 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 rounded-lg transition-colors flex items-center gap-1"
              >
                Add +
              </button>
            </div>
          </div>

          {/* Quick Paste Input */}
          <form onSubmit={handleQuickAddSubmit} className="relative mb-3">
            <input
              type="text"
              value={quickLinkInput}
              onChange={(e) => setQuickLinkInput(e.target.value)}
              placeholder="Paste a link or search…"
              className="w-full pl-8 pr-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/70 border border-zinc-200/80 dark:border-zinc-700/80 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white placeholder-zinc-400 transition-all shadow-2xs"
            />
            <FaLink className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 text-[11px]" />
          </form>

          {/* Draggable Block Cards List */}
          <div className="space-y-2">
            {blocks.map((block, idx) => {
              const isDragging = draggedIdx === idx;
              const isOver = dragOverIdx === idx;
              return (
                <div
                  key={block.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragOver={(e) => handleDragOver(e, idx)}
                  onDragEnd={handleDragEnd}
                  className={`group relative rounded-2xl border transition-all duration-150 ${
                    isDragging
                      ? 'opacity-30 border-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/30'
                      : isOver
                      ? 'border-indigo-500 bg-indigo-50/40 dark:bg-indigo-950/40 translate-y-1'
                      : block.active !== false
                      ? 'border-zinc-200/80 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-zinc-300 dark:hover:border-zinc-700 shadow-2xs'
                      : 'border-zinc-200/50 dark:border-zinc-800/50 bg-zinc-50/50 dark:bg-zinc-900/40 opacity-60'
                  }`}
                >
                  <div className="p-2.5 flex items-center gap-2.5">
                    {/* Drag Handle */}
                    <div className="cursor-grab active:cursor-grabbing text-zinc-300 dark:text-zinc-600 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors p-0.5">
                      <FaGripVertical className="text-xs" />
                    </div>

                    {/* Block Content Info (Click to edit) */}
                    <div
                      onClick={() => onOpenBlockEditor(block)}
                      className="flex-1 min-w-0 cursor-pointer"
                    >
                      <div className="flex items-center gap-1.5">
                        {block.type === 'link' && <FaLink className="text-indigo-500 text-[10px] flex-shrink-0" />}
                        {block.type === 'embed' && <FaPlay className="text-rose-500 text-[10px] flex-shrink-0" />}
                        {block.type === 'feed_grid' && <FaThLarge className="text-purple-500 text-[10px] flex-shrink-0" />}
                        {block.type === 'lead_capture' && <FaEnvelope className="text-emerald-500 text-[10px] flex-shrink-0" />}
                        <span className="text-xs font-bold text-zinc-900 dark:text-white truncate">
                          {block.title || block.headline || block.url || 'Untitled Link'}
                        </span>
                      </div>
                      {block.subtitle && (
                        <p className="text-[11px] text-zinc-400 truncate mt-0.5">{block.subtitle}</p>
                      )}
                      
                      {/* Sub-actions & click badges */}
                      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-zinc-400">
                        <button
                          onClick={(e) => { e.stopPropagation(); onDeleteBlock(block.id); }}
                          className="hover:text-rose-600 p-0.5"
                          title="Delete"
                        >
                          <FaTrash className="text-[9px]" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onToggleBlockActive(block.id); }}
                          className="hover:text-zinc-700 dark:hover:text-zinc-200 p-0.5"
                          title={block.active !== false ? 'Hide Block' : 'Show Block'}
                        >
                          {block.active !== false ? <FaEye className="text-[10px]" /> : <FaEyeSlash className="text-[10px] text-rose-500" />}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onDuplicateBlock(block); }}
                          className="hover:text-zinc-700 dark:hover:text-zinc-200 p-0.5"
                          title="Duplicate"
                        >
                          <FaCopy className="text-[9px]" />
                        </button>
                        {block.click_count !== undefined && block.click_count > 0 && (
                          <span className="ml-auto text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-0.5">
                            <FaChartLine className="text-[8px]" /> {block.click_count}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Thumbnail / Image Preview on Right */}
                    {block.media_url ? (
                      <div
                        onClick={() => onOpenBlockEditor(block)}
                        className="w-10 h-10 rounded-xl overflow-hidden bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 flex-shrink-0 cursor-pointer"
                      >
                        <img src={block.media_url} alt="" className="w-full h-full object-cover" />
                      </div>
                    ) : (
                      <button
                        onClick={() => onOpenBlockEditor(block)}
                        className="w-7 h-7 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center justify-center text-zinc-400 transition-colors flex-shrink-0"
                      >
                        <FaEllipsisV className="text-[10px]" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 6. Deleted Blocks Archive ── */}
        {deletedBlocks?.length > 0 && (
          <div className="pt-4 border-t border-zinc-100 dark:border-zinc-800">
            <button
              onClick={() => setTrashOpen(!trashOpen)}
              className="w-full flex items-center justify-between text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 py-1"
            >
              <span className="flex items-center gap-1.5">
                <FaTrash className="text-[10px]" /> Deleted Blocks ({deletedBlocks.length})
              </span>
              {trashOpen ? <FaChevronUp className="text-[10px]" /> : <FaChevronDown className="text-[10px]" />}
            </button>

            {trashOpen && (
              <div className="space-y-1.5 mt-2 bg-zinc-50 dark:bg-zinc-800/40 p-2 rounded-xl">
                {deletedBlocks.map((del) => (
                  <div key={del.id} className="flex items-center justify-between text-xs p-1.5 bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200/60 dark:border-zinc-800">
                    <span className="truncate font-medium text-zinc-700 dark:text-zinc-300 text-[11px]">
                      {del.title || del.url || 'Deleted Block'}
                    </span>
                    <button
                      onClick={() => onRestoreBlock(del)}
                      className="text-indigo-600 dark:text-indigo-400 font-bold hover:underline text-[10px]"
                    >
                      Restore
                    </button>
                  </div>
                ))}
                <button
                  onClick={onClearDeletedBlocks}
                  className="w-full text-center text-[10px] text-rose-500 font-bold hover:underline pt-1"
                >
                  Clear Deleted Blocks Permanently
                </button>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
