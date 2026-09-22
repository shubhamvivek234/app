import React, { useState } from 'react';
import OutreachLayout from './components/OutreachLayout';
import OutreachHome from './pages/OutreachHome';
import OutreachCampaigns from './pages/OutreachCampaigns';
import OutreachLeads from './pages/OutreachLeads';
import OutreachInbox from './pages/OutreachInbox';
import OutreachVoice from './pages/OutreachVoice';
import OutreachSettings from './pages/OutreachSettings';
import OutreachCampaignWizard from './pages/OutreachCampaignWizard';

export default function OutreachApp({ initialTab = 'home' }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardCampaignId, setWizardCampaignId] = useState('new');

  const handleOpenWizard = (campaignId = 'new') => {
    setWizardCampaignId(campaignId);
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
      onOpenWizard={() => handleOpenWizard('new')}
      hideTopHeader={isWizardOpen}
      isFullBleed={isWizardOpen}
    >
      {isWizardOpen ? (
        <OutreachCampaignWizard
          campaignId={wizardCampaignId}
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
              onOpenWizard={() => handleOpenWizard('new')}
            />
          )}
          {activeTab === 'campaigns' && (
            <OutreachCampaigns onOpenWizard={() => handleOpenWizard('new')} />
          )}
          {activeTab === 'leads' && <OutreachLeads />}
          {activeTab === 'inbox' && <OutreachInbox />}
          {activeTab === 'voice' && <OutreachVoice />}
          {activeTab === 'settings' && <OutreachSettings />}
        </>
      )}
    </OutreachLayout>
  );
}
