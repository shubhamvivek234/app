import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SequenceCanvas from './SequenceCanvas';

const node={id:'original',type:'visit_profile',title:'Original template visit',delay_hours:5,config:{}};
let container,root,getSnapshot,register,save;
const button=title=>container.querySelector(`[title="${title}"]`);
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;jest.useFakeTimers();container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  getSnapshot=null;register=jest.fn(callback=>{getSnapshot=callback;});save=jest.fn();global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>({capabilities:[]})});});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();delete global.fetch;jest.useRealTimers();});
const mount=async(props={})=>act(async()=>root.render(<SequenceCanvas templateTree={[node]} onRegisterTemplateSnapshot={register} onSave={save} {...props} />));

it('loads the exact supplied template and returns a copied graph without campaign fetch or autosave',async()=>{
  const tree=[{...node,config:{custom:'original'}}];await mount({templateTree:tree});
  expect(container.textContent).toContain('Original template visit');expect(container.textContent).not.toContain('Connection request');
  const graph=getSnapshot();expect(graph.nodes[0].delay_hours).toBe(5);graph.tree[0].config.custom='changed';
  expect(tree[0].config.custom).toBe('original');expect(getSnapshot().tree[0].config.custom).toBe('original');
  await act(async()=>jest.advanceTimersByTime(1000));
  expect(global.fetch.mock.calls.every(([url,options])=>url.includes('sequence-capabilities')&&!options?.method)).toBe(true);
  expect(save).not.toHaveBeenCalled();
});

it('visible delay editing changes the current snapshot and never posts a campaign sequence',async()=>{
  await mount();await act(async()=>button('Edit delay').click());
  const input=container.querySelector('input');
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'9');input.dispatchEvent(new Event('input',{bubbles:true}));});
  await act(async()=>button('Save delay').click());
  expect(getSnapshot().nodes[0].delay_hours).toBe(9);
  await act(async()=>jest.advanceTimersByTime(1000));expect(global.fetch.mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);
});

it.each([null,{},[],[null],[{...node,steps:[node]}]])('invalid supplied tree stays unavailable without starter substitution %#',async(tree)=>{
  await mount({templateTree:tree});expect(container.querySelector('[role="alert"]')).not.toBeNull();
  expect(()=>getSnapshot()).toThrow();expect(container.textContent).not.toContain('Connection request');
});

it('a template/campaign combination is denied before campaign reads and persistence',async()=>{
  await mount({campaignId:'campaign',onRegisterSave:jest.fn()});expect(container.textContent).toContain('Template editing cannot target a campaign');
  expect(global.fetch.mock.calls.every(([url])=>url.includes('sequence-capabilities'))).toBe(true);expect(()=>getSnapshot()).toThrow();
});
