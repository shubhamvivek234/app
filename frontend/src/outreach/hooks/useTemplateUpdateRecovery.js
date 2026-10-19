import { useCallback, useEffect, useRef, useState } from 'react';
import { validSaveContext } from './useTemplateSave';

const token = () => localStorage.getItem('token');

export default function useTemplateUpdateRecovery(viewKey, onConfirmed, contract) {
  const { readReferences, storeReference, clearReference } = contract.references;
  const noun = contract.noun || `${contract.label} update`;
  const held = `A saved ${noun} needs checking. Check its original status before changing or using templates.`;
  const initial = useCallback(() => {
    try { return readReferences().length ? { blocked: true, message: held } : { blocked: false, message: '' }; }
    catch (error) { return { blocked: true, message: error.message }; }
  }, [held, readReferences]);
  const [state, setState] = useState(initial);
  const mounted = useRef(false), checking = useRef(false), retained = useRef(null), reviewed = useRef(null);
  const view = useRef({ key: viewKey });
  if (view.current.key !== viewKey) view.current = { key: viewKey };
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { reviewed.current = null; setState(initial()); }, [viewKey, initial]);

  const restoreMissingReference = () => {
    const refs = readReferences();
    // Another mounted view may have confirmed A and admitted B. Preserve B;
    // only reconstruct our retained locator when its scope is actually absent.
    if (retained.current && !refs.some(ref => ref.scope_digest === retained.current.scope_digest)) storeReference(retained.current);
  };

  // This synchronous guard also catches references written since the last render.
  const allowAction = () => {
    if (checking.current) return false;
    try {
      restoreMissingReference();
      const refs = readReferences();
      const allowed = reviewed.current?.view === view.current && reviewed.current.token === token();
      if (!refs.length || allowed && !refs.some(ref => ref.scope_digest === reviewed.current.context.scope_digest)) return true;
      setState({ blocked: true, message: held });
    } catch (error) { setState({ blocked: true, message: error.message }); }
    return false;
  };

  const check = async () => {
    if (checking.current) return;
    checking.current = true;
    const capturedView = view.current, capturedToken = token();
    const current = () => mounted.current && capturedView === view.current && capturedToken === token();
    setState({ blocked: true, checking: true, message: `Checking saved ${noun}…` });
    let confirmed = false;
    try {
      // Validate storage before requesting status; corrupted data never supplies a URL.
      restoreMissingReference();
      readReferences();
      const options = { credentials: 'include', headers: { Authorization: capturedToken ? `Bearer ${capturedToken}` : '' } };
      const contextResponse = await fetch(`${contract.endpoint}/context`, options);
      const context = await contextResponse.json();
      if (!current() || contextResponse.ok !== true || contextResponse.status !== 200 || !validSaveContext(context)) return;
      const original = readReferences().find(ref => ref.scope_digest === context.scope_digest);
      if (!original) {
        reviewed.current = { view: capturedView, token: capturedToken, context };
        // All foreign locators stay in storage. No foreign original-status request.
        retained.current = null;
        confirmed = true;
        setState({ blocked: false, message: `No saved ${noun} matches this account and workspace. Other references remain in this tab.` });
        return;
      }
      if (original.workspace_id !== context.workspace_id) return;
      retained.current = original;
      const params = new URLSearchParams({ workspace_id: original.workspace_id,
        scope_digest: original.scope_digest, input_digest: original.input_digest });
      const response = await fetch(`${contract.endpoint}/${encodeURIComponent(original.request_id)}?${params}`, options);
      const receipt = await response.json();
      if (!current() || response.ok !== true || response.status !== 200 || !contract.validReceipt(receipt, original)) return;
      clearReference(original);
      if (!current()) return;
      retained.current = null;
      reviewed.current = { view: capturedView, token: capturedToken, context };
      confirmed = true;
      setState({ blocked: false, message: contract.confirmation || 'Original template update confirmed. Reloading current templates…' });
      onConfirmed(original, receipt);
    } catch { /* Corruption, unknown status or cleanup failure retain the hold. */ }
    finally {
      checking.current = false;
      if (mounted.current && !confirmed) setState({ blocked: true, message: held });
    }
  };
  return { ...state, allowAction, check };
}
