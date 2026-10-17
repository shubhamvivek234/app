import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { TextEncoder } from 'util';
import { webcrypto } from 'crypto';
import TemplateGraphEditor from './TemplateGraphEditor';
import {reviewedTemplateGraph} from '../utils/templateGraph';

jest.mock('./sequence/SequenceCanvas',()=>{
  const R=require('react');return ({templateTree,onRegisterTemplateSnapshot})=>{
    R.useEffect(()=>{onRegisterTemplateSnapshot(()=>global.__graphDraft||{nodes:templateTree,edges:[],tree:templateTree});
      return()=>onRegisterTemplateSnapshot(null);},[templateTree,onRegisterTemplateSnapshot]);
    return R.createElement('div',{'data-testid':'template-draft-canvas'},templateTree[0]?.title);
  };
});
const node={id:'root',type:'visit_profile',title:'Original',delay_hours:0,config:{}};
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',nodes:[node],edges:[],tree:[node],
  graph_review:{contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
    workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)}});
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>({...Object.fromEntries(Object.entries(body).filter(([k])=>k!=='graph_json')),
  status:'updated',template_id:row().id,new_revision:1,new_review_digest:'d'.repeat(64),graph_digest:'e'.repeat(64)});
let container,root,saved,close,refresh,hashing;
const button=label=>[...container.querySelectorAll('button')].find(item=>item.textContent.trim()===label);
const mount=async(record=row())=>act(async()=>root.render(<TemplateGraphEditor template={record} onSaved={saved} onClose={close} onRefresh={refresh} />));
// Native WebCrypto completes outside React's scheduler. Await its actual promise,
// so CPU load cannot make assertions race the transport continuation.
const saveAndHash=async(twice=false)=>act(async()=>{button('Save template sequence').click();if(twice)button('Save template sequence').click();await hashing;});
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;hashing=null;
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:(...args)=>{hashing=webcrypto.subtle.digest(...args);return hashing;}}}});
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);saved=jest.fn();close=jest.fn();refresh=jest.fn();localStorage.clear();});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;delete global.__graphDraft;});

it('hashes and submits the exact current canvas snapshot once, requiring exact receipt',async()=>{
  let body;global.fetch=jest.fn(async(url,options)=>{body=JSON.parse(options.body);return response(receipt(body));});
  const record=row();await mount(record);global.__graphDraft={nodes:[{...node,delay_hours:24}],edges:[],tree:[{...node,delay_hours:24}]};
  await saveAndHash(true);
  expect(global.fetch).toHaveBeenCalledTimes(1);expect(JSON.parse(body.graph_json)).toEqual(global.__graphDraft);
  expect(body.input_digest).toBe(Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(body.graph_json))).toString('hex'));
  expect({...body,graph_json:undefined,input_digest:undefined}).toEqual({...reviewedTemplateGraph(record),graph_json:undefined,input_digest:undefined});
  expect(saved).toHaveBeenCalledTimes(1);
});

it.each(['network','202','201','wrong_digest','wrong_revision','wrong_native','extra','malformed'])('holds %s without retry or automatic replacement',async(fault)=>{
  global.fetch=jest.fn(async(url,options)=>{
    if(fault==='network')throw new Error('network');const body=JSON.parse(options.body),data=receipt(body);
    if(fault==='wrong_digest')data.input_digest='f'.repeat(64);
    if(fault==='wrong_revision')data.new_revision=2;
    if(fault==='wrong_native')data.identity_digest='f'.repeat(64);
    if(fault==='extra')data.execution_authorized=true;
    if(fault==='malformed')return {ok:true,status:200,json:async()=>{throw new Error('bad JSON');}};
    return response(data,fault==='202'?202:fault==='201'?201:200);
  });await mount();await saveAndHash();
  expect(container.textContent).toContain('Earlier sequence update is unconfirmed');expect(saved).not.toHaveBeenCalled();
  expect(button('Save template sequence').disabled).toBe(true);expect(button('Cancel').disabled).toBe(true);
  expect(container.querySelector('[data-testid="template-draft-canvas"]')).toBeNull();
  await act(async()=>button('Reload and review templates').click());expect(refresh).toHaveBeenCalledTimes(1);expect(global.fetch).toHaveBeenCalledTimes(1);
});

it.each(['token','unmount','props'])('context change during hashing prevents graph PATCH: %s',async(change)=>{
  let release;const digest=jest.fn(()=>new Promise(resolve=>{release=()=>resolve(new Uint8Array(32).buffer);}));
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest}}});global.fetch=jest.fn();await mount();
  await act(async()=>{button('Save template sequence').click();await Promise.resolve();});
  if(change==='token')localStorage.setItem('token','new-account');
  else if(change==='props')await mount({...row(),name:'Replacement'});
  else {await act(async()=>root.unmount());root=createRoot(container);}
  await act(async()=>release());expect(global.fetch).not.toHaveBeenCalled();expect(saved).not.toHaveBeenCalled();
});

it('late receipt after unmount never invokes parent completion',async()=>{
  let release;global.fetch=jest.fn(async(url,options)=>new Promise(resolve=>{release=()=>resolve(response(receipt(JSON.parse(options.body))));}));
  await mount();await saveAndHash();await act(async()=>root.unmount());root=createRoot(container);
  await act(async()=>release());expect(saved).not.toHaveBeenCalled();
});

it('definite hash preparation failure preserves draft and allows correction without PATCH',async()=>{
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:async()=>{throw new Error('crypto unavailable');}}}});
  global.fetch=jest.fn();await mount();await act(async()=>button('Save template sequence').click());
  expect(container.querySelector('[data-testid="template-draft-canvas"]')).not.toBeNull();expect(button('Cancel').disabled).toBe(false);
  expect(container.textContent).toContain('Could not prepare');expect(global.fetch).not.toHaveBeenCalled();
});

it('reload has a synchronous latch and retains the hold on rejection',async()=>{
  global.fetch=jest.fn().mockRejectedValue(new Error('network'));let reject;refresh.mockImplementation(()=>new Promise((resolve,fail)=>{reject=fail;}));
  await mount();await saveAndHash();
  await act(async()=>{button('Reload and review templates').click();button('Reload and review templates').click();});expect(refresh).toHaveBeenCalledTimes(1);
  await act(async()=>reject(new Error('refresh failed')));expect(button('Save template sequence').disabled).toBe(true);
});
