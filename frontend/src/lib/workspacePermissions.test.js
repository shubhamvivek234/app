import {
  canReadApprovalsWorkspace,
  canReadTeamWorkspace,
  hasWorkspacePermission,
} from './workspacePermissions';

describe('workspacePermissions', () => {
  test('returns false when permission data is missing', () => {
    expect(hasWorkspacePermission(null, 'approval:read')).toBe(false);
    expect(canReadTeamWorkspace({})).toBe(false);
  });

  test('detects allowed permissions from auth profile', () => {
    const user = {
      workspace_permissions: ['workspace:read', 'approval:read'],
    };

    expect(hasWorkspacePermission(user, 'workspace:read')).toBe(true);
    expect(canReadTeamWorkspace(user)).toBe(true);
    expect(canReadApprovalsWorkspace(user)).toBe(true);
    expect(hasWorkspacePermission(user, 'post:update')).toBe(false);
  });

  test('allows approvals without granting team access', () => {
    const user = {
      workspace_permissions: ['approval:read'],
    };

    expect(canReadApprovalsWorkspace(user)).toBe(true);
    expect(canReadTeamWorkspace(user)).toBe(false);
  });
});
