import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {TextEncoder} from 'util';
import {webcrypto} from 'crypto';
import {toast} from 'sonner';
import OutreachCampaigns from './OutreachCampaigns';

jest.mock('sonner',()=>({toast:{success:jest.fn(),error:jest.fn()}}));
const node={id:'root',type:'visit_profile',title:'Original visit',delay_hours:5,config:{}};
const review={contract_version:1,reviewable:true,update_authorized:false,execution_authorized:false,
  workspace_id:'workspace',revision:0,review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64)};
const row=()=>({id:'tpl_custom_012345abcd',is_custom:true,name:'Starter',description:'Original',nodes:[node],edges:[],tree:[node],graph_review:review,
  metadata_review:{...review,scope_digest:'e'.repeat(64)},deletion_review:{...review,update_authorized:undefined,deletion_authorized:false,scope_digest:'f'.repeat(64)},
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false}});
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const receipt=body=>({...Object.fromEntries(Object.entries(body).filter(([key])=>key!=='graph_json')),
  status:'updated',template_id:row().id,new_revision:1,new_review_digest:'d'.repeat(64),graph_digest:'e'.repeat(64)});
let container,root,catalog,patch,catalogReads,hashing;
const button=label=>[...container.querySelectorAll('button')].find(item=>item.textContent.trim()===label);
const edit=()=>container.querySelector('[aria-label="Edit template sequence Starter"]');
const mutations=()=>global.fetch.mock.calls.filter(([,options])=>options?.method && options.method!=='GET');
const saveAndHash=async()=>act(async()=>{button('Save template sequence').click();await hashing;});
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;global.TextEncoder=TextEncoder;hashing=null;
  Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:(...args)=>{hashing=webcrypto.subtle.digest(...args);return hashing;}}}});
  localStorage.clear();sessionStorage.clear();container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  catalog=async()=>response([row()]);patch=async body=>response(receipt(body));catalogReads=0;toast.success.mockClear();toast.error.mockClear();
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/campaigns'))return response([]);
    if(url.includes('sequence-capabilities'))return response({capabilities:[]});
    if(url.endsWith('/templates')){catalogReads++;return catalog();}
    if(url.endsWith('/graph-reviewed'))return patch(JSON.parse(options.body));
    throw new Error('Unexpected request '+url);
  });
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});
async function open(){await act(async()=>root.render(<OutreachCampaigns onOpenWizard={jest.fn()} />));await act(async()=>button('Browse winning templates').click());}

it('older catalogs require a dedicated graph review without disabling ordinary Use',async()=>{
  catalog=async()=>response([{...row(),graph_review:null}]);await open();expect(edit().disabled).toBe(true);expect(button('Use').disabled).toBe(false);
});

it('graph editing excludes Use/Delete/metadata editing and can be cancelled without a write',async()=>{
  await open();await act(async()=>{edit().click();button('Use').click();container.querySelector('[aria-label="Edit template details Starter"]').click();});
  expect(button('Use').disabled).toBe(true);expect(container.querySelector('[aria-label="Delete template Starter"]').disabled).toBe(true);
  expect(container.querySelector('[aria-label="Edit template details Starter"]').disabled).toBe(true);expect(mutations()).toHaveLength(0);
  await act(async()=>button('Cancel').click());expect(button('Use').disabled).toBe(false);expect(mutations()).toHaveLength(0);
});

it('actual canvas changes reach the frozen PATCH and exact success reloads fresh reviews',async()=>{
  let body;patch=async captured=>{body=captured;catalog=async()=>response([{...row(),
    graph_review:{...review,revision:1,review_digest:'d'.repeat(64)},tree:JSON.parse(body.graph_json).tree,nodes:JSON.parse(body.graph_json).nodes}]);return response(receipt(body));};
  await open();await act(async()=>edit().click());await act(async()=>container.querySelector('[title="Edit delay"]').click());
  const input=container.querySelector('input[type="number"]');
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'9');input.dispatchEvent(new Event('input',{bubbles:true}));});
  await act(async()=>container.querySelector('[title="Save delay"]').click());
  await saveAndHash();const graph=JSON.parse(body.graph_json);
  expect(graph.tree[0].delay_hours).toBe(9);expect(graph.nodes[0].delay_hours).toBe(9);
  expect(catalogReads).toBe(2);expect(toast.success).toHaveBeenCalledWith('Template sequence updated');expect(mutations()).toHaveLength(1);
  expect(button('Use').disabled).toBe(false);expect(container.querySelector('[aria-label="Edit template sequence"]')).toBeNull();
});

it('unknown graph save permits only explicit catalog inspection without PATCH replay',async()=>{
  patch=async()=>{throw new Error('unknown');};await open();await act(async()=>edit().click());await saveAndHash();
  expect(button('Use').disabled).toBe(true);catalog=async()=>response([{...row(),graph_review:{...review,revision:1,review_digest:'d'.repeat(64)}}]);
  await act(async()=>button('Reload and review templates').click());expect(container.textContent).toContain('The earlier sequence update is unconfirmed');
  expect(edit().disabled).toBe(false);expect(mutations()).toHaveLength(1);expect(toast.success).not.toHaveBeenCalled();
});

it('account change during graph reload cannot release the shared operation hold',async()=>{
  patch=async()=>{throw new Error('unknown');};await open();await act(async()=>edit().click());await saveAndHash();
  let resolve;catalog=()=>new Promise(done=>{resolve=done;});
  await act(async()=>{button('Reload and review templates').click();button('Reload and review templates').click();});expect(catalogReads).toBe(2);
  await act(async()=>{localStorage.setItem('token','changed');resolve(response([{...row(),name:'Wrong account'}]));});
  expect(container.textContent).not.toContain('Wrong account');expect(button('Save template sequence').disabled).toBe(true);expect(button('← Campaigns').disabled).toBe(true);
});
