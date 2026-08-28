import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { FaTrash, FaPlus, FaLightbulb, FaCopy, FaClock, FaGlobe } from 'react-icons/fa';

const DAYS_OF_WEEK = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];
const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, '0'));
const MINUTES = ['00', '15', '30', '45'];
const CATEGORIES = ['Category 1', 'Category 2', 'Category 3', 'Custom'];

const DAY_OPTIONS = [
  { value: 'every_day', label: 'Every Day', days: DAYS_OF_WEEK },
  { value: 'weekdays', label: 'Weekdays', days: ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'] },
  { value: 'weekends', label: 'Weekends', days: ['SATURDAY', 'SUNDAY'] },
  { value: 'MONDAY', label: 'Monday', days: ['MONDAY'] },
  { value: 'TUESDAY', label: 'Tuesday', days: ['TUESDAY'] },
  { value: 'WEDNESDAY', label: 'Wednesday', days: ['WEDNESDAY'] },
  { value: 'THURSDAY', label: 'Thursday', days: ['THURSDAY'] },
  { value: 'FRIDAY', label: 'Friday', days: ['FRIDAY'] },
  { value: 'SATURDAY', label: 'Saturday', days: ['SATURDAY'] },
  { value: 'SUNDAY', label: 'Sunday', days: ['SUNDAY'] },
];

const IDEAL_TIMES = [
  { day: 'MONDAY', hour: '09', minute: '00', ampm: 'AM' },
  { day: 'TUESDAY', hour: '11', minute: '00', ampm: 'AM' },
  { day: 'WEDNESDAY', hour: '12', minute: '00', ampm: 'PM' },
  { day: 'THURSDAY', hour: '02', minute: '00', ampm: 'PM' },
  { day: 'FRIDAY', hour: '10', minute: '00', ampm: 'AM' },
  { day: 'SATURDAY', hour: '11', minute: '00', ampm: 'AM' },
  { day: 'SUNDAY', hour: '12', minute: '00', ampm: 'PM' },
];

const API = `${process.env.REACT_APP_BACKEND_URL}/api/v1`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' });
const getAccountValue = (account) => account?.account_id || account?.id || '';
const getAccountLabel = (account) =>
  account?.platform_username
  || account?.username
  || account?.display_name
  || account?.platform_user_id
  || account?.platform
  || 'Unknown account';

const Timeslots = () => {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(CATEGORIES[0]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [slots, setSlots] = useState({});

  const [dayOption, setDayOption] = useState('every_day');
  const [hour, setHour] = useState('09');
  const [minute, setMinute] = useState('00');
  const [ampm, setAmpm] = useState('AM');
  const [copyFrom, setCopyFrom] = useState(false);
  const [copySourceAccountId, setCopySourceAccountId] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const activeTimezone = user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

  const loadTimeslots = useCallback(async (accountId, category) => {
    if (!accountId) return;
    setLoading(true);
    try {
      const response = await fetch(
        `${API}/timeslots?account_id=${accountId}&category=${encodeURIComponent(category)}`,
        { headers: authHeaders() },
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to load timeslots');
      }
      const grouped = {};
      DAYS_OF_WEEK.forEach((day) => {
        grouped[day] = [];
      });
      (data.timeslots || []).forEach((slot) => {
        if (grouped[slot.day_of_week]) {
          grouped[slot.day_of_week].push(slot);
        }
      });
      DAYS_OF_WEEK.forEach((day) => {
        grouped[day].sort((a, b) => {
          const aHour = Number(a.hour) % 12 + (a.ampm === 'PM' ? 12 : 0);
          const bHour = Number(b.hour) % 12 + (b.ampm === 'PM' ? 12 : 0);
          if (aHour !== bHour) return aHour - bHour;
          return Number(a.minute) - Number(b.minute);
        });
      });
      setSlots(grouped);
    } catch (error) {
      toast.error(error.message || 'Failed to load timeslots');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    getSocialAccounts()
      .then((res) => {
        const accs = res.accounts || res || [];
        setAccounts(accs);
        if (accs.length) {
          setSelectedAccountId(getAccountValue(accs[0]));
          if (accs.length > 1) {
            setCopySourceAccountId(getAccountValue(accs[1]));
          }
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedAccountId) return;
    loadTimeslots(selectedAccountId, selectedCategory);
  }, [loadTimeslots, selectedAccountId, selectedCategory]);

  useEffect(() => {
    if (!copyFrom) return;
    if (!selectedAccountId) return;
    if (copySourceAccountId && copySourceAccountId !== selectedAccountId) return;
    const fallbackSource = accounts.find((account) => getAccountValue(account) !== selectedAccountId);
    setCopySourceAccountId(getAccountValue(fallbackSource));
  }, [accounts, copyFrom, copySourceAccountId, selectedAccountId]);

  const selectedDayObj = DAY_OPTIONS.find((d) => d.value === dayOption) || DAY_OPTIONS[0];

  const handleAddSlot = async () => {
    if (!selectedAccountId) { toast.error('Select an account first'); return; }
    const targetDays = selectedDayObj.days;
    setSaving(true);
    try {
      const results = await Promise.all(
        targetDays.map((day) =>
          fetch(`${API}/timeslots`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
              account_id: selectedAccountId,
              category: selectedCategory,
              day_of_week: day,
              hour,
              minute,
              ampm,
            }),
          }).then(async (response) => {
            const data = await response.json();
            return { ok: response.ok, data };
          })
        )
      );
      const successfulResults = results.filter((result) => result.ok);
      const duplicateResults = results.filter(
        (result) => !result.ok && result.data?.detail === 'An identical timeslot already exists for this account'
      );
      const hardFailures = results.filter(
        (result) => !result.ok && result.data?.detail !== 'An identical timeslot already exists for this account'
      );

      if (hardFailures.length) {
        throw new Error(hardFailures[0]?.data?.detail || 'Failed to save timeslot');
      }

      await loadTimeslots(selectedAccountId, selectedCategory);

      if (successfulResults.length && duplicateResults.length) {
        toast.success(
          `Added ${successfulResults.length} slot${successfulResults.length !== 1 ? 's' : ''} for ${selectedDayObj.label}. ` +
          `Skipped ${duplicateResults.length} duplicate${duplicateResults.length !== 1 ? 's' : ''}.`
        );
        return;
      }

      if (successfulResults.length) {
        toast.success(`Timeslot added for ${selectedDayObj.label}`);
        return;
      }

      if (duplicateResults.length) {
        toast.error(
          duplicateResults.length === 1
            ? 'That timeslot already exists for the selected account'
            : 'Those timeslots already exist for the selected account'
        );
        return;
      }

      throw new Error('Failed to save timeslot');
    } catch (error) {
      toast.error(error.message || 'Failed to save timeslot');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSlot = async (day, slotId) => {
    try {
      const response = await fetch(`${API}/timeslots/${slotId}`, { method: 'DELETE', headers: authHeaders() });
      if (!response.ok) {
        throw new Error('Failed to delete timeslot');
      }
      setSlots((prev) => ({
        ...prev,
        [day]: prev[day].filter((s) => s.id !== slotId),
      }));
      toast.success('Slot removed');
    } catch (error) {
      toast.error(error.message || 'Failed to delete timeslot');
    }
  };

  const handleClearAll = async () => {
    if (!selectedAccountId) return;
    if (!window.confirm(`Clear all timeslots for ${selectedCategory}?`)) return;
    try {
      const response = await fetch(
        `${API}/timeslots?account_id=${selectedAccountId}&category=${encodeURIComponent(selectedCategory)}`,
        { method: 'DELETE', headers: authHeaders() }
      );
      if (!response.ok) {
        throw new Error('Failed to clear timeslots');
      }
      const empty = {};
      DAYS_OF_WEEK.forEach((d) => { empty[d] = []; });
      setSlots(empty);
      toast.success('All timeslots cleared');
    } catch (error) {
      toast.error(error.message || 'Failed to clear timeslots');
    }
  };

  const handleSuggestIdeal = () => {
    if (!selectedAccountId) {
      toast.error('Select an account first');
      return;
    }
    setSaving(true);
    Promise.all(
      IDEAL_TIMES.map((slot) =>
        fetch(`${API}/timeslots`, {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({
            account_id: selectedAccountId,
            category: selectedCategory,
            day_of_week: slot.day,
            hour: slot.hour,
            minute: slot.minute,
            ampm: slot.ampm,
          }),
        }).then(async (response) => ({
          ok: response.ok,
          data: await response.json(),
        }))
      ),
    )
      .then(async (results) => {
        const failures = results.filter((result) => !result.ok && result.data?.detail !== 'An identical timeslot already exists for this account');
        if (failures.length) {
          throw new Error(failures[0]?.data?.detail || 'Failed to apply suggested schedule');
        }
        await loadTimeslots(selectedAccountId, selectedCategory);
        toast.success('Optimal schedule applied!');
      })
      .catch((error) => {
        toast.error(error.message || 'Failed to apply suggested schedule');
      })
      .finally(() => setSaving(false));
  };

  const handleCopySlots = async () => {
    if (!selectedAccountId || !copySourceAccountId) {
      toast.error('Select both source and target accounts');
      return;
    }
    if (selectedAccountId === copySourceAccountId) {
      toast.error('Choose a different source account');
      return;
    }
    setSaving(true);
    try {
      const sourceResponse = await fetch(
        `${API}/timeslots?account_id=${copySourceAccountId}&category=${encodeURIComponent(selectedCategory)}`,
        { headers: authHeaders() },
      );
      const sourceData = await sourceResponse.json();
      if (!sourceResponse.ok) {
        throw new Error(sourceData.detail || 'Failed to load source timeslots');
      }
      const sourceSlots = sourceData.timeslots || [];
      if (sourceSlots.length === 0) {
        throw new Error('No timeslots found on the source account for this category');
      }

      const copyResults = await Promise.all(
        sourceSlots.map((slot) =>
          fetch(`${API}/timeslots`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
              account_id: selectedAccountId,
              category: selectedCategory,
              day_of_week: slot.day_of_week,
              hour: slot.hour,
              minute: slot.minute,
              ampm: slot.ampm,
            }),
          }).then(async (response) => ({
            ok: response.ok,
            data: await response.json(),
          }))
        ),
      );
      const failures = copyResults.filter((result) => !result.ok && result.data?.detail !== 'An identical timeslot already exists for this account');
      if (failures.length) {
        throw new Error(failures[0]?.data?.detail || 'Failed to copy timeslots');
      }
      await loadTimeslots(selectedAccountId, selectedCategory);
      toast.success('Timeslots copied successfully');
    } catch (error) {
      toast.error(error.message || 'Failed to copy timeslots');
    } finally {
      setSaving(false);
    }
  };

  const totalSlots = Object.values(slots).reduce((acc, arr) => acc + arr.length, 0);

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-2 sm:px-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold text-black">🕒</span>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">Posting Timeslots</h1>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                {totalSlots} Active {totalSlots === 1 ? 'Slot' : 'Slots'}
              </span>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Set predetermined recurring slots. Posts created with "Add to Timeslot" auto-queue into the next open slot.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm">
              <FaGlobe className="text-slate-400 text-[11px]" />
              <span>Timezone: {activeTimezone}</span>
            </span>
          </div>
        </div>

        {/* Controls: Account & Category Selectors */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Account Selector */}
          <div className="space-y-1">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Target Account</span>
            <select
              value={selectedAccountId}
              onChange={(e) => setSelectedAccountId(e.target.value)}
              className="h-10 px-3.5 text-xs font-semibold border border-slate-200 rounded-xl bg-white text-slate-900 shadow-sm outline-none focus:border-black min-w-[200px]"
            >
              {accounts.length === 0 && <option value="">No accounts connected</option>}
              {accounts.map((a) => (
                <option key={getAccountValue(a)} value={getAccountValue(a)}>
                  {getAccountLabel(a)} ({a.platform || 'social'})
                </option>
              ))}
            </select>
          </div>

          {/* Category Selector */}
          <div className="space-y-1">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Content Pillar / Category</span>
            <div className="flex items-center gap-1.5">
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setSelectedCategory(c)}
                  className={`h-10 px-3.5 text-xs font-semibold rounded-xl border transition ${
                    selectedCategory === c
                      ? 'border-black bg-black text-white shadow-sm'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Add New Slot Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FaPlus className="text-xs text-black" />
              <h3 className="text-sm font-bold text-slate-900">Add New Timeslot</h3>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
              <input
                type="checkbox"
                checked={copyFrom}
                onChange={(e) => setCopyFrom(e.target.checked)}
                className="accent-black rounded"
              />
              <span>Copy schedule from another account</span>
            </label>
          </div>

          {copyFrom && (
            <div className="flex flex-wrap items-center gap-3 p-3.5 bg-slate-50 border border-slate-200 rounded-xl">
              <span className="text-xs font-medium text-slate-600">Copy from:</span>
              <select
                value={copySourceAccountId}
                onChange={(e) => setCopySourceAccountId(e.target.value)}
                className="h-9 px-3 text-xs border border-slate-200 rounded-lg bg-white text-slate-800 outline-none"
              >
                <option value="">Select source account</option>
                {accounts
                  .filter((account) => getAccountValue(account) !== selectedAccountId)
                  .map((account) => (
                    <option key={getAccountValue(account)} value={getAccountValue(account)}>
                      {getAccountLabel(account)}
                    </option>
                  ))}
              </select>
              <button
                onClick={handleCopySlots}
                disabled={saving || !copySourceAccountId}
                className="h-9 px-3.5 text-xs font-semibold bg-black text-white rounded-lg hover:bg-slate-800 disabled:opacity-50 transition flex items-center gap-1.5 shadow-sm"
              >
                <FaCopy className="text-[10px]" />
                <span>Copy Slots</span>
              </button>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            {/* Day selector */}
            <select
              value={dayOption}
              onChange={(e) => setDayOption(e.target.value)}
              className="h-10 px-3.5 text-xs font-semibold border border-slate-200 rounded-xl bg-slate-50 text-slate-900 outline-none focus:border-black focus:bg-white"
            >
              {DAY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>

            <span className="text-xs font-semibold text-slate-500">at</span>

            {/* Hour */}
            <select
              value={hour}
              onChange={(e) => setHour(e.target.value)}
              className="h-10 px-3 text-xs font-bold border border-slate-200 rounded-xl bg-slate-50 text-slate-900 outline-none focus:border-black focus:bg-white w-16"
            >
              {HOURS.map((h) => <option key={h}>{h}</option>)}
            </select>

            {/* Minute */}
            <select
              value={minute}
              onChange={(e) => setMinute(e.target.value)}
              className="h-10 px-3 text-xs font-bold border border-slate-200 rounded-xl bg-slate-50 text-slate-900 outline-none focus:border-black focus:bg-white w-16"
            >
              {MINUTES.map((m) => <option key={m}>{m}</option>)}
            </select>

            {/* AM/PM */}
            <select
              value={ampm}
              onChange={(e) => setAmpm(e.target.value)}
              className="h-10 px-3 text-xs font-bold border border-slate-200 rounded-xl bg-slate-50 text-slate-900 outline-none focus:border-black focus:bg-white w-20"
            >
              <option>AM</option>
              <option>PM</option>
            </select>

            <button
              onClick={handleAddSlot}
              disabled={saving || !selectedAccountId}
              className="h-10 px-4 text-xs font-semibold bg-black hover:bg-slate-800 text-white rounded-xl transition disabled:opacity-50 flex items-center gap-1.5 shadow-sm ml-auto sm:ml-0"
            >
              <FaPlus className="text-[10px]" />
              <span>{saving ? 'Adding…' : 'Add Slot'}</span>
            </button>
          </div>

          <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
            <button
              onClick={handleSuggestIdeal}
              disabled={saving || !selectedAccountId}
              className="px-3.5 py-1.5 text-xs font-semibold text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-50 transition flex items-center gap-1.5"
            >
              <FaLightbulb className="text-amber-500 text-xs" />
              <span>Apply Peak Engagement Schedule</span>
            </button>

            {totalSlots > 0 && (
              <button
                onClick={handleClearAll}
                className="text-xs font-semibold text-red-600 hover:text-red-700 transition flex items-center gap-1"
              >
                <FaTrash className="text-[10px]" />
                <span>Clear All Slots</span>
              </button>
            )}
          </div>
        </div>

        {/* 7-Day Weekly Grid */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/50">
            <span className="text-xs font-bold text-slate-900">
              Weekly Schedule for {selectedCategory}
            </span>
            <span className="text-xs text-slate-500">
              {totalSlots} configured {totalSlots === 1 ? 'slot' : 'slots'}
            </span>
          </div>

          {loading ? (
            <div className="py-16 text-center text-xs text-slate-400 animate-pulse">Loading timeslot schedule…</div>
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[640px]">
                {/* Day Header Row */}
                <div className="grid grid-cols-7 border-b border-slate-100 bg-slate-50/30">
                  {DAYS_OF_WEEK.map((day) => (
                    <div key={day} className="px-2 py-3 text-center border-r last:border-r-0 border-slate-100">
                      <p className="text-[11px] font-bold text-slate-700">{day.slice(0, 3)}</p>
                    </div>
                  ))}
                </div>

                {/* Slots Columns */}
                <div className="grid grid-cols-7 min-h-[140px] p-2 gap-1.5">
                  {DAYS_OF_WEEK.map((day) => (
                    <div key={day} className="space-y-1.5 p-1 rounded-xl bg-slate-50/50 border border-slate-100/80 min-h-[120px]">
                      {(slots[day] || []).map((slot) => (
                        <div
                          key={slot.id}
                          className="group flex items-center justify-between px-2 py-1.5 rounded-lg text-xs font-semibold bg-white text-slate-800 border border-slate-200/80 shadow-xs hover:border-slate-300 transition"
                        >
                          <span className="text-[11px]">{slot.hour}:{slot.minute} {slot.ampm}</span>
                          <button
                            onClick={() => handleDeleteSlot(day, slot.id)}
                            className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition ml-1"
                            title="Remove slot"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                      {!(slots[day] || []).length && (
                        <div className="text-[11px] text-slate-300 text-center pt-8">—</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Informative Guidance Card */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-600 space-y-1 shadow-sm">
          <p className="font-bold text-slate-900 flex items-center gap-1.5">
            <FaClock className="text-black text-[11px]" />
            How Timeslots Auto-Queue Works:
          </p>
          <p className="leading-relaxed">
            When creating a post, choosing <strong>"Add to Timeslot"</strong> schedules the post into the earliest unfilled slot for the selected account and category. It eliminates manual calendar date selection and prevents posts from double-booking or colliding.
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Timeslots;
