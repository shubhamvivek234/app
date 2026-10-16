import { STORAGE_KEY, readReferences, storeReference, clearReference, validReference } from './templateSaveReferences';
const ref=(index=0)=>({contract_version:1,workspace_id:'workspace',scope_digest:index.toString(16).padStart(64,'0'),request_id:`01234567-89ab-4cde-8fab-${index.toString(16).padStart(12,'0')}`,input_digest:'a'.repeat(64)});
beforeEach(()=>sessionStorage.clear());
test('stores only exact reference fields and conditionally removes its original',()=>{
  storeReference(ref());storeReference(ref(1));
  expect(readReferences()).toEqual([ref(),ref(1)]);clearReference(ref());
  expect(readReferences()).toEqual([ref(1)]);
});
test.each([null,[],{...ref(),graph:[]},{...ref(),contract_version:true},{...ref(),workspace_id:[]},{...ref(),request_id:'other'},{...ref(),input_digest:'bad'}])('rejects malformed reference %j',value=>expect(validReference(value)).toBe(false));
test.each(['[]','bad',JSON.stringify({contract_version:1,references:[ref(),ref()]}),'x'.repeat(8193)])('malformed storage holds without clearing',raw=>{
  sessionStorage.setItem(STORAGE_KEY,raw);expect(()=>readReferences()).toThrow();expect(sessionStorage.getItem(STORAGE_KEY)).toBe(raw);
});
test('a competing original in the same scope cannot be overwritten or cleared',()=>{
  storeReference(ref());const newer={...ref(),request_id:ref(1).request_id};
  expect(()=>storeReference(newer)).toThrow();expect(()=>clearReference(newer)).toThrow();expect(readReferences()).toEqual([ref()]);
});
test('full bounded storage never evicts unresolved references',()=>{
  for(let i=0;i<10;i++)storeReference(ref(i));
  expect(()=>storeReference(ref(10))).toThrow();expect(readReferences()).toHaveLength(10);
});
test('storage write and verification failures deny admission',()=>{
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{throw Error('blocked');}})).toThrow();
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{}})).toThrow();
});
test('duplicate UUIDs across different scopes are held',()=>{
  sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[ref(),{...ref(1),request_id:ref().request_id}]}));
  expect(()=>readReferences()).toThrow();
});
