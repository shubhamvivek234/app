import React, { useState, useEffect, useRef } from 'react';
import { flattenTreeToDAG } from './sequenceGraph';
import SequenceReview from './SequenceReview';
import FieldConditionEditor, { DEFAULT_FIELD_CONDITION, conditionBranchLabel } from './FieldConditionEditor';
import {
  Eye, UserPlus, MessageSquare, Mic, Mail, UserCheck, ThumbsUp, MessageCircle,
  CornerDownRight, Award, GitBranch, Clock, Plus, X, ZoomIn, ZoomOut, Maximize2,
  CheckCircle2, AlertCircle, Sparkles, ChevronRight, Edit3, Trash2, MoreVertical, Navigation,
  Link2, Check, Search, ExternalLink, Play, Copy, RefreshCw, ChevronDown,
  ArrowLeft, ArrowRight, Crosshair, Users
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
  { type: 'withdraw_invite', label: 'Withdraw invite', desc: 'Withdraw pending invite (21d cooldown)', icon: X, color: 'text-amber-700 bg-amber-50' },
  { type: 'add_tag', label: 'Add tag', desc: 'Tag prospect in CRM & Inbox', icon: Award, color: 'text-emerald-700 bg-emerald-50' },
];

const EMAIL_ACTION_DEFINITIONS = [
  { type: 'find_email', label: 'Find email', desc: 'Look up a prospect email using your Hunter key', icon: Search, color: 'text-teal-700 bg-teal-50' },
  { type: 'send_email', label: 'Send email', desc: 'Send through a connected sender mailbox', icon: Mail, color: 'text-teal-700 bg-teal-50' },
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
    label: 'Check contact field',
    desc: 'Check a stored value or typed comparison',
    icon: Clock,
    color: 'text-amber-700 bg-amber-100/70',
    leftCondition: 'No',
    rightCondition: 'Yes',
  },
];

const EMAIL_CONDITION_DEFINITIONS = [
  {
    type: 'if_email_available',
    label: 'If email available',
    desc: 'Check the current stored email policy',
    icon: GitBranch,
    color: 'text-teal-700 bg-teal-50',
    leftCondition: 'No',
    rightCondition: 'Yes',
  },
];

const VARIABLE_PILLS = [
  '{{first_name}}',
  '{{last_name}}',
  '{{full_name}}',
  '{{headline}}',
  '{{company_name}}',
  '{{job_title}}',
  '{{position}}',
  '{{industry}}',
  '{{location}}',
  '{{location_raw}}',
  '{{company_location}}',
  '{{connections_count}}',
  '{{top_skill}}',
  '{{company_followed}}',
  '{{school}}',
  '{{university_name}}',
  '{{profile_type}}',
  '{{years_in_company}}',
  '{{years_in_role}}',
  '{{mutual_connections}}',
  '{{summary}}',
];

const GUARANTEED_LINKEDIN_VARIABLE_CHIPS = [
  { label: '+ First Name', token: '{{first_name}}' },
  { label: '+ Last Name', token: '{{last_name}}' },
  { label: '+ Location', token: '{{location}}' },
];

export { flattenTreeToDAG } from './sequenceGraph';

const stepDelayHours = (step) => step.delay_hours === undefined ? (step.delay_days || 0) * 24 : step.delay_hours;
const formatDelay = (hours = 0) => {
  if (!hours) return 'No delay';
  if (hours < 24) return `Wait ${hours} hour${hours === 1 ? '' : 's'}, then`;
  if (hours % 24 === 0) {
    const wholeDays = hours / 24;
    return `Wait ${wholeDays} day${wholeDays === 1 ? '' : 's'}, then`;
  }
  return `Wait ${Math.floor(hours / 24)}d ${hours % 24}h, then`;
};

// Default sequence matching Template 1 "Connect and follow up" (media_1790104824235.png)
export const DEFAULT_TREE = [
  {
    id: 'step_connect_root',
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
        endsHere: true,
      },
      right: {
        condition: 'accepted',
        type: 'success',
        steps: [
          {
            id: 'step_msg_followup',
            type: 'send_message',
            title: 'Send message',
            subtitle: 'Hi {{first_name}}, thanks for ...',
            delay_days: 1,
            config: {
              body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
            },
            branches: {
              left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
              right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
            },
          },
        ],
      },
    },
  },
];

export default function SequenceCanvas({ campaignId, onSave, onRegisterSave, templateTree, onRegisterTemplateSnapshot }) {
  const templateMode = templateTree !== undefined;
  const [tree, setTree] = useState(() => {
    if (!templateMode) return DEFAULT_TREE;
    try {
      const supplied = JSON.parse(JSON.stringify(templateTree));
      if (!Array.isArray(supplied) || !supplied.length) return [];
      flattenTreeToDAG(supplied);
      return supplied;
    } catch { return []; }
  });
  const [selectedStepId, setSelectedStepId] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteTarget, setPaletteTarget] = useState(null); // { type: 'linear' | 'branch', stepId, branchKey, index }
  const [capabilities, setCapabilities] = useState(null);
  const [capabilityError, setCapabilityError] = useState('');
  const [capabilityRetryKey, setCapabilityRetryKey] = useState(0);
  const [nodeCounts, setNodeCounts] = useState({});
  const [nodeCountsLoading, setNodeCountsLoading] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const canvasViewportRef = useRef(null);
  const sequenceTreeRef = useRef(null);

  const clampPan = (x, y) => ({
    x: Math.max(-3000, Math.min(3000, x)),
    y: Math.max(-3000, Math.min(1000, y)),
  });

  const handleFitToScreen = () => {
    if (!canvasViewportRef.current || !sequenceTreeRef.current) {
      setZoomLevel(60);
      setPanOffset({ x: 0, y: 0 });
      return;
    }
    const viewport = canvasViewportRef.current.getBoundingClientRect();
    const treeEl = sequenceTreeRef.current;
    const treeWidth = treeEl.offsetWidth || 800;
    const treeHeight = treeEl.offsetHeight || 600;

    const availableWidth = Math.max(viewport.width - 100, 320);
    const availableHeight = Math.max(viewport.height - 140, 320);

    const scaleX = availableWidth / treeWidth;
    const scaleY = availableHeight / treeHeight;
    const idealScale = Math.min(scaleX, scaleY, 1.0);
    const targetZoom = Math.max(20, Math.min(100, Math.round(idealScale * 100)));

    setZoomLevel(targetZoom);
    setPanOffset({ x: 0, y: 0 });
  };

  const handleCanvasMouseDown = (e) => {
    if (e.button !== 0) return;
    if (e.target.closest('button, input, textarea, select, a, [role="button"], .card-interactive')) {
      return;
    }
    setIsPanning(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: panOffset.x,
      panY: panOffset.y,
    };
  };

  const handleCanvasMouseMove = (e) => {
    if (!isPanning) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    setPanOffset(clampPan(dragStartRef.current.panX + dx, dragStartRef.current.panY + dy));
  };

  const handleCanvasMouseUp = () => {
    if (isPanning) {
      setIsPanning(false);
    }
  };

  const handleCanvasWheel = (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const zoomDelta = e.deltaY < 0 ? 5 : -5;
      setZoomLevel((z) => Math.max(20, Math.min(200, z + zoomDelta)));
      return;
    }
    setPanOffset((prev) => clampPan(prev.x - e.deltaX, prev.y - e.deltaY));
  };

  const [showTip, setShowTip] = useState(true);
  const [toastMessage, setToastMessage] = useState(null);
  const [sequenceLoadError, setSequenceLoadError] = useState('');
  const [loadedCampaignId, setLoadedCampaignId] = useState(null);
  const [sequenceRetryKey, setSequenceRetryKey] = useState(0);
  const hasLoaded = useRef(false);
  const treeRef = useRef(tree);
  treeRef.current = tree;

  useEffect(() => {
    let cancelled = false;
    setCapabilities(null);
    setCapabilityError('');
    const loadCapabilities = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch('/api/v1/outreach/campaigns/features/sequence-capabilities', {
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (!response.ok) throw new Error('Step availability could not be checked.');
        const data = await response.json();
        if (!Array.isArray(data?.capabilities)) throw new Error('Step availability could not be checked.');
        if (!cancelled) setCapabilities(Object.fromEntries(data.capabilities
          .filter((item) => item && typeof item.type === 'string')
          .map((item) => [item.type, item])));
      } catch (_) {
        if (!cancelled) setCapabilityError('Step availability could not be checked. Retry before adding steps.');
      }
    };
    loadCapabilities();
    return () => { cancelled = true; };
  }, [capabilityRetryKey]);

  useEffect(() => {
    if (templateMode || !campaignId || campaignId === 'new') return;
    let cancelled = false;
    const fetchNodeCounts = async () => {
      try {
        setNodeCountsLoading(true);
        const token = localStorage.getItem('token');
        const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/node-counts`, {
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) {
          setNodeCounts(data?.waiting_node_counts || data?.node_counts || {});
        }
      } catch (_) {
        // Non-blocking
      } finally {
        if (!cancelled) setNodeCountsLoading(false);
      }
    };
    fetchNodeCounts();
    return () => { cancelled = true; };
  }, [campaignId, templateMode]);

  const stepCapability = (type) => capabilities?.[type] || null;
  const stepReason = (type) => {
    const capability = stepCapability(type);
    if (!capability) return capabilityError || (capabilities ? 'Not available in this deployment.' : 'Step availability is still loading.');
    if (capability.reason) return capability.reason;
    return capability.builder_available ? '' : 'This step is not available in the campaign builder.';
  };

  // Unravler AI Parity: AI Prompt Library & Preview State
  const [promptDrawerOpen, setPromptDrawerOpen] = useState(false);
  const [promptsList, setPromptsList] = useState([]);
  const [promptsLoading, setPromptsLoading] = useState(false);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [sequenceReviewOpen, setSequenceReviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [activeVariantTab, setActiveVariantTab] = useState('A');
  const [stepLeadsDrawer, setStepLeadsDrawer] = useState({ open: false, nodeId: null, title: '', loading: false, data: null });

  const openStepLeadsDrawer = async (step, e) => {
    if (e) e.stopPropagation();
    if (!campaignId || campaignId === 'new') return;
    setStepLeadsDrawer({ open: true, nodeId: step.id, title: step.title, loading: true, data: null });
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/sequence-step-leads?node_id=${encodeURIComponent(step.id)}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error('Failed to load step leads');
      const data = await res.json();
      setStepLeadsDrawer({ open: true, nodeId: step.id, title: step.title, loading: false, data });
    } catch {
      setStepLeadsDrawer({ open: true, nodeId: step.id, title: step.title, loading: false, data: { counts: {}, leads: [] } });
    }
  };
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewLeadId, setPreviewLeadId] = useState('');
  const [previewEvaluateAi, setPreviewEvaluateAi] = useState(false);
  const [showVariablePicker, setShowVariablePicker] = useState(false);
  const [showCreatePrompt, setShowCreatePrompt] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptText, setNewPromptText] = useState('');
  const [promptSearch, setPromptSearch] = useState('');
  const [inspectedPromptToken, setInspectedPromptToken] = useState(null);
  const [isSpeakingPreview, setIsSpeakingPreview] = useState(false);
  const [voicesList, setVoicesList] = useState([]);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef(null);
  const recordingChunksRef = useRef([]);
  const recordingTimerRef = useRef(null);
  const voiceFileInputRef = useRef(null);

  useEffect(() => {
    if (templateMode) return;
    let active = true;
    const token = localStorage.getItem('token');
    fetch('/api/v1/outreach/voice', {
      credentials: 'include',
      headers: { Authorization: token ? `Bearer ${token}` : '' },
    })
      .then((res) => (res && res.ok ? res.json() : null))
      .then((data) => {
        if (active && data && Array.isArray(data.voices)) {
          setVoicesList(data.voices);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        try { mediaRecorderRef.current.stop(); } catch (_) {}
      }
    };
  }, [templateMode]);

  const handleStartRecordingVoice = async () => {
    if (!selectedStep || selectedStep.type !== 'voice_note') return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
      setToastMessage('Microphone recording is not supported in this browser. Use Upload MP3 instead.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordingChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (evt) => {
        if (evt.data && evt.data.size > 0) recordingChunksRef.current.push(evt.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
        setIsRecordingVoice(false);
        const blob = new Blob(recordingChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        const reader = new FileReader();
        reader.onloadend = () => {
          const dataUrl = typeof reader.result === 'string' ? reader.result : '';
          setTree((prev) =>
            updateNode(prev, selectedStep.id, {
              config: {
                ...selectedStep.config,
                voice_mode: 'recorded',
                recorded_audio_data_url: dataUrl,
                recorded_audio_name: `voice-note-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.webm`,
                script: selectedStep.config?.script || 'Hey {{first_name}}, recorded a quick voice note for you!',
              },
              isActionRequired: false,
              subtitle: 'Recorded voice note ready',
            })
          );
          setToastMessage('Voice note recorded and attached to this step.');
        };
        reader.readAsDataURL(blob);
      };
      setRecordingSeconds(0);
      setIsRecordingVoice(true);
      recorder.start();
      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds((s) => {
          if (s + 1 >= 60) {
            try { recorder.stop(); } catch (_) {}
            return 60;
          }
          return s + 1;
        });
      }, 1000);
    } catch (_) {
      setToastMessage('Microphone access denied. Check browser permissions or upload an audio file.');
    }
  };

  const handleStopRecordingVoice = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try { mediaRecorderRef.current.stop(); } catch (_) {}
    }
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    setIsRecordingVoice(false);
  };

  const handleUploadVoiceFile = (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedStep) return;
    if (file.size > 10 * 1024 * 1024) {
      setToastMessage('Audio file exceeds the 10 MB limit.');
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = typeof reader.result === 'string' ? reader.result : '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: {
            ...selectedStep.config,
            voice_mode: 'uploaded',
            recorded_audio_data_url: dataUrl,
            recorded_audio_name: file.name,
            script: selectedStep.config?.script || `Voice note (${file.name})`,
          },
          isActionRequired: false,
          subtitle: `Audio: ${file.name}`,
        })
      );
      setToastMessage(`Uploaded "${file.name}" for this voice note step.`);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const fetchPrompts = async () => {
    setPromptsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/prompts', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setPromptsList(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error('Failed to load prompts:', err);
    } finally {
      setPromptsLoading(false);
    }
  };

  useEffect(() => {
    treeRef.current = tree;
  }, [tree]);

  const openPromptLibrary = () => {
    if (templateMode) return;
    setPromptDrawerOpen(true);
    fetchPrompts();
  };

  const copyPromptGuidance = async (promptText) => {
    try {
      await navigator.clipboard.writeText(promptText);
      setToastMessage('Prompt guidance copied. It is not generated automatically in live campaigns.');
    } catch (_) {
      setToastMessage('Could not copy prompt guidance. Check browser clipboard permissions.');
    }
    setPromptDrawerOpen(false);
  };

  const insertPromptIntoStep = (prompt) => {
    if (!selectedStep || !prompt) return;
    const tokenStr = `✨ [${prompt.name}]`;
    insertVariable(tokenStr);
    setPromptDrawerOpen(false);
    setToastMessage(`Inserted AI prompt "${prompt.name}". Click Preview to evaluate against real leads.`);
  };

  const applyEvaluatedPreviewToStep = (evaluatedCopy) => {
    if (!selectedStep || !evaluatedCopy) return;
    const text = evaluatedCopy.trim();
    if (!text) return;
    setTree((prev) =>
      updateNode(prev, selectedStep.id, {
        config: {
          ...selectedStep.config,
          ...(selectedStep.type === 'voice_note'
            ? { script: text }
            : selectedStep.type === 'connection_request'
            ? { note: text.slice(0, 300) }
            : selectedStep.type === 'inmail'
            ? { body: text, message: text }
            : selectedStep.type === 'comment_last_post'
            ? { comment: text, comment_template: text }
            : selectedStep.type === 'reply_to_comment'
            ? { reply_text: text }
            : { body: text }),
        },
        isActionRequired: false,
        subtitle: text.slice(0, 36) + (text.length > 36 ? '...' : ''),
      })
    );
    setPreviewModalOpen(false);
    setToastMessage('Personalized AI copy applied to this step.');
  };

  const handleCreatePrompt = async () => {
    if (templateMode) return;
    if (!newPromptName.trim() || !newPromptText.trim()) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/prompts', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: newPromptName.trim(),
          prompt_text: newPromptText.trim(),
          author_name: 'You',
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setPromptsList((prev) => [created, ...prev]);
        setNewPromptName('');
        setNewPromptText('');
        setShowCreatePrompt(false);
      } else {
        const error = await res.json().catch(() => ({}));
        setToastMessage(error.detail || 'Prompt could not be saved.');
      }
    } catch (err) {
      console.error('Failed to create prompt:', err);
    }
  };

  const handleOpenPreview = async (step, overrideLeadId = undefined, overrideEvalAi = undefined) => {
    if (templateMode || !step) return;
    const template =
      step.config?.script ||
      step.config?.body ||
      step.config?.message ||
      step.config?.comment ||
      step.config?.comment_template ||
      step.config?.reply_text ||
      step.config?.note ||
      '';
    const hasAiPrompt = template.includes('✨ [');
    const evalAi = overrideEvalAi !== undefined ? overrideEvalAi : (hasAiPrompt ? true : previewEvaluateAi);
    const targetLeadId = overrideLeadId !== undefined ? overrideLeadId : previewLeadId;
    setPreviewEvaluateAi(evalAi);
    setPreviewModalOpen(true);
    setPreviewLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/prompts/preview', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          template,
          alternative_message: step?.config?.alternative_message || step?.config?.fallback || undefined,
          subject: step?.config?.subject || undefined,
          campaign_id: campaignId && campaignId !== 'new' ? campaignId : undefined,
          lead_id: targetLeadId || undefined,
          evaluate_ai: evalAi,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewData(data);
        if (data.selected_lead_id) {
          setPreviewLeadId(data.selected_lead_id);
        }
      } else {
        const error = await res.json().catch(() => ({}));
        setPreviewData({ error: error.detail || 'Preview could not be generated.' });
      }
    } catch (err) {
      console.error('Failed to preview message:', err);
      setPreviewData({ error: 'Preview could not be generated. Please try again.' });
    } finally {
      setPreviewLoading(false);
    }
  };

  // Load existing sequence or pre-made template tree
  useEffect(() => {
    let cancelled = false;
    hasLoaded.current = false;
    setLoadedCampaignId(null);
    setSequenceReviewOpen(false);
    setSequenceLoadError('');

    if (templateMode) {
      try {
        if (campaignId) throw new Error('Template editing cannot target a campaign.');
        if (!Array.isArray(templateTree) || !templateTree.length) throw new Error('This template has no faithful visual tree.');
        const supplied = JSON.parse(JSON.stringify(templateTree));
        flattenTreeToDAG(supplied);
        setTree(supplied);
        treeRef.current = supplied;
        setSelectedStepId(null);
        setPromptDrawerOpen(false);
        setPreviewModalOpen(false);
        hasLoaded.current = true;
        setLoadedCampaignId(campaignId);
      } catch (error) { setSequenceLoadError(error.message || 'Template graph needs review.'); }
      return;
    }

    if (!campaignId || campaignId === 'new' || campaignId === 'new_campaign') {
      hasLoaded.current = true;
      setLoadedCampaignId(campaignId);
      return;
    }
    const loadSequence = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`/api/v1/outreach/sequences/${campaignId}`, {
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Sequence could not be loaded.');
        if (data.editor_error) throw new Error(data.editor_error);
        if (!Array.isArray(data.tree) || !data.tree.length) throw new Error('This saved sequence has no faithful visual tree. Review its original graph before editing.');
        if (!cancelled) {
          if (data.tree && Array.isArray(data.tree) && data.tree.length > 0) {
            flattenTreeToDAG(data.tree);
            setTree(data.tree);
            setSelectedStepId(null);
          }
          hasLoaded.current = true;
          setLoadedCampaignId(campaignId);
        }
      } catch (err) {
        console.error('Failed to load sequence:', err);
        if (!cancelled) setSequenceLoadError(err.message || 'Sequence could not be loaded.');
      }
    };
    loadSequence();
    return () => { cancelled = true; };
  }, [campaignId, sequenceRetryKey, templateMode, templateTree]);

  const templateSnapshot = React.useCallback(() => {
    if (!templateMode || campaignId || !hasLoaded.current || sequenceLoadError) throw new Error('Template draft is unavailable.');
    const current = JSON.parse(JSON.stringify(treeRef.current));
    return {...flattenTreeToDAG(current), tree:current};
  }, [templateMode, campaignId, sequenceLoadError]);
  useEffect(() => {
    if (templateMode && onRegisterTemplateSnapshot) onRegisterTemplateSnapshot(templateSnapshot);
    return () => { if (onRegisterTemplateSnapshot) onRegisterTemplateSnapshot(null); };
  }, [templateMode, onRegisterTemplateSnapshot, templateSnapshot]);

  const saveQueueRef = React.useRef(Promise.resolve());
  const persistSequence = React.useCallback((treeToSave = treeRef.current, assertCurrent) => {
    if (templateMode || !campaignId || campaignId === 'new' || campaignId === 'new_campaign') return false;
    if (!hasLoaded.current) {
      setToastMessage('Sequence is still loading. Wait a moment, then save again.');
      return false;
    }
    const save = saveQueueRef.current.catch(() => {}).then(async () => {
      try {
        assertCurrent?.();
        const token = localStorage.getItem('token');
        const { nodes, edges } = flattenTreeToDAG(treeToSave);
        const res = await fetch('/api/v1/outreach/sequences', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({ campaign_id: campaignId, nodes, edges, tree: treeToSave }),
        });
        assertCurrent?.();
        if (!res.ok) {
          const error = await res.json().catch(() => ({}));
          assertCurrent?.();
          setToastMessage(error.detail || 'Sequence could not be saved. Please try again.');
          return false;
        }
        if (onSave) onSave({ nodes, edges, tree: treeToSave });
        return true;
      } catch (err) {
        try { assertCurrent?.(); } catch (_) { return false; }
        console.error('Failed to save sequence:', err);
        setToastMessage(err.message || 'Sequence could not be saved. Check its graph and try again.');
        return false;
      }
    });
    saveQueueRef.current = save;
    return save;
  }, [campaignId, onSave, templateMode]);

  useEffect(() => {
    if (onRegisterSave) onRegisterSave(templateMode ? null : persistSequence);
    return () => { if (onRegisterSave) onRegisterSave(null); };
  }, [onRegisterSave, persistSequence, templateMode]);

  // Auto-save sequence debounced when tree changes
  useEffect(() => {
    if (templateMode || !hasLoaded.current || !campaignId || campaignId === 'new' || campaignId === 'new_campaign') return;
    const timer = setTimeout(() => persistSequence(tree), 600);
    return () => clearTimeout(timer);
  }, [tree, campaignId, persistSequence, templateMode]);

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
        const updated = typeof updater === 'function' ? updater(node) : { ...node, ...updater };
        if (Object.hasOwn(updated, 'delay_hours')) delete updated.delay_days;
        return updated;
      }
      if (node.branches) {
        return {
          ...node,
          branches: Object.fromEntries(Object.entries(node.branches).map(([key, branch]) => [key, { ...branch, steps: updateNode(branch.steps || [], id, updater) }])),
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
            branches: Object.fromEntries(Object.entries(node.branches).map(([key, branch]) => [key, { ...branch, steps: deleteNode(branch.steps || [], id) }])),
          };
        }
        return node;
      });
  };

  const makeStepId = () =>
    `step_${globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`}`;

  const subtreeHasType = (steps, types) =>
    (steps || []).some(
      (s) =>
        types.includes(s.type) ||
        (s.branches &&
          Object.values(s.branches).some((b) => subtreeHasType(b?.steps || [], types)))
    );

  const getPathStateAtTarget = (nodes, target, state = { connected: 'unknown', email: 'unknown', connectionAncestorId: null, leftBranchLength: 0 }) => {
    let curr = { ...state };
    const advanceStep = (s) => {
      if (s.type === 'withdraw_invite') curr.connected = 'withdrawn';
      if (s.type === 'find_email') curr.email = 'unknown';
    };
    if (!target || target.type === 'linear') {
      if (target?.stepId === 'start') return curr;
      for (const s of nodes || []) {
        advanceStep(s);
        if (s.id === target?.stepId) return curr;
      }
      return curr;
    }
    for (const s of nodes || []) {
      if (s.id === target.parentStepId && s.branches && target.branchKey) {
        let nextConn = curr.connected;
        let nextEmail = curr.email;
        let connAncestor = curr.connectionAncestorId;
        let leftLen = curr.leftBranchLength;
        if (s.type === 'connection_request' || s.type === 'if_connected') {
          if (target.branchKey === 'right') {
            nextConn = 'yes';
            connAncestor = s.id;
            leftLen = (s.branches.left?.steps || []).length;
          } else {
            nextConn = s.type === 'connection_request' || curr.connected === 'invited' ? 'invited' : 'no';
          }
        }
        if (s.type === 'if_email_available') {
          nextEmail = target.branchKey === 'right' ? 'yes' : 'no';
        }
        const branchSteps = s.branches[target.branchKey]?.steps || [];
        const limit = target.index !== undefined ? target.index : branchSteps.length;
        let branchState = { connected: nextConn, email: nextEmail, connectionAncestorId: connAncestor, leftBranchLength: leftLen };
        for (let i = 0; i < Math.min(limit, branchSteps.length); i += 1) {
          if (branchSteps[i].type === 'withdraw_invite') branchState.connected = 'withdrawn';
          if (branchSteps[i].type === 'find_email') branchState.email = 'unknown';
        }
        return branchState;
      }
      advanceStep(s);
      if (s.branches) {
        for (const [bKey, bVal] of Object.entries(s.branches)) {
          let nextConn = curr.connected;
          let nextEmail = curr.email;
          let connAncestor = curr.connectionAncestorId;
          let leftLen = curr.leftBranchLength;
          if (s.type === 'connection_request' || s.type === 'if_connected') {
            if (bKey === 'right') {
              nextConn = 'yes';
              connAncestor = s.id;
              leftLen = (s.branches.left?.steps || []).length;
            } else {
              nextConn = s.type === 'connection_request' || curr.connected === 'invited' ? 'invited' : 'no';
            }
          }
          if (s.type === 'if_email_available') {
            nextEmail = bKey === 'right' ? 'yes' : 'no';
          }
          const found = findNode(bVal?.steps || [], target.parentStepId);
          if (found) {
            return getPathStateAtTarget(bVal?.steps || [], target, {
              connected: nextConn,
              email: nextEmail,
              connectionAncestorId: connAncestor,
              leftBranchLength: leftLen,
            });
          }
        }
      }
    }
    return curr;
  };

  const spliceStepIntoList = (list, index, newStepOrSteps) => {
    const stepsToInsert = (Array.isArray(newStepOrSteps) ? newStepOrSteps : [newStepOrSteps]).filter(Boolean);
    if (!stepsToInsert.length) return list;
    const before = list.slice(0, index).map((item, idx, arr) =>
      idx === arr.length - 1 && item.endsHere ? { ...item, endsHere: false } : item
    );
    const trailing = list.slice(index);
    const lastInserted = stepsToInsert[stepsToInsert.length - 1];

    if (lastInserted.branches && trailing.length > 0) {
      let targetBranch = 'right';
      let adjustedTrailing = trailing;
      if (['send_message', 'voice_note', 'inmail'].includes(lastInserted.type)) {
        targetBranch = 'left';
      } else if (
        lastInserted.type === 'if_connected' &&
        subtreeHasType(trailing, ['connection_request', 'withdraw_invite'])
      ) {
        targetBranch = 'left';
      } else if (
        lastInserted.type === 'connection_request' &&
        subtreeHasType(trailing, ['connection_request', 'withdraw_invite'])
      ) {
        targetBranch = 'left';
        if (trailing[0]?.type === 'connection_request') {
          const withdrawStep = {
            id: makeStepId(),
            type: 'withdraw_invite',
            title: 'Withdraw invite',
            subtitle: 'Withdraw unaccepted invite',
            delay_days: 3,
            config: {},
          };
          const cooledFirst = {
            ...trailing[0],
            delay_hours: Math.max(stepDelayHours(trailing[0]), 504),
          };
          delete cooledFirst.delay_days;
          adjustedTrailing = [withdrawStep, cooledFirst, ...trailing.slice(1)];
        }
      }
      const existingBranch = lastInserted.branches[targetBranch] || { steps: [] };
      const updatedLast = {
        ...lastInserted,
        branches: {
          ...lastInserted.branches,
          [targetBranch]: {
            ...existingBranch,
            steps: [...(existingBranch.steps || []), ...adjustedTrailing],
            endsHere: false,
          },
        },
      };
      return [...before, ...stepsToInsert.slice(0, -1), updatedLast];
    }

    return [...before, ...stepsToInsert, ...trailing];
  };

  // Insert a new step into the tree
  const insertStep = (nodes, target, newStep) => {
    if (!target) return spliceStepIntoList(nodes, nodes.length, newStep);

    // Linear insertion after target stepId
    if (target.type === 'linear') {
      if (target.stepId === 'start') return spliceStepIntoList(nodes, 0, newStep);
      const idx = nodes.findIndex((n) => n.id === target.stepId);
      if (idx !== -1) {
        return spliceStepIntoList(nodes, idx + 1, newStep);
      }
    }

    // Branch insertion inside a branch
    return nodes.map((node) => {
      if (node.id === target.parentStepId && node.branches && target.branchKey) {
        const branch = node.branches[target.branchKey];
        if (!branch) return node;
        const steps = branch.steps || [];
        const insertIdx = target.index !== undefined ? target.index : steps.length;
        return {
          ...node,
          branches: {
            ...node.branches,
            [target.branchKey]: {
              ...branch,
              steps: spliceStepIntoList(steps, insertIdx, newStep),
              endsHere: false,
            },
          },
        };
      }
      if (node.branches) {
        return {
          ...node,
          branches: Object.fromEntries(Object.entries(node.branches).map(([key, branch]) => [key, { ...branch, steps: insertStep(branch.steps || [], target, newStep) }])),
        };
      }
      return node;
    });
  };

  const handleAddStepFromPalette = (type) => {
    if (!stepCapability(type)?.builder_available) return;
    const allConditions = [...CONDITION_DEFINITIONS, ...EMAIL_CONDITION_DEFINITIONS];
    const isCondition = allConditions.some((c) => c.type === type);
    const condDef = allConditions.find((c) => c.type === type);
    const actionDef = [...ACTION_DEFINITIONS, ...EMAIL_ACTION_DEFINITIONS].find((a) => a.type === type);

    // If user clicks Connection request at start when starter connection_request is already alone on canvas, select it
    if (
      type === 'connection_request' &&
      paletteTarget?.type === 'linear' &&
      paletteTarget?.stepId === 'start' &&
      tree.length === 1 &&
      tree[0]?.type === 'connection_request' &&
      !(tree[0]?.branches?.left?.steps?.length) &&
      !(tree[0]?.branches?.right?.steps?.length)
    ) {
      setSelectedStepId(tree[0].id);
      setToastMessage('Connection request selected.');
      setPaletteOpen(false);
      setPaletteTarget(null);
      return;
    }

    const newId = makeStepId();
    let newStep = null;

    if (isCondition && condDef) {
      const defaultCondConfig =
        type === 'has_data_in_column'
          ? { ...DEFAULT_FIELD_CONDITION }
          : ['if_connected', 'if_opened_message', 'open_profile_check'].includes(type)
          ? { timeout_days: 3 }
          : {};
      newStep = {
        id: newId,
        type: condDef.type,
        title: condDef.label,
        subtitle: condDef.desc,
        delay_days: 0,
        config: defaultCondConfig,
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
      const defaultActionConfigs = {
        send_message: {
          body: 'Hi {{first_name}}, thanks for connecting! Wanted to reach out regarding your work at {{company_name}}.',
        },
        voice_note: {
          script: 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!',
        },
        inmail: {
          subject: 'Quick question, {{first_name}}',
          body: 'Hi {{first_name}}, wanted to connect regarding {{company_name}}.',
          message: 'Hi {{first_name}}, wanted to connect regarding {{company_name}}.',
        },
        send_email: {
          subject: 'Quick question, {{first_name}}',
          body: 'Hi {{first_name}},\n\nWanted to reach out regarding your work at {{company_name}}.',
        },
        comment_last_post: {
          mode: 'custom',
          comment: 'Great insights on this, {{first_name}}!',
          comment_template: 'Great insights on this, {{first_name}}!',
        },
        like_last_post: {
          max_post_age_days: 30,
          skip_if_no_posts: true,
        },
        follow: {
          skip_if_following: true,
        },
        add_tag: {
          tag_name: 'Hot lead',
          auto_tag: 'Hot lead',
        },
      };
      newStep = {
        id: newId,
        type: actionDef.type,
        title: actionDef.label,
        subtitle: actionDef.desc,
        delay_days: 0,
        config: defaultActionConfigs[type] ? { ...defaultActionConfigs[type] } : {},
        isActionRequired: false,
      };

      if (type === 'connection_request') {
        newStep.branches = {
          left: { condition: 'not accepted yet', type: 'danger', steps: [] },
          right: { condition: 'accepted', type: 'success', steps: [] },
        };
      } else if (isBranchingAction) {
        newStep.branches = {
          left: { condition: 'no reply', type: 'danger', steps: [] },
          right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
        };
      }
    }

    if (newStep) {
      let effectiveTarget = paletteTarget;
      let pathState = getPathStateAtTarget(tree, effectiveTarget);

      // Redirect connection_request or withdraw_invite away from an already-connected ('yes') branch
      if (
        ['connection_request', 'withdraw_invite'].includes(type) &&
        pathState.connected === 'yes' &&
        pathState.connectionAncestorId
      ) {
        effectiveTarget = {
          type: 'branch',
          parentStepId: pathState.connectionAncestorId,
          branchKey: 'left',
          index: pathState.leftBranchLength,
        };
        pathState = getPathStateAtTarget(tree, effectiveTarget);
      }

      let stepsToInsert = newStep;

      if (['send_message', 'voice_note'].includes(type) && ['no', 'invited', 'withdrawn'].includes(pathState.connected)) {
        // Wrap in a positive connection check so negative/invited/withdrawn paths are guarded
        stepsToInsert = {
          id: makeStepId(),
          type: 'if_connected',
          title: 'If connected',
          subtitle: 'Check connection status',
          delay_days: 1,
          config: { timeout_days: 3 },
          branches: {
            left: { condition: 'not connected', type: 'danger', steps: [] },
            right: { condition: 'connected', type: 'success', steps: [newStep] },
          },
        };
      } else if (type === 'send_email' && pathState.email === 'no') {
        stepsToInsert = [
          {
            id: makeStepId(),
            type: 'find_email',
            title: 'Find email',
            subtitle: 'Find verified work email',
            delay_days: 0,
            config: {},
          },
          newStep,
        ];
      } else if (type === 'connection_request') {
        if (pathState.connected === 'withdrawn') {
          newStep = { ...newStep, delay_hours: 504 };
          delete newStep.delay_days;
          stepsToInsert = newStep;
        } else if (pathState.connected === 'invited') {
          const cooledInvite = { ...newStep, delay_hours: 504 };
          delete cooledInvite.delay_days;
          stepsToInsert = [
            {
              id: makeStepId(),
              type: 'withdraw_invite',
              title: 'Withdraw invite',
              subtitle: 'Withdraw unaccepted invite',
              delay_days: 3,
              config: {},
            },
            cooledInvite,
          ];
        }
      }

      setTree((prev) => insertStep(prev, effectiveTarget, stepsToInsert));
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
    const delayHours = stepDelayHours(step);
    if (delayHours % 24 !== 0) {
      setTempDelayValue(delayHours);
      setTempDelayUnit('hours');
    } else {
      setTempDelayValue(delayHours / 24);
      setTempDelayUnit('days');
    }
  };

  const handleSaveInlineDelay = (stepId, e) => {
    e.stopPropagation();
    const val = Number(tempDelayValue);
    const hours = tempDelayUnit === 'hours' ? val : val * 24;
    if (!Number.isInteger(hours) || hours < 0 || hours > 8760) { setToastMessage('Use whole hours from 0 to 8760.'); return; }
    setTree((prev) => updateNode(prev, stepId, { delay_hours: hours }));
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
      const curr = selectedStep.config?.body ?? selectedStep.config?.message ?? '';
      const nextVal = curr ? `${curr} ${variable}` : variable;
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, body: nextVal, message: nextVal },
          isActionRequired: false,
          subtitle: 'InMail message configured',
        })
      );
    } else if (selectedStep.type === 'comment_last_post') {
      const isAi = selectedStep.config?.mode === 'ai';
      const curr = isAi
        ? (selectedStep.config?.ai_prompt || '')
        : (selectedStep.config?.comment ?? selectedStep.config?.comment_template ?? '');
      const nextVal = curr ? `${curr} ${variable}` : variable;
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: isAi
            ? {
                ...selectedStep.config,
                ai_prompt: nextVal,
                comment: selectedStep.config?.comment || 'Great insights on this, {{first_name}}!',
                comment_template: selectedStep.config?.comment_template || 'Great insights on this, {{first_name}}!',
              }
            : { ...selectedStep.config, comment: nextVal, comment_template: nextVal },
          isActionRequired: false,
          subtitle: 'Comment template set',
        })
      );
    } else if (selectedStep.type === 'send_message' || selectedStep.type === 'send_email') {
      const curr = selectedStep.config?.body || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, body: curr ? `${curr} ${variable}` : variable },
          isActionRequired: false,
          subtitle: selectedStep.type === 'send_email' ? 'Email body configured' : 'Direct message configured',
        })
      );
    } else if (selectedStep.type === 'connection_request') {
      const curr = selectedStep.config?.note || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, note: curr ? `${curr} ${variable}` : variable },
        })
      );
    } else if (selectedStep.type === 'reply_to_comment') {
      const curr = selectedStep.config?.reply_text || '';
      setTree((prev) =>
        updateNode(prev, selectedStep.id, {
          config: { ...selectedStep.config, reply_text: curr ? `${curr} ${variable}` : variable },
          isActionRequired: false,
          subtitle: 'Reply copy ready',
        })
      );
    }
  };

  const getNodeVisuals = (type) => {
    const act = [...ACTION_DEFINITIONS, ...EMAIL_ACTION_DEFINITIONS].find((a) => a.type === type);
    if (act) return { icon: act.icon, color: act.color };
    const cond = [...CONDITION_DEFINITIONS, ...EMAIL_CONDITION_DEFINITIONS].find((c) => c.type === type);
    if (cond) return { icon: cond.icon, color: cond.color };
    return { icon: Eye, color: 'text-indigo-600 bg-indigo-50' };
  };

  const renderEditorToolbar = () => {
    const activeText =
      selectedStep?.config?.script ||
      selectedStep?.config?.body ||
      selectedStep?.config?.message ||
      selectedStep?.config?.comment ||
      selectedStep?.config?.comment_template ||
      selectedStep?.config?.reply_text ||
      selectedStep?.config?.note ||
      '';
    const detectedPromptNames = [];
    const tokenRegex = /✨\s*\[([^\]]+)\]/g;
    let m;
    while ((m = tokenRegex.exec(activeText)) !== null) {
      const pName = m[1].trim();
      if (pName && !detectedPromptNames.includes(pName)) {
        detectedPromptNames.push(pName);
      }
    }

    return (
      <div className="flex flex-col gap-2 mb-2">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
          {!templateMode && <button
            type="button"
            onClick={openPromptLibrary}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-purple-50 hover:bg-purple-100 text-purple-700 text-xs font-semibold border border-purple-200 shadow-2xs transition-colors shrink-0"
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-600" />
            Prompt guidance
          </button>}
          <button
            type="button"
            onClick={() => setShowVariablePicker(!showVariablePicker)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-gray-50 hover:bg-gray-100 text-gray-700 text-xs font-semibold border border-gray-200 transition-colors shrink-0"
          >
            + Contact Variables
          </button>
          {!templateMode && <button
            type="button"
            onClick={() => handleOpenPreview(selectedStep)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold border border-indigo-200 shadow-2xs transition-colors ml-auto shrink-0"
          >
            <Eye className="w-3.5 h-3.5" />
            Preview
          </button>}
        </div>

        {detectedPromptNames.length > 0 && !templateMode && (
          <div className="p-2.5 rounded-xl bg-purple-50/70 border border-purple-200 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700 flex items-center gap-1">
                <Sparkles className="w-3 h-3" /> Active AI Prompts (Click to inspect)
              </span>
              {inspectedPromptToken && (
                <button
                  type="button"
                  onClick={() => setInspectedPromptToken(null)}
                  className="text-[10px] font-semibold text-purple-600 hover:underline"
                >
                  Hide details
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {detectedPromptNames.map((pName) => (
                <button
                  key={pName}
                  type="button"
                  onClick={() => {
                    if (!promptsList.length) fetchPrompts();
                    setInspectedPromptToken(inspectedPromptToken === pName ? null : pName);
                  }}
                  onDoubleClick={() => {
                    if (!promptsList.length) fetchPrompts();
                    setInspectedPromptToken(pName);
                  }}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-semibold border transition-colors ${
                    inspectedPromptToken === pName
                      ? 'bg-purple-600 text-white border-purple-600'
                      : 'bg-white text-purple-800 border-purple-200 hover:bg-purple-100'
                  }`}
                >
                  ✨ [{pName}]
                </button>
              ))}
            </div>
            {inspectedPromptToken && detectedPromptNames.includes(inspectedPromptToken) && (() => {
              const matchedPrompt = promptsList.find((p) => p.name.toLowerCase() === inspectedPromptToken.toLowerCase());
              return (
                <div className="p-2.5 rounded-lg bg-white border border-purple-200 text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-gray-900">{inspectedPromptToken}</span>
                    <span className="text-[10px] text-purple-700 font-semibold">AI Personalization Prompt</span>
                  </div>
                  <p className="text-[11px] text-gray-600 leading-relaxed">
                    {matchedPrompt?.prompt_text || `Synthesizes a personalized snippet for "${inspectedPromptToken}" using the prospect's LinkedIn profile context.`}
                  </p>
                  <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-gray-100">
                    <span className="text-[10px] font-semibold text-gray-400 mr-1">Reads LinkedIn data:</span>
                    {['Headline', 'Biography / Summary', 'Company Overview', 'Experience & Skills'].map((src) => (
                      <span key={src} className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[9px] font-semibold border border-indigo-100">
                        {src}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {showVariablePicker && (
          <div className="p-2.5 bg-gray-50/90 rounded-xl border border-gray-200 animate-in fade-in duration-150">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block mb-1.5">
              Click variable to insert
            </span>
            <div className="flex flex-wrap gap-1.5">
              {VARIABLE_PILLS.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => insertVariable(v)}
                  className="px-2 py-0.5 rounded-lg border border-indigo-100 bg-white hover:bg-indigo-50 text-indigo-700 text-[11px] font-mono transition-colors shadow-2xs"
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Per-action condition rules were only stored in the builder and never
  // enforced by the executor. Branch nodes provide the supported conditions.
  const renderConditionRuleSelector = () => null;


  // Render a Single Step Card matching Unravler (media_1790088397090.png)
  const renderCard = (step) => {
    const isSelected = selectedStepId === step.id;
    const { icon: StepIcon, color: iconStyle } = getNodeVisuals(step.type);
    const isEditingThisDelay = editingDelayId === step.id;
    const isMenuOpen = contextMenuStepId === step.id;

    return (
      <div
        key={step.id}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          setSelectedStepId(step.id);
          setContextMenuStepId(null);
        }}
        className={`card-interactive relative w-[340px] shrink-0 rounded-2xl bg-white border transition-all cursor-pointer select-none text-left ${
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
                <span>{formatDelay(stepDelayHours(step))}</span>
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
            {nodeCounts[step.id] !== undefined && nodeCounts[step.id] > 0 && (
              <div className="mt-1.5 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={(e) => openStepLeadsDrawer(step, e)}
                  data-testid={`lead-count-${step.id}`}
                  className="inline-flex items-center gap-1 rounded-full bg-indigo-50 hover:bg-indigo-100 px-2 py-0.5 text-[10px] font-bold text-indigo-700 border border-indigo-200/80 shadow-2xs transition-colors"
                >
                  <Users className="w-2.5 h-2.5" />
                  {nodeCounts[step.id]} {nodeCounts[step.id] === 1 ? 'lead waiting' : 'leads waiting'}
                </button>
              </div>
            )}
            {Array.isArray(step.config?.variants) && step.config.variants.length > 1 && (
              <div className="mt-1 flex items-center gap-1">
                <span className="inline-flex items-center gap-1 rounded-md bg-violet-50 px-1.5 py-0.5 text-[9px] font-bold text-violet-700 border border-violet-200">
                  A/B Test ({step.config.variants.map((v) => v.id).join('/')})
                </span>
              </div>
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
  const renderBranchSubtree = (branchSteps, parentStepId, branchKey, endsHere, branchCondition = '') => {
    const isTerminalReplyBranch = (branchCondition || '').toLowerCase() === 'replied';
    return (
      <div className="flex flex-col items-center shrink-0 w-auto">
        {branchSteps && branchSteps.length > 0 ? (
          branchSteps.map((step, idx) => (
            <div key={step.id} className="flex flex-col items-center shrink-0 w-auto">
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
        ) : isTerminalReplyBranch ? (
          <div className="flex flex-col items-center mt-1">
            <div className="w-[2px] h-4 bg-slate-300" />
            <div className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 border border-slate-200 text-slate-600">
              <span>✓</span>
              <span>ENDS HERE</span>
            </div>
          </div>
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
    const left = node.branches.left || { condition: 'No path saved', type: 'danger', steps: [], endsHere: true };
    const right = node.branches.right || { condition: 'No path saved', type: 'success', steps: [], endsHere: true };

    return (
      <div className="flex flex-col items-center shrink-0 w-auto">
        {/* Center vertical trunk line dropping from parent card */}
        <div className="w-[2px] h-5 bg-slate-300 shrink-0" />

        {/* 2-Column Responsive Flex Layout for Branches */}
        <div className="flex flex-row items-start justify-center shrink-0 w-auto">
          {/* Left Branch Column */}
          <div className="flex flex-col items-center min-w-[360px] shrink-0 w-auto px-4">
            {/* Orthogonal Branch Header Connector */}
            <div className="w-full h-5 relative shrink-0">
              {/* Horizontal line from center (50%) to right seam (100%) */}
              <div className="absolute top-0 right-0 left-1/2 h-[2px] bg-slate-300" />
              {/* Vertical line from top-0 down to pill at center (50%) */}
              <div className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-[2px] bg-slate-300" />
            </div>

            {/* Left Condition Pill */}
            <div
              className={`flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold tracking-tight shadow-2xs shrink-0 ${
                left.type === 'danger'
                  ? 'bg-rose-50 border border-rose-200 text-rose-600'
                  : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
              }`}
            >
              <span>{left.type === 'danger' ? '✕' : '✓'}</span>
              <span>{left.condition}</span>
            </div>

            {/* Left Branch Subtree */}
            {node.branches.left ? renderBranchSubtree(left.steps, node.id, 'left', left.endsHere, left.condition) : <p className="mt-3 text-xs text-slate-500">No path saved; this outcome ends here.</p>}
          </div>

          {/* Right Branch Column */}
          <div className="flex flex-col items-center min-w-[360px] shrink-0 w-auto px-4">
            {/* Orthogonal Branch Header Connector */}
            <div className="w-full h-5 relative shrink-0">
              {/* Horizontal line from left seam (0%) to center (50%) */}
              <div className="absolute top-0 left-0 right-1/2 h-[2px] bg-slate-300" />
              {/* Vertical line from top-0 down to pill at center (50%) */}
              <div className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-[2px] bg-slate-300" />
            </div>

            {/* Right Condition Pill */}
            <div
              className={`flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-semibold tracking-tight shadow-2xs shrink-0 ${
                right.type === 'danger'
                  ? 'bg-rose-50 border border-rose-200 text-rose-600'
                  : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
              }`}
            >
              <span>{right.type === 'danger' ? '✕' : '✓'}</span>
              <span>{right.condition}</span>
            </div>

            {/* Right Branch Subtree */}
            {node.branches.right ? renderBranchSubtree(right.steps, node.id, 'right', right.endsHere, right.condition) : <p className="mt-3 text-xs text-slate-500">No path saved; this outcome ends here.</p>}
          </div>
        </div>
      </div>
    );
  };

  if (sequenceLoadError) {
    return (
      <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 bg-white p-8 text-center">
        <p className="text-sm font-semibold text-red-700">{sequenceLoadError}</p>
        <button type="button" onClick={() => setSequenceRetryKey((value) => value + 1)} className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white">Retry loading sequence</button>
      </div>
    );
  }

  return (
    <div
      className="relative flex flex-1 h-full max-h-full min-h-0 w-full bg-[#f8fafc] overflow-hidden select-none"
      onClick={() => {
        setContextMenuStepId(null);
        setSelectedStepId(null);
      }}
    >
      <button type="button" className="absolute bottom-4 left-4 z-30 rounded-xl border border-indigo-200 bg-white px-4 py-2 text-sm font-semibold text-indigo-700 shadow-sm"
        disabled={!!sequenceLoadError || loadedCampaignId !== campaignId} onClick={(event) => { event.stopPropagation(); setSequenceReviewOpen(true); }}>Validate & preview sequence</button>
      {sequenceReviewOpen && <SequenceReview tree={tree} campaignId={campaignId} onClose={() => setSequenceReviewOpen(false)} />}
      {/* Left Canvas Column */}
      <div className="relative flex-1 h-full min-h-0 overflow-hidden flex flex-col">
        {/* Background Dot Grid */}
        <div
          className="absolute inset-0 opacity-45 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(#94a3b8 1.4px, transparent 1.4px)',
            backgroundSize: '24px 24px',
          }}
        />

        {/* Top Floating Tip Banner matching media_1790088201124.png / media_1790104824235.png */}
        {showTip && tree[0]?.type === 'connection_request' && !tree[0]?.config?.note && (
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
        {toastMessage && (() => {
          const messageText = typeof toastMessage === 'string' ? toastMessage : toastMessage?.text || '';
          const isError = /could not|failed|error|exceeds|invalid|required|bound|cycle|must|cannot|rejected/i.test(messageText) || toastMessage?.type === 'error';
          return (
            <div className={`absolute top-16 left-1/2 -translate-x-1/2 z-20 w-[640px] max-w-[90%] flex items-center justify-between gap-2 rounded-xl border px-4 py-2 text-xs font-semibold shadow-xs animate-fade-in ${
              isError
                ? 'bg-rose-50 border-rose-200 text-rose-800'
                : 'bg-emerald-50 border-emerald-200 text-emerald-800'
            }`}>
              <div className="flex items-center gap-2">
                {isError
                  ? <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  : <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />}
                <span>{messageText}</span>
              </div>
              <button
                onClick={() => setToastMessage(null)}
                className={`p-1 rounded-md transition-colors ${
                  isError ? 'text-rose-500 hover:text-rose-800 hover:bg-rose-100' : 'text-emerald-500 hover:text-emerald-800 hover:bg-emerald-100'
                }`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })()}

        {/* Zoom & Canvas Panning Controls (Top Left) */}
        <div className="absolute top-5 left-6 z-20 flex items-center gap-1 rounded-xl bg-white border border-gray-200 p-1 shadow-xs text-gray-600">
          <button
            onClick={() => setPanOffset((p) => clampPan(p.x + 180, p.y))}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-gray-600 hover:text-indigo-600 flex items-center gap-1"
            title="Move canvas left (reveals leftward steps)"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-[10px] font-semibold text-gray-500 hidden md:inline">Left</span>
          </button>
          <button
            onClick={() => setPanOffset((p) => clampPan(p.x - 180, p.y))}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-gray-600 hover:text-indigo-600 flex items-center gap-1"
            title="Move canvas right"
          >
            <span className="text-[10px] font-semibold text-gray-500 hidden md:inline">Right</span>
            <ArrowRight className="h-4 w-4" />
          </button>

          <div className="w-px h-4 bg-gray-200 mx-0.5" />

          <button
            onClick={() => {
              setPanOffset({ x: 0, y: 0 });
              setZoomLevel(100);
            }}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-gray-600 hover:text-indigo-600 flex items-center gap-1"
            title="Recenter sequence & reset zoom"
          >
            <Crosshair className="h-3.5 w-3.5" />
            <span className="text-[10px] font-semibold text-gray-500 hidden sm:inline">Center</span>
          </button>

          <button
            onClick={handleFitToScreen}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-gray-600 hover:text-indigo-600 flex items-center gap-1"
            title="Fit sequence to screen"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            <span className="text-[10px] font-semibold text-gray-500 hidden sm:inline">Fit</span>
          </button>

          <div className="w-px h-4 bg-gray-200 mx-0.5" />

          <button
            onClick={() => setZoomLevel((z) => Math.max(z - 10, 20))}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <button
            onClick={() => setZoomLevel((z) => Math.min(z + 10, 200))}
            className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <span className="px-2 text-xs font-semibold text-gray-700 min-w-[38px] text-center">
            {zoomLevel}%
          </span>
        </div>

        {/* Main Flowchart Tree Canvas Area (Pannable & Clamped) */}
        <div
          ref={canvasViewportRef}
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          onMouseLeave={handleCanvasMouseUp}
          onWheel={handleCanvasWheel}
          className={`flex-1 h-full min-h-0 overflow-hidden flex flex-col items-center pt-24 pb-48 px-10 relative select-none ${
            isPanning ? 'cursor-grabbing' : 'cursor-grab'
          }`}
        >
          <div
            ref={sequenceTreeRef}
            className="flex flex-col items-center transition-transform origin-top will-change-transform shrink-0 w-auto"
            style={{
              transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel / 100})`,
              transitionDuration: isPanning ? '0ms' : '150ms',
            }}
          >
            {/* SEQUENCE START Pill (media_1790088201124.png) */}
            <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs font-bold tracking-wider text-slate-500 shadow-2xs mb-0">
              <Navigation className="w-3.5 h-3.5 text-slate-400 rotate-45" />
              <span>SEQUENCE START</span>
            </div>

            {tree.length === 0 && (
              <div className="mt-10 flex flex-col items-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white/80 px-10 py-8 text-center shadow-2xs">
                <p className="text-sm font-semibold text-slate-700">Your sequence is empty</p>
                <p className="text-xs text-slate-400">Add a step to start building the campaign flow.</p>
                <button
                  type="button"
                  onClick={() => {
                    setPaletteTarget({ type: 'linear', stepId: 'start' });
                    setPaletteOpen(true);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
                >
                  <Plus className="h-3.5 w-3.5" /> Add first step
                </button>
              </div>
            )}

            {/* Root vertical trunk lines and recursive nodes */}
            {tree.map((rootStep, index) => (
              <div key={rootStep.id} className="flex flex-col items-center shrink-0 w-auto">
                {renderVerticalConnector({
                  type: 'linear',
                  stepId: index > 0 ? tree[index - 1].id : 'start',
                })}
                {renderCard(rootStep)}
                {rootStep.branches && renderBranches(rootStep)}
                {!rootStep.branches && rootStep.endsHere && (
                  <div className="flex flex-col items-center mt-1">
                    <div className="w-[2px] h-3 bg-slate-300" />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPaletteTarget({ type: 'linear', stepId: rootStep.id });
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
                        setPaletteTarget({ type: 'linear', stepId: rootStep.id });
                        setPaletteOpen(true);
                      }}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 mt-2.5"
                    >
                      + Add a step
                    </button>
                  </div>
                )}
                {!rootStep.branches && !rootStep.endsHere && index === tree.length - 1 && (
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
                          setPaletteTarget({ type: 'linear', stepId: rootStep.id });
                          setPaletteOpen(true);
                        }}
                        className="w-7 h-7 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white flex items-center justify-center shadow-xs transition-colors"
                        title="Add a step"
                      >
                        <Plus className="w-4 h-4 stroke-[2.5]" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* RIGHT FIXED PANEL: Fixed width sidebar matching media_1790104824235.png & media_1790104866987.png */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-96 max-w-[90vw] shrink-0 h-full max-h-full bg-white border-l border-gray-200 shadow-2xs z-20 flex flex-col overflow-hidden"
      >
        {selectedStep ? (
          <>
            {/* Drawer Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
                  {React.createElement(getNodeVisuals(selectedStep.type).icon, { className: 'w-5 h-5' })}
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 text-sm">{selectedStep.title}</h3>
                  <span className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold">
                    {selectedStep.type === 'has_data_in_column' ? 'Contact field condition' : 'Outreach sequence'}
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
          <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-5 text-left">
            {/* Timing Stepper */}
            <div>
              <label className="block text-xs font-bold text-gray-900 mb-1">Wait before this step</label>
              <div className="flex items-center gap-2 mt-1.5">
                <div className="flex items-center border border-gray-200 rounded-xl bg-white shadow-2xs overflow-hidden">
                  <button
                    onClick={() =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          delay_hours: Math.max(0, stepDelayHours(selectedStep) - 24),
                        })
                      )
                    }
                    className="px-3 py-1.5 text-gray-500 hover:bg-gray-100 text-sm font-bold"
                  >
                    –
                  </button>
                  <span className="px-4 py-1.5 text-xs font-bold text-gray-900 w-12 text-center">
                    {stepDelayHours(selectedStep) / 24}
                  </span>
                  <button
                    onClick={() =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          delay_hours: Math.min(8760, stepDelayHours(selectedStep) + 24),
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
                <input
                  ref={voiceFileInputRef}
                  type="file"
                  accept="audio/*,.mp3,.wav,.m4a,.webm"
                  onChange={handleUploadVoiceFile}
                  className="hidden"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, voice_mode: 'script' },
                        })
                      )
                    }
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors ${
                      (selectedStep.config?.voice_mode || 'script') === 'script'
                        ? 'bg-indigo-50 text-indigo-800 border border-indigo-200'
                        : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Voice script
                  </button>
                  {isRecordingVoice ? (
                    <button
                      type="button"
                      onClick={handleStopRecordingVoice}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-1.5 shadow-2xs"
                    >
                      <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                      Stop recording ({recordingSeconds}s)
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStartRecordingVoice}
                      className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-rose-50 border border-gray-200 hover:border-rose-200 text-gray-700 hover:text-rose-700 flex items-center gap-1 transition-colors"
                    >
                      <Mic className="w-3.5 h-3.5 text-rose-500" />
                      Record audio
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => voiceFileInputRef.current?.click()}
                    className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-indigo-50 border border-gray-200 hover:border-indigo-200 text-gray-700 hover:text-indigo-700 transition-colors"
                  >
                    Upload MP3
                  </button>
                </div>

                {/* Audio Player Preview when recorded or uploaded */}
                {selectedStep.config?.recorded_audio_data_url && (
                  <div className="p-3 rounded-xl bg-rose-50/60 border border-rose-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-rose-900 truncate">
                        {selectedStep.config.recorded_audio_name || 'Attached Voice Recording'}
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: {
                                ...selectedStep.config,
                                voice_mode: 'script',
                                recorded_audio_data_url: undefined,
                                recorded_audio_name: undefined,
                              },
                            })
                          )
                        }
                        className="text-[10px] font-semibold text-rose-600 hover:underline"
                      >
                        Remove audio
                      </button>
                    </div>
                    <audio
                      controls
                      src={selectedStep.config.recorded_audio_data_url}
                      className="w-full h-8"
                    />
                  </div>
                )}

                {/* Cloned Voice Profile Selector */}
                {voicesList.length > 0 && (
                  <div>
                    <label className="block text-xs font-bold text-gray-900 mb-1">
                      AI Voice Profile
                    </label>
                    <select
                      value={selectedStep.config?.voice_id || ''}
                      onChange={(e) =>
                        setTree((prev) =>
                          updateNode(prev, selectedStep.id, {
                            config: { ...selectedStep.config, voice_id: e.target.value || undefined },
                          })
                        )
                      }
                      className="w-full rounded-xl border border-gray-200 px-3 py-2 text-xs bg-white text-gray-800 focus:border-indigo-600"
                    >
                      <option value="">Use sender&apos;s assigned voice profile</option>
                      {voicesList.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name} ({v.status || 'ready'})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <p className="text-xs text-gray-600">
                  Record directly, upload an MP3/WAV, or write a personalized voice script for your cloned voice profile. Live voice delivery uses the prepared and approved audio artifact.
                </p>

                <div>
                  {renderEditorToolbar()}
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
                          isActionRequired: e.target.value.trim().length === 0 && !selectedStep.config?.recorded_audio_data_url,
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
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Fallback text (if voice note cannot be delivered)
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
                    placeholder="Optional text fallback when voice note is unavailable."
                    className="w-full rounded-xl border border-gray-200 p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
                {renderConditionRuleSelector()}
              </div>
            )}

            {/* INMAIL CONFIGURATION */}
            {selectedStep.type === 'inmail' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-bold text-gray-900">InMail Subject Line</label>
                    <span className="text-[10px] font-semibold text-indigo-600">Supports Variables</span>
                  </div>
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
                    placeholder="e.g. Quick question for {{first_name}} at {{company_name}}"
                    className="w-full rounded-xl border border-gray-200 px-3 py-2 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  />
                  <div className="flex flex-wrap items-center gap-1 mt-1.5">
                    {[
                      { label: '+ First Name', token: '{{first_name}}' },
                      { label: '+ Company', token: '{{company_name}}' },
                      { label: '+ Job Title', token: '{{job_title}}' },
                      { label: '+ University', token: '{{university_name}}' },
                      { label: '+ Profile Type', token: '{{profile_type}}' },
                    ].map((chip) => (
                      <button
                        key={chip.token}
                        type="button"
                        onClick={() => {
                          const currSubj = selectedStep.config?.subject || '';
                          const nextSubj = currSubj ? `${currSubj} ${chip.token}` : chip.token;
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, subject: nextSubj },
                            })
                          );
                        }}
                        className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 cursor-pointer"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  {renderEditorToolbar()}
                  <div className="flex items-center justify-between text-xs font-bold text-gray-900 mb-1">
                    <span>Message</span>
                    <span className="text-[11px] font-normal text-gray-400">
                      {(selectedStep.config?.body ?? selectedStep.config?.message ?? '').length}/1900
                    </span>
                  </div>
                  <textarea
                    rows={5}
                    maxLength={1900}
                    value={selectedStep.config?.body ?? selectedStep.config?.message ?? ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, body: e.target.value, message: e.target.value },
                          isActionRequired: e.target.value.trim().length === 0,
                          subtitle: e.target.value.trim().length > 0 ? 'InMail copy ready' : 'Action required',
                        })
                      )
                    }
                    placeholder="Write your InMail copy here..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                </div>

                <div className="p-3 rounded-xl bg-amber-50/50 border border-amber-200/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-gray-900">
                      Alternative Message (If variable is missing)
                    </label>
                    <span className="text-[10px] font-semibold text-amber-800 bg-amber-100/80 px-2 py-0.5 rounded-full">
                      Guaranteed delivery
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Sent automatically if an optional profile variable (e.g. Top Skill, Company Followed, University) is missing on the lead&apos;s LinkedIn profile. Uses only mandatory LinkedIn fields:
                  </p>
                  <div className="flex flex-wrap items-center gap-1">
                    {GUARANTEED_LINKEDIN_VARIABLE_CHIPS.map((chip) => (
                      <button
                        key={chip.token}
                        type="button"
                        onClick={() => {
                          const currAlt = selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? '';
                          const nextAlt = currAlt ? `${currAlt} ${chip.token}` : chip.token;
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, alternative_message: nextAlt, fallback: nextAlt },
                            })
                          );
                        }}
                        className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-white text-amber-900 border border-amber-300 hover:bg-amber-100 cursor-pointer"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    rows={2}
                    value={selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: {
                            ...selectedStep.config,
                            alternative_message: e.target.value,
                            fallback: e.target.value,
                          },
                        })
                      )
                    }
                    placeholder="Hi {{first_name}}, wanted to connect with fellow professionals in {{location}}..."
                    className="w-full rounded-xl border border-amber-200 bg-white p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>
                {renderConditionRuleSelector()}
              </div>
            )}

            {/* REPLY TO COMMENT CONFIGURATION */}
            {selectedStep.type === 'reply_to_comment' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  {renderEditorToolbar()}
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
                {renderConditionRuleSelector()}
              </div>
            )}

            {/* SEND MESSAGE CONFIGURATION */}
            {selectedStep.type === 'send_message' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-gray-900">A/B Message Variants (up to 3)</label>
                    <div className="flex items-center gap-1">
                      {['A', 'B', 'C'].map((vid) => {
                        const variants = Array.isArray(selectedStep.config?.variants) ? selectedStep.config.variants : [];
                        const exists = vid === 'A' || variants.some((v) => v.id === vid);
                        return (
                          <button
                            key={vid}
                            type="button"
                            onClick={() => {
                              if (!exists) {
                                const baseBody = selectedStep.config?.body || 'Hi {{first_name}}, wanted to follow up on my previous note!';
                                const nextVariants = variants.length
                                  ? [...variants, { id: vid, body: baseBody }]
                                  : [{ id: 'A', body: baseBody }, { id: vid, body: baseBody }];
                                setTree((prev) =>
                                  updateNode(prev, selectedStep.id, {
                                    config: { ...selectedStep.config, variants: nextVariants },
                                  })
                                );
                              }
                              setActiveVariantTab(vid);
                            }}
                            className={`px-2 py-0.5 text-[11px] font-bold rounded-lg border transition-colors ${
                              activeVariantTab === vid
                                ? 'bg-indigo-600 text-white border-indigo-600'
                                : exists
                                ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                                : 'bg-gray-50 text-gray-400 border-gray-200 hover:text-gray-700'
                            }`}
                          >
                            {exists ? `Variant ${vid}` : `+ ${vid}`}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  {renderEditorToolbar()}
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Direct Message Copy {Array.isArray(selectedStep.config?.variants) && selectedStep.config.variants.length > 1 ? `(Variant ${activeVariantTab})` : ''}
                  </label>
                  <textarea
                    rows={4}
                    value={
                      Array.isArray(selectedStep.config?.variants) && selectedStep.config.variants.some((v) => v.id === activeVariantTab)
                        ? (selectedStep.config.variants.find((v) => v.id === activeVariantTab)?.body || '')
                        : (selectedStep.config?.body || '')
                    }
                    onChange={(e) => {
                      const val = e.target.value;
                      const variants = Array.isArray(selectedStep.config?.variants) ? selectedStep.config.variants : [];
                      const nextVariants = variants.length
                        ? variants.map((v) => (v.id === activeVariantTab ? { ...v, body: val } : v))
                        : undefined;
                      const primaryBody = activeVariantTab === 'A' ? val : (selectedStep.config?.body || val);
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: {
                            ...selectedStep.config,
                            body: primaryBody,
                            ...(nextVariants ? { variants: nextVariants } : {}),
                          },
                          isActionRequired: primaryBody.trim().length === 0,
                          subtitle: primaryBody.trim().length > 0 ? primaryBody.slice(0, 32) + '...' : 'Action required',
                        })
                      );
                    }}
                    placeholder="Hi {{first_name}}, thanks for connecting! Loved your recent thoughts on..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                  />
                </div>
                <div className="p-3 rounded-xl bg-amber-50/50 border border-amber-200/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-gray-900">
                      Alternative Message (If variable is missing)
                    </label>
                    <span className="text-[10px] font-semibold text-amber-800 bg-amber-100/80 px-2 py-0.5 rounded-full">
                      Guaranteed delivery
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    If a variable in your primary message (such as <code className="text-[10px] bg-white px-1 rounded border">{'{{top_skill}}'}</code> or <code className="text-[10px] bg-white px-1 rounded border">{'{{company_followed}}'}</code>) is missing on the lead&apos;s profile, this alternative message is sent instead using mandatory LinkedIn variables:
                  </p>
                  <div className="flex flex-wrap items-center gap-1">
                    {GUARANTEED_LINKEDIN_VARIABLE_CHIPS.map((chip) => (
                      <button
                        key={chip.token}
                        type="button"
                        onClick={() => {
                          const currAlt = selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? '';
                          const nextAlt = currAlt ? `${currAlt} ${chip.token}` : chip.token;
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, alternative_message: nextAlt, fallback: nextAlt },
                            })
                          );
                        }}
                        className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-white text-amber-900 border border-amber-300 hover:bg-amber-100 cursor-pointer"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    rows={3}
                    value={selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: {
                            ...selectedStep.config,
                            alternative_message: e.target.value,
                            fallback: e.target.value,
                          },
                        })
                      )
                    }
                    placeholder="Hi {{first_name}}, great connecting with you in {{location}}! How are things going?"
                    className="w-full rounded-xl border border-amber-200 bg-white p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>

                <div className="pt-2 border-t border-gray-100 space-y-2">
                  <label className="block text-xs font-bold text-gray-900">File Attachment (Optional)</label>
                  <input
                    type="url"
                    value={selectedStep.config?.attachment_url || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, attachment_url: e.target.value },
                        })
                      )
                    }
                    placeholder="https://... (PDF, Deck, Case Study URL)"
                    className="w-full rounded-xl border border-gray-200 px-3 py-1.5 text-xs focus:border-indigo-600"
                  />
                  <input
                    type="text"
                    value={selectedStep.config?.attachment_name || ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, attachment_name: e.target.value },
                        })
                      )
                    }
                    placeholder="Attachment filename (e.g. Unravler-Overview.pdf)"
                    className="w-full rounded-xl border border-gray-200 px-3 py-1.5 text-xs focus:border-indigo-600"
                  />
                </div>
                {renderConditionRuleSelector()}
              </div>
            )}

            {/* WITHDRAW INVITE CONFIGURATION */}
            {selectedStep.type === 'withdraw_invite' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-xs text-amber-900 leading-relaxed">
                  <strong>Withdraw Connection Request:</strong> Automatically withdraws a pending LinkedIn invitation if the prospect has not accepted yet. LinkedIn enforces a mandatory <strong>21-day (504h) cooldown</strong> before you can re-invite a prospect after withdrawing.
                </div>
              </div>
            )}

            {/* EMAIL CONFIGURATION: sending requires a connected mailbox at launch. */}
            {selectedStep.type === 'send_email' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <p className="rounded-xl border border-teal-100 bg-teal-50 p-3 text-xs text-teal-900">
                  Email is sent through the mailbox connected to this sender. A provider acceptance is not a delivery confirmation.
                </p>
                <div>
                  <label htmlFor={`email-subject-${selectedStep.id}`} className="block text-xs font-bold text-gray-900 mb-1">Email subject</label>
                  <input
                    id={`email-subject-${selectedStep.id}`}
                    type="text"
                    value={selectedStep.config?.subject || ''}
                    onChange={(event) => setTree((previous) => updateNode(previous, selectedStep.id, {
                      config: { ...selectedStep.config, subject: event.target.value },
                      isActionRequired: !event.target.value.trim() || !selectedStep.config?.body?.trim(),
                    }))}
                    placeholder="A quick note for {{first_name}}"
                    className="w-full rounded-xl border border-gray-200 px-3 py-2 text-xs focus:border-teal-600 focus:ring-1 focus:ring-teal-600"
                  />
                </div>
                <div>
                  {renderEditorToolbar()}
                  <label htmlFor={`email-body-${selectedStep.id}`} className="block text-xs font-bold text-gray-900 mb-1">Email body</label>
                  <textarea
                    id={`email-body-${selectedStep.id}`}
                    rows={6}
                    value={selectedStep.config?.body || ''}
                    onChange={(event) => setTree((previous) => updateNode(previous, selectedStep.id, {
                      config: { ...selectedStep.config, body: event.target.value },
                      isActionRequired: !event.target.value.trim() || !selectedStep.config?.subject?.trim(),
                    }))}
                    placeholder="Hi {{first_name}}, ..."
                    className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-teal-600 focus:ring-1 focus:ring-teal-600 resize-none"
                  />
                </div>
              </div>
            )}

            {selectedStep.type === 'find_email' && (
              <div className="rounded-xl border border-teal-100 bg-teal-50 p-3 text-xs text-teal-900">
                Uses the workspace Hunter key to look up a prospect email. No address found does not authorize sending; provider errors pause the lead for review.
              </div>
            )}

            {selectedStep.type === 'if_email_available' && (
              <div className="rounded-xl border border-teal-100 bg-teal-50 p-3 text-xs text-teal-900">
                Yes requires a correctly formatted address allowed by the current stored email policy and suppression checks. Missing verification follows the provided-address policy; this does not confirm delivery. Malformed policy data pauses for review.
              </div>
            )}

            {/* CONNECTION REQUEST CONFIGURATION */}
            {selectedStep.type === 'connection_request' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-amber-50/60 border border-amber-200 rounded-xl text-xs text-amber-800 leading-relaxed">
                  <strong>Unravler Tip:</strong> Connection invites without notes often get 15-20% higher acceptance rates.
                </div>
                <div>
                  {renderEditorToolbar()}
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

                <div className="p-3 rounded-xl bg-amber-50/50 border border-amber-200/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-gray-900">
                      Alternative Note (If variable is missing)
                    </label>
                    <span className="text-[10px] font-semibold text-amber-800 bg-amber-100/80 px-2 py-0.5 rounded-full">
                      {(selectedStep.config?.alternative_message || selectedStep.config?.fallback || '').length}/300
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Backup invite note sent if a variable in your primary note is missing on the lead&apos;s LinkedIn profile:
                  </p>
                  <div className="flex flex-wrap items-center gap-1">
                    {GUARANTEED_LINKEDIN_VARIABLE_CHIPS.map((chip) => (
                      <button
                        key={chip.token}
                        type="button"
                        onClick={() => {
                          const currAlt = selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? '';
                          const nextAlt = (currAlt ? `${currAlt} ${chip.token}` : chip.token).slice(0, 300);
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, alternative_message: nextAlt, fallback: nextAlt },
                            })
                          );
                        }}
                        className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-white text-amber-900 border border-amber-300 hover:bg-amber-100 cursor-pointer"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    rows={2}
                    maxLength={300}
                    value={selectedStep.config?.alternative_message ?? selectedStep.config?.fallback ?? ''}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: {
                            ...selectedStep.config,
                            alternative_message: e.target.value,
                            fallback: e.target.value,
                          },
                        })
                      )
                    }
                    placeholder="Hi {{first_name}}, would love to connect with fellow leaders in {{location}}!"
                    className="w-full rounded-xl border border-amber-200 bg-white p-2.5 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none"
                  />
                </div>

                {/* Unaccepted Invite Warmup Path Helper (Dripify Sequence Parity) */}
                {selectedStep.branches?.left && (
                  <div className="p-3 bg-indigo-50/60 border border-indigo-100 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-indigo-950">If Not Accepted Warmup Path</span>
                      <span className="text-[10px] font-semibold text-indigo-700 bg-white px-2 py-0.5 rounded-full border border-indigo-200">
                        {(selectedStep.branches.left.steps || []).length} steps
                      </span>
                    </div>
                    <p className="text-[11px] text-indigo-900/80 leading-relaxed">
                      Automatically warm up prospects who haven&apos;t accepted yet (Wait 1d → View Profile → Wait 3d → Like Post → Wait 5d → Withdraw Invite).
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        const warmupSteps = [
                          {
                            id: makeStepId(),
                            type: 'visit_profile',
                            title: 'Visit profile',
                            subtitle: 'Visit lead profile on LinkedIn',
                            delay_hours: 24,
                            config: {},
                          },
                          {
                            id: makeStepId(),
                            type: 'like_last_post',
                            title: 'Like a post',
                            subtitle: 'Like most recent post',
                            delay_hours: 72,
                            config: { post_index: 0 },
                          },
                          {
                            id: makeStepId(),
                            type: 'withdraw_invite',
                            title: 'Withdraw invite',
                            subtitle: 'Withdraw unaccepted invite',
                            delay_hours: 120,
                            config: {},
                          },
                        ];
                        setTree((prev) =>
                          updateNode(prev, selectedStep.id, {
                            branches: {
                              ...selectedStep.branches,
                              left: {
                                ...selectedStep.branches.left,
                                steps: warmupSteps,
                              },
                            },
                          })
                        );
                        setToastMessage('Added non-accepted warmup path (Visit → Like → Withdraw).');
                      }}
                      className="w-full py-1.5 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                    >
                      + Auto-Fill Unaccepted Warmup (Visit → Like → Withdraw)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const acceptedSteps = [
                          {
                            id: makeStepId(),
                            type: 'endorse_skill',
                            title: 'Endorse skill',
                            subtitle: 'Endorse top skill',
                            delay_days: 0,
                            delay_hours: 3,
                            config: { endorsement_mode: 'any_skill', max_skills: 1 },
                          },
                          {
                            id: makeStepId(),
                            type: 'like_last_post',
                            title: 'Like a post',
                            subtitle: 'Like recent post',
                            delay_days: 1,
                            config: { count: 1 },
                          },
                          {
                            id: makeStepId(),
                            type: 'send_message',
                            title: 'Send message',
                            subtitle: 'Welcome message ready',
                            delay_days: 0,
                            delay_hours: 6,
                            config: {
                              body: 'Thanks for connecting, {{first_name}}! Noticed your work as {{job_title}} at {{company_name}} — how is your team approaching outbound growth this quarter?',
                            },
                          },
                          {
                            id: makeStepId(),
                            type: 'send_message',
                            title: 'Send message',
                            subtitle: 'Follow-up message ready',
                            delay_days: 4,
                            config: {
                              body: 'Hi {{first_name}}, wanted to quickly bump this in case it got buried. Open to a brief chat next week?',
                            },
                          },
                        ];
                        setTree((prev) =>
                          updateNode(prev, selectedStep.id, {
                            branches: {
                              ...selectedStep.branches,
                              right: {
                                ...selectedStep.branches.right,
                                steps: acceptedSteps,
                              },
                            },
                          })
                        );
                        setToastMessage('Added accepted post-connect nurture path (Endorse → Like → Welcome Msg → Follow-Up).');
                      }}
                      className="w-full py-1.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                    >
                      + Auto-Fill Accepted Post-Connect Nurture (Endorse → Like → Msg)
                    </button>
                  </div>
                )}

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* VISIT PROFILE CONFIGURATION */}
            {selectedStep.type === 'visit_profile' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-indigo-50/70 border border-indigo-100 rounded-xl text-xs text-indigo-900 leading-relaxed">
                  <strong>Profile visit:</strong> Requests the lead&apos;s profile when this step runs. Browsing duration and repeat-visit skipping are unavailable; saved values below are not applied.
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Dwell Time & Browsing Depth
                  </label>
                  <select
                    disabled
                    value={selectedStep.config?.dwell_mode || 'realistic'}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, dwell_mode: e.target.value },
                        })
                      )
                    }
                    className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 bg-white text-gray-800 font-medium focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  >
                    <option value="realistic">Realistic — unavailable</option>
                    <option value="quick">Quick glance — unavailable</option>
                    <option value="deep">Deep engagement — unavailable</option>
                  </select>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/60">
                  <div>
                    <p className="text-xs font-semibold text-gray-900">Skip if already visited</p>
                    <p className="text-[11px] text-gray-500">Unavailable: the runner does not skip visits based on past activity.</p>
                  </div>
                  <input
                    disabled
                    type="checkbox"
                    checked={selectedStep.config?.skip_if_visited ?? true}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, skip_if_visited: e.target.checked },
                        })
                      )
                    }
                    className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-gray-300"
                  />
                </div>

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* LIKE LAST POST CONFIGURATION */}
            {selectedStep.type === 'like_last_post' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-sky-50/70 border border-sky-100 rounded-xl text-xs text-sky-900 leading-relaxed">
                  <strong>Post Like:</strong> Likes the lead's most recent post or share on LinkedIn. This puts your profile directly into their activity notifications and dramatically boosts invite acceptance.
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Maximum Post Age
                  </label>
                  <select
                    value={selectedStep.config?.max_post_age_days || 30}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, max_post_age_days: Number(e.target.value) },
                        })
                      )
                    }
                    className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 bg-white text-gray-800 font-medium focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  >
                    <option value={7}>Within last 7 days</option>
                    <option value={14}>Within last 14 days</option>
                    <option value={30}>Within last 30 days (recommended)</option>
                    <option value={90}>Within last 90 days</option>
                  </select>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/60">
                  <div>
                    <p className="text-xs font-semibold text-gray-900">Skip if no posts found</p>
                    <p className="text-[11px] text-gray-500">Advance without failing if lead hasn't posted</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={selectedStep.config?.skip_if_no_posts ?? true}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, skip_if_no_posts: e.target.checked },
                        })
                      )
                    }
                    className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-gray-300"
                  />
                </div>

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* COMMENT LAST POST CONFIGURATION */}
            {selectedStep.type === 'comment_last_post' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-purple-50/70 border border-purple-100 rounded-xl text-xs text-purple-900 leading-relaxed">
                  <strong>Post Comment:</strong> Leaves an insightful comment on the lead's latest post.
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-bold text-gray-900">Comment Mode</label>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, mode: 'ai' },
                            })
                          )
                        }
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-colors ${
                          (selectedStep.config?.mode || 'custom') === 'ai'
                            ? 'bg-purple-600 text-white shadow-2xs'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        AI Generated
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: { ...selectedStep.config, mode: 'custom' },
                            })
                          )
                        }
                        className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-colors ${
                          (selectedStep.config?.mode || 'custom') === 'custom'
                            ? 'bg-purple-600 text-white shadow-2xs'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        Custom Template
                      </button>
                    </div>
                  </div>

                  {renderEditorToolbar()}

                  {(selectedStep.config?.mode || 'custom') === 'ai' ? (
                    <div>
                      <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                        AI Prompt Instructions for Comment
                      </label>
                      <textarea
                        rows={3}
                        value={selectedStep.config?.ai_prompt || ''}
                        onChange={(e) =>
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: {
                                ...selectedStep.config,
                                ai_prompt: e.target.value,
                                comment: selectedStep.config?.comment || 'Great insights on this, {{first_name}}!',
                                comment_template: selectedStep.config?.comment_template || 'Great insights on this, {{first_name}}!',
                              },
                              subtitle: e.target.value.trim().length > 0 ? 'AI comment ready' : 'Action required',
                            })
                          )
                        }
                        placeholder="Write a warm, 1-2 sentence thoughtful observation about their post topic. Never sell or pitch."
                        className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                        Comment Template
                      </label>
                      <textarea
                        rows={3}
                        value={selectedStep.config?.comment ?? selectedStep.config?.comment_template ?? ''}
                        onChange={(e) =>
                          setTree((prev) =>
                            updateNode(prev, selectedStep.id, {
                              config: {
                                ...selectedStep.config,
                                comment: e.target.value,
                                comment_template: e.target.value,
                              },
                              subtitle: e.target.value.trim().length > 0 ? 'Comment template set' : 'Action required',
                            })
                          )
                        }
                        placeholder="Great point {{first_name}}! Completely agree with your perspective here."
                        className="w-full rounded-xl border border-gray-200 p-3 text-xs focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 resize-none font-sans"
                      />
                    </div>
                  )}
                </div>

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* FOLLOW PROFILE CONFIGURATION */}
            {selectedStep.type === 'follow' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-indigo-50/70 border border-indigo-100 rounded-xl text-xs text-indigo-900 leading-relaxed">
                  <strong>Follow Profile:</strong> Follows the prospect on LinkedIn so you see their content updates and appear in their followers list.
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/60">
                  <div>
                    <p className="text-xs font-semibold text-gray-900">Skip if already following</p>
                    <p className="text-[11px] text-gray-500">Avoid duplicate follow actions if already followed</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={selectedStep.config?.skip_if_following ?? true}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, skip_if_following: e.target.checked },
                        })
                      )
                    }
                    className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-gray-300"
                  />
                </div>

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* ENDORSE SKILLS CONFIGURATION */}
            {selectedStep.type === 'endorse_skills' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-indigo-50/70 border border-indigo-100 rounded-xl text-xs text-indigo-900 leading-relaxed">
                  <strong>Endorse Skills:</strong> Endorses top skills on the prospect's profile to generate a high-trust notification.
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Skills to Endorse
                  </label>
                  <select
                    value={selectedStep.config?.endorse_count || 3}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, endorse_count: Number(e.target.value) },
                        })
                      )
                    }
                    className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 bg-white text-gray-800 font-medium focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  >
                    <option value={1}>Top 1 skill</option>
                    <option value={3}>Top 3 skills (recommended)</option>
                    <option value={5}>Top 5 skills</option>
                  </select>
                </div>

                {renderConditionRuleSelector()}
              </div>
            )}

            {/* CONDITIONS CONFIGURATION */}
            {selectedStep.type === 'has_data_in_column' && <FieldConditionEditor key={`${campaignId}:${selectedStep.id}`} config={selectedStep.config} onChange={(config) => setTree((prev) => updateNode(prev, selectedStep.id, { config, branches: Object.fromEntries(Object.entries(selectedStep.branches || {}).map(([side, branch]) => [side, { ...branch, condition: conditionBranchLabel(branch.condition) }])) }))} />}
            {selectedStep.type !== 'has_data_in_column' && CONDITION_DEFINITIONS.some((c) => c.type === selectedStep.type) && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-amber-50/70 border border-amber-200/70 rounded-xl text-xs text-amber-900 leading-relaxed">
                  <strong>{selectedStep.title} Check:</strong> Sequences split dynamically based on lead response. Green branch runs if the condition is met, red branch runs if not.
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Timeout / Waiting Duration
                  </label>
                  <select
                    value={selectedStep.config?.timeout_days || 3}
                    onChange={(e) =>
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, timeout_days: Number(e.target.value) },
                        })
                      )
                    }
                    className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 bg-white text-gray-800 font-medium focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                  >
                    <option value={1}>Wait 1 day before evaluating</option>
                    <option value={3}>Wait 3 days before evaluating (recommended)</option>
                    <option value={5}>Wait 5 days before evaluating</option>
                    <option value={7}>Wait 7 days before evaluating</option>
                  </select>
                </div>
              </div>
            )}

            {/* ADD TAG CONFIGURATION */}
            {selectedStep.type === 'add_tag' && (
              <div className="space-y-4 pt-2 border-t border-gray-100">
                <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-xl text-xs text-emerald-900 leading-relaxed">
                  <strong>CRM Tag Action:</strong> Applies a custom or preset tag to the lead in your Unravler CRM &amp; Inbox as soon as they reach this step in the sequence.
                </div>

                <div>
                  <label className="block text-xs font-bold text-gray-900 mb-1">
                    Tag Name to Apply
                  </label>
                  <input
                    type="text"
                    value={selectedStep.config?.tag_name ?? selectedStep.config?.auto_tag ?? ''}
                    onChange={(e) => {
                      const val = e.target.value;
                      setTree((prev) =>
                        updateNode(prev, selectedStep.id, {
                          config: { ...selectedStep.config, tag_name: val, auto_tag: val },
                          isActionRequired: val.trim().length === 0,
                          subtitle: val.trim().length > 0 ? `Tag: ${val.trim()}` : 'Action required',
                        })
                      );
                    }}
                    placeholder="e.g. Hot lead, Engaged, AppSumo, ClientAmp..."
                    className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs text-gray-800 focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
                  />
                  <div className="flex flex-wrap gap-1.5 pt-2">
                    {['Hot lead', 'Interested', 'Wants to speak later', 'Follow up', 'High Priority'].map((presetTag) => {
                      const currentTag = selectedStep.config?.tag_name ?? selectedStep.config?.auto_tag ?? '';
                      return (
                        <button
                          key={presetTag}
                          type="button"
                          onClick={() =>
                            setTree((prev) =>
                              updateNode(prev, selectedStep.id, {
                                config: {
                                  ...selectedStep.config,
                                  tag_name: presetTag,
                                  auto_tag: presetTag,
                                },
                                isActionRequired: false,
                                subtitle: `Tag: ${presetTag}`,
                              })
                            )
                          }
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold border transition-colors ${
                            currentTag === presetTag
                              ? 'bg-emerald-600 text-white border-emerald-600'
                              : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                          }`}
                        >
                          + {presetTag}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Sequence Auto-Tagging (Prosp Parity: Tag leads from specific sequences automatically) */}
            {!['END', 'IF_CONNECTED', 'IF_OPENED_MESSAGE', 'add_tag'].includes(selectedStep.type) && (
              <div className="space-y-2 pt-2 border-t border-gray-100">
                <label className="block text-xs font-bold text-gray-800">
                  Auto-Tag Lead on Step Completion <span className="text-gray-400 font-normal">(Optional)</span>
                </label>
                <p className="text-[11px] text-gray-500">
                  Automatically apply a CRM &amp; Inbox tag to the prospect when this sequence step executes.
                </p>
                <input
                  type="text"
                  value={selectedStep.config?.auto_tag || ''}
                  onChange={(e) =>
                    setTree((prev) =>
                      updateNode(prev, selectedStep.id, {
                        config: { ...selectedStep.config, auto_tag: e.target.value },
                      })
                    )
                  }
                  placeholder="e.g. Hot lead, Sequence A, Follow up..."
                  className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs text-gray-800 focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600"
                />
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {['Hot lead', 'Interested', 'Wants to speak later', 'Follow up'].map((presetTag) => (
                    <button
                      key={presetTag}
                      type="button"
                      onClick={() =>
                        setTree((prev) =>
                          updateNode(prev, selectedStep.id, {
                            config: {
                              ...selectedStep.config,
                              auto_tag: selectedStep.config?.auto_tag === presetTag ? '' : presetTag,
                            },
                          })
                        )
                      }
                      className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold border transition-colors ${
                        selectedStep.config?.auto_tag === presetTag
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
                      }`}
                    >
                      + {presetTag}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer Actions */}
          <div className="p-4 border-t border-gray-100 bg-gray-50/40 flex items-center justify-between shrink-0">
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
        </>
      ) : (
        /* Empty State matching media_1790104824235.png & media_1790104866987.png */
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center select-none">
          <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center text-gray-400 mb-4 shadow-2xs">
            <Edit3 className="w-6 h-6 stroke-[1.5]" />
          </div>
          <h3 className="text-base font-bold text-gray-900 mb-1.5">Select a step to edit it</h3>
          <p className="text-xs text-gray-500 leading-relaxed max-w-[240px]">
            Click any card to change its message, timing, or how it branches.
          </p>
        </div>
      )}
    </div>

      {/* STEP PALETTE DRAWER (When clicking any + in the tree) */}
      {paletteOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-96 max-w-[90vw] h-full max-h-full bg-white border-l border-gray-200 shadow-2xl z-40 flex flex-col overflow-hidden animate-slide-left"
        >
          <div className="flex items-center justify-between p-4 border-b border-gray-100 shrink-0">
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

          <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-6 text-left">
            {capabilityError && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <p>{capabilityError}</p>
                <button type="button" onClick={() => setCapabilityRetryKey((value) => value + 1)} className="mt-2 font-semibold underline">
                  Retry availability
                </button>
              </div>
            )}
            {/* LinkedIn Actions */}
            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 block mb-2">
                LinkedIn Actions ({ACTION_DEFINITIONS.length})
              </span>
              <div className="grid grid-cols-2 gap-2">
                {ACTION_DEFINITIONS.map((action) => {
                  const Icon = action.icon;
                  const capability = stepCapability(action.type);
                  const available = Boolean(capability?.builder_available);
                  const reason = stepReason(action.type);
                  return (
                    <button
                      key={action.type}
                      type="button"
                      onClick={() => handleAddStepFromPalette(action.type)}
                      disabled={!available}
                      title={reason || action.desc}
                      className={`flex flex-col items-start p-2.5 rounded-xl border border-gray-200 text-left transition-all group ${available ? 'hover:border-indigo-500 hover:bg-indigo-50/20' : 'opacity-60 cursor-not-allowed'}`}
                    >
                      <div className={`p-2 rounded-lg ${action.color} group-hover:scale-105 transition-transform`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-gray-900 text-xs mt-2 group-hover:text-indigo-600">
                        {action.label}
                      </span>
                      {reason && <span className="text-[10px] text-gray-500 mt-1 leading-tight">{reason}</span>}
                      {available && !capability.live_enabled && <span className="text-[10px] font-semibold text-amber-700 mt-1">Draft only · live execution off</span>}
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
                  const capability = stepCapability(cond.type);
                  const available = Boolean(capability?.builder_available);
                  const reason = stepReason(cond.type);
                  return (
                    <button
                      key={cond.type}
                      type="button"
                      onClick={() => handleAddStepFromPalette(cond.type)}
                      disabled={!available}
                      title={reason || cond.desc}
                      className={`flex flex-col items-start p-2.5 rounded-xl border border-gray-200 text-left transition-all group ${available ? 'hover:border-amber-500 hover:bg-amber-50/20' : 'opacity-60 cursor-not-allowed'}`}
                    >
                      <div className={`p-2 rounded-lg ${cond.color} group-hover:scale-105 transition-transform`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-gray-900 text-xs mt-2 group-hover:text-amber-700">
                        {cond.label}
                      </span>
                      {reason && <span className="text-[10px] text-gray-500 mt-1 leading-tight">{reason}</span>}
                      {available && !capability.live_enabled && <span className="text-[10px] font-semibold text-amber-700 mt-1">Draft only · live execution off</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 block mb-2">Email Actions ({EMAIL_ACTION_DEFINITIONS.length})</span>
              <div className="grid grid-cols-2 gap-2">
                {EMAIL_ACTION_DEFINITIONS.map((action) => {
                  const Icon = action.icon;
                  const capability = stepCapability(action.type);
                  const available = Boolean(capability?.builder_available);
                  const reason = stepReason(action.type);
                  return (
                    <button key={action.type} type="button" onClick={() => handleAddStepFromPalette(action.type)} disabled={!available}
                      title={reason || action.desc}
                      className={`flex flex-col items-start p-2.5 rounded-xl border border-gray-200 text-left transition-all ${available ? 'hover:border-teal-500 hover:bg-teal-50' : 'opacity-60 cursor-not-allowed'}`}>
                      <div className={`p-2 rounded-lg ${action.color}`}><Icon className="h-4 w-4" /></div>
                      <span className="font-semibold text-gray-900 text-xs mt-2">{action.label}</span>
                      {reason && <span className="text-[10px] text-gray-500 mt-1 leading-tight">{reason}</span>}
                      {available && !capability.live_enabled && <span className="text-[10px] font-semibold text-amber-700 mt-1">Draft only · live execution off</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 block mb-2">Email Conditions ({EMAIL_CONDITION_DEFINITIONS.length})</span>
              <div className="grid grid-cols-2 gap-2">
                {EMAIL_CONDITION_DEFINITIONS.map((cond) => {
                  const Icon = cond.icon;
                  const capability = stepCapability(cond.type);
                  const available = Boolean(capability?.builder_available);
                  const reason = stepReason(cond.type);
                  return (
                    <button key={cond.type} type="button" onClick={() => handleAddStepFromPalette(cond.type)} disabled={!available}
                      title={reason || cond.desc}
                      className={`flex flex-col items-start p-2.5 rounded-xl border border-gray-200 text-left transition-all ${available ? 'hover:border-teal-500 hover:bg-teal-50' : 'opacity-60 cursor-not-allowed'}`}>
                      <div className={`p-2 rounded-lg ${cond.color}`}><Icon className="h-4 w-4" /></div>
                      <span className="font-semibold text-gray-900 text-xs mt-2">{cond.label}</span>
                      {reason && <span className="text-[10px] text-gray-500 mt-1 leading-tight">{reason}</span>}
                      {available && !capability.live_enabled && <span className="text-[10px] font-semibold text-amber-700 mt-1">Draft only · live execution off</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* AI PROMPT LIBRARY DRAWER (Matching seq_180s.jpg, seq_200s.jpg) */}
      {promptDrawerOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-[420px] max-w-[95vw] h-full max-h-full bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col overflow-hidden animate-slide-left"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-100 shrink-0">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-xl bg-purple-100 text-purple-700">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-gray-900 text-sm">AI Prompt Library</h3>
                <p className="text-[11px] text-gray-400">Insert hyper-personalized prompt instructions</p>
              </div>
            </div>
            <button
              onClick={() => setPromptDrawerOpen(false)}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Search & Actions */}
          <div className="p-4 border-b border-gray-100 space-y-3 shrink-0 bg-gray-50/50">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                value={promptSearch}
                onChange={(e) => setPromptSearch(e.target.value)}
                placeholder="Search templates or instructions..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-gray-200 focus:border-purple-600 focus:ring-1 focus:ring-purple-600 bg-white"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                {promptsList.length} Prompts Available
              </span>
              <button
                type="button"
                onClick={() => setShowCreatePrompt(!showCreatePrompt)}
                className="text-xs font-semibold text-purple-600 hover:text-purple-700"
              >
                {showCreatePrompt ? '– Cancel' : '+ Create Custom Prompt'}
              </button>
            </div>

            {showCreatePrompt && (
              <div className="p-3 bg-white rounded-xl border border-purple-200 space-y-2.5 shadow-2xs">
                <div>
                  <label className="text-[10px] font-bold text-gray-700 block mb-0.5">Prompt Name</label>
                  <input
                    type="text"
                    value={newPromptName}
                    onChange={(e) => setNewPromptName(e.target.value)}
                    placeholder="e.g. Website designer personalised first line"
                    className="w-full text-xs rounded-lg border border-gray-200 px-2.5 py-1 focus:border-purple-600"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-gray-700 block mb-0.5">Instruction for AI</label>
                  <textarea
                    rows={2}
                    value={newPromptText}
                    onChange={(e) => setNewPromptText(e.target.value)}
                    placeholder="Describe how the LLM should analyze lead profile and what to generate..."
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 focus:border-purple-600 resize-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleCreatePrompt}
                  disabled={!newPromptName.trim() || !newPromptText.trim()}
                  className="w-full py-1.5 bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs rounded-lg shadow-2xs disabled:opacity-50"
                >
                  Save Prompt
                </button>
              </div>
            )}
          </div>

          {/* Prompts Cards */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
            {promptsLoading ? (
              <div className="flex items-center justify-center py-12 text-gray-400 text-xs">
                Loading prompt templates...
              </div>
            ) : promptsList
                .filter((p) =>
                  !promptSearch ||
                  p.name.toLowerCase().includes(promptSearch.toLowerCase()) ||
                  p.prompt_text.toLowerCase().includes(promptSearch.toLowerCase())
                )
                .map((prompt) => (
                  <div
                    key={prompt.id || prompt.name}
                    className="p-3.5 rounded-xl border border-gray-200 hover:border-purple-300 hover:bg-purple-50/20 bg-white transition-all space-y-2 text-left"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-bold text-xs text-gray-900">{prompt.name}</span>
                        {prompt.is_system && (
                          <span className="text-[9px] bg-purple-100 text-purple-700 font-bold px-1.5 py-0.2 rounded">
                            Curated
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-gray-400 font-mono shrink-0">
                        {prompt.runs_count ? `${prompt.runs_count} runs` : 'Curated'}
                      </span>
                    </div>

                    <p className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed">
                      {prompt.prompt_text}
                    </p>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[10px] text-gray-400">By {prompt.author_name || 'Unravler'}</span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => copyPromptGuidance(prompt.prompt_text)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold text-[11px] rounded-lg transition-colors"
                        >
                          <Copy className="w-3 h-3" />
                          Copy
                        </button>
                        <button
                          type="button"
                          onClick={() => insertPromptIntoStep(prompt)}
                          className="inline-flex items-center gap-1 px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs rounded-lg shadow-2xs transition-colors"
                        >
                          <Sparkles className="w-3 h-3" />
                          Insert prompt
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
          </div>
        </div>
      )}

      {/* MESSAGE PERSONALIZATION PREVIEW MODAL (Matching seq_240s.jpg) */}
      {previewModalOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4"
        >
          <div className="relative w-full max-w-xl rounded-2xl bg-white shadow-2xl border border-gray-100 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/60">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-xl bg-indigo-100 text-indigo-700">
                  <Eye className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 text-sm">Message Personalization Preview</h3>
                  <p className="text-[11px] text-gray-400">
                    {previewData?.is_illustrative_preview
                      ? 'Illustrative rendering with sample lead fields'
                      : 'Live rendering with enrolled workspace lead profile'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setPreviewModalOpen(false)}
                className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-4">
              {/* Lead Switcher & AI Evaluation Toggle */}
              {Array.isArray(previewData?.available_leads) && previewData.available_leads.length > 0 && (
                <div className="flex items-center justify-between gap-2 pb-2 border-b border-gray-100">
                  <label className="text-[11px] font-bold text-gray-600 shrink-0">Preview for lead:</label>
                  <select
                    value={previewLeadId || previewData.selected_lead_id || ''}
                    onChange={(e) => {
                      const nextId = e.target.value;
                      setPreviewLeadId(nextId);
                      handleOpenPreview(selectedStep, nextId, previewEvaluateAi);
                    }}
                    className="flex-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs bg-white text-gray-900 font-medium focus:border-indigo-600"
                  >
                    {previewData.available_leads.map((ld) => (
                      <option key={ld.id} value={ld.id}>
                        {ld.first_name} {ld.last_name} {ld.company_name ? `— ${ld.company_name}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {previewLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <RefreshCw className="h-6 w-6 animate-spin text-indigo-600 mb-2" />
                  <span className="text-xs">Rendering personalized preview...</span>
                </div>
              ) : previewData?.error ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
                  {previewData.error}
                </div>
              ) : previewData ? (
                <>
                  {/* Lead Card Context */}
                  <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-200 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 text-white font-bold flex items-center justify-center text-sm shadow-xs">
                        {previewData.lead_preview?.first_name?.[0]}
                        {previewData.lead_preview?.last_name?.[0]}
                      </div>
                      <div>
                        <h4 className="font-bold text-sm text-gray-900">
                          {previewData.lead_preview?.first_name} {previewData.lead_preview?.last_name}
                        </h4>
                        <p className="text-xs text-gray-500 font-medium">
                          {previewData.lead_preview?.job_title} at{' '}
                          <span className="text-indigo-600 font-semibold">{previewData.lead_preview?.company_name}</span>
                        </p>
                        <p className="text-[10px] text-gray-400">{previewData.lead_preview?.location}</p>
                      </div>
                    </div>
                    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                      previewData.is_illustrative_preview
                        ? 'text-amber-700 bg-amber-50 border-amber-200'
                        : 'text-emerald-700 bg-emerald-50 border-emerald-200'
                    }`}>
                      {previewData.is_illustrative_preview ? 'Sample Lead' : 'Real Lead'}
                    </span>
                  </div>

                  {/* Evaluated Rendered Message */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[11px] font-bold uppercase tracking-wider text-gray-400">
                        {previewEvaluateAi ? 'Personalized AI Output' : 'Preview output'}
                      </label>
                      {previewData.has_ai_tokens && (
                        <button
                          type="button"
                          onClick={() => {
                            const nextEval = !previewEvaluateAi;
                            setPreviewEvaluateAi(nextEval);
                            handleOpenPreview(selectedStep, previewLeadId || previewData.selected_lead_id, nextEval);
                          }}
                          className="text-[11px] font-semibold text-purple-700 hover:text-purple-900 flex items-center gap-1"
                        >
                          <Sparkles className="w-3 h-3" />
                          {previewEvaluateAi ? 'Show raw placeholder' : 'Generate AI personalization'}
                        </button>
                      )}
                    </div>
                    <div className="p-4 rounded-xl bg-white border border-indigo-200 shadow-xs text-xs text-gray-800 leading-relaxed font-sans whitespace-pre-wrap space-y-2">
                      {previewData.evaluated_subject && (
                        <div className="pb-2 border-b border-indigo-100 text-xs">
                          <span className="font-bold text-indigo-700 uppercase tracking-wider text-[10px] mr-1.5">Subject:</span>
                          <span className="font-semibold text-gray-900">{previewData.evaluated_subject}</span>
                        </div>
                      )}
                      <div>{previewData.evaluated_text || 'No copy written for this step yet.'}</div>
                    </div>
                  </div>

                  {/* Voice Note Spoken Audio Preview inside Sequence Builder Preview Modal */}
                  {selectedStep?.type === 'voice_note' && (
                    <div className="p-3.5 rounded-xl bg-rose-50/70 border border-rose-200 space-y-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className="p-1.5 rounded-lg bg-rose-600 text-white">
                            <Mic className="w-3.5 h-3.5" />
                          </div>
                          <div>
                            <h5 className="text-xs font-bold text-rose-950">Spoken Voice Note Preview</h5>
                            <p className="text-[10px] text-rose-700">
                              {selectedStep.config?.recorded_audio_data_url
                                ? 'Playing attached custom audio recording'
                                : 'Listen to how this personalized script sounds for the selected prospect'}
                            </p>
                          </div>
                        </div>
                        {!selectedStep.config?.recorded_audio_data_url && (
                          <button
                            type="button"
                            onClick={() => {
                              const textToSpeak = previewData.evaluated_text || previewData.ai_generated_text || '';
                              if (!textToSpeak) return;
                              if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
                                if (isSpeakingPreview) {
                                  window.speechSynthesis.cancel();
                                  setIsSpeakingPreview(false);
                                  return;
                                }
                                window.speechSynthesis.cancel();
                                const utterance = new SpeechSynthesisUtterance(textToSpeak);
                                utterance.rate = 1.0;
                                utterance.onend = () => setIsSpeakingPreview(false);
                                utterance.onerror = () => setIsSpeakingPreview(false);
                                setIsSpeakingPreview(true);
                                window.speechSynthesis.speak(utterance);
                              } else {
                                setToastMessage('Browser speech synthesis unavailable in this environment.');
                              }
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-2xs transition-colors"
                          >
                            <Play className="w-3.5 h-3.5" />
                            {isSpeakingPreview ? 'Stop Voice Preview' : 'Listen to Voice Preview'}
                          </button>
                        )}
                      </div>
                      {selectedStep.config?.recorded_audio_data_url && (
                        <audio
                          controls
                          src={selectedStep.config.recorded_audio_data_url}
                          className="w-full h-8"
                        />
                      )}
                    </div>
                  )}

                  <div className="p-3 bg-purple-50/60 border border-purple-100 rounded-xl text-[11px] text-purple-900 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-purple-600 shrink-0 mt-0.5" />
                    <span>{previewData.notice || 'This is illustrative sample output. Prompt guidance is not generated by live campaigns.'}</span>
                  </div>
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-gray-100 bg-gray-50 flex items-center justify-between gap-2">
              {previewData?.has_ai_tokens && (previewData?.ai_generated_text || previewData?.evaluated_text) ? (
                <button
                  type="button"
                  onClick={() => applyEvaluatedPreviewToStep(previewData.ai_generated_text || previewData.evaluated_text)}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Apply AI Copy to Step
                </button>
              ) : <div />}
              <button
                type="button"
                onClick={() => setPreviewModalOpen(false)}
                className="px-5 py-2 bg-gray-900 hover:bg-black text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP LEADS QUEUE & FAILED LEADS DRAWER */}
      {stepLeadsDrawer.open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute top-0 right-0 bottom-0 w-[420px] max-w-[95vw] h-full max-h-full bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col overflow-hidden animate-slide-left"
        >
          <div className="flex items-center justify-between p-4 border-b border-gray-100 shrink-0">
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Step Queue: {stepLeadsDrawer.title}</h3>
              <p className="text-[11px] text-gray-400">Leads currently waiting, completed, or failed at this step</p>
            </div>
            <button
              type="button"
              onClick={() => setStepLeadsDrawer({ open: false, nodeId: null, title: '', loading: false, data: null })}
              className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 text-left">
            {stepLeadsDrawer.loading ? (
              <div className="py-12 text-center text-xs text-gray-400">Loading leads at this step...</div>
            ) : (
              <>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div className="p-2 rounded-xl bg-indigo-50 border border-indigo-100">
                    <div className="text-sm font-bold text-indigo-700">{stepLeadsDrawer.data?.counts?.queued || 0}</div>
                    <div className="text-[10px] text-indigo-600 font-semibold">Queued</div>
                  </div>
                  <div className="p-2 rounded-xl bg-amber-50 border border-amber-100">
                    <div className="text-sm font-bold text-amber-700">{stepLeadsDrawer.data?.counts?.in_progress || 0}</div>
                    <div className="text-[10px] text-amber-600 font-semibold">Waiting</div>
                  </div>
                  <div className="p-2 rounded-xl bg-emerald-50 border border-emerald-100">
                    <div className="text-sm font-bold text-emerald-700">{stepLeadsDrawer.data?.counts?.completed || 0}</div>
                    <div className="text-[10px] text-emerald-600 font-semibold">Done</div>
                  </div>
                  <div className="p-2 rounded-xl bg-rose-50 border border-rose-100">
                    <div className="text-sm font-bold text-rose-700">{stepLeadsDrawer.data?.counts?.failed || 0}</div>
                    <div className="text-[10px] text-rose-600 font-semibold">Failed</div>
                  </div>
                </div>
                {(stepLeadsDrawer.data?.leads || []).map((item) => (
                  <div key={item.lead_id} className="p-3 rounded-xl border border-gray-200 bg-white space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-900">
                        {item.first_name} {item.last_name}
                      </span>
                      <div className="flex items-center gap-1">
                        {item.ab_variant && (
                          <span className="px-1.5 py-0.5 rounded bg-violet-50 text-violet-700 text-[10px] font-bold border border-violet-200">
                            Var {item.ab_variant}
                          </span>
                        )}
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          item.step_status === 'failed'
                            ? 'bg-rose-50 text-rose-700 border border-rose-200'
                            : item.step_status === 'completed'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                        }`}>
                          {item.step_status}
                        </span>
                      </div>
                    </div>
                    <p className="text-[11px] text-gray-500">{item.job_title} {item.company_name ? `at ${item.company_name}` : ''}</p>
                    {item.failure_reason && (
                      <p className="text-[11px] text-rose-600 font-medium bg-rose-50/70 px-2 py-1 rounded-lg mt-1">
                        {item.failure_reason}
                      </p>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
