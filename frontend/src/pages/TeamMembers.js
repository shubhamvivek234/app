import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getTeamMembers, inviteTeamMember, updateTeamMember, removeTeamMember,
  resendTeamInvite, assignTeamMemberAccounts, getSocialAccounts,
} from '@/lib/api';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  FaUsers, FaUserPlus, FaTrash, FaEnvelope, FaCrown, FaRedo,
  FaShareAlt, FaTimes, FaCheck, FaCopy, FaLink,
} from 'react-icons/fa';

// ── Constants ─────────────────────────────────────────────────────────────────
const ROLES = [
  { value: 'admin',  label: 'Admin',  desc: 'Can manage posts, accounts, and settings' },
  { value: 'member', label: 'Member', desc: 'Can create and edit posts' },
  { value: 'viewer', label: 'Viewer', desc: 'Read-only access' },
];

const ROLE_COLORS = {
  owner:  'bg-amber-100 text-amber-800',
  admin:  'bg-purple-100 text-purple-800',
  member: 'bg-blue-100 text-blue-700',
  viewer: 'bg-white border border-gray-200 text-gray-600',
};

const STATUS_COLORS = {
  pending:  'bg-orange-50 text-orange-600',
  accepted: 'bg-emerald-50 text-emerald-700',
};

const PLATFORM_META = {
  facebook:  { label: 'Facebook',  color: '#1877F2' },
  instagram: { label: 'Instagram', color: '#E1306C' },
  twitter:   { label: 'Twitter',   color: '#1DA1F2' },
  linkedin:  { label: 'LinkedIn',  color: '#0A66C2' },
  youtube:   { label: 'YouTube',   color: '#FF0000' },
  tiktok:    { label: 'TikTok',    color: '#010101' },
  bluesky:   { label: 'Bluesky',   color: '#0085FF' },
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const getExpiryLabel = (expiresAt) => {
  if (!expiresAt) return null;
  const diff = new Date(expiresAt) - new Date();
  if (diff <= 0) return 'Expired';
  const days = Math.floor(diff / 86400000);
  if (days > 0) return `Expires in ${days}d`;
  const hours = Math.floor(diff / 3600000);
  return hours > 0 ? `Expires in ${hours}h` : 'Expiring soon';
};

// ── Sub-components ────────────────────────────────────────────────────────────
const AvatarPlaceholder = ({ email }) => {
  const colors = ['bg-blue-400', 'bg-purple-400', 'bg-pink-400', 'bg-green-400', 'bg-orange-400'];
  const bg = colors[(email?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`w-10 h-10 rounded-full ${bg} flex items-center justify-center text-white font-semibold text-sm flex-shrink-0`}>
      {email?.[0]?.toUpperCase() || '?'}
    </div>
  );
};

const PlatformDot = ({ platform }) => {
  const meta = PLATFORM_META[platform] || { color: '#6b7280' };
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ background: meta.color }}
      title={meta.label || platform}
    />
  );
};

// ── Assign Accounts Modal ─────────────────────────────────────────────────────
const AssignAccountsModal = ({ member, allAccounts, onClose, onSaved }) => {
  const [selected, setSelected] = useState(new Set(member.assigned_account_ids || []));
  const [saving, setSaving] = useState(false);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(allAccounts.map((a) => a.id)));
  const clearAll  = () => setSelected(new Set());

  const handleSave = async () => {
    setSaving(true);
    try {
      await assignTeamMemberAccounts(member.id, [...selected]);
      onSaved(member.id, [...selected]);
      toast.success('Account access updated');
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save account access');
    } finally {
      setSaving(false);
    }
  };

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Assign Social Accounts</h2>
            <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{member.email}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
            <FaTimes className="text-sm" />
          </button>
        </div>

        {/* Account list */}
        <div className="px-6 py-4 max-h-80 overflow-y-auto">
          {allAccounts.length === 0 ? (
            <div className="text-center py-8">
              <FaShareAlt className="text-3xl text-gray-200 mx-auto mb-2" />
              <p className="text-sm text-gray-400">No social accounts connected yet.</p>
              <p className="text-xs text-gray-300 mt-1">Connect accounts in Settings → Connections.</p>
            </div>
          ) : (
            <>
              {/* Select all / clear */}
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs text-gray-400">{selected.size} of {allAccounts.length} selected</p>
                <div className="flex gap-2">
                  <button onClick={selectAll} className="text-xs text-indigo-500 hover:underline">All</button>
                  <span className="text-gray-200">·</span>
                  <button onClick={clearAll}  className="text-xs text-gray-400 hover:underline">None</button>
                </div>
              </div>

              <div className="space-y-1">
                {allAccounts.map((account) => {
                  const meta = PLATFORM_META[account.platform] || { label: account.platform, color: '#6b7280' };
                  const isChecked = selected.has(account.id);
                  return (
                    <button
                      key={account.id}
                      onClick={() => toggle(account.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors ${isChecked ? 'bg-indigo-50 border border-indigo-200' : 'border border-transparent hover:bg-gray-50'}`}
                    >
                      {/* Avatar */}
                      {account.picture_url ? (
                        <img src={account.picture_url} alt="" className="w-9 h-9 rounded-full object-cover flex-shrink-0" />
                      ) : (
                        <div className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0" style={{ background: meta.color }}>
                          {(account.platform_username || account.platform)?.[0]?.toUpperCase()}
                        </div>
                      )}

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {account.platform_username || '—'}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <PlatformDot platform={account.platform} />
                          <span className="text-xs text-gray-400">{meta.label}</span>
                        </div>
                      </div>

                      {/* Checkbox */}
                      <div className={`w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0 transition-colors ${isChecked ? 'bg-indigo-600' : 'border border-gray-300'}`}>
                        {isChecked && <FaCheck className="text-white text-[10px]" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-2 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose} className="flex-1 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2 text-sm font-semibold bg-gray-900 hover:bg-gray-800 text-white rounded-xl disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save Access'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────────────
const TeamMembers = () => {
  const [members,       setMembers]       = useState([]);
  const [allAccounts,   setAllAccounts]   = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [inviteEmail,   setInviteEmail]   = useState('');
  const [inviteRole,    setInviteRole]    = useState('member');
  const [inviting,      setInviting]      = useState(false);
  const [showInvite,    setShowInvite]    = useState(false);
  const [assignTarget,  setAssignTarget]  = useState(null); // member being assigned

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [membersData, accountsData] = await Promise.all([
        getTeamMembers(),
        getSocialAccounts(),
      ]);
      setMembers(membersData);
      setAllAccounts(accountsData);
    } catch {
      toast.error('Failed to load team');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const member = await inviteTeamMember(inviteEmail.trim(), inviteRole);
      setMembers((prev) => [member, ...prev]);
      setInviteEmail('');
      setShowInvite(false);
      if (member.email_sent === false) {
        // Email not configured — copy the link immediately so they can share manually
        if (member.invite_token) {
          const link = `${window.location.origin}/accept-invite?token=${member.invite_token}`;
          try {
            await navigator.clipboard.writeText(link);
            toast.warning(
              `Email not configured (RESEND_API_KEY missing). Invite link copied to clipboard — share it manually with ${member.email}`,
              { duration: 12000 }
            );
          } catch {
            toast.warning(
              `Email not configured. Share this link manually: ${window.location.origin}/accept-invite?token=${member.invite_token}`,
              { duration: 20000 }
            );
          }
        } else {
          toast.warning(
            `Member added, but invite email could not be sent — RESEND_API_KEY is not configured in the backend .env file.`,
            { duration: 10000 }
          );
        }
      } else {
        toast.success(`Invite email sent to ${member.email} ✓`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to invite member');
    } finally {
      setInviting(false);
    }
  };

  const handleRoleChange = async (id, role) => {
    try {
      await updateTeamMember(id, { role });
      setMembers((prev) => prev.map((m) => m.id === id ? { ...m, role } : m));
      toast.success('Role updated');
    } catch {
      toast.error('Failed to update role');
    }
  };

  const handleRemove = async (id, email) => {
    if (!window.confirm(`Remove ${email} from your team?`)) return;
    try {
      await removeTeamMember(id);
      setMembers((prev) => prev.filter((m) => m.id !== id));
      toast.success('Member removed');
    } catch {
      toast.error('Failed to remove member');
    }
  };

  const handleResend = async (id, email) => {
    try {
      const result = await resendTeamInvite(id);
      if (result?.email_sent === false) {
        toast.warning(
          `Invite token refreshed, but email could not be sent — RESEND_API_KEY is not configured in the backend .env file.`,
          { duration: 10000 }
        );
      } else {
        toast.success(`Invite resent to ${email} ✓`);
      }
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to resend invite');
    }
  };

  const handleAssignSaved = (memberId, newIds) => {
    setMembers((prev) => prev.map((m) => m.id === memberId ? { ...m, assigned_account_ids: newIds } : m));
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto px-4 py-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <FaUsers className="text-gray-600 text-xl" />
            <h1 className="text-xl font-semibold text-gray-900">Team Members</h1>
            <span className="text-sm text-gray-400 ml-1">({members.length})</span>
          </div>
          <button
            onClick={() => setShowInvite(!showInvite)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <FaUserPlus className="text-xs" />
            Invite member
          </button>
        </div>

        {/* Invite panel */}
        {showInvite && (
          <div className="bg-white rounded-2xl border border-gray-200 p-5 mb-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">Invite a team member</h2>
            <div className="flex gap-3 mb-3">
              <div className="flex-1 relative">
                <FaEnvelope className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300 text-xs" />
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleInvite(); }}
                  placeholder="colleague@company.com"
                  className="w-full border border-gray-200 rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
                />
              </div>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <div className="mb-3">
              {ROLES.find((r) => r.value === inviteRole) && (
                <p className="text-xs text-gray-400">{ROLES.find((r) => r.value === inviteRole).desc}</p>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowInvite(false); setInviteEmail(''); }}
                className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleInvite}
                disabled={inviting || !inviteEmail.trim()}
                className="px-4 py-1.5 text-sm font-semibold bg-gray-900 hover:bg-gray-800 text-white rounded-lg disabled:opacity-50 transition-colors"
              >
                {inviting ? 'Sending…' : 'Send invite'}
              </button>
            </div>
          </div>
        )}

        {/* Member list */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          {/* Owner row */}
          <div className="flex items-center gap-4 px-5 py-4 border-b border-gray-100">
            <div className="w-10 h-10 rounded-full bg-gray-900 flex items-center justify-center text-white">
              <FaCrown className="text-amber-400 text-sm" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-gray-900">You (Owner)</p>
              <p className="text-xs text-gray-400">Full access to everything</p>
            </div>
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${ROLE_COLORS.owner}`}>Owner</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-700 rounded-full animate-spin" />
            </div>
          ) : members.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <FaUsers className="text-4xl text-gray-200 mb-2" />
              <p className="text-sm text-gray-400">No team members yet.</p>
              <p className="text-xs text-gray-300 mt-1">Invite your colleagues to collaborate.</p>
            </div>
          ) : (
            members.map((member, i) => {
              const assignedIds = member.assigned_account_ids || [];
              const assignedAccounts = allAccounts.filter((a) => assignedIds.includes(a.id));

              return (
                <div
                  key={member.id}
                  className={`px-5 py-4 ${i < members.length - 1 ? 'border-b border-gray-100' : ''} hover:bg-gray-50 transition-colors`}
                >
                  {/* Main row */}
                  <div className="flex items-center gap-4">
                    <AvatarPlaceholder email={member.email} />

                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{member.email}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${STATUS_COLORS[member.status] || STATUS_COLORS.pending}`}>
                          {member.status === 'accepted' ? 'Active' : 'Invite pending'}
                        </span>
                        {member.status === 'pending' && member.expires_at && (
                          <span className={`text-[10px] font-medium ${new Date(member.expires_at) < new Date() ? 'text-red-400' : 'text-gray-300'}`}>
                            {getExpiryLabel(member.expires_at)}
                          </span>
                        )}
                        {member.status === 'accepted' && (member.accepted_at || member.invited_at) && (
                          <span className="text-[10px] text-gray-300">
                            Joined {format(parseISO(member.accepted_at || member.invited_at), 'MMM d')}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Role selector */}
                    <select
                      value={member.role}
                      onChange={(e) => handleRoleChange(member.id, e.target.value)}
                      className={`text-xs font-semibold px-2.5 py-1.5 rounded-full border-0 focus:outline-none focus:ring-2 focus:ring-gray-300 cursor-pointer ${ROLE_COLORS[member.role] || ROLE_COLORS.member}`}
                    >
                      {ROLES.map((r) => (
                        <option key={r.value} value={r.value}>{r.label}</option>
                      ))}
                    </select>

                    {/* Can-approve toggle (accepted members only) */}
                    {member.status === 'accepted' && (
                      <button
                        onClick={async () => {
                          const next = !member.can_approve;
                          try {
                            await updateTeamMember(member.id, { can_approve: next });
                            setMembers((prev) => prev.map((m) => m.id === member.id ? { ...m, can_approve: next } : m));
                            toast.success(next ? 'Can now approve posts' : 'Approval permission removed');
                          } catch { toast.error('Failed to update approval permission'); }
                        }}
                        title={member.can_approve ? 'Remove post approval permission' : 'Allow this member to approve posts'}
                        className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold transition-colors ${member.can_approve ? 'bg-green-50 text-green-600 hover:bg-red-50 hover:text-red-500' : 'bg-gray-100 text-gray-400 hover:bg-green-50 hover:text-green-600'}`}
                      >
                        <FaCheck className="text-[9px]" />
                        {member.can_approve ? 'Approver' : 'Approver?'}
                      </button>
                    )}

                    {/* Assign accounts button (accepted members only) */}
                    {member.status === 'accepted' && (
                      <button
                        onClick={() => setAssignTarget(member)}
                        title="Assign social accounts"
                        className="p-2 text-gray-300 hover:text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors"
                      >
                        <FaShareAlt className="text-xs" />
                      </button>
                    )}

                    {/* Copy invite link + Resend (pending only) */}
                    {member.status === 'pending' && member.invite_token && (
                      <button
                        onClick={() => {
                          const link = `${window.location.origin}/accept-invite?token=${member.invite_token}`;
                          navigator.clipboard.writeText(link).then(() => {
                            toast.success('Invite link copied! Share it with your team member.');
                          }).catch(() => {
                            toast.info(`Invite link: ${link}`, { duration: 12000 });
                          });
                        }}
                        title="Copy invite link"
                        className="p-2 text-gray-300 hover:text-emerald-500 hover:bg-emerald-50 rounded-lg transition-colors"
                      >
                        <FaLink className="text-xs" />
                      </button>
                    )}
                    {member.status === 'pending' && (
                      <button
                        onClick={() => handleResend(member.id, member.email)}
                        title="Resend invite email"
                        className="p-2 text-gray-300 hover:text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors"
                      >
                        <FaRedo className="text-xs" />
                      </button>
                    )}

                    <button
                      onClick={() => handleRemove(member.id, member.email)}
                      title={member.status === 'pending' ? 'Cancel invite' : 'Remove member'}
                      className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <FaTrash className="text-xs" />
                    </button>
                  </div>

                  {/* Assigned accounts chips (accepted + has assignments) */}
                  {member.status === 'accepted' && (
                    <div className="mt-2.5 ml-14 flex items-center gap-1.5 flex-wrap">
                      {assignedAccounts.length === 0 ? (
                        <button
                          onClick={() => setAssignTarget(member)}
                          className="text-[11px] text-gray-300 hover:text-indigo-400 transition-colors flex items-center gap-1"
                        >
                          <FaShareAlt className="text-[9px]" />
                          No accounts assigned — click to assign
                        </button>
                      ) : (
                        <>
                          {assignedAccounts.slice(0, 5).map((acc) => {
                            const meta = PLATFORM_META[acc.platform] || { color: '#6b7280' };
                            return (
                              <span
                                key={acc.id}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium text-gray-600"
                                style={{ borderColor: meta.color + '40', background: meta.color + '10' }}
                              >
                                <PlatformDot platform={acc.platform} />
                                {acc.platform_username || acc.platform}
                              </span>
                            );
                          })}
                          {assignedAccounts.length > 5 && (
                            <span className="text-[11px] text-gray-400">+{assignedAccounts.length - 5} more</span>
                          )}
                          <button
                            onClick={() => setAssignTarget(member)}
                            className="text-[11px] text-indigo-400 hover:text-indigo-600 hover:underline ml-1"
                          >
                            Edit
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Info box */}
        <div className="mt-4 p-4 bg-blue-50 rounded-xl border border-blue-100">
          <p className="text-xs text-blue-600 font-medium mb-1">About team access</p>
          <ul className="text-xs text-blue-500 space-y-0.5">
            <li>• <strong>Admin</strong> — manage posts, accounts, and all settings</li>
            <li>• <strong>Member</strong> — create and edit posts, submit for review</li>
            <li>• <strong>Viewer</strong> — read-only access to posts and analytics</li>
            <li>• Use the <FaShareAlt className="inline text-[9px]" /> icon to control which social accounts each member can access</li>
            <li>• Toggle <strong>Approver</strong> on a member to let them receive approval request emails and approve/reject posts</li>
          </ul>
        </div>
      </div>

      {/* Assign Accounts Modal */}
      {assignTarget && (
        <AssignAccountsModal
          member={assignTarget}
          allAccounts={allAccounts}
          onClose={() => setAssignTarget(null)}
          onSaved={handleAssignSaved}
        />
      )}
    </DashboardLayout>
  );
};

export default TeamMembers;
