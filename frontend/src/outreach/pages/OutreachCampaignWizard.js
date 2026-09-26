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
  Sparkles,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';
import SequenceCanvas from '../components/sequence/SequenceCanvas';
import ImportLeadsModal from '../components/ImportLeadsModal';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';

const TIME_OPTIONS = [
  '12:00 AM', '12:30 AM', '01:00 AM', '01:30 AM', '02:00 AM', '02:30 AM',
  '03:00 AM', '03:30 AM', '04:00 AM', '04:30 AM', '05:00 AM', '05:30 AM',
  '06:00 AM', '06:30 AM', '07:00 AM', '07:30 AM', '08:00 AM', '08:30 AM',
  '09:00 AM', '09:30 AM', '10:00 AM', '10:30 AM', '11:00 AM', '11:30 AM',
  '12:00 PM', '12:30 PM', '01:00 PM', '01:30 PM', '02:00 PM', '02:30 PM',
  '03:00 PM', '03:30 PM', '04:00 PM', '04:30 PM', '05:00 PM', '05:30 PM',
  '06:00 PM', '06:30 PM', '07:00 PM', '07:30 PM', '08:00 PM', '08:30 PM',
  '09:00 PM', '09:30 PM', '10:00 PM', '10:30 PM', '11:00 PM', '11:30 PM',
];

const TIMEZONE_OPTIONS = [
  { value: 'UTC', label: 'Coordinated Universal Time (UTC)' },
  { value: 'America/New_York', label: 'Eastern Time (US & Canada) (ET)' },
  { value: 'America/Chicago', label: 'Central Time (US & Canada) (CT)' },
  { value: 'America/Denver', label: 'Mountain Time (US & Canada) (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada) (PT)' },
  { value: 'Europe/London', label: 'Greenwich Mean Time (GMT)' },
  { value: 'Europe/Paris', label: 'Central European Time (CET)' },
  { value: 'Asia/Kolkata', label: 'India Standard Time (IST)' },
  { value: 'Asia/Dubai', label: 'Gulf Standard Time (GST)' },
  { value: 'Asia/Singapore', label: 'Singapore Standard Time (SGT)' },
  { value: 'Asia/Tokyo', label: 'Japan Standard Time (JST)' },
  { value: 'Australia/Sydney', label: 'Australian Eastern Time (AET)' },
];

const WEEK_DAYS = [
  { day: 'Sunday', key: 'S' }, { day: 'Monday', key: 'M' }, { day: 'Tuesday', key: 'T' },
  { day: 'Wednesday', key: 'W' }, { day: 'Thursday', key: 'T' }, { day: 'Friday', key: 'F' },
  { day: 'Saturday', key: 'S' },
];

const createDefaultSchedule = () => WEEK_DAYS.map((day, index) => ({
  ...day,
  enabled: index >= 1 && index <= 5,
  ranges: [{ start: '09:00 AM', end: '05:00 PM' }],
}));

const formatTimeLabel = (value) => {
  if (!value) return '09:00 AM';
  if (/\s(AM|PM)$/i.test(value)) return value.toUpperCase();
  const [rawHours, rawMinutes = '00'] = String(value).split(':');
  const hours = Number(rawHours);
  if (!Number.isFinite(hours) || hours < 0 || hours > 23) return '09:00 AM';
  return `${String(hours % 12 || 12).padStart(2, '0')}:${String(rawMinutes).padStart(2, '0')} ${hours < 12 ? 'AM' : 'PM'}`;
};

const normalizeSchedule = (scheduleData) => {
  const defaults = createDefaultSchedule();
  const days = scheduleData?.days;
  if (Array.isArray(days) && days.some((day) => typeof day === 'object')) {
    return defaults.map((defaultDay) => {
      const storedDay = days.find((day) => String(day?.day || '').toLowerCase() === defaultDay.day.toLowerCase());
      if (!storedDay) return defaultDay;
      const ranges = Array.isArray(storedDay.ranges) && storedDay.ranges.length
        ? storedDay.ranges.map((range) => ({ start: formatTimeLabel(range.start), end: formatTimeLabel(range.end) }))
        : defaultDay.ranges;
      return { ...defaultDay, enabled: Boolean(storedDay.enabled), ranges };
    });
  }
  if (Array.isArray(days)) {
    return defaults.map((day, index) => ({ ...day, enabled: days.includes(index === 0 ? 6 : index - 1) }));
  }
  if (scheduleData?.start_time || scheduleData?.end_time) {
    return defaults.map((day, index) => ({
      ...day,
      enabled: (scheduleData.days || [0, 1, 2, 3, 4]).includes(index === 0 ? 6 : index - 1),
      ranges: [{ start: formatTimeLabel(scheduleData.start_time), end: formatTimeLabel(scheduleData.end_time) }],
    }));
  }
  return defaults;
};

const getTimezoneDetail = (timeZone) => {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone, hour: 'numeric', minute: '2-digit', timeZoneName: 'shortOffset',
    }).format(new Date());
  } catch (_) {
    return timeZone;
  }
};

export default function OutreachCampaignWizard({ campaignId = 'new_campaign', initialStep = 1, initialName = '', onBack, onComplete }) {
  const [activeCampaignId, setActiveCampaignId] = useState(
    campaignId && campaignId !== 'new' && campaignId !== 'new_campaign' ? campaignId : null
  );
  const [draftLoading, setDraftLoading] = useState(true);
  const [draftError, setDraftError] = useState('');
  const [draftRetryKey, setDraftRetryKey] = useState(0);
  const [currentStep, setCurrentStep] = useState(initialStep || 1);
  const [campaignName, setCampaignName] = useState(initialName || '');
  const hasUserEditedName = React.useRef(Boolean(initialName));
  const [senders, setSenders] = useState([]);
  const [senderError, setSenderError] = useState('');
  const [senderRetryKey, setSenderRetryKey] = useState(0);
  const [selectedSenders, setSelectedSenders] = useState([]);
  const [leadsModalOpen, setLeadsModalOpen] = useState(false);
  const [connectModalOpen, setConnectModalOpen] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [timezone, setTimezone] = useState('UTC');
  const [isLaunching, setIsLaunching] = useState(false);
  const [conditionalLaunchEnabled, setConditionalLaunchEnabled] = useState(false);
  const [autoLaunchAfterWarmup, setAutoLaunchAfterWarmup] = useState(false);
  const [engageLists, setEngageLists] = useState([]);
  const [selectedEngageListId, setSelectedEngageListId] = useState('');
  const [warmupHours, setWarmupHours] = useState(24);
  const [leadsCount, setLeadsCount] = useState(0);
  const [enrolledLeads, setEnrolledLeads] = useState([]);
  const [loadingLeads, setLoadingLeads] = useState(false);
  const [leadsError, setLeadsError] = useState('');

  const [schedule, setSchedule] = useState(createDefaultSchedule);
  const sequenceSaveRef = React.useRef(null);
  const navigationInFlight = React.useRef(false);
  const registerSequenceSave = React.useCallback((saveSequence) => {
    sequenceSaveRef.current = saveSequence;
  }, []);

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

  const resetSafeDefaults = () => {
    setLimits({
      connection_invites: 20,
      messages: 20,
      voice_notes: 20,
      inmails: 20,
      profile_visits: 20,
      follows: 20,
      post_likes: 20,
      comments: 20,
    });
    showToast('Reset to safe defaults (20/day)');
  };

  const toggleDayEnabled = (idx) => {
    setSchedule((prev) =>
      prev.map((d, i) => (i === idx ? { ...d, enabled: !d.enabled } : d))
    );
  };

  const updateRangeTime = (dIdx, rIdx, field, val) => {
    setSchedule((prev) =>
      prev.map((dayItem, i) => {
        if (i !== dIdx) return dayItem;
        const newRanges = dayItem.ranges.map((rng, j) => {
          if (j !== rIdx) return rng;
          return { ...rng, [field]: val };
        });
        return { ...dayItem, ranges: newRanges };
      })
    );
  };

  const addRange = (dIdx) => {
    setSchedule((prev) =>
      prev.map((dayItem, i) => {
        if (i !== dIdx) return dayItem;
        return {
          ...dayItem,
          ranges: [...dayItem.ranges, { start: '01:00 PM', end: '05:00 PM' }],
        };
      })
    );
  };

  const removeRange = (dIdx, rIdx) => {
    setSchedule((prev) =>
      prev.map((dayItem, i) => {
        if (i !== dIdx) return dayItem;
        if (dayItem.ranges.length <= 1) {
          return { ...dayItem, enabled: false };
        }
        return {
          ...dayItem,
          ranges: dayItem.ranges.filter((_, j) => j !== rIdx),
        };
      })
    );
  };

  const showToast = (msg) => {
    toast.success(msg);
  };

  const fetchEnrolledLeads = async (cid) => {
    const targetCid = cid || activeCampaignId || campaignId;
    if (!targetCid || targetCid === 'new' || targetCid === 'new_campaign') return;
    setLoadingLeads(true);
    setLeadsError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/leads?campaign_id=${targetCid}&limit=20`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Campaign leads could not be loaded.');
      setEnrolledLeads(data.leads || []);
      setLeadsCount(data.total ?? data.leads?.length ?? 0);
    } catch (err) {
      console.error('Failed to fetch enrolled leads:', err);
      setLeadsError(err.message || 'Campaign leads could not be loaded.');
    } finally {
      setLoadingLeads(false);
    }
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

  const syncDraft = async (overrideName, overrideStep) => {
    const rawName = overrideName !== undefined ? overrideName : campaignName;
    const targetName = (rawName || '').trim() || 'Connect and follow up';
    try {
      const token = localStorage.getItem('token');
      const step = overrideStep !== undefined ? overrideStep : currentStep;
      const progress = step === 1 ? 20 : step === 2 ? 60 : 80;
      const nextLabel =
        step === 1
          ? 'Next: configure sequence'
          : step === 2
          ? 'Next: review senders and launch'
          : 'Next: launch';

      const payload = {
        name: targetName,
        draft_step: step,
        draft_progress: progress,
        next_step_label: nextLabel,
        sender_account_ids: selectedSenders,
        schedule: {
          timezone,
          days: schedule,
        },
        limits,
      };

      if (activeCampaignId && activeCampaignId !== 'new' && activeCampaignId !== 'new_campaign') {
        payload.campaign_id = activeCampaignId;
      }

      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const doc = await res.json();
        if (doc && doc.id) {
          setActiveCampaignId(doc.id);
          if (!hasUserEditedName.current && doc.name) {
            setCampaignName(doc.name);
          }
          return doc;
        }
      }
    } catch (err) {
      console.error('Draft auto-save failed:', err);
    }
    return null;
  };

  const navigateToStep = async (nextStep) => {
    if (nextStep === currentStep || navigationInFlight.current) return;
    navigationInFlight.current = true;
    try {
      if (currentStep === 2 && sequenceSaveRef.current && !(await sequenceSaveRef.current())) {
        toast.error('Sequence could not be saved. Please review it and try again.');
        return;
      }
      if (!(await syncDraft(undefined, nextStep))) {
        toast.error('Campaign changes could not be saved. Please try again.');
        return;
      }
      setCurrentStep(nextStep);
    } catch (err) {
      toast.error(err.message || 'Campaign changes could not be saved. Please try again.');
    } finally {
      navigationInFlight.current = false;
    }
  };

  // Initial load / create draft
  useEffect(() => {
    let cancelled = false;
    const initCampaign = async () => {
      const token = localStorage.getItem('token');
      setDraftLoading(true);
      setDraftError('');
      try {
        if (campaignId && campaignId !== 'new' && campaignId !== 'new_campaign') {
          const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}`, {
            credentials: 'include',
            headers: { Authorization: token ? `Bearer ${token}` : '' },
          });
          if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Campaign could not be loaded');
          const data = await res.json();
          if (!data?.id) throw new Error('Campaign could not be loaded');
          if (['active', 'warming_up'].includes(data.status)) throw new Error('Pause the campaign before editing its sequence or settings.');
          if (!cancelled) {
            setActiveCampaignId(data.id);
            if (data.name && !hasUserEditedName.current) {
              setCampaignName(data.name);
            }
            if (data.schedule) setSchedule(normalizeSchedule(data.schedule));
            if (data.schedule?.timezone) setTimezone(data.schedule.timezone);
            if (data.limits) setLimits(data.limits);
            if (data.sender_account_ids?.length) setSelectedSenders(data.sender_account_ids);
            if (initialStep) setCurrentStep(initialStep);
            else if (data.draft_step) setCurrentStep(data.draft_step);
          }
        } else {
          // Auto-create draft immediately in MongoDB if none provided
          const defaultInitialName = (campaignName || initialName || '').trim() || 'Connect and follow up';
          const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              Authorization: token ? `Bearer ${token}` : '',
            },
            body: JSON.stringify({
              name: defaultInitialName,
              draft_step: initialStep || 1,
              draft_progress: initialStep === 1 ? 20 : initialStep === 2 ? 60 : 80,
              next_step_label:
                initialStep === 1
                  ? 'Next: configure sequence'
                  : initialStep === 2
                  ? 'Next: review senders and launch'
                  : 'Next: launch',
              schedule: { timezone, days: schedule },
              limits,
            }),
          });
          if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Campaign draft could not be created');
          const doc = await res.json();
          if (!doc?.id) throw new Error('Campaign draft could not be created');
          if (!cancelled) {
            setActiveCampaignId(doc.id);
            if (doc.name && !hasUserEditedName.current) {
              setCampaignName(doc.name);
            }
          }
        }
      } catch (err) {
        if (!cancelled) setDraftError(err.message || 'Campaign draft could not be loaded');
      } finally {
        if (!cancelled) setDraftLoading(false);
      }
    };
    initCampaign();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId, initialStep, draftRetryKey]);

  useEffect(() => {
    if (activeCampaignId) {
      fetchEnrolledLeads(activeCampaignId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCampaignId]);

  useEffect(() => {
    if (currentStep !== 3) return undefined;
    let canceled = false;
    const loadWarmupOptions = async () => {
      try {
        const token = localStorage.getItem('token');
        const options = { credentials: 'include', headers: { Authorization: token ? `Bearer ${token}` : '' } };
        const [featureRes, listRes] = await Promise.all([
          fetch('/api/v1/outreach/campaigns/features/conditional-launch', options),
          fetch('/api/v1/outreach/engage/lists', options),
        ]);
        if (canceled) return;
        if (featureRes.ok) setConditionalLaunchEnabled(Boolean((await featureRes.json()).enabled));
        if (listRes.ok) setEngageLists((await listRes.json()) || []);
      } catch (_) { /* Manual launch remains available. */ }
    };
    loadWarmupOptions();
    return () => { canceled = true; };
  }, [currentStep]);

  const handleLaunch = async () => {
    if (!campaignName.trim()) {
      toast.error('Add a campaign name before launching.');
      return;
    }
    if (!selectedSenders.length) {
      toast.error('Select at least one active LinkedIn sender account.');
      return;
    }
    const hasValidHours = schedule.some((day) => day.enabled && day.ranges?.some((range) => (
      TIME_OPTIONS.includes(range.start) && TIME_OPTIONS.includes(range.end)
      && TIME_OPTIONS.indexOf(range.start) < TIME_OPTIONS.indexOf(range.end)
    )));
    if (!hasValidHours) {
      toast.error('Choose at least one valid working-hours range.');
      return;
    }
    if (!leadsCount) {
      toast.error('Add at least one lead before launching this campaign.');
      return;
    }
    if (autoLaunchAfterWarmup && (!conditionalLaunchEnabled || !selectedEngageListId)) {
      toast.error('Select a Social Warm-Up Cohort before arming conditional launch.');
      return;
    }
    setIsLaunching(true);
    try {
      const savedDraft = await syncDraft(campaignName, 3);
      const targetId = savedDraft?.id || activeCampaignId || campaignId;
      if (!savedDraft?.id || targetId === 'new' || targetId === 'new_campaign') {
        throw new Error('Campaign draft could not be saved. Try again before launching.');
      }
      if (sequenceSaveRef.current && !(await sequenceSaveRef.current())) {
        throw new Error('Sequence could not be saved. Please review it and try again.');
      }
      const token = localStorage.getItem('token');
      const payload = {
        name: campaignName,
        sender_account_ids: selectedSenders,
        schedule,
        timezone,
        daily_limits: limits,
        status: 'active',
      };
      const path = autoLaunchAfterWarmup ? 'arm-warmup' : 'launch';
      const res = await fetch(`/api/v1/outreach/campaigns/${targetId}/${path}`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify(autoLaunchAfterWarmup
          ? { engage_list_id: selectedEngageListId, warmup_hours: Number(warmupHours) }
          : payload),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Campaign could not be launched.');
      }
      setReviewModalOpen(false);
      showToast(autoLaunchAfterWarmup
        ? 'Campaign armed. It will wait for every lead to be engaged and the cooldown to finish.'
        : 'Campaign successfully launched!');
      setTimeout(() => {
        if (onComplete) onComplete();
        else if (onBack) onBack();
      }, 1000);
    } catch (err) {
      console.error('Launch failed:', err);
      toast.error(err.message || 'Campaign could not be launched.');
    } finally {
      setIsLaunching(false);
    }
  };

  useEffect(() => {
    // Fetch available senders
    const fetchSenders = async () => {
      setSenderError('');
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/v1/outreach/accounts', {
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'LinkedIn senders could not be loaded.');
        if (!Array.isArray(data)) throw new Error('LinkedIn senders returned an invalid response.');
        setSenders(data);
        const activeAccounts = data.filter((account) => account.status === 'active');
        const activeIds = new Set(activeAccounts.map((account) => account.id));
        setSelectedSenders((current) => {
          const stillActive = current.filter((id) => activeIds.has(id));
          return stillActive.length || !activeAccounts.length ? stillActive : [activeAccounts[0].id];
        });
      } catch (err) {
        console.error('Failed to fetch senders:', err);
        setSenderError(err.message || 'LinkedIn senders could not be loaded.');
      }
    };
    fetchSenders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senderRetryKey]);

  const handleSaveAsTemplate = async () => {
    try {
      const token = localStorage.getItem('token');
      const savedDraft = await syncDraft();
      if (!savedDraft?.id) throw new Error('Save the campaign draft before creating a template.');
      if (sequenceSaveRef.current && !(await sequenceSaveRef.current())) {
        throw new Error('Save the sequence before creating a template.');
      }
      let nodes = [];
      let edges = [];
      let tree = null;

      if (activeCampaignId) {
        const seqRes = await fetch(`/api/v1/outreach/sequences/${activeCampaignId}`, {
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (seqRes.ok) {
          const seqData = await seqRes.json();
          if (seqData.is_default) {
            throw new Error('Open the sequence editor and save your sequence before creating a template.');
          }
          nodes = seqData.nodes || [];
          edges = seqData.edges || [];
          tree = seqData.tree || null;
        }
      }

      if (!nodes.length) throw new Error('This campaign does not have a saved sequence yet.');

      const res = await fetch('/api/v1/outreach/sequences/templates', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: campaignName || 'Custom Template',
          description: `Custom sequence template saved from campaign "${campaignName || ''}"`,
          nodes,
          edges,
          tree,
        }),
      });
      if (res.ok) {
        showToast(`Saved "${campaignName}" as template!`);
      } else {
        const errData = await res.json().catch(() => ({}));
        toast.error(errData.detail || 'Failed to save template');
      }
    } catch (err) {
      console.error('Failed to save template:', err);
      toast.error(err.message || 'Failed to save template.');
    }
  };

  if (draftLoading || draftError || !activeCampaignId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-white p-8 text-center">
        <p className="text-sm font-semibold text-gray-900">{draftLoading ? 'Preparing your campaign…' : draftError || 'Campaign draft is unavailable'}</p>
        {!draftLoading && <div className="flex gap-3">
          <button type="button" onClick={() => setDraftRetryKey((current) => current + 1)} className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white">Retry</button>
          {onBack && <button type="button" onClick={onBack} className="rounded-lg border border-gray-300 px-4 py-2 text-xs font-semibold text-gray-700">Back to campaigns</button>}
        </div>}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full max-h-full min-h-0 bg-white overflow-hidden">
      {/* Top Navigation Bar */}
      <div className="border-b border-gray-200/80 bg-white z-20 shrink-0">
        {/* Row 1: Workspace info & Main title actions */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
          {/* Left: Back button + Campaign Name */}
          <div className="flex items-center gap-4">
            <button
              onClick={async () => {
                const saved = await syncDraft(campaignName);
                if (!saved) {
                  toast.error('Campaign changes could not be saved. Please try again.');
                  return;
                }
                if (sequenceSaveRef.current && !(await sequenceSaveRef.current())) {
                  toast.error('Sequence could not be saved. Please try again before leaving.');
                  return;
                }
                if (onBack) onBack();
              }}
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
                onChange={(e) => {
                  hasUserEditedName.current = true;
                  setCampaignName(e.target.value);
                }}
                onBlur={() => syncDraft(campaignName)}
                placeholder="Name your campaign"
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
            <button
              onClick={handleSaveAsTemplate}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs"
            >
              Save as template
            </button>
            <button
              onClick={async () => {
                const saved = await syncDraft(campaignName);
                if (!saved) {
                  toast.error('Campaign changes could not be saved. Please try again.');
                  return;
                }
                if (sequenceSaveRef.current && !(await sequenceSaveRef.current())) {
                  toast.error('Sequence could not be saved. Please try again before closing.');
                  return;
                }
                toast.success('Campaign saved to drafts');
                if (onBack) onBack(saved);
              }}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 transition-colors shadow-2xs"
            >
              Save and close
            </button>

            {/* Ready indicator */}
            <div className="hidden sm:flex items-center gap-2 pl-2">
              <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-600 rounded-full transition-all duration-300"
                  style={{ width: `${currentStep === 1 ? 20 : currentStep === 2 ? 60 : 80}%` }}
                />
              </div>
              <span className="text-[11px] font-semibold text-gray-500">
                {currentStep === 1 ? '20%' : currentStep === 2 ? '60%' : '80%'} ready
              </span>
            </div>

            <button
              onClick={async () => {
                if (currentStep < 3) {
                  await navigateToStep(currentStep + 1);
                } else {
                  setReviewModalOpen(true);
                }
              }}
              className="inline-flex items-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-xs transition-colors"
            >
              {currentStep === 1
                ? 'Next: Sequence →'
                : currentStep === 2
                ? 'Next: Launch →'
                : 'Launch Campaign'}
            </button>
          </div>
        </div>

        {/* Row 2: Step Indicator Tabs */}
        <div className="flex items-center gap-8 px-6 py-2.5 text-xs font-semibold bg-gray-50/40">
          <button
            onClick={() => navigateToStep(1)}
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
            <span>Leads</span>
            {leadsCount > 0 && (
              <span className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold px-1.5 py-0.5 rounded-full">
                {leadsCount}
              </span>
            )}
          </button>

          <button
            onClick={() => navigateToStep(2)}
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
            onClick={() => navigateToStep(3)}
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
          <div className="flex-1 min-h-0 overflow-y-auto bg-[#f8f9fa] py-8 px-6">
            <div className="max-w-4xl mx-auto space-y-6">
              {leadsError && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  {leadsError} <button type="button" onClick={() => fetchEnrolledLeads(activeCampaignId)} className="ml-2 font-semibold underline">Retry</button>
                </div>
              )}
              {loadingLeads ? <p className="text-sm text-gray-500">Loading campaign leads…</p> : leadsError ? null : leadsCount === 0 ? (
                <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center shadow-xs">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 mb-4">
                    <Users className="h-7 w-7" />
                  </div>
                  <h2 className="text-2xl font-bold text-gray-900 tracking-tight">Add your leads</h2>
                  <p className="text-sm text-gray-500 mt-2 max-w-md mx-auto leading-relaxed">
                    Upload a CSV spreadsheet of LinkedIn profiles. We will handle deduplication automatically.
                  </p>
                  <button
                    onClick={() => setLeadsModalOpen(true)}
                    className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 shadow-sm transition-all"
                  >
                    <Plus className="h-4 w-4" />
                    Import leads list
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                        <CheckCircle2 className="h-6 w-6" />
                      </div>
                      <div>
                        <h2 className="text-lg font-bold text-gray-900">
                          {leadsCount} lead{leadsCount !== 1 ? 's' : ''} enrolled
                        </h2>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Prospects loaded into this campaign and queued for outbound steps.
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setLeadsModalOpen(true)}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Add more leads
                      </button>
                      <button
                        onClick={() => navigateToStep(2)}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors"
                      >
                        Proceed to Sequence →
                      </button>
                    </div>
                  </div>

                  {/* Leads Preview Table */}
                  <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-xs">
                    <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-800">Recent Prospects Preview</span>
                      <span className="text-[11px] text-gray-400">
                        Showing up to {enrolledLeads.length} leads
                      </span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
                          <tr>
                            <th className="py-2.5 px-5">NAME</th>
                            <th className="py-2.5 px-5">JOB TITLE</th>
                            <th className="py-2.5 px-5">COMPANY</th>
                            <th className="py-2.5 px-5">STATE</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {enrolledLeads.slice(0, 10).map((lead) => (
                            <tr key={lead.id} className="hover:bg-gray-50/50">
                              <td className="py-3 px-5 font-semibold text-gray-900">
                                {lead.first_name} {lead.last_name || ''}
                              </td>
                              <td className="py-3 px-5 text-gray-600">{lead.job_title || '—'}</td>
                              <td className="py-3 px-5 text-gray-600">{lead.company_name || '—'}</td>
                              <td className="py-3 px-5">
                                <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                                  {lead.execution_state || 'queued'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 2: Visual Canvas (Part 1, Image 4) */}
        {currentStep === 2 && (
        <SequenceCanvas campaignId={activeCampaignId || campaignId} onRegisterSave={registerSequenceSave} />
        )}

        {/* Step 3: Launch, Multi-Sender Pooling & Safe Defaults (media_1790103490135.png) */}
        {currentStep === 3 && (
          <div className="flex-1 min-h-0 overflow-y-auto bg-[#f8f9fa] py-8 px-6">
            <div className="max-w-3xl mx-auto space-y-6 pb-24">
              {/* Top Status Pill matching media_1790103490135.png */}
              <div className="flex items-center">
                <div className="inline-flex items-center px-3 py-1 rounded-full border border-indigo-100 bg-indigo-50/80 text-indigo-700 text-xs font-semibold shadow-2xs">
                  Campaign settings will be enforced when this campaign runs.
                </div>
              </div>

              {/* Card 1: Campaign name */}
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xs">
                <h3 className="text-base font-bold text-gray-900 tracking-tight">Campaign name</h3>
                <input
                  type="text"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  placeholder="First outreach campaign"
                  className="mt-3 w-full rounded-xl border border-gray-200 px-4 py-3 text-sm font-medium text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 bg-white transition-all shadow-2xs"
                />
                <p className="text-xs text-gray-500 mt-2.5">
                  Pick a name your team will recognize in the campaign list.
                </p>
              </div>

              {/* Section 2: Who is sending? (Heading on background, not in card) */}
              <div className="space-y-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900 tracking-tight">Who is sending?</h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Pick the accounts that send this campaign. We spread the work to keep each account safe.
                  </p>
                </div>

                {/* Control bar above the card */}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs font-bold text-gray-900">
                    {selectedSenders.length} of {senders.length} selected
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedSenders(senders.filter((s) => s.status === 'active').map((s) => s.id))}
                      className="rounded-lg border border-gray-200 bg-white px-3.5 py-1 text-xs font-semibold text-indigo-600 hover:bg-gray-50 transition-colors shadow-2xs"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedSenders([])}
                      className="rounded-lg border border-gray-200 bg-white px-3.5 py-1 text-xs font-semibold text-gray-500 hover:bg-gray-50 transition-colors shadow-2xs"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                {/* Accounts Card */}
                <div className="rounded-2xl border border-gray-200 bg-white p-7 shadow-xs">
                  {senderError && (
                    <div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                      <span>{senderError}</span>
                      <button type="button" className="font-bold underline" onClick={() => setSenderRetryKey((key) => key + 1)}>Retry</button>
                    </div>
                  )}
                  {senders.length === 0 ? (
                    <div className="py-6 text-center text-xs text-gray-500 leading-relaxed">
                      <p>
                        No LinkedIn account is connected to this workspace yet. Connect one in Settings, then come back and pick it here.
                      </p>
                      <button
                        type="button"
                        onClick={() => setConnectModalOpen(true)}
                        className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-indigo-600 hover:text-indigo-800 transition-colors"
                      >
                        + Connect an account now
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {senders.map((s) => {
                        const isChecked = selectedSenders.includes(s.id);
                        const isActive = s.status === 'active';
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
                                disabled={!isActive}
                                onChange={(e) => {
                                  if (e.target.checked) setSelectedSenders((current) => [...new Set([...current, s.id])]);
                                  else setSelectedSenders((current) => current.filter((id) => id !== s.id));
                                }}
                                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                              />
                              <div>
                                <span className="font-bold text-xs text-gray-900 block">{s.account_name}</span>
                                <span className="text-[11px] text-gray-400">
                                  {s.country_code ? `${s.country_code} Residential Proxy` : 'Assigned Proxy'}
                                </span>
                              </div>
                            </div>
                            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                              isActive
                                ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                                : 'text-amber-700 bg-amber-50 border-amber-200'
                            }`}>
                              {s.status || 'Unavailable'}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Section 3: When should it run? (Heading on background, not in card) */}
              <div className="space-y-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900 tracking-tight">When should it run?</h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Choose the local hours when this campaign may send. One campaign timezone applies to every enrolled lead.
                  </p>
                </div>

                <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xs space-y-6">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
                      <Calendar className="w-4 h-4 text-gray-600" />
                      <span>Weekly hours</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Turn a day off to make it unavailable, or add another time range.
                    </p>
                  </div>

                  {/* Day rows with fine horizontal dividers matching screenshot */}
                  <div className="divide-y divide-gray-100 border-t border-b border-gray-100">
                    {schedule.map((dayItem, dIdx) => (
                      <div key={dayItem.day} className="flex items-center justify-between py-3 text-xs">
                        <div className="flex items-center gap-3">
                          {/* Day Circle Button */}
                          <button
                            type="button"
                            onClick={() => toggleDayEnabled(dIdx)}
                            title={`Toggle ${dayItem.day}`}
                            className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold transition-all ${
                              dayItem.enabled
                                ? 'bg-black text-white'
                                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                            }`}
                          >
                            {dayItem.key}
                          </button>

                          {dayItem.enabled ? (
                            <div className="flex items-center gap-2">
                              {dayItem.ranges.map((rng, rIdx) => (
                                <div key={rIdx} className="flex items-center gap-2">
                                  {/* Start Time Select */}
                                  <div className="relative inline-flex items-center">
                                    <select
                                      value={rng.start}
                                      onChange={(e) => updateRangeTime(dIdx, rIdx, 'start', e.target.value)}
                                      className="appearance-none bg-gray-50/80 border border-gray-200 rounded-lg px-2.5 py-1.5 pr-7 text-xs font-semibold text-gray-800 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer shadow-2xs"
                                    >
                                      {TIME_OPTIONS.map((t) => (
                                        <option key={t} value={t}>{t}</option>
                                      ))}
                                    </select>
                                    <Clock className="w-3 h-3 text-gray-400 absolute right-2 pointer-events-none" />
                                  </div>

                                  <span className="text-xs text-gray-400 font-medium">to</span>

                                  {/* End Time Select */}
                                  <div className="relative inline-flex items-center">
                                    <select
                                      value={rng.end}
                                      onChange={(e) => updateRangeTime(dIdx, rIdx, 'end', e.target.value)}
                                      className="appearance-none bg-gray-50/80 border border-gray-200 rounded-lg px-2.5 py-1.5 pr-7 text-xs font-semibold text-gray-800 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer shadow-2xs"
                                    >
                                      {TIME_OPTIONS.map((t) => (
                                        <option key={t} value={t}>{t}</option>
                                      ))}
                                    </select>
                                    <Clock className="w-3 h-3 text-gray-400 absolute right-2 pointer-events-none" />
                                  </div>

                                  {/* Inline Remove range button (✕) */}
                                  <button
                                    type="button"
                                    onClick={() => removeRange(dIdx, rIdx)}
                                    title="Remove range"
                                    className="p-1 text-gray-400 hover:text-gray-600 transition-colors ml-0.5"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-gray-400 font-normal">Unavailable</span>
                              <button
                                type="button"
                                onClick={() => toggleDayEnabled(dIdx)}
                                title="Make available"
                                className="p-0.5 border border-gray-200 rounded-md text-gray-500 hover:text-gray-800 hover:bg-gray-50 shadow-2xs"
                              >
                                <Plus className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </div>

                        {/* Right Action Icons for Enabled Days (+ and Copy) */}
                        {dayItem.enabled && (
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              onClick={() => addRange(dIdx)}
                              title="Add another time range"
                              className="p-1 text-gray-400 hover:text-gray-700 transition-colors"
                            >
                              <Plus className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => copyToAllWeekdays(dIdx)}
                              title="Copy schedule to all weekdays"
                              className="p-1 text-gray-400 hover:text-gray-700 transition-colors"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Timezone Section */}
                  <div className="pt-2">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                      TIMEZONE
                    </p>
                    <div className="relative">
                      <select
                        value={timezone}
                        onChange={(e) => setTimezone(e.target.value)}
                        className="w-full appearance-none rounded-xl border border-gray-200 bg-white px-4 py-3 text-xs font-semibold text-gray-900 pr-10 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-2xs cursor-pointer"
                      >
                        {TIMEZONE_OPTIONS.map((tz) => (
                          <option key={tz.value} value={tz.value}>
                            {tz.label} · {getTimezoneDetail(tz.value)}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="w-4 h-4 text-gray-400 absolute right-3.5 top-3.5 pointer-events-none" />
                    </div>
                    <p className="text-[11px] text-gray-400 mt-2">
                      This timezone applies to the whole campaign, not separately to each lead or sender.
                    </p>
                  </div>
                </div>
              </div>

              {/* Section 4: Daily limits, applied per sender Card */}
              <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-bold text-gray-900">Daily limits, applied per sender</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Daily action limits per sender. The effective cap is the lower of this value and the sender account's own safety limit.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={resetSafeDefaults}
                    className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 hover:bg-emerald-100 transition-colors uppercase cursor-pointer"
                  >
                    safe defaults
                  </button>
                </div>

                {/* 8 Rows with dividers matching media_1790103490135.png */}
                <div className="divide-y divide-gray-100">
                  {[
                    { key: 'connection_invites', label: 'Connection invites', def: 20 },
                    { key: 'messages', label: 'Messages', def: 20 },
                    { key: 'voice_notes', label: 'Voice notes', def: 20 },
                    { key: 'inmails', label: 'InMails', def: 20, supported: false },
                    { key: 'profile_visits', label: 'Profile visits', def: 20 },
                    { key: 'follows', label: 'Follows', def: 20, supported: false },
                    { key: 'post_likes', label: 'Post likes', def: 20 },
                    { key: 'comments', label: 'Comments', def: 20, supported: false },
                  ].map((item) => (
                    <div key={item.key} className="flex items-center justify-between py-2.5">
                      <div>
                        <span className="text-xs font-semibold text-gray-900 block">{item.label}</span>
                        <span className="text-[11px] text-gray-400">{item.supported === false ? 'Runner support coming soon' : `default of ${item.def}`}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={item.supported === false}
                          onClick={() => handleLimitChange(item.key, -1)}
                          className="w-8 h-8 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 flex items-center justify-center text-gray-500 font-semibold transition-colors shadow-2xs disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Minus className="w-3 h-3" />
                        </button>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          disabled={item.supported === false}
                          value={limits[item.key] ?? item.def}
                          onChange={(e) => {
                            const val = parseInt(e.target.value, 10);
                            setLimits((prev) => ({
                              ...prev,
                              [item.key]: isNaN(val) ? 0 : Math.max(0, Math.min(100, val)),
                            }));
                          }}
                          className="w-14 h-8 rounded-lg border border-gray-200 bg-white text-center text-xs font-bold text-gray-900 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-2xs disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                        <button
                          type="button"
                          disabled={item.supported === false}
                          onClick={() => handleLimitChange(item.key, 1)}
                          className="w-8 h-8 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 flex items-center justify-center text-gray-500 font-semibold transition-colors shadow-2xs disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Plus className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                  Saved on the campaign, so these limits can be changed while it is running.
                </p>
              </div>

              <div className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-6 space-y-3">
                <h3 className="text-sm font-bold text-gray-900">Social Warm-Up Cohort</h3>
                <p className="text-xs text-gray-600">
                  Optional: hold this campaign until every lead has confirmed engagement in a linked Engage list and the 24- or 48-hour cooldown has elapsed.
                </p>
                {conditionalLaunchEnabled ? (
                  <>
                    <label className="flex items-center gap-2 text-xs font-semibold text-gray-800">
                      <input type="checkbox" aria-label="Automatically launch after warm-up" checked={autoLaunchAfterWarmup}
                        onChange={(event) => setAutoLaunchAfterWarmup(event.target.checked)} />
                      Automatically launch after warm-up
                    </label>
                    {autoLaunchAfterWarmup && (
                      <div className="grid gap-3 sm:grid-cols-2">
                        <fieldset className="space-y-1 text-xs font-semibold text-gray-700">
                          <legend>Social warm-up cohort</legend>
                          {engageLists.filter((list) => !list.campaign_id || list.campaign_id === activeCampaignId)
                            .map((list) => <label key={list.id} className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2">
                              <input type="radio" name="engage-cohort" value={list.id} checked={selectedEngageListId === list.id}
                                onChange={() => setSelectedEngageListId(list.id)} />
                              {list.name}
                            </label>)}
                          {engageLists.length === 0 && <p>No Engage lists yet. Create one in Engage & Grow first.</p>}
                        </fieldset>
                        <label className="text-xs font-semibold text-gray-700">Cooldown
                          <select value={warmupHours} onChange={(event) => setWarmupHours(Number(event.target.value))}
                            className="mt-1 w-full rounded-lg border border-gray-200 bg-white p-2 text-xs">
                            <option value={24}>24 hours</option><option value={48}>48 hours</option>
                          </select>
                        </label>
                      </div>
                    )}
                  </>
                ) : <p className="text-xs text-amber-800">Conditional auto-launch is unavailable for this deployment. You can still launch manually after reviewing engagement.</p>}
              </div>

              {/* Bottom CTA Button matching media_1790103490135.png */}
              <button
                type="button"
                onClick={() => setReviewModalOpen(true)}
                className="w-full py-4 bg-[#5851ea] hover:bg-[#4a42e0] text-white font-semibold text-sm rounded-2xl flex items-center justify-center gap-2 shadow-sm transition-all active:scale-[0.99] cursor-pointer"
              >
                <span>Review and launch →</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Pre-launch Review Modal */}
      {reviewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-fade-in">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-gray-100 space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div>
                <h3 className="text-lg font-bold text-gray-900">{autoLaunchAfterWarmup ? 'Review conditional launch' : 'Review campaign launch'}</h3>
                <p className="text-xs text-gray-500">{autoLaunchAfterWarmup
                  ? 'You explicitly authorize activation when every lead is engaged and the cooldown has elapsed.'
                  : 'Confirm settings before activating outbound automations'}</p>
              </div>
              <button
                onClick={() => setReviewModalOpen(false)}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs">
              <div className="p-3 bg-gray-50 rounded-xl flex justify-between">
                <span className="text-gray-500">Campaign:</span>
                <span className="font-bold text-gray-900">{campaignName}</span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl flex justify-between">
                <span className="text-gray-500">Sending Accounts:</span>
                <span className="font-bold text-gray-900">{selectedSenders.length} account(s) selected</span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl flex justify-between">
                <span className="text-gray-500">Active Days:</span>
                <span className="font-bold text-gray-900">
                  {schedule.filter((s) => s.enabled).map((s) => s.day).join(', ') || 'None'}
                </span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl flex justify-between">
                <span className="text-gray-500">Timezone:</span>
                <span className="font-bold text-gray-900">{timezone}</span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl flex justify-between">
                <span className="text-gray-500">Max Connection Invites:</span>
                <span className="font-bold text-indigo-600">{limits.connection_invites} / day / sender</span>
              </div>
              {autoLaunchAfterWarmup && <div className="p-3 bg-indigo-50 rounded-xl text-indigo-900">
                Linked Engage list: {engageLists.find((list) => list.id === selectedEngageListId)?.name || 'Not selected'} · {warmupHours}-hour cooldown. You can pause before activation.
              </div>}
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setReviewModalOpen(false)}
                className="flex-1 py-3 border border-gray-200 rounded-xl text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Back to edit
              </button>
              <button
                type="button"
                onClick={handleLaunch}
                disabled={isLaunching}
                className="flex-1 py-3 bg-[#5851ea] hover:bg-[#4a42e0] rounded-xl text-xs font-semibold text-white shadow-xs transition-colors disabled:opacity-50"
              >
                {isLaunching ? 'Saving...' : autoLaunchAfterWarmup ? 'Confirm conditional launch' : 'Confirm and Launch 🚀'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Connect LinkedIn Modal */}
      <ConnectLinkedInModal
        isOpen={connectModalOpen}
        onClose={() => setConnectModalOpen(false)}
        onAccountConnected={(newAcc) => {
          setSenders((prev) => [...prev.filter((sender) => sender.id !== newAcc.id), newAcc]);
          setSelectedSenders((prev) => [...new Set([...prev, newAcc.id])]);
          setSenderError('');
          showToast(`Account ${newAcc.account_name || 'LinkedIn'} connected!`);
        }}
      />

      {/* Leads Modal */}
      <ImportLeadsModal
        isOpen={leadsModalOpen}
        onClose={() => setLeadsModalOpen(false)}
        campaignId={activeCampaignId || campaignId}
        onLeadsImported={() => {
          fetchEnrolledLeads(activeCampaignId || campaignId);
          toast.success('Leads enrolled into campaign!');
        }}
      />
    </div>
  );
}
