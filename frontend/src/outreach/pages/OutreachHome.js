import React, { useState, useEffect } from 'react';
import { Check, Plus, UserPlus, Calendar, ArrowRight, Sparkles, Activity } from 'lucide-react';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';

export default function OutreachHome({ onNavigate, onOpenWizard }) {
  const [userName, setUserName] = useState('There');
  const [recentCampaigns, setRecentCampaigns] = useState([]);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [connectedAccountsCount, setConnectedAccountsCount] = useState(0);
  const [liveEvents, setLiveEvents] = useState([]);
  const [streamStatus, setStreamStatus] = useState('connecting');

  useEffect(() => {
    // Try to get user name from local storage or profile
    try {
      const stored = localStorage.getItem('user');
      if (stored) {
        const u = JSON.parse(stored);
        if (u.name) setUserName(u.name.split(' ')[0]);
      }
    } catch (_) {}

    // Fetch campaigns for recent list
    const loadOverview = async () => {
      try {
        const token = localStorage.getItem('token');
        const [campRes, accRes] = await Promise.all([
          fetch('/api/v1/outreach/campaigns', {
            headers: { Authorization: token ? `Bearer ${token}` : '' },
          }),
          fetch('/api/v1/outreach/accounts', {
            headers: { Authorization: token ? `Bearer ${token}` : '' },
          }),
        ]);

        if (campRes.ok) {
          const camps = await campRes.json();
          setRecentCampaigns(camps.slice(0, 5));
        }
        if (accRes.ok) {
          const accs = await accRes.json();
          setConnectedAccountsCount(accs.length);
        }
      } catch (err) {
        console.error('Failed to load overview:', err);
      }
    };

    loadOverview();

    // Connect to real-time live activity SSE stream ($0 infra cost)
    const token = localStorage.getItem('token');
    const sseUrl = `/api/v1/outreach/analytics/live-feed${token ? `?token=${encodeURIComponent(token)}` : ''}`;
    let eventSource;
    try {
      eventSource = new EventSource(sseUrl);

      eventSource.addEventListener('connected', () => {
        setStreamStatus('live');
      });

      eventSource.addEventListener('heartbeat', () => {
        setStreamStatus('live');
      });

      eventSource.addEventListener('task_completed', (e) => {
        try {
          const data = JSON.parse(e.data);
          setLiveEvents((prev) => [data, ...prev.slice(0, 19)]);
        } catch (_) {}
      });

      eventSource.onerror = () => {
        setStreamStatus('standby');
      };
    } catch (err) {
      setStreamStatus('standby');
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, []);

  const isAccountConnected = connectedAccountsCount > 0;
  const isCampaignCreated = recentCampaigns.length > 0;
  const completedSteps = 1 + (isAccountConnected ? 1 : 0) + (isCampaignCreated ? 1 : 0);

  return (
    <div className="min-h-screen bg-neutral-50/40 p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Welcome Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome, {userName}.
          </h1>
          <p className="text-xs text-gray-500 mt-1">Your workspace is ready.</p>
        </div>

        {/* Onboarding Checklist Card */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs overflow-hidden">
          <div className="p-6 border-b border-gray-100 flex items-center gap-4">
            <div className="w-12 h-12 rounded-full border-4 border-indigo-100 flex items-center justify-center font-bold text-xs text-indigo-600 bg-indigo-50/50 shrink-0">
              {completedSteps}/3
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Finish setting up</h3>
              <p className="text-xs text-gray-500">
                You are {Math.round((completedSteps / 3) * 100)}% of the way to your first meeting.
              </p>
            </div>
          </div>

          <div className="divide-y divide-gray-100 text-xs">
            {/* Step 1: Create your account */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5 stroke-[3]" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Create your account</p>
                  <p className="text-gray-400 text-[11px]">Done. Step 1 was on us.</p>
                </div>
              </div>
              <span className="text-gray-400 font-medium">Done</span>
            </div>

            {/* Step 2: Connect LinkedIn Account */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                {isAccountConnected ? (
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full border-2 border-gray-300 shrink-0" />
                )}
                <div>
                  <p className="font-medium text-gray-900">Connect your LinkedIn account</p>
                  <p className="text-gray-400 text-[11px]">Your first sender. Takes about a minute.</p>
                </div>
              </div>
              {isAccountConnected ? (
                <span className="text-gray-400 font-medium">Done</span>
              ) : (
                <button
                  onClick={() => setIsConnectModalOpen(true)}
                  className="px-4 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-medium rounded-lg transition-colors"
                >
                  Start
                </button>
              )}
            </div>

            {/* Step 3: Create your first campaign */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                {isCampaignCreated ? (
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full border-2 border-gray-300 shrink-0" />
                )}
                <div>
                  <p className="font-medium text-gray-900">Create your first campaign</p>
                  <p className="text-gray-400 text-[11px]">
                    {isCampaignCreated ? 'Your first campaign is saved.' : 'Build your multi-step sequence.'}
                  </p>
                </div>
              </div>
              {isCampaignCreated ? (
                <span className="text-gray-400 font-medium">Done</span>
              ) : (
                <button
                  onClick={onOpenWizard}
                  className="px-4 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-medium rounded-lg transition-colors"
                >
                  Start
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Recent Campaigns Card */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-900 text-sm">Recent campaigns</h3>
            <button
              onClick={() => onNavigate('campaigns')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
            >
              View all campaigns
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {recentCampaigns.length === 0 ? (
            <div className="py-8 text-center bg-gray-50/50 rounded-xl border border-dashed border-gray-200 text-gray-400 text-xs">
              No campaigns created yet. Click "+ Create campaign" to start your first sequence.
            </div>
          ) : (
            <div className="divide-y divide-gray-100 text-xs">
              {recentCampaigns.map((camp) => (
                <div
                  key={camp.id}
                  onClick={() => onNavigate('campaigns')}
                  className="py-3 flex items-center justify-between hover:bg-gray-50/60 px-2 rounded-lg cursor-pointer transition-colors"
                >
                  <span className="font-medium text-gray-900">{camp.name}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400 text-[11px]">
                      {new Date(camp.created_at || Date.now()).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600 capitalize">
                      {camp.status || 'draft'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Real-Time Live Activity Stream ($0 infra cost SSE) */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              <h3 className="font-bold text-gray-900 text-sm">Real-Time Outreach Activity</h3>
            </div>
            {streamStatus === 'live' ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live Feed
              </span>
            ) : streamStatus === 'connecting' ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                Connecting
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-gray-50 text-gray-500 border border-gray-200">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
                Standby
              </span>
            )}
          </div>

          {liveEvents.length === 0 ? (
            <div className="py-6 px-4 bg-gray-50/60 rounded-xl border border-gray-100 text-center">
              <p className="text-xs font-medium text-gray-700">Listening to live outreach pipeline</p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                Sent invitations, accepted invites, replies, and pre-warming visits stream here in real-time.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 text-xs">
              {liveEvents.map((evt, idx) => (
                <div key={evt.id || idx} className="py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-full bg-indigo-500" />
                    <span className="font-medium text-gray-900 capitalize">
                      {(evt.task_type || 'activity').replace(/_/g, ' ')}
                    </span>
                    {evt.lead_id && (
                      <span className="text-gray-400 text-[11px]">
                        Lead: {evt.lead_id.slice(0, 10)}...
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-gray-400 font-mono">
                    {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'just now'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Connect Account Modal */}
      <ConnectLinkedInModal
        isOpen={isConnectModalOpen}
        onClose={() => {
          setIsConnectModalOpen(false);
          setConnectedAccountsCount((c) => c + 1);
        }}
      />
    </div>
  );
}

