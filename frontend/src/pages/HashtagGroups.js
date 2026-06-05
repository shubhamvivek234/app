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
  FaBolt,
  FaCheck,
  FaCopy,
  FaEdit,
  FaFilter,
  FaHashtag,
  FaLayerGroup,
  FaMagic,
  FaPlus,
  FaSearch,
  FaSpinner,
  FaTrash,
} from 'react-icons/fa';
import { toast } from 'sonner';

const PLATFORMS = [
  {
    value: 'instagram',
    label: 'Instagram',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    active: 'bg-rose-600 text-white border-rose-600',
    idle: 'bg-white text-rose-700 border-rose-200 hover:bg-rose-50',
    dot: 'bg-rose-500',
  },
  {
    value: 'tiktok',
    label: 'TikTok',
    badge: 'bg-slate-100 text-slate-700 border-slate-200',
    active: 'bg-slate-900 text-white border-slate-900',
    idle: 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50',
    dot: 'bg-slate-800',
  },
  {
    value: 'youtube',
    label: 'YouTube',
    badge: 'bg-red-50 text-red-700 border-red-200',
    active: 'bg-red-600 text-white border-red-600',
    idle: 'bg-white text-red-700 border-red-200 hover:bg-red-50',
    dot: 'bg-red-500',
  },
];

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'alpha', label: 'A-Z' },
  { value: 'tags', label: 'Most tags' },
];

const DEFAULT_COUNT = 6;

const getPlatform = (value) => PLATFORMS.find((platform) => platform.value === value);

const parseHashtags = (raw) =>
  raw
    .split(/[\s,\n]+/)
    .map((tag) => tag.trim().replace(/^#+/, ''))
    .filter(Boolean)
    .map((tag) => `#${tag}`);

const formatUpdatedAt = (value) => {
  if (!value) return 'Updated recently';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Updated recently';
  return `Updated ${formatDistanceToNow(date, { addSuffix: true })}`;
};

const copyText = async (value, successMessage) => {
  try {
    await navigator.clipboard.writeText(value);
    toast.success(successMessage);
  } catch {
    toast.error('Copy failed');
  }
};

const FilterPills = ({ value, onChange, includeAll = false }) => {
  const options = includeAll
    ? [{ value: '', label: 'All platforms', active: 'bg-emerald-600 text-white border-emerald-600', idle: 'bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50' }, ...PLATFORMS]
    : PLATFORMS;

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.value || 'all'}
          type="button"
          onClick={() => onChange(option.value)}
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all active:scale-[0.98] ${
            value === option.value ? option.active : option.idle
          }`}
        >
          {option.dot ? <span className={`h-2 w-2 rounded-full ${option.dot}`} /> : null}
          {option.label}
        </button>
      ))}
    </div>
  );
};

const SortPills = ({ value, onChange }) => (
  <div className="flex flex-wrap gap-2">
    {SORT_OPTIONS.map((option) => (
      <button
        key={option.value}
        type="button"
        onClick={() => onChange(option.value)}
        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-all active:scale-[0.98] ${
          value === option.value
            ? 'border-slate-900 bg-slate-900 text-white'
            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
        }`}
      >
        {option.label}
      </button>
    ))}
  </div>
);

const TagChip = ({ tag, variant = 'default', onCopy }) => {
  const className =
    variant === 'result'
      ? 'border-violet-200 bg-white text-violet-700 hover:border-violet-600 hover:bg-violet-600 hover:text-white'
      : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700';

  return (
    <button
      type="button"
      onClick={() => onCopy(tag)}
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium transition-all active:scale-[0.98] ${className}`}
      title="Copy hashtag"
    >
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
        platform,
        hashtags: preview,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-[28px] border-slate-200 p-0">
        <div className="border-b border-slate-100 bg-slate-50/70 px-6 py-5">
          <DialogHeader className="text-left">
            <DialogTitle className="text-xl font-semibold text-slate-950">
              {mode === 'edit' ? 'Edit hashtag group' : 'Create hashtag group'}
            </DialogTitle>
            <DialogDescription>
              Save reusable tags by campaign, niche, or platform so the composer can insert them in one click.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="space-y-5 px-6 py-6">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Group name</span>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Launch hashtags"
                className="h-11 rounded-xl border-slate-200 bg-slate-50 text-slate-900"
                autoFocus
              />
            </label>
            <label className="grid gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Category</span>
              <Input
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                placeholder="Campaign, brand, evergreen"
                className="h-11 rounded-xl border-slate-200 bg-slate-50 text-slate-900"
              />
            </label>
          </div>

          <div className="grid gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Platform</span>
            <FilterPills value={platform} onChange={setPlatform} includeAll />
          </div>

          <label className="grid gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Hashtags</span>
            <textarea
              value={rawTags}
              onChange={(event) => setRawTags(event.target.value)}
              placeholder="#launch #creator #campaign"
              className="min-h-[132px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition-all placeholder:text-slate-300 focus:border-emerald-300 focus:bg-white focus:ring-2 focus:ring-emerald-200"
            />
            <span className="text-xs text-slate-400">Paste or type hashtags separated by spaces, commas, or new lines.</span>
          </label>

          <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-slate-900">Preview</p>
              <span className="text-xs text-slate-400">{preview.length} tags</span>
            </div>
            {preview.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {preview.map((tag) => (
                  <span key={tag} className="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-xs font-medium text-emerald-700">
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">Your cleaned hashtag set will appear here before saving.</p>
            )}
          </div>
        </div>

        <DialogFooter className="border-t border-slate-100 px-6 py-4 sm:justify-between sm:space-x-0">
          <p className="text-xs text-slate-400">Saved groups remain available in the composer and editor popovers.</p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)} className="text-slate-600">
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={saving} className="bg-emerald-600 text-white hover:bg-emerald-700">
              {saving ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Create group'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const GeneratorCard = ({ onSaveAsGroup }) => {
  const [topic, setTopic] = useState('');
  const [platform, setPlatform] = useState('instagram');
  const [hashtags, setHashtags] = useState([]);
  const [loading, setLoading] = useState(false);

  const activePlatform = getPlatform(platform);

  const handleGenerate = async () => {
    if (!topic.trim()) {
      toast.error('Describe your post first');
      return;
    }
    setLoading(true);
    try {
      const data = await generateHashtags(topic.trim(), platform || null, DEFAULT_COUNT);
      if (!data.hashtags?.length) {
        toast.error('No hashtags returned. Try a more specific topic.');
        setHashtags([]);
        return;
      }
      setHashtags(data.hashtags);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to generate hashtags');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-[32px] border border-emerald-100 bg-white shadow-[0_20px_60px_-30px_rgba(15,23,42,0.18)]">
      <div className="border-b border-emerald-100 bg-[linear-gradient(135deg,#f5fffb_0%,#ffffff_65%)] px-6 py-6 sm:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700">
              <FaBolt className="text-[10px]" />
              AI Generator
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Build reusable hashtag sets without losing the creative spark.</h1>
              <p className="max-w-2xl text-sm leading-6 text-slate-600">
                Generate a tight set for the post in front of you, then save the best combinations into clean, reusable libraries by campaign and platform.
              </p>
            </div>
          </div>
          <div className="grid min-w-[220px] grid-cols-2 gap-3 self-stretch">
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Output size</p>
              <p className="mt-2 text-2xl font-semibold text-slate-950">{DEFAULT_COUNT}</p>
              <p className="text-xs text-slate-500">optimized tags per generation</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Context</p>
              <p className="mt-2 text-sm font-semibold text-slate-950">{activePlatform?.label || 'All platforms'}</p>
              <p className="text-xs text-slate-500">current generation target</p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6 px-6 py-6 sm:px-8">
        <label className="grid gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Describe the post</span>
          <textarea
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) handleGenerate();
            }}
            className="min-h-[138px] w-full rounded-[24px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition-all placeholder:text-slate-300 focus:border-emerald-300 focus:bg-white focus:ring-2 focus:ring-emerald-200"
            placeholder="Morning routine reel for a wellness brand, highlighting breathwork, sunrise light, and a soft call-to-action."
          />
          <span className="text-xs text-slate-400">Press Command/Ctrl + Enter to generate quickly.</span>
        </label>

        <div className="grid gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Platform tuning</span>
          <FilterPills value={platform} onChange={setPlatform} />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleGenerate} disabled={loading} className="min-w-[180px] bg-slate-950 text-white hover:bg-slate-800">
            {loading ? <FaSpinner className="mr-2 animate-spin" /> : <FaMagic className="mr-2" />}
            {loading ? 'Generating…' : `Generate for ${activePlatform?.label || 'platform'}`}
          </Button>
          {hashtags.length > 0 ? (
            <Button variant="outline" onClick={handleGenerate} className="border-slate-200 text-slate-700">
              Regenerate
            </Button>
          ) : null}
        </div>

        <div className="rounded-[28px] border border-slate-200 bg-slate-50/70 p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-950">Generated set</p>
              <p className="text-sm text-slate-500">
                {hashtags.length > 0
                  ? `${hashtags.length} ready-to-use hashtags for ${activePlatform?.label || 'this platform'}.`
                  : 'Generate a set to review, copy, or save as a reusable group.'}
              </p>
            </div>
            {hashtags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => copyText(hashtags.join(' '), 'Copied all hashtags')}>
                  <FaCopy className="mr-2" /> Copy all
                </Button>
                <Button onClick={() => onSaveAsGroup(hashtags, platform)} className="bg-emerald-600 text-white hover:bg-emerald-700">
                  <FaPlus className="mr-2" /> Save as group
                </Button>
              </div>
            ) : null}
          </div>

          {loading ? (
            <div className="grid gap-2">
              <div className="h-10 rounded-full bg-white" />
              <div className="h-10 rounded-full bg-white" />
              <div className="h-10 rounded-full bg-white" />
            </div>
          ) : hashtags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {hashtags.map((tag) => (
                <TagChip key={tag} tag={tag} variant="result" onCopy={(value) => copyText(value, `Copied ${value}`)} />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-400">
              Your generated hashtags will land here once the prompt is specific enough to produce a clean set.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

const GroupCard = ({ group, onEdit, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  const visibleTags = expanded ? group.hashtags : group.hashtags.slice(0, 10);
  const hiddenCount = group.hashtags.length - visibleTags.length;
  const platform = getPlatform(group.platform);

  return (
    <article className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_14px_40px_-28px_rgba(15,23,42,0.3)] transition-all hover:border-emerald-200">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-slate-950">{group.name}</h3>
            {platform ? (
              <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${platform.badge}`}>
                <span className={`h-2 w-2 rounded-full ${platform.dot}`} />
                {platform.label}
              </span>
            ) : (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                All platforms
              </span>
            )}
            {group.category ? (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-500">
                {group.category}
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <span>{group.hashtags.length} tags</span>
            <span>{formatUpdatedAt(group.updated_at)}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full text-slate-500" onClick={() => copyText(group.hashtags.join(' '), 'Copied all hashtags')}>
            <FaCopy className="text-sm" />
          </Button>
          <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full text-slate-500" onClick={() => onEdit(group)}>
            <FaEdit className="text-sm" />
          </Button>
          <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full text-red-500 hover:text-red-600" onClick={() => onDelete(group)}>
            <FaTrash className="text-sm" />
          </Button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {visibleTags.map((tag) => (
          <TagChip key={tag} tag={tag} onCopy={(value) => copyText(value, `Copied ${value}`)} />
        ))}
        {hiddenCount > 0 ? (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 transition-all active:scale-[0.98]"
          >
            {expanded ? 'Show less' : `+${hiddenCount} more`}
          </button>
        ) : null}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-400">
        <span>Click any hashtag to copy individually.</span>
        <button type="button" onClick={() => copyText(group.hashtags.join(' '), 'Copied all hashtags')} className="font-semibold text-slate-600 transition-colors hover:text-emerald-700">
          Copy all
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
  const [search, setSearch] = useState('');
  const [platformFilter, setPlatformFilter] = useState('');
  const [sortBy, setSortBy] = useState('newest');

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

  const stats = useMemo(() => {
    const totalTags = groups.reduce((count, group) => count + (group.hashtags?.length || 0), 0);
    const platformScoped = groups.filter((group) => group.platform).length;
    return {
      totalGroups: groups.length,
      totalTags,
      platformScoped,
    };
  }, [groups]);

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
      <div className="mx-auto max-w-7xl space-y-8 px-4 py-1 sm:px-6 lg:px-8">
        <section className="grid gap-8 xl:grid-cols-[minmax(0,1.1fr)_minmax(380px,0.9fr)]">
          <GeneratorCard
            onSaveAsGroup={(hashtags, platform) => {
              openCreateDialog({ hashtags, platform });
            }}
          />

          <section className="space-y-5">
            <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-[0_20px_50px_-32px_rgba(15,23,42,0.26)]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-2">
                  <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                    <FaLayerGroup className="text-[10px]" />
                    Saved library
                  </div>
                  <div>
                    <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Reusable hashtag groups</h2>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      Keep your strongest tag combinations organized by platform, campaign, and topic.
                    </p>
                  </div>
                </div>

                <Button onClick={() => openCreateDialog()} className="bg-slate-950 text-white hover:bg-slate-800">
                  <FaPlus className="mr-2" /> New group
                </Button>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Groups</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950">{stats.totalGroups}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Saved tags</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950">{stats.totalTags}</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Platform specific</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950">{stats.platformScoped}</p>
                </div>
              </div>
            </div>

            <div className="rounded-[32px] border border-slate-200 bg-white p-6 shadow-[0_20px_50px_-32px_rgba(15,23,42,0.26)]">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
                <FaFilter className="text-slate-400" />
                Library controls
              </div>

              <div className="mt-4 grid gap-4">
                <label className="grid gap-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Search</span>
                  <div className="relative">
                    <FaSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-300" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Find by group name, category, or hashtag"
                      className="h-11 rounded-xl border-slate-200 bg-slate-50 pl-9"
                    />
                  </div>
                </label>

                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Platform filter</span>
                    <FilterPills value={platformFilter} onChange={setPlatformFilter} includeAll />
                  </div>
                  <div className="grid gap-2">
                    <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Sort</span>
                    <SortPills value={sortBy} onChange={setSortBy} />
                  </div>
                </div>
              </div>
            </div>
          </section>
        </section>

        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Saved groups</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
                {filteredGroups.length} {filteredGroups.length === 1 ? 'group' : 'groups'} in view
              </h2>
            </div>
            {(search || platformFilter || sortBy !== 'newest') ? (
              <button
                type="button"
                onClick={() => {
                  setSearch('');
                  setPlatformFilter('');
                  setSortBy('newest');
                }}
                className="text-sm font-medium text-slate-500 transition-colors hover:text-slate-900"
              >
                Reset filters
              </button>
            ) : null}
          </div>

          {loading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="rounded-[28px] border border-slate-200 bg-white p-5">
                  <div className="h-5 w-1/2 rounded bg-slate-100" />
                  <div className="mt-3 h-4 w-1/3 rounded bg-slate-100" />
                  <div className="mt-5 flex flex-wrap gap-2">
                    <div className="h-8 w-20 rounded-full bg-slate-100" />
                    <div className="h-8 w-24 rounded-full bg-slate-100" />
                    <div className="h-8 w-16 rounded-full bg-slate-100" />
                  </div>
                </div>
              ))}
            </div>
          ) : filteredGroups.length === 0 ? (
            <div className="rounded-[32px] border border-dashed border-slate-200 bg-white px-6 py-16 text-center shadow-[0_20px_40px_-32px_rgba(15,23,42,0.16)]">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                <FaHashtag className="text-lg" />
              </div>
              <h3 className="mt-5 text-lg font-semibold text-slate-950">
                {groups.length === 0 ? 'No saved groups yet' : 'No groups match these filters'}
              </h3>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
                {groups.length === 0
                  ? 'Generate a set above or create one manually to build your hashtag library.'
                  : 'Try a different search, platform filter, or sort view to surface the groups you need.'}
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <Button onClick={() => openCreateDialog()} className="bg-slate-950 text-white hover:bg-slate-800">
                  <FaPlus className="mr-2" /> Create group
                </Button>
                {groups.length > 0 ? (
                  <Button variant="outline" onClick={() => {
                    setSearch('');
                    setPlatformFilter('');
                    setSortBy('newest');
                  }}>
                    Clear filters
                  </Button>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filteredGroups.map((group) => (
                <GroupCard key={group.id} group={group} onEdit={openEditDialog} onDelete={setDeleteGroup} />
              ))}
            </div>
          )}
        </section>
      </div>

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

      <AlertDialog open={Boolean(deleteGroup)} onOpenChange={(open) => !open && setDeleteGroup(null)}>
        <AlertDialogContent className="rounded-[28px] border-slate-200">
          <AlertDialogHeader className="text-left">
            <AlertDialogTitle>Delete hashtag group?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteGroup
                ? `This will permanently remove "${deleteGroup.name}" from your saved library and composer shortcuts.`
                : 'This action cannot be undone.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 hover:bg-red-700" onClick={handleDelete}>
              Delete group
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DashboardLayout>
  );
};

export default HashtagGroups;
