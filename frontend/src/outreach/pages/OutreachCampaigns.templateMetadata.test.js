import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {TextEncoder} from 'util';
import {toast} from 'sonner';
import OutreachCampaigns from './OutreachCampaigns';
import {STORAGE_KEY,storeReference,readReferences} from '../utils/templateMetadataReferences';
jest.mock('sonner',()=>({toast:{success:jest.fn(),error:jest.fn()}}));
const record=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
  workspace_access:{contract_version:1,workspace_id:'workspace',visibility:'workspace',created_by_you:false,
    can_configure:true,can_edit:true,can_delete:true,execution_authorized:false},
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  deletion_review:{contract_version:1,reviewable:true,deletion_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'f'.repeat(64)},
  metadata_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const reply=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>{const old=JSON.parse(body.content_json);return {contract_version:1,workspace_id:body.workspace_id,
  scope_digest:body.scope_digest,request_id:body.request_id,input_digest:body.input_digest,status:'updated',template_id:old.template_id,
  revision:old.revision,review_digest:old.review_digest,identity_digest:old.identity_digest,review_scope_digest:old.scope_digest,
  new_revision:1,new_review_digest:'d'.repeat(64)};};
let container,root,catalog,post,status,body,reads;
const button=text=>[...container.querySelectorAll('button')].find(item=>item.textContent.trim()===text);
const edit=()=>container.querySelector('[aria-label="Edit template details Starter"]');
async function open(){await act(async()=>root.render(<OutreachCampaigns onOpenWizard={jest.fn()}/>));await act(async()=>button('Browse winning templates').click());}
async function save(){await act(async()=>edit().click());await act(async()=>button('Save details').click());}
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;localStorage.clear();sessionStorage.clear();
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID:()=> '01234567-89ab-cdef-0123-456789abcdef',subtle:{digest:async()=>new Uint8Array(32).buffer}}});
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);toast.success.mockClear();toast.error.mockClear();
  reads=0;body=null;catalog=async()=>reply([record()]);post=async b=>reply(receipt(b));status=async()=>reply(receipt(body));
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/campaigns'))return reply([]);if(url.includes('/sequence-capabilities'))return reply({capabilities:[]});
    if(url.endsWith('/templates')){reads++;return catalog();}if(url.endsWith('/template-metadata-updates/context'))return reply(context);
    if(options.method==='POST'){body=JSON.parse(options.body);return post(body);}return status();});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

it('requires dedicated native review while retaining ordinary Use',async()=>{
  catalog=async()=>reply([{...record(),metadata_review:null}]);await open();expect(edit().disabled).toBe(true);expect(button('Use').disabled).toBe(false);
});
it('opening details locks Use/Delete/navigation until Cancel without update preparation',async()=>{
  await open();await act(async()=>{edit().click();button('Use').click();container.querySelector('[aria-label="Delete template Starter"]').click();});
  expect(button('Use').disabled).toBe(true);expect(button('← Campaigns').disabled).toBe(true);expect(global.fetch).toHaveBeenCalledTimes(2);
  await act(async()=>button('Cancel').click());expect(button('Use').disabled).toBe(false);expect(edit().disabled).toBe(false);
});
it('exact original receipt refreshes fresh reviews rather than copying stale deletion proof',async()=>{
  post=async b=>{catalog=async()=>reply([{...record(),name:'Renamed',metadata_review:{...record().metadata_review,revision:1,review_digest:'d'.repeat(64)}}]);return reply(receipt(b));};
  await open();await save();expect(toast.success).toHaveBeenCalledWith('Template details updated');expect(reads).toBe(2);
  expect(container.querySelector('[aria-label="Edit template details Renamed"]')).not.toBeNull();
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
});
it('original status confirmation is historical and the gallery fetches current later details',async()=>{
  post=async()=>{throw new Error('unknown');};await open();await save();expect(button('Use').disabled).toBe(true);
  catalog=async()=>reply([{...record(),name:'Later edit',metadata_review:{...record().metadata_review,revision:2,review_digest:'e'.repeat(64)}}]);
  await act(async()=>button('Check original update status').click());
  expect(toast.success).toHaveBeenCalledWith('Original template update confirmed');expect(reads).toBe(2);
  expect(container.querySelector('[aria-label="Edit template details Later edit"]').disabled).toBe(false);
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
});
it.each([404,202])('unknown status%s cannot release gallery actions or generate a fresh update',async(code)=>{
  post=async()=>{throw new Error('unknown');};status=async()=>reply({},code);await open();await save();
  await act(async()=>button('Check original update status').click());
  expect(button('Save details').disabled).toBe(true);expect(button('← Campaigns').disabled).toBe(true);expect(reads).toBe(1);expect(toast.success).not.toHaveBeenCalled();
});
it('failed catalog after confirmed original receipt exposes Retry with no stale actions',async()=>{
  post=async b=>{catalog=async()=>reply({},503);return reply(receipt(b));};await open();await save();
  expect(button('Retry templates')).toBeDefined();expect(edit()).toBeNull();expect(toast.success).toHaveBeenCalledTimes(1);
});
it('token change during original status parsing cannot release held gallery',async()=>{
  post=async()=>{throw new Error('unknown');};status=async()=>({ok:true,status:200,json:async()=>{localStorage.setItem('token','other');return receipt(body);}});
  await open();await save();await act(async()=>{button('Check original update status').click();button('Check original update status').click();});
  expect(button('← Campaigns').disabled).toBe(true);expect(reads).toBe(1);expect(toast.success).not.toHaveBeenCalled();
});

const locator=()=>({contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
  request_id:'01234567-89ab-cdef-0123-456789abcdef',input_digest:'0'.repeat(64)});
const storedReceipt=()=>({...locator(),status:'updated',template_id:record().id,revision:0,review_digest:'a'.repeat(64),
  identity_digest:'b'.repeat(64),review_scope_digest:'c'.repeat(64),new_revision:1,new_review_digest:'d'.repeat(64)});
it('lost original update survives remount and uses only explicit fresh-context original GET',async()=>{
  post=async()=>{throw Error('lost');};await open();await save();
  expect(readReferences()).toEqual([locator()]);
  await act(async()=>root.unmount());root=createRoot(container);await open();
  expect(edit().disabled).toBe(true);expect(button('Use').disabled).toBe(true);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/template-metadata-updates/')).length).toBe(1);
  catalog=async()=>reply([{...record(),name:'Later edit'}]);
  await act(async()=>{button('Check saved details update status').click();button('Check saved details update status').click();});
  expect(readReferences()).toEqual([]);expect(toast.success).toHaveBeenCalledWith('Original template update confirmed');
  expect(container.querySelector('[aria-label="Edit template details Later edit"]').disabled).toBe(false);
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
  expect(global.fetch.mock.calls.at(-2)[0]).toContain('input_digest='+locator().input_digest);
});
it.each([404,403,202,503])('saved unknown status %s survives refresh and prevents new template mutations',async(code)=>{
  storeReference(locator());status=async()=>reply({},code);await open();
  await act(async()=>button('Check saved details update status').click());
  expect(readReferences()).toEqual([locator()]);expect(edit().disabled).toBe(true);expect(button('Use').disabled).toBe(true);
  expect(container.querySelector('[aria-label="Delete template Starter"]').disabled).toBe(true);
  expect(global.fetch.mock.calls.every(([,opts])=>opts.method!=='POST')).toBe(true);
});
it('malformed storage is preserved and denies template actions',async()=>{
  sessionStorage.setItem(STORAGE_KEY,'bad');await open();expect(button('Use').disabled).toBe(true);
  await act(async()=>button('Check saved details update status').click());
  expect(sessionStorage.getItem(STORAGE_KEY)).toBe('bad');expect(edit().disabled).toBe(true);
});
it('foreign scope is retained without original-status disclosure after explicit current-context inspection',async()=>{
  const foreign={...locator(),scope_digest:'1'.repeat(64)};storeReference(foreign);await open();
  await act(async()=>button('Check saved details update status').click());
  expect(readReferences()).toEqual([foreign]);expect(button('Use').disabled).toBe(false);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/template-metadata-updates/')&&!url.endsWith('/context'))).toHaveLength(0);
});
it('recovery token change during status parsing and newer storage references cannot clear holds',async()=>{
  storeReference(locator());status=async()=>({ok:true,status:200,json:async()=>{
    localStorage.setItem('token','changed');return storedReceipt();}});await open();
  await act(async()=>button('Check saved details update status').click());expect(edit().disabled).toBe(true);
  expect(readReferences()).toEqual([locator()]);expect(toast.success).not.toHaveBeenCalled();
  const later={...locator(),request_id:'11111111-1111-1111-1111-111111111111',input_digest:'1'.repeat(64)};
  status=async()=>{sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,
    references:[later]}));return reply(storedReceipt());};
  await act(async()=>button('Check saved details update status').click());expect(edit().disabled).toBe(true);
  expect(readReferences()[0].input_digest).toBe('1'.repeat(64));
  status=async()=>reply({...storedReceipt(),...later});
  await act(async()=>button('Check saved details update status').click());
  expect(readReferences()).toEqual([]);expect(edit().disabled).toBe(false);
  expect(global.fetch.mock.calls.at(-2)[0]).toContain(later.request_id);
});

it.each(['wrong_input','extra','bad_revision'])('restored locator rejects %s status receipt',async(fault)=>{
  storeReference(locator());status=async()=>reply({...storedReceipt(),...(fault==='wrong_input'?{input_digest:'1'.repeat(64)}
    :fault==='extra'?{name:'private'}:{new_revision:2})});await open();
  await act(async()=>button('Check saved details update status').click());expect(edit().disabled).toBe(true);
  expect(readReferences()).toEqual([locator()]);expect(toast.success).not.toHaveBeenCalled();
});
it('normal token refresh uses current credentials while a context switch prevents status disclosure',async()=>{
  storeReference(locator());await open();localStorage.setItem('token','fresh');
  const previous=global.fetch;
  global.fetch=jest.fn(async(url,opts)=>url.endsWith('/template-metadata-updates/context')
    ?reply({...context,scope_digest:'2'.repeat(64)}):previous(url,opts));
  await act(async()=>button('Check saved details update status').click());
  expect(global.fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer fresh');expect(readReferences()).toEqual([locator()]);
  expect(global.fetch.mock.calls).toHaveLength(1);expect(button('Use').disabled).toBe(false);
});
it('departure during context read prevents original status requests and restores the hold on return',async()=>{
  storeReference(locator());await open();let finish;const previous=global.fetch;
  global.fetch=jest.fn(async(url,opts)=>url.endsWith('/template-metadata-updates/context')
    ?new Promise(resolve=>{finish=()=>resolve(reply(context));}):previous(url,opts));
  await act(async()=>button('Check saved details update status').click());await act(async()=>button('← Campaigns').click());
  await act(async()=>finish());await act(async()=>button('Browse winning templates').click());
  expect(edit().disabled).toBe(true);expect(readReferences()).toEqual([locator()]);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/template-metadata-updates/')&&!url.endsWith('/context'))).toHaveLength(0);
});
it('a locator arriving after rendering is caught synchronously before an editor can open',async()=>{
  await open();storeReference(locator());await act(async()=>edit().click());
  expect(button('Save details')).toBeUndefined();expect(edit().disabled).toBe(true);
});
it('cleanup write failure cannot unlock a confirmed original status',async()=>{
  storeReference(locator());status=async()=>reply(storedReceipt());await open();
  const native=Storage.prototype.setItem;const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){
    if(key===STORAGE_KEY&&JSON.parse(value).references.length===0)throw Error('blocked');return native.call(this,key,value);});
  try {await act(async()=>button('Check saved details update status').click());
    expect(edit().disabled).toBe(true);expect(readReferences()).toEqual([locator()]);expect(toast.success).not.toHaveBeenCalled();
  } finally {spy.mockRestore();}
});
it('a lost in-memory foreign locator is restored before a different account can unlock',async()=>{
  storeReference(locator());status=async()=>reply({},404);await open();await act(async()=>button('Check saved details update status').click());
  sessionStorage.removeItem(STORAGE_KEY);const previous=global.fetch;
  global.fetch=jest.fn(async(url,opts)=>url.endsWith('/template-metadata-updates/context')
    ?reply({...context,scope_digest:'2'.repeat(64)}):previous(url,opts));
  await act(async()=>button('Check saved details update status').click());
  expect(readReferences()).toEqual([locator()]);expect(button('Use').disabled).toBe(false);
});

it('reentering the gallery requires a fresh context review before foreign locators allow actions',async()=>{
  const foreign={...locator(),scope_digest:'1'.repeat(64)};storeReference(foreign);await open();
  await act(async()=>button('Check saved details update status').click());expect(edit().disabled).toBe(false);
  await act(async()=>button('← Campaigns').click());await act(async()=>button('Browse winning templates').click());
  expect(edit().disabled).toBe(true);expect(readReferences()).toEqual([foreign]);
});
