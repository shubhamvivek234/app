import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { TextEncoder } from 'util';
import { webcrypto } from 'crypto';
import OutreachCampaignWizard from './OutreachCampaignWizard';
import { templateInputDigest, validSaveContext, validSaveReceipt } from '../hooks/useTemplateSave';
import { STORAGE_KEY, readReferences } from '../utils/templateSaveReferences';

jest.mock('../components/sequence/SequenceCanvas', () => {
  const MockReact=require('react');
  return ({onRegisterSave,campaignId}) => {
    MockReact.useEffect(() => { onRegisterSave(() => globalThis.__templateSequenceSave?.() ?? Promise.resolve(true));
      return () => onRegisterSave(null); }, [onRegisterSave]);
    return MockReact.createElement('div',{'data-testid':'template-sequence-campaign'},campaignId);
  };
});
jest.mock('../components/ImportLeadsModal', () => () => null);
jest.mock('../components/ConnectLinkedInModal', () => () => null);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
const context = { contract_version: 1, workspace_id: 'workspace', scope_digest: 'a'.repeat(64), execution_authorized: false };
const node = { id: 'root', type: 'visit_profile', delay_hours: 0, config: {} };
const receipt = (body) => ({ ...Object.fromEntries(['contract_version','workspace_id','scope_digest','request_id','input_digest'].map((key) => [key, body[key]])),
  status: 'saved', template_id: 'tpl_custom_012345abcd', template_revision: 1,
  template_identity_digest: 'b'.repeat(64), template_review_digest: 'c'.repeat(64) });
const response = (data, status = 200) => ({ ok: status === 200, status, json: async () => data });
let container; let root; let post; let status; let captured; let contextResult; let digests;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  global.TextEncoder = TextEncoder;
  digests = [];
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: {
    randomUUID: () => webcrypto.randomUUID(),
    subtle: { digest: (...args) => { const pending = webcrypto.subtle.digest(...args); digests.push(pending); return pending; } },
  } });
  localStorage.clear();
  sessionStorage.clear();
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  captured = null; contextResult = response(context);
  post = async (body) => response(receipt(body)); status = async () => response(receipt(captured));
  global.fetch = jest.fn(async (url, options = {}) => {
    if (url.endsWith('/template-saves/context')) return contextResult;
    if (url.endsWith('/template-saves')) { captured = JSON.parse(options.body); return post(captured); }
    if (url.includes('/template-saves/')) return status();
    if (url.includes('/auto-draft')) return response({ id: 'campaign', name: 'Café template' });
    if (url.endsWith('/accounts')) return response([]);
    if (url.endsWith('/sequences/campaign')) return response({ nodes: [node], edges: [], tree: [node] });
    return response({ leads: [], total: 0 });
  });
});
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; container.remove(); delete global.fetch; delete globalThis.__templateSequenceSave; });
const mount = async (props={}) => act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialName="Café template" {...props} />));
const button = (label) => [...container.querySelectorAll('button')].find((item) => item.textContent.trim() === label);
const finishDigests = async () => act(async () => { await Promise.all(digests); });
const click = async (label) => { await act(async () => button(label).click()); await finishDigests(); };
const posts = () => global.fetch.mock.calls.filter(([url, options]) => url.endsWith('/template-saves') && options?.method === 'POST');

test('hashes exact Unicode bytes and confirms only a matching creation receipt', async () => {
  await mount(); await click('Save as template');
  expect(captured.input_digest).toBe(await templateInputDigest(captured.content_json));
  expect(JSON.parse(captured.content_json).name).toBe('Café template');
  expect(container.textContent).toContain('Original template save confirmed');
  expect(posts()).toHaveLength(1);
  expect(global.fetch.mock.calls.some(([url, options]) => url.endsWith('/sequences/templates') && options?.method === 'POST')).toBe(false);
});

test('lost response holds and an explicit status GET recovers without another POST', async () => {
  post = async () => { throw new Error('Lost response'); };
  await mount(); await click('Save as template');
  expect(button('Save as template').disabled).toBe(true);
  expect(container.textContent).toContain('unconfirmed');
  await click('Check save status');
  expect(container.textContent).toContain('Original template save confirmed');
  expect(posts()).toHaveLength(1);
});

test.each([404,403,409,503])('status %s retains unknown hold and never replays', async (code) => {
  post = async () => { throw new Error('Lost response'); }; status = async () => response({},code);
  await mount(); await click('Save as template'); await click('Check save status');
  expect(button('Save as template').disabled).toBe(true); expect(posts()).toHaveLength(1);
});

test.each([201,202])('non-200 %s receipt cannot confirm creation', async (code) => {
  post = async (body) => response(receipt(body),code);
  await mount(); await click('Save as template');
  expect(container.textContent).toContain('unconfirmed'); expect(button('Save as template').disabled).toBe(true);
});

test.each([{input_digest:'e'.repeat(64)},{request_id:'other'},{execution_authorized:true},{status:'pending'},{template_revision:2}])('mismatched/extra receipt stays held: %j', async (change) => {
  post = async (body) => response({...receipt(body),...change});
  await mount(); await click('Save as template');
  expect(container.textContent).toContain('unconfirmed');
});

test('rapid duplicate clicks share one original request', async () => {
  await mount(); await act(async () => { button('Save as template').click(); button('Save as template').click(); });
  await finishDigests();
  expect(posts()).toHaveLength(1);
});

test('unsupported context makes no save request', async () => {
  contextResult=response({...context,execution_authorized:true});
  await mount(); await click('Save as template');
  expect(posts()).toHaveLength(0); expect(container.textContent).toContain('unavailable');
});

test('departure during context load cannot start preparation or save', async () => {
  let release; contextResult=new Promise((resolve) => { release=resolve; });
  await mount(); await act(async () => button('Save as template').click());
  await act(async () => root.unmount()); root=null;
  await act(async () => release(response(context)));
  expect(posts()).toHaveLength(0);
});

test('token change during original response cannot display a stale confirmation', async () => {
  let release; post=(body) => new Promise((resolve) => { release=() => resolve(response(receipt(body))); });
  await mount(); await click('Save as template'); localStorage.setItem('token','changed');
  await act(async () => release());
  expect(container.textContent).toContain('unconfirmed');
});

test('receipt and context validators reject arrays and malformed envelopes', () => {
  expect(validSaveContext([])).toBe(false);
  expect(validSaveContext({...context,unknown:true})).toBe(false);
  expect(validSaveReceipt([],{})).toBe(false);
});

test.each(['unmount','token'])('delayed draft save cannot start dependent sequence requests after %s', async (change) => {
  await mount({initialStep:2});
  const original=global.fetch;let release;
  globalThis.__templateSequenceSave=jest.fn(async()=>true);
  global.fetch=jest.fn((url,options)=>url.includes('/auto-draft')
    ? new Promise(resolve=>{release=()=>resolve(response({id:'campaign',name:'Café template'}));}) : original(url,options));
  await act(async()=>button('Save as template').click());
  if(change==='unmount'){await act(async()=>root.unmount());root=null;}
  else localStorage.setItem('token','changed');
  await act(async()=>release());
  expect(globalThis.__templateSequenceSave).not.toHaveBeenCalled();
  expect(global.fetch.mock.calls.some(([url])=>url.endsWith('/sequences/campaign'))).toBe(false);
  expect(posts()).toHaveLength(0);
});

test.each(['unmount','token'])('delayed sequence save cannot fetch or create a template after %s', async (change) => {
  await mount({initialStep:2});let release;
  globalThis.__templateSequenceSave=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
  await act(async()=>button('Save as template').click());
  expect(globalThis.__templateSequenceSave).toHaveBeenCalledTimes(1);
  if(change==='unmount'){await act(async()=>root.unmount());root=null;}
  else localStorage.setItem('token','changed');
  await act(async()=>release(true));
  expect(global.fetch.mock.calls.some(([url])=>url.endsWith('/sequences/campaign'))).toBe(false);
  expect(posts()).toHaveLength(0);
});

test('requested campaign switch invalidates a save while the new campaign is still loading', async () => {
  const original=global.fetch;
  global.fetch=jest.fn((url,options)=>url.endsWith('/campaigns/A')?Promise.resolve(response({id:'A',name:'A',status:'draft'}))
    :url.endsWith('/campaigns/B')?new Promise(()=>{}) : original(url,options));
  await mount({campaignId:'A',initialStep:2});let release;
  globalThis.__templateSequenceSave=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
  const routed=global.fetch;
  global.fetch=jest.fn((url,options)=>url.includes('/auto-draft')?Promise.resolve(response({id:'A',name:'A'})):routed(url,options));
  await act(async()=>button('Save as template').click());
  await act(async()=>root.render(<OutreachCampaignWizard campaignId="B" initialStep={2}/>));
  await act(async()=>release(true));
  expect(global.fetch.mock.calls.some(([url])=>url.endsWith('/sequences/A'))).toBe(false);
  expect(posts()).toHaveLength(0);
});

test('a delayed original draft response cannot overwrite a fully loaded replacement campaign', async () => {
  const original=global.fetch;
  global.fetch=jest.fn((url,options)=>url.endsWith('/campaigns/A')?Promise.resolve(response({id:'A',name:'A',status:'draft'}))
    :url.endsWith('/campaigns/B')?Promise.resolve(response({id:'B',name:'B',status:'draft'})):original(url,options));
  await mount({campaignId:'A',initialStep:2});let release;
  const routed=global.fetch;
  global.fetch=jest.fn((url,options)=>url.includes('/auto-draft')?new Promise(resolve=>{release=()=>resolve(response({id:'A',name:'A'}));}):routed(url,options));
  await act(async()=>button('Save as template').click());
  await act(async()=>root.render(<OutreachCampaignWizard campaignId="B" initialStep={2}/>));
  expect(container.querySelector('[data-testid="template-sequence-campaign"]').textContent).toBe('B');
  await act(async()=>release());
  expect(container.querySelector('[data-testid="template-sequence-campaign"]').textContent).toBe('B');
  expect(global.fetch.mock.calls.some(([url])=>url.endsWith('/sequences/A'))).toBe(false);
  expect(posts()).toHaveLength(0);
});

test('an unknown save survives remount and recovers only by explicit original status GET',async()=>{
  post=async()=>{throw Error('lost');};await mount();await click('Save as template');
  const original=captured;expect(readReferences()[0].request_id).toBe(original.request_id);
  expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('Café');
  expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('content_json');
  await act(async()=>root.unmount());root=createRoot(container);await mount();
  expect(button('Save as template').disabled).toBe(true);expect(posts()).toHaveLength(1);
  await click('Check save status');expect(posts()).toHaveLength(1);expect(readReferences()).toEqual([]);
  expect(container.textContent).toContain('Original template save confirmed');
});

test('foreign scope references are preserved and never used for status',async()=>{
  const foreign={contract_version:1,workspace_id:'other',scope_digest:'f'.repeat(64),request_id:'01234567-89ab-4cde-8fab-0123456789ab',input_digest:'e'.repeat(64)};
  sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[foreign]}));
  await mount();expect(button('Save as template').disabled).toBe(true);await click('Check save status');
  expect(button('Save as template').disabled).toBe(false);expect(readReferences()).toEqual([foreign]);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/template-saves/')&&!url.endsWith('/context'))).toHaveLength(0);
});

test('malformed stored data holds without a template POST or destructive cleanup',async()=>{
  sessionStorage.setItem(STORAGE_KEY,'[]');await mount();await click('Check save status');
  expect(button('Save as template').disabled).toBe(true);expect(posts()).toHaveLength(0);
  expect(sessionStorage.getItem(STORAGE_KEY)).toBe('[]');
});

test('a competing same-scope reference arriving during preparation blocks final POST admission',async()=>{
  await mount({initialStep:2});let release;
  globalThis.__templateSequenceSave=()=>new Promise(resolve=>{release=resolve;});
  await act(async()=>button('Save as template').click());
  const other={contract_version:1,workspace_id:'workspace',scope_digest:context.scope_digest,request_id:'01234567-89ab-4cde-8fab-0123456789ab',input_digest:'e'.repeat(64)};
  sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[other]}));
  await act(async()=>release(true));await finishDigests();
  expect(posts()).toHaveLength(0);expect(readReferences()).toEqual([other]);expect(button('Save as template').disabled).toBe(true);
});

test('stale exact receipt cannot clear or unlock a newer same-scope reference',async()=>{
  let release;post=body=>new Promise(resolve=>{release=()=>resolve(response(receipt(body)));});
  await mount();await click('Save as template');
  const newer={...readReferences()[0],request_id:'01234567-89ab-4cde-8fab-0123456789ab'};
  sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[newer]}));
  await act(async()=>release());expect(readReferences()).toEqual([newer]);expect(button('Save as template').disabled).toBe(true);
});

test('confirmed save with failed reference cleanup stays held',async()=>{
  let release;post=body=>new Promise(resolve=>{release=()=>resolve(response(receipt(body)));});
  await mount();await click('Save as template');
  const original=sessionStorage.getItem(STORAGE_KEY);
  const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error('blocked');});
  try{await act(async()=>release());expect(button('Save as template').disabled).toBe(true);expect(sessionStorage.getItem(STORAGE_KEY)).toBe(original);}
  finally{spy.mockRestore();}
});

test('same digest with a foreign workspace stays held without status GET',async()=>{
  const bad={contract_version:1,workspace_id:'foreign',scope_digest:context.scope_digest,request_id:'01234567-89ab-4cde-8fab-0123456789ab',input_digest:'e'.repeat(64)};
  sessionStorage.setItem(STORAGE_KEY,JSON.stringify({contract_version:1,references:[bad]}));
  await mount();await click('Check save status');expect(button('Save as template').disabled).toBe(true);
  expect(global.fetch.mock.calls.filter(([url])=>url.includes('/template-saves/')&&!url.endsWith('/context'))).toHaveLength(0);
});

test('switching scope restores an original memory reference lost from storage before unlocking',async()=>{
  post=async()=>{throw Error('lost');};await mount();await click('Save as template');const original=readReferences()[0];
  sessionStorage.clear();contextResult=response({...context,workspace_id:'B',scope_digest:'b'.repeat(64)});
  await click('Check save status');expect(readReferences()).toEqual([original]);expect(button('Save as template').disabled).toBe(false);
  contextResult=response(context);await click('Save as template');expect(posts()).toHaveLength(1);
  await click('Check save status');expect(container.textContent).toContain('Original template save confirmed');
});
