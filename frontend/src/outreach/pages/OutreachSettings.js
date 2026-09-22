import React, { useState, useEffect } from 'react';
import { Check, CreditCard, Shield, Sparkles, Minus, Plus } from 'lucide-react';
import OutreachAccounts from './OutreachAccounts';

export default function OutreachSettings({ initialTab = 'accounts' }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [interval, setInterval] = useState('monthly'); // 'annual' | 'quarterly' | 'monthly'
  const [seats, setSeats] = useState(1);
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialActive, setTrialActive] = useState(false);
  const [trialDaysLeft, setTrialDaysLeft] = useState(4);
  const [rateCards, setRateCards] = useState([]);
  const [featuresIncluded, setFeaturesIncluded] = useState([]);

  useEffect(() => {
    const fetchBilling = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/v1/outreach/billing/plans', {
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          const data = await res.json();
          setRateCards(data.rate_cards || []);
          setFeaturesIncluded(data.features_included || []);
          setTrialActive(data.trial_active || false);
          if (data.trial_days_remaining) setTrialDaysLeft(data.trial_days_remaining);
          if (data.subscription?.seats) setSeats(data.subscription.seats);
          if (data.subscription?.interval) setInterval(data.subscription.interval);
        }
      } catch (err) {
        console.error('Failed to load billing plans:', err);
      }
    };
    fetchBilling();
  }, []);

  const getActiveTier = () => {
    if (seats <= 5) return rateCards[0] || { annual: 61.99, quarterly: 69.99, monthly: 79.99, tier: '1-5' };
    if (seats <= 30) return rateCards[1] || { annual: 45.99, quarterly: 52.99, monthly: 59.99, tier: '6-30' };
    return rateCards[2] || { annual: 30.99, quarterly: 34.99, monthly: 39.99, tier: '30+' };
  };

  const activeTier = getActiveTier();
  const currentPrice = activeTier ? activeTier[interval] : 79.99;

  const handleStartTrial = async () => {
    setTrialLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/start-trial', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ seats, interval }),
      });
      if (res.ok) {
        setTrialActive(true);
        setTrialDaysLeft(4);
        alert('Your 4-day free trial has been activated!');
      }
    } catch (err) {
      console.error('Start trial failed:', err);
    } finally {
      setTrialLoading(false);
    }
  };

  const handleUpdateSeats = async (newSeats) => {
    if (newSeats < 1) return;
    setSeats(newSeats);
    try {
      const token = localStorage.getItem('token');
      await fetch('/api/v1/outreach/billing/update-seats', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ seats: newSeats }),
      });
    } catch (err) {
      console.error('Failed to update seats:', err);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-50/40 p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start">
          {/* Left Vertical Sub-Nav matching Part 3 Image 3 */}
          <div className="md:col-span-3 space-y-1">
            {[
              { id: 'accounts', label: 'Accounts' },
              { id: 'members', label: 'Members' },
              { id: 'billing', label: 'Billing' },
              { id: 'import_v1', label: 'Import from V1' },
              { id: 'help', label: 'Help' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full text-left px-3.5 py-2 rounded-lg text-xs font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-indigo-50 text-indigo-600 font-semibold shadow-xs'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100/60'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right Main Pane */}
          <div className="md:col-span-9">
            {activeTab === 'accounts' && <OutreachAccounts />}

            {activeTab === 'billing' && (
              <div className="space-y-6">
                {/* Billing Title & Description */}
                <div>
                  <h2 className="text-base font-bold text-gray-900">Billing</h2>
                  <p className="text-xs text-gray-500 mt-0.5 max-w-2xl leading-relaxed">
                    Simple per-account pricing. You only pay when your free trial ends. This workspace
                    is billed on its own subscription; payment methods are shared across your company.
                  </p>
                </div>

                {/* Billing Interval Toggle Pill matching Part 3 Image 4 */}
                <div className="flex items-center gap-1.5 bg-gray-100 p-1 rounded-xl w-fit text-xs font-medium text-gray-600">
                  <button
                    onClick={() => setInterval('annual')}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      interval === 'annual' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    <span>Annual</span>
                    <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">
                      save 23% • $240.79/yr back
                    </span>
                  </button>

                  <button
                    onClick={() => setInterval('quarterly')}
                    className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
                      interval === 'quarterly' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    <span>Quarterly</span>
                    <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">
                      save 13% • $133.77/yr back
                    </span>
                  </button>

                  <button
                    onClick={() => setInterval('monthly')}
                    className={`px-3.5 py-1.5 rounded-lg transition-all ${
                      interval === 'monthly' ? 'bg-white shadow-xs text-gray-900 font-semibold' : ''
                    }`}
                  >
                    Monthly
                  </button>
                </div>

                {/* Primary Plan Card (Royal Indigo matching Part 3 Image 4) */}
                <div className="bg-indigo-600 text-white rounded-2xl p-7 shadow-md space-y-6">
                  <div>
                    <span className="text-[10px] font-bold tracking-widest text-indigo-200 uppercase">
                      YOUR PLAN
                    </span>
                    <h3 className="text-2xl font-extrabold mt-1">4-day free trial</h3>
                    <p className="text-xs text-indigo-100 mt-1">
                      Then ${currentPrice} per account every 4 weeks, billed every 4 weeks, plus a 2.9%
                      processing fee. Cancel anytime.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <p className="text-xs font-semibold">How many seats?</p>
                    <p className="text-[11px] text-indigo-200">
                      One seat per LinkedIn account. The per-seat price drops as you add seats.
                    </p>

                    <div className="flex items-center gap-4 pt-1">
                      {/* Stepper */}
                      <div className="flex items-center bg-indigo-700/80 rounded-lg p-1 border border-indigo-500/50">
                        <button
                          onClick={() => handleUpdateSeats(Math.max(1, seats - 1))}
                          className="w-7 h-7 flex items-center justify-center rounded hover:bg-indigo-600 transition-colors text-white"
                        >
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="w-10 text-center text-sm font-bold">{seats}</span>
                        <button
                          onClick={() => handleUpdateSeats(seats + 1)}
                          className="w-7 h-7 flex items-center justify-center rounded hover:bg-indigo-600 transition-colors text-white"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <span className="text-xs font-medium text-indigo-100">
                        ${currentPrice} per account/4 weeks • {activeTier.label}
                      </span>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-indigo-500/40 space-y-3">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={handleStartTrial}
                        disabled={trialLoading || trialActive}
                        className="px-5 py-2.5 bg-white text-indigo-700 hover:bg-indigo-50 text-xs font-bold rounded-xl shadow-xs transition-colors disabled:opacity-75"
                      >
                        {trialActive
                          ? `Trial Active (${trialDaysLeft} days remaining)`
                          : `Start 4-day trial - ${interval.charAt(0).toUpperCase() + interval.slice(1)}`}
                      </button>
                      <button
                        onClick={() => alert('Payment method modal integration')}
                        className="px-5 py-2.5 bg-indigo-500/30 hover:bg-indigo-500/50 border border-indigo-400/40 text-white text-xs font-semibold rounded-xl transition-colors"
                      >
                        Add payment method
                      </button>
                    </div>
                    <p className="text-[11px] text-indigo-200">
                      Adding a card charges nothing. Your trial is free for 4 days.
                    </p>
                  </div>
                </div>

                {/* 2-Column Feature & Post-Trial Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Everything Included Card */}
                  <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-4">
                    <h3 className="font-bold text-gray-900 text-sm">Everything included</h3>
                    <ul className="space-y-2.5 text-xs text-gray-600">
                      {(featuresIncluded.length > 0
                        ? featuresIncluded
                        : [
                            'Unlimited campaigns, contacts, and messages',
                            'Every team member, free',
                            'Voice cloning',
                            'Unlimited LinkedIn accounts, each with a free proxy',
                            'Unified inbox across every account',
                            'Templates, analytics, API and webhooks',
                          ]
                      ).map((feat, idx) => (
                        <li key={idx} className="flex items-start gap-2.5">
                          <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Your Plan After the Trial Card */}
                  <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-3">
                    <h3 className="font-bold text-gray-900 text-sm">Your plan after the trial</h3>
                    <div>
                      <span className="text-3xl font-extrabold text-gray-900">${currentPrice}</span>
                      <span className="text-xs text-gray-500 ml-1">per account/4 weeks</span>
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed">
                      {interval.charAt(0).toUpperCase() + interval.slice(1)} term, billed $
                      {(currentPrice * seats).toFixed(2)} every 4 weeks per LinkedIn account — 1
                      four-week period per invoice. Quoted for {seats} {seats === 1 ? 'seat' : 'seats'}. A
                      2.9% processing fee applies to every invoice.
                    </p>
                    <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                      Standard support • 1 outbound specialist session / 12 weeks
                    </p>
                  </div>
                </div>

                {/* Rate Card Table matching Part 3 Image 4 */}
                <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
                  <h3 className="font-bold text-gray-900 text-sm">Rate card</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead>
                        <tr className="border-b border-gray-100 text-gray-400 font-medium">
                          <th className="pb-3 font-medium">Accounts</th>
                          <th className="pb-3 font-medium">Annual</th>
                          <th className="pb-3 font-medium">Quarterly</th>
                          <th className="pb-3 font-medium">Monthly</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {rateCards.map((rc) => {
                          const isCurrentTier = activeTier.tier === rc.tier;
                          return (
                            <tr
                              key={rc.tier}
                              className={`transition-colors ${
                                isCurrentTier ? 'bg-indigo-50/70 font-semibold' : 'hover:bg-gray-50/60'
                              }`}
                            >
                              <td className="py-3 px-2 flex items-center gap-2">
                                <span className={isCurrentTier ? 'text-indigo-900' : 'text-gray-900'}>
                                  {rc.label}
                                </span>
                                {isCurrentTier && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700">
                                    your plan
                                  </span>
                                )}
                              </td>
                              <td className="py-3 px-2 text-gray-700">${rc.annual.toFixed(2)}</td>
                              <td className="py-3 px-2 text-gray-700">${rc.quarterly.toFixed(2)}</td>
                              <td className="py-3 px-2 text-gray-700">${rc.monthly.toFixed(2)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-[11px] text-gray-400">
                    Prices are per account/4 weeks. Click a row or column to preview it.
                  </p>
                </div>

                {/* Billing Email Card matching Part 3 Image 4 */}
                <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-gray-900 text-sm">Billing email</h3>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Stripe sends invoices and receipts to this one address. Any company admin can change it.
                    </p>
                  </div>
                  <button
                    onClick={() => alert('Billing email management modal')}
                    className="px-4 py-2 border border-gray-200 text-gray-700 hover:bg-gray-50 rounded-lg text-xs font-medium transition-colors"
                  >
                    View billing email
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'members' && (
              <div className="bg-white rounded-2xl border border-gray-200/80 p-8 text-center space-y-3">
                <h3 className="font-bold text-gray-900 text-base">Workspace Members</h3>
                <p className="text-xs text-gray-500 max-w-sm mx-auto">
                  Every team member is free on Unravler Outreach. Invite collaborators to manage sequences and view inbox replies.
                </p>
                <button className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700">
                  Invite Teammate
                </button>
              </div>
            )}

            {(activeTab === 'import_v1' || activeTab === 'help') && (
              <div className="bg-white rounded-2xl border border-gray-200/80 p-8 text-center text-xs text-gray-400">
                Documentation and support options are available 24/7.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
