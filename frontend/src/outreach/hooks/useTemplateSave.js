import { useEffect, useRef, useState } from 'react';
import { readReferences, storeReference, clearReference, TemplateReferenceError } from '../utils/templateSaveReferences';

const HEX = /^[0-9a-f]{64}$/;
const RECEIPT_KEYS = ['contract_version', 'workspace_id', 'request_id', 'scope_digest', 'input_digest',
  'status', 'template_id', 'template_revision', 'template_identity_digest', 'template_review_digest'];
const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));

export function validSaveContext(value) {
  return exactKeys(value, ['contract_version', 'workspace_id', 'scope_digest', 'execution_authorized'])
    && value.contract_version === 1 && value.execution_authorized === false
    && typeof value.workspace_id === 'string' && value.workspace_id.trim().length > 0
    && value.workspace_id.length <= 200 && typeof value.scope_digest === 'string' && HEX.test(value.scope_digest);
}

export function validSaveReceipt(value, reference) {
  return exactKeys(value, RECEIPT_KEYS) && ['contract_version', 'workspace_id', 'request_id', 'scope_digest', 'input_digest']
    .every((key) => value[key] === reference[key]) && value.status === 'saved' && value.template_revision === 1
    && typeof value.template_id === 'string' && /^tpl_custom_[0-9a-f]{10}$/.test(value.template_id)
    && typeof value.template_identity_digest === 'string' && HEX.test(value.template_identity_digest)
    && typeof value.template_review_digest === 'string' && HEX.test(value.template_review_digest);
}

export async function templateInputDigest(content) {
  const bytes = new TextEncoder().encode(content);
  if (!bytes.length || bytes.length > 1048576) throw new Error('Template is too large to save.');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

const unknownMessage = 'Template save is unconfirmed. Check its original save status before saving again. Recovery references are retained in this browser tab when its storage is available.';
const token = () => localStorage.getItem('token');
const headers = () => ({ 'Content-Type': 'application/json', Authorization: token() ? `Bearer ${token()}` : '' });

export default function useTemplateSave(scopeKey) {
  const [state, setState] = useState(() => {
    try { return readReferences().length ? { phase: 'recovery', message: 'This tab has saved template request references. Check save status before saving again.' } : { phase: 'idle', message: '' }; }
    catch (error) { return { phase: 'storage_error', message: error.message }; }
  });
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const reference = useRef(null);
  const key = useRef(scopeKey); key.current = scopeKey;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const current = (capturedKey, capturedToken) => mounted.current && key.current === capturedKey && token() === capturedToken;
  const hold = () => { if (mounted.current) setState({ phase: 'unknown', message: unknownMessage }); };
  const confirm = (original) => {
    clearReference(original);
    reference.current = null;
    setState({ phase: 'saved', message: 'Original template save confirmed. This confirms its creation; later edits or deletion are separate.' });
  };

  const save = async (prepare) => {
    if (inFlight.current || reference.current || ['recovery','storage_error'].includes(state.phase)) return;
    inFlight.current = true;
    const capturedKey = key.current; const capturedToken = token();
    let submitted = false;
    setState({ phase: 'preparing', message: 'Preparing template save…' });
    try {
      const contextResponse = await fetch('/api/v1/outreach/sequences/template-saves/context', { credentials: 'include', headers: headers() });
      const context = await contextResponse.json();
      if (contextResponse.status !== 200 || contextResponse.ok !== true || !validSaveContext(context)) throw new Error('Template saving is unavailable. Please try again.');
      if (!current(capturedKey, capturedToken)) return;
      const existing = readReferences().find(item => item.scope_digest === context.scope_digest);
      if (existing) {
        if (existing.workspace_id !== context.workspace_id) throw new TemplateReferenceError('Saved template request scope needs review.');
        reference.current = existing; hold(); return;
      }
      const assertCurrent = () => {
        if (!current(capturedKey, capturedToken)) throw new Error('Template preparation stopped because the account or campaign changed.');
      };
      const content = JSON.stringify(await prepare(assertCurrent));
      if (!current(capturedKey, capturedToken)) return;
      const inputDigest = await templateInputDigest(content);
      if (!current(capturedKey, capturedToken)) return;
      const requestId = globalThis.crypto.randomUUID();
      const original = { contract_version: 1, workspace_id: context.workspace_id, scope_digest: context.scope_digest,
        request_id: requestId, input_digest: inputDigest };
      // Retain references only; status recovery never replays graph content.
      // Final synchronous admission after every preparation/hash await.
      storeReference(original);
      reference.current = original;
      submitted = true;
      setState({ phase: 'pending', message: 'Saving template…' });
      const response = await fetch('/api/v1/outreach/sequences/template-saves', { method: 'POST', credentials: 'include',
        headers: headers(), body: JSON.stringify({ ...original, content_json: content }) });
      const receipt = await response.json();
      if (!current(capturedKey, capturedToken) || response.status !== 200 || response.ok !== true || !validSaveReceipt(receipt, original)) { hold(); return; }
      confirm(original);
    } catch (error) {
      if (submitted) hold();
      else if (current(capturedKey, capturedToken)) setState({ phase: error instanceof TemplateReferenceError ? 'storage_error' : 'idle', message: error.message || 'Template could not be prepared.' });
    } finally {
      inFlight.current = false;
      if (!submitted && mounted.current && !current(capturedKey, capturedToken)) setState({ phase: 'idle', message: 'Template preparation stopped because the account or campaign changed.' });
    }
  };

  const check = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const capturedKey = key.current; const capturedToken = token();
    setState({ phase: 'checking', message: 'Checking original template save…' });
    try {
      const contextResponse = await fetch('/api/v1/outreach/sequences/template-saves/context', { credentials: 'include', headers: headers() });
      const context = await contextResponse.json();
      if (!current(capturedKey, capturedToken) || contextResponse.status !== 200 || contextResponse.ok !== true || !validSaveContext(context)) { hold(); return; }
      const original = readReferences().find(item => item.scope_digest === context.scope_digest)
        || (reference.current?.scope_digest === context.scope_digest ? reference.current : null);
      if (!original) {
        // Preserve a retained original if external storage clearing occurred
        // before the user explicitly reviewed another account/workspace.
        if (reference.current) storeReference(reference.current);
        reference.current = null;
        setState({ phase: 'idle', message: 'No recovery reference matches this account and workspace. Other saved references remain in this tab.' });
        return;
      }
      if (original.workspace_id !== context.workspace_id) throw new TemplateReferenceError('Saved template request scope needs review.');
      reference.current = original;
      const params = new URLSearchParams({ workspace_id: original.workspace_id, scope_digest: original.scope_digest });
      const response = await fetch(`/api/v1/outreach/sequences/template-saves/${encodeURIComponent(original.request_id)}?${params}`,
        { credentials: 'include', headers: headers() });
      const receipt = await response.json();
      if (!current(capturedKey, capturedToken) || response.status !== 200 || response.ok !== true || !validSaveReceipt(receipt, original)) { hold(); return; }
      confirm(original);
    } catch (error) {
      if (mounted.current && error instanceof TemplateReferenceError) setState({ phase: 'storage_error', message: error.message });
      else hold();
    }
    finally { inFlight.current = false; }
  };

  return { ...state, save, check, blocked: ['preparing', 'pending', 'unknown', 'checking', 'recovery', 'storage_error'].includes(state.phase),
    canCheck: ['unknown', 'recovery', 'storage_error'].includes(state.phase) };
}
