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
  LogOut,
} from 'lucide-react';
import { toast } from 'sonner';
import OutreachAccounts from './OutreachAccounts';
import OutreachMailboxes from './OutreachMailboxes';
import OutreachActionReview from './OutreachActionReview';
import OutreachContentReview from './OutreachContentReview';
import OutreachIntegrations from './OutreachIntegrations';
import OutreachSubscriptionMonitor from './OutreachSubscriptionMonitor';
import LeadTagManager from '../components/LeadTagManager';

export default function OutreachSettings({ initialTab = 'accounts', onSignOut }) {
  const [activeTab, setActiveTab] = useState(() => (
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('mailbox_job_id')
      ? 'mailboxes' : initialTab
  ));

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
  const [billingLoading, setBillingLoading] = useState(true);
  const [billingLoaded, setBillingLoaded] = useState(false);
  const [billingError, setBillingError] = useState('');

  // ── Members State ──────────────────────────────────────────────────────────
  const [members, setMembers] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [currentUserRole, setCurrentUserRole] = useState('viewer');
  const [permissions, setPermissions] = useState({});
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [membersError, setMembersError] = useState('');
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('editor');
  const [sendingInvite, setSendingInvite] = useState(false);
  const [showRoleMatrix, setShowRoleMatrix] = useState(false);
  const [updatingRoleFor, setUpdatingRoleFor] = useState(null);

  // ── Help & Contact State ───────────────────────────────────────────────────
  const [expandedFaq, setExpandedFaq] = useState(null);
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactMessage, setContactMessage] = useState('');
  const [contactAttachmentName, setContactAttachmentName] = useState('');
  const [sendingContact, setSendingContact] = useState(false);
  const [contactResult, setContactResult] = useState(null);

  const handleSubmitContactForm = async (e) => {
    e.preventDefault();
    if (!contactName.trim() || !contactEmail.trim() || contactMessage.trim().length < 10) {
      toast.error('Please enter your name, email, and a message of at least 10 characters.');
      return;
    }
    setSendingContact(true);
    try {
      const res = await fetch('/api/v1/support/public-contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: contactName.trim(),
          email: contactEmail.trim(),
          message: contactMessage.trim(),
          attachment_name: contactAttachmentName || null,
          acknowledged_terms: true,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Could not send message right now.');
      }
      setContactResult(data);
      toast.success('Thank you! Your message has been sent.');
    } catch (err) {
      toast.error(err.message || 'Could not send message right now. Please try again.');
    } finally {
      setSendingContact(false);
    }
  };

  // ── Fetch Billing Data ─────────────────────────────────────────────────────
  const fetchBilling = useCallback(async () => {
    setBillingLoading(true); setBillingError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/plans', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error('Billing status is unavailable. Try again.');
      if (res.ok) {
        const data = await res.json();
        if (typeof data.access_active !== 'boolean') throw new Error('Billing status is unavailable. Try again.');
        setEntitlement(data.subscription || null);
        setAccessActive(Boolean(data.access_active));
        setAccessRequest(data.access_request || null);
        setBillingLoaded(true);
        if (data.subscription?.seats) setSeats(data.subscription.seats);
        if (data.access_request?.country_code) setSenderCountry(data.access_request.country_code);
        if (data.billing_email) {
          setBillingEmail(data.billing_email);
          setNewBillingEmail(data.billing_email);
        }
      }
    } catch (err) {
      setBillingError('Billing status is unavailable. Your access has not been changed.');
    } finally {
      setBillingLoading(false);
    }
  }, []);

  // ── Fetch Members Data ─────────────────────────────────────────────────────
  const fetchMembers = useCallback(async () => {
    setLoadingMembers(true);
    setMembersError('');
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
      } else {
        const err = await res.json().catch(() => ({}));
        setMembersError(err.detail || 'Could not load workspace members.');
      }
    } catch (err) {
      setMembersError('Could not load workspace members.');
    } finally {
      setLoadingMembers(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('mailbox_job_id')) {
      setActiveTab('mailboxes');
    } else if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

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
    const rawEmails = (inviteEmail || '')
      .split(/[,;\n\s]+/)
      .map((s) => s.trim())
      .filter((s) => s && s.includes('@'));
    if (rawEmails.length === 0) {
      toast.error('Please provide at least one valid teammate email');
      return;
    }
    setSendingInvite(true);
    try {
      const token = localStorage.getItem('token');
      let successCount = 0;
      let lastError = '';
      for (const emailAddr of rawEmails) {
        const res = await fetch('/api/v1/workspace/members/invite', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({ email: emailAddr, role: inviteRole }),
        });
        if (res.ok) {
          successCount += 1;
        } else {
          const err = await res.json().catch(() => ({}));
          lastError = err.detail || `Failed to invite ${emailAddr}`;
        }
      }
      if (successCount > 0) {
        toast.success(
          successCount === 1
            ? `Invitation sent to ${rawEmails[0]}`
            : `Sent ${successCount} teammate invitations`
        );
        setInviteEmail('');
        setInviteModalOpen(false);
        fetchMembers();
      } else {
        toast.error(lastError || 'Failed to send invite');
      }
    } catch (_) {
      toast.error('Network error sending invite');
    } finally {
      setSendingInvite(false);
    }
  };

  const handleUpdateMemberRole = async (memberId, newRole) => {
    if (!memberId || !newRole) return;
    setUpdatingRoleFor(memberId);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/workspace/members/${memberId}/role`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ role: newRole }),
      });
      if (res.ok) {
        toast.success('Teammate role updated');
        fetchMembers();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to update member role');
      }
    } catch (_) {
      toast.error('Network error updating member role');
    } finally {
      setUpdatingRoleFor(null);
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

  const handleSignOut = async () => {
    if (typeof onSignOut === 'function') {
      await onSignOut();
      return;
    }
    try {
      localStorage.removeItem('token');
      await fetch('/api/auth/session/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
    } finally {
      window.location.assign('/login');
    }
  };

  // ── Navigation Tabs (Import from V1 permanently removed) ───────────────────
  const tabs = [
    { id: 'accounts', label: 'Accounts' },
    { id: 'mailboxes', label: 'Email mailboxes' },
    { id: 'action-reviews', label: 'Action reviews' },
    { id: 'content-reviews', label: 'Content reviews' },
    { id: 'integrations', label: 'Integrations & Webhooks' },
    { id: 'lead-tags', label: 'Lead tags' },
    { id: 'members', label: 'Members' },
    { id: 'billing', label: 'Billing' },
    { id: 'subscription-monitor', label: 'Subscriptions & Usage' },
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
            <div className="pt-2 mt-2 border-t border-gray-200/80">
              <button
                type="button"
                onClick={handleSignOut}
                data-testid="settings-signout-button"
                className="w-full text-left px-3.5 py-2.5 rounded-xl text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50/80 transition-all flex items-center gap-2"
              >
                <LogOut className="w-3.5 h-3.5 shrink-0" />
                Sign out
              </button>
            </div>
          </div>

          {/* Right Main Pane */}
          <div className="md:col-span-9 space-y-6">
            {/* ── TAB 1: ACCOUNTS ────────────────────────────────────────── */}
            {activeTab === 'accounts' && <OutreachAccounts />}
            {activeTab === 'mailboxes' && <OutreachMailboxes />}
            {activeTab === 'action-reviews' && <OutreachActionReview />}
            {activeTab === 'content-reviews' && <OutreachContentReview />}
            {activeTab === 'integrations' && <OutreachIntegrations />}
            {activeTab === 'lead-tags' && <LeadTagManager />}
            {activeTab === 'subscription-monitor' && <OutreachSubscriptionMonitor />}

            {/* ── TAB 2: MEMBERS ─────────────────────────────────────────── */}
            {activeTab === 'members' && (
              <div className="space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Workspace Members &amp; Team Roles</h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Collaborate on outreach campaigns, share sequence templates, and prevent duplicate lead outreach across teammates.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setShowRoleMatrix((v) => !v)}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 rounded-xl text-xs font-semibold shadow-xs transition-colors"
                    >
                      <HelpCircle className="w-3.5 h-3.5 text-indigo-600" />
                      {showRoleMatrix ? 'Hide Role Comparison' : 'See Key Differences Between Roles'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setInviteModalOpen(true)}
                      disabled={permissions.can_invite === false}
                      title={permissions.can_invite === false ? 'Only workspace owners and admins can invite teammates' : undefined}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
                    >
                      <UserPlus className="w-3.5 h-3.5" /> Invite Teammates
                    </button>
                  </div>
                </div>

                {/* Role & Permissions Comparison Matrix (Dripify Video #17 & #18) */}
                {showRoleMatrix && (
                  <div className="bg-indigo-50/50 rounded-2xl border border-indigo-100 p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-xs font-bold text-indigo-950 uppercase tracking-wider">
                          Roles &amp; Permissions Matrix
                        </h3>
                        <p className="text-[11px] text-indigo-700 mt-0.5">
                          Choose the right role for each teammate. Roles can be updated anytime from the Active Members list below.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowRoleMatrix(false)}
                        className="p-1 text-indigo-400 hover:text-indigo-700 rounded-lg"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                      <div className="bg-white rounded-xl border border-indigo-100 p-4 space-y-2 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-gray-900">User (Editor)</span>
                          <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-[10px] font-bold uppercase">Standard</span>
                        </div>
                        <ul className="space-y-1 text-[11px] text-gray-600">
                          <li>• Run campaigns &amp; manage own leads/inbox</li>
                          <li>• Use shared team sequence templates</li>
                          <li>• Automatic cross-team lead deduplication</li>
                          <li className="text-gray-400">✕ Cannot invite/remove teammates or change roles</li>
                        </ul>
                      </div>
                      <div className="bg-white rounded-xl border border-indigo-200 p-4 space-y-2 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-indigo-900">Manager (Admin)</span>
                          <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[10px] font-bold uppercase">Team Lead</span>
                        </div>
                        <ul className="space-y-1 text-[11px] text-gray-600">
                          <li>• View all team members &amp; LinkedIn stats</li>
                          <li>• Invite or remove members (except Owners) &amp; assign roles</li>
                          <li>• Create &amp; manage shared team sequence templates</li>
                          <li>• Inspect teammates&apos; campaigns, queues &amp; inbox</li>
                        </ul>
                      </div>
                      <div className="bg-white rounded-xl border border-emerald-200 p-4 space-y-2 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-emerald-900">Owner</span>
                          <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold uppercase">Full Control</span>
                        </div>
                        <ul className="space-y-1 text-[11px] text-gray-600">
                          <li>• All Manager &amp; User permissions</li>
                          <li>• Full workspace, billing &amp; seat administration</li>
                          <li>• Manage all team members, roles &amp; workspace settings</li>
                        </ul>
                      </div>
                    </div>
                  </div>
                )}

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
                  ) : membersError ? (
                    <div role="alert" className="p-8 text-center text-xs text-red-700 space-y-2">
                      <p>{membersError}</p>
                      <button
                        type="button"
                        onClick={fetchMembers}
                        className="px-3 py-1.5 rounded-lg border border-red-200 bg-red-50 text-red-700 font-semibold hover:bg-red-100"
                      >
                        Retry loading members
                      </button>
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
                            {permissions.can_update_member_role && member.role !== 'owner' ? (
                              <select
                                aria-label={`Change role for ${member.display_name || member.email}`}
                                value={member.role || 'editor'}
                                disabled={updatingRoleFor === member.user_id}
                                onChange={(e) => handleUpdateMemberRole(member.user_id, e.target.value)}
                                className="px-2.5 py-1 rounded-lg border border-gray-200 bg-white text-[11px] font-semibold text-gray-700 focus:outline-none focus:border-indigo-500"
                              >
                                <option value="editor">User (Editor)</option>
                                <option value="admin">Manager (Admin)</option>
                                <option value="client">Client</option>
                                <option value="viewer">Viewer</option>
                              </select>
                            ) : (
                              <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-gray-100 text-gray-700">
                                {member.role === 'admin' ? 'Manager (Admin)' : member.role === 'editor' ? 'User (Editor)' : (member.role || 'Member')}
                              </span>
                            )}
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
                              Role: <strong className="capitalize">{invite.role === 'admin' ? 'Manager (Admin)' : invite.role === 'editor' ? 'User (Editor)' : invite.role}</strong> • Status: {invite.status}
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
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-red-200 text-[11px] font-semibold text-red-600 hover:bg-red-50 transition-colors"
                              title="Recall invite"
                            >
                              <X className="w-3 h-3" /> Recall Invite
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
                      {billingLoading ? 'Checking billing status…' : billingError ? 'Billing status unavailable'
                        : accessActive ? 'Paid access active' : accessRequest ? 'Access request pending review' : 'No paid sender access yet'}
                    </p>
                    {billingError && <div role="alert" className="mt-2">
                      <p>{billingError}</p>
                      {billingLoaded && <p>Last confirmed: {accessActive ? 'paid access active' : accessRequest ? 'request pending review' : 'no active paid access'}.</p>}
                      <button type="button" onClick={fetchBilling} disabled={billingLoading} className="mt-2 underline">Retry billing</button>
                    </div>}
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
                    <button type="button" onClick={handleRequestAccess} disabled={requestingAccess || billingLoading || Boolean(billingError)} className="rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50">
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
                      <p className="mt-1 max-w-xs truncate text-xs text-gray-500">{billingEmail || (billingLoaded ? 'No billing email configured' : 'Billing email unavailable')}</p>
                    </div>
                    <button onClick={() => setBillingModalOpen(true)} className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium">Update</button>
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-gray-200 bg-white p-6 shadow-xs">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Cancel at period end</h3>
                      <p className="mt-1 max-w-xs text-xs text-gray-500">Service continues until paid-through. Your IP is not reassigned to another customer during its provider term.</p>
                    </div>
                    <button onClick={handleCancelSubscription} disabled={billingLoading || Boolean(billingError) || !accessActive || entitlement?.cancel_at_period_end || cancelingSubscription} className="rounded-lg border border-red-200 px-4 py-2 text-xs font-medium text-red-600 disabled:opacity-40">
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

                {/* Campaign Playbooks & Walkthrough Guides (Prosp Parity) */}
                <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Campaign Playbooks &amp; Walkthrough Guides</h3>
                      <p className="text-[11px] text-gray-500 mt-0.5">
                        Step-by-step reference guides for sourcing leads, AI prompt personalization, voice notes, and CRM sync.
                      </p>
                    </div>
                    <span className="px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 text-[10px] font-bold uppercase tracking-wider">
                      4 Core Workflows
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="p-3.5 rounded-xl border border-gray-100 bg-gray-50/60 space-y-1">
                      <p className="font-bold text-gray-900">1. Interactive Lead Finder &amp; Search Import</p>
                      <p className="text-[11px] text-gray-500 leading-relaxed">
                        Filter prospects by industry, location, company headcount, connection degree, or recent LinkedIn post activity, or paste any LinkedIn Search / Sales Navigator / Post Engagers URL.
                      </p>
                    </div>
                    <div className="p-3.5 rounded-xl border border-gray-100 bg-gray-50/60 space-y-1">
                      <p className="font-bold text-gray-900">2. AI Personalization &amp; Prompt Library</p>
                      <p className="text-[11px] text-gray-500 leading-relaxed">
                        Insert <code className="font-mono text-indigo-600">✨ [Prompt Name]</code> tokens alongside <code className="font-mono text-indigo-600">{'{{first_name}}'}</code> and <code className="font-mono text-indigo-600">{'{{company_name}}'}</code> to synthesize profile-aware icebreakers and preview them across real enrolled leads.
                      </p>
                    </div>
                    <div className="p-3.5 rounded-xl border border-gray-100 bg-gray-50/60 space-y-1">
                      <p className="font-bold text-gray-900">3. Cloned Voice Notes &amp; Spoken Previews</p>
                      <p className="text-[11px] text-gray-500 leading-relaxed">
                        Record or upload a clean 15–60s voice sample in Voice Studio, preview dynamic spoken variables against real workspace contacts, and attach voice note steps to your sequence.
                      </p>
                    </div>
                    <div className="p-3.5 rounded-xl border border-gray-100 bg-gray-50/60 space-y-1">
                      <p className="font-bold text-gray-900">4. Unified Inbox, Auto-Tagging &amp; Webhooks</p>
                      <p className="text-[11px] text-gray-500 leading-relaxed">
                        Configure sequence steps to auto-tag leads on completion, filter conversations by campaign/sender/tag in Unified Inbox, and stream real-time webhook events to Slack, Make, or HubSpot.
                      </p>
                    </div>
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

                {/* Simple & Elegant Contact Form Card */}
                <div
                  data-testid="outreach-settings-contact-card"
                  className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 sm:p-8"
                >
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                    <div className="lg:col-span-5 flex justify-center">
                      <img
                        src="/assets/contact-illustration.png"
                        alt="Person thinking with question marks"
                        width="980"
                        height="980"
                        className="w-full max-w-[260px] h-auto object-contain"
                      />
                    </div>
                    <div className="lg:col-span-7 space-y-4">
                      <div>
                        <h3 className="text-base font-bold text-gray-900">Send us a message</h3>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Fill in your details below and our team will reply to you shortly.
                        </p>
                      </div>

                      {contactResult ? (
                        <div className="p-6 rounded-xl bg-emerald-50/70 border border-emerald-200 text-center space-y-3">
                          <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mx-auto">
                            <Check className="w-5 h-5" />
                          </div>
                          <h4 className="text-sm font-bold text-gray-900">Message sent</h4>
                          <p className="text-xs text-gray-600 max-w-md mx-auto">
                            Thank you for reaching out. Our team has received your message and will reply within 24 hours.
                          </p>
                          {contactResult.ticket_id && (
                            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-emerald-200 text-[11px] font-mono font-bold text-emerald-800">
                              Reference: {contactResult.ticket_id}
                            </div>
                          )}
                          <div>
                            <button
                              type="button"
                              onClick={() => {
                                setContactResult(null);
                                setContactMessage('');
                                setContactAttachmentName('');
                              }}
                              className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors"
                            >
                              Send another message
                            </button>
                          </div>
                        </div>
                      ) : (
                        <form onSubmit={handleSubmitContactForm} className="space-y-3.5">
                          <div>
                            <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                              Full name *
                            </label>
                            <input
                              type="text"
                              required
                              value={contactName}
                              onChange={(e) => setContactName(e.target.value)}
                              placeholder="Enter your full name"
                              className="w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/15"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                              Email *
                            </label>
                            <input
                              type="email"
                              required
                              value={contactEmail}
                              onChange={(e) => setContactEmail(e.target.value)}
                              placeholder="Enter your email"
                              className="w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/15"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                              Your message *
                            </label>
                            <textarea
                              rows={4}
                              required
                              value={contactMessage}
                              onChange={(e) => setContactMessage(e.target.value)}
                              placeholder="Write your message..."
                              className="w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/15 resize-y"
                            />
                          </div>
                          <div>
                            <label className="flex items-center justify-between gap-2 px-3.5 py-2.5 rounded-xl border border-dashed border-gray-300 bg-gray-50/60 cursor-pointer hover:border-indigo-400 transition-colors">
                              <span className="text-xs font-medium text-gray-600 truncate">
                                {contactAttachmentName ? `Attached: ${contactAttachmentName}` : 'Attach a file (optional)'}
                              </span>
                              <input
                                type="file"
                                className="sr-only"
                                accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.csv"
                                onChange={(e) => {
                                  const file = e.target.files && e.target.files[0];
                                  setContactAttachmentName(file ? file.name : '');
                                }}
                              />
                            </label>
                          </div>
                          <div className="pt-1">
                            <button
                              type="submit"
                              disabled={sendingContact}
                              className="inline-flex items-center gap-1.5 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition-all disabled:opacity-50"
                            >
                              {sendingContact ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Sending...
                                </>
                              ) : (
                                <>
                                  <Mail className="w-3.5 h-3.5" /> Send message
                                </>
                              )}
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                  </div>
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
                  Teammate Email Address(es) *
                </label>
                <input
                  type="text"
                  required
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com, teammate2@company.com"
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
                <p className="mt-1 text-[10px] text-gray-400">
                  Separate multiple email addresses with commas to invite several teammates at once.
                </p>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-gray-700">
                    Role &amp; Permissions
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowRoleMatrix(true)}
                    className="text-[10px] font-semibold text-indigo-600 hover:underline"
                  >
                    See key differences between roles
                  </button>
                </div>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2 text-xs bg-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="editor">User (Editor) — Run own campaigns, leads &amp; shared templates</option>
                  <option value="admin">Manager (Admin) — Manage team members, templates &amp; view all campaigns</option>
                  <option value="client">Client — View inbox &amp; analytics only</option>
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
