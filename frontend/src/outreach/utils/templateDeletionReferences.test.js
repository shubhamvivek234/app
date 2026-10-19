import {STORAGE_KEY,readReferences,storeReference,clearReference} from './templateDeletionReferences';
import {storeReference as storeMetadataReference,readReferences as readMetadataReferences} from './templateMetadataReferences';
import {storeReference as storeGraphReference,readReferences as readGraphReferences} from './templateGraphReferences';
const ref=(i=0)=>({contract_version:1,workspace_id:'workspace',scope_digest:i.toString(16).padStart(64,'0'),
  request_id:`01234567-89ab-4cde-8fab-${i.toString(16).padStart(12,'0')}`,input_digest:'a'.repeat(64)});
beforeEach(()=>sessionStorage.clear());
test('deletion locators are independent of graph, metadata, creation and campaign deletion keys',()=>{
  storeReference(ref());storeMetadataReference(ref());storeGraphReference(ref());
  sessionStorage.setItem('unravler.campaign-deletions.v1','campaign reference');
  sessionStorage.setItem('unravler.outreach.templateSaveReferences.v1','creation reference');
  clearReference(ref());expect(readReferences()).toEqual([]);expect(readMetadataReferences()).toEqual([ref()]);expect(readGraphReferences()).toEqual([ref()]);
  expect(sessionStorage.getItem('unravler.campaign-deletions.v1')).toBe('campaign reference');
  expect(sessionStorage.getItem('unravler.outreach.templateSaveReferences.v1')).toBe('creation reference');
});
test.each(['bad','[]','x'.repeat(8193),JSON.stringify({contract_version:2,references:[]}),
  JSON.stringify({contract_version:1,references:[ref(),ref()]}),
  JSON.stringify({contract_version:1,references:[ref(),{...ref(1),request_id:ref().request_id}]}),
  JSON.stringify({contract_version:1,references:[{...ref(),name:'private'}]})])('invalid deletion storage holds without rewriting %#',raw=>{
  sessionStorage.setItem(STORAGE_KEY,raw);expect(()=>readReferences()).toThrow();expect(sessionStorage.getItem(STORAGE_KEY)).toBe(raw);
});
test('full storage never evicts and a newer original cannot be overwritten or cleared',()=>{
  for(let i=0;i<10;i++)storeReference(ref(i));expect(()=>storeReference(ref(10))).toThrow();
  expect(()=>clearReference({...ref(),input_digest:'b'.repeat(64)})).toThrow();
  expect(()=>storeReference({...ref(),input_digest:'b'.repeat(64)})).toThrow();expect(readReferences()).toHaveLength(10);
});
test('write and readback failures deny admission',()=>{
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{throw Error('blocked');}})).toThrow();
  expect(()=>storeReference(ref(),{getItem:()=>null,setItem:()=>{}})).toThrow();
});
