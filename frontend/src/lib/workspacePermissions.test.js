import {
  canReadApprovalsWorkspace,
  canReadTeamWorkspace,
  hasWorkspacePermission,
} from './workspacePermissions';

describe('workspacePermissions', () => {
  test('returns false when permission data is missing', () => {
    expect(hasWorkspacePermission(null, 'post:read')).toBe(false);
    expect(canReadTeamWorkspace({})).toBe(false);
  });

  test('detects allowed permissions from auth profile', () => {
    const user = {
      workspace_permissions: ['workspace:read', 'post:read'],
    };

    expect(hasWorkspacePermission(user, 'workspace:read')).toBe(true);
    expect(canReadTeamWorkspace(user)).toBe(true);
    expect(canReadApprovalsWorkspace(user)).toBe(true);
    expect(hasWorkspacePermission(user, 'post:update')).toBe(false);
  });
});
