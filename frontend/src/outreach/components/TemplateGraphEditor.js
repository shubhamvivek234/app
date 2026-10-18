import React, { useCallback, useEffect, useRef, useState } from 'react';
import SequenceCanvas from './sequence/SequenceCanvas';
import { reviewedTemplateGraph, browserGraphValues } from '../utils/templateGraph';
import { validSaveContext, templateInputDigest } from '../hooks/useTemplateSave';
import { matchesGraphUpdateReceipt } from '../utils/templateGraphUpdates';

export default function TemplateGraphEditor({template,onSaved,onClose}) {
  const tree=useRef(template.tree),snapshot=useRef(null);
  const register=useCallback(callback=>{snapshot.current=callback;},[]);
  const [phase,setPhase] = useState('editing');
  const [error,setError] = useState('');
  const original = useRef(template);
  const latest = useRef(template); latest.current = template;
  const mounted = useRef(true), flight = useRef(null), refreshing = useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(template!==original.current)setPhase(flight.current?.reference?'held':'stopped');},[template]);
  const review = reviewedTemplateGraph(original.current);
  const save = async () => {
    if (flight.current || phase!=='editing' || !review || latest.current!==original.current || !snapshot.current) return;
    const token = localStorage.getItem('token');
    let captured,frozen;
    try {
      const visible=snapshot.current();
      if(!browserGraphValues(visible))throw new Error('Unsupported graph values');
      tree.current=visible.tree;
      captured={...review,template_id:original.current.id,nodes:visible.nodes,edges:visible.edges,tree:visible.tree};
      frozen=JSON.stringify(captured);
    } catch {setError('This draft needs a valid visible graph before saving.');return;}
    const operation = {captured,token,reference:null}; flight.current=operation;setError('');setPhase('preparing');
    const current = () => mounted.current && flight.current===operation;
    const contextCurrent = () => latest.current===original.current && token===localStorage.getItem('token');
    let submitted=false;
    try {
      const options={credentials:'include',headers:{'Content-Type':'application/json',Authorization:token?`Bearer ${token}`:''}};
      const contextResponse=await fetch('/api/v1/outreach/sequences/template-graph-updates/context',options);
      const context=await contextResponse.json();
      if(!current())return;
      if(!contextCurrent()){setPhase('stopped');return;}
      if(contextResponse.ok!==true || contextResponse.status!==200 || !validSaveContext(context)
        || context.workspace_id!==review.workspace_id)throw new Error('Invalid update context');
      const inputDigest=await templateInputDigest(frozen);
      if(!current())return;
      if(!contextCurrent()){setPhase('stopped');return;}
      const requestId=globalThis.crypto.randomUUID();
      if(typeof requestId!=='string'||! /^(?:[0-9a-f]{8}-)(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(requestId))throw new Error('Invalid update reference');
      const reference={contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
        request_id:requestId,input_digest:inputDigest};
      operation.reference=reference;submitted=true;setPhase('pending');
      const response = await fetch('/api/v1/outreach/sequences/template-graph-updates',{
        ...options,method:'POST',body:JSON.stringify({...reference,content_json:frozen})});
      const data = await response.json();
      if(!current())return;
      if(!contextCurrent() || response.ok!==true || response.status!==200
        || !matchesGraphUpdateReceipt(data,reference,captured)) {
        setPhase('held');return;
      }
      setPhase('confirmed');onSaved(original.current,data);
    } catch {if(current()){
      if(!submitted&&contextCurrent()){flight.current=null;setPhase('editing');setError('Could not prepare this update. Review the sequence and retry.');}
      else setPhase(submitted?'held':'stopped');
    }}
  };
  const refresh = async () => {
    const operation=flight.current;
    if(phase!=='held' || refreshing.current || !operation?.reference)return;
    refreshing.current=true;
    setPhase('checking');let confirmed=false;
    const checkingToken=localStorage.getItem('token');
    const current=()=>mounted.current && flight.current===operation && latest.current===original.current
      && checkingToken===localStorage.getItem('token');
    try {
      if(!current())return;
      const {workspace_id,scope_digest,input_digest,request_id}=operation.reference;
      const options={credentials:'include',headers:{Authorization:checkingToken?`Bearer ${checkingToken}`:''}};
      const contextResponse=await fetch('/api/v1/outreach/sequences/template-graph-updates/context',options);
      const freshContext=await contextResponse.json();
      if(!current() || contextResponse.ok!==true || contextResponse.status!==200 || !validSaveContext(freshContext)
        || freshContext.workspace_id!==workspace_id || freshContext.scope_digest!==scope_digest)return;
      const params=new URLSearchParams({workspace_id,scope_digest,input_digest});
      const response=await fetch(`/api/v1/outreach/sequences/template-graph-updates/${encodeURIComponent(request_id)}?${params}`,options);
      const data=await response.json();
      if(!current() || response.ok!==true || response.status!==200
        || !matchesGraphUpdateReceipt(data,operation.reference,operation.captured))return;
      confirmed=true;setPhase('confirmed');onSaved(original.current,data,{historical:true});
    } catch { /* Unknown/missing status retains the original reference; no replay. */ }
    finally {refreshing.current=false;if(mounted.current&&!confirmed)setPhase('held');}
  };
  const locked = phase!=='editing';
  return <section aria-label="Edit template sequence" className="mb-4 rounded-xl border border-gray-200 bg-white p-4 text-sm">
    <h2 className="font-semibold text-gray-900">Edit template sequence</h2>
    <p className="mt-1 text-xs text-gray-500">Edit this shared workspace template. Save applies to future uses; existing campaigns keep their saved sequences.</p>
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
    {phase==='editing' && review && <div className="mt-3 h-[640px] overflow-hidden rounded-lg border border-gray-200">
      <SequenceCanvas templateTree={tree.current} onRegisterTemplateSnapshot={register}/>
    </div>}
    {!review && <p role="alert">Reload a valid template review before editing.</p>}
    {phase==='stopped' && <p role="alert" className="mt-3 text-amber-800">Update preparation stopped because the account or template changed. No update was submitted. Close this editor and reload templates before editing.</p>}
    {['held','checking'].includes(phase) && <div role="alert" className="mt-3 text-amber-800">
      <p>Earlier sequence update is unconfirmed. Check the original update status before another edit.</p>
      <p>This confirms the original update, not the current template. Missing status stays unconfirmed; your edit will not be replayed.</p>
      <p>Keep this view open. This update reference is retained only in this view.</p>
      <button type="button" disabled={phase==='checking'||!flight.current?.reference} onClick={refresh} className="mt-2 font-semibold">Check original sequence update status</button>
    </div>}
    {phase==='preparing' && <p role="status" className="mt-3">Preparing reviewed template sequence…</p>}
    {phase==='pending' && <p role="status" className="mt-3">Saving reviewed template sequence…</p>}
    <div className="mt-4 flex gap-3">
      <button type="button" disabled={locked||!review} onClick={save}
        className="rounded bg-indigo-600 px-3 py-2 text-white disabled:opacity-50">Save template sequence</button>
      <button type="button" disabled={!['editing','stopped'].includes(phase)} onClick={onClose}>Cancel</button>
    </div>
  </section>;
}
