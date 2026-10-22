import React, { useState, useEffect, useRef } from 'react';
import {
  Plus,
  Search,
  Sparkles,
  MoreVertical,
  RefreshCw,
  Pencil,
  Calendar,
  X,
  Play,
  Pause,
  Trash2,
  ExternalLink,
  ArrowRight,
  Copy,
} from 'lucide-react';
import { toast } from 'sonner';
import OutreachCampaignWizard from './OutreachCampaignWizard';
import OutreachCampaignDetail from './OutreachCampaignDetail';
import { flattenTreeToDAG } from '../components/sequence/sequenceGraph';
import { reviewedTemplateDeletion } from '../utils/templateDeletion';
import { deletionInputDigest, matchesDeletionReceipt } from '../utils/templateDeletionRecovery';
import { validSaveContext } from '../hooks/useTemplateSave';
import TemplateMetadataEditor from '../components/TemplateMetadataEditor';
import { reviewedTemplateMetadata } from '../utils/templateMetadata';
import TemplateGraphEditor from '../components/TemplateGraphEditor';
import { reviewedTemplateGraph } from '../utils/templateGraph';
import useTemplateMetadataRecovery from '../hooks/useTemplateMetadataRecovery';
import useTemplateGraphRecovery from '../hooks/useTemplateGraphRecovery';
import useTemplateDeletionRecovery from '../hooks/useTemplateDeletionRecovery';
import { readReferences as readTemplateDeletionReferences, storeReference as storeTemplateDeletionReference, clearReference as clearTemplateDeletionReference } from '../utils/templateDeletionReferences';
import { sameReference } from '../utils/templateSaveReferences';
import { templateActionAllowed, templateAccessLabel } from '../utils/templateAccess';

const DELETION_REFERENCES_KEY = 'unravler.campaign-deletions.v1';
const readDeletionReferences = () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(DELETION_REFERENCES_KEY) || '{}');
    return Object.fromEntries(Object.entries(saved).filter(([, op]) => op
      && typeof op.id === 'string' && typeof op.workspaceId === 'string'
      && typeof op.requestId === 'string' && /^[a-f0-9-]{36}$/i.test(op.requestId)
      && ['deletion_pending', 'deleted', 'restore_pending'].includes(op.phase)));
  } catch { return {}; }
};
const deletionKey = (op) => JSON.stringify([op.workspaceId, op.id]);

export const PREBUILT_TEMPLATES = [
  {
    id: 'tpl_connect_and_follow_up',
    name: 'Connect and follow up',
    description: 'Clean connection invite with no note, and follow-up message 1 day after acceptance.',
    nodes: [
      {
        id: 'step_connect_root',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 0,
        config: { note: '' },
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_msg_followup',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Hi {{first_name}}, thanks for...',
        delay_hours: 24,
        config: {
          body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
        },
        position: { x: 400, y: 200 },
      },
    ],
    edges: [
      { id: 'e_conn_to_msg', source: 'step_connect_root', target: 'step_msg_followup', label: 'accepted' },
    ],
    tree: [
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
    ],
  },
  {
    id: 'tpl_profile_warmup',
    name: 'Profile warm-up',
    description: 'Multi-touch warm-up sequence: View profile and like recent post before sending a connection invite and welcome message.',
    nodes: [
      {
        id: 'step_warmup_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_hours: 0,
        config: { dwell_mode: 'realistic', skip_if_visited: true },
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_warmup_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_hours: 24,
        config: { max_post_age_days: 30, skip_if_no_posts: true },
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_warmup_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 24,
        config: { note: '' },
        position: { x: 250, y: 310 },
      },
      {
        id: 'step_warmup_msg',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Hi {{first_name}}, thanks for...',
        delay_hours: 24,
        config: {
          body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
        },
        position: { x: 400, y: 440 },
      },
    ],
    edges: [
      { id: 'e_warmup_1', source: 'step_warmup_visit', target: 'step_warmup_like' },
      { id: 'e_warmup_2', source: 'step_warmup_like', target: 'step_warmup_connect' },
      { id: 'e_warmup_3', source: 'step_warmup_connect', target: 'step_warmup_msg', label: 'accepted' },
    ],
    tree: [
      {
        id: 'step_warmup_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_days: 0,
        config: { dwell_mode: 'realistic', skip_if_visited: true },
      },
      {
        id: 'step_warmup_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_days: 1,
        config: { max_post_age_days: 30, skip_if_no_posts: true },
      },
      {
        id: 'step_warmup_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_days: 1,
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
                id: 'step_warmup_msg',
                type: 'send_message',
                title: 'Send message',
                subtitle: 'Hi {{first_name}}, thanks for...',
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
    ],
  },
  {
    id: 'tpl_voice_note_outreach',
    name: 'Voice note outreach',
    description: 'Profile visit, clean invite, and personalized voice note upon acceptance.',
    nodes: [
      {
        id: 'step_vn_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_hours: 0,
        config: {},
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_vn_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 24,
        config: { note: '' },
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_vn_voice',
        type: 'voice_note',
        title: 'Voice note',
        subtitle: 'Personalized AI cloned voice bubble',
        delay_hours: 24,
        config: {
          script: 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!',
          fallback: 'Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.',
        },
        position: { x: 400, y: 320 },
      },
      {
        id: 'step_vn_msg',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Following up on voice note',
        delay_hours: 48,
        config: {
          body: 'Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!',
        },
        position: { x: 300, y: 460 },
      },
    ],
    edges: [
      { id: 'e_vn_1', source: 'step_vn_visit', target: 'step_vn_connect' },
      { id: 'e_vn_2', source: 'step_vn_connect', target: 'step_vn_voice', label: 'accepted' },
      { id: 'e_vn_3', source: 'step_vn_voice', target: 'step_vn_msg', label: 'no reply' },
    ],
    tree: [
      {
        id: 'step_vn_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_days: 0,
        config: {},
      },
      {
        id: 'step_vn_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_days: 1,
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
                id: 'step_vn_voice',
                type: 'voice_note',
                title: 'Voice note',
                subtitle: 'Personalized AI cloned voice bubble',
                delay_days: 1,
                config: {
                  script: 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!',
                  fallback: 'Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.',
                },
                branches: {
                  left: {
                    condition: 'no reply',
                    type: 'danger',
                    steps: [
                      {
                        id: 'step_vn_msg',
                        type: 'send_message',
                        title: 'Send message',
                        subtitle: 'Following up on voice note',
                        delay_days: 2,
                        config: {
                          body: 'Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!',
                        },
                        branches: {
                          left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
                          right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                        },
                      },
                    ],
                  },
                  right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                },
              },
            ],
          },
        },
      },
    ],
  },
  {
    id: 'tpl_multitouch_inmail',
    name: 'Multi-touch InMail & engage',
    description: 'Engage via follow and post like before dispatching targeted InMail directly to decision makers.',
    nodes: [
      {
        id: 'step_inmail_follow',
        type: 'follow',
        title: 'Follow',
        subtitle: "Follow lead's profile",
        delay_hours: 0,
        config: {},
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_inmail_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_hours: 24,
        config: {},
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_inmail_send',
        type: 'inmail',
        title: 'InMail',
        subtitle: 'Send message to 2nd/3rd degree lead',
        delay_hours: 24,
        config: {
          subject: 'Quick question regarding {{company_name}}',
          message: 'Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!',
        },
        position: { x: 250, y: 320 },
      },
    ],
    edges: [
      { id: 'e_inmail_1', source: 'step_inmail_follow', target: 'step_inmail_like' },
      { id: 'e_inmail_2', source: 'step_inmail_like', target: 'step_inmail_send' },
    ],
    tree: [
      {
        id: 'step_inmail_follow',
        type: 'follow',
        title: 'Follow',
        subtitle: "Follow lead's profile",
        delay_days: 0,
        config: {},
      },
      {
        id: 'step_inmail_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_days: 1,
        config: {},
      },
      {
        id: 'step_inmail_send',
        type: 'inmail',
        title: 'InMail',
        subtitle: 'Send message to 2nd/3rd degree lead',
        delay_days: 1,
        config: {
          subject: 'Quick question regarding {{company_name}}',
          message: 'Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!',
        },
        branches: {
          left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
          right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
        },
      },
    ],
  },
];

// Configuration eligibility comes from shared server graph/capability analysis.
// It grants neither live execution nor sender/mailbox readiness.
export const isLaunchableTemplate = (template) => {
  if (!Boolean(
  template && Array.isArray(template.nodes) && template.nodes.length > 0
  && template.nodes.length <= 100 && Array.isArray(template.edges) && template.edges.length <= 200
  && Array.isArray(template.tree) && template.tree.length > 0 && template.tree.length <= 100
  && template.compatibility?.contract_version === 1 && template.compatibility.valid === true
  && template.compatibility.configuration_available === true && template.compatibility.execution_authorized === false
  )) return false;
  try {
    const visible = flattenTreeToDAG(template.tree);
    const ids = new Set(template.nodes.map((node) => node?.id));
    return ids.size === template.nodes.length
      && template.nodes.every((node) => node && typeof node.id === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(node.id) && typeof node.type === 'string')
      && template.edges.every((edge) => edge && ids.has(edge.source) && ids.has(edge.target))
      && visible.nodes.length === template.nodes.length
      && visible.nodes.every((node) => template.nodes.some((raw) => raw.id === node.id && raw.type === node.type));
  } catch { return false; }
};

export default function OutreachCampaigns({
  onOpenWizard,
  selectedCampaignId: propSelectedCampaignId,
  onSelectCampaign: propOnSelectCampaign,
  refreshKey,
  lastSavedDraft,
}) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [campaignError, setCampaignError] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [activeCampaignId, setActiveCampaignId] = useState(null);
  const [activeWizardStep, setActiveWizardStep] = useState(1);
  const [activeWizardName, setActiveWizardName] = useState('');
  const openCampaignWizard = (id, step = 2, name = '') => {
    if (onOpenWizard) {
      onOpenWizard(id, step, name);
    } else {
      setActiveCampaignId(id);
      setActiveWizardStep(step);
      setActiveWizardName(name || '');
      setIsWizardOpen(true);
    }
  };
  const [internalSelectedId, setInternalSelectedId] = useState(null);
  const selectedCampaignId = propSelectedCampaignId !== undefined ? propSelectedCampaignId : internalSelectedId;
  const setSelectedCampaignId = (id) => {
    if (propOnSelectCampaign) {
      propOnSelectCampaign(id);
    } else {
      setInternalSelectedId(id);
    }
  };
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templatesList, setTemplatesList] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [templateError, setTemplateError] = useState('');
  const templateRequestRef = useRef(0);
  const templateCatalogTokenRef = useRef(undefined);
  const templateUseRef = useRef(false);
  const [usingTemplateId, setUsingTemplateId] = useState(null);
  const templateDeleteRef = useRef(null);
  const [templateDeletion, setTemplateDeletion] = useState(null);
  const templateDeletionBlocked = Boolean(templateDeletion);
  const templateMetadataRef = useRef(null);
  const [templateMetadata, setTemplateMetadata] = useState(null);
  const [templateMetadataNotice, setTemplateMetadataNotice] = useState(false);
  const [templateGraphNotice, setTemplateGraphNotice] = useState(false);
  const metadataRecovery = useTemplateMetadataRecovery(isTemplatesOpen, () => {
    toast.success('Original template update confirmed');
    fetchTemplates(true);
  });
  const graphRecovery = useTemplateGraphRecovery(isTemplatesOpen, () => {
    toast.success('Original template sequence update confirmed');
    fetchTemplates(true);
  });
  const deletionRecovery = useTemplateDeletionRecovery(isTemplatesOpen, (reference) => {
    if (sameReference(templateDeleteRef.current?.reference, reference)) {
      templateDeleteRef.current = null;
      setTemplateDeletion(null);
    }
    toast.success('Original template deletion confirmed');
    fetchTemplates(true);
  });
  const templateRecoveryBlocked = metadataRecovery.blocked || graphRecovery.blocked || deletionRecovery.blocked;
  const templateMountedRef = useRef(true);
  const currentTemplateCatalog = () => templateMountedRef.current
    && templateCatalogTokenRef.current === localStorage.getItem('token');
  useEffect(() => {
    templateMountedRef.current = true;
    return () => { templateMountedRef.current = false; };
  }, []);
  const [deletionOperations, setDeletionOperations] = useState(readDeletionReferences);
  const deletionOperationsRef = useRef(deletionOperations);
  const [deletionBusy, setDeletionBusy] = useState({});
  const saveDeletionReference = (op, remove = false) => {
    const next = { ...deletionOperationsRef.current };
    if (remove) delete next[deletionKey(op)];
    else next[deletionKey(op)] = op;
    // Save the request identity before transport. Only operation references are retained.
    sessionStorage.setItem(DELETION_REFERENCES_KEY, JSON.stringify(next));
    deletionOperationsRef.current = next;
    setDeletionOperations(next);
  };
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [newCampaignModalOpen, setNewCampaignModalOpen] = useState(false);
  const [scratchCampaignName, setScratchCampaignName] = useState('');
  const [isCreatingCampaign, setIsCreatingCampaign] = useState(false);

  useEffect(() => {
    if (!menuOpenId) return undefined;
    const handleOutsideClick = () => setMenuOpenId(null);
    document.addEventListener('click', handleOutsideClick);
    return () => document.removeEventListener('click', handleOutsideClick);
  }, [menuOpenId]);

  // Optimistically reflect newly saved campaign from wizard with 0ms latency
  useEffect(() => {
    if (lastSavedDraft && lastSavedDraft.id) {
      setCampaigns((prev) => {
        const without = prev.filter((c) => c.id !== lastSavedDraft.id);
        return [lastSavedDraft, ...without];
      });
    }
  }, [lastSavedDraft]);

  const fetchCampaigns = async () => {
    setLoading(true);
    setCampaignError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        const incoming = Array.isArray(data) ? data : [];
        setCampaigns((prev) => {
          if (lastSavedDraft && lastSavedDraft.id) {
            const found = incoming.find((c) => c.id === lastSavedDraft.id);
            if (!found) {
              return [lastSavedDraft, ...incoming];
            }
          }
          return incoming;
        });
      } else {
        const error = await res.json().catch(() => ({}));
        setCampaignError(error.detail || 'Could not load campaigns. Please try again.');
      }
    } catch (err) {
      console.error('Failed to fetch campaigns:', err);
      setCampaignError(err.message || 'Could not load campaigns. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplates = async (reviewMetadata = false) => {
    if (templateUseRef.current || ['preparing', 'pending', 'checking'].includes(templateDeleteRef.current?.phase)
      || templateMetadataRef.current && reviewMetadata !== true) return false;
    const generation = ++templateRequestRef.current;
    templateCatalogTokenRef.current = undefined;
    setLoadingTemplates(true);
    setTemplatesList([]);
    setTemplateError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/sequences/templates', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        if (reviewMetadata === true && res.status !== 200) throw new Error('Could not review current template details. Please retry.');
        const data = await res.json();
        if (token !== localStorage.getItem('token')) {
          throw new Error('Template account changed. Reload to review current details.');
        }
        if (!Array.isArray(data) || data.length > 104 || data.some((item) => !item || typeof item.id !== 'string'
          || !item.id || typeof item.name !== 'string' || !item.name || item.description != null && typeof item.description !== 'string')
          || new Set(data.map((item) => item.id)).size !== data.length) {
          throw new Error('Sequence template data needs review. Please retry.');
        }
        if (generation === templateRequestRef.current && templateMountedRef.current) {
          templateCatalogTokenRef.current = token;
          setTemplatesList(data);
          if (reviewMetadata === true && templateMountedRef.current) {
            templateMetadataRef.current = null;
            setTemplateMetadata(null);
          }
          return true;
        }
      } else {
        throw new Error('Could not load sequence templates. Please retry.');
      }
    } catch (err) {
      if (generation === templateRequestRef.current) {
        setTemplateError(err.message || 'Could not load sequence templates. Please retry.');
      }
    } finally {
      if (generation === templateRequestRef.current) setLoadingTemplates(false);
    }
    return false;
  };

  useEffect(() => {
    fetchCampaigns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (isTemplatesOpen) {
      fetchTemplates();
    }
    return () => { templateRequestRef.current += 1; };
  }, [isTemplatesOpen]);

  const deletionHeaders = (token) => ({'Content-Type':'application/json',Authorization:token ? `Bearer ${token}` : ''});
  const confirmTemplateDeletion = (operation, stillCurrent) => {
    if (!templateMountedRef.current || templateDeleteRef.current !== operation || !stillCurrent()) return false;
    clearTemplateDeletionReference(operation.reference);
    if (!stillCurrent()) return false;
    templateDeleteRef.current = null;
    setTemplateDeletion(null);
    toast.success('Original template deletion confirmed');
    // Historical confirmation cannot remove a replacement from the current catalog.
    fetchTemplates(true);
    return true;
  };

  const handleDeleteTemplate = async (template) => {
    if (!metadataRecovery.allowAction() || !graphRecovery.allowAction() || !deletionRecovery.allowAction()) return;
    if (!currentTemplateCatalog() || !templateActionAllowed(template, 'delete')) return;
    const captured = reviewedTemplateDeletion(template);
    if (!captured || loadingTemplates || templateError || templateUseRef.current || templateMetadataRef.current
      || templateDeleteRef.current || !templatesList.includes(template)) return;
    const original = {...captured, template_id:template.id};
    const frozen = JSON.stringify(original);
    const operation = {original, phase:'preparing'};
    const generation = templateRequestRef.current;
    const token = localStorage.getItem('token');
    templateDeleteRef.current = operation;
    setTemplateDeletion({...operation});
    const current = () => templateMountedRef.current && templateDeleteRef.current === operation;
    const sameContext = () => current() && generation === templateRequestRef.current && token === localStorage.getItem('token');
    const publish = (phase) => {if(current()){operation.phase=phase;setTemplateDeletion({...operation});}};
    let submitted = false;
    try {
      const contextResponse = await fetch('/api/v1/outreach/sequences/template-deletions/context', {
        credentials:'include', headers:deletionHeaders(token)});
      const context = await contextResponse.json();
      if (!sameContext()) {publish('stopped');return;}
      if (contextResponse.ok !== true || contextResponse.status !== 200 || !validSaveContext(context)
        || context.workspace_id !== original.workspace_id) throw new Error('context');
      const inputDigest = await deletionInputDigest(frozen);
      if (!sameContext()) {publish('stopped');return;}
      const requestId = globalThis.crypto.randomUUID();
      if (typeof requestId !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(requestId)) throw new Error('reference');
      const reference = {contract_version:1,workspace_id:context.workspace_id,scope_digest:context.scope_digest,
        request_id:requestId,input_digest:inputDigest};
      operation.reference = reference;
      submitted = true;
      storeTemplateDeletionReference(reference);
      publish('pending');
      const res = await fetch('/api/v1/outreach/sequences/template-deletions', {
        method:'POST',credentials:'include',headers:deletionHeaders(token),
        body:JSON.stringify({...reference,content_json:frozen})});
      const data = await res.json();
      if (!sameContext() || res.status !== 200 || res.ok !== true
        || !matchesDeletionReceipt(data,reference,original)) {publish('held');return;}
      if (!confirmTemplateDeletion(operation, sameContext)) publish('held');
    } catch {
      if (submitted) publish('held');
      else if (sameContext()) {
        templateDeleteRef.current=null;setTemplateDeletion(null);
        toast.error('Could not prepare template deletion. Review the current template and try again.');
      } else publish('stopped');
    }
  };

  const checkTemplateDeletion = async () => {
    const operation = templateDeleteRef.current;
    if (!operation?.reference || operation.phase !== 'held') return;
    operation.phase = 'checking';
    setTemplateDeletion({...operation});
    const generation = templateRequestRef.current;
    const token = localStorage.getItem('token');
    const current = () => templateMountedRef.current && templateDeleteRef.current === operation;
    const sameContext = () => current() && generation === templateRequestRef.current && token === localStorage.getItem('token');
    const hold = () => {if(current()){operation.phase='held';setTemplateDeletion({...operation});}};
    try {
      const res = await fetch('/api/v1/outreach/sequences/template-deletions/context', {
        credentials:'include',headers:deletionHeaders(token)});
      const context = await res.json();
      const reference = operation.reference;
      if (!sameContext() || res.status !== 200 || res.ok !== true || !validSaveContext(context)
        || context.workspace_id !== reference.workspace_id || context.scope_digest !== reference.scope_digest) {hold();return;}
      const query = new URLSearchParams({workspace_id:reference.workspace_id,scope_digest:reference.scope_digest,input_digest:reference.input_digest});
      const result = await fetch(`/api/v1/outreach/sequences/template-deletions/${encodeURIComponent(reference.request_id)}?${query}`, {
        credentials:'include',headers:deletionHeaders(token)});
      const receipt = await result.json();
      if (!sameContext() || result.status !== 200 || result.ok !== true
        || !matchesDeletionReceipt(receipt,reference,operation.original)) {hold();return;}
      if (!confirmTemplateDeletion(operation, sameContext)) hold();
    } catch {hold();}
  };

  const handleUseTemplate = async (tpl) => {
    if (!metadataRecovery.allowAction() || !graphRecovery.allowAction() || !deletionRecovery.allowAction()) return;
    if (!currentTemplateCatalog() || !templateActionAllowed(tpl, 'configure')) return false;
    const fullTpl = tpl;
    if (templateUseRef.current || templateMetadataRef.current || loadingTemplates || templateError || !isLaunchableTemplate(fullTpl)
      || templateDeleteRef.current) {
      toast.error('This template needs a successful compatibility review before configuration.');
      return false;
    }
    templateUseRef.current = true;
    setUsingTemplateId(fullTpl.id);
    const generation = templateRequestRef.current;
    const token = localStorage.getItem('token');
    const currentUse = () => templateMountedRef.current && generation === templateRequestRef.current
      && token === localStorage.getItem('token');
    try {
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: fullTpl.name || 'Connect and follow up',
          draft_step: 2,
          draft_progress: 60,
          next_step_label: 'Next: Launch',
        }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Could not create a campaign from this template.');
      }
      const draft = await res.json();
      if (!draft?.id) throw new Error('The campaign draft was not saved.');
      if (!currentUse()) return false;
      const sequenceRes = await fetch('/api/v1/outreach/sequences', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: draft.id,
          nodes: fullTpl.nodes,
          edges: fullTpl.edges,
          tree: fullTpl.tree || null,
        }),
      });
      if (!sequenceRes.ok) {
        const error = await sequenceRes.json().catch(() => ({}));
        throw new Error(error.detail || 'The campaign was created, but its sequence could not be saved.');
      }
      if (!currentUse()) return false;
      setIsTemplatesOpen(false);
      toast.success(`Template loaded: “${fullTpl.name}”`);
      openCampaignWizard(draft.id, 2, fullTpl.name);
      return true;
    } catch (err) {
      if (currentUse()) toast.error(err.message || 'Could not load this template. Please try again.');
      return false;
    } finally {
      templateUseRef.current = false;
      if (templateMountedRef.current) setUsingTemplateId(null);
    }
  };

  const openTemplateMetadata = (template) => {
    if (!currentTemplateCatalog() || !templateActionAllowed(template, 'edit')) return;
    if (!metadataRecovery.allowAction() || !graphRecovery.allowAction() || !deletionRecovery.allowAction()) return;
    if (templateMetadataRef.current || templateUseRef.current || loadingTemplates || templateError
      || templateDeleteRef.current
      || !reviewedTemplateMetadata(template) || !templatesList.includes(template)) return;
    const operation = {template,generation:templateRequestRef.current};
    templateMetadataRef.current = operation;
    setTemplateMetadata(operation);
  };

  const closeTemplateMetadata = () => {
    templateMetadataRef.current = null;
    setTemplateMetadata(null);
  };

  const openTemplateGraph = (template) => {
    if (!currentTemplateCatalog() || !templateActionAllowed(template, 'edit')) return;
    if (!metadataRecovery.allowAction() || !graphRecovery.allowAction() || !deletionRecovery.allowAction()) return;
    if (templateMetadataRef.current || templateUseRef.current || loadingTemplates || templateError
      || templateDeleteRef.current
      || !reviewedTemplateGraph(template) || !isLaunchableTemplate(template) || !templatesList.includes(template)) return;
    const operation = {template,generation:templateRequestRef.current,kind:'graph'};
    templateMetadataRef.current = operation;
    setTemplateMetadata(operation);
  };

  const savedTemplateMetadata = (template,receipt,recovery) => {
    const operation = templateMetadataRef.current;
    if (!templateMountedRef.current || operation?.template !== template
      || operation.generation !== templateRequestRef.current) return;
    closeTemplateMetadata();
    toast.success(recovery?.historical === true
      ? operation.kind === 'graph' ? 'Original template sequence update confirmed' : 'Original template update confirmed'
      : operation.kind === 'graph' ? 'Template sequence updated' : 'Template details updated');
    fetchTemplates();
  };

  // Auto-drafting when user clicks "New campaign"
  const handleCreateNewCampaign = async (nameOverride) => {
    const safeName = typeof nameOverride === 'string' && nameOverride.trim()
      ? nameOverride.trim()
      : `Campaign ${campaigns.length + 1}`;

    setIsCreatingCampaign(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: safeName,
          draft_step: 1,
          draft_progress: 20,
          next_step_label: 'Next: configure sequence',
        }),
      });
      if (res.ok) {
        const draft = await res.json();
        if (!draft?.id) throw new Error('The campaign draft was not saved.');
        toast.success(`Campaign created: “${safeName}”`);
        openCampaignWizard(draft.id, 1, draft.name || safeName);
        return true;
      }
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'Could not create campaign. Please try again.');
    } catch (err) {
      console.error('Failed to auto-draft campaign:', err);
      toast.error(err.message || 'Could not create campaign. Please try again.');
      return false;
    } finally {
      setIsCreatingCampaign(false);
    }
  };

  const handlePauseCampaign = async (campaignId, campaignName) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/pause`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success(`Paused “${campaignName}”`);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to pause campaign');
      }
    } catch (err) {
      console.error('Failed to pause campaign:', err);
      toast.error('Error pausing campaign');
    }
  };

  const handleResumeCampaign = async (campaignId, campaignName) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/launch`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ status: 'active' }),
      });
      if (res.ok) {
        toast.success(`Resumed “${campaignName}”`);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to resume campaign');
      }
    } catch (err) {
      console.error('Failed to resume campaign:', err);
      toast.error('Error resuming campaign');
    }
  };

  const handleDuplicateCampaign = async (campaignId) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/duplicate`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const cloned = await res.json();
        toast.success(`Duplicated as “${cloned.name}”`);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to duplicate campaign');
      }
    } catch (err) {
      console.error('Failed to duplicate campaign:', err);
      toast.error('Error duplicating campaign');
    }
  };

  const runCampaignDeletion = async (op, restore = false) => {
    const key = deletionKey(op);
    if (deletionBusy[key]) return;
    const pending = { ...op, phase: restore ? 'restore_pending' : 'deletion_pending' };
    try {
      saveDeletionReference(pending);
    } catch {
      toast.error('Could not save the operation reference. Enable tab storage before continuing.');
      return;
    }
    setDeletionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      const token = localStorage.getItem('token');
      const query = new URLSearchParams({ request_id: op.requestId, expected_workspace_id: op.workspaceId });
      const res = await fetch(`/api/v1/outreach/campaigns/${encodeURIComponent(op.id)}${restore ? '/restore' : ''}?${query}`, {
        method: restore ? 'POST' : 'DELETE', credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 404 && !restore) {
          saveDeletionReference(op, true);
          fetchCampaigns();
          toast.success('Campaign deleted');
          return;
        }
        throw new Error(data.detail || 'Could not confirm the change. Retry this operation.');
      }
      if (data.id !== op.id || data.request_id !== op.requestId
        || !['deleted', 'restored', 'deletion_pending', 'restore_pending'].includes(data.status)) {
        throw new Error('The operation could not be confirmed. Check its status before continuing.');
      }
      if (data.status === 'restored') {
        saveDeletionReference(op, true);
        toast.success('Campaign restored and paused. Review it before launching.');
      } else {
        saveDeletionReference({ ...op, phase: data.status });
        if (data.status === 'deleted') toast.success('Campaign deleted');
      }
      fetchCampaigns();
    } catch (err) {
      toast.error(err.message || 'Could not confirm the change. Retry this operation.');
    } finally {
      setDeletionBusy((prev) => ({ ...prev, [key]: false }));
    }
  };

  const handleSoftDelete = (campaignId) => {
    setMenuOpenId(null);
    const campaign = campaigns.find((item) => item.id === campaignId);
    if (!campaign || typeof campaign.workspace_id !== 'string' || !globalThis.crypto?.randomUUID) {
      toast.error('Reload the campaign in a secure browser before deleting it.');
      return;
    }
    const identity = { id: campaignId, workspaceId: campaign.workspace_id };
    const existing = deletionOperationsRef.current[deletionKey(identity)];
    runCampaignDeletion(existing || { ...identity, requestId: globalThis.crypto.randomUUID(), phase: 'deletion_pending' });
  };

  // If a campaign is selected, render Campaign Details (media_1790104472298.png)
  if (selectedCampaignId) {
    return (
      <OutreachCampaignDetail
        campaignId={selectedCampaignId}
        onBack={() => {
          setSelectedCampaignId(null);
          fetchCampaigns();
        }}
        onEdit={(id, step, name) => {
          openCampaignWizard(id, step || 2, name || '');
        }}
      />
    );
  }

  // If standalone wizard fallback is open
  if (isWizardOpen) {
    return (
      <OutreachCampaignWizard
        campaignId={activeCampaignId || 'new'}
        initialStep={activeWizardStep}
        initialName={activeWizardName}
        onBack={() => {
          setIsWizardOpen(false);
          setActiveCampaignId(null);
          fetchCampaigns();
        }}
        onComplete={() => {
          setIsWizardOpen(false);
          setActiveCampaignId(null);
          fetchCampaigns();
        }}
      />
    );
  }

  // Templates View matching media_1790104784825.png
  if (isTemplatesOpen) {
    const displayTemplates = loadingTemplates || templateError ? [] : templatesList;

    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <button
          onClick={() => {
            const operation = templateDeleteRef.current;
            if (operation?.reference) {
              try {
                if (!readTemplateDeletionReferences().some(ref => ref.scope_digest === operation.reference.scope_digest)) {
                  storeTemplateDeletionReference(operation.reference);
                }
              }
              catch { toast.error('Could not retain the deletion reference. Check its original status before leaving this view.'); return; }
              templateDeleteRef.current = null;
              setTemplateDeletion(null);
            }
            setIsTemplatesOpen(false);
          }}
          disabled={usingTemplateId !== null || Boolean(templateMetadata) || ['preparing','pending','checking'].includes(templateDeletion?.phase)}
          className="text-xs font-semibold text-gray-500 hover:text-gray-900 transition-colors mb-4 inline-flex items-center gap-1.5"
        >
          ← Campaigns
        </button>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Templates</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Prebuilt sequences and workspace templates. Your role controls edits and deletion; Use creates a campaign draft.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {loadingTemplates && <span className="text-xs text-gray-400 animate-pulse">Loading templates...</span>}
            <button type="button" onClick={() => fetchTemplates()}
              disabled={loadingTemplates || usingTemplateId !== null || Boolean(templateMetadata) || Boolean(templateDeletion)}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
              Reload templates
            </button>
          </div>
        </div>

        {templateError && <div role="alert" className="mb-4 rounded-lg border border-rose-200 p-4 text-sm">
          <p>{templateError}</p>
          <button type="button" onClick={fetchTemplates} className="mt-2 font-semibold">Retry templates</button>
        </div>}
        {!loadingTemplates && !templateError && displayTemplates.length === 0 && <p className="mb-4 text-sm text-gray-500">No sequence templates are available.</p>}

        {metadataRecovery.blocked && !templateMetadata && <div role="alert" className="mb-4 rounded-lg border border-amber-200 p-4 text-sm">
          <p>{metadataRecovery.message}</p>
          <p>This checks the original update only. Missing status stays unconfirmed; edited text is not replayed.</p>
          <button type="button" disabled={metadataRecovery.checking} onClick={metadataRecovery.check}
            className="mt-2 font-semibold">Check saved details update status</button>
        </div>}
        {graphRecovery.blocked && !templateMetadata && <div role="alert" className="mb-4 rounded-lg border border-amber-200 p-4 text-sm">
          <p>{graphRecovery.message}</p>
          <p>This checks the original sequence update only. Missing status stays unconfirmed; the sequence is not replayed.</p>
          <button type="button" disabled={graphRecovery.checking} onClick={graphRecovery.check}
            className="mt-2 font-semibold">Check saved sequence update status</button>
        </div>}
        {deletionRecovery.blocked && !templateMetadata && !templateDeletion && <div role="alert" className="mb-4 rounded-lg border border-amber-200 p-4 text-sm">
          <p>{deletionRecovery.message}</p>
          <p>This confirms the original deletion only. A replacement is kept; missing status stays unconfirmed and deletion is not replayed.</p>
          <button type="button" disabled={deletionRecovery.checking} onClick={deletionRecovery.check}
            className="mt-2 font-semibold">Check saved deletion status</button>
        </div>}

        {templateMetadataNotice && !templateMetadata && <p role="status" className="mb-4 text-sm text-amber-800">
          {templateGraphNotice ? 'The earlier sequence update is unconfirmed. These are the current catalog templates; review the sequence before making a new edit.'
            : 'The earlier details update is unconfirmed. These are the current catalog details; review them before making a new edit.'}
        </p>}
        {templateMetadata?.kind === 'graph' ? <TemplateGraphEditor template={templateMetadata.template}
          onClose={closeTemplateMetadata} onSaved={savedTemplateMetadata}
          onRefresh={() => {setTemplateMetadataNotice(true);setTemplateGraphNotice(true);return fetchTemplates(true);}} />
          : templateMetadata && <TemplateMetadataEditor template={templateMetadata.template}
            onClose={closeTemplateMetadata} onSaved={savedTemplateMetadata}
            onRefresh={() => {setTemplateMetadataNotice(true);setTemplateGraphNotice(false);return fetchTemplates(true);}} />}

        {templateDeletion && <div role={['preparing','pending','checking'].includes(templateDeletion.phase) ? 'status' : 'alert'} className="mb-4 rounded-lg border border-amber-200 p-4 text-sm">
          {templateDeletion.phase === 'preparing' ? <p>Preparing reviewed template deletion…</p>
            : templateDeletion.phase === 'pending' ? <p>Deleting the reviewed template…</p>
              : templateDeletion.phase === 'checking' ? <p>Checking original template deletion…</p>
                : templateDeletion.phase === 'stopped' ? <>
                  <p>Deletion preparation stopped because the account or view changed. No deletion was submitted.</p>
                  <button type="button" onClick={() => {if(templateDeleteRef.current?.phase==='stopped'){templateDeleteRef.current=null;setTemplateDeletion(null);}}}
                    className="mt-2 font-semibold">Cancel deletion preparation</button>
                </> : <>
                  <p>Earlier deletion is unconfirmed. A refreshed catalog is not a deletion receipt.</p>
                  <p>Check the original request before another deletion. It will not be replayed. The reference is retained in this browser tab when storage is available; after reload, check its saved status in Templates.</p>
                  <button type="button" onClick={checkTemplateDeletion} className="mt-2 font-semibold">Check original deletion status</button>
                </>}
        </div>}

        <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-5">TEMPLATE</th>
                <th className="py-3 px-5">STEPS</th>
                <th className="py-3 px-5">READINESS</th>
                <th className="py-3 px-5 text-right">ACTION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {displayTemplates.map((tpl) => (
                <tr key={tpl.id} className="hover:bg-gray-50/60 transition-colors">
                  <td className="py-4 px-5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-gray-900">{tpl.name}</span>
                      {tpl.is_custom && (
                        <span className="px-2 py-0.5 text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 rounded-md">
                          Custom
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-gray-500 mt-1">{templateAccessLabel(tpl)}</p>
                    {tpl.description && (
                      <p className="text-[11px] text-gray-400 mt-0.5 truncate max-w-md">{tpl.description}</p>
                    )}
                  </td>
                  <td className="py-4 px-5 text-gray-500">{Array.isArray(tpl.nodes) ? tpl.nodes.length : '—'}</td>
                  <td className="py-4 px-5 text-gray-500">{isLaunchableTemplate(tpl) ? 'Ready to configure' : 'Graph needs review'}
                    {!isLaunchableTemplate(tpl) && <p className="max-w-sm text-xs">{typeof tpl.compatibility?.error === 'string' ? tpl.compatibility.error : 'This saved graph needs compatibility review before configuration.'}</p>}
                  </td>
                  <td className="py-4 px-5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {tpl.is_custom === true && (
                        <button type="button" onClick={() => openTemplateGraph(tpl)}
                          disabled={!templateActionAllowed(tpl, 'edit') || templateRecoveryBlocked || usingTemplateId !== null || Boolean(templateMetadata) || Boolean(templateDeletionBlocked) || !reviewedTemplateGraph(tpl) || !isLaunchableTemplate(tpl)}
                          aria-label={`Edit template sequence ${tpl.name}`}
                          className="rounded-lg px-2 py-1 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50">
                          Edit sequence
                        </button>
                      )}
                      {tpl.is_custom === true && (
                        <button type="button" onClick={() => openTemplateMetadata(tpl)}
                          disabled={!templateActionAllowed(tpl, 'edit') || templateRecoveryBlocked || usingTemplateId !== null || Boolean(templateMetadata) || Boolean(templateDeletionBlocked) || !reviewedTemplateMetadata(tpl)}
                          aria-label={`Edit template details ${tpl.name}`}
                          className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg transition-colors disabled:opacity-50">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {tpl.is_custom === true && (
                        <button
                          onClick={() => handleDeleteTemplate(tpl)}
                          disabled={!templateActionAllowed(tpl, 'delete') || templateRecoveryBlocked || usingTemplateId !== null || Boolean(templateMetadata) || Boolean(templateDeletionBlocked) || !reviewedTemplateDeletion(tpl)}
                          className="p-1.5 text-gray-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                          title={reviewedTemplateDeletion(tpl) ? 'Delete reviewed custom template' : 'Reload a valid template review before deleting'}
                          aria-label={`Delete template ${tpl.name}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => handleUseTemplate(tpl)}
                        disabled={!templateActionAllowed(tpl, 'configure') || templateRecoveryBlocked || !isLaunchableTemplate(tpl) || usingTemplateId !== null || Boolean(templateMetadata) || Boolean(templateDeletionBlocked)}
                        title={!isLaunchableTemplate(tpl) ? 'Requires a compatible, editable sequence graph' : undefined}
                        className="rounded-lg bg-indigo-50 text-[#5145cd] hover:bg-indigo-100 px-3.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {usingTemplateId === tpl.id ? 'Creating draft…' : !isLaunchableTemplate(tpl) ? 'Unavailable' : templateActionAllowed(tpl, 'configure') ? 'Use' : 'View only'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Find most recent draft campaign to display in Draft Banner
  const draftCampaign = campaigns.find((c) => c.status === 'draft');

  const filteredCampaigns = campaigns.filter((c) => {
    const matchesStatus =
      statusFilter === 'all' ||
      (statusFilter === 'sending' && c.status === 'active') ||
      (statusFilter === 'warming' && c.status === 'warming_up') ||
      (statusFilter === 'paused' && c.status === 'paused') ||
      (statusFilter === 'draft' && c.status === 'draft');
    const matchesSearch =
      !searchQuery || (c.name || '').toLowerCase().includes(searchQuery.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  return (
    <div className="max-w-6xl mx-auto px-6 pt-8 pb-48 space-y-4">
      {/* Top Header matching media_1790104399010.png */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Campaigns</h1>
          <p className="text-xs text-gray-500 mt-0.5">Your outreach campaigns, newest first.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsTemplatesOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            Browse winning templates
          </button>
          <button
            onClick={() => {
              setScratchCampaignName(`Campaign #${campaigns.length + 1}`);
              setNewCampaignModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New campaign
          </button>
        </div>
      </div>

      {/* Banner 1: Draft Banner matching media_1790104399010.png */}
      {draftCampaign && (statusFilter === 'all' || statusFilter === 'draft') && !searchQuery.trim() && (
        <div className="rounded-2xl border border-indigo-100 bg-white/90 p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-[#5145cd]">
              <Pencil className="h-4 w-4" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-900">
                  Your draft: {draftCampaign.name}
                </span>
                <span className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-[#5145cd]">
                  {draftCampaign.draft_progress || 40}% ready
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-36 sm:w-48 rounded-full bg-gray-100 overflow-hidden">
                  <div
                    className="h-full bg-[#5145cd] rounded-full transition-all duration-300"
                    style={{ width: `${draftCampaign.draft_progress || 40}%` }}
                  />
                </div>
                <span className="text-[11px] text-gray-400">
                  {draftCampaign.next_step_label || 'Next: configure sequence'}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={() => openCampaignWizard(draftCampaign.id, draftCampaign.draft_step || 2, draftCampaign.name)}
            className="rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors shrink-0"
          >
            Resume draft
          </button>
        </div>
      )}

      {/* Filter Row: Segmented Pills & Search Input matching media_1790104399010.png */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
        <div className="inline-flex items-center bg-gray-100/80 p-1 rounded-xl gap-1">
          {[
            { id: 'all', label: 'All', count: campaigns.length },
            { id: 'sending', label: 'Sending', count: campaigns.filter((c) => c.status === 'active').length },
            { id: 'warming', label: 'Warming up', count: campaigns.filter((c) => c.status === 'warming_up').length },
            { id: 'paused', label: 'Paused', count: campaigns.filter((c) => c.status === 'paused').length },
            { id: 'draft', label: 'Draft', count: campaigns.filter((c) => c.status === 'draft').length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all inline-flex items-center gap-1.5 ${
                statusFilter === tab.id
                  ? 'bg-white text-gray-900 shadow-2xs'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  statusFilter === tab.id ? 'bg-gray-100 text-gray-700' : 'text-gray-400'
                }`}
              >
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2 h-3.5 w-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search campaigns"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white pl-8 pr-3 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-2xs"
          />
        </div>
      </div>

      {Object.values(deletionOperations).map((op) => (
        <div key={deletionKey(op)} className="rounded-xl border border-gray-200 bg-gray-50/90 p-3.5 flex items-center justify-between text-xs transition-all shadow-2xs">
          <span className="text-gray-700">
            {op.phase === 'deleted' ? 'Campaign deleted. Undo restores it paused.'
              : op.phase === 'restore_pending' ? 'Campaign restoration needs confirmation. It stays stopped until complete.'
                : 'Campaign deletion needs confirmation. Finish cleanup using the same request.'}
          </span>
          <div className="flex items-center gap-2">
            <button
              disabled={deletionBusy[deletionKey(op)]}
              onClick={() => runCampaignDeletion(op, op.phase !== 'deletion_pending')}
              className="rounded-lg bg-[#5145cd] hover:bg-[#4338ca] text-white px-3 py-1 font-semibold text-xs transition-colors disabled:opacity-50"
            >
              {deletionBusy[deletionKey(op)] ? 'Checking…' : op.phase === 'deleted' ? 'Undo'
                : op.phase === 'restore_pending' ? 'Finish restoration' : 'Finish deletion'}
            </button>
            {op.phase === 'deleted' && (
              <button
                type="button"
                disabled={deletionBusy[deletionKey(op)]}
                onClick={() => saveDeletionReference(op, true)}
                aria-label="Dismiss deleted campaign notice"
                title="Dismiss"
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white hover:bg-gray-100 text-gray-600 hover:text-gray-900 px-2.5 py-1 font-semibold text-xs transition-colors disabled:opacity-50"
              >
                <X className="h-3.5 w-3.5" />
                <span>Dismiss</span>
              </button>
            )}
          </div>
        </div>
      ))}

      {/* Campaigns Table matching media_1790104399010.png */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-visible">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <RefreshCw className="h-6 w-6 animate-spin" />
          </div>
        ) : campaignError ? (
          <div role="alert" className="p-16 text-center text-sm text-red-600">
            {campaignError} <button type="button" onClick={fetchCampaigns} className="ml-2 font-semibold underline">Retry</button>
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <div className="p-16 text-center text-gray-500">
            <p className="text-xs font-medium text-gray-500">No campaigns found in this view.</p>
            <button
              onClick={() => {
                setScratchCampaignName(`Campaign #${campaigns.length + 1}`);
                setNewCampaignModalOpen(true);
              }}
              className="mt-3 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              + Create your first outreach campaign
            </button>
          </div>
        ) : (
          <div className="overflow-visible">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
                <tr>
                  <th className="py-3 px-5 rounded-tl-2xl">STATUS</th>
                  <th className="py-3 px-5">NAME</th>
                  <th className="py-3 px-5">LEADS DONE</th>
                  <th className="py-3 px-5">ACCEPTANCE</th>
                  <th className="py-3 px-5">REPLY</th>
                  <th className="py-3 px-5">SENDERS</th>
                  <th className="py-3 px-5">LAST ACTION</th>
                  <th className="py-3 px-5 text-right rounded-tr-2xl"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredCampaigns.map((camp) => (
                  <tr
                    key={camp.id}
                    onClick={() => {
                      if (camp.status === 'draft') {
                        openCampaignWizard(camp.id, camp.draft_step || 2, camp.name);
                      } else {
                        setSelectedCampaignId(camp.id);
                      }
                    }}
                    className="hover:bg-gray-50/60 transition-colors cursor-pointer group"
                  >
                    {/* Status Pill */}
                    <td className="py-4 px-5">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                          camp.status === 'active'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : camp.status === 'warming_up'
                            ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                            : camp.status === 'paused'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : camp.status === 'completed'
                            ? 'bg-blue-50 text-blue-700 border-blue-200'
                            : 'bg-white text-gray-600 border-gray-200'
                        }`}
                      >
                        {camp.status || 'draft'}
                      </span>
                    </td>

                    {/* Name + Subtitle */}
                    <td className="py-4 px-5">
                      <p className="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">
                        {camp.name}
                      </p>
                      <p className="text-[11px] text-gray-400 mt-0.5 font-normal">
                        {camp.leads_count ? `${camp.leads_count} leads` : 'Audience not set'} · {camp.status || 'draft'}
                        {camp.status === 'warming_up' && camp.auto_launch_missing_count > 0 && ` · ${camp.auto_launch_missing_count} awaiting warmup`}
                      </p>
                    </td>

                    {/* Leads Done */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.status === 'draft' || !camp.leads_contacted
                        ? '—'
                        : `${camp.leads_contacted} / ${camp.leads_count || 0}`}
                    </td>

                    {/* Acceptance */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.leads_contacted && camp.leads_contacted > 0
                        ? `${Math.round((camp.acceptances_count / camp.leads_contacted) * 100)}%`
                        : '—'}
                    </td>

                    {/* Reply */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.leads_contacted && camp.leads_contacted > 0
                        ? `${Math.round((camp.replies_count / camp.leads_contacted) * 100)}%`
                        : '—'}
                    </td>

                    {/* Senders */}
                    <td className="py-4 px-5 text-gray-500">
                      {camp.sender_account_ids?.length
                        ? `${camp.sender_account_ids.length} pooled`
                        : '—'}
                    </td>

                    {/* Last Action */}
                    <td className="py-4 px-5 text-gray-400 font-mono text-[11px]">
                      {camp.status === 'draft' ? '—' : camp.updated_at ? new Date(camp.updated_at).toLocaleDateString() : '—'}
                    </td>

                    {/* Options Menu ⋮ */}
                    <td
                      className="py-4 px-5 text-right relative"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => setMenuOpenId(menuOpenId === camp.id ? null : camp.id)}
                        className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>

                      {menuOpenId === camp.id && (
                        <div className="absolute right-5 mt-1 w-44 rounded-xl border border-gray-100 bg-white p-1 shadow-lg z-30 text-xs">
                          {camp.status === 'active' && (
                            <button
                              onClick={() => handlePauseCampaign(camp.id, camp.name)}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-amber-700 hover:bg-amber-50 font-medium flex items-center gap-2"
                            >
                              <Pause className="h-3.5 w-3.5 text-amber-600" />
                              Pause campaign
                            </button>
                          )}
                          {camp.status === 'warming_up' && (
                            <button onClick={() => handlePauseCampaign(camp.id, camp.name)}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-amber-700 hover:bg-amber-50 font-medium flex items-center gap-2">
                              <Pause className="h-3.5 w-3.5" /> Cancel auto-launch
                            </button>
                          )}
                          {camp.status === 'paused' && (
                            <button
                              onClick={() => handleResumeCampaign(camp.id, camp.name)}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-emerald-700 hover:bg-emerald-50 font-medium flex items-center gap-2"
                            >
                              <Play className="h-3.5 w-3.5 text-emerald-600" />
                              Resume campaign
                            </button>
                          )}
                          {camp.status === 'draft' && (
                            <button
                              onClick={() => {
                                setMenuOpenId(null);
                                openCampaignWizard(camp.id, camp.draft_step || 2, camp.name);
                              }}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-indigo-700 hover:bg-indigo-50 font-medium flex items-center gap-2"
                            >
                              <Play className="h-3.5 w-3.5 text-indigo-600" />
                              Resume draft
                            </button>
                          )}
                          <button
                            onClick={() => handleDuplicateCampaign(camp.id)}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <Copy className="h-3.5 w-3.5 text-gray-500" />
                            Duplicate
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              setSelectedCampaignId(camp.id);
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <ExternalLink className="h-3.5 w-3.5 text-gray-500" />
                            View details
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              if (['active', 'warming_up'].includes(camp.status)) {
                                toast.error('Pause the campaign before editing its sequence.');
                              } else {
                                openCampaignWizard(camp.id, 2, camp.name);
                              }
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <Pencil className="h-3.5 w-3.5 text-gray-500" />
                            Edit sequence
                          </button>
                          <div className="h-px bg-gray-100 my-1" />
                          <button
                            onClick={() => handleSoftDelete(camp.id, camp.name)}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-rose-600 hover:bg-rose-50 font-medium flex items-center gap-2"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Start a new campaign Modal */}
      {newCampaignModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl border border-gray-100 p-6 space-y-6 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">
                  Start a new campaign
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Add leads first, then build the outreach sequence.
                </p>
              </div>
              <button
                onClick={() => setNewCampaignModalOpen(false)}
                className="p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                title="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* 2-Card Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              {/* Card 1: Build it your way */}
              <div className="flex flex-col rounded-2xl border border-gray-200 bg-white p-4 hover:border-indigo-300 hover:shadow-md transition-all group">
                {/* Visual Art Box */}
                <div className="relative h-32 rounded-xl border border-indigo-100 bg-gradient-to-br from-[#EEF0FF] to-[#E3E7FF] p-3 flex flex-col justify-between overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-[10px]">
                      in
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-white/80 text-[10px] font-semibold text-indigo-700 shadow-2xs">
                      Scratch
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    <div className="h-2 w-28 bg-white/70 rounded-full" />
                    <div className="h-2 w-16 bg-white/50 rounded-full" />
                  </div>
                </div>

                {/* Content */}
                <div className="mt-4 flex-1 flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-base font-extrabold text-gray-900">
                      Build it your way
                    </h3>
                    <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                      Create a draft and add leads from an existing lead list. Set the campaign name and supported lead filters.
                    </p>
                  </div>

                  <div className="space-y-2 pt-2">
                    <input
                      type="text"
                      value={scratchCampaignName}
                      onChange={(e) => setScratchCampaignName(e.target.value)}
                      placeholder="e.g. Q4 Growth Leaders"
                      className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      disabled={isCreatingCampaign}
                      onClick={async () => {
                        const name = scratchCampaignName.trim() || `Campaign #${campaigns.length + 1}`;
                        if (await handleCreateNewCampaign(name)) setNewCampaignModalOpen(false);
                      }}
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2.5 text-xs font-bold text-white shadow-xs transition-colors disabled:opacity-60"
                    >
                      {isCreatingCampaign ? 'Creating…' : 'Build from scratch'}
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Card 2: starter template */}
              <div className="flex flex-col rounded-2xl border-2 border-indigo-200/90 bg-indigo-50/10 p-4 hover:border-indigo-400 hover:shadow-md transition-all group relative">
                {/* Recommended Badge */}
                <div className="absolute -top-2.5 right-4 px-2 py-0.5 rounded-full bg-[#5145cd] text-white text-[10px] font-bold shadow-xs">
                  Recommended
                </div>

                {/* Visual Art Box */}
                <div className="relative h-32 rounded-xl border border-rose-100 bg-gradient-to-br from-[#FDECEC] to-[#FBE3E8] p-3 flex flex-col justify-between overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500 text-white font-bold text-[10px]">
                      %
                    </span>
                    <div className="flex items-center gap-1">
                    <span className="px-2 py-0.5 rounded-md bg-white/90 text-[10px] font-bold text-indigo-700 shadow-2xs">Starter sequence</span>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="h-2 w-32 bg-white/70 rounded-full" />
                    <div className="h-2 w-20 bg-white/50 rounded-full" />
                  </div>
                </div>

                {/* Content */}
                <div className="mt-4 flex-1 flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-base font-extrabold text-gray-900">
                      Use a starter template
                    </h3>
                    <p className="text-xs text-indigo-600 font-semibold mt-0.5">
                      Configure a sequence quickly.
                    </p>
                    <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                      Browse prebuilt sequences and choose a supported flow to customize.
                    </p>
                  </div>

                  <div className="pt-2">
                    <button
                      onClick={() => {
                        setNewCampaignModalOpen(false);
                        setIsTemplatesOpen(true);
                      }}
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl border border-indigo-200 bg-white hover:bg-indigo-50 px-4 py-2.5 text-xs font-bold text-indigo-700 shadow-2xs transition-colors"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                      Browse templates
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
