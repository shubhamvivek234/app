// Original native/context metadata correlates an edit; current authority is server checked.
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const validMetadataText = (name, description) => typeof name === 'string' && Boolean(name.trim())
  && name.length <= 100 && typeof description === 'string' && description.length <= 1000
  && !/[\u0000\uD800-\uDFFF]/u.test(name.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, ''))
  && !/[\u0000\uD800-\uDFFF]/u.test(description.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, ''));

export function reviewedTemplateMetadata(template) {
  const review = template?.metadata_review;
  if (template?.is_custom !== true || typeof template.id !== 'string' || !/^tpl_custom_[a-f0-9]{10}$/.test(template.id)
    || !validMetadataText(template.name, template.description === undefined ? '' : template.description)
    || review?.contract_version !== 1 || review.reviewable !== true
    || review.update_authorized !== false || review.execution_authorized !== false
    || !Number.isSafeInteger(review.revision) || review.revision < 0 || review.revision >= Number.MAX_SAFE_INTEGER
    || typeof review.workspace_id !== 'string' || !review.workspace_id.trim() || review.workspace_id.length > 200
    || !digest(review.review_digest) || !digest(review.identity_digest) || !digest(review.scope_digest)) return null;
  return {contract_version:1,workspace_id:review.workspace_id,revision:review.revision,
    review_digest:review.review_digest,identity_digest:review.identity_digest,scope_digest:review.scope_digest};
}

export function matchesMetadataReceipt(receipt, templateId, captured) {
  if (!receipt || Array.isArray(receipt) || typeof receipt !== 'object' || !digest(receipt.new_review_digest)) return false;
  const expected = {...captured,status:'updated',template_id:templateId,new_revision:captured.revision+1,
    new_review_digest:receipt.new_review_digest};
  return Object.keys(receipt).length === Object.keys(expected).length
    && Object.entries(expected).every(([key,value])=>receipt[key]===value);
}
