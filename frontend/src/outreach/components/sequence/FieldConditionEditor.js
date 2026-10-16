import React, { useState } from 'react';
import ConditionNumberInput from './ConditionNumberInput';

export const STORED_FIELDS = ['first_name', 'last_name', 'company_name', 'job_title', 'location', 'country_code', 'email', 'phone'];
export const DEFAULT_FIELD_CONDITION = { condition_contract_version: 1, field: 'company_name', operator: 'has_value' };
const style = 'w-full rounded-lg border border-gray-200 bg-white p-2 text-sm';
export function conditionBranchLabel(label) {
  const normalized = typeof label === 'string' ? label.trim().toLowerCase() : label;
  if (['yes', 'true', 'positive', 'has data'].includes(normalized)) return 'Yes';
  if (['no', 'false', 'negative', 'missing data'].includes(normalized)) return 'No';
  return label; // Unrecognized labels still require server review.
}

export default function FieldConditionEditor({ config, onChange }) {
  const [editing, setEditing] = useState(false);
  const fieldValid = typeof config?.field === 'string' && (STORED_FIELDS.includes(config.field) || /^custom_variables\.[A-Za-z_][A-Za-z0-9_]{0,99}$/.test(config.field));
  const compare = config?.operator !== 'has_value';
  const keys = compare ? ['condition_contract_version', 'field', 'operator', 'value_type', 'value'] : ['condition_contract_version', 'field', 'operator'];
  const strict = fieldValid && Object.keys(config).length === keys.length && keys.every((key) => Object.hasOwn(config, key))
    && (!compare || (config.value_type === 'text' && typeof config.value === 'string' && config.value.length <= 1000
      || !STORED_FIELDS.includes(config.field) && (config.value_type === 'boolean' && typeof config.value === 'boolean'
        || config.value_type === 'number' && typeof config.value === 'number' && Number.isFinite(config.value) && Math.abs(config.value) <= Number.MAX_SAFE_INTEGER)));
  if (!config || Array.isArray(config) || config.condition_contract_version !== 1 || typeof config.field !== 'string'
    || !['has_value', 'equals', 'not_equals'].includes(config.operator)
    || !editing && !strict
    || config.operator !== 'has_value' && (!['text', 'number', 'boolean'].includes(config.value_type) || !['string', 'number', 'boolean'].includes(typeof config.value))) return <div>
    <p>These older field settings need an explicit review before they can run.</p>
    <button type="button" onClick={() => { setEditing(true); onChange({ ...DEFAULT_FIELD_CONDITION }); }}>Set up stored-field condition</button>
  </div>;
  const custom = config.field?.startsWith('custom_variables.');
  const update = (changes) => {
    setEditing(true);
    const next = { ...config, ...changes };
    if (next.operator === 'has_value') { delete next.value; delete next.value_type; }
    else if (!next.value_type) { next.value_type = 'text'; next.value = ''; }
    onChange(next);
  };
  return <div className="space-y-3">
    <p className="text-xs text-gray-600">Checks the stored contact value when this step runs. Missing or mismatched comparison data requires review. Field presence does not verify an email or LinkedIn connection.</p>
    <label className="block text-sm">Contact field<select className={style} aria-label="Condition contact field" value={custom ? 'custom' : config.field} onChange={(e) => update({ field: e.target.value === 'custom' ? 'custom_variables.column' : e.target.value, ...(e.target.value !== 'custom' && config.operator !== 'has_value' ? { value_type: 'text', value: '' } : {}) })}>
      {STORED_FIELDS.map((name) => <option key={name} value={name}>{name.replace(/_/g, ' ')}</option>)}<option value="custom">Custom column</option>
    </select></label>
    {custom && <label className="block text-sm">Custom column key<input className={style} aria-label="Condition custom column key" maxLength={100} value={config.field.slice(17)} onChange={(e) => update({ field: `custom_variables.${e.target.value}` })} /><span className="text-xs text-gray-500">Use the exact key: letters, numbers and underscores, starting with a letter or underscore. Other imported headers need explicit mapping.</span></label>}
    <label className="block text-sm">Check<select className={style} aria-label="Condition operator" value={config.operator} onChange={(e) => update({ operator: e.target.value })}>
      <option value="has_value">Has a value</option><option value="equals">Equals</option><option value="not_equals">Does not equal</option>
    </select></label>
    {config.operator !== 'has_value' && <>
      <label className="block text-sm">Value type<select className={style} aria-label="Condition comparison type" value={config.value_type} onChange={(e) => update({ value_type: e.target.value, value: e.target.value === 'boolean' ? false : e.target.value === 'number' ? 0 : '' })}>
        <option value="text">Text</option>{custom && <><option value="number">Number</option><option value="boolean">True / false</option></>}
      </select></label>
      <label className="block text-sm">Compare with{config.value_type === 'boolean' ? <select className={style} aria-label="Condition comparison value" value={String(config.value)} onChange={(e) => update({ value: e.target.value === 'true' })}><option value="false">False</option><option value="true">True</option></select>
        : config.value_type === 'number' ? <ConditionNumberInput className={style} aria-label="Condition comparison value" maxLength={1000} value={config.value} onChange={(value) => update({ value })} />
          : <input className={style} aria-label="Condition comparison value" maxLength={1000} value={config.value ?? ''} onChange={(e) => update({ value: e.target.value })} />}</label>
      <p className="text-xs text-gray-500">Text matches exactly, including case and spaces. CSV custom values stay text; “0” and “false” are not numbers or booleans.</p>
    </>}
  </div>;
}
