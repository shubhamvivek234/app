const keys = ['contract_version', 'workspace_id', 'visibility', 'created_by_you', 'can_configure',
  'can_edit', 'can_delete', 'execution_authorized'];

function accessFor(template) {
  const access = template?.workspace_access;
  if (!access || typeof access !== 'object' || Array.isArray(access) || Object.keys(access).length !== keys.length
    || !keys.every(key => Object.prototype.hasOwnProperty.call(access, key)) || access.contract_version !== 1
    || typeof access.workspace_id !== 'string' || !access.workspace_id.trim() || access.workspace_id.length > 200
    || !['created_by_you', 'can_configure', 'can_edit', 'can_delete'].every(key => typeof access[key] === 'boolean')
    || access.execution_authorized !== false) return null;
  if (access.visibility === 'workspace' && template.is_custom === true) return access;
  if (access.visibility === 'builtin' && template.is_custom !== true
    && access.created_by_you === false && access.can_edit === false && access.can_delete === false) return access;
  return null;
}

export function templateActionAllowed(template, action) {
  const access = accessFor(template);
  return Boolean(access && ['configure', 'edit', 'delete'].includes(action) && access[`can_${action}`] === true);
}

export function templateAccessLabel(template) {
  const access = accessFor(template);
  if (!access) return 'Access needs review';
  if (access.visibility === 'builtin') return 'Built-in template';
  return access.created_by_you ? 'Workspace template · Saved by you' : 'Workspace template';
}
