// Untrusted, same-tab locators only. Server status remains the authority.
export const STORAGE_KEY = 'unravler.outreach.templateSaveReferences.v1';
const FIELDS = ['contract_version','workspace_id','scope_digest','request_id','input_digest'];
const exactKeys=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)
  &&Object.keys(value).length===keys.length&&keys.every(key=>Object.prototype.hasOwnProperty.call(value,key));
export class TemplateReferenceError extends Error {}
const unavailable=()=>new TemplateReferenceError('Saved template request references need review. Retry recovery before saving again.');
export function validReference(value){
  return Boolean(exactKeys(value,FIELDS)&&value.contract_version===1
    &&typeof value.workspace_id==='string'&&value.workspace_id.trim().length>0&&value.workspace_id.length<=200
    &&['scope_digest','input_digest'].every(key=>typeof value[key]==='string'&&/^[0-9a-f]{64}$/.test(value[key]))
    &&typeof value.request_id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value.request_id));
}
export const sameReference=(a,b)=>validReference(a)&&validReference(b)&&FIELDS.every(key=>a[key]===b[key]);
export function readReferences(storage){
  try{
    const target=storage||window.sessionStorage;const raw=target.getItem(STORAGE_KEY);
    if(raw===null)return [];
    if(typeof raw!=='string'||raw.length>8192)throw unavailable();
    const data=JSON.parse(raw);
    if(!exactKeys(data,['contract_version','references'])||data.contract_version!==1||!Array.isArray(data.references)
      ||data.references.length>10||!data.references.every(validReference)
      ||new Set(data.references.map(ref=>ref.scope_digest)).size!==data.references.length
      ||new Set(data.references.map(ref=>ref.request_id)).size!==data.references.length)throw unavailable();
    return data.references;
  }catch(_){throw unavailable();}
}
function writeReferences(refs,storage){
  const raw=JSON.stringify({contract_version:1,references:refs});
  if(raw.length>8192)throw unavailable();
  storage.setItem(STORAGE_KEY,raw);
  if(storage.getItem(STORAGE_KEY)!==raw)throw unavailable();
}
export function storeReference(ref,storage){
  try{
    if(!validReference(ref))throw unavailable();
    const target=storage||window.sessionStorage;const refs=readReferences(target);
    const existing=refs.find(item=>item.scope_digest===ref.scope_digest);
    if(existing){if(!sameReference(existing,ref))throw unavailable();return;}
    if(refs.length===10||refs.some(item=>item.request_id===ref.request_id))throw unavailable();
    writeReferences([...refs,ref],target);
  }catch(_){throw unavailable();}
}
export function clearReference(ref,storage){
  try{
    if(!validReference(ref))throw unavailable();
    const target=storage||window.sessionStorage;const refs=readReferences(target);
    const existing=refs.find(item=>item.scope_digest===ref.scope_digest);
    if(existing&&!sameReference(existing,ref))throw unavailable();
    if(existing)writeReferences(refs.filter(item=>!sameReference(item,ref)),target);
    // Reinspect before unlocking; a different same-scope locator must survive.
    if(readReferences(target).some(item=>item.scope_digest===ref.scope_digest))throw unavailable();
  }catch(_){throw unavailable();}
}
