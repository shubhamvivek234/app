import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SequenceCanvas from './SequenceCanvas';

const node={id:'root',type:'visit_profile',delay_hours:0,config:{}};
let container;let root;let save;let release;let postCount;let onSave;
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;jest.useFakeTimers();localStorage.clear();
  container=document.createElement('div');document.body.appendChild(container);root=createRoot(container);
  postCount=0;onSave=jest.fn();save=null;
  global.fetch=jest.fn((url,options)=>{
    if(options?.method==='POST'){
      postCount+=1;
      if(postCount===1)return new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({status:'saved'})});});
      return Promise.resolve({ok:true,json:async()=>({status:'saved'})});
    }
    const body=url.includes('sequence-capabilities')?{capabilities:[]}
      :url.includes('node-counts')?{node_counts:{},waiting_node_counts:{}}
      :{nodes:[node],edges:[],tree:[node]};
    return Promise.resolve({ok:true,json:async()=>body});
  });
});
afterEach(async()=>{if(root)await act(async()=>root.unmount());container.remove();delete global.fetch;jest.useRealTimers();});
const mount=async()=>act(async()=>root.render(<SequenceCanvas campaignId="campaign" onSave={onSave} onRegisterSave={callback=>{if(callback)save=callback;}}/>));

test.each(['departure','token'])('a template-triggered save queued behind an earlier POST never starts after %s',async(change)=>{
  await mount();let first,second;let live=true;const capturedToken=localStorage.getItem('token');
  const guard=()=>{if(!live||localStorage.getItem('token')!==capturedToken)throw new Error('Context changed');};
  await act(async()=>{first=save();await Promise.resolve();});
  expect(postCount).toBe(1);
  await act(async()=>{second=save(undefined,guard);await Promise.resolve();});
  if(change==='departure'){live=false;await act(async()=>root.unmount());root=null;}
  else localStorage.setItem('token','changed');
  let result;await act(async()=>{release();await first;result=await second;});
  expect(result).toBe(false);expect(postCount).toBe(1);
});

test('an already-started guarded sequence save cannot publish a stale completion callback',async()=>{
  await mount();let pending;let current=true;
  await act(async()=>{pending=save(undefined,()=>{if(!current)throw new Error('Context changed');});await Promise.resolve();});
  expect(postCount).toBe(1);current=false;
  let result;await act(async()=>{release();result=await pending;});
  expect(result).toBe(false);expect(onSave).not.toHaveBeenCalled();
});
