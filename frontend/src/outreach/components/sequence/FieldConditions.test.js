import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import FieldConditionEditor, { DEFAULT_FIELD_CONDITION, conditionBranchLabel } from './FieldConditionEditor';
import ConditionSamples from './ConditionSamples';

const change = async (el, value) => act(async () => {
  const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});
let container, root, latest;
beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); latest = null; });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
function Editor({ initial }) { const [config, setConfig] = useState(initial); latest = config; return <FieldConditionEditor config={config} onChange={setConfig} />; }
function Samples({ fields }) { const [values, setValues] = useState({}); latest = values; return <ConditionSamples fields={fields} values={values} onChange={setValues} />; }
const label = (name) => container.querySelector(`[aria-label="${name}"]`);

it.each([{}, { condition_contract_version: 1, field: [] }, { ...DEFAULT_FIELD_CONDITION, timeout_days: 3 }, { ...DEFAULT_FIELD_CONDITION, field: 'secret' }, { ...DEFAULT_FIELD_CONDITION, operator: 'equals', value_type: 'boolean', value: false }])('requires explicit repair for malformed or older settings %p', async (initial) => {
  await act(async () => root.render(<Editor initial={initial} />));
  expect(container.textContent).toContain('explicit review');
  await act(async () => container.querySelector('button').click());
  expect(latest).toEqual(DEFAULT_FIELD_CONDITION);
});

it('keeps scalar comparisons explicit, preserves decimal typing and removes irrelevant comparison settings', async () => {
  await act(async () => root.render(<Editor initial={DEFAULT_FIELD_CONDITION} />));
  await change(label('Condition contact field'), 'custom');
  await change(label('Condition custom column key'), '');
  await change(label('Condition custom column key'), 'score');
  await change(label('Condition operator'), 'equals');
  await change(label('Condition comparison type'), 'number');
  for (const value of ['1', '1.', '1.5']) { await change(label('Condition comparison value'), value); expect(label('Condition comparison value').value).toBe(value); }
  expect(latest.value).toBe(1.5);
  await change(label('Condition comparison type'), 'boolean');
  expect(latest.value).toBe(false);
  await change(label('Condition operator'), 'has_value');
  expect(latest).toEqual({ condition_contract_version: 1, field: 'custom_variables.score', operator: 'has_value' });
});

it.each(['__proto__', 'constructor', 'score'])('preserves literal custom sample key %s with false/0/null/missing', async (key) => {
  const field = `custom_variables.${key}`;
  await act(async () => root.render(<Samples fields={[field]} />));
  await change(label(`Condition sample type ${field}`), 'boolean');
  expect(JSON.parse(JSON.stringify(latest)).custom_variables[key]).toBe(false);
  await change(label(`Condition sample type ${field}`), 'number');
  expect(JSON.parse(JSON.stringify(latest)).custom_variables[key]).toBe(0);
  for (const value of ['1', '1.', '1.5']) await change(label(`Condition sample value ${field}`), value);
  expect(latest.custom_variables[key]).toBe(1.5);
  await change(label(`Condition sample type ${field}`), 'null');
  expect(latest.custom_variables[key]).toBe(null);
  await change(label(`Condition sample type ${field}`), 'missing');
  expect(Object.hasOwn(latest.custom_variables, key)).toBe(false);
});

it('canonicalizes branch meanings independently of left/right positions', () => {
  expect(conditionBranchLabel('has data')).toBe('Yes');
  expect(conditionBranchLabel('missing data')).toBe('No');
  expect(conditionBranchLabel('No')).toBe('No');
  expect(conditionBranchLabel('unproven')).toBe('unproven');
});
