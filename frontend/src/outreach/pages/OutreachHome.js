import React, { useState, useEffect } from 'react';
import { Check, Plus, UserPlus, Calendar, ArrowRight, Sparkles } from 'lucide-react';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';

export default function OutreachHome({ onNavigate, onOpenWizard }) {
  const [userName, setUserName] = useState('There');
  const [recentCampaigns, setRecentCampaigns] = useState([]);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [connectedAccountsCount, setConnectedAccountsCount] = useState(0);

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
  }, []);

  const isAccountConnected = connectedAccountsCount > 0;
  const isCampaignCreated = recentCampaigns.length > 0;
  const completedSteps = 2 + (isAccountConnected ? 1 : 0) + (isCampaignCreated ? 1 : 0);

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

        {/* Onboarding Checklist Card matching Part 1 Image 1 */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs overflow-hidden">
          <div className="p-6 border-b border-gray-100 flex items-center gap-4">
            <div className="w-12 h-12 rounded-full border-4 border-indigo-100 flex items-center justify-center font-bold text-xs text-indigo-600 bg-indigo-50/50 shrink-0">
              {completedSteps}/4
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Finish setting up</h3>
              <p className="text-xs text-gray-500">
                You are {completedSteps * 25}% of the way to your first meeting.
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

            {/* Step 4: Invite teammate */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50 opacity-75">
              <div className="flex items-center gap-3.5">
                <div className="w-6 h-6 rounded-full bg-gray-100 text-gray-400 flex items-center justify-center font-bold text-[10px] shrink-0">
                  ?
                </div>
                <div>
                  <p className="font-medium text-gray-900">Invite your teammate</p>
                  <p className="text-gray-400 text-[11px]">Invite flow coming soon</p>
                </div>
              </div>
              <span className="text-gray-400 font-medium">unavailable</span>
            </div>

            {/* Step 5: Have a free session */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                <div className="w-6 h-6 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <Calendar className="w-3 h-3" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Have a free session with Jack (Our LinkedIn Expert)</p>
                  <p className="text-gray-400 text-[11px]">Worth $175. Free for you.</p>
                </div>
              </div>
              <button
                onClick={() => window.open('https://calendly.com', '_blank')}
                className="px-4 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-medium rounded-lg transition-colors"
              >
                Start
              </button>
            </div>
          </div>
        </div>

        {/* Recent Campaigns Card matching Part 1 Image 1 */}
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

        {/* Activity Placeholder matching Part 1 Image 1 */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6">
          <h3 className="font-bold text-gray-900 text-sm">No outreach activity yet.</h3>
          <p className="text-xs text-gray-400 mt-1">
            Campaign performance will appear here after outreach starts.
          </p>
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
