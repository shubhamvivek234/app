import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import OutreachCampaigns from './OutreachCampaigns';

jest.mock('sonner',()=>({toast:{success:jest.fn(),error:jest.fn()}}));
const review={contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',
  review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),
  update_authorized:false,deletion_authorized:false,execution_authorized:false};
const row=()=>({id:'tpl_custom_012345abcd',name:'Shared starter',is_custom:true,
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  metadata_review:{...review},graph_review:{...review},deletion_review:{...review},
  workspace_access:{contract_version:1,workspace_id:'workspace',visibility:'workspace',created_by_you:true,
    can_configure:true,can_edit:true,can_delete:false,execution_authorized:false}});
let root,container,record;
const button=label=>[...container.querySelectorAll('button')].find(b=>b.textContent.trim()===label);
const metadata=()=>container.querySelector('[aria-label="Edit template details Shared starter"]');
const graph=()=>container.querySelector('[aria-label="Edit template sequence Shared starter"]');
const deletion=()=>container.querySelector('[aria-label="Delete template Shared starter"]');
const response=data=>({ok:true,status:200,json:async()=>data});
const open=async()=>{await act(async()=>root.render(<OutreachCampaigns/>));await act(async()=>button('Browse winning templates').click());};
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;localStorage.clear();sessionStorage.clear();
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);record=row();
  global.fetch=jest.fn(async url=>response(url.endsWith('/sequences/templates')?[record]:[]));
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

test('editor can configure and edit a workspace template but creator attribution cannot delete',async()=>{
  await open();expect(container.textContent).toContain('Workspace template · Saved by you');
  expect(button('Use').disabled).toBe(false);expect(metadata().disabled).toBe(false);expect(graph().disabled).toBe(false);
  expect(deletion().disabled).toBe(true);await act(async()=>deletion().click());
  expect(global.fetch).toHaveBeenCalledTimes(2);
  await act(async()=>metadata().click());expect(button('Save details')).toBeDefined();
});
test('viewer can inspect shared graph without any mutation controls or context requests',async()=>{
  Object.assign(record.workspace_access,{can_configure:false,can_edit:false,can_delete:false});await open();
  expect(container.textContent).toContain('Ready to configure');expect(button('View only').disabled).toBe(true);
  expect(metadata().disabled).toBe(true);expect(graph().disabled).toBe(true);expect(deletion().disabled).toBe(true);
  await act(async()=>{metadata().click();graph().click();deletion().click();button('View only').click();});
  expect(global.fetch).toHaveBeenCalledTimes(2);
});
test('explicit catalog reload reflects a changed role without creator ownership overrides',async()=>{
  Object.assign(record.workspace_access,{can_configure:false,can_edit:false});await open();
  expect(button('View only').disabled).toBe(true);
  record=row();await act(async()=>button('Reload templates').click());
  expect(button('Use').disabled).toBe(false);expect(metadata().disabled).toBe(false);expect(deletion().disabled).toBe(true);
});
test.each(['missing','version','coercion','extra'])('unsupported %s access keeps current template visible but held',async(kind)=>{
  if(kind==='missing')delete record.workspace_access;
  else Object.assign(record.workspace_access,kind==='version'?{contract_version:2}:kind==='coercion'?{can_delete:'true'}:{extra:true});
  await open();expect(container.textContent).toContain('Shared starter');expect(container.textContent).toContain('Access needs review');
  expect(metadata().disabled).toBe(true);expect(graph().disabled).toBe(true);expect(deletion().disabled).toBe(true);
  expect(button('View only').disabled).toBe(true);
});
test('token change after catalog prevents using or editing the earlier account catalog',async()=>{
  await open();localStorage.setItem('token','another-account');
  await act(async()=>{metadata().click();graph().click();button('Use').click();});
  expect(button('Save details')).toBeUndefined();expect(button('Save template sequence')).toBeUndefined();
  expect(global.fetch).toHaveBeenCalledTimes(2);
});
test('token change while catalog JSON resolves cannot publish stale access',async()=>{
  global.fetch=jest.fn(async url=>url.endsWith('/sequences/templates')?{ok:true,status:200,json:async()=>{
    localStorage.setItem('token','another-account');return [record];}}:response([]));
  await open();expect(container.textContent).toContain('Template account changed');expect(metadata()).toBeNull();
});
test.each(['draft','sequence'])('token change during %s prevents later template transport or navigation',async(stage)=>{
  let finish;const opened=jest.fn();
  global.fetch=jest.fn(async(url,options={})=>{
    if(url.endsWith('/sequences/templates'))return response([record]);
    if(options.method==='POST') {
      if(stage==='draft'&&url.endsWith('/auto-draft')||stage==='sequence'&&url.endsWith('/sequences')) {
        return new Promise(resolve=>{finish=()=>resolve(response({id:'saved-draft'}));});
      }
      return response({id:'saved-draft'});
    }
    return response([]);
  });
  await act(async()=>root.render(<OutreachCampaigns onOpenWizard={opened}/>));
  await act(async()=>button('Browse winning templates').click());await act(async()=>button('Use').click());
  localStorage.setItem('token','other');await act(async()=>finish());
  expect(opened).not.toHaveBeenCalled();
  expect(global.fetch.mock.calls.filter(([,opts])=>opts?.method==='POST')).toHaveLength(stage==='draft'?1:2);
});
