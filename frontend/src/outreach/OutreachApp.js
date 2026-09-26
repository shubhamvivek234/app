import React, { useState, useEffect, useCallback } from 'react';
import OutreachLayout from './components/OutreachLayout';
import OutreachHome from './pages/OutreachHome';
import OutreachCampaigns from './pages/OutreachCampaigns';
import OutreachAnalytics from './pages/OutreachAnalytics';
import OutreachLeads from './pages/OutreachLeads';
import OutreachInbox from './pages/OutreachInbox';
import OutreachVoice from './pages/OutreachVoice';
import OutreachSettings from './pages/OutreachSettings';
import OutreachCampaignWizard from './pages/OutreachCampaignWizard';
import OutreachEngage from './pages/OutreachEngage';
import OutreachSwipeFiles from './pages/OutreachSwipeFiles';

const VALID_TABS = ['home', 'campaigns', 'analytics', 'engage', 'leads', 'inbox', 'voice', 'swipe', 'settings'];

function parseQueryParams(fallbackTab = 'home') {
  if (typeof window === 'undefined') {
    return { tab: fallbackTab, isWizard: false, campaignId: 'new', step: 1, detailId: null };
  }
  const params = new URLSearchParams(window.location.search);
  const rawTab = params.get('tab');
  const tab = VALID_TABS.includes(rawTab) ? rawTab : fallbackTab;
  const isWizard = params.get('wizard') === 'true';
  const campaignId = params.get('campaignId') || 'new';
  const step = parseInt(params.get('step') || '1', 10);
  const detailId = params.get('detail') === 'true' && params.get('campaignId') ? params.get('campaignId') : null;

  return {
    tab,
    isWizard,
    campaignId: campaignId || 'new',
    step: isNaN(step) ? 1 : step,
    detailId,
  };
}

export default function OutreachApp({ initialTab = 'home' }) {
  const initial = parseQueryParams(initialTab);
  const [activeTab, setActiveTab] = useState(initial.tab);
  const [isWizardOpen, setIsWizardOpen] = useState(initial.isWizard);
  const [wizardCampaignId, setWizardCampaignId] = useState(initial.campaignId);
  const [wizardStep, setWizardStep] = useState(initial.step);
  const [wizardCampaignName, setWizardCampaignName] = useState('');
  const [selectedCampaignId, setSelectedCampaignId] = useState(initial.detailId);
  const [campaignsRefreshKey, setCampaignsRefreshKey] = useState(0);
  const [lastSavedDraft, setLastSavedDraft] = useState(null);

  // Sync state changes to browser URL via pushState
  const syncUrl = useCallback((tab, isWizard, campId, step, detailId, replace = false) => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);

    // Clear previous params
    ['tab', 'wizard', 'campaignId', 'step', 'detail'].forEach((p) => url.searchParams.delete(p));

    if (isWizard) {
      url.searchParams.set('tab', 'campaigns');
      url.searchParams.set('wizard', 'true');
      if (campId && campId !== 'new') url.searchParams.set('campaignId', campId);
      if (step && step !== 1) url.searchParams.set('step', String(step));
    } else if (tab === 'campaigns' && detailId) {
      url.searchParams.set('tab', 'campaigns');
      url.searchParams.set('campaignId', detailId);
      url.searchParams.set('detail', 'true');
    } else {
      url.searchParams.set('tab', tab || 'home');
    }

    const newUrl = url.pathname + url.search;
    const currentState = { tab, isWizard, campId, step, detailId };
    if (replace) {
      window.history.replaceState(currentState, '', newUrl);
    } else if (url.search !== window.location.search) {
      window.history.pushState(currentState, '', newUrl);
    }
  }, []);

  // Listen to browser Back / Forward buttons (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const parsed = parseQueryParams(initialTab);
      setActiveTab(parsed.tab);
      setIsWizardOpen(parsed.isWizard);
      setWizardCampaignId(parsed.campaignId);
      setWizardStep(parsed.step);
      setSelectedCampaignId(parsed.detailId);
    };

    // Ensure initial URL is cleanly populated if bare
    if (typeof window !== 'undefined' && !window.location.search) {
      syncUrl(initial.tab, initial.isWizard, initial.campaignId, initial.step, initial.detailId, true);
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [initialTab, initial.tab, initial.isWizard, initial.campaignId, initial.step, initial.detailId, syncUrl]);

  const handleNavigate = (tab) => {
    setIsWizardOpen(false);
    setSelectedCampaignId(null);
    setActiveTab(tab);
    syncUrl(tab, false, 'new', 2, null);
  };

  const handleOpenWizard = (campaignId = 'new', step = 1, name = '') => {
    const validId = typeof campaignId === 'string' && campaignId ? campaignId : 'new';
    const validStep = typeof step === 'number' ? step : 1;
    setWizardCampaignId(validId);
    setWizardStep(validStep);
    setWizardCampaignName(name || '');
    setIsWizardOpen(true);
    syncUrl('campaigns', true, validId, validStep, null);
  };

  const handleCloseWizard = (savedDraft) => {
    if (savedDraft && typeof savedDraft === 'object' && savedDraft.id) {
      setLastSavedDraft(savedDraft);
    }
    setIsWizardOpen(false);
    setActiveTab('campaigns');
    setSelectedCampaignId(null);
    setCampaignsRefreshKey(Date.now());
    syncUrl('campaigns', false, 'new', 2, null);
  };

  const handleSelectCampaign = (campId) => {
    setSelectedCampaignId(campId);
    syncUrl('campaigns', false, 'new', 2, campId);
  };

  return (
    <OutreachLayout
      activeTab={isWizardOpen ? 'campaigns' : activeTab}
      onNavigate={handleNavigate}
      onOpenWizard={() => handleOpenWizard('new', 1)}
      hideTopHeader={isWizardOpen}
      isFullBleed={isWizardOpen}
    >
      {isWizardOpen ? (
        <OutreachCampaignWizard
          key={`${wizardCampaignId}_${wizardStep}`}
          campaignId={wizardCampaignId}
          initialStep={wizardStep}
          initialName={wizardCampaignName}
          onBack={handleCloseWizard}
          onClose={handleCloseWizard}
          onComplete={() => {
            setIsWizardOpen(false);
            setActiveTab('campaigns');
            setSelectedCampaignId(null);
            setCampaignsRefreshKey(Date.now());
            syncUrl('campaigns', false, 'new', 2, null);
          }}
        />
      ) : (
        <>
          {activeTab === 'home' && (
            <OutreachHome
              onNavigate={handleNavigate}
              onOpenWizard={(id, step, name) => handleOpenWizard(id || 'new', step || 1, name || '')}
              onOpenCampaign={(id) => {
                setActiveTab('campaigns');
                handleSelectCampaign(id);
              }}
            />
          )}
          {activeTab === 'campaigns' && (
            <OutreachCampaigns
              key={`camp_list_${campaignsRefreshKey}`}
              refreshKey={campaignsRefreshKey}
              lastSavedDraft={lastSavedDraft}
              selectedCampaignId={selectedCampaignId}
              onSelectCampaign={handleSelectCampaign}
              onOpenWizard={(id, step, name) => handleOpenWizard(id || 'new', step || 1, name || '')}
            />
          )}
          {activeTab === 'analytics' && <OutreachAnalytics />}
          {activeTab === 'engage' && <OutreachEngage />}
          {activeTab === 'leads' && (
            <OutreachLeads onOpenWizard={() => handleOpenWizard('new', 1)} />
          )}
          {activeTab === 'inbox' && <OutreachInbox />}
          {activeTab === 'voice' && <OutreachVoice />}
          {activeTab === 'swipe' && <OutreachSwipeFiles />}
          {activeTab === 'settings' && <OutreachSettings />}
        </>
      )}
    </OutreachLayout>
  );
}
