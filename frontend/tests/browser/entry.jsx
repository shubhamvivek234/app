import React from 'react';
import { createRoot } from 'react-dom/client';
import OutreachInbox from '../../src/outreach/pages/OutreachInbox';
import OutreachCampaignWizard from '../../src/outreach/pages/OutreachCampaignWizard';
import OutreachAnalytics from '../../src/outreach/pages/OutreachAnalytics';
import OutreachHome from '../../src/outreach/pages/OutreachHome';
import OutreachVoice from '../../src/outreach/pages/OutreachVoice';
import OutreachLeads from '../../src/outreach/pages/OutreachLeads';
import LeadTagManager from '../../src/outreach/components/LeadTagManager';
import SequenceCanvas from '../../src/outreach/components/sequence/SequenceCanvas';
import OutreachCampaigns from '../../src/outreach/pages/OutreachCampaigns';

const view = new URLSearchParams(window.location.search).get('view');
createRoot(document.getElementById('root')).render(view === 'wizard'
  ? <OutreachCampaignWizard campaignId="new" initialStep={3} />
  : view === 'analytics' ? <OutreachAnalytics />
  : view === 'templates' ? <OutreachCampaigns onOpenWizard={(id) => { document.body.dataset.openedDraft = id; }} />
  : view === 'home' ? <OutreachHome />
  : view === 'leads' ? <OutreachLeads onOpenWizard={(id) => { document.body.dataset.openedDraft = typeof id === 'string' ? id : 'new'; }} />
  : view === 'sequence' ? <SequenceCanvas campaignId="preview-campaign" />
  : view === 'tags' ? <LeadTagManager />
  : view === 'voice' ? <OutreachVoice /> : <OutreachInbox />);
