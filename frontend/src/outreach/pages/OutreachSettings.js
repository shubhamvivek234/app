import React, { useState, useEffect, useCallback } from 'react';
import {
  Check,
  CreditCard,
  Shield,
  Sparkles,
  Minus,
  Plus,
  Users,
  UserPlus,
  Mail,
  Trash2,
  Copy,
  ExternalLink,
  HelpCircle,
  ChevronDown,
  ChevronRight,
  X,
  Loader2,
  AlertTriangle,
  Globe,
  Sliders,
} from 'lucide-react';
import { toast } from 'sonner';
import OutreachAccounts from './OutreachAccounts';

export default function OutreachSettings({ initialTab = 'accounts' }) {
  const [activeTab, setActiveTab] = useState(initialTab);

  // ── Billing State ──────────────────────────────────────────────────────────
  const [interval, setInterval] = useState('monthly'); // 'annual' | 'quarterly' | 'monthly'
  const [seats, setSeats] = useState(1);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialActive, setTrialActive] = useState(false);
  const [trialDaysLeft, setTrialDaysLeft] = useState(4);
  const [rateCards, setRateCards] = useState([]);
  const [featuresIncluded, setFeaturesIncluded] = useState([]);
  const [billingEmail, setBillingEmail] = useState('');
  const [billingModalOpen, setBillingModalOpen] = useState(false);
  const [newBillingEmail, setNewBillingEmail] = useState('');
  const [savingBillingEmail, setSavingBillingEmail] = useState(false);
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [cancelingSubscription, setCancelingSubscription] = useState(false);

  // ── Members State ──────────────────────────────────────────────────────────
  const [members, setMembers] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [currentUserRole, setCurrentUserRole] = useState('viewer');
  const [permissions, setPermissions] = useState({});
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('editor');
  const [sendingInvite, setSendingInvite] = useState(false);

  // ── Help State ─────────────────────────────────────────────────────────────
  const [expandedFaq, setExpandedFaq] = useState(null);

  // ── Fetch Billing Data ─────────────────────────────────────────────────────
  const fetchBilling = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/plans', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setRateCards(data.rate_cards || []);
        setFeaturesIncluded(data.features_included || []);
        setTrialActive(data.trial_active || false);
        if (data.trial_days_remaining) setTrialDaysLeft(data.trial_days_remaining);
        if (data.subscription?.seats) setSeats(data.subscription.seats);
        if (data.subscription?.interval) setInterval(data.subscription.interval);
        if (data.billing_email) {
          setBillingEmail(data.billing_email);
          setNewBillingEmail(data.billing_email);
        }
      }
    } catch (err) {
      console.error('Failed to load billing plans:', err);
    }
  }, []);

  // ── Fetch Members Data ─────────────────────────────────────────────────────
  const fetchMembers = useCallback(async () => {
    setLoadingMembers(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/workspace/members', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setMembers(data.members || []);
        setPendingInvites(data.pending_invites || []);
        setCurrentUserRole(data.current_user_role || 'viewer');
        setPermissions(data.permissions || {});
      }
    } catch (err) {
      console.error('Failed to load members:', err);
    } finally {
      setLoadingMembers(false);
    }
  }, []);

  useEffect(() => {
    fetchBilling();
  }, [fetchBilling]);

  useEffect(() => {
    if (activeTab === 'members') {
      fetchMembers();
    }
  }, [activeTab, fetchMembers]);

  // ── Billing Actions ────────────────────────────────────────────────────────
  const getActiveTier = () => {
    if (seats <= 5) return rateCards[0] || { annual: 61.99, quarterly: 69.99, monthly: 79.99, tier: '1-5' };
    if (seats <= 30) return rateCards[1] || { annual: 45.99, quarterly: 52.99, monthly: 59.99, tier: '6-30' };
    return rateCards[2] || { annual: 30.99, quarterly: 34.99, monthly: 39.99, tier: '30+' };
  };

  const activeTier = getActiveTier();
  const currentPrice = activeTier ? activeTier[interval] : 79.99;

  const handleStartTrial = async () => {
    setTrialLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/start-trial', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ seats, interval }),
      });
      if (res.ok) {
        setTrialActive(true);
        setTrialDaysLeft(4);
        toast.success('Your 4-day free trial has been activated!');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Could not start trial');
      }
    } catch (err) {
      toast.error('Network error starting trial');
    } finally {
      setTrialLoading(false);
    }
  };

  const handleUpdateSeats = async (newSeats) => {
    if (newSeats < 1) return;
    setSeats(newSeats);
    try {
      const token = localStorage.getItem('token');
      await fetch('/api/v1/outreach/billing/update-seats', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ seats: newSeats }),
      });
    } catch (err) {
      console.error('Failed to update seats:', err);
    }
  };

  const handleSaveBillingEmail = async (e) => {
    e.preventDefault();
    if (!newBillingEmail || !newBillingEmail.includes('@')) {
      toast.error('Please enter a valid billing email address');
      return;
    }
    setSavingBillingEmail(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/billing-email', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ billing_email: newBillingEmail.trim() }),
      });
      if (res.ok) {
        setBillingEmail(newBillingEmail.trim());
        setBillingModalOpen(false);
        toast.success('Billing receipt email updated');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to update billing email');
      }
    } catch (_) {
      toast.error('Network error updating billing email');
    } finally {
      setSavingBillingEmail(false);
    }
  };

  const handleCancelSubscription = async () => {
    if (!window.confirm('Are you sure you want to cancel your outreach subscription? All assigned residential proxies will be released immediately.')) {
      return;
    }
    setCancelingSubscription(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/cancel', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setTrialActive(false);
        if (data.failed_proxy_releases) toast.error(data.message || 'Subscription canceled, but proxy cleanup needs support.');
        else toast.success(data.message || 'Subscription canceled and proxies released.');
        fetchBilling();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Could not cancel subscription');
      }
    } catch (_) {
      toast.error('Network error canceling subscription');
    } finally {
      setCancelingSubscription(false);
    }
  };

  // ── Member Actions ─────────────────────────────────────────────────────────
  const handleSendInvite = async (e) => {
    e.preventDefault();
    if (!inviteEmail || !inviteEmail.includes('@')) {
      toast.error('Please provide a valid teammate email');
      return;
    }
    setSendingInvite(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/workspace/members/invite', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      });
      if (res.ok) {
        toast.success(`Invitation sent to ${inviteEmail}`);
        setInviteEmail('');
        setInviteModalOpen(false);
        fetchMembers();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to send invite');
      }
    } catch (_) {
      toast.error('Network error sending invite');
    } finally {
      setSendingInvite(false);
    }
  };

  const handleRemoveMember = async (memberId, memberName) => {
    if (!window.confirm(`Remove ${memberName || 'this member'} from the workspace?`)) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/workspace/members/${memberId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Member removed from workspace');
        fetchMembers();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to remove member');
      }
    } catch (_) {
      toast.error('Network error removing member');
    }
  };

  const handleRevokeInvite = async (inviteId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/workspace/invites/${inviteId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Invite revoked');
        fetchMembers();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to revoke invite');
      }
    } catch (_) {
      toast.error('Network error revoking invite');
    }
  };

  const copyToClipboard = (text, label = 'Copied!') => {
    navigator.clipboard.writeText(text);
    toast.success(label);
  };

  // ── Navigation Tabs (Import from V1 permanently removed) ───────────────────
  const tabs = [
    { id: 'accounts', label: 'Accounts' },
    { id: 'members', label: 'Members' },
    { id: 'billing', label: 'Billing' },
    { id: 'help', label: 'Help & Resources' },
  ];

  const faqs = [
    {
      q: 'Do daily limits make automated outreach compliant?',
      a: 'No. Rate limits reduce request volume but do not authorize automated outreach or remove account-restriction risk. Review LinkedIn’s current policies and get appropriate product/legal advice before using session-based features.',
    },
    {
      q: 'Does a residential proxy prevent account restrictions?',
      a: 'No. A proxy is part of the session connection infrastructure. It does not make non-public API access authorized or prevent LinkedIn from restricting an account.',
    },
    {
      q: 'How does the 4-day free trial work?',
      a: 'Your trial gives you full access to all Outreach features: sequences, automated actions, voice cloning, and unified inbox. Adding a payment card charges nothing until your 4-day trial period finishes. You can cancel at any time in Billing.',
    },
    {
      q: 'How are personalized AI voice notes generated?',
      a: 'In the Voice studio, you record a single 30-second audio script. Our ElevenLabs engine clones your unique voice and tone. When a sequence executes, dynamic tokens like {{first_name}} and {{company_name}} are synthesized into individual voice message files and sent to prospects.',
    },
    {
      q: 'What happens when a prospect replies to my outreach message?',
      a: 'The sequence automatically detects the response, stops all subsequent follow-up steps for that lead, marks the lead as "Replied", and routes the message directly into your Unified Outreach Inbox for real-time human response.',
    },
  ];

  return (
    <div className="min-h-screen bg-neutral-50/40 p-6 md:p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Settings</h1>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Left Vertical Sub-Nav */}
          <div className="md:col-span-3 space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-indigo-50 text-indigo-700 font-semibold shadow-xs'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100/70'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right Main Pane */}
          <div className="md:col-span-9 space-y-6">
            {/* ── TAB 1: ACCOUNTS ────────────────────────────────────────── */}
            {activeTab === 'accounts' && <OutreachAccounts />}

            {/* ── TAB 2: MEMBERS ─────────────────────────────────────────── */}
            {activeTab === 'members' && (
              <div className="space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Workspace Members</h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Collaborate on outreach campaigns, share unified inboxes, and manage sender accounts.
                    </p>
                  </div>
                  <button
                    onClick={() => setInviteModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-colors"
                  >
                    <UserPlus className="w-3.5 h-3.5" /> Invite Teammate
                  </button>
                </div>

                {/* Members List Table */}
                <div className="bg-white rounded-2xl border border-gray-200 shadow-xs overflow-hidden">
                  <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                    <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">
                      Active Members ({members.length})
                    </span>
                    <span className="text-[11px] text-gray-400 font-medium">
                      Your role: <strong className="text-gray-700 capitalize">{currentUserRole}</strong>
                    </span>
                  </div>

                  {loadingMembers ? (
                    <div className="p-12 flex justify-center text-gray-400">
                      <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
                    </div>
                  ) : members.length === 0 ? (
                    <div className="p-8 text-center text-xs text-gray-500">
                      No members found in this workspace.
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-100">
                      {members.map((member) => (
                        <div key={member.user_id} className="px-6 py-3.5 flex items-center justify-between gap-4 hover:bg-gray-50/50 transition-colors">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-xs shrink-0">
                              {member.avatar_url ? (
                                <img src={member.avatar_url} alt="" className="w-9 h-9 rounded-full object-cover" />
                              ) : (
                                (member.display_name || member.email || 'U').charAt(0).toUpperCase()
                              )}
                            </div>
                            <div className="min-w-0">
                              <h4 className="text-xs font-bold text-gray-900 truncate">
                                {member.display_name || 'Team Member'}
                              </h4>
                              <p className="text-[11px] text-gray-400 truncate">{member.email}</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-3">
                            <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-gray-100 text-gray-700">
                              {member.role || 'Member'}
                            </span>
                            {permissions.can_remove_member && member.role !== 'owner' && (
                              <button
                                onClick={() => handleRemoveMember(member.user_id, member.display_name)}
                                className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                title="Remove member"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Pending Invites Table */}
                {pendingInvites.length > 0 && (
                  <div className="bg-white rounded-2xl border border-gray-200 shadow-xs overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-100">
                      <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">
                        Pending Invites ({pendingInvites.length})
                      </span>
                    </div>
                    <div className="divide-y divide-gray-100">
                      {pendingInvites.map((invite) => (
                        <div key={invite.invite_id} className="px-6 py-3.5 flex items-center justify-between gap-4">
                          <div>
                            <p className="text-xs font-semibold text-gray-800">{invite.email}</p>
                            <span className="text-[10px] text-gray-400">
                              Role: <strong className="capitalize">{invite.role}</strong> • Status: {invite.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            {invite.invite_url && (
                              <button
                                onClick={() => copyToClipboard(invite.invite_url, 'Invite link copied!')}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-gray-200 text-[11px] text-gray-600 hover:bg-gray-50 transition-colors"
                              >
                                <Copy className="w-3 h-3" /> Copy Link
                              </button>
                            )}
                            <button
                              onClick={() => handleRevokeInvite(invite.invite_id)}
                              className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                              title="Revoke invite"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── TAB 3: BILLING ─────────────────────────────────────────── */}
            {activeTab === 'billing' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-base font-bold text-gray-900">Billing & Subscriptions</h2>
                  <p className="text-xs text-gray-500 mt-0.5 max-w-2xl leading-relaxed">
                    Each connected sender needs a dedicated static residential proxy from your configured provider. Proxy purchases are billed separately, including when unused.
                  </p>
                </div>

                {/* Interval Toggle */}
                <div className="flex items-center gap-1.5 bg-gray-100 p-1 rounded-xl w-fit text-xs font-medium text-gray-600">
                  <button
                    onClick={() => setInterval('annual')}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      interval === 'annual' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    <span>Annual</span>
                    <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">
                      save 23%
                    </span>
                  </button>

                  <button
                    onClick={() => setInterval('quarterly')}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      interval === 'quarterly' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    <span>Quarterly</span>
                    <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">
                      save 13%
                    </span>
                  </button>

                  <button
                    onClick={() => setInterval('monthly')}
                    className={`px-3 py-1.5 rounded-lg transition-all ${
                      interval === 'monthly' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    Monthly
                  </button>
                </div>

                {/* Primary Plan Card */}
                <div className="bg-indigo-600 text-white rounded-2xl p-7 shadow-md space-y-6">
                  <div>
                    <span className="text-[10px] font-bold tracking-widest text-indigo-200 uppercase">
                      YOUR OUTREACH PLAN
                    </span>
                    <h3 className="text-2xl font-extrabold mt-1">
                      {trialActive ? `4-Day Trial (${trialDaysLeft} days remaining)` : 'Standard Outbound Tier'}
                    </h3>
                    <p className="text-xs text-indigo-100 mt-1">
                      ${currentPrice} per account every 4 weeks. Proxy provider charges are separate and must be managed with that provider.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <p className="text-xs font-semibold">How many accounts / seats?</p>
                    <p className="text-[11px] text-indigo-200">
                      Each connected LinkedIn sender needs its own dedicated proxy, purchased separately.
                    </p>

                    <div className="flex items-center gap-4 pt-1">
                      <div className="flex items-center bg-indigo-700/80 rounded-lg p-1 border border-indigo-500/50">
                        <button
                          onClick={() => handleUpdateSeats(Math.max(1, seats - 1))}
                          className="w-7 h-7 flex items-center justify-center rounded hover:bg-indigo-600 transition-colors text-white"
                        >
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="w-10 text-center text-sm font-bold">{seats}</span>
                        <button
                          onClick={() => handleUpdateSeats(seats + 1)}
                          className="w-7 h-7 flex items-center justify-center rounded hover:bg-indigo-600 transition-colors text-white"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <span className="text-xs font-medium text-indigo-100">
                        ${currentPrice} / account / 4 weeks • {activeTier.label}
                      </span>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-indigo-500/40 space-y-3">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleStartTrial}
                        disabled={trialLoading || trialActive}
                        className="px-5 py-2.5 bg-white text-indigo-700 hover:bg-indigo-50 text-xs font-bold rounded-xl shadow-xs transition-colors disabled:opacity-75"
                      >
                        {trialActive
                          ? `Trial Active (${trialDaysLeft} days left)`
                          : `Start 4-day trial - ${interval.charAt(0).toUpperCase() + interval.slice(1)}`}
                      </button>
                      <button
                        onClick={() => setPaymentModalOpen(true)}
                        className="px-5 py-2.5 bg-indigo-500/30 hover:bg-indigo-500/50 border border-indigo-400/40 text-white text-xs font-semibold rounded-xl transition-colors inline-flex items-center gap-1.5"
                      >
                        <CreditCard className="w-3.5 h-3.5" /> Payment Method
                      </button>
                    </div>
                    <p className="text-[11px] text-indigo-200">
                      Adding a payment method charges nothing during your trial period.
                    </p>
                  </div>
                </div>

                {/* 2-Column Feature & Post-Trial Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-4">
                    <h3 className="font-bold text-gray-900 text-sm">Everything included</h3>
                    <ul className="space-y-2.5 text-xs text-gray-600">
                      {(featuresIncluded.length > 0
                        ? featuresIncluded
                        : [
                            'Unlimited campaigns, contacts, and messages',
                            'Every team member, free',
                            'Voice cloning studio',
                            'Supports one separately purchased dedicated proxy per sender',
                            'Unified inbox across every account',
                            'Templates, analytics, and DAG sequences',
                          ]
                      ).map((feat, idx) => (
                        <li key={idx} className="flex items-start gap-2.5">
                          <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-3">
                    <h3 className="font-bold text-gray-900 text-sm">Your plan after the trial</h3>
                    <div>
                      <span className="text-3xl font-extrabold text-gray-900">${currentPrice}</span>
                      <span className="text-xs text-gray-500 ml-1">per account/4 weeks</span>
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed">
                      {interval.charAt(0).toUpperCase() + interval.slice(1)} billing, total ${(currentPrice * seats).toFixed(2)} every 4 weeks for {seats} {seats === 1 ? 'seat' : 'seats'}.
                    </p>
                    <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                      Disconnecting a sender clears its proxy assignment in our app; cancel or resize the provider plan separately to change proxy charges.
                    </p>
                  </div>
                </div>

                {/* Rate Card Table */}
                <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
                  <h3 className="font-bold text-gray-900 text-sm">Volume Rate Card</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="border-b border-gray-100 text-gray-400 font-medium">
                          <th className="pb-3 font-medium">Account Tier</th>
                          <th className="pb-3 font-medium">Annual</th>
                          <th className="pb-3 font-medium">Quarterly</th>
                          <th className="pb-3 font-medium">Monthly</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {rateCards.map((rc) => {
                          const isCurrentTier = activeTier.tier === rc.tier;
                          return (
                            <tr
                              key={rc.tier}
                              className={`transition-colors ${
                                isCurrentTier ? 'bg-indigo-50/70 font-semibold' : 'hover:bg-gray-50/60'
                              }`}
                            >
                              <td className="py-3 px-2 flex items-center gap-2">
                                <span className={isCurrentTier ? 'text-indigo-900' : 'text-gray-900'}>
                                  {rc.label}
                                </span>
                                {isCurrentTier && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700">
                                    your plan
                                  </span>
                                )}
                              </td>
                              <td className="py-3 px-2 text-gray-700">${rc.annual.toFixed(2)}</td>
                              <td className="py-3 px-2 text-gray-700">${rc.quarterly.toFixed(2)}</td>
                              <td className="py-3 px-2 text-gray-700">${rc.monthly.toFixed(2)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Billing Email & Subscription Settings */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 flex items-center justify-between">
                    <div>
                      <h3 className="font-bold text-gray-900 text-sm">Billing Email</h3>
                      <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">
                        {billingEmail || 'No receipt email configured'}
                      </p>
                    </div>
                    <button
                      onClick={() => setBillingModalOpen(true)}
                      className="px-4 py-2 border border-gray-200 text-gray-700 hover:bg-gray-50 rounded-lg text-xs font-medium transition-colors"
                    >
                      Update Email
                    </button>
                  </div>

                  <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 flex items-center justify-between">
                    <div>
                      <h3 className="font-bold text-gray-900 text-sm">Cancel Subscription</h3>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Pauses senders and clears local proxy assignments. Provider subscriptions must be managed separately.
                      </p>
                    </div>
                    <button
                      onClick={handleCancelSubscription}
                      disabled={cancelingSubscription}
                      className="px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {cancelingSubscription ? 'Canceling...' : 'Cancel Tier'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* ── TAB 4: HELP & RESOURCES ────────────────────────────────── */}
            {activeTab === 'help' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-base font-bold text-gray-900">Help & Outreach Safety Guidelines</h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Understand the limitations and risks of session-based outreach before using it.
                  </p>
                </div>

                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
                  <strong>Platform policy notice:</strong> Session-based outreach uses non-public LinkedIn interfaces. Automated access, likes, comments, and messages may violate LinkedIn’s User Agreement and can result in account restrictions. Human review, rate limits, and proxies do not remove that risk.
                </div>

                {/* Safety Cards Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-white rounded-2xl border border-gray-200/80 p-5 shadow-xs space-y-2">
                    <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <Shield className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-gray-900">Volume Controls</h3>
                    <p className="text-[11px] text-gray-500 leading-relaxed">
                      Daily limits cap activity within the app. They are operational controls, not a guarantee of account safety or platform permission.
                    </p>
                  </div>

                  <div className="bg-white rounded-2xl border border-gray-200/80 p-5 shadow-xs space-y-2">
                    <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                      <Globe className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-gray-900">Residential Proxies</h3>
                    <p className="text-[11px] text-gray-500 leading-relaxed">
                      Session connections may route through a dedicated proxy. Its availability and location depend on the provider; it does not prevent platform enforcement.
                    </p>
                  </div>

                  <div className="bg-white rounded-2xl border border-gray-200/80 p-5 shadow-xs space-y-2">
                    <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
                      <Sliders className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-gray-900">Manual Review</h3>
                    <p className="text-[11px] text-gray-500 leading-relaxed">
                      Review every suggested comment for accuracy and tone. Drafts in Engage are not published automatically.
                    </p>
                  </div>
                </div>

                {/* FAQ Accordion */}
                <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-3">
                  <h3 className="text-sm font-bold text-gray-900 mb-2">Frequently Asked Questions</h3>
                  <div className="divide-y divide-gray-100">
                    {faqs.map((faq, idx) => (
                      <div key={idx} className="py-3">
                        <button
                          onClick={() => setExpandedFaq(expandedFaq === idx ? null : idx)}
                          className="w-full flex items-center justify-between text-left text-xs font-semibold text-gray-800 hover:text-indigo-600 transition-colors"
                        >
                          <span>{faq.q}</span>
                          {expandedFaq === idx ? (
                            <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                          )}
                        </button>
                        {expandedFaq === idx && (
                          <p className="mt-2 text-[11px] text-gray-500 leading-relaxed bg-gray-50/70 p-3 rounded-xl border border-gray-100">
                            {faq.a}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Support Banner */}
                <div className="bg-indigo-50/70 border border-indigo-100 rounded-2xl p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-indigo-900">Need personalized outbound assistance?</h4>
                    <p className="text-[11px] text-indigo-700 mt-0.5">
                      Our support specialists can help review your campaign DAG sequences, copy, and targeting.
                    </p>
                  </div>
                  <a
                    href="mailto:support@unravler.com?subject=LinkedIn%20Outreach%20Support%20Request"
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition-colors shrink-0"
                  >
                    <Mail className="w-3.5 h-3.5" /> Contact Support
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── MODAL: INVITE TEAMMATE ─────────────────────────────────────────── */}
      {inviteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-900">Invite Workspace Teammate</h3>
              <button
                onClick={() => setInviteModalOpen(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSendInvite} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Teammate Email Address *
                </label>
                <input
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com"
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Role & Permissions
                </label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs bg-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="editor">Editor — Can edit sequences, leads & reply in inbox</option>
                  <option value="admin">Admin — Full workspace control, billing & account setup</option>
                  <option value="client">Client — View inbox & analytics only</option>
                  <option value="viewer">Viewer — Read-only access</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setInviteModalOpen(false)}
                  className="px-4 py-2 border border-gray-200 text-gray-600 rounded-xl text-xs font-semibold hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={sendingInvite}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {sendingInvite ? 'Sending...' : 'Send Invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: BILLING EMAIL ───────────────────────────────────────────── */}
      {billingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-900">Update Billing Email</h3>
              <button
                onClick={() => setBillingModalOpen(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-gray-500">
              Invoices, receipts, and subscription notices are delivered to this address.
            </p>

            <form onSubmit={handleSaveBillingEmail} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Recipient Email Address
                </label>
                <input
                  type="email"
                  required
                  value={newBillingEmail}
                  onChange={(e) => setNewBillingEmail(e.target.value)}
                  placeholder="billing@company.com"
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setBillingModalOpen(false)}
                  className="px-4 py-2 border border-gray-200 text-gray-600 rounded-xl text-xs font-semibold hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingBillingEmail}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {savingBillingEmail ? 'Saving...' : 'Save Email'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: PAYMENT METHOD ──────────────────────────────────────────── */}
      {paymentModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-900">Payment Details</h3>
              <button
                onClick={() => setPaymentModalOpen(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-xl border border-gray-200 bg-gray-50/50 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-600">Payment Gateway</span>
                <span className="text-xs font-bold text-gray-900">Stripe Secure</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-600">Trial Period</span>
                <span className="text-xs font-bold text-emerald-600">4 Days Free</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-600">Billed Amount Today</span>
                <span className="text-xs font-bold text-gray-900">$0.00</span>
              </div>
            </div>

            <p className="text-[11px] text-gray-400 leading-relaxed">
              When starting your trial or subscription, payment authorization is handled via Stripe's encrypted payment vault. No card numbers touch our servers.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setPaymentModalOpen(false)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
