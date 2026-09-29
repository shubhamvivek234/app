import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  ExternalLink,
  Mail,
  Phone,
  MapPin,
  Building,
  Calendar,
  Clock,
  User,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Play,
  Pause,
  Trash2,
  MessageSquare,
  FileText,
  Send,
  RefreshCw,
  Mic,
  ChevronRight,
} from 'lucide-react';
import { toast } from 'sonner';

const formatTaskType = (type) => {
  if (!type) return 'Outreach Action';
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

const PIPELINE_STAGES = [
  { id: 'unassigned', label: 'Unassigned' },
  { id: 'in_campaign', label: 'In Campaign' },
  { id: 'contacted', label: 'Contacted' },
  { id: 'replied', label: 'Replied' },
  { id: 'call_booked', label: 'Call booked' },
];

const authHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
};

export default function LeadActivityDrawer({ leadId, isOpen, onClose, onLeadUpdated, onDeleteLead }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [noteText, setNoteText] = useState('');
  const [submittingNote, setSubmittingNote] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [pauseReasonInput, setPauseReasonInput] = useState('');
  const [showPausePrompt, setShowPausePrompt] = useState(false);
  const [updatingStage, setUpdatingStage] = useState(false);

  const fetchActivity = useCallback(async () => {
    if (!leadId) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/activity`, {
        credentials: 'include',
        headers: authHeaders(),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(resData.detail || 'Could not load lead activity history.');
      }
      setData(resData);
    } catch (err) {
      console.error('Failed to load lead activity:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => {
    if (isOpen && leadId) {
      fetchActivity();
    } else {
      setData(null);
      setError('');
      setShowPausePrompt(false);
      setPauseReasonInput('');
    }
  }, [isOpen, leadId, fetchActivity]);

  if (!isOpen) return null;

  const lead = data?.lead;
  const activities = data?.activities || [];

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim()) return;
    setSubmittingNote(true);
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/notes`, {
        method: 'POST',
        credentials: 'include',
        headers: authHeaders(),
        body: JSON.stringify({ note: noteText.trim() }),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(resData.detail || 'Failed to save note');
      setNoteText('');
      toast.success('Note added');
      fetchActivity();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmittingNote(false);
    }
  };

  const handlePause = async () => {
    setPausing(true);
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/pause`, {
        method: 'POST',
        credentials: 'include',
        headers: authHeaders(),
        body: JSON.stringify({ reason: pauseReasonInput.trim() || undefined }),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(resData.detail || 'Failed to pause lead');
      toast.success('Lead outreach paused');
      setShowPausePrompt(false);
      setPauseReasonInput('');
      fetchActivity();
      if (onLeadUpdated) onLeadUpdated();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setPausing(false);
    }
  };

  const handleResume = async () => {
    setResuming(true);
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/resume`, {
        method: 'POST',
        credentials: 'include',
        headers: authHeaders(),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(resData.detail || 'Failed to resume lead');
      }
      toast.success('Lead resumed for sequence queue');
      fetchActivity();
      if (onLeadUpdated) onLeadUpdated();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setResuming(false);
    }
  };

  const handleUpdateStage = async (newStage) => {
    setUpdatingStage(true);
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/stage`, {
        method: 'PATCH',
        credentials: 'include',
        headers: authHeaders(),
        body: JSON.stringify({ pipeline_stage: newStage }),
      });
      const resData = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(resData.detail || 'Failed to update pipeline stage');
      toast.success('Pipeline stage updated');
      fetchActivity();
      if (onLeadUpdated) onLeadUpdated();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUpdatingStage(false);
    }
  };

  const getInitials = (first, last) => {
    return `${(first || '')[0] || ''}${(last || '')[0] || ''}`.toUpperCase() || 'L';
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-2xs flex justify-end">
      <div className="w-full max-w-lg bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200 border-l border-gray-200">
        {/* Header */}
        <div className="p-6 border-b border-gray-100 flex items-start justify-between bg-gradient-to-b from-gray-50/70 to-white shrink-0">
          {loading && !lead ? (
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-gray-100 animate-pulse" />
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
                <div className="h-3 w-20 bg-gray-100 rounded animate-pulse" />
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-sm shrink-0">
                {getInitials(lead?.first_name, lead?.last_name)}
              </div>
              <div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <h3 className="text-base font-bold text-gray-900 leading-tight">
                    {lead?.first_name || lead?.last_name
                      ? `${lead?.first_name || ''} ${lead?.last_name || ''}`.trim()
                      : 'Prospect Lead'}
                  </h3>
                  {lead?.linkedin_url && (
                    <a
                      href={lead.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center justify-center w-4 h-4 rounded bg-[#0077b5] text-white text-[9px] font-bold hover:opacity-90"
                      title="Open LinkedIn profile"
                    >
                      in
                    </a>
                  )}
                </div>
                {lead?.job_title && (
                  <p className="text-xs text-gray-600 font-medium mt-0.5">{lead.job_title}</p>
                )}
                {lead?.company_name && (
                  <p className="text-xs text-indigo-600 font-semibold">{lead.company_name}</p>
                )}
              </div>
            </div>
          )}

          <button
            onClick={onClose}
            className="p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="Close drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Drawer Body Scroll */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={fetchActivity} className="font-bold underline ml-2">Retry</button>
            </div>
          )}

          {lead && (
            <>
              {/* Sequence Position & Execution Status */}
              <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                    Outreach Status & Position
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      lead.execution_state === 'replied'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : lead.execution_state === 'paused'
                        ? 'bg-amber-50 text-amber-800 border border-amber-200'
                        : lead.execution_state === 'accepted'
                        ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                        : 'bg-gray-100 text-gray-700 border border-gray-200'
                    }`}
                  >
                    {lead.execution_state || 'queued'}
                  </span>
                </div>

                {lead.pause_reason && (
                  <div className="p-2.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold">Paused: </span>
                      <span>{lead.pause_reason}</span>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                  <div className="p-2.5 rounded-xl bg-gray-50 border border-gray-100">
                    <p className="text-[10px] text-gray-400 uppercase font-semibold">Current Step</p>
                    <p className="font-mono font-bold text-gray-800 mt-0.5 truncate">
                      {lead.current_node_id || 'Not started'}
                    </p>
                  </div>
                  <div className="p-2.5 rounded-xl bg-gray-50 border border-gray-100">
                    <p className="text-[10px] text-gray-400 uppercase font-semibold">Assigned Sender</p>
                    <p className="font-bold text-gray-800 mt-0.5 truncate">
                      {lead.assigned_sender_name || 'Unassigned'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1 text-xs">
                  <span className="text-gray-500">Next Action Due:</span>
                  <span className="font-mono text-gray-800">
                    {lead.next_action_due_at
                      ? new Date(lead.next_action_due_at).toLocaleString()
                      : 'None scheduled'}
                  </span>
                </div>

                {/* Pipeline Stage changer */}
                <div className="flex items-center justify-between pt-2 border-t border-gray-100 text-xs">
                  <span className="text-gray-500 font-medium">Pipeline Stage:</span>
                  <select
                    value={lead.pipeline_stage || 'unassigned'}
                    onChange={(e) => handleUpdateStage(e.target.value)}
                    disabled={updatingStage}
                    className="text-xs font-semibold text-gray-800 bg-white border border-gray-200 rounded-lg px-2.5 py-1 cursor-pointer focus:ring-1 focus:ring-indigo-500"
                  >
                    {PIPELINE_STAGES.map((s) => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>
                </div>

                {/* Pause / Resume Controls */}
                <div className="pt-2 border-t border-gray-100 flex items-center gap-2">
                  {lead.execution_state === 'paused' || lead.execution_state === 'replied' ? (
                    <button
                      type="button"
                      onClick={handleResume}
                      disabled={resuming}
                      className="flex-1 py-2 px-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                    >
                      <Play className="w-3.5 h-3.5" />
                      {resuming ? 'Resuming...' : 'Resume outreach'}
                    </button>
                  ) : (
                    <>
                      {showPausePrompt ? (
                        <div className="w-full space-y-2">
                          <input
                            type="text"
                            value={pauseReasonInput}
                            onChange={(e) => setPauseReasonInput(e.target.value)}
                            placeholder="Reason for pausing (optional)"
                            className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={handlePause}
                              disabled={pausing}
                              className="flex-1 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
                            >
                              {pausing ? 'Pausing...' : 'Confirm pause'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setShowPausePrompt(false)}
                              className="px-3 py-1.5 border border-gray-200 text-gray-600 hover:bg-gray-50 rounded-lg text-xs"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setShowPausePrompt(true)}
                          className="w-full py-2 px-3 border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                        >
                          <Pause className="w-3.5 h-3.5" />
                          Pause sequence for this lead
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* Campaign & Contact Details */}
              <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-2xs space-y-2.5 text-xs">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Campaign & Contact Info
                </span>
                <div className="flex items-center justify-between text-gray-600">
                  <span>Campaign:</span>
                  <span className="font-semibold text-gray-900">{lead.campaign_name || lead.campaign_id || '—'}</span>
                </div>
                <div className="flex items-center justify-between text-gray-600">
                  <span>Source:</span>
                  <span className="font-mono text-gray-700 capitalize">{lead.source || 'csv'}</span>
                </div>
                {lead.email && (
                  <div className="flex items-center justify-between text-gray-600">
                    <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5 text-gray-400" /> Email:</span>
                    <span className="font-mono text-gray-900">{lead.email}</span>
                  </div>
                )}
              </div>

              {/* Internal Notes Section */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Operator Notes
                </span>
                <form onSubmit={handleAddNote} className="space-y-2">
                  <textarea
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    placeholder="Add an internal note about this prospect..."
                    rows={2}
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600"
                  />
                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={submittingNote || !noteText.trim()}
                      className="px-3.5 py-1.5 bg-gray-900 hover:bg-gray-800 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
                    >
                      {submittingNote ? 'Saving...' : 'Add Note'}
                    </button>
                  </div>
                </form>
              </div>

              {/* Complete Activity Timeline */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                    Activity & Audit Trail ({activities.length})
                  </span>
                  <button
                    onClick={fetchActivity}
                    className="text-[11px] text-indigo-600 hover:underline flex items-center gap-1 font-semibold"
                  >
                    <RefreshCw className="w-3 h-3" /> Refresh
                  </button>
                </div>

                {activities.length === 0 ? (
                  <div className="py-8 text-center text-xs text-gray-400 border border-dashed border-gray-200 rounded-xl">
                    No activity recorded yet.
                  </div>
                ) : (
                  <div className="relative pl-5 space-y-4 border-l-2 border-indigo-100 ml-2">
                    {activities.map((act) => {
                      const ts = act.timestamp ? new Date(act.timestamp).toLocaleString() : '';

                      if (act.kind === 'task') {
                        return (
                          <div key={act.id} className="relative">
                            <span
                              className={`absolute -left-[27px] top-0.5 w-3 h-3 rounded-full ring-4 ring-white ${
                                act.status === 'completed'
                                  ? 'bg-emerald-500'
                                  : act.status === 'failed'
                                  ? 'bg-rose-500'
                                  : act.status === 'skipped'
                                  ? 'bg-amber-400'
                                  : 'bg-indigo-500'
                              }`}
                            />
                            <div className="p-2.5 rounded-xl bg-gray-50 border border-gray-100 space-y-1">
                              <div className="flex items-center justify-between text-xs">
                                <span className="font-bold text-gray-900">
                                  {formatTaskType(act.task_type)}
                                </span>
                                <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${
                                  act.status === 'completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-200 text-gray-700'
                                }`}>
                                  {act.status}
                                </span>
                              </div>
                              {act.node_id && (
                                <p className="text-[10px] font-mono text-gray-500">Step: {act.node_id}</p>
                              )}
                              {act.error_reason && (
                                <p className="text-[11px] text-amber-700">{act.error_reason}</p>
                              )}
                              <p className="text-[10px] text-gray-400 font-mono">{ts}</p>
                            </div>
                          </div>
                        );
                      }

                      if (act.kind === 'message') {
                        const isLead = act.sender_type === 'lead';
                        return (
                          <div key={act.id} className="relative">
                            <span className={`absolute -left-[27px] top-0.5 w-3 h-3 rounded-full ring-4 ring-white ${isLead ? 'bg-emerald-600' : 'bg-indigo-600'}`} />
                            <div className={`p-2.5 rounded-xl border text-xs space-y-1 ${isLead ? 'bg-emerald-50/50 border-emerald-100' : 'bg-indigo-50/50 border-indigo-100'}`}>
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-gray-900">
                                  {isLead ? 'Prospect replied' : 'Sent message'}
                                </span>
                                {act.is_voice_note && (
                                  <span className="inline-flex items-center gap-1 text-[10px] text-indigo-700 font-semibold bg-indigo-100 px-1.5 py-0.5 rounded">
                                    <Mic className="w-2.5 h-2.5" /> Voice
                                  </span>
                                )}
                              </div>
                              <p className="text-gray-700 whitespace-pre-wrap">{act.body}</p>
                              <p className="text-[10px] text-gray-400 font-mono">{ts}</p>
                            </div>
                          </div>
                        );
                      }

                      if (act.kind === 'note') {
                        return (
                          <div key={act.id} className="relative">
                            <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-purple-500 ring-4 ring-white" />
                            <div className="p-2.5 rounded-xl bg-purple-50/50 border border-purple-100 text-xs space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-bold text-purple-900">Note by {act.author}</span>
                              </div>
                              <p className="text-gray-800 whitespace-pre-wrap">{act.note}</p>
                              <p className="text-[10px] text-gray-400 font-mono">{ts}</p>
                            </div>
                          </div>
                        );
                      }

                      // Lifecycle
                      return (
                        <div key={act.id} className="relative">
                          <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-gray-400 ring-4 ring-white" />
                          <div>
                            <p className="text-xs font-bold text-gray-800">{act.description}</p>
                            <p className="text-[10px] text-gray-400 font-mono">{ts}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer Actions */}
        {lead && (
          <div className="p-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between shrink-0">
            <button
              onClick={() => onDeleteLead && onDeleteLead(lead.id)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-600 hover:text-rose-800 p-2 rounded-lg hover:bg-rose-50 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete Contact
            </button>

            {lead.linkedin_url && (
              <a
                href={lead.linkedin_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-[#0077b5] hover:bg-[#006097] text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
              >
                <span>Open LinkedIn</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
