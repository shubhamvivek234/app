import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getHashtagGroups, createHashtagGroup, updateHashtagGroup, deleteHashtagGroup } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FaHashtag, FaEdit, FaTrash, FaPlus, FaTimes, FaCheck, FaCopy } from 'react-icons/fa';
import { toast } from 'sonner';

const PLATFORM_OPTIONS = [
  { value: '', label: 'All Platforms' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'twitter', label: 'Twitter / X' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'pinterest', label: 'Pinterest' },
  { value: 'threads', label: 'Threads' },
  { value: 'bluesky', label: 'Bluesky' },
];

// ── Parse hashtag text into a clean array ─────────────────────────────────────
const parseHashtags = (raw) =>
  raw
    .split(/[\s,\n]+/)
    .map((t) => t.trim().replace(/^#+/, ''))
    .filter(Boolean)
    .map((t) => `#${t}`);

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
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Input
          placeholder="Group name (e.g. Travel, Marketing)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="text-sm"
          autoFocus
        />
        <Input
          placeholder="Category (optional)"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="text-sm"
        />
      </div>

      <select
        value={platform}
        onChange={(e) => setPlatform(e.target.value)}
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-400 bg-white text-gray-700"
      >
        {PLATFORM_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <textarea
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-green-400 placeholder:text-gray-300 text-gray-800 min-h-[80px]"
        placeholder="#travel #wanderlust #adventure (space, comma or newline separated)"
        value={rawTags}
        onChange={(e) => setRawTags(e.target.value)}
      />

      {preview.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {preview.map((tag) => (
            <span
              key={tag}
              className="inline-block text-xs bg-green-50 text-green-700 border border-green-200 rounded-full px-2 py-0.5"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={saving}
          className="bg-green-500 hover:bg-green-600 text-white gap-1.5"
        >
          <FaCheck className="text-xs" />
          {saving ? 'Saving…' : 'Save Group'}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onCancel}
          className="text-gray-500 hover:text-gray-700 gap-1.5"
        >
          <FaTimes className="text-xs" />
          Cancel
        </Button>
      </div>
    </div>
  );
};

// ── Single group card ─────────────────────────────────────────────────────────
const GroupCard = ({ group, onEdit, onDelete }) => {
  const MAX_PREVIEW = 6;
  const visible = group.hashtags.slice(0, MAX_PREVIEW);
  const extra   = group.hashtags.length - MAX_PREVIEW;

  const handleCopy = () => {
    navigator.clipboard.writeText(group.hashtags.join(' '));
    toast.success('Hashtags copied to clipboard');
  };

  const platformLabel = PLATFORM_OPTIONS.find((o) => o.value === group.platform)?.label;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-start justify-between gap-3 hover:border-gray-300 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <FaHashtag className="text-green-500 text-sm flex-shrink-0" />
          <p className="font-semibold text-gray-900 text-sm truncate">{group.name}</p>
          <span className="text-xs text-gray-400 flex-shrink-0">
            {group.hashtags.length} {group.hashtags.length === 1 ? 'tag' : 'tags'}
          </span>
          {group.category && (
            <span className="text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5 flex-shrink-0">
              {group.category}
            </span>
          )}
          {platformLabel && group.platform && (
            <span className="text-xs bg-blue-50 text-blue-600 rounded-full px-2 py-0.5 flex-shrink-0">
              {platformLabel}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {visible.map((tag) => (
            <span
              key={tag}
              className="inline-block text-xs bg-white text-gray-600 border border-gray-200 rounded-full px-2 py-0.5 cursor-pointer hover:bg-green-50 hover:border-green-300 hover:text-green-700 transition-colors"
              onClick={() => { navigator.clipboard.writeText(tag); toast.success(`Copied ${tag}`); }}
              title="Click to copy this tag"
            >
              {tag}
            </span>
          ))}
          {extra > 0 && (
            <span className="inline-block text-xs text-gray-400 px-1 py-0.5">
              +{extra} more
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          onClick={handleCopy}
          className="p-2 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors"
          title="Copy all hashtags"
        >
          <FaCopy className="text-sm" />
        </button>
        <button
          onClick={() => onEdit(group)}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-50 transition-colors"
          title="Edit group"
        >
          <FaEdit className="text-sm" />
        </button>
        <button
          onClick={() => onDelete(group)}
          className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          title="Delete group"
        >
          <FaTrash className="text-sm" />
        </button>
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
const HashtagGroups = () => {
  const [groups, setGroups]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showNew, setShowNew]     = useState(false);
  const [editingId, setEditingId] = useState(null);

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

  const handleUpdate = async (id, { name, hashtags }) => {
    try {
      const updated = await updateHashtagGroup(id, { name, hashtags });
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

  return (
    <DashboardLayout>
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Hashtag Groups</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Create reusable hashtag sets — insert them with one click while composing posts.
            </p>
          </div>
          {!showNew && (
            <Button
              onClick={() => { setShowNew(true); setEditingId(null); }}
              className="bg-green-500 hover:bg-green-600 text-white gap-2"
            >
              <FaPlus className="text-xs" />
              New Group
            </Button>
          )}
        </div>

        {/* New group form */}
        {showNew && (
          <div className="mb-4">
            <GroupForm
              onSave={handleCreate}
              onCancel={() => setShowNew(false)}
            />
          </div>
        )}

        {/* Group list */}
        {loading ? (
          <div className="text-center py-16 text-gray-400 text-sm">Loading…</div>
        ) : groups.length === 0 && !showNew ? (
          <div className="text-center py-16">
            <div className="w-12 h-12 rounded-full bg-white border border-gray-200 flex items-center justify-center mx-auto mb-3">
              <FaHashtag className="text-gray-400 text-lg" />
            </div>
            <p className="text-gray-500 font-medium mb-1">No hashtag groups yet</p>
            <p className="text-gray-400 text-sm mb-4">
              Create your first group to speed up post creation.
            </p>
            <Button
              onClick={() => setShowNew(true)}
              className="bg-green-500 hover:bg-green-600 text-white gap-2"
            >
              <FaPlus className="text-xs" />
              Create First Group
            </Button>
          </div>
        ) : (
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
        )}
      </div>
    </DashboardLayout>
  );
};

export default HashtagGroups;
