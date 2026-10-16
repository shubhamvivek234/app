import React, { useEffect, useRef, useState } from 'react';
import { flattenTreeToDAG } from './sequenceGraph';
import ConditionSamples from './ConditionSamples';

const field = 'w-full rounded-lg border border-gray-200 bg-white p-2 text-sm';
const WAIT = ['connection_request', 'if_connected', 'send_message', 'voice_note'];
const LABELS = { yes: 'Yes — assumed observation', no: 'No — before deadline', unknown: 'Unknown', deadline_no: 'No — at deadline', deadline_unknown: 'Unknown — at deadline' };
const STATUSES = { evaluated_branch: 'Branch from supplied field value', terminal_condition: 'No successor path saved', would_attempt: 'Would attempt; outcome unverified', connection_required: 'Connection required', already_connected: 'Already connected — no invitation', usable_email_required: 'Usable email required', sample_variables_missing: 'Sample variables missing', needs_review: 'Needs review', waiting_for_observation: 'Waiting for an observation', waiting_for_deadline: 'Waiting for the condition deadline', stopped_on_reply: 'Stopped on reply', assumed_branch: 'Assumed branch' };
const ENDINGS = { finished: 'Illustrated path ends here', invalid_graph: 'Fix sequence validation errors', await_action_outcome: 'Awaiting an action outcome', ...STATUSES };
function validReport(report, request) {
  const ids = new Set(request.nodes.map((node) => node.id));
  return report?.request_id === request.request_id && report.request_scope === request.request_scope && report.contract_version === 1 && typeof report.valid === 'boolean'
    && report.execution_authorized === false && report.provider_outcomes_verified === false
    && typeof report.input_digest === 'string' && /^[0-9a-f]{64}$/.test(report.input_digest)
    && typeof report.graph_digest === 'string' && /^[0-9a-f]{64}$/.test(report.graph_digest)
    && typeof report.ending === 'string' && Object.hasOwn(ENDINGS, report.ending)
    && Array.isArray(report.issues) && report.issues.length <= 100 && report.issues.every((issue) => issue && ids.has(issue.node_id) && ['error', 'warning'].includes(issue.severity) && typeof issue.message === 'string')
    && Array.isArray(report.steps) && report.steps.length <= 100 && new Set(report.steps.map((step) => step?.node_id)).size === report.steps.length
    && report.steps.every((step) => step && ids.has(step.node_id) && request.nodes.find((node) => node.id === step.node_id).type === step.type
      && (step.status !== 'evaluated_branch' || step.type === 'has_data_in_column' && ['positive', 'negative'].includes(step.branch)) && Object.hasOwn(STATUSES, step.status) && Number.isInteger(step.configured_delay_hours) && step.configured_delay_hours >= 0 && step.configured_delay_hours <= 8760
      && (!step.content || (typeof step.content === 'object' && !Array.isArray(step.content) && Object.values(step.content).every((value) => value && typeof value.text === 'string' && value.text.length <= 2000 && typeof value.truncated === 'boolean'))))
    && Number.isInteger(report.configured_delay_hours) && report.configured_delay_hours >= 0
    && Number.isInteger(report.assumed_wait_hours) && report.assumed_wait_hours >= 0;
}
export default function SequenceReview({ tree, campaignId, onClose }) {
  const [sample, setSample] = useState({ first_name: '', last_name: '', company_name: '', job_title: '', headline: '', industry: '', location: '', location_raw: '', email: '' });
  const [custom, setCustom] = useState('{}');
  const [conditionValues, setConditionValues] = useState({});
  const [conditionErrors, setConditionErrors] = useState({});
  const [observations, setObservations] = useState({});
  const [connected, setConnected] = useState('unknown');
  const [email, setEmail] = useState('unknown');
  const [complete, setComplete] = useState(false);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [scope, setScope] = useState(null);
  const [contextError, setContextError] = useState('');
  const version = useRef(0);
  const controller = useRef(null);
  const invalidate = () => { ++version.current; controller.current?.abort(); setReport(null); setError(''); setBusy(false); };
  useEffect(() => { invalidate(); setObservations({}); return () => { ++version.current; controller.current?.abort(); }; }, [tree, campaignId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const contextController = new AbortController(); setScope(null); setContextError('');
    const token = localStorage.getItem('token');
    fetch('/api/v1/outreach/sequences/preview-context', { credentials: 'include', signal: contextController.signal, headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(async (response) => { const data = await response.json();
        if (!response.ok || data?.contract_version !== 1 || typeof data.request_scope !== 'string' || !/^[0-9a-f]{64}$/.test(data.request_scope)) throw new Error('Could not confirm preview account and workspace. Reopen the review.');
        if (!contextController.signal.aborted) setScope(data.request_scope);
      }).catch((failure) => { if (!contextController.signal.aborted) setContextError(failure.message); });
    return () => contextController.abort();
  }, [campaignId]);
  let graph, graphError;
  try { graph = flattenTreeToDAG(tree); } catch (failure) { graphError = failure.message; }
  const conditionFields = [...new Set((graph?.nodes || []).filter((node) => node.type === 'has_data_in_column' && typeof node.config?.field === 'string').map((node) => node.config.field))];
  const watched = graph?.nodes.filter((node) => node.type === 'if_connected' || node.type === 'if_email_available' || WAIT.includes(node.type) && graph.edges.some((edge) => edge.source === node.id && edge.label));
  const run = async () => {
    if (!graph || busy || !scope) return;
    invalidate();
    const current = version.current;
    setBusy(true);
    try {
      if (conditionFields.some((name) => conditionErrors[name])) throw new Error('Enter complete, finite field-sample numbers within the safe range, or choose a different value type.');
      const variables = JSON.parse(custom);
      if (!variables || typeof variables !== 'object' || Array.isArray(variables) || Object.keys(variables).length > 50 || Object.values(variables).some((value) => typeof value !== 'string')) throw new Error('Custom variables must be an object with up to 50 text values.');
      if (typeof window.crypto?.randomUUID !== 'function') throw new Error('This browser cannot bind a fresh preview request.');
      const request = { ...graph, tree, request_scope: scope, request_id: window.crypto.randomUUID(), sample: { ...sample, custom_variables: variables }, condition_values: conditionValues, observations,
        initial_connected: connected, initial_email_available: email, assume_action_completion: complete };
      const token = localStorage.getItem('token');
      controller.current = new AbortController();
      const response = await fetch('/api/v1/outreach/sequences/preview', { method: 'POST', credentials: 'include', signal: controller.current.signal,
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(request) });
      const result = await response.json();
      if (current !== version.current) return;
      if (!response.ok) throw new Error(typeof result?.detail === 'string' ? result.detail : 'Preview is unavailable. Check your sequence and sample fields.');
      if (!validReport(result, request)) throw new Error('Could not confirm this preview. Generate a fresh report.');
      setReport(result);
    } catch (failure) { if (current === version.current) setError(failure.message); }
    finally { if (current === version.current) setBusy(false); }
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="Sequence validation and preview" onClick={(event) => event.stopPropagation()}>
    <div className="max-h-[90vh] w-full max-w-3xl space-y-4 overflow-auto rounded-2xl bg-white p-6 text-gray-900 shadow-xl">
      <div className="flex justify-between gap-4"><h2 className="text-xl font-semibold">Sequence validation & preview</h2><button type="button" onClick={onClose}>Close sequence preview</button></div>
      <p className="text-sm text-gray-600">This illustrates a path using supplied sample values and assumptions. It sends nothing and verifies no provider outcome. Sending still requires current access, consent, review and execution checks.</p>
      <div className="grid grid-cols-2 gap-3">{Object.entries(sample).map(([key, value]) => <label key={key} className="text-sm">{key.replace(/_/g, ' ')}<input className={field} aria-label={`Sequence sample ${key}`} maxLength={1000} value={value} onChange={(event) => { invalidate(); setSample((prior) => ({ ...prior, [key]: event.target.value })); }} /></label>)}</div>
      <label className="block text-sm">Custom sample variables (JSON text values)<textarea aria-label="Sequence custom sample variables" className={field} rows={2} maxLength={10000} value={custom} onChange={(event) => { invalidate(); setCustom(event.target.value); }} /></label>
      <ConditionSamples fields={conditionFields} values={conditionValues} onChange={(values, errors) => { invalidate(); setConditionValues(values); setConditionErrors(errors); }} />
      <div className="grid grid-cols-2 gap-3">{[['Existing connection assumption', connected, setConnected], ['Usable, unsuppressed email assumption', email, setEmail]].map(([label, value, setter]) => <label className="text-sm" key={label}>{label}<select className={field} aria-label={label} value={value} onChange={(event) => { invalidate(); setter(event.target.value); }}><option value="unknown">Unknown</option><option value="yes">Yes — assumed</option><option value="no">No — assumed</option></select></label>)}</div>
      <label className="block text-sm"><input aria-label="Assume successful action completion" type="checkbox" checked={complete} onChange={(event) => { invalidate(); setComplete(event.target.checked); }} /> Assume actions complete successfully to illustrate continuation</label>
      <p className="text-xs text-gray-500">Without that assumption, the preview stops at the first action outcome. An invitation does not establish a connection, and an email address does not establish usable-email permission.</p>
      <div className="space-y-2">{watched?.map((node) => <label key={node.id} className="block text-sm">{node.title || node.type} ({node.id})<select className={field} aria-label={`Assumed observation ${node.id}`} value={observations[node.id] || 'unknown'} onChange={(event) => { invalidate(); setObservations((prior) => ({ ...prior, [node.id]: event.target.value })); }}>
        {Object.entries(LABELS).filter(([value]) => node.type !== 'if_email_available' || ['yes', 'no', 'unknown'].includes(value)).map(([value, label]) => <option key={value} value={value}>{node.type === 'if_email_available' && value === 'no' ? 'No — usable-email policy check' : label}</option>)}
      </select></label>)}</div>
      {!scope && !contextError && <p role="status">Checking preview account and workspace…</p>}
      {(error || graphError || contextError) && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error || graphError || contextError}</p>}
      <button type="button" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || !graph || !scope} onClick={run}>{busy ? 'Checking sequence…' : 'Validate & preview path'}</button>
      {report && <div className="space-y-3" aria-label="Sequence preview result">
        <p className={`font-semibold ${report.valid ? 'text-gray-900' : 'text-red-700'}`}>{report.valid ? 'Graph checks passed; execution is not authorized' : 'Sequence needs correction'}</p>
        <ul className="space-y-1 text-sm">{report.issues.map((issue, index) => <li key={index}>{issue.severity === 'error' ? 'Fix' : 'Review'} · {issue.node_id}: {issue.message}</li>)}</ul>
        <ol className="space-y-3">{report.steps.map((step) => <li key={step.node_id} className="rounded-lg border border-gray-200 p-3 text-sm">
          <strong>{step.node_id}</strong> · {STATUSES[step.status]}<p>Configured delay: {step.configured_delay_hours} hours</p>
          {step.status === 'evaluated_branch' && <p>Chosen path: {step.branch === 'positive' ? 'Yes' : 'No'}. This is a sample field decision.</p>}
          {step.assumed_completion && <p>Successful completion is assumed for this illustration.</p>}
          {step.assumed_observation && <p>Supplied observation: {LABELS[step.assumed_observation]}</p>}
          {Array.isArray(step.missing_variables) && step.missing_variables.every((value) => typeof value === 'string') && <p>Missing sample variables: {step.missing_variables.join(', ')}</p>}
          {Object.entries(step.content || {}).map(([key, value]) => <div key={key}><p className="mt-2 font-medium">{key}</p><p className="whitespace-pre-wrap break-words">{value.text}</p>{value.truncated && <p>Only the first 2,000 characters are shown.</p>}</div>)}
        </li>)}</ol>
        <p className="font-medium">{ENDINGS[report.ending]}</p><p className="text-xs text-gray-500">Configured path delays: {report.configured_delay_hours} hours. Assumed deadline waits: {report.assumed_wait_hours} hours. Actual scheduling, limits and runtime checks can defer work further.</p>
      </div>}
    </div>
  </div>;
}
