import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {TextEncoder} from 'util';
import {toast} from 'sonner';
import OutreachCampaigns from './OutreachCampaigns';
jest.mock('sonner',()=>({toast:{success:jest.fn(),error:jest.fn()}}));
const record=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
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
