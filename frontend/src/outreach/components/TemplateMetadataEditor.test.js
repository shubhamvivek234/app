import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {TextEncoder} from 'util';
import TemplateMetadataEditor from './TemplateMetadataEditor';
import {reviewedTemplateMetadata,matchesMetadataReceipt} from '../utils/templateMetadata';

const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',
  metadata_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const context={contract_version:1,workspace_id:'workspace',scope_digest:'f'.repeat(64),execution_authorized:false};
const reply=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>{const old=JSON.parse(body.content_json);return {contract_version:1,workspace_id:body.workspace_id,
  scope_digest:body.scope_digest,request_id:body.request_id,input_digest:body.input_digest,status:'updated',template_id:old.template_id,
  revision:old.revision,review_digest:old.review_digest,identity_digest:old.identity_digest,review_scope_digest:old.scope_digest,
  new_revision:old.revision+1,new_review_digest:'d'.repeat(64)};};
let container,root,saved,close,post,status,body,contextReply;
const button=text=>[...container.querySelectorAll('button')].find(item=>item.textContent.trim()===text);
const render=async(record=row())=>act(async()=>root.render(<TemplateMetadataEditor template={record} onSaved={saved} onClose={close}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;localStorage.clear();
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID:()=> '01234567-89ab-cdef-0123-456789abcdef',subtle:{digest:async()=>new Uint8Array(32).buffer}}});
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);saved=jest.fn();close=jest.fn();
  contextReply=reply(context);post=async b=>reply(receipt(b));status=async()=>reply(receipt(body));body=null;
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/context'))return contextReply;
    if(options.method==='POST'){body=JSON.parse(options.body);return post(body);}
    return status();});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

it('single flight freezes inputs while preparation and original transport are pending',async()=>{
  let resolve;post=b=>new Promise(done=>{resolve=()=>done(reply(receipt(b)));});await render();
  await act(async()=>{button('Save details').click();button('Save details').click();});
  expect(container.querySelector('input').disabled).toBe(true);expect(button('Cancel').disabled).toBe(true);
  expect(global.fetch.mock.calls.filter(([,opts])=>opts.method==='POST')).toHaveLength(1);
  await act(async()=>resolve());expect(saved).toHaveBeenCalledTimes(1);
});
it.each(['unmount','props','token'])('late original transport cannot confirm after %s changes',async(change)=>{
  let resolve;post=b=>new Promise(done=>{resolve=()=>done(reply(receipt(b)));});await render();await act(async()=>button('Save details').click());
  if(change==='unmount'){await act(async()=>root.unmount());root=createRoot(container);}
  else if(change==='props')await render({...row(),name:'Replacement'});else localStorage.setItem('token','other');
  await act(async()=>resolve());expect(saved).not.toHaveBeenCalled();
});
it.each([201,202,503])('context HTTP%s is a definite pretransport failure with no update UUID',async(code)=>{
  contextReply=reply(context,code);await render();await act(async()=>button('Save details').click());
  expect(body).toBeNull();expect(button('Save details').disabled).toBe(false);expect(saved).not.toHaveBeenCalled();
});
it('invalid names and absent native reviews never start preparation',async()=>{
  await render({...row(),name:'   '});expect(button('Save details').disabled).toBe(true);
  await act(async()=>button('Save details').click());expect(global.fetch).not.toHaveBeenCalled();
  await render({...row(),metadata_review:null});expect(button('Save details').disabled).toBe(true);
});
it('status inspection latches duplicate clicks and retains hold after rejection',async()=>{
  post=async()=>{throw new Error('unknown');};let reject;status=()=>new Promise((resolve,fail)=>{reject=fail;});
  await render();await act(async()=>button('Save details').click());
  await act(async()=>{button('Check original update status').click();button('Check original update status').click();});
  expect(global.fetch).toHaveBeenCalledTimes(4);await act(async()=>reject(new Error('offline')));
  expect(button('Save details').disabled).toBe(true);expect(button('Cancel').disabled).toBe(true);
});
it('a mismatched status receipt cannot release the original unknown hold',async()=>{
  post=async()=>{throw new Error('unknown');};status=async()=>reply({...receipt(body),review_digest:'e'.repeat(64)});
  await render();await act(async()=>button('Save details').click());await act(async()=>button('Check original update status').click());
  expect(saved).not.toHaveBeenCalled();expect(button('Save details').disabled).toBe(true);
});
it('legacy metadata proof validation remains strict for its retained API',()=>{
  const record=row(),captured={...reviewedTemplateMetadata(record),name:'Renamed',description:''};
  const legacy={...captured,status:'updated',template_id:record.id,new_revision:1,new_review_digest:'d'.repeat(64)};
  expect(matchesMetadataReceipt(legacy,record.id,captured)).toBe(true);
  expect(matchesMetadataReceipt({...legacy,new_review_digest:'bad'},record.id,captured)).toBe(false);
  expect(matchesMetadataReceipt(null,record.id,captured)).toBe(false);
  expect(reviewedTemplateMetadata({...record,is_custom:false})).toBeNull();
  expect(reviewedTemplateMetadata({...record,name:'  '})).toBeNull();
  expect(reviewedTemplateMetadata({...record,metadata_review:{...record.metadata_review,revision:Number.MAX_SAFE_INTEGER}})).toBeNull();
});
