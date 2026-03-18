import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getWorkspaceMembers, inviteWorkspaceMember, removeWorkspaceMember,
  getSocialAccounts,
} from '@/lib/api';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';
import {
  FaUsers, FaUserPlus, FaTrash, FaEnvelope, FaCrown,
  FaShareAlt, FaTimes, FaCheck,
} from 'react-icons/fa';

// ── Constants ─────────────────────────────────────────────────────────────────
const ROLES = [
  { value: 'admin',  label: 'Admin',  desc: 'Can manage posts, accounts, and settings' },
  { value: 'editor', label: 'Editor', desc: 'Can create and edit posts' },
  { value: 'viewer', label: 'Viewer', desc: 'Read-only access' },
];

const ROLE_COLORS = {
  owner:  'bg-amber-100 text-amber-800',
  admin:  'bg-purple-100 text-purple-800',
  editor: 'bg-blue-100 text-blue-700',
  viewer: 'bg-white border border-gray-200 text-gray-600',
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
const getRoleLabel = (role) => ROLES.find((r) => r.value === role)?.label || role;

// ── Sub-components ────────────────────────────────────────────────────────────
const AvatarPlaceholder = ({ email, name }) => {
  const colors = ['bg-blue-400', 'bg-purple-400', 'bg-pink-400', 'bg-green-400', 'bg-orange-400'];
  const seed = email || name || '?';
  const bg = colors[(seed.charCodeAt(0) || 0) % colors.length];
  const initial = (name?.[0] || email?.[0] || '?').toUpperCase();
  return (
    <div className={`w-10 h-10 rounded-full ${bg} flex items-center justify-center text-white font-semibold text-sm flex-shrink-0`}>
      {initial}
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

// ── Main Component ────────────────────────────────────────────────────────────
const TeamMembers = () => {
  const [members,     setMembers]     = useState([]);
  const [workspaceId, setWorkspaceId] = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole,  setInviteRole]  = useState('viewer');
  const [inviting,    setInviting]    = useState(false);
  const [showInvite,  setShowInvite]  = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getWorkspaceMembers();
      // Exclude the owner (role === 'owner') from the members list shown — owner row is rendered separately
      setMembers((data.members || []).filter((m) => m.role !== 'owner'));
      setWorkspaceId(data.workspace_id || null);
    } catch {
      toast.error('Failed to load workspace members');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const result = await inviteWorkspaceMember(inviteEmail.trim(), inviteRole);
      setInviteEmail('');
      setShowInvite(false);
      toast.success(result.message || `Invitation sent to ${inviteEmail}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to send invitation');
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (memberUserId, email) => {
    if (!window.confirm(`Remove ${email} from this workspace?`)) return;
    try {
      await removeWorkspaceMember(memberUserId);
      setMembers((prev) => prev.filter((m) => m.user_id !== memberUserId));
      toast.success('Member removed');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to remove member');
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto px-4 py-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <FaUsers className="text-gray-600 text-xl" />
            <h1 className="text-xl font-semibold text-gray-900">Team Members</h1>
            <span className="text-sm text-gray-400 ml-1">({members.length + 1})</span>
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
            members.map((member, i) => (
              <div
                key={member.user_id}
                className={`px-5 py-4 ${i < members.length - 1 ? 'border-b border-gray-100' : ''} hover:bg-gray-50 transition-colors`}
              >
                <div className="flex items-center gap-4">
                  <AvatarPlaceholder email={member.email} name={member.name} />

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {member.name || member.email}
                    </p>
                    <p className="text-xs text-gray-400 truncate">{member.email}</p>
                    {member.joined_at && (
                      <p className="text-[10px] text-gray-300 mt-0.5">
                        Joined {format(parseISO(member.joined_at), 'MMM d, yyyy')}
                      </p>
                    )}
                  </div>

                  {/* Role badge */}
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${ROLE_COLORS[member.role] || ROLE_COLORS.viewer}`}>
                    {getRoleLabel(member.role)}
                  </span>

                  {/* Remove button */}
                  <button
                    onClick={() => handleRemove(member.user_id, member.email)}
                    title="Remove member"
                    className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <FaTrash className="text-xs" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Info box */}
        <div className="mt-4 p-4 bg-blue-50 rounded-xl border border-blue-100">
          <p className="text-xs text-blue-600 font-medium mb-1">About workspace access</p>
          <ul className="text-xs text-blue-500 space-y-0.5">
            <li>• <strong>Admin</strong> — manage posts, accounts, members, and settings</li>
            <li>• <strong>Editor</strong> — create and edit posts, publish content</li>
            <li>• <strong>Viewer</strong> — read-only access to analytics</li>
            <li>• Invited members receive an email with a link to join the workspace</li>
          </ul>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default TeamMembers;
