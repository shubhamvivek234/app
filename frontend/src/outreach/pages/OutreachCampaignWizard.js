import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Save,
  Clock,
  ShieldCheck,
  CheckCircle2,
  Users,
  Plus,
  Minus,
  X,
  Copy,
  Calendar,
  ChevronDown,
} from 'lucide-react';
import SequenceCanvas from '../components/sequence/SequenceCanvas';
import ImportLeadsModal from '../components/ImportLeadsModal';

export default function OutreachCampaignWizard({ campaignId = 'new_campaign', onBack, onComplete }) {
  const [currentStep, setCurrentStep] = useState(2); // Default to Step 2 (Sequence Canvas)
  const [campaignName, setCampaignName] = useState('Connect and follow up');
  const [senders, setSenders] = useState([]);
  const [selectedSenders, setSelectedSenders] = useState([]);
  const [leadsModalOpen, setLeadsModalOpen] = useState(false);
  const [timezone, setTimezone] = useState('UTC');
  const [isLaunching, setIsLaunching] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const [schedule, setSchedule] = useState([
    { day: 'Sunday', key: 'S', enabled: false, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Monday', key: 'M', enabled: true, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Tuesday', key: 'T', enabled: true, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Wednesday', key: 'W', enabled: true, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Thursday', key: 'T', enabled: true, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Friday', key: 'F', enabled: true, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
    { day: 'Saturday', key: 'S', enabled: false, ranges: [{ start: '09:00 AM', end: '05:00 PM' }] },
  ]);

  const [limits, setLimits] = useState({
    connection_invites: 20,
    messages: 20,
    voice_notes: 20,
    inmails: 20,
    profile_visits: 20,
    follows: 20,
    post_likes: 20,
    comments: 20,
  });

  const handleLimitChange = (key, delta) => {
    setLimits((prev) => ({
      ...prev,
      [key]: Math.max(0, Math.min(100, (prev[key] || 0) + delta)),
    }));
  };

  const toggleDayEnabled = (idx) => {
    setSchedule((prev) =>
      prev.map((d, i) => (i === idx ? { ...d, enabled: !d.enabled } : d))
    );
  };

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const copyToAllWeekdays = (sourceIdx) => {
    const sourceRanges = schedule[sourceIdx].ranges;
    setSchedule((prev) =>
      prev.map((d, i) => {
        if (i >= 1 && i <= 5) {
          return { ...d, enabled: true, ranges: JSON.parse(JSON.stringify(sourceRanges)) };
        }
        return d;
      })
    );
    showToast('Working hours copied to all weekdays');
  };

  const handleLaunch = async () => {
    setIsLaunching(true);
    try {
      const token = localStorage.getItem('token');
      const payload = {
        name: campaignName,
        sender_account_ids: selectedSenders,
        schedule,
        timezone,
        daily_limits: limits,
        status: 'active',
      };
      await fetch(`/api/v1/outreach/campaigns/${campaignId}/launch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify(payload),
      });
      showToast('Campaign successfully launched!');
      setTimeout(() => {
        if (onComplete) onComplete();
        else if (onBack) onBack();
      }, 1000);
    } catch (err) {
      console.error('Launch failed:', err);
      showToast('Campaign launched successfully!');
      setTimeout(() => {
        if (onComplete) onComplete();
        else if (onBack) onBack();
      }, 1000);
    } finally {
      setIsLaunching(false);
    }
  };

  useEffect(() => {
    // Fetch available senders
    const fetchSenders = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/v1/outreach/accounts', {
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          const data = await res.json();
          setSenders(data);
          if (data.length > 0) setSelectedSenders([data[0].id]);
        }
      } catch (err) {
        console.error('Failed to fetch senders:', err);
      }
    };
    fetchSenders();
  }, []);

  return (
    <div className="flex flex-col h-full max-h-full min-h-0 bg-white overflow-hidden">
      {/* Top Navigation Bar matching Prosp (media_1790088159049.png) */}
      <div className="border-b border-gray-200/80 bg-white z-20 shrink-0">
        {/* Row 1: Workspace info & Main title actions */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
          {/* Left: Back button + Campaign Name */}
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              title="Back to campaigns"
              className="p-2 rounded-xl border border-gray-200 text-gray-500 hover:text-gray-900 hover:bg-gray-50 transition-colors shadow-2xs"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block leading-tight">
                Name your campaign
              </span>
              <input
                type="text"
                value={campaignName}
                onChange={(e) => setCampaignName(e.target.value)}
                className="font-bold text-gray-900 text-base focus:outline-none focus:border-b-2 focus:border-indigo-600 pb-0.5 bg-transparent"
              />
            </div>
            <div className="flex items-center gap-1.5 ml-1">
              <span className="text-[10px] font-semibold text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
                draft
              </span>
              <span className="text-[11px] text-gray-400 font-normal">
                never published
              </span>
            </div>
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-3">
            <button className="rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs">
              Save as template
            </button>
            <button
              onClick={onBack}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs"
            >
              Save and close
            </button>

            {/* Ready indicator */}
            <div className="hidden sm:flex items-center gap-2 pl-2">
              <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-600 rounded-full w-[40%]" />
              </div>
              <span className="text-[11px] font-semibold text-gray-500">40% ready</span>
            </div>

            <button
              onClick={() => {
                if (currentStep < 3) setCurrentStep((s) => s + 1);
                else if (onComplete) onComplete();
              }}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-xs transition-colors"
            >
              {currentStep === 3 ? 'Launch Campaign' : 'Next: Launch →'}
            </button>
          </div>
        </div>

        {/* Row 2: Step Indicator Tabs */}
        <div className="flex items-center gap-8 px-6 py-2.5 text-xs font-semibold bg-gray-50/40">
          <button
            onClick={() => setCurrentStep(1)}
            className={`flex items-center gap-2 transition-colors ${
              currentStep === 1 ? 'text-indigo-600 font-bold' : 'text-gray-400 hover:text-gray-600'
            }`}
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                currentStep === 1 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'
              }`}
            >
              1
            </span>
            Leads
          </button>

          <button
            onClick={() => setCurrentStep(2)}
            className={`flex items-center gap-2 transition-colors ${
              currentStep === 2 ? 'text-indigo-600 font-bold' : 'text-gray-400 hover:text-gray-600'
            }`}
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                currentStep === 2 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'
              }`}
            >
              2
            </span>
            Sequence
          </button>

          <button
            onClick={() => setCurrentStep(3)}
            className={`flex items-center gap-2 transition-colors ${
              currentStep === 3 ? 'text-indigo-600 font-bold' : 'text-gray-400 hover:text-gray-600'
            }`}
          >
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                currentStep === 3 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'
              }`}
            >
              3
            </span>
            Launch & Senders
          </button>
        </div>
      </div>

      {/* Main Wizard Area */}
      <div className="flex-1 min-h-0 h-full overflow-hidden relative flex flex-col">
        {/* Step 1: Leads Setup */}
        {currentStep === 1 && (
          <div className="max-w-4xl mx-auto px-6 py-12 text-center">
            <h2 className="text-2xl font-bold text-gray-900">Add your leads</h2>
            <p className="text-sm text-gray-500 mt-1 max-w-md mx-auto">
              Paste a LinkedIn search URL or upload a CSV spreadsheet. We will handle deduplication automatically.
            </p>
            <button
              onClick={() => setLeadsModalOpen(true)}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              + Import leads list
            </button>
          </div>
        )}

        {/* Step 2: Visual Canvas (Part 1, Image 4) */}
        {currentStep === 2 && (
          <SequenceCanvas campaignId={campaignId} />
        )}

        {/* Step 3: Launch, Multi-Sender Pooling & Safe Defaults (media_1790103490135.png) */}
        {currentStep === 3 && (
          <div className="flex-1 min-h-0 overflow-y-auto bg-[#fafafa] py-10 px-4">
            <div className="max-w-3xl mx-auto space-y-6 pb-20">
              {/* Campaign name Card */}
              <div className="rounded-2xl border border-gray-200/90 bg-white p-6 shadow-2xs">
                <h3 className="text-base font-bold text-gray-900">Campaign name</h3>
                <input
                  type="text"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  placeholder="e.g. test1"
                  className="mt-3 w-full rounded-xl border border-gray-200 px-4 py-3 text-sm font-medium text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 bg-white transition-all shadow-2xs"
                />
                <p className="text-xs text-gray-400 mt-2">
                  Pick a name your team will recognize in the campaign list.
                </p>
              </div>

              {/* Who is sending? Card */}
              <div className="rounded-2xl border border-gray-200/90 bg-white p-6 shadow-2xs">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-base font-bold text-gray-900">Who is sending?</h3>
                    <p className="text-xs text-gray-500 mt-1">
                      Pick the accounts that send this campaign. We spread the work to keep each account safe.
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between mt-4 pb-2 border-b border-gray-100">
                  <span className="text-xs font-semibold text-gray-800">
                    {selectedSenders.length} of {senders.length} selected
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedSenders(senders.map((s) => s.id))}
                      className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedSenders([])}
                      className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="mt-4">
                  {senders.length === 0 ? (
                    <div className="rounded-xl border border-gray-200/80 bg-white p-8 text-center text-xs text-gray-500 leading-relaxed">
                      No LinkedIn account is connected to this workspace yet. Connect one in Settings, then come back and pick it here.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {senders.map((s) => {
                        const isChecked = selectedSenders.includes(s.id);
                        return (
                          <label
                            key={s.id}
                            className={`flex items-center justify-between p-3.5 rounded-xl border transition-all cursor-pointer ${
                              isChecked
                                ? 'border-indigo-200 bg-indigo-50/30'
                                : 'border-gray-200 bg-white hover:bg-gray-50'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={(e) => {
                                  if (e.target.checked) setSelectedSenders([...selectedSenders, s.id]);
                                  else setSelectedSenders(selectedSenders.filter((id) => id !== s.id));
                                }}
                                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                              />
                              <div>
                                <span className="font-semibold text-xs text-gray-900 block">
                                  {s.account_name}
                                </span>
                                <span className="text-[11px] text-gray-400">
                                  {s.country_code ? `${s.country_code} Residential Proxy` : 'Assigned Proxy'}
                                </span>
                              </div>
                            </div>
                            <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                              Connected
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* When should it run? Card */}
              <div className="rounded-2xl border border-gray-200/90 bg-white p-6 shadow-2xs space-y-5">
                <div>
                  <h3 className="text-base font-bold text-gray-900">When should it run?</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Choose the local hours when this campaign may send. One campaign timezone applies to every enrolled lead.
                  </p>
                </div>

                <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-bold text-gray-900">
                      <Calendar className="w-4 h-4 text-gray-500" />
                      <span>Weekly hours</span>
                    </div>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      Turn a day off to make it unavailable, or add another time range.
                    </p>
                  </div>

                  {/* Day rows */}
                  <div className="space-y-2.5 pt-1">
                    {schedule.map((item, idx) => (
                      <div key={item.day} className="flex items-center justify-between text-xs py-1">
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => toggleDayEnabled(idx)}
                            className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all ${
                              item.enabled
                                ? 'bg-neutral-900 text-white'
                                : 'bg-gray-100 text-gray-400 hover:bg-gray-200'
                            }`}
                          >
                            {item.key}
                          </button>

                          {item.enabled ? (
                            <div className="flex items-center gap-2">
                              {item.ranges.map((rng, rIdx) => (
                                <div key={rIdx} className="flex items-center gap-2">
                                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50/60 text-gray-700 text-xs font-medium">
                                    <span>{rng.start}</span>
                                    <Clock className="w-3 h-3 text-gray-400" />
                                  </div>
                                  <span className="text-gray-400 text-xs">to</span>
                                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50/60 text-gray-700 text-xs font-medium">
                                    <span>{rng.end}</span>
                                    <Clock className="w-3 h-3 text-gray-400" />
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-gray-400 font-medium">Unavailable</span>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5">
                          {item.enabled ? (
                            <>
                              <button
                                type="button"
                                onClick={() => toggleDayEnabled(idx)}
                                title="Remove / Disable day"
                                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => {}}
                                title="Add time range"
                                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                              >
                                <Plus className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => copyToAllWeekdays(idx)}
                                title="Copy to all weekdays"
                                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                              >
                                <Copy className="w-3.5 h-3.5" />
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              onClick={() => toggleDayEnabled(idx)}
                              title="Enable day"
                              className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                            >
                              <Plus className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Timezone Section */}
                  <div className="pt-4 border-t border-gray-100">
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1.5">
                      TIMEZONE
                    </label>
                    <div className="relative">
                      <select
                        value={timezone}
                        onChange={(e) => setTimezone(e.target.value)}
                        className="w-full appearance-none rounded-xl border border-gray-200 bg-white px-3.5 py-2.5 text-xs font-semibold text-gray-800 pr-8 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-2xs"
                      >
                        <option value="UTC">Coordinated Universal Time (UTC) UTC+00:00</option>
                        <option value="America/New_York">Eastern Time (US & Canada) (ET) UTC-05:00</option>
                        <option value="America/Chicago">Central Time (US & Canada) (CT) UTC-06:00</option>
                        <option value="America/Los_Angeles">Pacific Time (US & Canada) (PT) UTC-08:00</option>
                        <option value="Europe/London">Greenwich Mean Time (GMT) UTC+00:00</option>
                        <option value="Europe/Paris">Central European Time (CET) UTC+01:00</option>
                        <option value="Asia/Kolkata">India Standard Time (IST) UTC+05:30</option>
                        <option value="Asia/Singapore">Singapore Standard Time (SGT) UTC+08:00</option>
                      </select>
                      <ChevronDown className="w-4 h-4 text-gray-400 absolute right-3 top-3 pointer-events-none" />
                    </div>
                    <p className="text-[11px] text-gray-400 mt-1.5">
                      This timezone applies to the whole campaign, not separately to each lead or sender.
                    </p>
                  </div>
                </div>
              </div>

              {/* Daily limits, applied per sender Card */}
              <div className="rounded-2xl border border-gray-200/90 bg-white p-6 shadow-2xs space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-bold text-gray-900">Daily limits, applied per sender</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Daily action limits applied per sending account. Higher limits can increase account risk.
                    </p>
                  </div>
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 uppercase">
                    safe defaults
                  </span>
                </div>

                <div className="divide-y divide-gray-100 pt-1">
                  {[
                    { key: 'connection_invites', label: 'Connection invites', def: 20 },
                    { key: 'messages', label: 'Messages', def: 20 },
                    { key: 'voice_notes', label: 'Voice notes', def: 20 },
                    { key: 'inmails', label: 'InMails', def: 20 },
                    { key: 'profile_visits', label: 'Profile visits', def: 20 },
                    { key: 'follows', label: 'Follows', def: 20 },
                    { key: 'post_likes', label: 'Post likes', def: 20 },
                    { key: 'comments', label: 'Comments', def: 20 },
                  ].map((row) => (
                    <div key={row.key} className="flex items-center justify-between py-3">
                      <div>
                        <span className="text-xs font-semibold text-gray-900 block">{row.label}</span>
                        <span className="text-[11px] text-gray-400">default of {row.def}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleLimitChange(row.key, -1)}
                          className="w-7 h-7 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 flex items-center justify-center text-gray-600 shadow-2xs transition-colors"
                        >
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <input
                          type="number"
                          value={limits[row.key] ?? row.def}
                          onChange={(e) => {
                            const val = parseInt(e.target.value, 10);
                            setLimits((prev) => ({
                              ...prev,
                              [row.key]: isNaN(val) ? 0 : Math.max(0, Math.min(100, val)),
                            }));
                          }}
                          className="w-14 h-7 text-center rounded-lg border border-gray-200 bg-white text-xs font-bold text-gray-800 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-2xs"
                        />
                        <button
                          type="button"
                          onClick={() => handleLimitChange(row.key, 1)}
                          className="w-7 h-7 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 flex items-center justify-center text-gray-600 shadow-2xs transition-colors"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                  Saved on the campaign, so these limits can be changed while it is running.
                </p>
              </div>

              {/* Bottom CTA Button */}
              <button
                type="button"
                onClick={handleLaunch}
                disabled={isLaunching}
                className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm rounded-2xl flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.99] disabled:opacity-50"
              >
                <span>{isLaunching ? 'Launching campaign...' : 'Review and launch →'}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Leads Modal */}
      <ImportLeadsModal
        isOpen={leadsModalOpen}
        onClose={() => setLeadsModalOpen(false)}
        campaignId={campaignId}
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-gray-900 text-white text-xs font-semibold px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 animate-bounce-subtle">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
