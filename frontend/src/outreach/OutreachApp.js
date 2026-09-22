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

  return (
    <OutreachLayout
      activeTab={activeTab}
      onNavigate={(tab) => setActiveTab(tab)}
      onOpenWizard={() => setIsWizardOpen(true)}
    >
      {activeTab === 'home' && (
        <OutreachHome
          onNavigate={(tab) => setActiveTab(tab)}
          onOpenWizard={() => setIsWizardOpen(true)}
        />
      )}
      {activeTab === 'campaigns' && <OutreachCampaigns />}
      {activeTab === 'leads' && <OutreachLeads />}
      {activeTab === 'inbox' && <OutreachInbox />}
      {activeTab === 'voice' && <OutreachVoice />}
      {activeTab === 'settings' && <OutreachSettings />}

      {/* Campaign Wizard Overlay Modal */}
      {isWizardOpen && (
        <OutreachCampaignWizard
          onClose={() => setIsWizardOpen(false)}
          onSuccess={() => {
            setIsWizardOpen(false);
            setActiveTab('campaigns');
          }}
        />
      )}
    </OutreachLayout>
  );
}
