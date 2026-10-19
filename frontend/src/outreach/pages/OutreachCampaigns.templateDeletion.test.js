import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { TextEncoder } from 'util';
import { toast } from 'sonner';
import OutreachCampaigns from './OutreachCampaigns';
import { reviewedTemplateDeletion } from '../utils/templateDeletion';
import { STORAGE_KEY, readReferences, storeReference } from '../utils/templateDeletionReferences';

jest.mock('sonner', () => ({toast:{success:jest.fn(),error:jest.fn()}}));
const request='01234567-89ab-cdef-0123-456789abcdef';
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const row = (change={}) => ({ id:'tpl_custom_012345abcd',name:'Reviewed starter',is_custom:true,
  workspace_access:{contract_version:1,workspace_id:'workspace',visibility:'workspace',created_by_you:false,
    can_configure:true,can_edit:true,can_delete:true,execution_authorized:false},
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  metadata_review:{contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'d'.repeat(64),update_authorized:false,execution_authorized:false},
  graph_review:{contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'e'.repeat(64),update_authorized:false,execution_authorized:false},
  deletion_review:{contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',
    review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),
    deletion_authorized:false,execution_authorized:false},...change });
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>{const p=JSON.parse(body.content_json);const {content_json,...ref}=body;
  return {...ref,status:'deleted',template_id:p.template_id,revision:p.revision,review_digest:p.review_digest,identity_digest:p.identity_digest,review_scope_digest:p.scope_digest};};
let container,root,post,status,contextReply,catalog,original;
const button=text=>[...container.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
const deleteButton=()=>container.querySelector('[aria-label="Delete template Reviewed starter"]');
const posts=()=>global.fetch.mock.calls.filter(([,opts])=>opts?.method==='POST');
async function open(){
  await act(async()=>root.render(<OutreachCampaigns onOpenWizard={jest.fn()}/>));
  await act(async()=>button('Browse winning templates').click());
}
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;localStorage.clear();sessionStorage.clear();
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID:jest.fn(()=>request),subtle:{digest:jest.fn(async()=>new Uint8Array(32).buffer)}}});
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  toast.success.mockClear();toast.error.mockClear();original=null;catalog=[row()];
  post=async body=>response(receipt(body));status=async()=>response(receipt(original));contextReply=async()=>response(context);
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/template-deletions/context'))return contextReply();
    if(url.endsWith('/template-deletions')&&options.method==='POST'){original=JSON.parse(options.body);catalog=[];return post(original);}
    if(url.includes('/template-deletions/'))return status(url,options);
    if(url.endsWith('/sequences/templates'))return response(catalog);
    if(url.endsWith('/campaigns'))return response([]);
    throw new Error('Unexpected request');
  });
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

it('freezes original review and one UUID, posts once and reloads current catalog only after exact receipt',async()=>{
  await open();await act(async()=>{deleteButton().click();deleteButton().click();button('Use').click();});
  const body=JSON.parse(posts()[0][1].body);
  expect(JSON.parse(body.content_json)).toEqual({...reviewedTemplateDeletion(row()),template_id:row().id});
  expect(body.scope_digest).toBe(context.scope_digest);expect(body.scope_digest).not.toBe(JSON.parse(body.content_json).scope_digest);
  expect(posts()).toHaveLength(1);expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(deleteButton()).toBeNull();expect(toast.success).toHaveBeenCalledWith('Original template deletion confirmed');
  expect(global.fetch.mock.calls.filter(([,opts])=>opts?.method==='DELETE')).toHaveLength(0);
  expect(readReferences()).toEqual([]);
});

it.each([null,{contract_version:1,reviewable:false}])('holds unreviewable custom templates %#',async(review)=>{
  catalog=[row({deletion_review:review})];await open();expect(deleteButton().disabled).toBe(true);expect(posts()).toHaveLength(0);
});

it.each(['network','404','202','201','wrong_revision','wrong_native','wrong_inner_scope','wrong_outer_scope','legacy_success','extra','json'])('unknown %s can recover only the original GET without another deletion',async(fault)=>{
  post=async body=>{if(fault==='network')throw new Error('lost');const data=receipt(body);
    if(fault==='wrong_revision')data.revision=1;if(fault==='wrong_native')data.identity_digest='e'.repeat(64);
    if(fault==='wrong_inner_scope')data.review_scope_digest='e'.repeat(64);if(fault==='wrong_outer_scope')data.scope_digest='e'.repeat(64);
    if(fault==='extra')data.execution_authorized=true;if(fault==='legacy_success')return response({status:'success'});
    if(fault==='json')return {ok:true,status:200,json:async()=>{throw new Error('json');}};
    return response(data,fault==='404'?404:fault==='202'?202:fault==='201'?201:200);
  };
  await open();await act(async()=>deleteButton().click());
  expect(container.textContent).toContain('Earlier deletion is unconfirmed');expect(deleteButton().disabled).toBe(true);expect(button('Use').disabled).toBe(true);
  expect(toast.success).not.toHaveBeenCalled();
  await act(async()=>{button('Check original deletion status').click();button('Check original deletion status').click();});
  expect(toast.success).toHaveBeenCalledWith('Original template deletion confirmed');
  expect(posts()).toHaveLength(1);expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);
  const get=global.fetch.mock.calls.find(([url])=>url.includes('/template-deletions/'+request))[0];
  expect(get).toContain('input_digest='+original.input_digest);expect(get).toContain('scope_digest='+context.scope_digest);
});

it.each([404,403,503,202])('status %s retains the original hold and blocks fresh deletion',async(code)=>{
  post=async()=>{throw new Error('unknown');};status=async()=>response({},code);
  await open();await act(async()=>deleteButton().click());await act(async()=>button('Check original deletion status').click());
  expect(deleteButton().disabled).toBe(true);expect(button('Use').disabled).toBe(true);expect(posts()).toHaveLength(1);
  expect(toast.success).not.toHaveBeenCalled();expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);
});

it('historical receipt reloads and preserves a replacement current template',async()=>{
  post=async()=>{throw new Error('unknown');};await open();await act(async()=>deleteButton().click());
  catalog=[row({deletion_review:{...row().deletion_review,identity_digest:'e'.repeat(64),review_digest:'d'.repeat(64)}})];
  await act(async()=>button('Check original deletion status').click());
  expect(deleteButton().disabled).toBe(false);expect(container.textContent).toContain('Reviewed starter');expect(posts()).toHaveLength(1);
  expect(toast.success).toHaveBeenCalledWith('Original template deletion confirmed');
});

it('normal token refresh uses current credentials for fresh context and original status',async()=>{
  post=async()=>{throw new Error('unknown');};localStorage.setItem('token','old');
  await open();await act(async()=>deleteButton().click());localStorage.setItem('token','refreshed');
  await act(async()=>button('Check original deletion status').click());
  const call=global.fetch.mock.calls.find(([url])=>url.includes('/template-deletions/'+request));
  expect(call[1].headers.Authorization).toBe('Bearer refreshed');expect(posts()).toHaveLength(1);
});

it('foreign fresh scope never requests the original status or unlocks deletion',async()=>{
  post=async()=>{throw new Error('unknown');};await open();await act(async()=>deleteButton().click());
  contextReply=async()=>response({...context,scope_digest:'e'.repeat(64)});
  await act(async()=>button('Check original deletion status').click());
  expect(global.fetch.mock.calls.some(([url])=>url.includes('/template-deletions/'+request))).toBe(false);
  expect(deleteButton().disabled).toBe(true);expect(toast.success).not.toHaveBeenCalled();
});

it.each(['token','unmount'])('changed %s during hash preparation prevents any POST',async(kind)=>{
  let release;global.crypto.subtle.digest=jest.fn(()=>new Promise(resolve=>{release=()=>resolve(new Uint8Array(32).buffer);}));
  await open();await act(async()=>deleteButton().click());
  if(kind==='token')localStorage.setItem('token','other');else{await act(async()=>root.unmount());root=createRoot(container);}
  await act(async()=>release());expect(posts()).toHaveLength(0);expect(global.crypto.randomUUID).not.toHaveBeenCalled();expect(toast.success).not.toHaveBeenCalled();
  if(kind==='token'){await act(async()=>button('Cancel deletion preparation').click());expect(deleteButton().disabled).toBe(false);}
});

it('token drift while status JSON resolves cannot confirm an original',async()=>{
  post=async()=>{throw new Error('unknown');};status=async()=>({ok:true,status:200,json:async()=>{localStorage.setItem('token','other');return receipt(original);}});
  await open();await act(async()=>deleteButton().click());await act(async()=>button('Check original deletion status').click());
  expect(toast.success).not.toHaveBeenCalled();expect(deleteButton().disabled).toBe(true);expect(posts()).toHaveLength(1);
});

it('definite preparation failure permits correction without a request reference',async()=>{
  global.crypto.subtle.digest=jest.fn(async()=>{throw new Error('crypto');});await open();await act(async()=>deleteButton().click());
  expect(deleteButton().disabled).toBe(false);expect(posts()).toHaveLength(0);expect(global.crypto.randomUUID).not.toHaveBeenCalled();
});

it('unmount after submission never applies a receipt or starts catalog refresh',async()=>{
  let release;post=()=>new Promise(resolve=>{release=()=>resolve(response(receipt(original)));});
  await open();await act(async()=>deleteButton().click());const count=global.fetch.mock.calls.length;
  await act(async()=>root.unmount());root=createRoot(container);await act(async()=>release());
  expect(toast.success).not.toHaveBeenCalled();expect(global.fetch).toHaveBeenCalledTimes(count);
});

it.each(['token','unmount'])('changed %s during delayed context JSON never submits deletion',async(kind)=>{
  let release;contextReply=async()=>({ok:true,status:200,json:()=>new Promise(resolve=>{release=()=>resolve(context);})});
  await open();await act(async()=>deleteButton().click());
  if(kind==='token')localStorage.setItem('token','other');else{await act(async()=>root.unmount());root=createRoot(container);}
  await act(async()=>release());expect(posts()).toHaveLength(0);expect(global.crypto.randomUUID).not.toHaveBeenCalled();
  if(kind==='token')expect(button('Cancel deletion preparation')).toBeDefined();
});

it.each(['pending','held'])('%s deletion blocks otherwise valid metadata and sequence editors',async(phase)=>{
  let release;post=phase==='held'?async()=>{throw new Error('lost');}:()=>new Promise(resolve=>{release=()=>resolve(response(receipt(original)));});
  await open();
  const metadata=()=>container.querySelector('[aria-label="Edit template details Reviewed starter"]');
  const graph=()=>container.querySelector('[aria-label="Edit template sequence Reviewed starter"]');
  expect(metadata().disabled).toBe(false);expect(graph().disabled).toBe(false);
  await act(async()=>deleteButton().click());
  expect(metadata().disabled).toBe(true);expect(graph().disabled).toBe(true);
  await act(async()=>{metadata().click();graph().click();});expect(posts()).toHaveLength(1);
  if(release)await act(async()=>release());
});

it('invalid generated UUID fails before submission and permits a new deliberate preparation',async()=>{
  global.crypto.randomUUID=jest.fn(()=>'invalid');await open();await act(async()=>deleteButton().click());
  expect(posts()).toHaveLength(0);expect(deleteButton().disabled).toBe(false);expect(toast.success).not.toHaveBeenCalled();
});

it('token drift in fresh status context JSON never requests historical outcome',async()=>{
  post=async()=>{throw new Error('lost');};await open();await act(async()=>deleteButton().click());
  contextReply=async()=>({ok:true,status:200,json:async()=>{localStorage.setItem('token','other');return context;}});
  await act(async()=>button('Check original deletion status').click());
  expect(global.fetch.mock.calls.some(([url])=>url.includes('/template-deletions/'+request))).toBe(false);
  expect(toast.success).not.toHaveBeenCalled();expect(deleteButton().disabled).toBe(true);
});

it('token drift in POST receipt JSON retains original reference without confirmation',async()=>{
  post=async body=>({ok:true,status:200,json:async()=>{localStorage.setItem('token','refreshed');return receipt(body);}});
  await open();await act(async()=>deleteButton().click());expect(toast.success).not.toHaveBeenCalled();
  expect(deleteButton().disabled).toBe(true);expect(button('Check original deletion status')).toBeDefined();expect(posts()).toHaveLength(1);
});

const locator=()=>({contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
  request_id:request,input_digest:'0'.repeat(64)});
const savedReceipt=()=>({...locator(),status:'deleted',template_id:row().id,revision:0,
  review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),review_scope_digest:'c'.repeat(64)});
it('lost deletion survives remount and original status confirms without removing a replacement',async()=>{
  post=async()=>{throw Error('lost');};await open();await act(async()=>deleteButton().click());
  expect(readReferences()).toEqual([locator()]);expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('Reviewed starter');
  await act(async()=>root.unmount());root=createRoot(container);catalog=[row({name:'Replacement'})];await open();
  expect(button('Use').disabled).toBe(true);expect(posts()).toHaveLength(1);
  await act(async()=>{button('Check saved deletion status').click();button('Check saved deletion status').click();});
  expect(readReferences()).toEqual([]);expect(posts()).toHaveLength(1);
  expect(container.querySelector('[aria-label="Delete template Replacement"]').disabled).toBe(false);
  expect(toast.success).toHaveBeenCalledWith('Original template deletion confirmed');
});
it.each([404,403,202,503])('saved status%s preserves locator and denies all template mutations',async(code)=>{
  storeReference(locator());status=async()=>response({},code);await open();
  await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([locator()]);
  expect(button('Use').disabled).toBe(true);expect(deleteButton().disabled).toBe(true);expect(posts()).toHaveLength(0);
  expect(container.querySelector('[aria-label="Edit template details Reviewed starter"]').disabled).toBe(true);
  expect(container.querySelector('[aria-label="Edit template sequence Reviewed starter"]').disabled).toBe(true);
});
it('corrupt deletion storage holds unchanged without transport',async()=>{
  sessionStorage.setItem(STORAGE_KEY,'bad');await open();await act(async()=>button('Check saved deletion status').click());
  expect(deleteButton().disabled).toBe(true);expect(sessionStorage.getItem(STORAGE_KEY)).toBe('bad');expect(posts()).toHaveLength(0);
});
it('foreign context retains the saved original without disclosing its status',async()=>{
  storeReference(locator());contextReply=async()=>response({...context,scope_digest:'e'.repeat(64)});await open();
  await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([locator()]);
  expect(global.fetch.mock.calls.some(([url])=>url.includes('/template-deletions/'+request))).toBe(false);
  expect(deleteButton().disabled).toBe(false);
});
it('held in-view deletion can leave and return through stored-reference recovery',async()=>{
  post=async()=>{throw Error('lost');};await open();await act(async()=>deleteButton().click());
  await act(async()=>button('← Campaigns').click());catalog=[row()];await act(async()=>button('Browse winning templates').click());
  expect(button('Check original deletion status')).toBeUndefined();expect(button('Use').disabled).toBe(true);
  await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([]);expect(deleteButton().disabled).toBe(false);
});
it('newer same-scope request survives stale cleanup and can be explicitly recovered',async()=>{
  storeReference(locator());const later={...locator(),request_id:'11111111-1111-1111-1111-111111111111',input_digest:'1'.repeat(64)};
  status=async()=>{sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[later]}));return response(savedReceipt());};
  await open();await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([later]);
  status=async()=>response({...savedReceipt(),...later});await act(async()=>button('Check saved deletion status').click());
  expect(readReferences()).toEqual([]);expect(global.fetch.mock.calls.at(-2)[0]).toContain(later.request_id);
});
it('verified locator is present before deletion POST; blocked storage prevents transport',async()=>{
  post=async body=>{expect(readReferences()[0].request_id).toBe(body.request_id);return response(receipt(body));};
  await open();await act(async()=>deleteButton().click());expect(readReferences()).toEqual([]);
  catalog=[row()];await act(async()=>button('← Campaigns').click());await act(async()=>button('Browse winning templates').click());
  const native=Storage.prototype.setItem;const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){
    if(key===STORAGE_KEY)throw Error('blocked');return native.call(this,key,value);});
  try {await act(async()=>deleteButton().click());expect(posts()).toHaveLength(1);expect(deleteButton().disabled).toBe(true);}
  finally {spy.mockRestore();}
});

it.each(['extra','wrong_input','bad_revision','update_receipt','bad_native'])('restored deletion rejects %s receipt',async(fault)=>{
  storeReference(locator());status=async()=>response({...savedReceipt(),...(fault==='extra'?{name:'private'}
    :fault==='wrong_input'?{input_digest:'1'.repeat(64)}:fault==='bad_revision'?{revision:true}
      :fault==='update_receipt'?{status:'updated',new_revision:1}:{identity_digest:'bad'})});
  await open();await act(async()=>button('Check saved deletion status').click());
  expect(readReferences()).toEqual([locator()]);expect(deleteButton().disabled).toBe(true);expect(toast.success).not.toHaveBeenCalled();
});
it('cleanup failure after original receipt cannot unlock a new deletion',async()=>{
  storeReference(locator());status=async()=>response(savedReceipt());await open();
  const native=Storage.prototype.setItem;const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){
    if(key===STORAGE_KEY&&JSON.parse(value).references.length===0)throw Error('blocked');return native.call(this,key,value);});
  try {await act(async()=>button('Check saved deletion status').click());
    expect(readReferences()).toEqual([locator()]);expect(deleteButton().disabled).toBe(true);expect(toast.success).not.toHaveBeenCalled();
  } finally {spy.mockRestore();}
});
it('current-token restoration prevents a stale status response from clearing the reference',async()=>{
  storeReference(locator());await open();localStorage.setItem('token','fresh');
  status=async(url,opts)=>({ok:true,status:200,json:async()=>{expect(opts.headers.Authorization).toBe('Bearer fresh');
    localStorage.setItem('token','other');return savedReceipt();}});
  await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([locator()]);expect(deleteButton().disabled).toBe(true);
});
it('departing during restored status context prevents original-status transport and reentry stays held',async()=>{
  storeReference(locator());await open();let finish;
  contextReply=()=>new Promise(resolve=>{finish=()=>resolve(response(context));});
  await act(async()=>button('Check saved deletion status').click());await act(async()=>button('← Campaigns').click());
  await act(async()=>finish());await act(async()=>button('Browse winning templates').click());
  expect(global.fetch.mock.calls.some(([url])=>url.includes('/template-deletions/'+request))).toBe(false);
  expect(deleteButton().disabled).toBe(true);expect(readReferences()).toEqual([locator()]);
});
it('same-tab locator arriving after render is caught before a new deletion context is requested',async()=>{
  await open();storeReference(locator());await act(async()=>deleteButton().click());
  expect(posts()).toHaveLength(0);expect(deleteButton().disabled).toBe(true);
  expect(global.fetch.mock.calls.some(([url])=>url.endsWith('/template-deletions/context'))).toBe(false);
});
it('a competing locator admitted during input hashing prevents another POST',async()=>{
  global.crypto.subtle.digest=jest.fn(async()=>{storeReference({...locator(),request_id:'11111111-1111-1111-1111-111111111111'});
    return new Uint8Array(32).buffer;});await open();await act(async()=>deleteButton().click());
  expect(posts()).toHaveLength(0);expect(readReferences()[0].request_id).toBe('11111111-1111-1111-1111-111111111111');
});
it('storage failure prevents discarding a held in-view original on departure',async()=>{
  post=async()=>{throw Error('lost');};await open();await act(async()=>deleteButton().click());
  const native=Storage.prototype.setItem;const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){
    if(key===STORAGE_KEY)throw Error('blocked');return native.call(this,key,value);});
  // Force a verified write instead of the identical-original no-op.
  sessionStorage.removeItem(STORAGE_KEY);
  try {await act(async()=>button('← Campaigns').click());expect(button('Check original deletion status')).toBeDefined();
    expect(toast.error).toHaveBeenCalled();} finally {spy.mockRestore();}
});
it('stale inline cleanup preserves a newer saved deletion and departure lets it be recovered',async()=>{
  post=async()=>{throw Error('lost');};await open();await act(async()=>deleteButton().click());
  const later={...locator(),request_id:'11111111-1111-1111-1111-111111111111',input_digest:'1'.repeat(64)};
  status=async()=>{sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[later]}));return response(savedReceipt());};
  await act(async()=>button('Check original deletion status').click());
  expect(readReferences()).toEqual([later]);expect(deleteButton().disabled).toBe(true);expect(toast.success).not.toHaveBeenCalled();
  catalog=[row({deletion_review:{...row().deletion_review,identity_digest:'e'.repeat(64),review_digest:'d'.repeat(64)}})];
  await act(async()=>button('← Campaigns').click());expect(button('Browse winning templates')).toBeDefined();
  await act(async()=>button('Browse winning templates').click());expect(button('Check original deletion status')).toBeUndefined();
  status=async()=>response({...savedReceipt(),...later});
  await act(async()=>button('Check saved deletion status').click());expect(readReferences()).toEqual([]);
  expect(global.fetch.mock.calls.at(-2)[0]).toContain(later.request_id);expect(posts()).toHaveLength(1);
  expect(deleteButton().disabled).toBe(false);
});
