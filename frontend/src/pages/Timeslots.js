import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { FaQuestionCircle, FaTrash, FaPlus, FaLightbulb } from 'react-icons/fa';

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

// Ideal posting times per platform (AI suggestion stub)
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

const Timeslots = () => {
  const { user } = useAuth();

  const [accounts, setAccounts] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(CATEGORIES[0]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [slots, setSlots] = useState({}); // { MONDAY: [{id, hour, minute, ampm}], ... }

  // Add slot form state
  const [dayOption, setDayOption] = useState('every_day');
  const [showDayDropdown, setShowDayDropdown] = useState(false);
  const [hour, setHour] = useState('12');
  const [minute, setMinute] = useState('00');
  const [ampm, setAmpm] = useState('PM');
  const [copyFrom, setCopyFrom] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load accounts
  useEffect(() => {
    getSocialAccounts()
      .then((res) => {
        const accs = res.accounts || res || [];
        setAccounts(accs);
        if (accs.length) setSelectedAccountId(accs[0].id);
      })
      .catch(() => {});
  }, []);

  // Load timeslots when account/category changes
  useEffect(() => {
    if (!selectedAccountId) return;
    setLoading(true);
    fetch(`${API}/timeslots?account_id=${selectedAccountId}&category=${encodeURIComponent(selectedCategory)}`, {
      headers: authHeaders(),
    })
      .then((r) => r.json())
      .then((data) => {
        const grouped = {};
        DAYS_OF_WEEK.forEach((d) => { grouped[d] = []; });
        (data.timeslots || []).forEach((slot) => {
          if (grouped[slot.day_of_week]) {
            grouped[slot.day_of_week].push(slot);
          }
        });
        setSlots(grouped);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedAccountId, selectedCategory]);

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
          }).then((r) => r.json())
        )
      );
      const newSlots = { ...slots };
      results.forEach((slot, i) => {
        if (slot.id) {
          newSlots[targetDays[i]] = [...(newSlots[targetDays[i]] || []), slot];
        }
      });
      setSlots(newSlots);
      toast.success(`Timeslot added for ${selectedDayObj.label}`);
    } catch {
      toast.error('Failed to save timeslot');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSlot = async (day, slotId) => {
    try {
      await fetch(`${API}/timeslots/${slotId}`, { method: 'DELETE', headers: authHeaders() });
      setSlots((prev) => ({
        ...prev,
        [day]: prev[day].filter((s) => s.id !== slotId),
      }));
    } catch {
      toast.error('Failed to delete timeslot');
    }
  };

  const handleClearAll = async () => {
    if (!selectedAccountId) return;
    if (!window.confirm('Clear all timeslots for this account?')) return;
    try {
      await fetch(
        `${API}/timeslots?account_id=${selectedAccountId}&category=${encodeURIComponent(selectedCategory)}`,
        { method: 'DELETE', headers: authHeaders() }
      );
      const empty = {};
      DAYS_OF_WEEK.forEach((d) => { empty[d] = []; });
      setSlots(empty);
      toast.success('All timeslots cleared');
    } catch {
      toast.error('Failed to clear timeslots');
    }
  };

  const handleSuggestIdeal = () => {
    const suggested = { ...slots };
    DAYS_OF_WEEK.forEach((d) => { suggested[d] = []; });
    // Insert suggested times (would call AI endpoint in production)
    IDEAL_TIMES.forEach((t) => {
      suggested[t.day] = [{ id: `suggested-${t.day}`, hour: t.hour, minute: t.minute, ampm: t.ampm, _suggested: true }];
    });
    setSlots(suggested);
    toast.success('Ideal posting times loaded — click Save to apply');
  };

  const selectedAccount = accounts.find((a) => a.id === selectedAccountId);
  const totalSlots = Object.values(slots).reduce((acc, arr) => acc + arr.length, 0);

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto pb-12">
        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Timeslots</h1>
          <button className="text-gray-400 hover:text-gray-600 transition-colors" title="Creating a timeslot allows you to set predetermined posting times. When you choose 'Add to Timeslot', posts are added to the next unfilled slot.">
            <FaQuestionCircle />
          </button>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap gap-3 mb-6">
          {/* Category */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-4 py-2.5 text-sm border border-gray-200 rounded-xl bg-white text-gray-700 focus:outline-none focus:border-green-400 shadow-sm min-w-[160px]"
          >
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>

          {/* Account */}
          <select
            value={selectedAccountId}
            onChange={(e) => setSelectedAccountId(e.target.value)}
            className="px-4 py-2.5 text-sm border border-gray-200 rounded-xl bg-white text-gray-700 focus:outline-none focus:border-green-400 shadow-sm min-w-[200px]"
          >
            {accounts.length === 0 && <option value="">No accounts connected</option>}
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.username || a.display_name || a.platform}
              </option>
            ))}
          </select>
        </div>

        {/* Add New Timeslot */}
        <div className="bg-white rounded-2xl border border-gray-200 p-5 shadow-sm mb-6">
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-sm font-bold text-gray-900">Add New Timeslot:</h3>
            <label className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer">
              <input
                type="checkbox"
                checked={copyFrom}
                onChange={(e) => setCopyFrom(e.target.checked)}
                className="accent-green-500"
              />
              Copy timeslots from another account
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Day picker */}
            <div className="relative">
              <button
                onClick={() => setShowDayDropdown((v) => !v)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-green-500 text-white rounded-lg min-w-[130px] justify-between"
              >
                <span>{selectedDayObj.label}</span>
                <span className="text-[10px]">▼</span>
              </button>
              {showDayDropdown && (
                <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-xl z-20 min-w-[160px] overflow-hidden">
                  {DAY_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => { setDayOption(opt.value); setShowDayDropdown(false); }}
                      className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 transition-colors ${
                        dayOption === opt.value ? 'bg-green-50 text-green-700 font-semibold' : 'text-gray-700'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <span className="text-xs font-medium text-gray-600">Choose Time:</span>

            {/* Hour */}
            <select
              value={hour}
              onChange={(e) => setHour(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-green-400 w-16"
            >
              {HOURS.map((h) => <option key={h}>{h}</option>)}
            </select>

            {/* Minute */}
            <select
              value={minute}
              onChange={(e) => setMinute(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-green-400 w-16"
            >
              {MINUTES.map((m) => <option key={m}>{m}</option>)}
            </select>

            {/* AM/PM */}
            <select
              value={ampm}
              onChange={(e) => setAmpm(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-green-400 w-20"
            >
              <option>AM</option>
              <option>PM</option>
            </select>

            <button
              onClick={handleAddSlot}
              disabled={saving || !selectedAccountId}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50 shadow-sm"
            >
              <FaPlus className="text-xs" />
              {saving ? 'Adding…' : 'Add Slot'}
            </button>
          </div>

          {/* Suggest ideal times */}
          <button
            onClick={handleSuggestIdeal}
            className="mt-4 flex items-center gap-2 px-4 py-2 text-xs font-bold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors shadow-sm"
          >
            <FaLightbulb />
            Suggest ideal posting times
          </button>
        </div>

        {/* Week grid */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
            <span className="text-xs font-semibold text-gray-500">
              {totalSlots} slot{totalSlots !== 1 ? 's' : ''} scheduled
            </span>
            {totalSlots > 0 && (
              <button
                onClick={handleClearAll}
                className="flex items-center gap-1.5 text-xs font-semibold text-red-500 hover:text-red-700 transition-colors"
              >
                <FaTrash className="text-[10px]" />
                Clear all
              </button>
            )}
          </div>

          {loading ? (
            <div className="py-12 text-center text-sm text-gray-400">Loading timeslots…</div>
          ) : (
            <div className="overflow-x-auto">
              <div className="min-w-[600px]">
                {/* Day headers */}
                <div className="grid grid-cols-7 border-b border-gray-100">
                  {DAYS_OF_WEEK.map((day) => (
                    <div key={day} className="px-3 py-3 text-center">
                      <p className="text-[11px] font-bold text-gray-500 tracking-wide">{day.slice(0, 3)}</p>
                    </div>
                  ))}
                </div>

                {/* Slots row */}
                <div className="grid grid-cols-7 min-h-[80px] p-3 gap-2">
                  {DAYS_OF_WEEK.map((day) => (
                    <div key={day} className="space-y-1.5">
                      {(slots[day] || []).map((slot) => (
                        <div
                          key={slot.id}
                          className={`group flex items-center justify-between px-2 py-1.5 rounded-lg text-[11px] font-semibold ${
                            slot._suggested
                              ? 'bg-green-100 text-green-700 border border-green-200'
                              : 'bg-gray-100 text-gray-700 border border-gray-200'
                          }`}
                        >
                          <span>{slot.hour}:{slot.minute} {slot.ampm}</span>
                          {!slot._suggested && (
                            <button
                              onClick={() => handleDeleteSlot(day, slot.id)}
                              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-all ml-1"
                            >
                              ×
                            </button>
                          )}
                        </div>
                      ))}
                      {!(slots[day] || []).length && (
                        <div className="text-[10px] text-gray-300 text-center pt-2">—</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Info box */}
        <div className="mt-4 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-xs text-blue-700 leading-relaxed">
          <strong>How timeslots work:</strong> When you create a post and choose "Add to Timeslot",
          it will be scheduled to the next unfilled timeslot for the selected category and account.
          This lets you maintain a consistent posting schedule without manually setting dates each time.
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Timeslots;
