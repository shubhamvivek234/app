import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {TextEncoder} from 'util';
import TemplateMetadataEditor from './TemplateMetadataEditor';
import {reviewedTemplateMetadata} from '../utils/templateMetadata';
import {matchesMetadataUpdateReceipt} from '../utils/templateMetadataUpdates';
import {STORAGE_KEY,readReferences,storeReference} from '../utils/templateMetadataReferences';

const request='01234567-89ab-cdef-0123-456789abcdef';
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
  metadata_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>{const original=JSON.parse(body.content_json);return {...Object.fromEntries(Object.entries(body).filter(([k])=>k!=='content_json')),
  status:'updated',template_id:original.template_id,revision:original.revision,review_digest:original.review_digest,
  identity_digest:original.identity_digest,review_scope_digest:original.scope_digest,new_revision:original.revision+1,new_review_digest:'d'.repeat(64)};};
let container,root,saved,close,refresh,post,status,original;
const button=text=>[...container.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
const mount=async(record=row())=>act(async()=>root.render(<TemplateMetadataEditor template={record} onSaved={saved} onClose={close} onRefresh={refresh}/>));
const set=(label,value)=>{const el=container.querySelector(`[aria-label="${label}"]`);
  Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);
  el.dispatchEvent(new Event('input',{bubbles:true}));};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;localStorage.clear();sessionStorage.clear();
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID:jest.fn(()=>request),subtle:{digest:jest.fn(async()=>new Uint8Array(32).buffer)}}});
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  saved=jest.fn();close=jest.fn();refresh=jest.fn();original=null;
  post=async body=>response(receipt(body));status=async()=>response(receipt(original));
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/template-metadata-updates/context'))return response(context);
    if(options.method==='POST'){original=JSON.parse(options.body);return post(original);}
    if(url.includes('/template-metadata-updates/'))return status(url);
    throw new Error('Unexpected request');
  });});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

it('freezes original reviewed input, uses one UUID and confirms only a minimal exact receipt',async()=>{
  await mount();await act(async()=>{set('Template name','Renamed ☕');set('Template description','');});
  await act(async()=>{button('Save details').click();button('Save details').click();});
  expect(global.fetch.mock.calls.map(([url])=>url)).toEqual(['/api/v1/outreach/sequences/template-metadata-updates/context','/api/v1/outreach/sequences/template-metadata-updates']);
  expect(JSON.parse(original.content_json)).toEqual({...reviewedTemplateMetadata(row()),template_id:row().id,name:'Renamed ☕',description:''});
  expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);expect(saved).toHaveBeenCalledTimes(1);
  expect(readReferences()).toEqual([]);expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('Renamed');
  expect(original.scope_digest).not.toBe(JSON.parse(original.content_json).scope_digest);
});

it.each(['network','202','201','wrong_input','wrong_native','wrong_revision','extra','malformed'])('unknown %s can recover only original status without POST replay',async(fault)=>{
  post=async body=>{if(fault==='network')throw new Error('lost');const data=receipt(body);
    if(fault==='wrong_input')data.input_digest='e'.repeat(64);if(fault==='wrong_native')data.identity_digest='e'.repeat(64);
    if(fault==='wrong_revision')data.new_revision=2;if(fault==='extra')data.name='not in receipt';
    if(fault==='malformed')return {ok:true,status:200,json:async()=>{throw new Error('json');}};
    return response(data,fault==='202'?202:fault==='201'?201:200);};
  await mount();await act(async()=>button('Save details').click());
  expect(container.textContent).toContain('Earlier update is unconfirmed');expect(button('Cancel').disabled).toBe(true);expect(saved).not.toHaveBeenCalled();
  await act(async()=>{button('Check original update status').click();button('Check original update status').click();});
  expect(saved).toHaveBeenCalledTimes(1);expect(refresh).not.toHaveBeenCalled();
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
  const last=global.fetch.mock.calls.at(-1)[0];expect(last).toContain(request);expect(last).toContain('input_digest='+original.input_digest);
});

it.each([404,403,503,202])('status %s retains original reference and never admits a fresh request',async(code)=>{
  post=async()=>{throw new Error('unknown');};status=async()=>response({},code);
  await mount();await act(async()=>button('Save details').click());
  await act(async()=>button('Check original update status').click());
  expect(button('Save details').disabled).toBe(true);expect(button('Cancel').disabled).toBe(true);
  expect(global.crypto.randomUUID).toHaveBeenCalledTimes(1);expect(refresh).not.toHaveBeenCalled();expect(saved).not.toHaveBeenCalled();
});

it.each(['token','props','unmount'])('changed %s during preparation prevents POST',async(kind)=>{
  let release;global.crypto.subtle.digest=jest.fn(()=>new Promise(resolve=>{release=()=>resolve(new Uint8Array(32).buffer);}));
  await mount();await act(async()=>button('Save details').click());
  if(kind==='token')localStorage.setItem('token','other');else if(kind==='props')await mount({...row(),name:'Other'});
  else {await act(async()=>root.unmount());root=createRoot(container);}
  await act(async()=>release());expect(original).toBeNull();expect(saved).not.toHaveBeenCalled();
  if(kind!=='unmount')expect(button('Cancel').disabled).toBe(false);
});

it('account changes after status JSON prevent confirmation',async()=>{
  post=async()=>{throw new Error('unknown');};status=async()=>({ok:true,status:200,json:async()=>{localStorage.setItem('token','other');return receipt(original);}});
  await mount();await act(async()=>button('Save details').click());await act(async()=>button('Check original update status').click());
  expect(saved).not.toHaveBeenCalled();expect(button('Save details').disabled).toBe(true);
});

it('definite preparation failure allows correction but creates no request reference',async()=>{
  global.crypto.subtle.digest=jest.fn(async()=>{throw new Error('crypto');});await mount();await act(async()=>button('Save details').click());
  expect(original).toBeNull();expect(button('Save details').disabled).toBe(false);expect(button('Cancel').disabled).toBe(false);
  expect(container.textContent).toContain('Could not prepare');expect(global.crypto.randomUUID).not.toHaveBeenCalled();
});

it('receipt matcher denies missing native proof and invented content',()=>{
  const captured={...reviewedTemplateMetadata(row()),template_id:row().id,name:'Original',description:''};
  const body={contract_version:1,workspace_id:'workspace',request_id:request,scope_digest:context.scope_digest,input_digest:'0'.repeat(64),content_json:JSON.stringify(captured)};
  expect(matchesMetadataUpdateReceipt(receipt(body),body,captured)).toBe(true);
  expect(matchesMetadataUpdateReceipt({...receipt(body),name:'Other'},body,captured)).toBe(false);
  expect(matchesMetadataUpdateReceipt({...receipt(body),review_scope_digest:'bad'},body,captured)).toBe(false);
});

it('persists and verifies the locator before POST without retaining original edit content',async()=>{
  post=async body=>{expect(readReferences()).toEqual([{contract_version:1,workspace_id:body.workspace_id,
    scope_digest:body.scope_digest,request_id:body.request_id,input_digest:body.input_digest}]);
    expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('Starter');throw Error('lost');};
  await mount();await act(async()=>button('Save details').click());
  expect(readReferences()).toHaveLength(1);expect(button('Save details').disabled).toBe(true);
});

it('write failure before transport and cleanup failure after a receipt both retain a hold',async()=>{
  const native=Storage.prototype.setItem;const writer=jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){
    if(key===STORAGE_KEY)throw Error('storage blocked');return native.call(this,key,value);});
  try {
    await mount();await act(async()=>button('Save details').click());expect(original).toBeNull();expect(saved).not.toHaveBeenCalled();
    expect(button('Save details').disabled).toBe(true);
  } finally {writer.mockRestore();}
  // Explicit same-original status remains the only route out of the view hold.
  expect(button('Check original update status')).toBeDefined();
});

it('a newer stored locator cannot be cleared by an older successful response',async()=>{
  post=async body=>{sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[{
    contract_version:1,workspace_id:body.workspace_id,scope_digest:body.scope_digest,
    request_id:body.request_id,input_digest:'e'.repeat(64)}]}));return response(receipt(body));};
  await mount();await act(async()=>button('Save details').click());
  expect(saved).not.toHaveBeenCalled();expect(readReferences()[0].input_digest).toBe('e'.repeat(64));expect(button('Cancel').disabled).toBe(true);
});

it('a competing original admitted during hashing prevents a second POST',async()=>{
  global.crypto.subtle.digest=jest.fn(async()=>{
    storeReference({contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
      request_id:'11111111-1111-1111-1111-111111111111',input_digest:'a'.repeat(64)});
    return new Uint8Array(32).buffer;});
  await mount();await act(async()=>button('Save details').click());expect(original).toBeNull();expect(readReferences()).toHaveLength(1);
});

it('normal token refresh can check the same original scope using current credentials',async()=>{
  localStorage.setItem('token','before-refresh');post=async()=>{throw new Error('lost');};
  await mount();await act(async()=>button('Save details').click());localStorage.setItem('token','after-refresh');
  await act(async()=>button('Check original update status').click());
  expect(saved).toHaveBeenCalledTimes(1);
  expect(global.fetch.mock.calls.at(-1)[1].headers.Authorization).toBe('Bearer after-refresh');
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
});

it('foreign current context does not request an original outcome or unlock editing',async()=>{
  post=async()=>{throw new Error('lost');};await mount();await act(async()=>button('Save details').click());
  global.fetch.mockImplementation(async()=>response({...context,scope_digest:'e'.repeat(64)}));
  localStorage.setItem('token','other-account');await act(async()=>button('Check original update status').click());
  expect(global.fetch.mock.calls.at(-1)[0]).toContain('/context');expect(saved).not.toHaveBeenCalled();expect(button('Save details').disabled).toBe(true);
});
