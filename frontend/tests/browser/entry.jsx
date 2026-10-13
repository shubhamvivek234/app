import React from 'react';
import { createRoot } from 'react-dom/client';
import OutreachInbox from '../../src/outreach/pages/OutreachInbox';
import OutreachCampaignWizard from '../../src/outreach/pages/OutreachCampaignWizard';
import OutreachAnalytics from '../../src/outreach/pages/OutreachAnalytics';

const view = new URLSearchParams(window.location.search).get('view');
createRoot(document.getElementById('root')).render(view === 'wizard'
  ? <OutreachCampaignWizard campaignId="new" initialStep={3} />
  : view === 'analytics' ? <OutreachAnalytics /> : <OutreachInbox />);
