import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { toast } from 'sonner';
import OutreachCampaigns from './OutreachCampaigns';
import { reviewedTemplateDeletion } from '../utils/templateDeletion';

jest.mock('sonner', () => ({toast:{success:jest.fn(),error:jest.fn()}}));
const row = (change={}) => ({ id:'tpl_custom_012345abcd',name:'Reviewed starter',is_custom:true,
  nodes:[{id:'root',type:'visit_profile'}],edges:[],tree:[{id:'root',type:'visit_profile'}],
  compatibility:{contract_version:1,valid:true,configuration_available:true,execution_authorized:false},
  deletion_review:{contract_version:1,reviewable:true,revision:0,workspace_id:'workspace',
    review_digest:'a'.repeat(64),identity_digest:'b'.repeat(64),scope_digest:'c'.repeat(64),
    deletion_authorized:false,execution_authorized:false},...change });
const response = (body,ok=true,status=200) => ({ok,status,json:async()=>body});
const receipt = (record) => ({...reviewedTemplateDeletion(record),status:'deleted',template_id:record.id});
let container,root;
const button = (text) => [...container.querySelectorAll('button')].find((item)=>item.textContent.trim()===text);
const deleteButton = () => container.querySelector('[aria-label="Delete template Reviewed starter"]');
async function open() {
  await act(async()=>root.render(<OutreachCampaigns onOpenWizard={jest.fn()} />));
  await act(async()=>button('Browse winning templates').click());
}
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  toast.success.mockClear();toast.error.mockClear();
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;});

it('sends the exact reviewed context and removes only after exact acknowledgement',async()=>{
  const record=row();global.fetch=jest.fn().mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(response([record])).mockResolvedValueOnce(response(receipt(record)));
  await open();await act(async()=>deleteButton().click());
  expect(global.fetch.mock.calls[2][0]).toBe('/api/v1/outreach/sequences/templates/'+record.id+'/reviewed');
  expect(global.fetch.mock.calls[2][1].method).toBe('DELETE');
  expect(JSON.parse(global.fetch.mock.calls[2][1].body)).toEqual(reviewedTemplateDeletion(record));
  expect(deleteButton()).toBeNull();expect(toast.success).toHaveBeenCalledWith('Reviewed template deleted');
});

it.each([null,{contract_version:1,reviewable:false}])('holds custom templates without a native review %#',async(review)=>{
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([row({deletion_review:review})]));
  await open();expect(deleteButton().disabled).toBe(true);expect(global.fetch).toHaveBeenCalledTimes(2);
});

it.each(['network','404','accepted202','created201','wrong_revision','wrong_native','wrong_scope','legacy_success','extra_grant'])('retains unknown/invalid %s outcomes without replay',async(kind)=>{
  const record=row();let reply=receipt(record);
  if(kind==='wrong_revision')reply.revision=1;
  if(kind==='wrong_native')reply.identity_digest='d'.repeat(64);
  if(kind==='wrong_scope')reply.scope_digest='d'.repeat(64);
  if(kind==='legacy_success')reply={status:'success'};
  if(kind==='extra_grant')reply.execution_authorized=true;
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([record]));
  if(kind==='network')global.fetch.mockRejectedValueOnce(new Error('unknown transport'));
  else global.fetch.mockResolvedValueOnce(response(reply,kind!=='404',kind==='accepted202'?202:kind==='created201'?201:200));
  await open();await act(async()=>deleteButton().click());
  expect(container.textContent).toContain('Earlier deletion is unconfirmed');
  expect(deleteButton().disabled).toBe(true);expect(button('Use').disabled).toBe(true);
  expect(global.fetch).toHaveBeenCalledTimes(3);expect(toast.success).not.toHaveBeenCalled();
});

it('blocks overlapping delete and Use while awaiting the original receipt',async()=>{
  const record=row();let resolve;
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([record]))
    .mockImplementationOnce(()=>new Promise((done)=>{resolve=done;}));
  await open();await act(async()=>{deleteButton().click();deleteButton().click();button('Use').click();});
  expect(global.fetch).toHaveBeenCalledTimes(3);expect(button('← Campaigns').disabled).toBe(true);
  await act(async()=>resolve(response(receipt(record))));
  expect(deleteButton()).toBeNull();
});

it('explicit catalog reload does not confirm a missing template or replay DELETE',async()=>{
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([row()]))
    .mockRejectedValueOnce(new Error('unknown')).mockResolvedValueOnce(response([]));
  await open();await act(async()=>deleteButton().click());
  await act(async()=>button('Reload and review templates').click());
  expect(container.textContent).toContain('Earlier deletion is unconfirmed');
  expect(container.textContent).toContain('A refreshed catalog is not a deletion receipt');
  expect(container.textContent).toContain('No sequence templates are available');
  expect(global.fetch.mock.calls.filter(([,options])=>options?.method==='DELETE')).toHaveLength(1);
  expect(toast.success).not.toHaveBeenCalled();
});

it('only a fresh deliberate delete after reload can target a replacement native record',async()=>{
  const original=row(),replacement=row({deletion_review:{...row().deletion_review,identity_digest:'e'.repeat(64),review_digest:'f'.repeat(64)}});
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([original]))
    .mockRejectedValueOnce(new Error('unknown')).mockResolvedValueOnce(response([replacement]))
    .mockResolvedValueOnce(response(receipt(replacement)));
  await open();await act(async()=>deleteButton().click());
  await act(async()=>button('Reload and review templates').click());
  expect(global.fetch).toHaveBeenCalledTimes(4);expect(deleteButton().disabled).toBe(false);
  expect(toast.success).not.toHaveBeenCalled();
  await act(async()=>deleteButton().click());
  expect(JSON.parse(global.fetch.mock.calls[4][1].body).identity_digest).toBe('e'.repeat(64));
  expect(deleteButton()).toBeNull();
});

it('failed explicit reload retains the deletion hold',async()=>{
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([row()]))
    .mockRejectedValueOnce(new Error('unknown')).mockResolvedValueOnce(response({},false));
  await open();await act(async()=>deleteButton().click());
  await act(async()=>button('Reload and review templates').click());
  expect(container.textContent).toContain('Earlier deletion is unconfirmed');
  expect(container.textContent).toContain('Could not load sequence templates');
  expect(global.fetch.mock.calls.filter(([,options])=>options?.method==='DELETE')).toHaveLength(1);
});

it('does not apply receipt or toast after unmount',async()=>{
  const record=row();let resolve;
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([record]))
    .mockImplementationOnce(()=>new Promise((done)=>{resolve=done;}));
  await open();await act(async()=>deleteButton().click());await act(async()=>root.unmount());root=createRoot(container);
  await act(async()=>resolve(response(receipt(record))));
  expect(toast.success).not.toHaveBeenCalled();expect(global.fetch).toHaveBeenCalledTimes(3);
});

it('latches explicit refresh synchronously against a competing catalog retry',async()=>{
  let resolve;
  global.fetch=jest.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([row()]))
    .mockRejectedValueOnce(new Error('unknown')).mockResolvedValueOnce(response({},false))
    .mockImplementationOnce(()=>new Promise((done)=>{resolve=done;}));
  await open();await act(async()=>deleteButton().click());
  await act(async()=>button('Reload and review templates').click());
  expect(button('Retry templates')).toBeDefined();
  await act(async()=>{button('Reload and review templates').click();button('Retry templates').click();});
  expect(global.fetch).toHaveBeenCalledTimes(5);
  await act(async()=>resolve(response([row()])));
  expect(deleteButton().disabled).toBe(false);
  expect(container.textContent).toContain('Earlier deletion is unconfirmed');
});
