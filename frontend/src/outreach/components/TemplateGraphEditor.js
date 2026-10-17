import React, { useCallback, useEffect, useRef, useState } from 'react';
import SequenceCanvas from './sequence/SequenceCanvas';
import { templateInputDigest } from '../hooks/useTemplateSave';
import { reviewedTemplateGraph, matchesTemplateGraphReceipt, browserGraphValues } from '../utils/templateGraph';

export default function TemplateGraphEditor({template,onSaved,onClose,onRefresh}) {
  const original=useRef(template),latest=useRef(template); latest.current=template;
  const tree=useRef(template.tree),snapshot=useRef(null),flight=useRef(null),mounted=useRef(true),refreshing=useRef(false);
  const [phase,setPhase]=useState('editing'),[error,setError]=useState('');
  const register=useCallback(callback=>{snapshot.current=callback;},[]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(template!==original.current)setPhase('held');},[template]);
  const review=reviewedTemplateGraph(original.current);
  const save=async()=>{
    if(flight.current || phase!=='editing' || !review || latest.current!==original.current || !snapshot.current)return;
    let frozen;
    try {const graph=snapshot.current();if(!browserGraphValues(graph))throw new Error('Graph needs safe JSON values');tree.current=graph.tree;frozen=JSON.stringify(graph);}
    catch {setError('This draft needs a valid visible graph before saving.');return;}
    const token=localStorage.getItem('token'),operation={...review,graph_json:frozen};
    flight.current=operation;setError('');setPhase('preparing');let submitted=false;
    const live=()=>mounted.current && flight.current===operation;
    const context=()=>latest.current===original.current && localStorage.getItem('token')===token;
    try {
      operation.input_digest=await templateInputDigest(frozen);
      if(!live())return;
      if(!context()){setPhase('held');return;}
      submitted=true;setPhase('pending');
      const response=await fetch(`/api/v1/outreach/sequences/templates/${encodeURIComponent(original.current.id)}/graph-reviewed`,{
        method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json',Authorization:token?`Bearer ${token}`:''},body:JSON.stringify(operation)});
      const data=await response.json();
      if(!live())return;
      if(!context() || response.ok!==true || response.status!==200 || !matchesTemplateGraphReceipt(data,original.current.id,operation)) {setPhase('held');return;}
      setPhase('confirmed');onSaved(original.current,data);
    } catch {
      if(!live())return;
      if(!submitted && context()){flight.current=null;setPhase('editing');setError('Could not prepare this graph. Review the draft and retry.');}
      else setPhase('held');
    }
  };
  const refresh=async()=>{
    if(phase!=='held' || refreshing.current)return;refreshing.current=true;setPhase('refreshing');
    try {await onRefresh();} catch { /* Inspection failure cannot confirm a prior write. */ }
    finally {refreshing.current=false;if(mounted.current)setPhase('held');}
  };
  return <section aria-label="Edit template sequence" className="mb-4 rounded-xl border border-gray-200 bg-white p-4 text-sm">
    <h2 className="font-semibold text-gray-900">Edit template sequence</h2>
    <p className="mt-1 text-xs text-gray-500">Edit this shared workspace template. Save applies to future uses; existing campaigns keep their saved sequences.</p>
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
    {!review && <p role="alert">Reload a valid template graph review before editing.</p>}
    {phase==='editing' && review && <div className="mt-3 h-[640px] overflow-hidden rounded-lg border border-gray-200">
      <SequenceCanvas templateTree={tree.current} onRegisterTemplateSnapshot={register} />
    </div>}
    {['preparing','pending'].includes(phase) && <p role="status" className="mt-3">{phase==='preparing'?'Preparing reviewed template graph…':'Saving reviewed template graph…'}</p>}
    {['held','refreshing'].includes(phase) && <div role="alert" className="mt-3 text-amber-800">
      <p>Earlier sequence update is unconfirmed. Reload to inspect the current template before another edit.</p>
      <p>A refreshed catalog is not an update receipt. The earlier graph will not be replayed.</p>
      <button type="button" disabled={phase==='refreshing'} onClick={refresh} className="mt-2 font-semibold">Reload and review templates</button>
    </div>}
    <div className="mt-4 flex gap-3">
      <button type="button" disabled={phase!=='editing'||!review} onClick={save} className="rounded bg-indigo-600 px-3 py-2 text-white disabled:opacity-50">Save template sequence</button>
      <button type="button" disabled={phase!=='editing'} onClick={onClose}>Cancel</button>
    </div>
  </section>;
}
