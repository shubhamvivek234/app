import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getRecurringRules, createRecurringRule, updateRecurringRule, deleteRecurringRule,
  getSocialAccounts,
} from '@/lib/api';
import { toast } from 'sonner';
import { FaRedo, FaPlus, FaPause, FaPlay, FaTrash, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import { format, parseISO } from 'date-fns';

// ── Constants ─────────────────────────────────────────────────────────────────
const PLATFORM_LABELS = {
  instagram: 'Instagram', twitter: 'Twitter / X', facebook: 'Facebook',
  linkedin: 'LinkedIn', youtube: 'YouTube', tiktok: 'TikTok',
  pinterest: 'Pinterest', threads: 'Threads', bluesky: 'Bluesky',
  reddit: 'Reddit', snapchat: 'Snapchat',
};

const DAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const FREQ_LABELS = {
  daily:   'Daily',
  weekly:  'Weekly',
  monthly: 'Monthly',
};

const ORDINALS = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th',
  '11th', '12th', '13th', '14th', '15th', '16th', '17th', '18th', '19th', '20th',
  '21st', '22nd', '23rd', '24th', '25th', '26th', '27th', '28th'];

const defaultForm = {
  content: '',
  platforms: [],
  accounts: [],
  post_type: 'text',
  media_urls: [],
  frequency: 'weekly',
  days_of_week: [1], // Mon
  day_of_month: 1,
  time_of_day: '09:00',
};

// ── Frequency description helper ──────────────────────────────────────────────
const describeFrequency = (rule) => {
  if (rule.frequency === 'daily') return `Daily at ${rule.time_of_day} UTC`;
  if (rule.frequency === 'weekly') {
    const days = (rule.days_of_week || []).map((d) => DAY_LABELS[d]).join(', ');
    return `Weekly on ${days || '—'} at ${rule.time_of_day} UTC`;
  }
  if (rule.frequency === 'monthly') {
    return `Monthly on the ${ORDINALS[rule.day_of_month] || rule.day_of_month} at ${rule.time_of_day} UTC`;
  }
  return rule.frequency;
};

// ── Rule card ─────────────────────────────────────────────────────────────────
const RuleCard = ({ rule, onToggle, onDelete }) => {
  const isActive = rule.status === 'active';
  const toggling = false;

  return (
    <div className={`bg-offwhite rounded-xl border transition-colors ${isActive ? 'border-gray-200' : 'border-gray-100 opacity-75'}`}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          {/* Status dot */}
          <div className={`mt-1.5 w-2.5 h-2.5 rounded-full flex-shrink-0 ${isActive ? 'bg-green-400' : 'bg-gray-300'}`} />

          <div className="flex-1 min-w-0">
            {/* Content preview */}
            <p className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug">
              {rule.content || <span className="text-gray-400 italic">No content</span>}
            </p>

            {/* Metadata row */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2">
              <span className="text-xs font-semibold text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                {FREQ_LABELS[rule.frequency] || rule.frequency}
              </span>
              <span className="text-xs text-gray-500">{describeFrequency(rule)}</span>
              {rule.platforms?.length > 0 && (
                <span className="text-xs text-gray-400">
                  {rule.platforms.map((p) => PLATFORM_LABELS[p] || p).join(' · ')}
                </span>
              )}
            </div>

            {/* Upcoming count */}
            <p className="text-xs text-gray-400 mt-1.5">
              {isActive
                ? `${rule.upcoming_count ?? 0} upcoming scheduled post${rule.upcoming_count !== 1 ? 's' : ''}`
                : 'Paused — no posts being generated'}
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              onClick={() => onToggle(rule)}
              disabled={toggling}
              title={isActive ? 'Pause' : 'Resume'}
              className={`p-2 rounded-lg transition-colors text-sm ${
                isActive
                  ? 'text-amber-500 hover:bg-amber-50'
                  : 'text-green-500 hover:bg-green-50'
              }`}
            >
              {isActive ? <FaPause /> : <FaPlay />}
            </button>
            <button
              onClick={() => onDelete(rule)}
              title="Delete"
              className="p-2 rounded-lg text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors text-sm"
            >
              <FaTrash />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Create form ───────────────────────────────────────────────────────────────
const CreateForm = ({ accounts, onSubmit, onCancel, saving }) => {
  const [form, setForm] = useState(defaultForm);

  const set = (key, val) => setForm((prev) => ({ ...prev, [key]: val }));

  const togglePlatform = (platform) => {
    set('platforms', form.platforms.includes(platform)
      ? form.platforms.filter((p) => p !== platform)
      : [...form.platforms, platform]);
  };

  const toggleDay = (day) => {
    set('days_of_week', form.days_of_week.includes(day)
      ? form.days_of_week.filter((d) => d !== day)
      : [...form.days_of_week, day]);
  };

  const availablePlatforms = [...new Set(accounts.map((a) => a.platform))];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.content.trim()) { toast.error('Content is required'); return; }
    if (!form.platforms.length) { toast.error('Select at least one platform'); return; }
    if (form.frequency === 'weekly' && !form.days_of_week.length) {
      toast.error('Select at least one day of the week'); return;
    }
    onSubmit(form);
  };

  return (
    <form onSubmit={handleSubmit} className="bg-offwhite rounded-xl border border-green-200 p-5 space-y-4">
      <h3 className="text-sm font-semibold text-gray-900">New Recurring Post</h3>

      {/* Content */}
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Post Content</label>
        <textarea
          rows={3}
          value={form.content}
          onChange={(e) => set('content', e.target.value)}
          placeholder="What would you like to post repeatedly?"
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-green-300 placeholder:text-gray-300"
          required
        />
      </div>

      {/* Platforms */}
      {availablePlatforms.length > 0 && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-2">Platforms</label>
          <div className="flex flex-wrap gap-2">
            {availablePlatforms.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => togglePlatform(p)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                  form.platforms.includes(p)
                    ? 'bg-green-500 border-green-500 text-white'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300'
                }`}
              >
                {PLATFORM_LABELS[p] || p}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Frequency */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Frequency</label>
          <select
            value={form.frequency}
            onChange={(e) => set('frequency', e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300 bg-offwhite"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>

        {/* Time */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Time (UTC)</label>
          <input
            type="time"
            value={form.time_of_day}
            onChange={(e) => set('time_of_day', e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300"
          />
        </div>
      </div>

      {/* Days of week (weekly only) */}
      {form.frequency === 'weekly' && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-2">Days of Week</label>
          <div className="flex gap-1.5">
            {DAY_LABELS.map((day, i) => (
              <button
                key={i}
                type="button"
                onClick={() => toggleDay(i)}
                className={`w-9 h-9 text-xs font-semibold rounded-lg border transition-colors ${
                  form.days_of_week.includes(i)
                    ? 'bg-green-500 border-green-500 text-white'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300'
                }`}
              >
                {day}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Day of month (monthly only) */}
      {form.frequency === 'monthly' && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Day of Month</label>
          <select
            value={form.day_of_month}
            onChange={(e) => set('day_of_month', parseInt(e.target.value))}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300 bg-offwhite"
          >
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>{ORDINALS[d]} ({d})</option>
            ))}
          </select>
        </div>
      )}

      {/* Preview */}
      {form.content && form.platforms.length > 0 && (
        <div className="bg-offwhite rounded-lg px-3 py-2.5 text-xs text-gray-500 border border-gray-200">
          <span className="font-medium text-gray-700">Preview: </span>
          {describeFrequency(form)} on {form.platforms.map((p) => PLATFORM_LABELS[p] || p).join(', ')}
        </div>
      )}

      {/* Buttons */}
      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-60"
        >
          {saving ? 'Creating…' : 'Create Rule'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-xs font-semibold text-gray-500 hover:text-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

// ── Main component ────────────────────────────────────────────────────────────
const RecurringPosts = () => {
  const [rules, setRules] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a] = await Promise.all([getRecurringRules(), getSocialAccounts()]);
      setRules(r);
      setAccounts(a.filter ? a.filter((acc) => acc.is_active !== false) : a);
    } catch {
      toast.error('Failed to load recurring posts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async (form) => {
    setSaving(true);
    try {
      const created = await createRecurringRule(form);
      setRules((prev) => [created, ...prev]);
      setShowForm(false);
      toast.success(`Recurring rule created — ${created.upcoming_count ?? 0} posts scheduled`);
    } catch {
      toast.error('Failed to create rule');
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (rule) => {
    const newStatus = rule.status === 'active' ? 'paused' : 'active';
    try {
      const updated = await updateRecurringRule(rule.id, { status: newStatus });
      setRules((prev) => prev.map((r) => (r.id === rule.id ? updated : r)));
      toast.success(newStatus === 'active' ? 'Rule resumed' : 'Rule paused');
    } catch {
      toast.error('Failed to update rule');
    }
  };

  const handleDelete = async (rule) => {
    if (!window.confirm('Delete this recurring rule? All future scheduled posts from it will be removed.')) return;
    try {
      await deleteRecurringRule(rule.id);
      setRules((prev) => prev.filter((r) => r.id !== rule.id));
      toast.success('Rule deleted');
    } catch {
      toast.error('Failed to delete rule');
    }
  };

  const activeCount = rules.filter((r) => r.status === 'active').length;

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <FaRedo className="text-green-500 text-base" />
              Recurring Posts
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {rules.length} rule{rules.length !== 1 ? 's' : ''}{activeCount > 0 ? ` · ${activeCount} active` : ''}
            </p>
          </div>
          {!showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
            >
              <FaPlus className="text-xs" />
              New Rule
            </button>
          )}
        </div>

        {/* Create form */}
        {showForm && (
          <div className="mb-5">
            <CreateForm
              accounts={accounts}
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              saving={saving}
            />
          </div>
        )}

        {/* Rules list */}
        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="bg-offwhite rounded-xl border border-gray-200 p-4 h-24 animate-pulse" />
            ))}
          </div>
        ) : rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center bg-offwhite rounded-xl border border-dashed border-gray-200">
            <FaRedo className="text-4xl text-gray-200 mb-3" />
            <p className="text-sm font-semibold text-gray-500">No recurring rules yet</p>
            <p className="text-xs text-gray-400 mt-1 max-w-xs">
              Create a rule to automatically schedule the same post on a recurring basis — daily, weekly, or monthly.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="mt-4 px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
            >
              Create First Rule
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map((rule) => (
              <RuleCard
                key={rule.id}
                rule={rule}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

        {/* Info callout */}
        {rules.length > 0 && (
          <p className="text-xs text-gray-400 text-center mt-6">
            Recurring posts are pre-scheduled for the next 60 days. Active rules regenerate automatically.
          </p>
        )}
      </div>
    </DashboardLayout>
  );
};

export default RecurringPosts;
