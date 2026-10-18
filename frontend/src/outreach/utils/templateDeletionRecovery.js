import { templateInputDigest } from '../hooks/useTemplateSave';

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
