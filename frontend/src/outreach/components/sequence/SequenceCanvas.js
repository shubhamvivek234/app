import React, { useState } from 'react';
import {
  Eye, UserPlus, MessageSquare, Mic, Mail, UserCheck, ThumbsUp, MessageCircle,
  CornerDownRight, Award, GitBranch, Clock, Plus, X, ZoomIn, ZoomOut, Maximize2,
  CheckCircle2, Sparkles, ChevronRight, Edit3, Trash2, MoreVertical, Navigation,
  Link2, Check
} from 'lucide-react';

const ACTION_DEFINITIONS = [
  { type: 'visit_profile', label: 'Visit profile', desc: "Visit lead's profile", icon: Eye, color: 'text-indigo-600 bg-indigo-50' },
  { type: 'connection_request', label: 'Connection request', desc: 'Send a connection request', icon: UserPlus, color: 'text-indigo-600 bg-indigo-50' },
  { type: 'send_message', label: 'Send message', desc: 'Direct message to connection', icon: MessageSquare, color: 'text-violet-600 bg-violet-50' },
  { type: 'voice_note', label: 'Voice note', desc: 'Personalized AI cloned voice bubble', icon: Mic, color: 'text-rose-500 bg-rose-50' },
  { type: 'inmail', label: 'InMail', desc: 'Send message to 2nd/3rd degree lead', icon: Mail, color: 'text-rose-500 bg-rose-50' },
  { type: 'follow', label: 'Follow', desc: 'Follow prospect profile', icon: UserCheck, color: 'text-indigo-600 bg-indigo-50' },
  { type: 'like_last_post', label: 'Like last post', desc: 'Like most recent activity', icon: ThumbsUp, color: 'text-sky-600 bg-sky-50' },
  { type: 'comment_last_post', label: 'Comment on last post', desc: 'Engage with AI comment', icon: MessageCircle, color: 'text-purple-600 bg-purple-50' },
  { type: 'reply_to_comment', label: 'Reply to comment', desc: 'Respond to prospect reply', icon: CornerDownRight, color: 'text-indigo-600 bg-indigo-50' },
  { type: 'endorse_skills', label: 'Endorse skills', desc: 'Endorse their top skills', icon: CheckCircle2, color: 'text-indigo-600 bg-indigo-50' },
];

const CONDITION_DEFINITIONS = [
  {
    type: 'if_connected',
    label: 'If connected',
    desc: 'Check if lead accepted',
    icon: Link2,
    color: 'text-amber-700 bg-amber-100/70',
    leftCondition: 'not connected',
    rightCondition: 'connected',
  },
  {
    type: 'if_opened_message',
    label: 'If opened message',
    desc: 'Check InMail read receipt',
    icon: Eye,
    color: 'text-amber-700 bg-amber-100/70',
    leftCondition: 'not opened',
    rightCondition: 'opened',
  },
  {
    type: 'open_profile_check',
    label: 'Open-profile check',
    desc: 'Free InMail eligible check',
    icon: UserCheck,
    color: 'text-amber-700 bg-amber-100/70',
    leftCondition: 'closed profile',
    rightCondition: 'open profile',
  },
  {
    type: 'has_data_in_column',
    label: 'Has data in column',
    desc: 'Verify email or phone',
    icon: Clock,
    color: 'text-amber-700 bg-amber-100/70',
    leftCondition: 'missing data',
    rightCondition: 'has data',
  },
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

// Initial sequence exactly matching media_1790088446398.png
const INITIAL_TREE = [
  {
    id: 'step_visit',
    type: 'visit_profile',
    title: 'Visit profile',
    subtitle: "Visit lead's profile",
    delay_days: 0,
    config: {},
  },
  {
    id: 'step_connect',
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
      },
      right: {
        condition: 'accepted',
        type: 'success',
        steps: [
          {
            id: 'step_voice',
            type: 'voice_note',
            title: 'Voice note',
            subtitle: 'Action required',
            delay_days: 0,
            config: { script: '', fallback: '' },
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
                steps: [
                  {
                    id: 'step_inmail',
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
                      },
                      right: {
                        condition: 'replied',
                        type: 'success',
                        steps: [
                          {
                            id: 'step_follow',
                            type: 'follow',
                            title: 'Follow',
                            subtitle: "Follow lead's profile",
                            delay_days: 0,
                            config: {},
                          },
                          {
                            id: 'step_if_conn_1',
                            type: 'if_connected',
                            title: 'If connected',
                            subtitle: 'Check if lead accepted',
                            delay_days: 0,
                            config: {},
                            branches: {
                              left: {
                                condition: 'not connected',
                                type: 'danger',
                                steps: [],
                              },
                              right: {
                                condition: 'connected',
                                type: 'success',
                                steps: [
                                  {
                                    id: 'step_if_conn_2',
                                    type: 'if_connected',
                                    title: 'If connected',
                                    subtitle: 'Check if lead accepted',
                                    delay_days: 0,
                                    config: {},
                                    branches: {
                                      left: {
                                        condition: 'not connected',
                                        type: 'danger',
                                        steps: [
                                          {
                                            id: 'step_endorse_1',
                                            type: 'endorse_skills',
                                            title: 'Endorse skills',
                                            subtitle: 'Endorse their top skills',
                                            delay_days: 4,
                                            config: {},
                                          },
                                          {
                                            id: 'step_endorse_2',
                                            type: 'endorse_skills',
                                            title: 'Endorse skills',
                                            subtitle: 'Endorse their top skills',
                                            delay_days: 0,
                                            config: {},
                                          },
                                          {
                                            id: 'step_reply_comment',
                                            type: 'reply_to_comment',
                                            title: 'Reply to comment',
                                            subtitle: 'Action required',
                                            delay_days: 0,
                                            config: {},
                                            isActionRequired: true,
                                          },
                                        ],
                                      },
                                      right: {
                                        condition: 'connected',
                                        type: 'success',
                                        steps: [],
                                      },
                                    },
                                  },
                                ],
                              },
                            },
                          },
                        ],
                      },
                    },
                  },
                ],
              },
            },
          },
        ],
      },
    },
  },
];

export default function SequenceCanvas({ campaignId, onSave }) {
  const [tree, setTree] = useState(INITIAL_TREE);
  const [selectedStepId, setSelectedStepId] = useState('step_reply_comment');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteTarget, setPaletteTarget] = useState(null); // { type: 'linear' | 'branch', stepId, branchKey, index }
  const [zoomLevel, setZoomLevel] = useState(100);
  const [showTip, setShowTip] = useState(true);
  const [toastMessage, setToastMessage] = useState('Reply to comment added.');

  // Inline header delay editor state (matches media_1790088397090.png)
  const [editingDelayId, setEditingDelayId] = useState(null);
  const [tempDelayValue, setTempDelayValue] = useState(0);
  const [tempDelayUnit, setTempDelayUnit] = useState('days');

  // Card Context dropdown state (matches media_1790088397090.png)
  const [contextMenuStepId, setContextMenuStepId] = useState(null);

  // Helper to find a node by ID anywhere in the tree
  const findNode = (nodes, id) => {
    for (const node of nodes) {
      if (node.id === id) return node;
      if (node.branches) {
        if (node.branches.left?.steps) {
          const found = findNode(node.branches.left.steps, id);
          if (found) return found;
        }
        if (node.branches.right?.steps) {
          const found = findNode(node.branches.right.steps, id);
          if (found) return found;
        }
      }
    }
    return null;
  };

  const selectedStep = findNode(tree, selectedStepId);

  // Helper to update a node in the tree immutably
  const updateNode = (nodes, id, updater) => {
    return nodes.map((node) => {
      if (node.id === id) {
        return typeof updater === 'function' ? updater(node) : { ...node, ...updater };
      }
      if (node.branches) {
        return {
          ...node,
          branches: {
            left: {
              ...node.branches.left,
              steps: node.branches.left?.steps ? updateNode(node.branches.left.steps, id, updater) : [],
            },
            right: {
              ...node.branches.right,
              steps: node.branches.right?.steps ? updateNode(node.branches.right.steps, id, updater) : [],
            },
          },
        };
      }
      return node;
    });
  };

  // Helper to delete a node from the tree immutably
  const deleteNode = (nodes, id) => {
    return nodes
      .filter((n) => n.id !== id)
      .map((node) => {
        if (node.branches) {
          return {
            ...node,
            branches: {
              left: {
                ...node.branches.left,
                steps: node.branches.left?.steps ? deleteNode(node.branches.left.steps, id) : [],
              },
              right: {
                ...node.branches.right,
                steps: node.branches.right?.steps ? deleteNode(node.branches.right.steps, id) : [],
              },
            },
          };
        }
        return node;
      });
  };

  // Insert a new step into the tree
  const insertStep = (nodes, target, newStep) => {
    if (!target) return [...nodes, newStep];

    // Linear insertion after target stepId
    if (target.type === 'linear') {
      const idx = nodes.findIndex((n) => n.id === target.stepId);
      if (idx !== -1) {
        const copy = [...nodes];
        copy.splice(idx + 1, 0, newStep);
        return copy;
      }
    }

    // Branch insertion inside a branch
    return nodes.map((node) => {
      if (node.id === target.parentStepId && node.branches && target.branchKey) {
        const branch = node.branches[target.branchKey];
        return {
          ...node,
          branches: {
            ...node.branches,
            [target.branchKey]: {
              ...branch,
              steps: target.index !== undefined ? [...branch.steps.slice(0, target.index), newStep, ...branch.steps.slice(target.index)] : [...branch.steps, newStep],
              endsHere: false,
            },
          },
        };
      }
      if (node.branches) {
        return {
          ...node,
          branches: {
            left: {
              ...node.branches.left,
              steps: insertStep(node.branches.left?.steps || [], target, newStep),
            },
            right: {
              ...node.branches.right,
              steps: insertStep(node.branches.right?.steps || [], target, newStep),
            },
          },
        };
      }
      return node;
    });
  };

  const handleAddStepFromPalette = (type) => {
    const isCondition = CONDITION_DEFINITIONS.some((c) => c.type === type);
    const condDef = CONDITION_DEFINITIONS.find((c) => c.type === type);
    const actionDef = ACTION_DEFINITIONS.find((a) => a.type === type);

    const newId = `step_${Date.now().toString().slice(-5)}`;
    let newStep = null;

    if (isCondition && condDef) {
      newStep = {
        id: newId,
        type: condDef.type,
        title: condDef.label,
        subtitle: condDef.desc,
        delay_days: 0,
        config: {},
        branches: {
          left: {
            condition: condDef.leftCondition,
            type: 'danger',
            steps: [],
          },
          right: {
            condition: condDef.rightCondition,
            type: 'success',
            steps: [],
          },
        },
      };
    } else if (actionDef) {
      const isBranchingAction = ['connection_request', 'voice_note', 'inmail', 'send_message'].includes(type);
      newStep = {
        id: newId,
        type: actionDef.type,
        title: actionDef.label,
        subtitle: actionDef.desc,
        delay_days: 0,
        config: {},
        isActionRequired: ['voice_note', 'inmail', 'send_message', 'reply_to_comment'].includes(type),
      };

      if (type === 'connection_request') {
        newStep.branches = {
          left: { condition: 'not accepted yet', type: 'danger', steps: [] },
          right: { condition: 'accepted', type: 'success', steps: [] },
        };
      } else if (isBranchingAction) {
        newStep.branches = {
          left: { condition: 'no reply', type: 'danger', steps: [] },
          right: { condition: 'replied', type: 'success', steps: [] },
        };
      }
    }

    if (newStep) {
      setTree((prev) => insertStep(prev, paletteTarget, newStep));
      setToastMessage(`${newStep.title} added.`);
      setSelectedStepId(newStep.id);
    }

    setPaletteOpen(false);
    setPaletteTarget(null);
  };

  const handleDeleteStep = (id) => {
    setTree((prev) => deleteNode(prev, id));
    if (selectedStepId === id) setSelectedStepId(null);
  };

  const handleStartInlineDelayEdit = (step, e) => {
    e.stopPropagation();
    setEditingDelayId(step.id);
    setTempDelayValue(step.delay_days || 0);
    setTempDelayUnit('days');
  };

  const handleSaveInlineDelay = (stepId, e) => {
    e.stopPropagation();
    const val = parseInt(tempDelayValue, 10) || 0;
    setTree((prev) => updateNode(prev, stepId, { delay_days: val }));
    setEditingDelayId(null);
  };

  const insertVariable = (variable) => {
    if (!selectedStep) return;
    if (selectedStep.type === 'voice_note') {
      const curr = selectedStep.config?.script || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, script: curr ? `${curr} ${variable}` : variable },
          isActionRequired: false,
          subtitle: 'Voice note copy ready',
        })
      );
    } else if (selectedStep.type === 'inmail') {
      const curr = selectedStep.config?.message || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, message: curr ? `${curr} ${variable}` : variable },
          isActionRequired: false,
          subtitle: 'InMail message configured',
        })
      );
    } else if (selectedStep.type === 'send_message') {
      const curr = selectedStep.config?.body || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, body: curr ? `${curr} ${variable}` : variable },
          isActionRequired: false,
          subtitle: 'Direct message configured',
        })
      );
    } else if (selectedStep.type === 'connection_request') {
      const curr = selectedStep.config?.note || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, note: curr ? `${curr} ${variable}` : variable },
        })
      );
    }
  };

  const getNodeVisuals = (type) => {
    const act = ACTION_DEFINITIONS.find((a) => a.type === type);
    if (act) return { icon: act.icon, color: act.color };
    const cond = CONDITION_DEFINITIONS.find((c) => c.type === type);
    if (cond) return { icon: cond.icon, color: cond.color };
    return { icon: Eye, color: 'text-indigo-600 bg-indigo-50' };
  };

  // Render a Single Step Card matching Prosp (media_1790088397090.png)
  const renderCard = (step) => {
    const isSelected = selectedStepId === step.id;
    const { icon: StepIcon, color: iconStyle } = getNodeVisuals(step.type);
    const isEditingThisDelay = editingDelayId === step.id;
    const isMenuOpen = contextMenuStepId === step.id;

    return (
      <div
        key={step.id}
        onClick={(e) => {
          e.stopPropagation();
          setSelectedStepId(step.id);
          setContextMenuStepId(null);
        }}
        className={`relative w-[340px] rounded-2xl bg-white border transition-all cursor-pointer select-none text-left ${
          isSelected
            ? 'border-indigo-600 ring-4 ring-indigo-500/20 shadow-md'
            : step.isActionRequired
            ? 'border-rose-300 hover:border-rose-400 bg-rose-50/10 shadow-xs'
            : 'border-slate-200 hover:border-slate-300 shadow-xs'
        }`}
      >
        {/* Timing Header Bar */}
        <div className="flex items-center justify-between px-3.5 py-1.5 bg-slate-50/90 rounded-t-2xl border-b border-slate-100 text-xs text-slate-500 min-h-[32px]">
          {isEditingThisDelay ? (
            /* Inline Delay Editor matching media_1790088397090.png */
            <div className="flex items-center gap-1.5 w-full" onClick={(e) => e.stopPropagation()}>
              <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <input
                type="number"
                min="0"
                value={tempDelayValue}
                onChange={(e) => setTempDelayValue(e.target.value)}
                className="w-12 px-1.5 py-0.5 text-xs text-center border border-slate-300 rounded-md bg-white font-medium focus:outline-none focus:border-indigo-600"
              />
              <select
                value={tempDelayUnit}
                onChange={(e) => setTempDelayUnit(e.target.value)}
                className="px-1.5 py-0.5 text-xs border border-slate-300 rounded-md bg-white font-medium focus:outline-none"
              >
                <option value="days">days</option>
                <option value="hours">hours</option>
              </select>
              <button
                type="button"
                onClick={(e) => handleSaveInlineDelay(step.id, e)}
                className="p-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md transition shadow-2xs ml-auto"
                title="Save delay"
              >
                <Check className="w-3.5 h-3.5 stroke-[3]" />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-1.5 font-medium">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>{step.delay_days === 0 ? 'No delay' : `Wait ${step.delay_days} days, then`}</span>
              </div>
              <button
                type="button"
                onClick={(e) => handleStartInlineDelayEdit(step, e)}
                className="p-1 hover:bg-slate-200/60 rounded text-slate-400 hover:text-indigo-600"
                title="Edit delay"
              >
                <Edit3 className="w-3 h-3" />
              </button>
            </>
          )}
        </div>

        {/* Card Body */}
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
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setContextMenuStepId(isMenuOpen ? null : step.id);
            }}
            className="text-slate-300 hover:text-slate-600 p-1 rounded-lg"
          >
            <MoreVertical className="w-4 h-4" />
          </button>
        </div>

        {/* Context Dropdown Menu matching media_1790088397090.png */}
        {isMenuOpen && (
          <div
            className="absolute right-2 top-12 w-32 bg-white rounded-xl border border-slate-200 shadow-xl py-1 z-30 animate-fade-in text-left"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => {
                setSelectedStepId(step.id);
                setContextMenuStepId(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 flex items-center gap-2 font-medium"
            >
              Edit step
            </button>
            <button
              onClick={() => {
                handleDeleteStep(step.id);
                setContextMenuStepId(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 flex items-center gap-2 font-medium"
            >
              Delete step
            </button>
          </div>
        )}
      </div>
    );
  };

  // Render centered vertical connector line with Plus button
  const renderVerticalConnector = (target) => (
    <div className="flex flex-col items-center justify-center relative my-0 shrink-0">
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

  // Recursive Branch / Subtree Renderer
  const renderBranchSubtree = (branchSteps, parentStepId, branchKey, endsHere) => {
    return (
      <div className="flex flex-col items-center w-full">
        {branchSteps && branchSteps.length > 0 ? (
          branchSteps.map((step, idx) => (
            <div key={step.id} className="flex flex-col items-center w-full">
              {renderVerticalConnector({
                type: 'branch',
                parentStepId,
                branchKey,
                index: idx,
              })}
              {renderCard(step)}
              {step.branches && renderBranches(step)}
              {/* If last in this linear branch list and does not branch, show leaf */}
              {!step.branches && idx === branchSteps.length - 1 && (
                <div className="flex flex-col items-center mt-0">
                  <div className="w-[2px] h-4 bg-slate-300" />
                  <div className="flex items-center gap-1.5">
                    <div className="px-3 py-1 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 shadow-2xs">
                      End
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPaletteTarget({
                          type: 'branch',
                          parentStepId,
                          branchKey,
                          index: branchSteps.length,
                        });
                        setPaletteOpen(true);
                      }}
                      className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center shadow-xs transition-colors"
                      title="Add step to end"
                    >
                      <Plus className="w-4 h-4 stroke-[2.5]" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        ) : endsHere ? (
          /* Ends Here Badge matching media_1790088201124.png Voice Note Left Branch */
          <div className="flex flex-col items-center mt-1">
            <div className="w-[2px] h-3 bg-slate-300" />
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setPaletteTarget({ type: 'branch', parentStepId, branchKey, index: 0 });
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
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setPaletteTarget({ type: 'branch', parentStepId, branchKey, index: 0 });
                setPaletteOpen(true);
              }}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 mt-2.5"
            >
              + Add a step
            </button>
          </div>
        ) : (
          /* Standard Leaf End button */
          <div className="flex flex-col items-center mt-1">
            <div className="w-[2px] h-4 bg-slate-300" />
            <div className="flex items-center gap-1.5">
              <div className="px-3 py-1 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-600 shadow-2xs">
                End
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setPaletteTarget({ type: 'branch', parentStepId, branchKey, index: 0 });
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
    );
  };

  // Render SVG Branch Splitter for any branching node
  const renderBranches = (node) => {
    if (!node.branches) return null;
    const { left, right } = node.branches;

    return (
      <div className="flex flex-col items-center w-full">
        {/* Orthogonal SVG Connector */}
        <div className="w-full flex justify-center">
          <svg className="w-[680px] h-[36px] overflow-visible" viewBox="0 0 680 36" fill="none">
            {/* Center trunk dropping from parent */}
            <line x1="340" y1="0" x2="340" y2="18" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Horizontal splitter busbar */}
            <line x1="170" y1="18" x2="510" y2="18" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Left drop line into left condition pill */}
            <line x1="170" y1="18" x2="170" y2="36" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
            {/* Right drop line into right condition pill */}
            <line x1="510" y1="18" x2="510" y2="36" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>

        {/* Two Branch Columns */}
        <div className="flex items-start justify-center gap-16 w-full">
          {/* Left Branch */}
          <div className="w-[340px] flex flex-col items-center">
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
            {renderBranchSubtree(left.steps, node.id, 'left', left.endsHere)}
          </div>

          {/* Right Branch */}
          <div className="w-[340px] flex flex-col items-center">
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
            {renderBranchSubtree(right.steps, node.id, 'right', false)}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div
      className="relative flex h-full w-full bg-[#f8fafc] overflow-hidden select-none"
      onClick={() => {
        setContextMenuStepId(null);
        setSelectedStepId(null);
      }}
    >
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

      {/* Action Toast Banner matching media_1790088446398.png */}
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

      {/* Zoom Controls (Top Left) */}
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

      {/* Main Flowchart Tree Canvas Area (Scrollable) */}
      <div className="flex-1 overflow-auto flex flex-col items-center pt-24 pb-48 px-10">
        <div
          className="flex flex-col items-center transition-transform duration-150 origin-top"
          style={{ transform: `scale(${zoomLevel / 100})` }}
        >
          {/* SEQUENCE START Pill (media_1790088201124.png) */}
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs font-bold tracking-wider text-slate-500 shadow-2xs mb-0">
            <Navigation className="w-3.5 h-3.5 text-slate-400 rotate-45" />
            <span>SEQUENCE START</span>
          </div>

          {/* Root vertical trunk lines and recursive nodes */}
          {tree.map((rootStep, index) => (
            <div key={rootStep.id} className="flex flex-col items-center w-full">
              {renderVerticalConnector({
                type: 'linear',
                stepId: index > 0 ? tree[index - 1].id : 'start',
              })}
              {renderCard(rootStep)}
              {rootStep.branches && renderBranches(rootStep)}
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT DRAWER: Step Configuration Inspector matching media_1790088114763.png */}
      {selectedStep && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-96 max-w-[90vw] bg-white border-l border-gray-200 shadow-2xl z-30 flex flex-col animate-slide-left"
        >
          {/* Drawer Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
                {React.createElement(getNodeVisuals(selectedStep.type).icon, { className: 'w-5 h-5' })}
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

          {/* Drawer Content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5 text-left">
            {/* Timing Stepper */}
            <div>
              <label className="block text-xs font-bold text-gray-900 mb-1">Wait before this step</label>
              <div className="flex items-center gap-2 mt-1.5">
                <div className="flex items-center border border-gray-200 rounded-xl bg-white shadow-2xs overflow-hidden">
                  <button
                    onClick={() =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          delay_days: Math.max(0, (selectedStep.delay_days || 0) - 1),
                        })
                      )
                    }
                    className="px-3 py-1.5 text-gray-500 hover:bg-gray-100 text-sm font-bold"
                  >
                    –
                  </button>
                  <span className="px-4 py-1.5 text-xs font-bold text-gray-900 w-12 text-center">
                    {selectedStep.delay_days || 0}
                  </span>
                  <button
                    onClick={() =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          delay_days: (selectedStep.delay_days || 0) + 1,
                        })
                      )
                    }
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

            {/* VOICE NOTE CONFIGURATION */}
            {selectedStep.type === 'voice_note' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
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
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, script: e.target.value },
                          isActionRequired: e.target.value.trim().length === 0,
                          subtitle: e.target.value.trim().length > 0 ? 'AI voice note ready' : 'Action required',
                        })
                      )
                    }
                    placeholder="Keep it short and natural: hello, one reason you reached out, a soft ask."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                  <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">
                    LinkedIn caps a voice note at about a minute; this limit keeps the spoken note under it, even for a slower voice.
                  </p>
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

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Fallback if a variable is missing (490 characters)
                  </label>
                  <textarea
                    rows={2}
                    maxLength={490}
                    value={selectedStep.config?.fallback || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, fallback: e.target.value },
                        })
                      )
                    }
                    placeholder="A version with no variables, always safe to send"
                    className="w-full rounded-xl border border-gray-200 p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
              </div>
            )}

            {/* INMAIL CONFIGURATION */}
            {selectedStep.type === 'inmail' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">Subject</label>
                  <input
                    type="text"
                    value={selectedStep.config?.subject || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, subject: e.target.value },
                        })
                      )
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
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, message: e.target.value },
                          isActionRequired: e.target.value.trim().length === 0,
                          subtitle: e.target.value.trim().length > 0 ? 'InMail copy ready' : 'Action required',
                        })
                      )
                    }
                    placeholder="Write your InMail copy here..."
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

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Fallback if a variable is missing
                  </label>
                  <textarea
                    rows={2}
                    value={selectedStep.config?.fallback || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, fallback: e.target.value },
                        })
                      )
                    }
                    placeholder="A version with no variables, always safe to send"
                    className="w-full rounded-xl border border-gray-200 p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
              </div>
            )}

            {/* REPLY TO COMMENT CONFIGURATION */}
            {selectedStep.type === 'reply_to_comment' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    AI Reply Template or Comment
                  </label>
                  <textarea
                    rows={4}
                    value={selectedStep.config?.reply_text || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, reply_text: e.target.value },
                          isActionRequired: e.target.value.trim().length === 0,
                          subtitle: e.target.value.trim().length > 0 ? 'Reply copy ready' : 'Action required',
                        })
                      )
                    }
                    placeholder="Thanks for engaging {{first_name}}! Appreciate your thoughts on..."
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

            {/* SEND MESSAGE CONFIGURATION */}
            {selectedStep.type === 'send_message' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">Direct Message Copy</label>
                  <textarea
                    rows={4}
                    value={selectedStep.config?.body || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, body: e.target.value },
                          isActionRequired: e.target.value.trim().length === 0,
                          subtitle: e.target.value.trim().length > 0 ? e.target.value.slice(0, 32) + '...' : 'Action required',
                        })
                      )
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
                  <strong>Prosp Tip:</strong> Connection invites without notes often get 15-20% higher acceptance rates.
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
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, note: e.target.value },
                        })
                      )
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

      {/* STEP PALETTE DRAWER (When clicking any + in the tree) */}
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
            <button
              onClick={() => {
                setPaletteOpen(false);
                setPaletteTarget(null);
              }}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6 text-left">
            {/* LinkedIn Actions */}
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
                      className="flex flex-col items-start p-2.5 rounded-xl border border-gray-200 hover:border-amber-500 hover:bg-amber-50/20 text-left transition-all group"
                    >
                      <div className={`p-2 rounded-lg ${cond.color} group-hover:scale-105 transition-transform`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-gray-900 text-xs mt-2 group-hover:text-amber-700">
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
