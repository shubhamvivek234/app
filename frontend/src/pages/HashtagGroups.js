import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getHashtagGroups, createHashtagGroup, updateHashtagGroup,
  deleteHashtagGroup, generateHashtags,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  FaHashtag, FaEdit, FaTrash, FaPlus, FaTimes, FaCheck,
  FaCopy, FaMagic, FaSpinner, FaLayerGroup, FaBolt,
} from 'react-icons/fa';
import { toast } from 'sonner';

// ── Platform config ───────────────────────────────────────────────────────────
const PLATFORMS = [
  {
    value: 'instagram',
    label: 'Instagram',
    emoji: '📸',
    badge: 'bg-pink-100 text-pink-700',
    pill: 'border-pink-300 bg-pink-50 text-pink-700',
    pillActive: 'bg-pink-500 text-white border-pink-500',
  },
  {
    value: 'tiktok',
    label: 'TikTok',
    emoji: '🎵',
    badge: 'bg-slate-100 text-slate-700',
    pill: 'border-slate-300 bg-slate-50 text-slate-700',
    pillActive: 'bg-slate-800 text-white border-slate-800',
  },
  {
    value: 'youtube',
    label: 'YouTube',
    emoji: '▶',
    badge: 'bg-red-100 text-red-600',
    pill: 'border-red-300 bg-red-50 text-red-600',
    pillActive: 'bg-red-500 text-white border-red-500',
  },
];

const getPlatform = (value) => PLATFORMS.find((p) => p.value === value);

// ── Platform pills ────────────────────────────────────────────────────────────
const PlatformPills = ({ value, onChange, includeAll = false }) => {
  const allOpt = {
    value: '', label: 'Any', emoji: '🌐',
    pill: 'border-violet-200 bg-violet-50 text-violet-600',
    pillActive: 'bg-violet-600 text-white border-violet-600',
  };
  const opts = includeAll ? [allOpt, ...PLATFORMS] : PLATFORMS;
  return (
    <div className="flex flex-wrap gap-2">
      {opts.map((p) => (
        <button
          key={p.value}
          type="button"
          onClick={() => onChange(p.value)}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
            value === p.value ? p.pillActive : p.pill + ' hover:opacity-75'
          }`}
        >
          <span>{p.emoji}</span>{p.label}
        </button>
      ))}
    </div>
  );
};

// ── Parse raw hashtag text ────────────────────────────────────────────────────
const parseHashtags = (raw) =>
  raw.split(/[\s,\n]+/)
    .map((t) => t.trim().replace(/^#+/, ''))
    .filter(Boolean)
    .map((t) => `#${t}`);

// ── Tag chip with copy feedback ───────────────────────────────────────────────
const TagChip = ({ tag, onCopy, className = '' }) => {
  const [copied, setCopied] = useState(false);
  const handle = () => { onCopy(tag); setCopied(true); setTimeout(() => setCopied(false), 1000); };
  return (
    <span
      onClick={handle}
      title="Click to copy"
      className={`inline-flex items-center gap-1 text-xs rounded-full px-3 py-1 cursor-pointer select-none transition-all ${className}`}
    >
      {copied && <FaCheck className="text-[9px]" />}
      {tag}
    </span>
  );
};

// ── Group create / edit form ──────────────────────────────────────────────────
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
    try { await onSave({ name: name.trim(), hashtags: preview, category: category.trim(), platform }); }
    finally { setSaving(false); }
  };

  return (
    <div className="bg-white rounded-2xl border border-violet-100 shadow-md shadow-violet-50 p-5 space-y-4">
      <p className="text-sm font-semibold text-slate-800">{initial?.name ? 'Edit Group' : 'New Hashtag Group'}</p>
      <div className="grid grid-cols-2 gap-3">
        <Input placeholder="Group name" value={name} onChange={(e) => setName(e.target.value)}
          className="text-sm bg-slate-50 border-slate-200" autoFocus />
        <Input placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)}
          className="text-sm bg-slate-50 border-slate-200" />
      </div>
      <div>
        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Platform</p>
        <PlatformPills value={platform} onChange={setPlatform} includeAll />
      </div>
      <div>
        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-2">Hashtags</p>
        <textarea
          className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 placeholder:text-slate-300 text-slate-800 min-h-[72px] bg-slate-50"
          placeholder="#travel #wanderlust #adventure"
          value={rawTags} onChange={(e) => setRawTags(e.target.value)}
        />
      </div>
      {preview.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {preview.map((tag) => (
            <span key={tag} className="text-xs bg-violet-50 text-violet-700 border border-violet-200 rounded-full px-2.5 py-1">{tag}</span>
          ))}
        </div>
      )}
      <div className="flex gap-2 pt-1">
        <Button size="sm" onClick={handleSave} disabled={saving}
          className="bg-violet-600 hover:bg-violet-700 text-white gap-1.5">
          <FaCheck className="text-xs" />{saving ? 'Saving…' : 'Save Group'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} className="text-slate-500 gap-1.5">
          <FaTimes className="text-xs" />Cancel
        </Button>
      </div>
    </div>
  );
};

// ── Group card ────────────────────────────────────────────────────────────────
const GroupCard = ({ group, onEdit, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  const MAX = 8;
  const visible = expanded ? group.hashtags : group.hashtags.slice(0, MAX);
  const extra   = group.hashtags.length - MAX;
  const pl = getPlatform(group.platform);

  const copyAll = () => { navigator.clipboard.writeText(group.hashtags.join(' ')); toast.success('Copied all hashtags!'); };
  const copyTag = (tag) => { navigator.clipboard.writeText(tag); toast.success(`Copied ${tag}`); };

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm hover:shadow-md hover:border-violet-100 transition-all group p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center flex-shrink-0">
            <FaHashtag className="text-violet-500 text-xs" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-slate-900 text-sm truncate">{group.name}</p>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span className="text-xs text-slate-400">{group.hashtags.length} tags</span>
              {group.category && <span className="text-xs bg-slate-100 text-slate-500 rounded-full px-2 py-px">{group.category}</span>}
              {pl && <span className={`text-xs rounded-full px-2 py-px font-medium ${pl.badge}`}>{pl.emoji} {pl.label}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button onClick={copyAll} className="p-1.5 rounded-lg text-slate-400 hover:text-violet-600 hover:bg-violet-50 transition-colors" title="Copy all">
            <FaCopy className="text-xs" />
          </button>
          <button onClick={() => onEdit(group)} className="p-1.5 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors" title="Edit">
            <FaEdit className="text-xs" />
          </button>
          <button onClick={() => onDelete(group)} className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors" title="Delete">
            <FaTrash className="text-xs" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {visible.map((tag) => (
          <TagChip key={tag} tag={tag} onCopy={copyTag}
            className="bg-slate-50 text-slate-600 border border-slate-200 hover:bg-violet-50 hover:text-violet-700 hover:border-violet-200" />
        ))}
        {!expanded && extra > 0 && (
          <button onClick={() => setExpanded(true)}
            className="text-xs text-violet-600 px-2.5 py-1 rounded-full border border-violet-200 bg-violet-50 hover:bg-violet-100 transition-colors font-medium">
            +{extra} more
          </button>
        )}
        {expanded && (
          <button onClick={() => setExpanded(false)}
            className="text-xs text-slate-400 px-2.5 py-1 rounded-full border border-slate-200 hover:bg-slate-50 transition-colors">
            show less
          </button>
        )}
      </div>

      <div className="mt-3 pt-3 border-t border-slate-50 flex items-center justify-between">
        <span className="text-xs text-slate-300">Click any tag to copy individually</span>
        <button onClick={copyAll} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-violet-600 transition-colors font-medium">
          <FaCopy className="text-[10px]" /> Copy all
        </button>
      </div>
    </div>
  );
};

// ── AI Hashtag Generator ──────────────────────────────────────────────────────
const STEPS = [
  { n: '1', label: 'Describe your post' },
  { n: '2', label: 'Pick a platform' },
  { n: '3', label: 'Generate & copy' },
];

const DEFAULT_COUNT = 6;

const HashtagGenerator = ({ onSaveAsGroup }) => {
  const [topic, setTopic]       = useState('');
  const [platform, setPlatform] = useState('instagram');
  const [loading, setLoading]   = useState(false);
  const [hashtags, setHashtags] = useState([]);
  const [step, setStep]         = useState(1); // 1 = topic, 2 = platform, 3 = results

  const activePlatform = getPlatform(platform);

  const handleGenerate = async () => {
    if (!topic.trim()) { toast.error('Describe your post first'); return; }
    setLoading(true);
    setHashtags([]);
    try {
      const data = await generateHashtags(topic.trim(), platform || null, DEFAULT_COUNT);
      if (!data.hashtags?.length) { toast.error('No hashtags returned — try a different topic'); }
      else { setHashtags(data.hashtags); setStep(3); }
    } catch { toast.error('Failed to generate hashtags'); }
    finally { setLoading(false); }
  };

  const copyAll = () => { navigator.clipboard.writeText(hashtags.join(' ')); toast.success('All hashtags copied!'); };
  const copyTag = (tag) => { navigator.clipboard.writeText(tag); toast.success(`Copied ${tag}`); };

  return (
    <div className="rounded-3xl overflow-hidden border border-violet-100 shadow-xl shadow-violet-100/50">
      {/* Hero header */}
      <div className="bg-gradient-to-br from-violet-600 via-purple-600 to-indigo-600 px-8 py-8 relative overflow-hidden">
        {/* Decorative circles */}
        <div className="absolute -top-8 -right-8 w-40 h-40 rounded-full bg-white/5" />
        <div className="absolute -bottom-12 -left-6 w-32 h-32 rounded-full bg-white/5" />

        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center">
              <FaBolt className="text-white text-sm" />
            </div>
            <span className="text-white/70 text-xs font-semibold uppercase tracking-widest">AI-Powered</span>
          </div>
          <h2 className="text-white text-2xl font-bold leading-tight mb-2">
            Social Media Hashtag Generator
          </h2>
          <p className="text-violet-200 text-sm max-w-md">
            Describe your post and get trending hashtags tailored to your platform — instantly.
          </p>

          {/* Step indicators */}
          <div className="flex items-center gap-6 mt-6">
            {STEPS.map((s, i) => (
              <div key={s.n} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                  step >= i + 1 ? 'bg-white text-violet-600' : 'bg-white/20 text-white'
                }`}>
                  {step > i + 1 ? <FaCheck className="text-[10px]" /> : s.n}
                </div>
                <span className={`text-xs font-medium hidden sm:block ${step >= i + 1 ? 'text-white' : 'text-white/50'}`}>
                  {s.label}
                </span>
                {i < STEPS.length - 1 && <div className="w-8 h-px bg-white/20 hidden sm:block" />}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Form body */}
      <div className="bg-white px-8 py-6 space-y-6">
        {/* Step 1 — Topic */}
        <div>
          <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-2">
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-violet-100 text-violet-600 text-[9px] font-bold mr-1.5">1</span>
            What's your post about?
          </label>
          <textarea
            className="w-full text-sm border border-slate-200 rounded-xl px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent placeholder:text-slate-300 text-slate-800 bg-slate-50 focus:bg-white transition-all min-h-[90px]"
            placeholder='"Morning yoga routine at sunrise" or "Our new product launch — eco-friendly water bottles"'
            value={topic}
            onChange={(e) => { setTopic(e.target.value); if (step === 1 && e.target.value) setStep(2); }}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleGenerate(); }}
          />
          <p className="text-[11px] text-slate-300 mt-1.5">The more specific, the better results. Press ⌘+Enter to generate.</p>
        </div>

        {/* Step 2 — Platform */}
        <div>
          <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-2">
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-violet-100 text-violet-600 text-[9px] font-bold mr-1.5">2</span>
            Choose platform
          </label>
          <PlatformPills value={platform} onChange={setPlatform} />
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={loading}
          className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl text-sm font-bold transition-all ${
            loading
              ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
              : 'bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 text-white shadow-lg shadow-violet-200 hover:shadow-violet-300 active:scale-[0.98]'
          }`}
        >
          {loading
            ? <><FaSpinner className="animate-spin" /> Generating hashtags…</>
            : <><FaMagic /> Generate hashtags{activePlatform ? ` for ${activePlatform.label}` : ''}</>
          }
        </button>

        {/* Step 3 — Results */}
        {hashtags.length > 0 && (
          <div className="rounded-2xl border border-violet-100 bg-gradient-to-b from-violet-50 to-white p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <FaCheck className="text-violet-500 text-xs" />
                <span className="text-sm font-bold text-slate-800">{hashtags.length} hashtags ready</span>
                {activePlatform && (
                  <span className={`text-xs rounded-full px-2.5 py-0.5 font-semibold ${activePlatform.badge}`}>
                    {activePlatform.emoji} {activePlatform.label}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyAll}
                  className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-violet-700 bg-white border border-slate-200 hover:border-violet-300 rounded-lg px-3 py-1.5 transition-all"
                >
                  <FaCopy className="text-[10px]" /> Copy All
                </button>
                <button
                  onClick={() => onSaveAsGroup(hashtags, platform)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-white bg-violet-600 hover:bg-violet-700 rounded-lg px-3 py-1.5 transition-all"
                >
                  <FaPlus className="text-[10px]" /> Save as Group
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {hashtags.map((tag) => (
                <TagChip key={tag} tag={tag} onCopy={copyTag}
                  className="bg-white text-violet-700 border border-violet-200 hover:bg-violet-600 hover:text-white hover:border-violet-600 font-medium" />
              ))}
            </div>
            <p className="text-[11px] text-slate-300 mt-3">Click any hashtag to copy individually</p>
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
    try { const data = await getHashtagGroups(); setGroups(data); }
    catch { toast.error('Failed to load hashtag groups'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (groupData) => {
    try {
      const created = await createHashtagGroup(groupData);
      setGroups((prev) => [created, ...prev]);
      setShowNew(false);
      setPrefillTags(null);
      toast.success('Group created!');
    } catch { toast.error('Failed to create group'); }
  };

  const handleUpdate = async (id, data) => {
    try {
      const updated = await updateHashtagGroup(id, data);
      setGroups((prev) => prev.map((g) => (g.id === id ? updated : g)));
      setEditingId(null);
      toast.success('Group updated!');
    } catch { toast.error('Failed to update group'); }
  };

  const handleDelete = async (group) => {
    if (!window.confirm(`Delete "${group.name}"?`)) return;
    try {
      await deleteHashtagGroup(group.id);
      setGroups((prev) => prev.filter((g) => g.id !== group.id));
      toast.success('Group deleted');
    } catch { toast.error('Failed to delete group'); }
  };

  const handleSaveGeneratedAsGroup = (hashtags, platform) => {
    setPrefillTags({ hashtags, platform });
    setShowNew(true);
    setEditingId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto">

        {/* ── Generator (top, hero feature) ── */}
        <div className="mb-10">
          <HashtagGenerator onSaveAsGroup={handleSaveGeneratedAsGroup} />
        </div>

        {/* ── Saved Groups section ── */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-8 h-8 rounded-xl bg-slate-100 flex items-center justify-center flex-shrink-0">
            <FaLayerGroup className="text-slate-500 text-xs" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-bold text-slate-900 leading-tight">Saved Hashtag Groups</h2>
            <p className="text-xs text-slate-400">Insert into any post with one click</p>
          </div>
          {!showNew && (
            <Button
              onClick={() => { setShowNew(true); setEditingId(null); setPrefillTags(null); }}
              className="bg-slate-900 hover:bg-slate-700 text-white gap-2 text-xs shadow-sm flex-shrink-0"
              size="sm"
            >
              <FaPlus className="text-[10px]" /> New Group
            </Button>
          )}
        </div>

        {/* New / prefill group form */}
        {showNew && (
          <div className="mb-5">
            <GroupForm
              key={prefillTags ? 'prefill' : 'manual'}
              initial={prefillTags ? { hashtags: prefillTags.hashtags, platform: prefillTags.platform } : undefined}
              onSave={handleCreate}
              onCancel={() => { setShowNew(false); setPrefillTags(null); }}
            />
          </div>
        )}

        {/* Group list */}
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-slate-400 text-sm">
            <FaSpinner className="animate-spin" /> Loading…
          </div>
        ) : groups.length === 0 && !showNew ? (
          <div className="text-center py-16 bg-white rounded-2xl border border-dashed border-slate-200">
            <div className="w-12 h-12 rounded-2xl bg-violet-50 flex items-center justify-center mx-auto mb-3">
              <FaHashtag className="text-violet-400 text-lg" />
            </div>
            <p className="text-slate-700 font-semibold mb-1">No saved groups yet</p>
            <p className="text-slate-400 text-sm mb-5">Generate hashtags above and save them as a group.</p>
            <Button onClick={() => setShowNew(true)} className="bg-slate-900 hover:bg-slate-700 text-white gap-2 text-xs" size="sm">
              <FaPlus className="text-[10px]" /> Create Manually
            </Button>
          </div>
        ) : (
          <>
            {groups.length > 0 && (
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-3">
                {groups.length} {groups.length === 1 ? 'group' : 'groups'}
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

      </div>
    </DashboardLayout>
  );
};

export default HashtagGroups;
