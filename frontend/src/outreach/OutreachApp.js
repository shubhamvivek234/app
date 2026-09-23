import React, { useState } from 'react';
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

export default function OutreachApp({ initialTab = 'home' }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardCampaignId, setWizardCampaignId] = useState('new');
  const [wizardStep, setWizardStep] = useState(2);

  const handleOpenWizard = (campaignId = 'new', step = 2) => {
    const validId = typeof campaignId === 'string' && campaignId ? campaignId : 'new';
    const validStep = typeof step === 'number' ? step : 2;
    setWizardCampaignId(validId);
    setWizardStep(validStep);
    setIsWizardOpen(true);
  };

  const handleCloseWizard = () => {
    setIsWizardOpen(false);
  };

  return (
    <OutreachLayout
      activeTab={isWizardOpen ? 'campaigns' : activeTab}
      onNavigate={(tab) => {
        setIsWizardOpen(false);
        setActiveTab(tab);
      }}
      onOpenWizard={() => handleOpenWizard('new', 2)}
      hideTopHeader={isWizardOpen}
      isFullBleed={isWizardOpen}
    >
      {isWizardOpen ? (
        <OutreachCampaignWizard
          key={`${wizardCampaignId}_${wizardStep}`}
          campaignId={wizardCampaignId}
          initialStep={wizardStep}
          onBack={handleCloseWizard}
          onClose={handleCloseWizard}
          onComplete={() => {
            setIsWizardOpen(false);
            setActiveTab('campaigns');
          }}
        />
      ) : (
        <>
          {activeTab === 'home' && (
            <OutreachHome
              onNavigate={(tab) => setActiveTab(tab)}
              onOpenWizard={(id, step) => handleOpenWizard(id || 'new', step || 2)}
            />
          )}
          {activeTab === 'campaigns' && (
            <OutreachCampaigns
              onOpenWizard={(id, step) => handleOpenWizard(id || 'new', step || 2)}
            />
          )}
          {activeTab === 'analytics' && <OutreachAnalytics />}
          {activeTab === 'engage' && <OutreachEngage />}
          {activeTab === 'leads' && <OutreachLeads />}
          {activeTab === 'inbox' && <OutreachInbox />}
          {activeTab === 'voice' && <OutreachVoice />}
          {activeTab === 'swipe' && <OutreachSwipeFiles />}
          {activeTab === 'settings' && <OutreachSettings />}
        </>
      )}
    </OutreachLayout>
  );
}

