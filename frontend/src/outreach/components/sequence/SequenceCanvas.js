import React, { useState } from 'react';
import {
  Eye, UserPlus, MessageSquare, Mic, Mail, UserCheck, ThumbsUp, MessageCircle,
  CornerDownRight, Award, GitBranch, Clock, Plus, X, ZoomIn, ZoomOut, Maximize2,
  AlertCircle, CheckCircle2, Sparkles, ChevronRight, Edit3, Trash2, MoreVertical,
  Navigation
} from 'lucide-react';

const ACTION_DEFINITIONS = [
  { type: 'visit_profile', label: 'Visit profile', desc: "Visit lead's profile", icon: Eye, color: 'text-indigo-600 bg-indigo-50' },
  { type: 'connection_request', label: 'Connection request', desc: 'Send a connection request', icon: UserPlus, color: 'text-blue-600 bg-blue-50' },
  { type: 'send_message', label: 'Send message', desc: 'Direct message to connection', icon: MessageSquare, color: 'text-violet-600 bg-violet-50' },
  { type: 'voice_note', label: 'Voice note', desc: 'Personalized AI cloned voice bubble', icon: Mic, color: 'text-rose-600 bg-rose-50' },
  { type: 'inmail', label: 'InMail', desc: 'Send message to 2nd/3rd degree lead', icon: Mail, color: 'text-amber-600 bg-amber-50' },
  { type: 'follow', label: 'Follow', desc: 'Follow prospect profile', icon: UserCheck, color: 'text-emerald-600 bg-emerald-50' },
  { type: 'like_last_post', label: 'Like last post', desc: 'Like most recent activity', icon: ThumbsUp, color: 'text-sky-600 bg-sky-50' },
  { type: 'comment_last_post', label: 'Comment on last post', desc: 'Engage with AI comment', icon: MessageCircle, color: 'text-purple-600 bg-purple-50' },
  { type: 'reply_to_comment', label: 'Reply to comment', desc: 'Respond to prospect reply', icon: CornerDownRight, color: 'text-teal-600 bg-teal-50' },
  { type: 'endorse_skills', label: 'Endorse skills', desc: 'Endorse top profile skill', icon: Award, color: 'text-fuchsia-600 bg-fuchsia-50' },
];

const CONDITION_DEFINITIONS = [
  { type: 'if_connected', label: 'If connected', desc: 'Check 1st degree connection', icon: GitBranch },
  { type: 'if_opened_message', label: 'If opened message', desc: 'Check InMail read receipt', icon: Eye },
  { type: 'open_profile_check', label: 'Open-profile check', desc: 'Free InMail eligible check', icon: UserCheck },
  { type: 'has_data_in_column', label: 'Has data in column', desc: 'Verify email or phone', icon: Clock },
];

const VARIABLE_PILLS = [
  '{{first_name}}',
  '{{last_name}}',
  '{{full_name}}',
  '{{headline}}',
  '{{company_name}}',
  '{{job_title}}',
  '{{industry}}',
  '{{location_raw}}',
];

const INITIAL_TREE = {
  step1: {
    id: 'step1',
    type: 'visit_profile',
    title: 'Visit profile',
    subtitle: "Visit lead's profile",
    delay_days: 0,
    config: {},
  },
  step2: {
    id: 'step2',
    type: 'connection_request',
    title: 'Connection request',
    subtitle: 'Send a connection request',
    delay_days: 0,
    config: { note: '' },
    branches: {
      left: {
        condition: 'not accepted yet',
        type: 'danger',
        steps: [],
        terminated: true,
      },
      right: {
        condition: 'accepted',
        type: 'success',
        steps: ['step3'],
      },
    },
  },
  step3: {
    id: 'step3',
    type: 'voice_note',
    title: 'Voice note',
    subtitle: 'Action required',
    delay_days: 0,
    config: { script: '', fallback: '', mode: 'cloner' },
    isActionRequired: true,
    branches: {
      left: {
        condition: 'no reply',
        type: 'danger',
        steps: [],
        endsHere: true,
      },
      right: {
        condition: 'replied',
        type: 'success',
        steps: ['step4'],
      },
    },
  },
  step4: {
    id: 'step4',
    type: 'inmail',
    title: 'InMail',
    subtitle: 'Action required',
    delay_days: 0,
    config: { subject: '', message: '', fallback: '' },
    isActionRequired: true,
    branches: {
      left: {
        condition: 'no reply',
        type: 'danger',
        steps: [],
        terminated: true,
      },
      right: {
        condition: 'replied',
        type: 'success',
        steps: ['step5'],
      },
    },
  },
  step5: {
    id: 'step5',
    type: 'follow',
    title: 'Follow',
    subtitle: "Follow lead's profile",
    delay_days: 0,
    config: {},
    terminated: true,
  },
};

export default function SequenceCanvas({ campaignId, onSave }) {
  const [treeData, setTreeData] = useState(INITIAL_TREE);
  const [selectedStepId, setSelectedStepId] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteTarget, setPaletteTarget] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [showTip, setShowTip] = useState(true);
  const [toastMessage, setToastMessage] = useState('Follow added.');

  const selectedStep = treeData[selectedStepId] || null;

  const updateStepConfig = (stepId, updater) => {
    setTreeData((prev) => {
      const step = prev[stepId];
      if (!step) return prev;
      const updated = typeof updater === 'function' ? updater(step) : { ...step, ...updater };
      return { ...prev, [stepId]: updated };
    });
  };

  const handleAddStepFromPalette = (actionType) => {
    const actionDef = ACTION_DEFINITIONS.find((a) => a.type === actionType) || { label: 'New Step', desc: '' };
    const newId = `step_${Date.now().toString().slice(-5)}`;
    const newStep = {
      id: newId,
      type: actionType,
      title: actionDef.label,
      subtitle: actionDef.desc || "Action ready",
      delay_days: 0,
      config: {},
      isActionRequired: ['voice_note', 'inmail', 'send_message'].includes(actionType),
      terminated: true,
    };

    setTreeData((prev) => {
      const copy = { ...prev, [newId]: newStep };
      if (paletteTarget && paletteTarget.parentStepId && paletteTarget.branchKey) {
        const parent = copy[paletteTarget.parentStepId];
        if (parent && parent.branches && parent.branches[paletteTarget.branchKey]) {
          parent.branches[paletteTarget.branchKey].steps.push(newId);
          parent.branches[paletteTarget.branchKey].terminated = false;
          parent.branches[paletteTarget.branchKey].endsHere = false;
        }
      }
      return copy;
    });

    setPaletteOpen(false);
    setSelectedStepId(newId);
    setToastMessage(`${actionDef.label} added.`);
  };

  const handleDeleteStep = (stepId) => {
    setTreeData((prev) => {
      const copy = { ...prev };
      delete copy[stepId];
      // Clean up references in branches
      Object.keys(copy).forEach((k) => {
        const s = copy[k];
        if (s.branches) {
          Object.keys(s.branches).forEach((bk) => {
            s.branches[bk].steps = s.branches[bk].steps.filter((id) => id !== stepId);
            if (s.branches[bk].steps.length === 0) {
              s.branches[bk].terminated = true;
            }
          });
        }
      });
      return copy;
    });
    if (selectedStepId === stepId) setSelectedStepId(null);
  };

  const insertVariable = (variable) => {
    if (!selectedStep) return;
    if (selectedStep.type === 'voice_note') {
      const curr = selectedStep.config?.script || '';
      updateStepConfig(selectedStep.id, {
        config: { ...selectedStep.config, script: curr ? `${curr} ${variable}` : variable },
        isActionRequired: false,
        subtitle: 'Personalized script ready',
      });
    } else if (selectedStep.type === 'inmail') {
      const curr = selectedStep.config?.message || '';
      updateStepConfig(selectedStep.id, {
        config: { ...selectedStep.config, message: curr ? `${curr} ${variable}` : variable },
        isActionRequired: false,
        subtitle: 'InMail message configured',
      });
    } else if (selectedStep.type === 'send_message') {
      const curr = selectedStep.config?.body || '';
      updateStepConfig(selectedStep.id, {
        config: { ...selectedStep.config, body: curr ? `${curr} ${variable}` : variable },
        isActionRequired: false,
        subtitle: 'Direct message configured',
      });
    } else if (selectedStep.type === 'connection_request') {
      const curr = selectedStep.config?.note || '';
      updateStepConfig(selectedStep.id, {
        config: { ...selectedStep.config, note: curr ? `${curr} ${variable}` : variable },
      });
    }
  };

  // Helper for node icon
  const getActionIcon = (type) => {
    const found = ACTION_DEFINITIONS.find((a) => a.type === type);
    if (!found) return { icon: Eye, color: 'text-indigo-600 bg-indigo-50' };
    return { icon: found.icon, color: found.color };
  };

  // Render a Single Step Card
  const renderCard = (step) => {
    if (!step) return null;
    const isSelected = selectedStepId === step.id;
    const { icon: StepIcon, color: iconStyle } = getActionIcon(step.type);

    return (
      <div
        key={step.id}
        onClick={(e) => {
          e.stopPropagation();
          setSelectedStepId(step.id);
        }}
        className={`w-[340px] rounded-2xl bg-white border transition-all cursor-pointer select-none text-left ${
          isSelected
            ? 'border-indigo-600 ring-4 ring-indigo-500/20 shadow-md'
            : step.isActionRequired
            ? 'border-rose-400 bg-rose-50/15 hover:border-rose-500 shadow-xs'
            : 'border-slate-200 hover:border-slate-300 shadow-xs'
        }`}
      >
        {/* Timing Bar Header matching Prosp (media_1790088201124.png) */}
        <div className="flex items-center justify-between px-3.5 py-1.5 bg-slate-50/90 rounded-t-2xl border-b border-slate-100 text-xs text-slate-500">
          <div className="flex items-center gap-1.5 font-medium">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>{step.delay_days === 0 ? 'No delay' : `Wait ${step.delay_days} days, then`}</span>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedStepId(step.id);
            }}
            className="p-1 hover:bg-slate-200/60 rounded text-slate-400 hover:text-indigo-600"
          >
            <Edit3 className="w-3 h-3" />
          </button>
        </div>

        {/* Card Main Body */}
        <div className="p-3.5 flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${iconStyle}`}>
            <StepIcon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-bold text-slate-900 leading-tight">{step.title}</h4>
            {step.isActionRequired ? (
              <p className="text-xs font-semibold text-rose-500 mt-0.5">Action required</p>
            ) : (
              <p className="text-xs text-slate-400 truncate mt-0.5">{step.subtitle}</p>
            )}
          </div>
          <div className="text-slate-300 hover:text-slate-600 p-1">
            <MoreVertical className="w-4 h-4" />
          </div>
        </div>
      </div>
    );
  };

  // Render vertical trunk with centered Plus button
  const renderVerticalConnector = (target) => (
    <div className="flex flex-col items-center justify-center relative my-0">
      <div className="w-[2px] h-4 bg-slate-300" />
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setPaletteTarget(target);
          setPaletteOpen(true);
        }}
        className="w-5 h-5 rounded-full border border-slate-300 bg-white text-slate-400 hover:text-indigo-600 hover:border-indigo-500 hover:scale-110 transition-all flex items-center justify-center shadow-2xs z-10"
        title="Add a step"
      >
        <Plus className="w-3 h-3 stroke-[2.5]" />
      </button>
      <div className="w-[2px] h-4 bg-slate-300" />
    </div>
  );

  // Render Branch Splitter (orthogonal elbows + condition pills)
  const renderBranching = (parentStep) => {
    if (!parentStep || !parentStep.branches) return null;
    const { left, right } = parentStep.branches;

    return (
      <div className="flex flex-col items-center w-full">
        {/* SVG Orthogonal Branch Splitter */}
        <div className="w-full flex justify-center">
          <svg className="w-[680px] h-[36px] overflow-visible" viewBox="0 0 680 36" fill="none">
            {/* Center vertical line dropping from parent card */}
            <line x1="340" y1="0" x2="340" y2="18" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Horizontal splitter bar */}
            <line x1="170" y1="18" x2="510" y2="18" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Left drop line into left condition pill */}
            <line x1="170" y1="18" x2="170" y2="36" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Right drop line into right condition pill */}
            <line x1="510" y1="18" x2="510" y2="36" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>

        {/* Two Branch Columns (Left & Right) */}
        <div className="flex items-start justify-center gap-16 w-full">
          {/* LEFT BRANCH */}
          <div className="w-[340px] flex flex-col items-center">
            {/* Condition Pill */}
            <div
              className={`flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold tracking-tight shadow-2xs ${
                left.type === 'danger'
                  ? 'bg-rose-50 border border-rose-200 text-rose-600'
                  : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
              }`}
            >
              <span>{left.type === 'danger' ? '✕' : '✓'}</span>
              <span>{left.condition}</span>
            </div>

            {/* If Left Branch has steps, render them */}
            {left.steps && left.steps.length > 0 ? (
              left.steps.map((childId) => {
                const child = treeData[childId];
                return (
                  <div key={childId} className="flex flex-col items-center w-full">
                    {renderVerticalConnector({ parentStepId: parentStep.id, branchKey: 'left' })}
                    {renderCard(child)}
                    {renderBranching(child)}
                  </div>
                );
              })
            ) : left.endsHere ? (
              /* Ends Here Badge matching Voice Note Left Branch */
              <div className="flex flex-col items-center mt-2">
                <div className="w-[2px] h-3 bg-slate-300" />
                <button
                  onClick={() => {
                    setPaletteTarget({ parentStepId: parentStep.id, branchKey: 'left' });
                    setPaletteOpen(true);
                  }}
                  className="w-5 h-5 rounded-full border border-slate-300 bg-white text-slate-400 hover:text-indigo-600 hover:border-indigo-500 hover:scale-110 transition flex items-center justify-center shadow-2xs z-10"
                >
                  <Plus className="w-3 h-3 stroke-[2.5]" />
                </button>
                <div className="w-[2px] h-3 bg-slate-300" />
                <div className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 border border-slate-200 text-slate-600 mt-1">
                  <span>✓</span>
                  <span>ENDS HERE</span>
                </div>
                <button
                  onClick={() => {
                    setPaletteTarget({ parentStepId: parentStep.id, branchKey: 'left' });
                    setPaletteOpen(true);
                  }}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 mt-2.5"
                >
                  + Add a step
                </button>
              </div>
            ) : (
              /* Terminated End + Button matching Connection Request Left Branch */
              <div className="flex flex-col items-center mt-2">
                <div className="w-[2px] h-4 bg-slate-300" />
                <div className="flex items-center gap-1.5">
                  <div className="px-3 py-1 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 shadow-2xs">
                    End
                  </div>
                  <button
                    onClick={() => {
                      setPaletteTarget({ parentStepId: parentStep.id, branchKey: 'left' });
                      setPaletteOpen(true);
                    }}
                    className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center shadow-xs transition-colors"
                    title="Add step to this path"
                  >
                    <Plus className="w-4 h-4 stroke-[2.5]" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* RIGHT BRANCH */}
          <div className="w-[340px] flex flex-col items-center">
            {/* Condition Pill */}
            <div
              className={`flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold tracking-tight shadow-2xs ${
                right.type === 'danger'
                  ? 'bg-rose-50 border border-rose-200 text-rose-600'
                  : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
              }`}
            >
              <span>{right.type === 'danger' ? '✕' : '✓'}</span>
              <span>{right.condition}</span>
            </div>

            {/* Right Branch Steps */}
            {right.steps && right.steps.length > 0 ? (
              right.steps.map((childId) => {
                const child = treeData[childId];
                return (
                  <div key={childId} className="flex flex-col items-center w-full">
                    {renderVerticalConnector({ parentStepId: parentStep.id, branchKey: 'right' })}
                    {renderCard(child)}
                    {renderBranching(child)}
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center mt-2">
                <div className="w-[2px] h-4 bg-slate-300" />
                <div className="flex items-center gap-1.5">
                  <div className="px-3 py-1 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 shadow-2xs">
                    End
                  </div>
                  <button
                    onClick={() => {
                      setPaletteTarget({ parentStepId: parentStep.id, branchKey: 'right' });
                      setPaletteOpen(true);
                    }}
                    className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center shadow-xs transition-colors"
                  >
                    <Plus className="w-4 h-4 stroke-[2.5]" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="relative flex h-full w-full bg-[#f8fafc] overflow-hidden select-none">
      {/* Background Dot Grid */}
      <div
        className="absolute inset-0 opacity-45 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(#94a3b8 1.4px, transparent 1.4px)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* Top Floating Tip Banner matching media_1790088201124.png */}
      {showTip && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 w-[640px] max-w-[90%] flex items-center justify-between gap-3 rounded-2xl bg-indigo-50/90 border border-indigo-100 px-4 py-2.5 text-xs text-indigo-950 shadow-xs backdrop-blur-sm animate-fade-in">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-2xs">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="font-bold text-indigo-900 mr-1">Tip:</span>
              <span className="text-indigo-800">
                Your first invite has no note. That is good—invites with notes are often accepted less.
              </span>
            </div>
          </div>
          <button onClick={() => setShowTip(false)} className="text-indigo-400 hover:text-indigo-700 p-1">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Action Toast Banner matching media_1790088201124.png */}
      {toastMessage && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 w-[640px] max-w-[90%] flex items-center justify-between gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-2 text-xs font-semibold text-emerald-800 shadow-xs animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>{toastMessage}</span>
          </div>
          <button onClick={() => setToastMessage(null)} className="text-emerald-500 hover:text-emerald-800">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Zoom Controls (Top Left matching media_1790088201124.png) */}
      <div className="absolute top-5 left-6 z-20 flex items-center gap-1 rounded-xl bg-white border border-gray-200 p-1 shadow-xs text-gray-600">
        <button
          onClick={() => setZoomLevel((z) => Math.max(z - 10, 60))}
          className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
          title="Zoom out"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          onClick={() => setZoomLevel((z) => Math.min(z + 10, 140))}
          className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
          title="Zoom in"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          onClick={() => setZoomLevel(100)}
          className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
          title="Reset zoom"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
        <span className="px-2 text-xs font-semibold text-gray-700">{zoomLevel}%</span>
      </div>

      {/* Flowchart Tree Canvas (Scrollable) */}
      <div
        className="flex-1 overflow-auto flex flex-col items-center pt-20 pb-36 px-10"
        onClick={() => setSelectedStepId(null)}
      >
        <div
          className="flex flex-col items-center transition-transform duration-150 origin-top"
          style={{ transform: `scale(${zoomLevel / 100})` }}
        >
          {/* SEQUENCE START Pill (media_1790088201124.png) */}
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs font-bold tracking-wider text-slate-500 shadow-2xs mb-0">
            <Navigation className="w-3.5 h-3.5 text-slate-400 rotate-45" />
            <span>SEQUENCE START</span>
          </div>

          {/* Root vertical line to Step 1 */}
          {renderVerticalConnector({ parentStepId: null, branchKey: null })}

          {/* Step 1: Visit Profile */}
          {renderCard(treeData.step1)}

          {/* Vertical line to Step 2 */}
          {renderVerticalConnector({ parentStepId: 'step1', branchKey: null })}

          {/* Step 2: Connection Request */}
          {renderCard(treeData.step2)}

          {/* Branching from Step 2 */}
          {renderBranching(treeData.step2)}
        </div>
      </div>

      {/* RIGHT DRAWER: Step Configuration Inspector matching media_1790088114763.png & media_1790088159049.png */}
      {selectedStep && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-96 max-w-[90vw] bg-white border-l border-gray-200 shadow-2xl z-30 flex flex-col animate-slide-left"
        >
          {/* Drawer Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
                {React.createElement(getActionIcon(selectedStep.type).icon, { className: 'w-5 h-5' })}
              </div>
              <div>
                <h3 className="font-bold text-gray-900 text-sm">{selectedStep.title}</h3>
                <span className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">
                  LinkedIn Outreach
                </span>
              </div>
            </div>
            <button
              onClick={() => setSelectedStepId(null)}
              className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Drawer Content Form */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5 text-left">
            {/* Timing Delay Stepper */}
            <div>
              <label className="block text-xs font-bold text-gray-900 mb-1">Wait before this step</label>
              <div className="flex items-center gap-2 mt-1.5">
                <div className="flex items-center border border-gray-200 rounded-xl bg-white shadow-2xs overflow-hidden">
                  <button
                    onClick={() => updateStepConfig(selectedStep.id, { delay_days: Math.max(0, (selectedStep.delay_days || 0) - 1) })}
                    className="px-3 py-1.5 text-gray-500 hover:bg-gray-100 text-sm font-bold"
                  >
                    –
                  </button>
                  <span className="px-4 py-1.5 text-xs font-bold text-gray-900 w-12 text-center">
                    {selectedStep.delay_days || 0}
                  </span>
                  <button
                    onClick={() => updateStepConfig(selectedStep.id, { delay_days: (selectedStep.delay_days || 0) + 1 })}
                    className="px-3 py-1.5 text-gray-500 hover:bg-gray-100 text-sm font-bold"
                  >
                    +
                  </button>
                </div>
                <span className="text-xs font-semibold text-gray-600 bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-xl">
                  days ▾
                </span>
              </div>
              <p className="text-[11px] text-gray-400 mt-1.5">
                Set 0 to run as soon as the step before it finishes.
              </p>
            </div>

            {/* VOICE NOTE CONFIGURATION (media_1790088114763.png) */}
            {selectedStep.type === 'voice_note' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                {/* Voice Source Options */}
                <div className="flex items-center gap-2">
                  <button className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 text-white shadow-2xs">
                    Voice cloner
                  </button>
                  <button className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white border border-gray-200 text-gray-600 hover:bg-gray-50">
                    Record audio
                  </button>
                  <button className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white border border-gray-200 text-gray-600 hover:bg-gray-50">
                    Upload MP3
                  </button>
                </div>

                {/* Voice Script Textarea */}
                <div>
                  <div className="flex items-center justify-between text-xs font-bold text-gray-900 mb-1">
                    <span>Voice script (490 characters)</span>
                    <span className="text-[11px] font-normal text-gray-400">
                      {(selectedStep.config?.script || '').length}/490
                    </span>
                  </div>
                  <textarea
                    rows={4}
                    maxLength={490}
                    value={selectedStep.config?.script || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, script: e.target.value },
                        isActionRequired: e.target.value.trim().length === 0,
                        subtitle: e.target.value.trim().length > 0 ? 'AI voice note ready' : 'Action required',
                      })
                    }
                    placeholder="Keep it short and natural: hello, one reason you reached out, a soft ask."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                  <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                    LinkedIn caps a voice note at about a minute; this limit keeps the spoken note under it, even for a slower voice.
                  </p>
                </div>

                {/* Variable Pills */}
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1.5">
                    Insert variable
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {VARIABLE_PILLS.map((v) => (
                      <button
                        key={v}
                        onClick={() => insertVariable(v)}
                        className="px-2 py-0.5 rounded-lg border border-indigo-100 bg-indigo-50/50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-mono transition-colors"
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Fallback Textarea */}
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Fallback if a variable is missing (490 characters)
                  </label>
                  <textarea
                    rows={2}
                    maxLength={490}
                    value={selectedStep.config?.fallback || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, fallback: e.target.value },
                      })
                    }
                    placeholder="A version with no variables, always safe to send"
                    className="w-full rounded-xl border border-gray-200 p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
              </div>
            )}

            {/* INMAIL CONFIGURATION (media_1790088159049.png) */}
            {selectedStep.type === 'inmail' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">Subject</label>
                  <input
                    type="text"
                    value={selectedStep.config?.subject || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, subject: e.target.value },
                      })
                    }
                    placeholder="Subject line..."
                    className="w-full rounded-xl border border-gray-200 px-3 py-2 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs font-bold text-gray-900 mb-1">
                    <span>Message</span>
                    <span className="text-[11px] font-normal text-gray-400">
                      {(selectedStep.config?.message || '').length}/1900
                    </span>
                  </div>
                  <textarea
                    rows={5}
                    maxLength={1900}
                    value={selectedStep.config?.message || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, message: e.target.value },
                        isActionRequired: e.target.value.trim().length === 0,
                        subtitle: e.target.value.trim().length > 0 ? 'InMail copy ready' : 'Action required',
                      })
                    }
                    placeholder="Write your InMail copy here..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                </div>

                {/* Variable Pills */}
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1.5">
                    Insert variable
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {VARIABLE_PILLS.map((v) => (
                      <button
                        key={v}
                        onClick={() => insertVariable(v)}
                        className="px-2 py-0.5 rounded-lg border border-indigo-100 bg-indigo-50/50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-mono transition-colors"
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Fallback Textarea */}
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Fallback if a variable is missing
                  </label>
                  <textarea
                    rows={2}
                    value={selectedStep.config?.fallback || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, fallback: e.target.value },
                      })
                    }
                    placeholder="A version with no variables, always safe to send"
                    className="w-full rounded-xl border border-gray-200 p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
              </div>
            )}

            {/* SEND MESSAGE CONFIGURATION */}
            {selectedStep.type === 'send_message' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">Direct Message Copy</label>
                  <textarea
                    rows={4}
                    value={selectedStep.config?.body || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, body: e.target.value },
                        isActionRequired: e.target.value.trim().length === 0,
                        subtitle: e.target.value.trim().length > 0 ? e.target.value.slice(0, 32) + '...' : 'Action required',
                      })
                    }
                    placeholder="Hi {{first_name}}, thanks for connecting! Loved your recent thoughts on..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                </div>

                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1.5">
                    Insert variable
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {VARIABLE_PILLS.map((v) => (
                      <button
                        key={v}
                        onClick={() => insertVariable(v)}
                        className="px-2 py-0.5 rounded-lg border border-indigo-100 bg-indigo-50/50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-mono transition-colors"
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* CONNECTION REQUEST CONFIGURATION */}
            {selectedStep.type === 'connection_request' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-amber-50/60 border border-amber-200 rounded-xl text-xs text-amber-800 leading-relaxed">
                  <strong>Prosp Recommendation:</strong> Connection invites sent without a note typically get 15-20% higher acceptance rates.
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Invite Note (Optional, 300 chars)
                  </label>
                  <textarea
                    rows={3}
                    maxLength={300}
                    value={selectedStep.config?.note || ''}
                    onChange={(e) =>
                      updateStepConfig(selectedStep.id, {
                        config: { ...selectedStep.config, note: e.target.value },
                      })
                    }
                    placeholder="Leave empty for blank invite (recommended) or write personalized invite..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer Actions */}
          <div className="p-4 border-t border-gray-100 bg-gray-50/40 flex items-center justify-between">
            <button
              onClick={() => handleDeleteStep(selectedStep.id)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-xl transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete step
            </button>
            <button
              onClick={() => setSelectedStepId(null)}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* STEP PALETTE DRAWER (When clicking + anywhere) */}
      {paletteOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-84 bg-white border-l border-gray-200 shadow-2xl z-40 flex flex-col animate-slide-left"
        >
          <div className="flex items-center justify-between p-4 border-b border-gray-100">
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Add a step</h3>
              <p className="text-xs text-gray-400">Pick what happens next in this path.</p>
            </div>
            <button onClick={() => setPaletteOpen(false)} className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6 text-left">
            {/* Actions */}
            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 block mb-2">
                LinkedIn Actions ({ACTION_DEFINITIONS.length})
              </span>
              <div className="grid grid-cols-2 gap-2">
                {ACTION_DEFINITIONS.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button
                      key={action.type}
                      onClick={() => handleAddStepFromPalette(action.type)}
                      className="flex flex-col items-start p-2.5 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/20 text-left transition-all group"
                    >
                      <div className={`p-2 rounded-lg ${action.color} group-hover:scale-105 transition-transform`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-gray-900 text-xs mt-2 group-hover:text-indigo-600">
                        {action.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Conditions */}
            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 block mb-2">
                Conditions ({CONDITION_DEFINITIONS.length})
              </span>
              <div className="grid grid-cols-2 gap-2">
                {CONDITION_DEFINITIONS.map((cond) => {
                  const Icon = cond.icon;
                  return (
                    <button
                      key={cond.type}
                      onClick={() => handleAddStepFromPalette(cond.type)}
                      className="flex flex-col items-start p-2.5 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/20 text-left transition-all group"
                    >
                      <div className="p-2 rounded-lg bg-amber-50 text-amber-600 group-hover:scale-105 transition-transform">
                        <Icon className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-gray-900 text-xs mt-2 group-hover:text-amber-600">
                        {cond.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
