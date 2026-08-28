import React, { useEffect, useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getHashtagGroups,
  createHashtagGroup,
  updateHashtagGroup,
  deleteHashtagGroup,
  generateHashtags,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  FaCheck,
  FaCopy,
  FaEdit,
  FaHashtag,
  FaMagic,
  FaPlus,
  FaSearch,
  FaSpinner,
  FaTimes,
  FaTrash,
} from 'react-icons/fa';
import { toast } from 'sonner';

const PLATFORMS = [
  {
    value: 'instagram',
    label: 'Instagram',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    dot: 'bg-rose-500',
  },
  {
    value: 'tiktok',
    label: 'TikTok',
    badge: 'bg-slate-100 text-slate-800 border-slate-200',
    dot: 'bg-slate-700',
  },
  {
    value: 'youtube',
    label: 'YouTube',
    badge: 'bg-red-50 text-red-700 border-red-200',
    dot: 'bg-red-500',
  },
];

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'alpha', label: 'A-Z' },
  { value: 'tags', label: 'Most tags' },
];

const DEFAULT_COUNT = 8;

const getPlatform = (value) => PLATFORMS.find((p) => p.value === value);

const parseHashtags = (raw) =>
  raw
    .split(/[\s,\n]+/)
    .map((tag) => tag.trim().replace(/^#+/, ''))
    .filter(Boolean)
    .map((tag) => `#${tag}`);

const formatUpdatedAt = (value) => {
  if (!value) return 'recently';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'recently';
  return formatDistanceToNow(date, { addSuffix: true });
};

const copyText = async (value, successMessage) => {
  try {
    await navigator.clipboard.writeText(value);
    toast.success(successMessage);
  } catch {
    toast.error('Copy failed');
  }
};

const TagChip = ({ tag, onCopy }) => {
  const [copied, setCopied] = useState(false);

  const handleClick = () => {
    onCopy(tag);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all active:scale-95 ${
        copied
          ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
          : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-slate-100'
      }`}
      title="Click to copy hashtag"
    >
      {copied ? <FaCheck className="text-[10px]" /> : null}
      {tag}
    </button>
  );
};

const GroupDialog = ({ open, onOpenChange, initial, mode, onSave }) => {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [platform, setPlatform] = useState('');
  const [rawTags, setRawTags] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name || '');
    setCategory(initial?.category || '');
    setPlatform(initial?.platform || '');
    setRawTags((initial?.hashtags || []).join(' '));
  }, [initial, open]);

  const preview = useMemo(() => parseHashtags(rawTags), [rawTags]);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('Group name is required');
      return;
    }
    if (preview.length === 0) {
      toast.error('Add at least one hashtag');
      return;
    }
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        category: category.trim(),
        platform: platform || null,
        hashtags: preview,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl rounded-2xl border-slate-200 bg-white p-0 shadow-xl">
        <div className="border-b border-slate-100 px-6 py-5">
          <DialogHeader className="text-left">
            <DialogTitle className="text-lg font-bold text-slate-900">
              {mode === 'edit' ? 'Edit Hashtag Group' : 'Create Hashtag Group'}
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500">
              Save reusable tag collections for one-click insertion in the post composer.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-slate-700">Group Name *</span>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Daily Growth"
                className="h-10 rounded-xl border-slate-200 bg-slate-50 text-sm focus:border-black focus:bg-white"
                autoFocus
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-xs font-semibold text-slate-700">Category</span>
              <Input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g. Evergreen, Launch"
                className="h-10 rounded-xl border-slate-200 bg-slate-50 text-sm focus:border-black focus:bg-white"
              />
            </label>
          </div>

          <div className="grid gap-1.5">
            <span className="text-xs font-semibold text-slate-700">Platform</span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setPlatform('')}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold border transition ${
                  !platform
                    ? 'border-black bg-black text-white'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                All Platforms
              </button>
              {PLATFORMS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setPlatform(p.value)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold border transition flex items-center gap-1.5 ${
                    platform === p.value
                      ? 'border-black bg-black text-white'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <label className="grid gap-1.5">
            <span className="text-xs font-semibold text-slate-700">Hashtags *</span>
            <textarea
              value={rawTags}
              onChange={(e) => setRawTags(e.target.value)}
              placeholder="#growth #creator #marketing"
              className="min-h-[100px] w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-black focus:bg-white"
            />
            <span className="text-[11px] text-slate-400">Separate tags with spaces, commas, or new lines.</span>
          </label>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold text-slate-700">Preview</p>
              <span className="text-xs text-slate-500">{preview.length} tags</span>
            </div>
            {preview.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {preview.map((tag) => (
                  <span key={tag} className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-700">
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">Your clean tag pills will appear here.</p>
            )}
          </div>
        </div>

        <DialogFooter className="border-t border-slate-100 px-6 py-4">
          <div className="flex w-full items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-xs text-slate-600 hover:bg-slate-100">
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={saving} className="bg-black text-xs font-semibold text-white hover:bg-slate-800">
              {saving ? 'Saving…' : mode === 'edit' ? 'Save Changes' : 'Create Group'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const GroupCard = ({ group, onEdit, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  const visibleTags = expanded ? group.hashtags : group.hashtags.slice(0, 10);
  const hiddenCount = group.hashtags.length - visibleTags.length;
  const platform = getPlatform(group.platform);

  return (
    <article className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-slate-300 hover:shadow-md space-y-4">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-sm font-bold text-slate-900">{group.name}</h3>
              {platform ? (
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${platform.badge}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${platform.dot}`} />
                  {platform.label}
                </span>
              ) : (
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                  All Platforms
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400">
              {group.category ? `Category: ${group.category} · ` : ''}{group.hashtags.length} tags · updated {formatUpdatedAt(group.updated_at)}
            </p>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => copyText(group.hashtags.join(' '), 'Copied all hashtags')}
              className="p-1.5 rounded-lg text-slate-400 hover:text-black hover:bg-slate-100 transition"
              title="Copy all tags"
            >
              <FaCopy className="text-xs" />
            </button>
            <button
              onClick={() => onEdit(group)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-black hover:bg-slate-100 transition"
              title="Edit group"
            >
              <FaEdit className="text-xs" />
            </button>
            <button
              onClick={() => onDelete(group)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition"
              title="Delete group"
            >
              <FaTrash className="text-xs" />
            </button>
          </div>
        </div>

        <div className="mt-3.5 flex flex-wrap gap-1.5">
          {visibleTags.map((tag) => (
            <TagChip key={tag} tag={tag} onCopy={(val) => copyText(val, `Copied ${val}`)} />
          ))}
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition"
            >
              {expanded ? 'Show less' : `+${hiddenCount} more`}
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-400">
        <span>Click any tag to copy</span>
        <button
          type="button"
          onClick={() => copyText(group.hashtags.join(' '), 'Copied all hashtags')}
          className="font-semibold text-slate-700 hover:underline"
        >
          Copy all ({group.hashtags.length})
        </button>
      </div>
    </article>
  );
};

const HashtagGroups = () => {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState('create');
  const [editingGroup, setEditingGroup] = useState(null);
  const [deleteGroup, setDeleteGroup] = useState(null);

  // Filters & Search
  const [search, setSearch] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [sortBy, setSortBy] = useState('newest');

  // AI Generator Panel
  const [showGenerator, setShowGenerator] = useState(false);
  const [aiTopic, setAiTopic] = useState('');
  const [aiPlatform, setAiPlatform] = useState('instagram');
  const [aiGeneratedTags, setAiGeneratedTags] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);

  const load = async () => {
    try {
      const data = await getHashtagGroups();
      setGroups(data || []);
    } catch {
      toast.error('Failed to load hashtag groups');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleGenerate = async () => {
    if (!aiTopic.trim()) {
      toast.error('Describe your post topic first');
      return;
    }
    setAiLoading(true);
    try {
      const data = await generateHashtags(aiTopic.trim(), aiPlatform || null, DEFAULT_COUNT);
      if (!data.hashtags?.length) {
        toast.error('No hashtags returned. Try a more specific topic.');
        setAiGeneratedTags([]);
        return;
      }
      setAiGeneratedTags(data.hashtags);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to generate hashtags');
    } finally {
      setAiLoading(false);
    }
  };

  const filteredGroups = useMemo(() => {
    const query = search.trim().toLowerCase();
    let next = [...groups];

    if (platformFilter) {
      next = next.filter((group) => group.platform === platformFilter);
    }

    if (query) {
      next = next.filter((group) => {
        const haystack = [group.name, group.category, ...(group.hashtags || [])].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }

    if (sortBy === 'alpha') {
      next.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === 'tags') {
      next.sort((a, b) => (b.hashtags?.length || 0) - (a.hashtags?.length || 0));
    } else {
      next.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    }

    return next;
  }, [groups, platformFilter, search, sortBy]);

  const openCreateDialog = (initial = null) => {
    setDialogMode('create');
    setEditingGroup(initial);
    setDialogOpen(true);
  };

  const openEditDialog = (group) => {
    setDialogMode('edit');
    setEditingGroup(group);
    setDialogOpen(true);
  };

  const handleCreate = async (payload) => {
    try {
      const created = await createHashtagGroup(payload);
      setGroups((current) => [created, ...current]);
      setDialogOpen(false);
      setEditingGroup(null);
      toast.success('Group created');
    } catch {
      toast.error('Failed to create group');
    }
  };

  const handleUpdate = async (payload) => {
    if (!editingGroup?.id) return;
    try {
      const updated = await updateHashtagGroup(editingGroup.id, payload);
      setGroups((current) => current.map((group) => (group.id === editingGroup.id ? updated : group)));
      setDialogOpen(false);
      setEditingGroup(null);
      toast.success('Group updated');
    } catch {
      toast.error('Failed to update group');
    }
  };

  const handleDelete = async () => {
    if (!deleteGroup?.id) return;
    try {
      await deleteHashtagGroup(deleteGroup.id);
      setGroups((current) => current.filter((group) => group.id !== deleteGroup.id));
      setDeleteGroup(null);
      toast.success('Group deleted');
    } catch {
      toast.error('Failed to delete group');
    }
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-2 sm:px-6">
        {/* Clean Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold text-black">#</span>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">Hashtag Library</h1>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                {groups.length} {groups.length === 1 ? 'Group' : 'Groups'}
              </span>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Organize reusable hashtag sets by campaign and platform, or generate fresh sets with AI.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setShowGenerator((v) => !v)}
              className={`px-3.5 py-2 text-xs font-semibold rounded-xl border transition flex items-center gap-1.5 shadow-sm ${
                showGenerator
                  ? 'border-black bg-black text-white'
                  : 'border-slate-200 bg-white text-slate-800 hover:bg-slate-50'
              }`}
            >
              <FaMagic className="text-xs" />
              <span>AI Generator</span>
            </button>
            <Button
              onClick={() => openCreateDialog()}
              className="bg-black text-xs font-semibold text-white hover:bg-slate-800 rounded-xl px-4 py-2 shadow-sm"
            >
              <FaPlus className="mr-1.5 text-[10px]" /> New Group
            </Button>
          </div>
        </div>

        {/* Collapsible AI Generator Panel */}
        {showGenerator && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4 transition-all">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-black animate-pulse" />
                <h3 className="text-sm font-bold text-slate-900">Generate Hashtags with AI</h3>
                <span className="text-xs text-slate-400 hidden sm:inline">Describe your post topic</span>
              </div>
              <button
                onClick={() => setShowGenerator(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 transition"
              >
                <FaTimes className="text-xs" />
              </button>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Input
                  value={aiTopic}
                  onChange={(e) => setAiTopic(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleGenerate();
                  }}
                  placeholder="e.g. Morning coffee routine reel for a productivity creator"
                  className="h-10 rounded-xl border-slate-200 bg-slate-50 text-sm focus:border-black focus:bg-white"
                />
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={aiPlatform}
                  onChange={(e) => setAiPlatform(e.target.value)}
                  className="h-10 px-3 text-xs bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-medium outline-none"
                >
                  <option value="instagram">Instagram</option>
                  <option value="tiktok">TikTok</option>
                  <option value="youtube">YouTube</option>
                  <option value="">All Platforms</option>
                </select>
                <Button
                  onClick={handleGenerate}
                  disabled={aiLoading}
                  className="h-10 bg-black px-4 text-xs font-semibold text-white hover:bg-slate-800 rounded-xl"
                >
                  {aiLoading ? <FaSpinner className="mr-1.5 animate-spin text-xs" /> : <FaMagic className="mr-1.5 text-xs" />}
                  {aiLoading ? 'Generating…' : 'Generate'}
                </Button>
              </div>
            </div>

            {/* AI Results */}
            {aiGeneratedTags.length > 0 && (
              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  {aiGeneratedTags.map((tag) => (
                    <TagChip key={tag} tag={tag} onCopy={(val) => copyText(val, `Copied ${val}`)} />
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => copyText(aiGeneratedTags.join(' '), 'Copied all generated tags')}
                    className="border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 rounded-lg"
                  >
                    <FaCopy className="mr-1.5 text-[10px]" /> Copy All
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      openCreateDialog({ hashtags: aiGeneratedTags, platform: aiPlatform });
                    }}
                    className="bg-black text-xs font-semibold text-white hover:bg-slate-800 rounded-lg"
                  >
                    <FaPlus className="mr-1.5 text-[10px]" /> Save as Group
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Filter & Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-80">
            <FaSearch className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-xs" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by group name or tag..."
              className="h-9 pl-9 rounded-xl border-slate-200 bg-white text-xs text-slate-900 placeholder:text-slate-400 focus:border-black shadow-sm"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-end overflow-x-auto pb-1 sm:pb-0">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setPlatformFilter('')}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                  !platformFilter
                    ? 'bg-black text-white shadow-sm'
                    : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                All ({groups.length})
              </button>
              {PLATFORMS.map((p) => {
                const count = groups.filter((g) => g.platform === p.value).length;
                return (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setPlatformFilter(p.value)}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
                      platformFilter === p.value
                        ? 'bg-black text-white shadow-sm'
                        : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
                    {p.label} {count > 0 ? `(${count})` : ''}
                  </button>
                );
              })}
            </div>

            <div className="hidden md:flex items-center gap-1 pl-2 border-l border-slate-200">
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setSortBy(opt.value)}
                  className={`px-2.5 py-1 text-xs rounded-md font-medium transition ${
                    sortBy === opt.value
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Group Cards Grid */}
        {loading ? (
          <div className="grid gap-4 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="rounded-2xl border border-slate-200 bg-white p-5 animate-pulse space-y-3">
                <div className="h-4 w-1/3 rounded bg-slate-100" />
                <div className="h-3 w-1/4 rounded bg-slate-100" />
                <div className="flex flex-wrap gap-1.5 pt-2">
                  <div className="h-6 w-16 rounded-lg bg-slate-100" />
                  <div className="h-6 w-20 rounded-lg bg-slate-100" />
                  <div className="h-6 w-14 rounded-lg bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredGroups.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-14 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-50 text-slate-600">
              <FaHashtag className="text-base" />
            </div>
            <h3 className="mt-4 text-base font-bold text-slate-900">
              {groups.length === 0 ? 'No hashtag groups yet' : 'No matching groups found'}
            </h3>
            <p className="mx-auto mt-1.5 max-w-sm text-xs text-slate-500">
              {groups.length === 0
                ? 'Create reusable hashtag groups manually or generate a set using the AI Generator.'
                : 'Try adjusting your search query or platform filter to see more groups.'}
            </p>
            <div className="mt-5 flex justify-center gap-2">
              <Button
                onClick={() => openCreateDialog()}
                className="bg-black text-xs font-semibold text-white hover:bg-slate-800 rounded-xl px-4 py-2"
              >
                <FaPlus className="mr-1.5 text-[10px]" /> Create Group
              </Button>
              {groups.length > 0 && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setSearch('');
                    setPlatformFilter('');
                    setSortBy('newest');
                  }}
                  className="border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 rounded-xl"
                >
                  Clear Filters
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {filteredGroups.map((group) => (
              <GroupCard
                key={group.id}
                group={group}
                onEdit={openEditDialog}
                onDelete={setDeleteGroup}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create / Edit Dialog */}
      <GroupDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setEditingGroup(null);
        }}
        initial={editingGroup}
        mode={dialogMode}
        onSave={dialogMode === 'edit' ? handleUpdate : handleCreate}
      />

      {/* Delete Confirmation Alert Dialog */}
      <AlertDialog open={Boolean(deleteGroup)} onOpenChange={(open) => !open && setDeleteGroup(null)}>
        <AlertDialogContent className="rounded-2xl border-slate-200 bg-white">
          <AlertDialogHeader className="text-left">
            <AlertDialogTitle className="text-base font-bold text-slate-900">
              Delete hashtag group?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-xs text-slate-500">
              {deleteGroup
                ? `This will permanently remove "${deleteGroup.name}" from your saved library.`
                : 'This action cannot be undone.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="text-xs">Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 text-xs text-white hover:bg-red-700" onClick={handleDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DashboardLayout>
  );
};

export default HashtagGroups;
