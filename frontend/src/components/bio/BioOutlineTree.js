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
  FaFolder,
  FaFolderOpen,
  FaPlus,
  FaTimes,
  FaCheck,
  FaSitemap,
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
  deletedBlocks,
  onRestoreBlock,
  onClearDeletedBlocks,
  onReorderBlocks,
}) {
  const [pageDropdownOpen, setPageDropdownOpen] = useState(false);
  const [addPageModalOpen, setAddPageModalOpen] = useState(false);
  const [newPageTitle, setNewPageTitle] = useState('');
  const [newPageSlug, setNewPageSlug] = useState('');

  const [headerOpen, setHeaderOpen] = useState(false);
  const [socialsOpen, setSocialsOpen] = useState(false);
  const [announceOpen, setAnnounceOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const [quickLinkInput, setQuickLinkInput] = useState('');
  const [draggedIdx, setDraggedIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);

  const activePage = pages.find((p) => p.id === activePageId) || { title: 'Home', slug: 'home' };

  const handleQuickAddSubmit = (e) => {
    e.preventDefault();
    if (!quickLinkInput.trim()) return;
    onQuickAddLink(quickLinkInput.trim());
    setQuickLinkInput('');
  };

  const handleCreatePageSubmit = (e) => {
    e.preventDefault();
    if (!newPageTitle.trim()) return;
    const cleanSlug = (newPageSlug.trim() || newPageTitle.trim().toLowerCase().replace(/[^a-z0-9]/g, '-'));
    onAddPage?.(newPageTitle.trim(), cleanSlug);
    setNewPageTitle('');
    setNewPageSlug('');
    setAddPageModalOpen(false);
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

  const toggleFolderExpanded = (blockId) => {
    setBlocks((prev) =>
      prev.map((b) => (b.id === blockId ? { ...b, is_expanded: !b.is_expanded } : b))
    );
  };

  return (
    <div className="flex flex-col h-full bg-white border-r border-gray-200 text-gray-700 select-none overflow-y-auto custom-scrollbar">
      
      {/* ── 1. Page Switcher Dropdown (Multi-Page Mini Sites) ── */}
      <div className="p-3.5 border-b border-gray-100 flex items-center justify-between gap-2 relative">
        <div
          onClick={() => setPageDropdownOpen(!pageDropdownOpen)}
          className="flex items-center gap-2 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl px-3 py-1.5 cursor-pointer flex-1"
        >
          <span className="text-xs font-semibold text-gray-400">Page:</span>
          <span className="text-xs font-bold text-gray-900 truncate">
            {activePage.title}
          </span>
          <FaChevronDown className="text-[10px] text-gray-500 ml-auto" />
        </div>

        <button
          onClick={() => setAddPageModalOpen(true)}
          className="px-3 py-1.5 text-xs font-bold text-gray-500 hover:text-gray-900 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-xl transition-colors whitespace-nowrap flex items-center gap-1"
        >
          <FaPlus className="text-[9px]" /> Add page
        </button>

        {/* Page Switcher Popover Menu */}
        {pageDropdownOpen && (
          <div className="absolute top-14 left-3.5 right-3.5 z-40 bg-white border border-gray-200 rounded-2xl shadow-xl p-2 space-y-1 animate-in fade-in zoom-in-95 duration-100">
            <div className="p-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-500">
              Your Site Pages ({pages.length || 1})
            </div>
            
            {/* Default Home Page */}
            <div
              onClick={() => { onSelectPage?.('home'); setPageDropdownOpen(false); }}
              className={`flex items-center justify-between p-2 rounded-xl text-xs font-bold cursor-pointer transition-colors ${
                activePageId === 'home'
                  ? 'bg-indigo-50 text-indigo-600'
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              <div className="flex items-center gap-2">
                <FaSitemap className="text-xs text-indigo-500" />
                <span>Home</span>
                <span className="text-[10px] font-mono opacity-50">(/)</span>
              </div>
              {activePageId === 'home' && <FaCheck className="text-xs" />}
            </div>

            {/* Custom Sub-Pages */}
            {pages.filter((p) => p.id !== 'home').map((pg) => (
              <div
                key={pg.id}
                onClick={() => { onSelectPage?.(pg.id); setPageDropdownOpen(false); }}
                className={`flex items-center justify-between p-2 rounded-xl text-xs font-bold cursor-pointer transition-colors group ${
                  activePageId === pg.id
                    ? 'bg-indigo-50 text-indigo-600'
                    : 'hover:bg-gray-100 text-gray-600'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <FaFolder className="text-xs text-amber-500 flex-shrink-0" />
                  <span className="truncate">{pg.title}</span>
                  <span className="text-[10px] font-mono opacity-50 truncate">
                    (/{pg.slug})
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {activePageId === pg.id && <FaCheck className="text-xs" />}
                  <button
                    onClick={(e) => { e.stopPropagation(); onDeletePage?.(pg.id); }}
                    className="text-gray-500 hover:text-rose-600 p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete Page"
                  >
                    <FaTrash className="text-[10px]" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-3.5 space-y-2.5 flex-1">
        
        {/* ── 2. Collapsible Header Card ── */}
        <div className="border border-gray-200 rounded-2xl bg-gray-50 overflow-hidden transition-all">
          <button
            onClick={() => setHeaderOpen(!headerOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-gray-100/50 transition-colors"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold overflow-hidden flex-shrink-0">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                ) : (
                  <FaUser className="text-gray-500 text-xs" />
                )}
              </div>
              <span className="text-xs font-bold text-gray-700 truncate">
                Header
              </span>
            </div>
            {headerOpen ? <FaChevronUp className="text-xs text-gray-500" /> : <FaChevronDown className="text-xs text-gray-500" />}
          </button>

          {headerOpen && (
            <div className="p-3 pt-0 space-y-2.5 border-t border-gray-100 mt-1">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">
                  Profile Title / Name
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Your Name or Brand"
                  className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 font-semibold text-gray-900"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">
                  Bio Description
                </label>
                <textarea
                  rows={2}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Artist, founder & content creator based in..."
                  className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-gray-700 resize-none"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-gray-500 mb-1">
                  Avatar Photo URL
                </label>
                <input
                  type="url"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="https://.../avatar.jpg"
                  className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-gray-700 font-mono"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── 3. Collapsible Socials Strip ── */}
        <div className="border border-gray-200 rounded-2xl bg-gray-50 overflow-hidden transition-all">
          <button
            onClick={() => setSocialsOpen(!socialsOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-gray-100/50 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <FaShareAlt className="text-xs text-indigo-500 flex-shrink-0" />
              <span className="text-xs font-bold text-gray-700">
                Socials
              </span>
              <span className="text-[10px] text-gray-500">
                ({Object.keys(socialLinks || {}).filter((k) => socialLinks[k]).length} active)
              </span>
            </div>
            {socialsOpen ? <FaChevronUp className="text-xs text-gray-500" /> : <FaChevronDown className="text-xs text-gray-500" />}
          </button>

          {socialsOpen && (
            <div className="p-3 pt-0 space-y-2 border-t border-gray-100 mt-1">
              {['instagram', 'tiktok', 'youtube', 'twitter', 'linkedin', 'spotify', 'github', 'discord'].map((plat) => (
                <div key={plat} className="flex items-center gap-2">
                  <span className="w-16 text-[10px] font-bold uppercase tracking-wider text-gray-500 capitalize">
                    {plat === 'twitter' ? 'X' : plat}
                  </span>
                  <input
                    type="text"
                    value={socialLinks?.[plat] || ''}
                    onChange={(e) => setSocialLinks({ ...socialLinks, [plat]: e.target.value })}
                    placeholder={`https://${plat}.com/...`}
                    className="flex-1 px-2.5 py-1 text-xs bg-white border border-gray-200 rounded-lg outline-hidden focus:ring-1 focus:ring-indigo-500 text-gray-700 font-mono"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 4. Collapsible Announcement Banner ── */}
        <div className="border border-gray-200 rounded-2xl bg-gray-50 overflow-hidden transition-all">
          <button
            onClick={() => setAnnounceOpen(!announceOpen)}
            className="w-full flex items-center justify-between p-3 text-left hover:bg-gray-100/50 transition-colors"
          >
            <div className="flex items-center gap-2 min-w-0">
              <FaBell className="text-xs text-amber-500 flex-shrink-0" />
              <span className="text-xs font-bold text-gray-700">
                Announce
              </span>
              {theme?.announcement_active && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              )}
            </div>
            <span className="text-[10px] font-bold text-indigo-600 hover:underline">
              {theme?.announcement_active ? 'Edit' : 'Add'}
            </span>
          </button>

          {announceOpen && (
            <div className="p-3 pt-0 space-y-2.5 border-t border-gray-100 mt-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-600">Show Top Banner</span>
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
                  className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-gray-900"
                />
              </div>
              <div>
                <input
                  type="url"
                  value={theme?.announcement_url || ''}
                  onChange={(e) => setTheme({ ...theme, announcement_url: e.target.value })}
                  placeholder="https://..."
                  className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-gray-900 font-mono"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── 5. Blocks Header & Quick Paste Bar ── */}
        <div className="pt-2">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-gray-900">Blocks</span>
              <span className="text-[10px] font-bold text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded-full">
                {blocks.length}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={onOpenAddModal}
                className="px-2.5 py-1 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors flex items-center gap-1"
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
              className="w-full pl-8 pr-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-gray-900 placeholder-gray-400 transition-all shadow-2xs"
            />
            <FaLink className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-[11px]" />
          </form>

          {/* Draggable Block Cards List */}
          <div className="space-y-2">
            {blocks.map((block, idx) => {
              const isDragging = draggedIdx === idx;
              const isOver = dragOverIdx === idx;
              const isFolder = block.type === 'folder' || block.type === 'tab_group';

              return (
                <div
                  key={block.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragOver={(e) => handleDragOver(e, idx)}
                  onDragEnd={handleDragEnd}
                  className={`group relative rounded-2xl border transition-all duration-150 ${
                    isDragging
                      ? 'opacity-30 border-indigo-400 bg-indigo-50/50'
                      : isOver
                      ? 'border-indigo-500 bg-indigo-50/40 translate-y-1'
                      : isFolder
                      ? 'border-amber-200 bg-amber-50'
                      : block.active !== false
                      ? 'border-gray-200 bg-white hover:border-gray-300 shadow-2xs'
                      : 'border-gray-200/50 bg-gray-50 opacity-60'
                  }`}
                >
                  <div className="p-2.5 flex items-center gap-2.5">
                    {/* Drag Handle */}
                    <div className="cursor-grab active:cursor-grabbing text-gray-600 hover:text-gray-500 transition-colors p-0.5">
                      <FaGripVertical className="text-xs" />
                    </div>

                    {/* Block Content Info */}
                    <div
                      onClick={() => onOpenBlockEditor(block)}
                      className="flex-1 min-w-0 cursor-pointer"
                    >
                      <div className="flex items-center gap-1.5">
                        {isFolder ? (
                          <FaFolder className="text-amber-500 text-xs flex-shrink-0" />
                        ) : block.type === 'link' ? (
                          <FaLink className="text-indigo-500 text-[10px] flex-shrink-0" />
                        ) : block.type === 'embed' ? (
                          <FaPlay className="text-rose-500 text-[10px] flex-shrink-0" />
                        ) : block.type === 'feed_grid' ? (
                          <FaThLarge className="text-purple-500 text-[10px] flex-shrink-0" />
                        ) : (
                          <FaEnvelope className="text-emerald-500 text-[10px] flex-shrink-0" />
                        )}

                        <span className="text-xs font-bold text-gray-900 truncate">
                          {block.title || block.headline || block.url || (isFolder ? 'New Folder' : 'Untitled Link')}
                        </span>

                        {isFolder && (
                          <span className="text-[10px] font-black uppercase text-amber-600 bg-amber-50 px-1.5 py-0.2 rounded-md">
                            Folder
                          </span>
                        )}
                      </div>

                      {block.subtitle && (
                        <p className="text-[11px] text-gray-500 truncate mt-0.5">{block.subtitle}</p>
                      )}
                      
                      {/* Sub-actions */}
                      <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-500">
                        <button
                          onClick={(e) => { e.stopPropagation(); onDeleteBlock(block.id); }}
                          className="hover:text-rose-600 p-0.5"
                          title="Delete"
                        >
                          <FaTrash className="text-[9px]" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onToggleBlockActive(block.id); }}
                          className="hover:text-gray-600 p-0.5"
                          title={block.active !== false ? 'Hide Block' : 'Show Block'}
                        >
                          {block.active !== false ? <FaEye className="text-[10px]" /> : <FaEyeSlash className="text-[10px] text-rose-500" />}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onDuplicateBlock(block); }}
                          className="hover:text-gray-600 p-0.5"
                          title="Duplicate"
                        >
                          <FaCopy className="text-[9px]" />
                        </button>
                        {block.click_count !== undefined && block.click_count > 0 && (
                          <span className="ml-auto text-emerald-600 font-bold flex items-center gap-0.5">
                            <FaChartLine className="text-[8px]" /> {block.click_count}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Thumbnail or Folder Toggle */}
                    {isFolder ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleFolderExpanded(block.id); }}
                        className="p-1.5 rounded-lg bg-amber-50 hover:bg-amber-500/20 text-amber-600 text-xs transition-colors flex-shrink-0"
                        title={block.is_expanded ? 'Collapse Folder' : 'Expand Folder'}
                      >
                        {block.is_expanded ? <FaChevronUp /> : <FaChevronDown />}
                      </button>
                    ) : block.media_url ? (
                      <div
                        onClick={() => onOpenBlockEditor(block)}
                        className="w-10 h-10 rounded-xl overflow-hidden bg-gray-100 border border-gray-200 flex-shrink-0 cursor-pointer"
                      >
                        <img src={block.media_url} alt="" className="w-full h-full object-cover" />
                      </div>
                    ) : (
                      <button
                        onClick={() => onOpenBlockEditor(block)}
                        className="w-7 h-7 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-500 transition-colors flex-shrink-0"
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
          <div className="pt-4 border-t border-gray-100">
            <button
              onClick={() => setTrashOpen(!trashOpen)}
              className="w-full flex items-center justify-between text-xs text-gray-500 hover:text-gray-500 py-1"
            >
              <span className="flex items-center gap-1.5">
                <FaTrash className="text-[10px]" /> Deleted Blocks ({deletedBlocks.length})
              </span>
              {trashOpen ? <FaChevronUp className="text-[10px]" /> : <FaChevronDown className="text-[10px]" />}
            </button>

            {trashOpen && (
              <div className="space-y-1.5 mt-2 bg-gray-50 p-2 rounded-xl">
                {deletedBlocks.map((del) => (
                  <div key={del.id} className="flex items-center justify-between text-xs p-1.5 bg-white rounded-lg border border-gray-200/60">
                    <span className="truncate font-medium text-gray-600 text-[11px]">
                      {del.title || del.url || 'Deleted Block'}
                    </span>
                    <button
                      onClick={() => onRestoreBlock(del)}
                      className="text-indigo-600 font-bold hover:underline text-[10px]"
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

      {/* ── 7. Add Sub-Page Modal ── */}
      {addPageModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-gray-200 rounded-3xl max-w-sm w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                <FaSitemap className="text-indigo-500 text-xs" /> Add New Sub-Page
              </h3>
              <button onClick={() => setAddPageModalOpen(false)} className="text-gray-500 hover:text-gray-500">
                <FaTimes className="text-xs" />
              </button>
            </div>

            <form onSubmit={handleCreatePageSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  Page Title
                </label>
                <input
                  type="text"
                  value={newPageTitle}
                  onChange={(e) => {
                    setNewPageTitle(e.target.value);
                    if (!newPageSlug) setNewPageSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '-'));
                  }}
                  placeholder="e.g. Music & Tour, Merch Shop"
                  className="w-full px-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 font-bold text-gray-900"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">
                  URL Path Slug
                </label>
                <div className="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-xs font-mono">
                  <span className="text-gray-500">/</span>
                  <input
                    type="text"
                    value={newPageSlug}
                    onChange={(e) => setNewPageSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                    placeholder="music"
                    className="bg-transparent outline-hidden flex-1 text-gray-900"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setAddPageModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-bold text-gray-500 hover:bg-gray-100 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newPageTitle.trim()}
                  className="px-4 py-1.5 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-colors disabled:opacity-50"
                >
                  Create Page
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
