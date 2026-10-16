import React, { useState } from 'react';
import ConditionNumberInput from './ConditionNumberInput';
const style = 'w-full rounded-lg border border-gray-200 bg-white p-2 text-sm';

export default function ConditionSamples({ fields, values, onChange }) {
  const [types, setTypes] = useState({});
  const [invalid, setInvalid] = useState({});
  const setValue = (field, value, remove = false, expectedType = null) => {
    const next = { ...values };
    if (field.startsWith('custom_variables.')) {
      const key = field.slice(17); next.custom_variables = { ...next.custom_variables };
      if (remove) delete next.custom_variables[key]; else next.custom_variables = { ...next.custom_variables, [key]: value };
    } else if (remove) delete next[field]; else next[field] = value;
    const errors = { ...invalid };
    if (expectedType === 'number' && (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER)) errors[field] = true;
    else delete errors[field];
    setInvalid(errors);
    onChange(next, errors);
  };
  if (!fields.length) return null;
  return <div className="space-y-3" aria-label="Stored-field condition samples">
    <p className="text-sm">Field-check samples are separate from message variables. These supplied values illustrate a decision; they do not read or change contacts.</p>
    {fields.map((field) => {
      const custom = field.startsWith('custom_variables.');
      const source = custom ? values.custom_variables || {} : values;
      const key = custom ? field.slice(17) : field;
      const value = Object.hasOwn(source, key) ? source[key] : undefined;
      const kind = types[field] || (!Object.hasOwn(source, key) ? 'missing' : value === null ? 'null' : typeof value);
      return <div key={field} className="space-y-1">
        <label className="block text-sm">{field}<select className={style} aria-label={`Condition sample type ${field}`} value={kind} onChange={(e) => { setTypes((prior) => ({ ...prior, [field]: e.target.value })); setValue(field, e.target.value === 'null' ? null : e.target.value === 'boolean' ? false : e.target.value === 'number' ? 0 : '', e.target.value === 'missing'); }}>
          <option value="missing">Missing</option><option value="null">Null</option><option value="string">Text</option>{custom && <><option value="number">Number</option><option value="boolean">True / false</option></>}
        </select></label>
        {kind === 'boolean' ? <select className={style} aria-label={`Condition sample value ${field}`} value={String(value)} onChange={(e) => setValue(field, e.target.value === 'true')}><option value="false">False</option><option value="true">True</option></select>
          : kind === 'number' ? <ConditionNumberInput className={style} aria-label={`Condition sample value ${field}`} maxLength={1000} value={value} onChange={(number) => setValue(field, number, false, 'number')} />
            : kind === 'string' && <input className={style} aria-label={`Condition sample value ${field}`} maxLength={1000} value={value} onChange={(e) => setValue(field, e.target.value)} />}
      </div>;
    })}
  </div>;
}
