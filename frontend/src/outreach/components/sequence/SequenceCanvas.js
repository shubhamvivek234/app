import React, { useState } from 'react';
import {
  Eye, UserPlus, MessageSquare, Mic, Mail, UserCheck, ThumbsUp, MessageCircle,
  CornerDownRight, Award, GitBranch, Clock, Plus, X, ZoomIn, ZoomOut, Maximize2,
  AlertCircle, CheckCircle2, Sparkles, ChevronRight, Edit3, Trash2
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

export default function SequenceCanvas({ campaignId, initialNodes, initialEdges, onSave }) {
  const [nodes, setNodes] = useState(initialNodes || [
    { id: 'node_1', type: 'visit_profile', title: 'Visit profile', delay_hours: 0, position: { x: 300, y: 50 } },
    { id: 'node_2', type: 'connection_request', title: 'Connection request', delay_hours: 0, config: { note: '' }, position: { x: 300, y: 200 } },
    { id: 'node_3', type: 'send_message', title: 'Send message', delay_hours: 24, config: { body: 'Hi {{first_name}}, thanks for connecting!' }, position: { x: 450, y: 350 } },
  ]);
  const [edges, setEdges] = useState(initialEdges || [
    { id: 'e1', source: 'node_1', target: 'node_2' },
    { id: 'e2', source: 'node_2', target: 'node_3', label: 'accepted' },
  ]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [activeBranchSource, setActiveBranchSource] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [bannerToast, setBannerToast] = useState('Tip: Your first Invite has no note. That is good — Invites with notes are often accepted less.');

  const handleAddStep = (actionType) => {
    const actionDef = ACTION_DEFINITIONS.find((a) => a.type === actionType) || { label: 'New Step' };
    const newNodeId = `node_${Date.now().toString().slice(-4)}`;
    const newNode = {
      id: newNodeId,
      type: actionType,
      title: actionDef.label,
      delay_hours: 24,
      config: {},
    };

    setNodes([...nodes, newNode]);

    if (activeBranchSource) {
      const newEdge = {
        id: `e_${Date.now().toString().slice(-4)}`,
        source: activeBranchSource.nodeId,
        target: newNodeId,
        label: activeBranchSource.label || null,
      };
      setEdges([...edges, newEdge]);
      setActiveBranchSource(null);
    }

    setPaletteOpen(false);
    setSelectedNodeId(newNodeId);
    setBannerToast(`${actionDef.label} added to sequence.`);
  };

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  return (
    <div className="relative flex h-full min-h-[750px] w-full bg-[#fafafa] overflow-hidden select-none">
      {/* Background Dot Grid */}
      <div
        className="absolute inset-0 opacity-40 pointer-events-none"
        style={{
          backgroundImage: 'radial-gradient(#cbd5e1 1.2px, transparent 1.2px)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* Top Floating Toast */}
      {bannerToast && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-2 text-xs font-medium text-emerald-800 shadow-sm animate-fade-in">
          <Sparkles className="h-4 w-4 text-emerald-600" />
          <span>{bannerToast}</span>
          <button onClick={() => setBannerToast(null)} className="ml-2 text-emerald-600 hover:text-emerald-900">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Zoom Controls (Top Left) */}
      <div className="absolute top-5 left-5 z-20 flex items-center gap-1 rounded-xl bg-white border border-gray-200 p-1 shadow-sm text-gray-600">
        <button onClick={() => setZoomLevel((z) => Math.max(z - 10, 60))} className="p-1.5 hover:bg-gray-100 rounded-lg">
          <ZoomOut className="h-4 w-4" />
        </button>
        <button onClick={() => setZoomLevel((z) => Math.min(z + 10, 140))} className="p-1.5 hover:bg-gray-100 rounded-lg">
          <ZoomIn className="h-4 w-4" />
        </button>
        <span className="px-2 text-xs font-semibold">{zoomLevel}%</span>
      </div>

      {/* Canvas Workflow View */}
      <div
        className="flex-1 flex flex-col items-center pt-20 pb-28 overflow-y-auto"
        style={{ transform: `scale(${zoomLevel / 100})`, transformOrigin: 'top center' }}
      >
        {/* Sequence Start Pill */}
        <div className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-1.5 text-xs font-semibold text-gray-500 shadow-sm mb-6">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          SEQUENCE START
        </div>

        {/* Nodes Pipeline */}
        <div className="flex flex-col items-center space-y-6 w-full max-w-xl">
          {nodes.map((node, index) => {
            const actionDef = ACTION_DEFINITIONS.find((a) => a.type === node.type) || { icon: Eye, color: 'text-indigo-600 bg-indigo-50', desc: '' };
            const Icon = actionDef.icon;
            const isSelected = selectedNodeId === node.id;

            return (
              <div key={node.id} className="flex flex-col items-center w-full">
                {/* Node Box */}
                <div
                  onClick={() => setSelectedNodeId(node.id)}
                  className={`relative w-96 rounded-2xl border bg-white p-4 shadow-sm transition-all cursor-pointer ${
                    isSelected ? 'border-indigo-600 ring-2 ring-indigo-500/20 shadow-md' : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  {/* Timing Pill */}
                  <div className="flex items-center justify-between pb-2 mb-2 border-b border-gray-100 text-[11px] text-gray-400">
                    <span className="flex items-center gap-1 font-medium text-gray-600">
                      <Clock className="h-3 w-3 text-gray-400" />
                      {node.delay_hours === 0 ? 'No delay' : `Wait ${Math.round(node.delay_hours / 24)} days, then`}
                    </span>
                    <Edit3 className="h-3.5 w-3.5 text-gray-400 hover:text-indigo-600" />
                  </div>

                  {/* Action Row */}
                  <div className="flex items-center gap-3">
                    <div className={`p-2.5 rounded-xl ${actionDef.color}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-bold text-gray-900 leading-tight">{node.title}</h4>
                      <p className="text-xs text-gray-400 truncate mt-0.5">
                        {node.config?.body || node.config?.note || actionDef.desc}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Connection Branching Buttons */}
                {node.type === 'connection_request' && (
                  <div className="flex items-center justify-center gap-8 mt-4">
                    <div className="flex flex-col items-center">
                      <span className="text-[10px] font-bold text-red-500 bg-red-50 px-2 py-0.5 rounded-full mb-2">
                        ✕ not accepted yet
                      </span>
                      <button
                        onClick={() => {
                          setActiveBranchSource({ nodeId: node.id, label: 'not accepted yet' });
                          setPaletteOpen(true);
                        }}
                        className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 border border-indigo-200 hover:bg-indigo-600 hover:text-white transition-colors"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    <div className="flex flex-col items-center">
                      <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full mb-2">
                        ✓ accepted
                      </span>
                      <button
                        onClick={() => {
                          setActiveBranchSource({ nodeId: node.id, label: 'accepted' });
                          setPaletteOpen(true);
                        }}
                        className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 border border-indigo-200 hover:bg-indigo-600 hover:text-white transition-colors"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Normal Step Add Button */}
                {node.type !== 'connection_request' && index === nodes.length - 1 && (
                  <div className="mt-4 flex flex-col items-center">
                    <button
                      onClick={() => {
                        setActiveBranchSource({ nodeId: node.id, label: null });
                        setPaletteOpen(true);
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-white shadow-md hover:bg-indigo-700 transition-colors"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Drawer: Step Palette (Part 1, Image 4) */}
      {paletteOpen && (
        <div className="absolute top-0 right-0 bottom-0 w-80 bg-white border-l border-gray-200 shadow-xl z-30 flex flex-col">
          <div className="flex items-center justify-between p-4 border-b border-gray-100">
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Add a step</h3>
              <p className="text-xs text-gray-400">Pick what happens next in this path.</p>
            </div>
            <button onClick={() => setPaletteOpen(false)} className="p-1 text-gray-400 hover:bg-gray-100 rounded-full">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Actions */}
            <div>
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400">
                LinkedIn Actions ({ACTION_DEFINITIONS.length})
              </span>
              <div className="grid grid-cols-2 gap-2 mt-2">
                {ACTION_DEFINITIONS.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button
                      key={action.type}
                      onClick={() => handleAddStep(action.type)}
                      className="flex flex-col items-start p-2.5 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 text-left transition-all group"
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
              <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400">
                Conditions ({CONDITION_DEFINITIONS.length})
              </span>
              <div className="grid grid-cols-2 gap-2 mt-2">
                {CONDITION_DEFINITIONS.map((cond) => {
                  const Icon = cond.icon;
                  return (
                    <button
                      key={cond.type}
                      onClick={() => handleAddStep(cond.type)}
                      className="flex flex-col items-start p-2.5 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 text-left transition-all group"
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

      {/* Right Drawer: Edit Step Inspector */}
      {!paletteOpen && selectedNode && (
        <div className="absolute top-0 right-0 bottom-0 w-80 bg-white border-l border-gray-200 shadow-xl z-30 p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <h3 className="font-bold text-gray-900 text-sm">Step Settings</h3>
              <button onClick={() => setSelectedNodeId(null)} className="p-1 text-gray-400 hover:bg-gray-100 rounded-full">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700">Delay Before Step</label>
                <div className="flex items-center gap-2 mt-1">
                  <input
                    type="number"
                    min={0}
                    value={Math.round(selectedNode.delay_hours / 24)}
                    onChange={(e) => {
                      const days = parseInt(e.target.value) || 0;
                      setNodes(nodes.map((n) => (n.id === selectedNode.id ? { ...n, delay_hours: days * 24 } : n)));
                    }}
                    className="w-20 rounded-xl border border-gray-300 px-3 py-1.5 text-xs text-center"
                  />
                  <span className="text-xs text-gray-500 font-medium">Days</span>
                </div>
              </div>

              {selectedNode.type === 'send_message' && (
                <div>
                  <label className="block text-xs font-semibold text-gray-700">Message Copy</label>
                  <textarea
                    rows={4}
                    value={selectedNode.config?.body || ''}
                    onChange={(e) => {
                      const body = e.target.value;
                      setNodes(nodes.map((n) => (n.id === selectedNode.id ? { ...n, config: { ...n.config, body } } : n)));
                    }}
                    placeholder="Hi {{first_name}}, loved your recent post on..."
                    className="mt-1 w-full rounded-xl border border-gray-300 p-2.5 text-xs font-mono"
                  />
                  <div className="flex gap-1.5 mt-1.5">
                    <span className="text-[10px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded font-mono">
                      {"{{first_name}}"}
                    </span>
                    <span className="text-[10px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded font-mono">
                      {"{{company_name}}"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={() => {
              setNodes(nodes.filter((n) => n.id !== selectedNode.id));
              setSelectedNodeId(null);
            }}
            className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-red-600 border border-red-200 rounded-xl hover:bg-red-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete Step
          </button>
        </div>
      )}
    </div>
  );
}
