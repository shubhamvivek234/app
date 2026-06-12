export const getWorkspacePermissions = (user) => (
  Array.isArray(user?.workspace_permissions) ? user.workspace_permissions : []
);

export const hasWorkspacePermission = (user, permission) => (
  getWorkspacePermissions(user).includes(permission)
);

export const canReadTeamWorkspace = (user) => hasWorkspacePermission(user, 'workspace:read');

export const canReadApprovalsWorkspace = (user) => hasWorkspacePermission(user, 'approval:read');
