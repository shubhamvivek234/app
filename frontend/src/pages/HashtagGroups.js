import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getHashtagGroups, createHashtagGroup, updateHashtagGroup, deleteHashtagGroup, generateHashtags } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FaHashtag, FaEdit, FaTrash, FaPlus, FaTimes, FaCheck,
  FaCopy, FaMagic, FaSpinner, FaLayerGroup,
} from 'react-icons/fa';
import { toast } from 'sonner';

// ── Platform config (only 3 platforms) ───────────────────────────────────────
const PLATFORMS = [
  {
    value: 'instagram',
    label: 'Instagram',
    emoji: '📸',
    color: 'bg-pink-50 text-pink-600 border-pink-200',
    active: 'bg-pink-500 text-white border-pink-500',
    badge: 'bg-pink-50 text-pink-600',
  },
  {
    value: 'tiktok',
    label: 'TikTok',
    emoji: '🎵',
    color: 'bg-gray-50 text-gray-800 border-gray-200',
    active: 'bg-gray-900 text-white border-gray-900',
    badge: 'bg-gray-100 text-gray-700',
  },
  {
    value: 'youtube',
    label: 'YouTube',
    emoji: '▶',
    color: 'bg-red-50 text-red-600 border-red-200',
    active: 'bg-red-500 text-white border-red-500',
    badge: 'bg-red-50 text-red-600',
  },
];

const getPlatform = (value) => PLATFORMS.find((p) => p.value === value);

// ── Platform pill toggle (used in both form & generator) ─────────────────────
const PlatformPills = ({ value, onChange, includeAll = false }) => {
  const allOption = { value: '', label: 'Any', emoji: '🌐', active: 'bg-green-500 text-white border-green-500', color: 'bg-green-50 text-green-700 border-green-200' };
  const options = includeAll ? [allOption, ...PLATFORMS] : PLATFORMS;

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => onChange(p.value)}
          className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
            value === p.value ? p.active : p.color + ' hover:opacity-80'
          }`}
        >
          <span>{p.emoji}</span>
          {p.label}
        </button>
      ))}
    </div>
  );
};

// ── Parse hashtag text into a clean array ─────────────────────────────────────
const parseHashtags = (raw) =>
  raw
    .split(/[\s,\n]+/)
    .map((t) => t.trim().replace(/^#+/, ''))
    .filter(Boolean)
    .map((t) => `#${t}`);

// ── Tag chip ──────────────────────────────────────────────────────────────────
const TagChip = ({ tag, onCopy, variant = 'default' }) => {
  const [copied, setCopied] = useState(false);
  const handleClick = () => {
    onCopy(tag);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  const base =
    variant === 'green'
      ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100'
      : 'bg-white text-gray-700 border-gray-200 hover:bg-green-50 hover:border-green-300 hover:text-green-700';

  return (
    <span
      onClick={handleClick}
      title="Click to copy"
      className={`inline-flex items-center gap-1 text-xs border rounded-full px-2.5 py-1 cursor-pointer transition-all select-none ${base}`}
    >
      {copied ? <FaCheck className="text-[10px] text-green-500" /> : null}
      {tag}
    </span>
  );
};

// ── Inline form for creating / editing a group ────────────────────────────────
const GroupForm = ({ initial, onSave, onCancel }) => {
  const [name, setName]         = useState(initial?.name || '');
  const [rawTags, setRawTags]   = useState(initial?.hashtags?.join(' ') || '');
  const [category, setCategory] = useState(initial?.category || '');
  const [platform, setPlatform] = useState(initial?.platform || '');
  const [saving, setSaving]     = useState(false);

  const preview = parseHashtags(rawTags);

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Group name is required'); return; }
    if (preview.length === 0) { toast.error('Add at least one hashtag'); return; }
    setSaving(true);
    try {
      await onSave({ name: name.trim(), hashtags: preview, category: category.trim(), platform });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-4">
      <h3 className="text-sm font-semibold text-gray-800">
        {initial?.name ? 'Edit Group' : 'New Hashtag Group'}
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <Input
          placeholder="Group name (e.g. Travel vibes)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="text-sm bg-gray-50 border-gray-200 focus:bg-white"
          autoFocus
        />
        <Input
          placeholder="Category (optional)"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="text-sm bg-gray-50 border-gray-200 focus:bg-white"
        />
      </div>

      {/* Platform pills */}
      <div>
        <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Platform</p>
        <PlatformPills value={platform} onChange={setPlatform} includeAll />
      </div>

      {/* Hashtag input */}
      <div>
        <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Hashtags</p>
        <textarea
          className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-green-400 placeholder:text-gray-300 text-gray-800 min-h-[72px] bg-gray-50 focus:bg-white transition-colors"
          placeholder="#travel #wanderlust #adventure (space, comma or newline)"
          value={rawTags}
          onChange={(e) => setRawTags(e.target.value)}
        />
      </div>

      {/* Preview chips */}
      {preview.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {preview.map((tag) => (
            <span key={tag} className="inline-block text-xs bg-green-50 text-green-700 border border-green-200 rounded-full px-2.5 py-1">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button size="sm" onClick={handleSave} disabled={saving} className="bg-green-500 hover:bg-green-600 text-white gap-1.5">
          <FaCheck className="text-xs" />
          {saving ? 'Saving…' : 'Save Group'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} className="text-gray-500 hover:text-gray-700 gap-1.5">
          <FaTimes className="text-xs" />
          Cancel
        </Button>
      </div>
    </div>
  );
};

// ── Single group card ─────────────────────────────────────────────────────────
const GroupCard = ({ group, onEdit, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  const MAX_PREVIEW = 8;
  const visible = expanded ? group.hashtags : group.hashtags.slice(0, MAX_PREVIEW);
  const extra   = group.hashtags.length - MAX_PREVIEW;
  const platform = getPlatform(group.platform);

  const handleCopyAll = () => {
    navigator.clipboard.writeText(group.hashtags.join(' '));
    toast.success('All hashtags copied!');
  };

  const handleCopyTag = (tag) => {
    navigator.clipboard.writeText(tag);
    toast.success(`Copied ${tag}`);
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 hover:border-gray-300 hover:shadow-md transition-all group">
      {/* Card header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-green-50 border border-green-100 flex items-center justify-center flex-shrink-0">
            <FaHashtag className="text-green-500 text-xs" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 text-sm truncate leading-tight">{group.name}</p>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span className="text-xs text-gray-400">{group.hashtags.length} tags</span>
              {group.category && (
                <span className="text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-px">{group.category}</span>
              )}
              {platform && (
                <span className={`text-xs rounded-full px-2 py-px font-medium ${platform.badge}`}>
                  {platform.emoji} {platform.label}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopyAll}
            className="p-1.5 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
            title="Copy all hashtags"
          >
            <FaCopy className="text-xs" />
          </button>
          <button
            onClick={() => onEdit(group)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
            title="Edit group"
          >
            <FaEdit className="text-xs" />
          </button>
          <button
            onClick={() => onDelete(group)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
            title="Delete group"
          >
            <FaTrash className="text-xs" />
          </button>
        </div>
      </div>

      {/* Tag chips */}
      <div className="flex flex-wrap gap-1.5">
        {visible.map((tag) => (
          <TagChip key={tag} tag={tag} onCopy={handleCopyTag} />
        ))}
        {!expanded && extra > 0 && (
          <button
            onClick={() => setExpanded(true)}
            className="text-xs text-green-600 hover:text-green-700 px-2.5 py-1 rounded-full border border-green-200 bg-green-50 hover:bg-green-100 transition-colors font-medium"
          >
            +{extra} more
          </button>
        )}
        {expanded && (
          <button
            onClick={() => setExpanded(false)}
            className="text-xs text-gray-400 hover:text-gray-600 px-2.5 py-1 rounded-full border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            show less
          </button>
        )}
      </div>

      {/* Copy all footer (always visible) */}
      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
        <span className="text-xs text-gray-400">Click any tag to copy</span>
        <button
          onClick={handleCopyAll}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-green-600 transition-colors font-medium"
        >
          <FaCopy className="text-[10px]" /> Copy all
        </button>
      </div>
    </div>
  );
};

// ── AI Hashtag Generator ──────────────────────────────────────────────────────
const DEFAULT_HASHTAG_COUNT = 6;

const HashtagGenerator = ({ onSaveAsGroup }) => {
  const [topic, setTopic]       = useState('');
  const [platform, setPlatform] = useState('instagram');
  const [loading, setLoading]   = useState(false);
  const [hashtags, setHashtags] = useState([]);

  const handleGenerate = async () => {
    if (!topic.trim()) { toast.error('Describe your post first'); return; }
    setLoading(true);
    setHashtags([]);
    try {
      const data = await generateHashtags(topic.trim(), platform || null, DEFAULT_HASHTAG_COUNT);
      if (!data.hashtags || data.hashtags.length === 0) {
        toast.error('No hashtags returned — try a different topic');
      } else {
        setHashtags(data.hashtags);
        toast.success(`${data.hashtags.length} hashtags generated!`);
      }
    } catch {
      toast.error('Failed to generate hashtags — please try again');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyAll = () => {
    navigator.clipboard.writeText(hashtags.join(' '));
    toast.success('All hashtags copied to clipboard');
  };

  const handleCopyTag = (tag) => {
    navigator.clipboard.writeText(tag);
    toast.success(`Copied ${tag}`);
  };

  const activePlatform = getPlatform(platform);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header band */}
      <div className="bg-gradient-to-r from-green-500 to-emerald-400 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
            <FaMagic className="text-white text-sm" />
          </div>
          <div>
            <h2 className="text-white font-semibold text-base leading-tight">Social Media Hashtag Generator</h2>
            <p className="text-green-100 text-xs mt-0.5">Describe your post — AI finds the trending hashtags for you</p>
          </div>
        </div>
      </div>

      <div className="p-6 space-y-5">
        {/* Topic input */}
        <div>
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 block">
            What's your post about?
          </label>
          <textarea
            className="w-full text-sm border border-gray-200 rounded-xl px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-green-400 placeholder:text-gray-300 text-gray-800 min-h-[88px] bg-gray-50 focus:bg-white transition-colors"
            placeholder='e.g. "Morning yoga routine on the beach at sunrise" or "Launching our new eco-friendly coffee brand"'
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleGenerate(); }}
          />
          <p className="text-xs text-gray-400 mt-1.5">Press ⌘+Enter to generate</p>
        </div>

        {/* Platform row */}
        <div>
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 block">Platform</label>
          <PlatformPills value={platform} onChange={setPlatform} />
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={loading}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold transition-all ${
            loading
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-green-500 hover:bg-green-600 text-white shadow-sm hover:shadow-md active:scale-[0.98]'
          }`}
        >
          {loading ? (
            <><FaSpinner className="animate-spin text-xs" /> Generating…</>
          ) : (
            <><FaMagic className="text-xs" /> Generate Hashtags{activePlatform ? ` for ${activePlatform.label}` : ''}</>
          )}
        </button>

        {/* Results */}
        {hashtags.length > 0 && (
          <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-gray-800">{hashtags.length} hashtags</span>
                {activePlatform && (
                  <span className={`text-xs rounded-full px-2.5 py-0.5 font-medium ${activePlatform.badge}`}>
                    {activePlatform.emoji} {activePlatform.label}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopyAll}
                  className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-green-600 border border-gray-200 hover:border-green-300 bg-white rounded-lg px-3 py-1.5 transition-colors font-medium"
                >
                  <FaCopy className="text-[10px]" /> Copy All
                </button>
                <button
                  onClick={() => onSaveAsGroup(hashtags, platform)}
                  className="flex items-center gap-1.5 text-xs text-white bg-green-500 hover:bg-green-600 rounded-lg px-3 py-1.5 transition-colors font-medium"
                >
                  <FaPlus className="text-[10px]" /> Save as Group
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {hashtags.map((tag) => (
                <TagChip key={tag} tag={tag} onCopy={handleCopyTag} variant="green" />
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-3">Click any hashtag to copy it individually</p>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
const HashtagGroups = () => {
  const [groups, setGroups]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const [showNew, setShowNew]         = useState(false);
  const [editingId, setEditingId]     = useState(null);
  const [prefillTags, setPrefillTags] = useState(null);

  const load = async () => {
    try {
      const data = await getHashtagGroups();
      setGroups(data);
    } catch {
      toast.error('Failed to load hashtag groups');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (groupData) => {
    try {
      const created = await createHashtagGroup(groupData);
      setGroups((prev) => [created, ...prev]);
      setShowNew(false);
      toast.success('Group created!');
    } catch {
      toast.error('Failed to create group');
    }
  };

  const handleUpdate = async (id, data) => {
    try {
      const updated = await updateHashtagGroup(id, data);
      setGroups((prev) => prev.map((g) => (g.id === id ? updated : g)));
      setEditingId(null);
      toast.success('Group updated!');
    } catch {
      toast.error('Failed to update group');
    }
  };

  const handleDelete = async (group) => {
    if (!window.confirm(`Delete "${group.name}"? This cannot be undone.`)) return;
    try {
      await deleteHashtagGroup(group.id);
      setGroups((prev) => prev.filter((g) => g.id !== group.id));
      toast.success('Group deleted');
    } catch {
      toast.error('Failed to delete group');
    }
  };

  const handleSaveGeneratedAsGroup = (hashtags, platform) => {
    setPrefillTags({ hashtags, platform });
    setShowNew(true);
    setEditingId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCreateWithPrefill = async (groupData) => {
    await handleCreate(groupData);
    setPrefillTags(null);
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto">

        {/* ── Page header ── */}
        <div className="flex items-start justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-green-50 border border-green-100 flex items-center justify-center flex-shrink-0">
              <FaLayerGroup className="text-green-500 text-base" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 leading-tight">Hashtag Groups</h1>
              <p className="text-sm text-gray-500 mt-0.5">
                Reusable hashtag sets — insert with one click while composing.
              </p>
            </div>
          </div>
          {!showNew && (
            <Button
              onClick={() => { setShowNew(true); setEditingId(null); }}
              className="bg-green-500 hover:bg-green-600 text-white gap-2 shadow-sm"
            >
              <FaPlus className="text-xs" />
              New Group
            </Button>
          )}
        </div>

        {/* ── New group form ── */}
        {showNew && (
          <div className="mb-6">
            <GroupForm
              initial={prefillTags ? { hashtags: prefillTags.hashtags, platform: prefillTags.platform } : undefined}
              onSave={prefillTags ? handleCreateWithPrefill : handleCreate}
              onCancel={() => { setShowNew(false); setPrefillTags(null); }}
            />
          </div>
        )}

        {/* ── Groups section ── */}
        {loading ? (
          <div className="flex items-center justify-center py-20 gap-2 text-gray-400 text-sm">
            <FaSpinner className="animate-spin" /> Loading groups…
          </div>
        ) : groups.length === 0 && !showNew ? (
          <div className="text-center py-20 bg-white rounded-2xl border border-dashed border-gray-200">
            <div className="w-14 h-14 rounded-2xl bg-green-50 border border-green-100 flex items-center justify-center mx-auto mb-4">
              <FaHashtag className="text-green-400 text-xl" />
            </div>
            <p className="text-gray-700 font-semibold mb-1">No hashtag groups yet</p>
            <p className="text-gray-400 text-sm mb-5 max-w-xs mx-auto">
              Create a group or use the AI generator below to get started.
            </p>
            <Button
              onClick={() => setShowNew(true)}
              className="bg-green-500 hover:bg-green-600 text-white gap-2 shadow-sm"
            >
              <FaPlus className="text-xs" />
              Create First Group
            </Button>
          </div>
        ) : (
          <>
            {groups.length > 0 && (
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-3">
                {groups.length} {groups.length === 1 ? 'Group' : 'Groups'}
              </p>
            )}
            <div className="space-y-3">
              {groups.map((group) =>
                editingId === group.id ? (
                  <GroupForm
                    key={group.id}
                    initial={group}
                    onSave={(data) => handleUpdate(group.id, data)}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <GroupCard
                    key={group.id}
                    group={group}
                    onEdit={(g) => { setEditingId(g.id); setShowNew(false); }}
                    onDelete={handleDelete}
                  />
                )
              )}
            </div>
          </>
        )}

        {/* ── AI Generator ── */}
        <div className="mt-10">
          <div className="flex items-center gap-3 mb-5">
            <div className="flex-1 h-px bg-gray-100" />
            <span className="text-xs text-gray-400 font-semibold uppercase tracking-widest flex-shrink-0">AI Tools</span>
            <div className="flex-1 h-px bg-gray-100" />
          </div>
          <HashtagGenerator onSaveAsGroup={handleSaveGeneratedAsGroup} />
        </div>

      </div>
    </DashboardLayout>
  );
};

export default HashtagGroups;
