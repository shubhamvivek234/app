import React, { useEffect, useRef, useState } from 'react';
import { reviewedTemplateMetadata, validMetadataText } from '../utils/templateMetadata';
import { validSaveContext, templateInputDigest } from '../hooks/useTemplateSave';
import { matchesMetadataUpdateReceipt } from '../utils/templateMetadataUpdates';
import { storeReference, clearReference } from '../utils/templateMetadataReferences';

export default function TemplateMetadataEditor({template,onSaved,onClose}) {
  const [name,setName] = useState(template.name);
  const [description,setDescription] = useState(template.description || '');
  const [phase,setPhase] = useState('editing');
  const [error,setError] = useState('');
  const original = useRef(template);
  const latest = useRef(template); latest.current = template;
  const mounted = useRef(true), flight = useRef(null), refreshing = useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{if(template!==original.current)setPhase(flight.current?.reference?'held':'stopped');},[template]);
  const review = reviewedTemplateMetadata(original.current);
  const save = async () => {
    if (flight.current || phase!=='editing' || !review || latest.current!==original.current || !validMetadataText(name,description)) return;
    const token = localStorage.getItem('token');
    const captured = {...review,template_id:original.current.id,name,description};
    const frozen = JSON.stringify(captured);
    const operation = {captured,token,reference:null}; flight.current=operation;setError('');setPhase('preparing');
    const current = () => mounted.current && flight.current===operation;
    const contextCurrent = () => latest.current===original.current && token===localStorage.getItem('token');
    let submitted=false;
    try {
      const options={credentials:'include',headers:{'Content-Type':'application/json',Authorization:token?`Bearer ${token}`:''}};
      const contextResponse=await fetch('/api/v1/outreach/sequences/template-metadata-updates/context',options);
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
      operation.reference=reference;submitted=true;
      // Write and reread the locator before transport. Failure holds without POST.
      storeReference(reference);setPhase('pending');
      const response = await fetch('/api/v1/outreach/sequences/template-metadata-updates',{
        ...options,method:'POST',body:JSON.stringify({...reference,content_json:frozen})});
      const data = await response.json();
      if(!current())return;
      if(!contextCurrent() || response.ok!==true || response.status!==200
        || !matchesMetadataUpdateReceipt(data,reference,captured)) {
        setPhase('held');return;
      }
      clearReference(reference);
      if(!contextCurrent()) {setPhase('held');return;}
      setPhase('confirmed');onSaved(original.current,data);
    } catch {if(current()){
      if(!submitted&&contextCurrent()){flight.current=null;setPhase('editing');setError('Could not prepare this update. Review the details and retry.');}
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
      const contextResponse=await fetch('/api/v1/outreach/sequences/template-metadata-updates/context',options);
      const freshContext=await contextResponse.json();
      if(!current() || contextResponse.ok!==true || contextResponse.status!==200 || !validSaveContext(freshContext)
        || freshContext.workspace_id!==workspace_id || freshContext.scope_digest!==scope_digest)return;
      const params=new URLSearchParams({workspace_id,scope_digest,input_digest});
      const response=await fetch(`/api/v1/outreach/sequences/template-metadata-updates/${encodeURIComponent(request_id)}?${params}`,options);
      const data=await response.json();
      if(!current() || response.ok!==true || response.status!==200
        || !matchesMetadataUpdateReceipt(data,operation.reference,operation.captured))return;
      clearReference(operation.reference);
      if(!current())return;
      confirmed=true;setPhase('confirmed');onSaved(original.current,data,{historical:true});
    } catch { /* Unknown/missing status retains the original reference; no replay. */ }
    finally {refreshing.current=false;if(mounted.current&&!confirmed)setPhase('held');}
  };
  const locked = phase!=='editing';
  return <section aria-label="Edit template details" className="mb-4 rounded-xl border border-gray-200 bg-white p-4 text-sm">
    <h2 className="font-semibold text-gray-900">Edit template details</h2>
    <p className="mt-1 text-xs text-gray-500">Rename this shared workspace template or change its description. Existing campaigns keep their saved sequences.</p>
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
    <label className="mt-3 block">Name<input aria-label="Template name" value={name} maxLength={100} disabled={locked}
      onChange={event=>setName(event.target.value)} className="mt-1 block w-full rounded border border-gray-300 p-2" /></label>
    <label className="mt-3 block">Description<textarea aria-label="Template description" value={description} maxLength={1000} disabled={locked}
      onChange={event=>setDescription(event.target.value)} className="mt-1 block w-full rounded border border-gray-300 p-2" /></label>
    {!review && <p role="alert">Reload a valid template review before editing.</p>}
    {phase==='stopped' && <p role="alert" className="mt-3 text-amber-800">Update preparation stopped because the account or template changed. No update was submitted. Close this editor and reload templates before editing.</p>}
    {['held','checking'].includes(phase) && <div role="alert" className="mt-3 text-amber-800">
      <p>Earlier update is unconfirmed. Check the original update status before another edit.</p>
      <p>This confirms the original update, not the current template. Missing status stays unconfirmed; your edit will not be replayed.</p>
      <p>The request reference is retained in this browser tab when storage is available. After a reload, check its saved status in Templates. Edited text is not retained.</p>
      <button type="button" disabled={phase==='checking'||!flight.current?.reference} onClick={refresh} className="mt-2 font-semibold">Check original update status</button>
    </div>}
    {phase==='preparing' && <p role="status" className="mt-3">Preparing reviewed template details…</p>}
    {phase==='pending' && <p role="status" className="mt-3">Saving reviewed template details…</p>}
    <div className="mt-4 flex gap-3">
      <button type="button" disabled={locked||!review||!validMetadataText(name,description)} onClick={save}
        className="rounded bg-indigo-600 px-3 py-2 text-white disabled:opacity-50">Save details</button>
      <button type="button" disabled={!['editing','stopped'].includes(phase)} onClick={onClose}>Cancel</button>
    </div>
  </section>;
}
