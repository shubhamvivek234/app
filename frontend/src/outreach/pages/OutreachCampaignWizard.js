import React, { useState, useEffect } from 'react';
import { ArrowLeft, ArrowRight, Save, Clock, ShieldCheck, CheckCircle2, Users } from 'lucide-react';
import SequenceCanvas from '../components/sequence/SequenceCanvas';
import ImportLeadsModal from '../components/ImportLeadsModal';

export default function OutreachCampaignWizard({ campaignId = 'new_campaign', onBack, onComplete }) {
  const [currentStep, setCurrentStep] = useState(2); // Default to Step 2 (Sequence Canvas)
  const [campaignName, setCampaignName] = useState('Connect and follow up');
  const [senders, setSenders] = useState([]);
  const [selectedSenders, setSelectedSenders] = useState([]);
  const [leadsModalOpen, setLeadsModalOpen] = useState(false);
  const [timezone, setTimezone] = useState('UTC');
  const [limits, setLimits] = useState({
    connection_invites: 20,
    messages: 20,
    voice_notes: 20,
    inmails: 20,
    profile_visits: 20,
    follows: 20,
    post_likes: 20,
    comments: 20,
  });

  useEffect(() => {
    // Fetch available senders
    const fetchSenders = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/v1/outreach/accounts', {
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          const data = await res.json();
          setSenders(data);
          if (data.length > 0) setSelectedSenders([data[0].id]);
        }
      } catch (err) {
        console.error('Failed to fetch senders:', err);
      }
    };
    fetchSenders();
  }, []);

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Top Navigation Bar (Part 1, Image 4) */}
      <div className="flex items-center justify-between px-6 py-3.5 border-b border-gray-200 bg-white z-20 shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Name your campaign</span>
            <input
              type="text"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              className="block font-bold text-gray-900 text-base focus:outline-none focus:border-b-2 focus:border-indigo-600 pb-0.5"
            />
          </div>
          <span className="text-[11px] font-semibold text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
            draft
          </span>
        </div>

        {/* Step Indicator Tabs */}
        <div className="flex items-center gap-6 text-xs font-semibold">
          <button
            onClick={() => setCurrentStep(1)}
            className={`flex items-center gap-1.5 ${currentStep === 1 ? 'text-indigo-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${currentStep === 1 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'}`}>
              1
            </span>
            Leads
          </button>

          <button
            onClick={() => setCurrentStep(2)}
            className={`flex items-center gap-1.5 ${currentStep === 2 ? 'text-indigo-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${currentStep === 2 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'}`}>
              2
            </span>
            Sequence
          </button>

          <button
            onClick={() => setCurrentStep(3)}
            className={`flex items-center gap-1.5 ${currentStep === 3 ? 'text-indigo-600' : 'text-gray-400 hover:text-gray-600'}`}
          >
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${currentStep === 3 ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-600'}`}>
              3
            </span>
            Launch & Senders
          </button>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2.5">
          <button className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-semibold text-gray-600 hover:bg-gray-50">
            Save as template
          </button>
          <button
            onClick={() => {
              if (currentStep < 3) setCurrentStep((s) => s + 1);
              else if (onComplete) onComplete();
            }}
            className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-sm"
          >
            {currentStep === 3 ? 'Review & Launch' : 'Next: Launch'}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Main Wizard Area */}
      <div className="flex-1 overflow-hidden">
        {/* Step 1: Leads Setup */}
        {currentStep === 1 && (
          <div className="max-w-4xl mx-auto px-6 py-12 text-center">
            <h2 className="text-2xl font-bold text-gray-900">Add your leads</h2>
            <p className="text-sm text-gray-500 mt-1 max-w-md mx-auto">
              Paste a LinkedIn search URL or upload a CSV spreadsheet. We will handle deduplication automatically.
            </p>
            <button
              onClick={() => setLeadsModalOpen(true)}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              + Import leads list
            </button>
          </div>
        )}

        {/* Step 2: Visual Canvas (Part 1, Image 4) */}
        {currentStep === 2 && (
          <SequenceCanvas campaignId={campaignId} />
        )}

        {/* Step 3: Launch, Multi-Sender Pooling & Safe Defaults (Part 2, Image 1) */}
        {currentStep === 3 && (
          <div className="max-w-3xl mx-auto px-6 py-10 overflow-y-auto h-full space-y-8">
            {/* Sender Selection (Multi-Account Pooling) */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="text-base font-bold text-gray-900">Who is sending?</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Pick the accounts that send this campaign. We automatically distribute leads across senders to keep each account safe.
              </p>

              <div className="mt-4">
                {senders.length === 0 ? (
                  <div className="p-6 text-center rounded-xl bg-gray-50 border border-gray-200 text-xs text-gray-500">
                    No LinkedIn accounts connected yet. Please connect an account in Settings.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {senders.map((s) => (
                      <label key={s.id} className="flex items-center justify-between p-3 rounded-xl border border-gray-200 hover:bg-gray-50 cursor-pointer">
                        <div className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={selectedSenders.includes(s.id)}
                            onChange={(e) => {
                              if (e.target.checked) setSelectedSenders([...selectedSenders, s.id]);
                              else setSelectedSenders(selectedSenders.filter((id) => id !== s.id));
                            }}
                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span className="font-semibold text-xs text-gray-800">{s.account_name}</span>
                        </div>
                        <span className="text-[11px] text-gray-400">{s.country_code} Proxy</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* When Should It Run? (Working Hours Grid) */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-gray-900">When should it run?</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Campaign actions only execute during local business hours to mimic human behavior.
                  </p>
                </div>
                <Clock className="h-5 w-5 text-indigo-500" />
              </div>

              <div className="p-4 rounded-xl bg-gray-50 text-xs text-gray-600 flex items-center justify-between">
                <span>Monday – Friday</span>
                <span className="font-bold text-gray-800">09:00 AM – 05:00 PM ({timezone})</span>
              </div>
            </div>

            {/* Daily Limits (Safe Defaults) */}
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-gray-900">Daily limits, applied per sender</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Daily action limits per sending account. Higher limits can increase restriction risk.
                  </p>
                </div>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full uppercase">
                  safe defaults
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div className="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/50">
                  <span className="text-xs text-gray-700">Connection invites:</span>
                  <strong className="text-sm font-bold text-indigo-600">{limits.connection_invites}/day</strong>
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/50">
                  <span className="text-xs text-gray-700">Messages:</span>
                  <strong className="text-sm font-bold text-indigo-600">{limits.messages}/day</strong>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Leads Modal */}
      <ImportLeadsModal
        isOpen={leadsModalOpen}
        onClose={() => setLeadsModalOpen(false)}
        campaignId={campaignId}
      />
    </div>
  );
}
