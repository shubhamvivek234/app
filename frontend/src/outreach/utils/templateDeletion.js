// This metadata correlates one destructive request; it grants no authority.
const digest = (value) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export function reviewedTemplateDeletion(template) {
  const review = template?.deletion_review;
  if (template?.is_custom !== true || typeof template.id !== 'string' || !/^tpl_custom_[a-f0-9]{10}$/.test(template.id)
    || review?.contract_version !== 1 || review.reviewable !== true
    || review.deletion_authorized !== false || review.execution_authorized !== false
    || !Number.isSafeInteger(review.revision) || review.revision < 0
    || typeof review.workspace_id !== 'string' || !review.workspace_id.trim() || review.workspace_id.length > 200
    || !digest(review.review_digest) || !digest(review.identity_digest) || !digest(review.scope_digest)) return null;
  return { contract_version: 1, workspace_id: review.workspace_id, revision: review.revision,
    review_digest: review.review_digest, identity_digest: review.identity_digest, scope_digest: review.scope_digest };
}

export function matchesTemplateDeletionReceipt(receipt, templateId, captured) {
  if (!receipt || Array.isArray(receipt) || typeof receipt !== 'object') return false;
  const expected = { ...captured, status: 'deleted', template_id: templateId };
  return Object.keys(receipt).length === Object.keys(expected).length
    && Object.entries(expected).every(([key, value]) => receipt[key] === value);
}
