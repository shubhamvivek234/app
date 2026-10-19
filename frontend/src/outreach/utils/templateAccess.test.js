import { templateActionAllowed, templateAccessLabel } from './templateAccess';

const row = (changes = {}) => ({ is_custom: true, workspace_access: { contract_version: 1, workspace_id: 'workspace',
  visibility: 'workspace', created_by_you: false, can_configure: true, can_edit: true, can_delete: false,
  execution_authorized: false, ...changes } });
test('workspace access describes roles rather than creator authority', () => {
  expect(templateAccessLabel(row())).toBe('Workspace template');
  expect(templateAccessLabel(row({created_by_you: true}))).toBe('Workspace template · Saved by you');
  expect(templateActionAllowed(row(), 'configure')).toBe(true);
  expect(templateActionAllowed(row(), 'edit')).toBe(true);
  expect(templateActionAllowed(row({created_by_you: true}), 'delete')).toBe(false);
  expect(templateActionAllowed(row(), 'launch')).toBe(false);
});
test('builtins can configure but never edit or delete', () => {
  const builtin = { ...row({visibility: 'builtin', can_edit: false}), is_custom: false };
  expect(templateAccessLabel(builtin)).toBe('Built-in template');
  expect(templateActionAllowed(builtin, 'configure')).toBe(true);
  expect(templateActionAllowed(builtin, 'edit')).toBe(false);
});
test.each([{}, {contract_version: 2}, {can_edit: 1}, {can_delete: 'true'}, {execution_authorized: true},
  {workspace_id: []}, {visibility: 'public'}, {created_by_you: 'yes'}, {extra: true}])('unsupported access fails closed: %j', changes => {
  const value = Object.keys(changes).length ? row(changes) : {is_custom: true};
  for (const action of ['configure', 'edit', 'delete']) expect(templateActionAllowed(value, action)).toBe(false);
  expect(templateAccessLabel(value)).toBe('Access needs review');
});
test('inconsistent builtin capabilities cannot masquerade as custom workspace permission', () => {
  expect(templateActionAllowed({...row(), is_custom: false}, 'configure')).toBe(false);
  expect(templateActionAllowed(row({visibility: 'builtin'}), 'edit')).toBe(false);
});
