import { validReference, sameReference } from './templateSaveReferences';

// Separate immutable module configurations share the same bounded locator rules.
export function createTemplateReferenceStore(STORAGE_KEY, ReferenceErrorType, message) {
  const unavailable = () => new ReferenceErrorType(message);
  const target = storage => storage || window.sessionStorage;
  
  function readReferences(storage) {
    try {
      const raw = target(storage).getItem(STORAGE_KEY);
      if (raw === null) return [];
      if (typeof raw !== 'string' || raw.length > 8192) throw unavailable();
      const value = JSON.parse(raw);
      if (!value || Array.isArray(value) || Object.keys(value).length !== 2
        || value.contract_version !== 1 || !Array.isArray(value.references) || value.references.length > 10
        || !value.references.every(validReference)
        || new Set(value.references.map(ref => ref.scope_digest)).size !== value.references.length
        || new Set(value.references.map(ref => ref.request_id)).size !== value.references.length) throw unavailable();
      return value.references;
    } catch { throw unavailable(); }
  }
  
  function writeReferences(refs, storage) {
    const raw = JSON.stringify({ contract_version: 1, references: refs });
    if (raw.length > 8192) throw unavailable();
    storage.setItem(STORAGE_KEY, raw);
    if (storage.getItem(STORAGE_KEY) !== raw) throw unavailable();
  }
  
  function storeReference(ref, storage) {
    try {
      if (!validReference(ref)) throw unavailable();
      const destination = target(storage), refs = readReferences(destination);
      const existing = refs.find(item => item.scope_digest === ref.scope_digest);
      if (existing) { if (!sameReference(existing, ref)) throw unavailable(); return; }
      if (refs.length === 10 || refs.some(item => item.request_id === ref.request_id)) throw unavailable();
      writeReferences([...refs, ref], destination);
    } catch { throw unavailable(); }
  }
  
  function clearReference(ref, storage) {
    try {
      if (!validReference(ref)) throw unavailable();
      const destination = target(storage), refs = readReferences(destination);
      const existing = refs.find(item => item.scope_digest === ref.scope_digest);
      if (existing && !sameReference(existing, ref)) throw unavailable();
      if (existing) writeReferences(refs.filter(item => !sameReference(item, ref)), destination);
      if (readReferences(destination).some(item => item.scope_digest === ref.scope_digest)) throw unavailable();
    } catch { throw unavailable(); }
  }
  
  return Object.freeze({ readReferences, storeReference, clearReference });
}
