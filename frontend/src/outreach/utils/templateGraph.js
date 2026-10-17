import { flattenTreeToDAG } from '../components/sequence/sequenceGraph';
const digest = value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);

export function browserGraphValues(value) {
  const pending=[[value,0]];let items=0;
  while(pending.length){
    const [current,depth]=pending.pop();
    if(++items>20000 || depth>12)return false;
    if(typeof current==='number') {if(!Number.isFinite(current)||Math.abs(current)>Number.MAX_SAFE_INTEGER)return false;}
    else if(current!==null && typeof current==='object'){
      if(!Array.isArray(current) && Object.getPrototypeOf(current)!==Object.prototype)return false;
      const entries=Object.entries(current);
      if(items+pending.length+entries.length>20000)return false;
      for(const [key,item]of entries){if(key.length>200||key.includes('\0'))return false;pending.push([item,depth+1]);}
    } else if(current!==null && !['boolean','string'].includes(typeof current))return false;
  }
  return true;
}

export function reviewedTemplateGraph(template) {
  const review=template?.graph_review;
  if(template?.is_custom!==true || typeof template.id!=='string' || !/^tpl_custom_[a-f0-9]{10}$/.test(template.id)
    || review?.contract_version!==1 || review.reviewable!==true || review.update_authorized!==false || review.execution_authorized!==false
    || !Number.isSafeInteger(review.revision) || review.revision<0 || review.revision>=Number.MAX_SAFE_INTEGER
    || typeof review.workspace_id!=='string' || !review.workspace_id.trim() || review.workspace_id.length>200
    || !digest(review.review_digest) || !digest(review.identity_digest) || !digest(review.scope_digest)
    || !Array.isArray(template.tree) || !template.tree.length
    || !browserGraphValues({nodes:template.nodes,edges:template.edges,tree:template.tree})) return null;
  try {flattenTreeToDAG(template.tree);} catch {return null;}
  return {contract_version:1,workspace_id:review.workspace_id,revision:review.revision,
    review_digest:review.review_digest,identity_digest:review.identity_digest,scope_digest:review.scope_digest};
}

export function matchesTemplateGraphReceipt(receipt, templateId, captured) {
  if(!receipt || Array.isArray(receipt) || typeof receipt!=='object' || !digest(receipt.new_review_digest) || !digest(receipt.graph_digest)) return false;
  const expected={...captured,status:'updated',template_id:templateId,new_revision:captured.revision+1,
    new_review_digest:receipt.new_review_digest,graph_digest:receipt.graph_digest};
  delete expected.graph_json;
  return Object.keys(receipt).length===Object.keys(expected).length && Object.entries(expected).every(([key,value])=>receipt[key]===value);
}
