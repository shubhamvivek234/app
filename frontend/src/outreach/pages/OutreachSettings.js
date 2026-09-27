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
  const [seats, setSeats] = useState(1);
  const [senderCountry, setSenderCountry] = useState('');
  const [requestingAccess, setRequestingAccess] = useState(false);
  const [accessRequest, setAccessRequest] = useState(null);
  const [entitlement, setEntitlement] = useState(null);
  const [accessActive, setAccessActive] = useState(false);
  const [billingEmail, setBillingEmail] = useState('');
  const [billingModalOpen, setBillingModalOpen] = useState(false);
  const [newBillingEmail, setNewBillingEmail] = useState('');
  const [savingBillingEmail, setSavingBillingEmail] = useState(false);
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
        setEntitlement(data.subscription || null);
        setAccessActive(Boolean(data.access_active));
        setAccessRequest(data.access_request || null);
        if (data.subscription?.seats) setSeats(data.subscription.seats);
        if (data.access_request?.country_code) setSenderCountry(data.access_request.country_code);
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
  const handleRequestAccess = async () => {
    if (!/^[A-Z]{2}$/.test(senderCountry)) {
      toast.error('Enter the two-letter country code for your sender');
      return;
    }
    setRequestingAccess(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/request-access', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ seats, country_code: senderCountry }),
      });
      if (res.ok) {
        setAccessRequest({ seats, country_code: senderCountry, status: 'pending_quote' });
        toast.success('Request received. We will confirm availability and price before payment.');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Could not request managed access');
      }
    } catch (err) {
      toast.error('Network error requesting access');
    } finally {
      setRequestingAccess(false);
    }
  };

  const handleUpdateSeats = async (newSeats) => {
    if (newSeats < 1 || newSeats > 5) return;
    setSeats(newSeats);
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
    if (!window.confirm('Schedule cancellation at the end of your paid period? Access continues until then. Sender IPs remain reserved through their already-paid provider terms.')) {
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
        toast.success(data.message || 'Cancellation scheduled for the end of the paid period.');
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
      q: 'How does paid pilot access work?',
      a: 'Request your sender count and country. We check IP availability and send a quote before payment. Only an independently verified paid invoice activates access; no trial or in-app card checkout is offered. Cancellation takes effect at your paid-period end.',
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
                  <h2 className="text-base font-bold text-gray-900">Outreach billing</h2>
                  <p className="mt-1 max-w-2xl text-xs leading-relaxed text-gray-600">
                    Invite-only paid pilot. No free trial or in-app card collection is active. Each sender needs its own dedicated IP; availability and any country-specific quote are confirmed before payment.
                  </p>
                </div>

                <div className="rounded-2xl bg-indigo-600 p-7 text-white shadow-md">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-200">Founding pilot price</p>
                  <h3 className="mt-2 text-3xl font-extrabold">$59 <span className="text-base font-medium">USD / sender / month</span></h3>
                  <p className="mt-2 text-xs leading-relaxed text-indigo-100">
                    One country-matched dedicated IP is managed per paid sender seat where available. Taxes and any exceptional regional costs are quoted before you pay. No annual, quarterly, or unlimited-usage promise is offered.
                  </p>
                  <div className="mt-5 border-t border-indigo-400/40 pt-4 text-xs">
                    <p className="font-semibold">
                      {accessActive ? 'Paid access active' : accessRequest ? 'Access request pending review' : 'No paid sender access yet'}
                    </p>
                    {entitlement?.paid_through && <p className="mt-1 text-indigo-100">Paid through {new Date(entitlement.paid_through).toLocaleDateString()} · {entitlement.seats} {entitlement.seats === 1 ? 'sender seat' : 'sender seats'}</p>}
                    {entitlement?.cancel_at_period_end && <p className="mt-1 text-amber-100">Cancellation scheduled for the paid-period end.</p>}
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-xs">
                  <h3 className="text-sm font-bold text-gray-900">Request or change managed access</h3>
                  <p className="mt-1 text-xs leading-relaxed text-gray-600">
                    Choose the number of sender accounts and their shared proxy country. This pilot supports one country per workspace; contact support for a mixed-country team. We check IP availability, confirm the final quote, and send payment instructions. Access is activated only after payment is independently verified. If a country is unavailable, you are not charged.
                  </p>
                  <div className="mt-5 flex flex-wrap items-end gap-4">
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-gray-700">Sender seats (1–5)</label>
                      <div className="flex items-center rounded-lg border border-gray-200">
                        <button type="button" onClick={() => handleUpdateSeats(seats - 1)} disabled={seats <= 1} aria-label="Remove sender seat" className="p-2 disabled:opacity-40"><Minus className="h-4 w-4" /></button>
                        <span className="w-9 text-center text-sm font-semibold">{seats}</span>
                        <button type="button" onClick={() => handleUpdateSeats(seats + 1)} disabled={seats >= 5} aria-label="Add sender seat" className="p-2 disabled:opacity-40"><Plus className="h-4 w-4" /></button>
                      </div>
                    </div>
                    <div>
                      <label htmlFor="pilot-country" className="mb-1 block text-xs font-semibold text-gray-700">Sender proxy country</label>
                      <input id="pilot-country" value={senderCountry} onChange={(event) => setSenderCountry(event.target.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 2))} maxLength={2} placeholder="e.g. IN" className="w-28 rounded-lg border border-gray-200 px-3 py-2 text-sm uppercase" />
                    </div>
                    <button type="button" onClick={handleRequestAccess} disabled={requestingAccess} className="rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50">
                      {requestingAccess ? 'Sending request…' : accessActive ? 'Request a seat change' : 'Request managed access'}
                    </button>
                  </div>
                  <p className="mt-3 text-xs text-gray-500">Estimate: ${(59 * seats).toFixed(2)} USD/month before taxes for {seats} {seats === 1 ? 'seat' : 'seats'}. This request does not charge you or activate a sender.</p>
                  {accessRequest && <p className="mt-2 text-xs text-indigo-700">Latest request: {accessRequest.seats} {accessRequest.seats === 1 ? 'seat' : 'seats'} in {accessRequest.country_code} · awaiting availability and quote.</p>}
                </div>

                <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                  <div className="flex items-center justify-between rounded-2xl border border-gray-200 bg-white p-6 shadow-xs">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Billing email</h3>
                      <p className="mt-1 max-w-xs truncate text-xs text-gray-500">{billingEmail || 'No billing email configured'}</p>
                    </div>
                    <button onClick={() => setBillingModalOpen(true)} className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium">Update</button>
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-gray-200 bg-white p-6 shadow-xs">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Cancel at period end</h3>
                      <p className="mt-1 max-w-xs text-xs text-gray-500">Service continues until paid-through. Your IP is not reassigned to another customer during its provider term.</p>
                    </div>
                    <button onClick={handleCancelSubscription} disabled={!accessActive || entitlement?.cancel_at_period_end || cancelingSubscription} className="rounded-lg border border-red-200 px-4 py-2 text-xs font-medium text-red-600 disabled:opacity-40">
                      {cancelingSubscription ? 'Scheduling…' : 'Cancel'}
                    </button>
                  </div>
                </div>
                <p className="text-xs leading-relaxed text-gray-500">Session-based automated outreach uses unofficial LinkedIn interfaces and carries account-restriction risk. Paid access and dedicated IPs do not make it authorized by LinkedIn.</p>
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

    </div>
  );
}
