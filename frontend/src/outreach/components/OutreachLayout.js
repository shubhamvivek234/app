import React, { useState, useEffect } from 'react';
import {
  LayoutGrid,
  Send,
  Users,
  Mail,
  Mic,
  Settings as SettingsIcon,
  Plus,
  ChevronDown,
  Sparkles,
  Bookmark,
} from 'lucide-react';
import UnravlerLogo from '@/components/UnravlerLogo';

export default function OutreachLayout({ activeTab, onNavigate, onOpenWizard, hideTopHeader = false, isFullBleed = false, children }) {
  const [workspaceName, setWorkspaceName] = useState('My First Workspace');
  const [accountsCount, setAccountsCount] = useState(0);
  const [trialDays, setTrialDays] = useState(4);

  useEffect(() => {
    const fetchOverview = async () => {
      try {
        const token = localStorage.getItem('token');
        const [accRes, billRes] = await Promise.all([
          fetch('/api/v1/outreach/accounts', {
            headers: { Authorization: token ? `Bearer ${token}` : '' },
          }),
          fetch('/api/v1/outreach/billing/plans', {
            headers: { Authorization: token ? `Bearer ${token}` : '' },
          }),
        ]);

        if (accRes.ok) {
          const accs = await accRes.json();
          setAccountsCount(accs.length || 0);
        }
        if (billRes.ok) {
          const bill = await billRes.json();
          if (bill.trial_days_remaining) setTrialDays(bill.trial_days_remaining);
        }
      } catch (_) {}
    };
    fetchOverview();
  }, [activeTab]);

  const navItems = [
    { id: 'home', label: 'Home', icon: LayoutGrid },
    { id: 'campaigns', label: 'Campaigns', icon: Send },
    { id: 'engage', label: 'Engage', icon: Sparkles },
    { id: 'leads', label: 'Leads', icon: Users },
    { id: 'inbox', label: 'Inbox', icon: Mail },
    { id: 'voice', label: 'Voice', icon: Mic },
    { id: 'swipe', label: 'Swipe', icon: Bookmark },
  ];


  return (
    <div className="h-screen max-h-screen flex bg-neutral-50/50 font-sans text-gray-900 selection:bg-indigo-500 selection:text-white overflow-hidden">
      {/* Prosp Minimal Left Nav Sidebar matching all user screenshots */}
      <aside className="w-16 md:w-20 h-full max-h-screen border-r border-gray-200/80 bg-white flex flex-col items-center py-5 justify-between shrink-0 z-20">
        <div className="flex flex-col items-center gap-7 w-full">
          {/* Logo */}
          <div
            onClick={() => onNavigate('home')}
            className="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-600 via-indigo-500 to-sky-400 text-white flex items-center justify-center cursor-pointer shadow-xs hover:opacity-95 hover:scale-105 active:scale-95 transition-all p-2 focus:outline-none"
            title="Unravler Outreach - Home"
            aria-label="Unravler Outreach - Home"
          >
            <UnravlerLogo size="small" showText={false} color="white" />
          </div>

          {/* Navigation Items */}
          <nav className="flex flex-col items-center gap-4 w-full">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  title={item.label}
                  className={`flex flex-col items-center justify-center w-12 py-2 rounded-xl transition-all duration-200 group relative ${
                    isActive
                      ? 'bg-indigo-50/80 text-indigo-600 font-semibold'
                      : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/60'
                  }`}
                >
                  <Icon
                    className={`w-5 h-5 transition-transform duration-200 ${
                      isActive ? 'stroke-[2.5]' : 'stroke-[1.75] group-hover:scale-105'
                    }`}
                  />
                  <span className="text-[10px] mt-1 tracking-tight">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom Profile / Settings */}
        <div className="flex flex-col items-center gap-3 w-full">
          <button
            onClick={() => onNavigate('settings')}
            title="Settings"
            className={`w-10 h-10 rounded-xl flex items-center justify-center transition-colors ${
              activeTab === 'settings'
                ? 'bg-indigo-50 text-indigo-600 font-semibold'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100/60'
            }`}
          >
            <SettingsIcon className="w-5 h-5" />
          </button>

          <div
            onClick={() => onNavigate('settings')}
            className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold cursor-pointer hover:ring-2 hover:ring-indigo-300 transition-all"
          >
            SS
          </div>
        </div>
      </aside>

      {/* Main App Container */}
      <div className="flex-1 flex flex-col min-w-0 h-full max-h-screen overflow-hidden">
        {/* Top Header Bar matching Prosp screenshots */}
        {!hideTopHeader && (
          <header className="h-16 px-6 border-b border-gray-200/80 bg-white flex items-center justify-between shrink-0 z-10">
            <div className="flex items-center gap-3">
              {/* Workspace Switcher Pill */}
              <div
                onClick={() => onNavigate('settings')}
                className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 cursor-pointer transition-colors shadow-2xs"
              >
                <div className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-xs font-bold">
                  M
                </div>
                <div className="text-left">
                  <p className="text-xs font-bold text-gray-900 leading-tight flex items-center gap-1">
                    {workspaceName}
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  </p>
                  <p className="text-[10px] text-gray-400 leading-none">
                    {accountsCount} {accountsCount === 1 ? 'account' : 'accounts'}
                  </p>
                </div>
              </div>

              {/* Trial Status Pill */}
              <div className="hidden sm:flex items-center px-2.5 py-1 rounded-full border border-indigo-100 bg-indigo-50/60 text-indigo-700 text-[11px] font-medium">
                Trial ends in {trialDays} days
              </div>
            </div>

            {/* Primary Action Button matching media_1790104087386.png */}
            <div className="flex items-center gap-3">
              <button
                onClick={onOpenWizard}
                className="px-4 py-2 bg-[#2f2b60] hover:bg-[#252250] text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 shadow-xs transition-colors active:scale-98"
              >
                <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
                Create campaign
              </button>
            </div>
          </header>
        )}

        {/* Page Content Scroll Area */}
        <main className={`flex-1 min-h-0 h-full overflow-hidden ${isFullBleed ? 'flex flex-col' : 'overflow-y-auto'}`}>
          {children}
        </main>
      </div>
    </div>
  );
}
