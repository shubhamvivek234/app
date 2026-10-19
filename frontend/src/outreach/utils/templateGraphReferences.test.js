import { STORAGE_KEY, readReferences, storeReference, clearReference } from './templateGraphReferences';
import { validHistoricalGraphReceipt } from './templateGraphUpdates';
const ref=(i=0)=>({contract_version:1,workspace_id:'workspace',scope_digest:i.toString(16).padStart(64,'0'),
  request_id:`01234567-89ab-4cde-8fab-${i.toString(16).padStart(12,'0')}`,input_digest:'a'.repeat(64)});
const receipt=()=>({...ref(),status:'updated',template_id:'tpl_custom_012345abcd',revision:0,
  review_digest:'b'.repeat(64),identity_digest:'c'.repeat(64),review_scope_digest:'d'.repeat(64),
  new_revision:1,new_review_digest:'e'.repeat(64),graph_digest:'f'.repeat(64)});
beforeEach(()=>sessionStorage.clear());
test('keeps only bounded locators, independent of existing creation references',()=>{
  sessionStorage.setItem('unravler.outreach.templateSaveReferences.v1','creation');
  storeReference(ref());storeReference(ref(1));storeReference(ref());
  expect(readReferences()).toEqual([ref(),ref(1)]);clearReference(ref());expect(readReferences()).toEqual([ref(1)]);
  expect(sessionStorage.getItem('unravler.outreach.templateSaveReferences.v1')).toBe('creation');
});
test.each(['bad','[]','x'.repeat(8193),JSON.stringify({contract_version:2,references:[]}),
  JSON.stringify({contract_version:1,references:[ref(),ref()]}),
  JSON.stringify({contract_version:1,references:[ref(),{...ref(1),request_id:ref().request_id}]}),
  JSON.stringify({contract_version:1,references:[{...ref(),name:'secret'}]})])('malformed storage holds unchanged',raw=>{
  sessionStorage.setItem(STORAGE_KEY,raw);expect(()=>readReferences()).toThrow();expect(sessionStorage.getItem(STORAGE_KEY)).toBe(raw);
});
test('cannot overwrite or clear a competing original and never evicts full storage',()=>{
  storeReference(ref());const other={...ref(),input_digest:'b'.repeat(64)};
  expect(()=>storeReference(other)).toThrow();expect(()=>clearReference(other)).toThrow();
  for(let i=1;i<10;i++)storeReference(ref(i));expect(()=>storeReference(ref(10))).toThrow();expect(readReferences()).toHaveLength(10);
});
test('blocked, unverified and changed-during-cleanup storage deny progress',()=>{
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{throw Error();}})).toThrow();
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{}})).toThrow();
  storeReference(ref());const native=sessionStorage.getItem(STORAGE_KEY);let calls=0;
  const other=JSON.stringify({contract_version:1,references:[{...ref(),input_digest:'b'.repeat(64)}]});
  const storage={getItem:()=>++calls===1?native:other,setItem:()=>{}};
  expect(()=>clearReference(ref(),storage)).toThrow();
});
test.each([null,{...ref(),name:'text'},{...ref(),request_id:'bad'}])('invalid locators cannot be saved or cleared',value=>{
  expect(()=>storeReference(value)).toThrow();expect(()=>clearReference(value)).toThrow();
});
test('strict historical confirmation binds original locator and safe native receipt shape',()=>{
  expect(validHistoricalGraphReceipt(receipt(),ref())).toBe(true);
  const last={...receipt(),revision:Number.MAX_SAFE_INTEGER-1,new_revision:Number.MAX_SAFE_INTEGER};
  expect(validHistoricalGraphReceipt(last,ref())).toBe(true);
});
test.each([{revision:true},{revision:-1},{revision:0.5},{revision:Number.MAX_SAFE_INTEGER},
  {new_revision:2},{new_revision:'1'},{template_id:'tpl_custom_bad'},{identity_digest:'bad'},
  {review_scope_digest:[]},{name:'unexpected'},{input_digest:'f'.repeat(64)},{status:'saved'},
  {workspace_id:'other'},{contract_version:true},{graph_digest:'bad'}])('malformed or foreign receipt is never confirmation %j',change=>{
  expect(validHistoricalGraphReceipt({...receipt(),...change},ref())).toBe(false);
});
