import { deletionInputDigest, matchesDeletionReceipt, validHistoricalDeletionReceipt } from './templateDeletionRecovery';
import { TextEncoder } from 'util';

const reference={contract_version:1,workspace_id:'workspace',request_id:'01234567-89ab-cdef-0123-456789abcdef',scope_digest:'f'.repeat(64),input_digest:'0'.repeat(64)};
const original={contract_version:1,workspace_id:'workspace',template_id:'tpl_custom_012345abcd',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)};
const receipt=()=>({...reference,status:'deleted',template_id:original.template_id,revision:0,review_digest:original.review_digest,identity_digest:original.identity_digest,review_scope_digest:original.scope_digest});
it('matches only the exact original reference and native review without exposing content',()=>{
  expect(matchesDeletionReceipt(receipt(),{...reference,content_json:'private input'},original)).toBe(true);
});
it.each([{revision:1},{template_id:'other'},{review_digest:'d'.repeat(64)},{identity_digest:'d'.repeat(64)},
  {review_scope_digest:'d'.repeat(64)},{scope_digest:'d'.repeat(64)},{input_digest:'d'.repeat(64)},
  {request_id:'other'},{status:'success'},{workspace_id:'other'},{contract_version:2},{execution_authorized:true}])('rejects changed or extra receipts %#',change=>{
  expect(matchesDeletionReceipt({...receipt(),...change},reference,original)).toBe(false);
});
it.each([null,[],{}])('rejects missing receipt %#',value=>expect(matchesDeletionReceipt(value,reference,original)).toBe(false));
it('bounds the complete UTF8 operation before hashing',async()=>{
  global.TextEncoder=TextEncoder;
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:jest.fn(async()=>new Uint8Array(32).buffer)}}});
  await expect(deletionInputDigest('☕'.repeat(2731))).rejects.toThrow();
  expect(global.crypto.subtle.digest).not.toHaveBeenCalled();
  await expect(deletionInputDigest('a'.repeat(8192))).resolves.toBe('0'.repeat(64));
});
it('reload receipt has exact native shape and permits the final JS-safe revision',()=>{
  expect(validHistoricalDeletionReceipt(receipt(),reference)).toBe(true);
  expect(validHistoricalDeletionReceipt({...receipt(),revision:Number.MAX_SAFE_INTEGER},reference)).toBe(true);
});
it.each([null,[],{},...['revision','review_digest','identity_digest','review_scope_digest'].map(key=>{const value=receipt();delete value[key];return value;})])('reload rejects absent receipt proof %#',value=>{
  expect(validHistoricalDeletionReceipt(value,reference)).toBe(false);
});
it.each([{revision:true},{revision:-1},{revision:0.5},{revision:Number.MAX_SAFE_INTEGER+1},
  {status:'updated'},{template_id:'tpl_custom_bad'},{review_digest:'bad'},{identity_digest:[]},
  {review_scope_digest:'bad'},{input_digest:'e'.repeat(64)},{workspace_id:'other'},{contract_version:true},
  {name:'unwanted text'},{graph_digest:'e'.repeat(64)}])('reload rejects malformed or foreign proof %#',change=>{
  expect(validHistoricalDeletionReceipt({...receipt(),...change},reference)).toBe(false);
});
