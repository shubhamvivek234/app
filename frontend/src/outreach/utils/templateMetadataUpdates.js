// Original-operation receipts establish a historical update, not current content.
const digest=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
export function matchesMetadataUpdateReceipt(receipt,reference,original) {
  if(!receipt || typeof receipt!=='object' || Array.isArray(receipt) || !digest(receipt.new_review_digest))return false;
  const {content_json,...locator}=reference;
  const expected={...locator,status:'updated',template_id:original.template_id,revision:original.revision,
    review_digest:original.review_digest,identity_digest:original.identity_digest,review_scope_digest:original.scope_digest,
    new_revision:original.revision+1,new_review_digest:receipt.new_review_digest};
  return Object.keys(receipt).length===Object.keys(expected).length
    && Object.entries(expected).every(([key,value])=>receipt[key]===value);
}
