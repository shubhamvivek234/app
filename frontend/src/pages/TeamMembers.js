import React, { useCallback, useEffect, useState } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import {
  FaCrown,
  FaEnvelope,
  FaLink,
  FaLock,
  FaShareAlt,
  FaTrash,
  FaUserPlus,
  FaUsers,
} from 'react-icons/fa';
import { toast } from 'sonner';

import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import {
  getWorkspaceMembers,
  inviteWorkspaceMember,
  removeWorkspaceMember,
  revokeWorkspaceInvite,
  updateWorkspaceMemberRole,
} from '@/lib/api';

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin', description: 'Manage members, posts, and accounts' },
  { value: 'editor', label: 'Editor', description: 'Create and update content' },
  { value: 'viewer', label: 'Viewer', description: 'Read-only workspace access' },
  { value: 'client', label: 'Client', description: 'Review and approve/reject scheduled content' },
];

const ROLE_STYLES = {
  owner: 'border-amber-200 bg-amber-50 text-amber-800',
  admin: 'border-violet-200 bg-violet-50 text-violet-800',
  editor: 'border-blue-200 bg-blue-50 text-blue-800',
  viewer: 'border-slate-200 bg-slate-50 text-slate-700',
  client: 'border-emerald-200 bg-emerald-50 text-emerald-700',
};

const Avatar = ({ member }) => {
  if (member.avatar_url) {
    return (
      <img
        src={member.avatar_url}
        alt=""
        className="h-10 w-10 rounded-full border border-slate-200 object-cover"
      />
    );
  }

  const seed = (member.display_name || member.email || member.user_id || '?').trim();
  const initial = seed[0]?.toUpperCase() || '?';
  const palette = ['bg-blue-500', 'bg-emerald-500', 'bg-amber-500', 'bg-violet-500', 'bg-rose-500'];
  const tone = palette[seed.charCodeAt(0) % palette.length];

  return (
    <div className={`flex h-10 w-10 items-center justify-center rounded-full ${tone} text-sm font-semibold text-white`}>
      {initial}
    </div>
  );
};

const formatTimestamp = (value, fallback) => {
  if (!value) return fallback;
  try {
    return format(new Date(value), 'MMM d, yyyy');
  } catch {
    return fallback;
  }
};

const formatRelativeExpiry = (value) => {
  if (!value) return 'Expires soon';
  try {
    return `Expires ${formatDistanceToNow(new Date(value), { addSuffix: true })}`;
  } catch {
    return 'Expires soon';
  }
};

const TeamMembers = () => {
  const { user } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadErrorStatus, setLoadErrorStatus] = useState(null);
  const [inviting, setInviting] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('viewer');
  const [removeBusyId, setRemoveBusyId] = useState(null);
  const [roleBusyId, setRoleBusyId] = useState(null);
  const [revokeBusyId, setRevokeBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadErrorStatus(null);
    try {
      const data = await getWorkspaceMembers();
      setWorkspace(data);
    } catch (error) {
      const status = error?.response?.status || null;
      setLoadErrorStatus(status);
      if (status !== 403) {
        toast.error(error?.response?.data?.detail || 'Failed to load team workspace');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const members = workspace?.members || [];
  const pendingInvites = workspace?.pending_invites || [];
  const permissions = workspace?.permissions || {};
  const currentUserId = user?.user_id;
  const currentMember = members.find((member) => member.user_id === currentUserId) || null;

  if (!loading && loadErrorStatus === 403) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:px-8">
          <section className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 text-white">
              <FaUsers className="text-sm" />
            </div>
            <h1 className="mt-5 text-2xl font-semibold text-slate-950">Team access is limited in this workspace</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Your current role can’t open the Team workspace surface. Ask an admin or owner to grant a role with workspace access if you need to review members or manage invites.
            </p>
          </section>
        </div>
      </DashboardLayout>
    );
  }

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      const result = await inviteWorkspaceMember({
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteEmail('');
      setInviteRole('viewer');
      await load();
      toast.success(result?.invite?.invite_url ? 'Invite created. Share the link from Pending invites.' : 'Invite created');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to create invite');
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (member) => {
    if (!window.confirm(`Remove ${member.email || member.display_name || 'this member'} from the workspace?`)) {
      return;
    }
    setRemoveBusyId(member.user_id);
    try {
      await removeWorkspaceMember(member.user_id);
      await load();
      toast.success('Member removed');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to remove member');
    } finally {
      setRemoveBusyId(null);
    }
  };

  const handleRoleChange = async (memberId, nextRole) => {
    setRoleBusyId(memberId);
    try {
      await updateWorkspaceMemberRole(memberId, nextRole);
      setWorkspace((current) => {
        if (!current) return current;
        return {
          ...current,
          members: (current.members || []).map((member) => (
            member.user_id === memberId ? { ...member, role: nextRole } : member
          )),
        };
      });
      toast.success('Role updated');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to update role');
    } finally {
      setRoleBusyId(null);
    }
  };

  const handleCopyInvite = async (invite) => {
    try {
      await navigator.clipboard.writeText(invite.invite_url);
      toast.success(`Copied invite for ${invite.email}`);
    } catch {
      toast.error('Could not copy invite link');
    }
  };

  const handleRevokeInvite = async (invite) => {
    if (!window.confirm(`Revoke the invite for ${invite.email}?`)) {
      return;
    }
    setRevokeBusyId(invite.invite_id);
    try {
      await revokeWorkspaceInvite(invite.invite_id);
      setWorkspace((current) => {
        if (!current) return current;
        return {
          ...current,
          pending_invites: (current.pending_invites || []).filter((item) => item.invite_id !== invite.invite_id),
        };
      });
      toast.success('Invite revoked');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to revoke invite');
    } finally {
      setRevokeBusyId(null);
    }
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white">
                  <FaUsers className="text-sm" />
                </div>
                <div>
                  <h1 className="text-2xl font-semibold text-slate-950">Team</h1>
                  <p className="text-sm text-slate-500">{workspace?.workspace_name || 'Workspace access'}</p>
                </div>
              </div>
              <p className="max-w-2xl text-sm leading-6 text-slate-600">
                Manage who can access this workspace, which roles they hold, and which invites are still outstanding.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Members</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{members.length}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Pending invites</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{pendingInvites.length}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Your role</p>
                <p className="mt-2 text-sm font-semibold text-slate-950">{currentMember?.role || workspace?.current_user_role || 'viewer'}</p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-950">Members</h2>
                <p className="text-sm text-slate-500">Workspace roles and access.</p>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {loading ? (
                <div className="space-y-3">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="h-20 animate-pulse rounded-lg border border-slate-200 bg-slate-50" />
                  ))}
                </div>
              ) : members.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                  No members in this workspace yet.
                </div>
              ) : (
                members.map((member) => {
                  const roleTone = ROLE_STYLES[member.role] || ROLE_STYLES.viewer;
                  const canEditRole = permissions.can_update_member_role && member.role !== 'owner' && member.user_id !== currentUserId;
                  const canRemove = permissions.can_remove_member && member.role !== 'owner' && member.user_id !== currentUserId;
                  return (
                    <div key={member.user_id} className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-slate-50/70 p-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="flex min-w-0 items-center gap-3">
                        <Avatar member={member} />
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="truncate text-sm font-semibold text-slate-900">
                              {member.display_name || member.email || member.user_id}
                            </p>
                            {member.role === 'owner' ? (
                              <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800">
                                <FaCrown className="text-[10px]" />
                                Owner
                              </span>
                            ) : null}
                            {member.user_id === currentUserId ? (
                              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                                You
                              </span>
                            ) : null}
                          </div>
                          <p className="truncate text-sm text-slate-500">{member.email || 'No email available'}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            Joined {formatTimestamp(member.joined_at, 'recently')}
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {canEditRole ? (
                          <select
                            value={member.role}
                            onChange={(event) => handleRoleChange(member.user_id, event.target.value)}
                            disabled={roleBusyId === member.user_id}
                            className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300"
                          >
                            {ROLE_OPTIONS.map((role) => (
                              <option key={role.value} value={role.value}>
                                {role.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold capitalize ${roleTone}`}>
                            {member.role}
                          </span>
                        )}

                        {canRemove ? (
                          <button
                            type="button"
                            onClick={() => handleRemove(member)}
                            disabled={removeBusyId === member.user_id}
                            className="inline-flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                          >
                            <FaTrash className="text-xs" />
                            {removeBusyId === member.user_id ? 'Removing…' : 'Remove'}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="border-b border-slate-100 pb-4">
                <h2 className="text-lg font-semibold text-slate-950">Invite teammate</h2>
                <p className="text-sm text-slate-500">Create a role-specific invite link for this workspace.</p>
              </div>

              {!user?.email_verified ? (
                <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  <FaLock className="mt-0.5 shrink-0 text-amber-600" />
                  <p>Verify your email before creating workspace invites.</p>
                </div>
              ) : !permissions.can_invite ? (
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  Your role can view the team, but it cannot create new invites.
                </div>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="grid gap-3">
                    <label className="grid gap-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Email</span>
                      <div className="relative">
                        <FaEnvelope className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-300" />
                        <input
                          type="email"
                          value={inviteEmail}
                          onChange={(event) => setInviteEmail(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.preventDefault();
                              void handleInvite();
                            }
                          }}
                          placeholder="teammate@company.com"
                          className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm text-slate-900 outline-none focus:ring-2 focus:ring-slate-300"
                        />
                      </div>
                    </label>

                    <label className="grid gap-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Role</span>
                      <select
                        value={inviteRole}
                        onChange={(event) => setInviteRole(event.target.value)}
                        className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-slate-300"
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role.value} value={role.value}>
                            {role.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-sm font-medium text-slate-900">
                      {ROLE_OPTIONS.find((role) => role.value === inviteRole)?.label}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {ROLE_OPTIONS.find((role) => role.value === inviteRole)?.description}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleInvite}
                    disabled={inviting || !inviteEmail.trim()}
                    className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                  >
                    <FaUserPlus className="text-xs" />
                    {inviting ? 'Creating invite…' : 'Create invite'}
                  </button>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-950">Pending invites</h2>
                  <p className="text-sm text-slate-500">Share the invite link directly or revoke it before it expires.</p>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600">
                  {pendingInvites.length} open
                </span>
              </div>

              <div className="mt-4 space-y-3">
                {loading ? (
                  <div className="h-24 animate-pulse rounded-lg border border-slate-200 bg-slate-50" />
                ) : pendingInvites.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
                    No pending invites.
                  </div>
                ) : (
                  pendingInvites.map((invite) => (
                    <div key={invite.invite_id} className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="truncate text-sm font-semibold text-slate-900">{invite.email}</p>
                            <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold capitalize ${ROLE_STYLES[invite.role] || ROLE_STYLES.viewer}`}>
                              {invite.role}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-slate-500">{formatRelativeExpiry(invite.expires_at)}</p>
                          <p className="mt-1 text-xs text-slate-400">
                            Created {formatTimestamp(invite.created_at, 'recently')}
                            {invite.invited_by_name ? ` by ${invite.invited_by_name}` : ''}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleCopyInvite(invite)}
                            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                          >
                            <FaLink className="text-xs" />
                            Copy link
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRevokeInvite(invite)}
                            disabled={revokeBusyId === invite.invite_id}
                            className="inline-flex h-10 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-sm font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                          >
                            <FaShareAlt className="text-xs" />
                            {revokeBusyId === invite.invite_id ? 'Revoking…' : 'Revoke'}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
};

export default TeamMembers;
