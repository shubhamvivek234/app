import { templateInputDigest } from '../hooks/useTemplateSave';
import { validReference } from './templateSaveReferences';

// A reload retains only a locator. Current authorized GET supplies the native
// historical assertion; the browser cannot reconstruct the deleted row's proof.
export function validHistoricalDeletionReceipt(receipt, reference) {
  return Boolean(validReference(reference) && receipt && typeof receipt === 'object' && !Array.isArray(receipt)
    && Object.keys(receipt).length === 11 && Object.entries(reference).every(([key,value]) => receipt[key] === value)
    && receipt.status === 'deleted' && typeof receipt.template_id === 'string'
    && /^tpl_custom_[0-9a-f]{10}$/.test(receipt.template_id)
    && Number.isSafeInteger(receipt.revision) && receipt.revision >= 0
    && ['review_digest','identity_digest','review_scope_digest'].every(key => typeof receipt[key] === 'string'
      && /^[0-9a-f]{64}$/.test(receipt[key])));
}

// This confirms a historical original deletion, never current catalog absence.
export function matchesDeletionReceipt(receipt, reference, original) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return false;
  const { content_json, ...locator } = reference;
  const expected = { ...locator, status: 'deleted', template_id: original.template_id,
    revision: original.revision, review_digest: original.review_digest,
    identity_digest: original.identity_digest, review_scope_digest: original.scope_digest };
  return Object.keys(receipt).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => receipt[key] === value);
}

export async function deletionInputDigest(content) {
  if (typeof content !== 'string' || !content || new TextEncoder().encode(content).length > 8192) {
    throw new Error('Template deletion review exceeds the supported input bound.');
  }
  return templateInputDigest(content);
}
