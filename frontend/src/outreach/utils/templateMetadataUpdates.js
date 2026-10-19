// Original-operation receipts establish a historical update, not current content.
import { validReference } from './templateSaveReferences';
const digest=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
// After reload only the locator survives. Current authorized status GET supplies
// the historical native proof; it does not establish the current template state.
export function validHistoricalMetadataReceipt(receipt, reference) {
  return Boolean(validReference(reference) && receipt && typeof receipt === 'object' && !Array.isArray(receipt)
    && Object.keys(receipt).length === 13
    && Object.entries(reference).every(([key,value]) => receipt[key] === value)
    && receipt.status === 'updated' && typeof receipt.template_id === 'string'
    && /^tpl_custom_[0-9a-f]{10}$/.test(receipt.template_id)
    && Number.isSafeInteger(receipt.revision) && receipt.revision >= 0 && receipt.revision < Number.MAX_SAFE_INTEGER
    && receipt.new_revision === receipt.revision + 1
    && ['review_digest','identity_digest','review_scope_digest','new_review_digest'].every(key => digest(receipt[key])));
}
export function matchesMetadataUpdateReceipt(receipt,reference,original) {
  if(!receipt || typeof receipt!=='object' || Array.isArray(receipt) || !digest(receipt.new_review_digest))return false;
  const {content_json,...locator}=reference;
  const expected={...locator,status:'updated',template_id:original.template_id,revision:original.revision,
    review_digest:original.review_digest,identity_digest:original.identity_digest,review_scope_digest:original.scope_digest,
    new_revision:original.revision+1,new_review_digest:receipt.new_review_digest};
  return Object.keys(receipt).length===Object.keys(expected).length
    && Object.entries(expected).every(([key,value])=>receipt[key]===value);
}
